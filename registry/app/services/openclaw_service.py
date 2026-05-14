"""OpenClaw instance service.

Owns enrollment-token issuance, instance enrollment, heartbeat, policy
derivation, and audit ingestion for OpenClaw instances. Each OpenClaw
instance is backed by an Agent row so it rides the existing governance
pipeline (DRAFT → SUBMITTED → ... → ACTIVE).
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from flask import current_app

from app import db
from app.models.agent import (
    Agent,
    AgentStatus,
    AuthMethod,
    Classification,
    DataSensitivity,
    EndpointType,
    RiskTier,
)
from app.models.openclaw import (
    OpenClawEnrollmentToken,
    OpenClawInstance,
    OpenClawInstanceStatus,
)


class OpenClawServiceError(Exception):
    pass


class EnrollmentTokenInvalid(OpenClawServiceError):
    pass


class InstanceNotFoundError(OpenClawServiceError):
    pass


INSTANCE_JWT_TTL_SECONDS = 30 * 24 * 3600
ENROLLMENT_TOKEN_TTL_SECONDS = 24 * 3600


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class OpenClawService:
    @staticmethod
    def issue_enrollment_token(
        tenant_id: str,
        created_by_user_id: Optional[uuid.UUID],
        ttl_seconds: int = ENROLLMENT_TOKEN_TTL_SECONDS,
    ) -> tuple[str, OpenClawEnrollmentToken]:
        token = secrets.token_urlsafe(32)
        record = OpenClawEnrollmentToken(
            tenant_id=tenant_id,
            token_hash=_hash_token(token),
            created_by=created_by_user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        db.session.add(record)
        db.session.commit()
        return token, record

    @staticmethod
    def enroll(
        enrollment_token: str,
        tenant_id: str,
        machine_id: str,
        instance_fingerprint: dict,
        plugin_version: Optional[str],
        openclaw_version: Optional[str] = None,
    ) -> tuple[OpenClawInstance, str]:
        token_hash = _hash_token(enrollment_token)
        token_row = OpenClawEnrollmentToken.query.filter_by(token_hash=token_hash).first()
        if token_row is None or not token_row.is_usable():
            raise EnrollmentTokenInvalid("Enrollment token is missing, expired, or already used")
        if token_row.tenant_id != tenant_id:
            raise EnrollmentTokenInvalid("Enrollment token does not belong to this tenant")

        existing = OpenClawInstance.query.filter_by(
            tenant_id=tenant_id, machine_id=machine_id
        ).first()
        if existing is not None:
            jwt_str = OpenClawService._issue_instance_jwt(existing)
            existing.plugin_version = plugin_version or existing.plugin_version
            existing.openclaw_version = openclaw_version or existing.openclaw_version
            existing.last_heartbeat_at = datetime.now(timezone.utc)
            db.session.commit()
            return existing, jwt_str

        agent = Agent(
            tenant_id=tenant_id,
            name=f"openclaw-{machine_id[:12]}",
            version="0.0.0",
            description="OpenClaw instance registered via openclaw-recursant plugin",
            owner_id=str(token_row.created_by) if token_row.created_by else "system",
            team_id="openclaw",
            contact_email="openclaw@local",
            classification=Classification.INTERNAL,
            data_sensitivity=DataSensitivity.PII,
            risk_tier=RiskTier.MEDIUM,
            status=AgentStatus.DRAFT,
            endpoint_type=EndpointType.OPENCLAW,
            endpoint_url=f"local://{machine_id}",
            endpoint_auth_method=AuthMethod.API_KEY,
            endpoint_timeout_ms=30000,
            endpoint_agent_protocol="A2A",
        )
        db.session.add(agent)
        db.session.flush()

        instance = OpenClawInstance(
            agent_id=agent.id,
            tenant_id=tenant_id,
            machine_id=machine_id,
            instance_fingerprint=instance_fingerprint,
            os=instance_fingerprint.get("os") if isinstance(instance_fingerprint, dict) else None,
            openclaw_version=openclaw_version,
            plugin_version=plugin_version,
            status=OpenClawInstanceStatus.PENDING,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.session.add(instance)
        db.session.flush()

        token_row.consumed_at = datetime.now(timezone.utc)
        token_row.consumed_by_instance_id = instance.id
        db.session.commit()

        return instance, OpenClawService._issue_instance_jwt(instance)

    @staticmethod
    def heartbeat(
        instance_id: uuid.UUID,
        plugin_version: Optional[str] = None,
        extras: Optional[dict] = None,
    ) -> OpenClawInstance:
        instance = db.session.get(OpenClawInstance, instance_id)
        if instance is None:
            raise InstanceNotFoundError(str(instance_id))
        if plugin_version:
            instance.plugin_version = plugin_version
        instance.last_heartbeat_at = datetime.now(timezone.utc)
        if instance.status == OpenClawInstanceStatus.PENDING and instance.agent.status == AgentStatus.ACTIVE:
            instance.status = OpenClawInstanceStatus.ACTIVE
        db.session.commit()
        return instance

    @staticmethod
    def get_policy_for_instance(instance: OpenClawInstance) -> dict:
        agent = instance.agent
        is_active = agent.status == AgentStatus.ACTIVE and instance.status in (
            OpenClawInstanceStatus.PENDING,
            OpenClawInstanceStatus.ACTIVE,
        )
        return {
            "version": int(agent.updated_at.timestamp()) if agent.updated_at else 0,
            "allowed_tools": "*" if is_active else [],
            "blocked_tools": [] if is_active else ["*"],
            "rate_limit": {"requests_per_minute": 60},
            "pii_redaction": agent.data_sensitivity in (DataSensitivity.PII, DataSensitivity.PHI),
        }

    @staticmethod
    def revoke(instance_id: uuid.UUID) -> OpenClawInstance:
        instance = db.session.get(OpenClawInstance, instance_id)
        if instance is None:
            raise InstanceNotFoundError(str(instance_id))
        instance.status = OpenClawInstanceStatus.REVOKED
        instance.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        return instance

    @staticmethod
    def _issue_instance_jwt(instance: OpenClawInstance) -> str:
        payload = {
            "sub": f"openclaw:{instance.id}",
            "kind": "openclaw_instance",
            "instance_id": str(instance.id),
            "agent_id": str(instance.agent_id),
            "tenant_id": instance.tenant_id,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=INSTANCE_JWT_TTL_SECONDS),
        }
        return jwt.encode(
            payload,
            current_app.config["JWT_SECRET_KEY"],
            algorithm="HS256",
        )

    @staticmethod
    def decode_instance_jwt(token: str) -> dict:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
        )
        if payload.get("kind") != "openclaw_instance":
            raise jwt.InvalidTokenError("Not an OpenClaw instance JWT")
        return payload
