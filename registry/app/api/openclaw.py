"""OpenClaw instance API.

Endpoints:
  POST /v1/openclaw/enrollment-tokens     (admin) — issue one-time token
  POST /v1/openclaw/instances/enroll      (token) — exchange token for JWT
  POST /v1/openclaw/instances/heartbeat   (instance JWT) — liveness
  GET  /v1/openclaw/instances/policy      (instance JWT) — current policy
  POST /v1/openclaw/instances/audit       (instance JWT) — push audit batch
  POST /v1/openclaw/instances/deregister  (instance JWT) — graceful shutdown
  GET  /v1/openclaw/instances             (admin) — list
  GET  /v1/openclaw/instances/<id>        (admin) — detail
  POST /v1/openclaw/instances/<id>/revoke (admin) — revoke
"""
import uuid
from functools import wraps

import jwt
from flask import g, jsonify, request

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.openclaw import OpenClawInstance, OpenClawInstanceStatus
from app.models.user import GroupType
from app.services.audit_service import AuditService
from app.services.openclaw_service import (
    EnrollmentTokenInvalid,
    InstanceNotFoundError,
    OpenClawService,
)


def _instance_jwt_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Missing or malformed Authorization header"}), 401
        try:
            payload = OpenClawService.decode_instance_jwt(parts[1])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Instance token expired"}), 401
        except jwt.InvalidTokenError as exc:
            return jsonify({"error": f"Invalid instance token: {exc}"}), 401

        instance = OpenClawInstance.query.filter_by(id=uuid.UUID(payload["instance_id"])).first()
        if instance is None or instance.status == OpenClawInstanceStatus.REVOKED:
            return jsonify({"error": "Instance not found or revoked"}), 403
        g.openclaw_instance = instance
        return fn(*args, **kwargs)

    return wrapped


def _tenant_id() -> str:
    return request.headers.get("X-Tenant-ID", "default")


def _instance_to_dict(instance: OpenClawInstance) -> dict:
    return {
        "id": str(instance.id),
        "agent_id": str(instance.agent_id),
        "tenant_id": instance.tenant_id,
        "machine_id": instance.machine_id,
        "os": instance.os,
        "openclaw_version": instance.openclaw_version,
        "plugin_version": instance.plugin_version,
        "status": instance.status.value,
        "enrolled_at": instance.enrolled_at.isoformat() if instance.enrolled_at else None,
        "last_heartbeat_at": instance.last_heartbeat_at.isoformat() if instance.last_heartbeat_at else None,
    }


@api_bp.route("/openclaw/enrollment-tokens", methods=["POST"])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def issue_enrollment_token():
    data = request.get_json(silent=True) or {}
    tenant_id = data.get("tenant_id") or _tenant_id()
    ttl_seconds = int(data.get("ttl_seconds", 24 * 3600))

    user_info = g.current_user
    created_by = uuid.UUID(user_info["id"]) if user_info.get("id") else None

    token, record = OpenClawService.issue_enrollment_token(
        tenant_id=tenant_id,
        created_by_user_id=created_by,
        ttl_seconds=ttl_seconds,
    )
    AuditService.log("openclaw.enrollment_token.issued", "openclaw_enrollment_token", record.id)
    return (
        jsonify(
            {
                "token": token,
                "expires_at": record.expires_at.isoformat(),
                "tenant_id": record.tenant_id,
            }
        ),
        201,
    )


@api_bp.route("/openclaw/instances/enroll", methods=["POST"])
def enroll_instance():
    data = request.get_json(silent=True) or {}
    token = data.get("enrollment_token")
    if not token:
        return jsonify({"error": "enrollment_token is required"}), 400
    tenant_id = data.get("tenant_id") or _tenant_id()
    machine_id = data.get("machine_id")
    fingerprint = data.get("instance_fingerprint") or {}
    if not machine_id:
        return jsonify({"error": "machine_id is required"}), 400

    try:
        instance, instance_jwt = OpenClawService.enroll(
            enrollment_token=token,
            tenant_id=tenant_id,
            machine_id=machine_id,
            instance_fingerprint=fingerprint,
            plugin_version=data.get("plugin_version"),
            openclaw_version=data.get("openclaw_version"),
        )
    except EnrollmentTokenInvalid as exc:
        return jsonify({"error": str(exc)}), 400

    return (
        jsonify(
            {
                "agent_id": str(instance.agent_id),
                "instance_id": str(instance.id),
                "jwt": instance_jwt,
                "status": instance.status.value,
            }
        ),
        201,
    )


@api_bp.route("/openclaw/instances/heartbeat", methods=["POST"])
@_instance_jwt_required
def heartbeat_instance():
    instance: OpenClawInstance = g.openclaw_instance
    data = request.get_json(silent=True) or {}
    try:
        updated = OpenClawService.heartbeat(
            instance.id,
            plugin_version=data.get("plugin_version"),
            extras=data,
        )
    except InstanceNotFoundError:
        return jsonify({"error": "Instance not found"}), 404
    return jsonify({"status": updated.status.value})


@api_bp.route("/openclaw/instances/policy", methods=["GET"])
@_instance_jwt_required
def get_instance_policy():
    instance: OpenClawInstance = g.openclaw_instance
    return jsonify(OpenClawService.get_policy_for_instance(instance))


@api_bp.route("/openclaw/instances/audit", methods=["POST"])
@_instance_jwt_required
def push_audit():
    instance: OpenClawInstance = g.openclaw_instance
    data = request.get_json(silent=True) or {}
    events = data.get("events") or []
    if not isinstance(events, list):
        return jsonify({"error": "events must be a list"}), 400
    for event in events:
        if not isinstance(event, dict):
            continue
        AuditService.log(
            f"openclaw.{event.get('type', 'unknown')}",
            "openclaw_instance",
            instance.id,
            detail={
                "decision": event.get("decision"),
                "decision_reason": event.get("decisionReason"),
                "payload": event.get("payload"),
                "timestamp": event.get("timestamp"),
            },
        )
    return jsonify({"accepted": len(events)})


@api_bp.route("/openclaw/instances/deregister", methods=["POST"])
@_instance_jwt_required
def deregister_instance():
    instance: OpenClawInstance = g.openclaw_instance
    OpenClawService.revoke(instance.id)
    AuditService.log("openclaw.instance.deregistered", "openclaw_instance", instance.id)
    return jsonify({"status": "revoked"})


@api_bp.route("/openclaw/instances", methods=["GET"])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_instances():
    tenant_id = _tenant_id()
    instances = (
        OpenClawInstance.query.filter_by(tenant_id=tenant_id)
        .order_by(OpenClawInstance.enrolled_at.desc())
        .all()
    )
    return jsonify({"instances": [_instance_to_dict(i) for i in instances]})


@api_bp.route("/openclaw/instances/<uuid:instance_id>", methods=["GET"])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_instance(instance_id):
    instance = OpenClawInstance.query.filter_by(id=instance_id).first()
    if instance is None:
        return jsonify({"error": "Instance not found"}), 404
    return jsonify(_instance_to_dict(instance))


@api_bp.route("/openclaw/instances/<uuid:instance_id>/revoke", methods=["POST"])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def revoke_instance(instance_id):
    try:
        instance = OpenClawService.revoke(instance_id)
    except InstanceNotFoundError:
        return jsonify({"error": "Instance not found"}), 404
    AuditService.log("openclaw.instance.revoked", "openclaw_instance", instance.id)
    return jsonify(_instance_to_dict(instance))
