"""Business logic for stage-based guardrail configurations."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app import db
from app.models.guardrail import (
    EnforcementMode,
    Guardrail,
    GuardrailStatus,
)
from app.models.guardrail_config import GuardrailConfig, GuardrailConfigEntry

logger = logging.getLogger(__name__)


class GuardrailConfigServiceError(Exception):
    pass


class GuardrailConfigNotFoundError(GuardrailConfigServiceError):
    pass


class GuardrailConfigValidationError(GuardrailConfigServiceError):
    pass


class GuardrailConfigService:
    """Service for stage-based guardrail configuration management."""

    # --- CRUD ---

    @staticmethod
    def create_config(data: dict, created_by: str, tenant_id: str = 'default') -> GuardrailConfig:
        config = GuardrailConfig(
            name=data['name'],
            description=data.get('description'),
            created_by=created_by,
            tenant_id=tenant_id,
        )
        db.session.add(config)
        db.session.commit()
        logger.info("guardrail_config_created id=%s name=%s", config.id, config.name)
        return config

    @staticmethod
    def update_config(config_id: UUID, data: dict, tenant_id: str = 'default') -> GuardrailConfig:
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)
        for field in ('name', 'description'):
            if field in data:
                setattr(config, field, data[field])
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return config

    @staticmethod
    def delete_config(config_id: UUID, tenant_id: str = 'default'):
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)
        if config.is_active:
            raise GuardrailConfigValidationError('Cannot delete the active configuration')
        db.session.delete(config)
        db.session.commit()

    @staticmethod
    def get_config(config_id: UUID, tenant_id: str = 'default') -> GuardrailConfig:
        return GuardrailConfigService._get_or_404(config_id, tenant_id)

    @staticmethod
    def list_configs(tenant_id: str = 'default', page: int = 1, per_page: int = 50):
        return GuardrailConfig.query.filter_by(
            tenant_id=tenant_id,
        ).order_by(
            GuardrailConfig.is_active.desc(),
            GuardrailConfig.updated_at.desc(),
        ).paginate(page=page, per_page=per_page, error_out=False)

    # --- Activate / deactivate ---

    @staticmethod
    def activate_config(config_id: UUID, activated_by: str, tenant_id: str = 'default') -> GuardrailConfig:
        """Atomically swap the active configuration."""
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)

        # Deactivate current active config
        GuardrailConfig.query.filter(
            GuardrailConfig.tenant_id == tenant_id,
            GuardrailConfig.is_active.is_(True),
        ).update({'is_active': False, 'updated_at': datetime.now(timezone.utc)})

        config.is_active = True
        config.activated_by = activated_by
        config.activated_at = datetime.now(timezone.utc)
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("guardrail_config_activated id=%s name=%s", config.id, config.name)
        return config

    # --- Clone ---

    @staticmethod
    def clone_config(config_id: UUID, new_name: str, created_by: str, tenant_id: str = 'default') -> GuardrailConfig:
        source = GuardrailConfigService._get_or_404(config_id, tenant_id)

        clone = GuardrailConfig(
            name=new_name,
            description=f'Cloned from {source.name}',
            created_by=created_by,
            tenant_id=tenant_id,
        )
        db.session.add(clone)
        db.session.flush()

        for entry in source.entries.all():
            new_entry = GuardrailConfigEntry(
                config_id=clone.id,
                guardrail_id=entry.guardrail_id,
                enforcement_mode_override=entry.enforcement_mode_override,
                enabled=entry.enabled,
                priority_override=entry.priority_override,
                config_override=entry.config_override,
            )
            db.session.add(new_entry)

        db.session.commit()
        return clone

    # --- Diff ---

    @staticmethod
    def diff_configs(config_a_id: UUID, config_b_id: UUID, tenant_id: str = 'default') -> dict:
        config_a = GuardrailConfigService._get_or_404(config_a_id, tenant_id)
        config_b = GuardrailConfigService._get_or_404(config_b_id, tenant_id)

        entries_a = {str(e.guardrail_id): e for e in config_a.entries.all()}
        entries_b = {str(e.guardrail_id): e for e in config_b.entries.all()}

        all_guardrail_ids = set(entries_a.keys()) | set(entries_b.keys())
        diffs = []

        for gid in all_guardrail_ids:
            ea = entries_a.get(gid)
            eb = entries_b.get(gid)

            if ea and not eb:
                diffs.append({
                    'guardrail_id': gid,
                    'change': 'removed_in_b',
                    'a': {'enabled': ea.enabled, 'enforcement_mode': ea.enforcement_mode_override, 'priority': ea.priority_override},
                })
            elif eb and not ea:
                diffs.append({
                    'guardrail_id': gid,
                    'change': 'added_in_b',
                    'b': {'enabled': eb.enabled, 'enforcement_mode': eb.enforcement_mode_override, 'priority': eb.priority_override},
                })
            else:
                changes = {}
                if ea.enabled != eb.enabled:
                    changes['enabled'] = {'a': ea.enabled, 'b': eb.enabled}
                if ea.enforcement_mode_override != eb.enforcement_mode_override:
                    changes['enforcement_mode'] = {'a': ea.enforcement_mode_override, 'b': eb.enforcement_mode_override}
                if ea.priority_override != eb.priority_override:
                    changes['priority'] = {'a': ea.priority_override, 'b': eb.priority_override}
                if changes:
                    diffs.append({
                        'guardrail_id': gid,
                        'change': 'modified',
                        'details': changes,
                    })

        return {
            'config_a': {'id': str(config_a.id), 'name': config_a.name},
            'config_b': {'id': str(config_b.id), 'name': config_b.name},
            'differences': diffs,
            'total_changes': len(diffs),
        }

    # --- Entry CRUD ---

    @staticmethod
    def add_entry(config_id: UUID, data: dict, tenant_id: str = 'default') -> GuardrailConfigEntry:
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)

        entry = GuardrailConfigEntry(
            config_id=config.id,
            guardrail_id=data['guardrail_id'],
            enforcement_mode_override=data.get('enforcement_mode_override'),
            enabled=data.get('enabled', True),
            priority_override=data.get('priority_override'),
            config_override=data.get('config_override'),
        )
        db.session.add(entry)
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return entry

    @staticmethod
    def remove_entry(config_id: UUID, entry_id: UUID, tenant_id: str = 'default'):
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)
        entry = GuardrailConfigEntry.query.filter_by(
            id=entry_id, config_id=config.id,
        ).first()
        if not entry:
            raise GuardrailConfigNotFoundError('Entry not found')
        db.session.delete(entry)
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def list_entries(config_id: UUID, tenant_id: str = 'default') -> list[GuardrailConfigEntry]:
        config = GuardrailConfigService._get_or_404(config_id, tenant_id)
        return config.entries.all()

    # --- Effective guardrails ---

    @staticmethod
    def get_effective_guardrails(guardrails: list[Guardrail], tenant_id: str = 'default') -> list[Guardrail]:
        """Apply active config overrides to a list of guardrails.

        Returns the modified list sorted by (overridden) priority.
        """
        active_config = GuardrailConfig.query.filter_by(
            tenant_id=tenant_id,
            is_active=True,
        ).first()

        if not active_config:
            return guardrails

        entries_by_guardrail = {
            str(e.guardrail_id): e for e in active_config.entries.all()
        }

        effective = []
        for g in guardrails:
            entry = entries_by_guardrail.get(str(g.id))
            if entry:
                if not entry.enabled:
                    continue  # Skip disabled guardrails
                # Apply overrides (modify in-place on detached-ish objects)
                if entry.enforcement_mode_override:
                    g.enforcement_mode = EnforcementMode(entry.enforcement_mode_override)
                if entry.priority_override is not None:
                    g.priority = entry.priority_override
                if entry.config_override:
                    merged = dict(g.config or {})
                    merged.update(entry.config_override)
                    g.config = merged
            effective.append(g)

        return sorted(effective, key=lambda g: g.priority)

    # --- Helpers ---

    @staticmethod
    def _get_or_404(config_id: UUID, tenant_id: str) -> GuardrailConfig:
        config = GuardrailConfig.query.filter_by(
            id=config_id, tenant_id=tenant_id,
        ).first()
        if not config:
            raise GuardrailConfigNotFoundError(f'Config {config_id} not found')
        return config
