"""Audit logging service for immutable compliance-grade logging."""

import logging
from uuid import UUID

from flask import g, request
from sqlalchemy import and_

from app import db
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Service for creating and querying immutable audit log entries."""

    @staticmethod
    def log(action, resource_type, resource_id=None, resource_name=None, detail=None):
        """
        Record an audit log entry.

        Reads user info from g.current_user, IP from request.remote_addr,
        and tenant_id from X-Tenant-ID header.
        """
        try:
            user_info = getattr(g, 'current_user', None)
            user_id = None
            username = 'system'

            if user_info:
                user_id = user_info.get('id')
                username = user_info.get('username', 'unknown')

            ip_address = request.remote_addr if request else None
            tenant_id = request.headers.get('X-Tenant-ID', 'default') if request else 'default'

            entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                detail=detail,
                ip_address=ip_address,
                tenant_id=tenant_id,
            )
            db.session.add(entry)
            db.session.commit()
            return entry
        except Exception:
            logger.exception("Failed to write audit log entry")
            db.session.rollback()
            return None

    @staticmethod
    def list_logs(tenant_id, action=None, resource_type=None, resource_id=None,
                  user_id=None, date_from=None, date_to=None, page=1, per_page=50):
        """
        Query audit logs with filters. Returns (logs, total, pages).
        """
        query = AuditLog.query.filter(AuditLog.tenant_id == tenant_id)

        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if resource_id:
            query = query.filter(AuditLog.resource_id == resource_id)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)

        query = query.order_by(AuditLog.timestamp.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    @staticmethod
    def get_log(log_id):
        """Get a single audit log entry by ID."""
        return db.session.get(AuditLog, log_id)
