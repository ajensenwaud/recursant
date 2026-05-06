#!/usr/bin/env python3
"""Seed the observability dashboard with historical demo data.

Generates realistic guardrails (with assignments), mesh registrations (with
sovereignty zones), compliance rules, audit logs, guardrail events, and
anomalies to populate all 6 tabs of the observability dashboard.

Usage:
    python scripts/seed_observability_demo.py
    # or via kubectl:
    kubectl exec -it deploy/recursant-registry -- python scripts/seed_observability_demo.py

Environment variables:
    TENANT_ID: Tenant ID (default: default)
    NUM_TRACES: Number of traces to generate (default: 200)
    DAYS_BACK: Days of history (default: 7)
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'registry'))

from app import create_app, db
from app.models.agent import Agent, AgentStatus
from app.models.mesh import MeshAnomaly, MeshAuditLog, MeshComplianceRule, MeshRegistration
from app.models.guardrail import (
    Guardrail, GuardrailAssignment, GuardrailEvent,
    GuardrailMechanism, GuardrailScope, GuardrailStatus, GuardrailType,
    EnforcementMode,
)


# Mortgage demo agent names
AGENTS = [
    "Customer Agent",
    "Authentication Agent",
    "KYC Agent",
    "Credit Agent",
    "Core Banking Agent",
    "Compliance Crew",
    "Research Assistant",
    "Fact Checker Agent",
]

# Sovereignty zones
AGENT_ZONES = {
    "Customer Agent": "EU",
    "Authentication Agent": "EU",
    "KYC Agent": "EU",
    "Credit Agent": "US",
    "Core Banking Agent": "US",
    "Compliance Crew": "US",
    "Research Assistant": "APAC",
    "Fact Checker Agent": "APAC",
}

# Hub-and-spoke: Customer Agent calls backend agents
VALID_ROUTES = [
    ("Customer Agent", "Authentication Agent"),
    ("Customer Agent", "KYC Agent"),
    ("Customer Agent", "Credit Agent"),
    ("Customer Agent", "Core Banking Agent"),
    ("Customer Agent", "Compliance Crew"),
    ("Research Assistant", "Fact Checker Agent"),
]

A2A_METHODS = [
    "tasks/send", "tasks/get", "tasks/cancel",
    "tasks/sendSubscribe", "agent/authenticatedExtendedCard",
]

MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "gpt-4o-mini",
]

COST_PER_TOKEN = {
    "claude-sonnet-4-5-20250929": (0.000003, 0.000015),
    "claude-haiku-4-5-20251001": (0.0000008, 0.000004),
    "gpt-4o-mini": (0.00000015, 0.0000006),
}

# Guardrail definitions to seed
GUARDRAIL_DEFS = [
    {
        "name": "PII Detection",
        "description": "Detects and blocks PII (SSN, credit cards, phone numbers) in inputs and outputs",
        "type": GuardrailType.PRE_PROCESSING,
        "mechanism": GuardrailMechanism.REGEX,
        "enforcement_mode": EnforcementMode.BLOCK,
        "config": {"patterns": ["SSN", "credit_card", "phone_number", "email_address"]},
        "priority": 10,
    },
    {
        "name": "Prompt Injection Filter",
        "description": "Detects prompt injection attempts using pattern matching",
        "type": GuardrailType.PRE_PROCESSING,
        "mechanism": GuardrailMechanism.REGEX,
        "enforcement_mode": EnforcementMode.BLOCK,
        "config": {"patterns": ["ignore_previous", "system_prompt_extraction", "jailbreak"]},
        "priority": 5,
    },
    {
        "name": "Toxicity Check",
        "description": "Checks outputs for toxic, offensive, or harmful content using vector similarity",
        "type": GuardrailType.POST_PROCESSING,
        "mechanism": GuardrailMechanism.VECTOR_LOOKUP,
        "enforcement_mode": EnforcementMode.BLOCK,
        "config": {"similarity_threshold": 0.85, "collection": "toxicity_patterns"},
        "priority": 20,
    },
    {
        "name": "Hallucination Guard",
        "description": "Uses LLM-as-judge to verify factual accuracy of agent outputs",
        "type": GuardrailType.POST_PROCESSING,
        "mechanism": GuardrailMechanism.LLM_JUDGE,
        "enforcement_mode": EnforcementMode.WARN,
        "config": {"judge_model": "claude-haiku-4-5-20251001", "threshold": 0.7},
        "priority": 30,
    },
    {
        "name": "Bias Detector",
        "description": "Detects biased content in agent responses using ML classifier",
        "type": GuardrailType.POST_PROCESSING,
        "mechanism": GuardrailMechanism.ML_CLASSIFIER,
        "enforcement_mode": EnforcementMode.WARN,
        "config": {"model_path": "bias_classifier_v2", "threshold": 0.6},
        "priority": 40,
    },
    {
        "name": "Data Exfiltration Block",
        "description": "Blocks attempts to exfiltrate data via encoded payloads or URLs",
        "type": GuardrailType.PRE_PROCESSING,
        "mechanism": GuardrailMechanism.REGEX,
        "enforcement_mode": EnforcementMode.BLOCK,
        "config": {"patterns": ["base64_payload", "exfiltration_url", "encoded_data"]},
        "priority": 8,
    },
]

# Which agents get which guardrails (all get PII + Injection, specific ones get others)
GUARDRAIL_ASSIGNMENTS = {
    "PII Detection": AGENTS,  # All agents
    "Prompt Injection Filter": AGENTS,  # All agents
    "Toxicity Check": ["Customer Agent", "Research Assistant", "Fact Checker Agent"],
    "Hallucination Guard": ["Customer Agent", "Credit Agent", "Compliance Crew", "Research Assistant"],
    "Bias Detector": ["Customer Agent", "KYC Agent", "Credit Agent"],
    "Data Exfiltration Block": AGENTS,  # All agents
}


def seed_guardrails(tenant_id: str) -> dict[str, str]:
    """Create guardrail definitions and return {name: id} mapping."""
    created = {}
    for gdef in GUARDRAIL_DEFS:
        # Check if already exists
        existing = Guardrail.query.filter_by(
            tenant_id=tenant_id, name=gdef["name"]
        ).filter(Guardrail.deleted_at.is_(None)).first()

        if existing:
            print(f"  Guardrail '{gdef['name']}' already exists (id={existing.id})")
            created[gdef["name"]] = str(existing.id)
            # Ensure it's active
            if existing.status != GuardrailStatus.ACTIVE:
                existing.status = GuardrailStatus.ACTIVE
                existing.approved_by = "observability-seed"
                existing.approved_at = datetime.now(timezone.utc)
            continue

        guardrail = Guardrail(
            tenant_id=tenant_id,
            name=gdef["name"],
            description=gdef["description"],
            type=gdef["type"],
            mechanism=gdef["mechanism"],
            enforcement_mode=gdef["enforcement_mode"],
            config=gdef["config"],
            scope=GuardrailScope.SPECIFIC_AGENTS,
            priority=gdef["priority"],
            status=GuardrailStatus.ACTIVE,
            created_by="observability-seed",
            approved_by="observability-seed",
            approved_at=datetime.now(timezone.utc),
        )
        db.session.add(guardrail)
        db.session.flush()
        created[gdef["name"]] = str(guardrail.id)
        print(f"  Created guardrail: {gdef['name']} (id={guardrail.id})")

    db.session.commit()
    return created


def seed_guardrail_assignments(tenant_id: str, guardrail_ids: dict[str, str]) -> int:
    """Assign guardrails to agents. Returns count of assignments created."""
    count = 0
    for guardrail_name, agent_names in GUARDRAIL_ASSIGNMENTS.items():
        gid = guardrail_ids.get(guardrail_name)
        if not gid:
            continue

        for agent_name in agent_names:
            # Look up agent by name
            agent = Agent.query.filter_by(
                tenant_id=tenant_id, name=agent_name
            ).filter(Agent.deleted_at.is_(None)).first()

            agent_id = agent.id if agent else None

            # Check if assignment already exists
            existing = GuardrailAssignment.query.filter_by(
                guardrail_id=gid,
                agent_name=agent_name,
                tenant_id=tenant_id,
            ).first()
            if existing:
                continue

            assignment = GuardrailAssignment(
                guardrail_id=gid,
                agent_id=agent_id,
                agent_name=agent_name,
                tenant_id=tenant_id,
            )
            db.session.add(assignment)
            count += 1

    db.session.commit()
    return count


def seed_registrations(tenant_id: str) -> int:
    """Create MeshRegistration records with sovereignty zones for all agents."""
    count = 0
    for agent_name in AGENTS:
        agent = Agent.query.filter_by(
            tenant_id=tenant_id, name=agent_name
        ).filter(Agent.deleted_at.is_(None)).first()

        if not agent:
            print(f"  WARNING: Agent '{agent_name}' not found, skipping registration")
            continue

        # Check if registration already exists
        existing = MeshRegistration.query.filter_by(agent_id=agent.id).first()
        if existing:
            # Update sovereignty zone if needed
            zone = AGENT_ZONES.get(agent_name)
            if zone and existing.sovereignty_zone != zone:
                existing.sovereignty_zone = zone
            continue

        zone = AGENT_ZONES.get(agent_name)
        reg = MeshRegistration(
            agent_id=agent.id,
            sidecar_url=f"http://sidecar-{agent_name.lower().replace(' ', '-')}:9000",
            agent_card={"name": agent_name, "zone": zone},
            sovereignty_zone=zone,
            tenant_id=tenant_id,
            status="healthy",
        )
        db.session.add(reg)
        count += 1
        print(f"  Registered: {agent_name} (zone={zone})")

    db.session.commit()
    return count


def seed_compliance_rules(tenant_id: str) -> int:
    """Create sovereignty zone compliance rules."""
    rules = [
        # EU <-> EU: allow
        {"rule_type": "sovereignty", "source_value": "EU", "dest_value": "EU", "action": "allow", "priority": 0},
        # US <-> US: allow
        {"rule_type": "sovereignty", "source_value": "US", "dest_value": "US", "action": "allow", "priority": 0},
        # APAC <-> APAC: allow
        {"rule_type": "sovereignty", "source_value": "APAC", "dest_value": "APAC", "action": "allow", "priority": 0},
        # EU -> US: allow (mortgage flow needs this)
        {"rule_type": "sovereignty", "source_value": "EU", "dest_value": "US", "action": "allow", "priority": 10},
        # US -> EU: block (sensitive data can't flow back to EU)
        {"rule_type": "sovereignty", "source_value": "US", "dest_value": "EU", "action": "block", "priority": 10},
        # APAC -> EU/US: block
        {"rule_type": "sovereignty", "source_value": "APAC", "dest_value": "EU", "action": "block", "priority": 10},
        {"rule_type": "sovereignty", "source_value": "APAC", "dest_value": "US", "action": "block", "priority": 10},
    ]

    count = 0
    for rule in rules:
        existing = MeshComplianceRule.query.filter_by(
            tenant_id=tenant_id,
            rule_type=rule["rule_type"],
            source_value=rule["source_value"],
            dest_value=rule["dest_value"],
        ).first()
        if existing:
            continue

        db.session.add(MeshComplianceRule(tenant_id=tenant_id, **rule))
        count += 1

    db.session.commit()
    return count


def generate_audit_traces(tenant_id: str, num_traces: int, days_back: int) -> list:
    """Generate multi-hop audit traces."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)
    records = []

    prev_hash = None
    seq = 0

    for i in range(num_traces):
        ts = start + timedelta(seconds=random.uniform(0, days_back * 86400))
        if ts.hour < 7 or ts.hour > 20:
            if random.random() > 0.2:
                ts = ts.replace(hour=random.randint(8, 18))

        task_id = str(uuid.uuid4())

        if random.random() < 0.7:
            route_idx = random.randint(0, 4)
            src, dst = VALID_ROUTES[route_idx]
        else:
            src, dst = VALID_ROUTES[5]

        r = random.random()
        if r < 0.03:
            decision = "block"
            outcome = "blocked"
        elif r < 0.08:
            decision = "allow"
            outcome = "error"
        else:
            decision = "allow"
            outcome = "success"

        method = random.choice(A2A_METHODS)
        model = random.choice(MODELS)
        input_tokens = random.randint(100, 3000)
        output_tokens = random.randint(50, 2000)
        cost_in, cost_out = COST_PER_TOKEN.get(model, (0.000003, 0.000015))
        cost_usd = input_tokens * cost_in + output_tokens * cost_out

        sidecar_id = f"sidecar-{src.lower().replace(' ', '-')}"

        content = f"{task_id}:{src}:{dst}:{ts.isoformat()}:{seq}"
        record_hash = hashlib.sha256(content.encode()).hexdigest()

        records.append(MeshAuditLog(
            tenant_id=tenant_id,
            timestamp=ts,
            source_agent_name=src,
            dest_agent_name=dst,
            task_id=task_id,
            a2a_method=method,
            message_hash=hashlib.sha256(f"msg-{i}-out".encode()).hexdigest()[:16],
            direction="outbound",
            decision=decision,
            outcome=outcome,
            sidecar_id=sidecar_id,
            record_hash=record_hash,
            previous_record_hash=prev_hash,
            sequence_number=seq,
            details={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model_name": model,
                "estimated_cost_usd": round(cost_usd, 8),
                "latency_ms": round(random.lognormvariate(4.5, 0.8), 1),
                "sovereignty_zone_src": AGENT_ZONES.get(src),
                "sovereignty_zone_dst": AGENT_ZONES.get(dst),
            },
        ))
        prev_hash = record_hash
        seq += 1

        ts_in = ts + timedelta(milliseconds=random.uniform(5, 200))
        content_in = f"{task_id}:{dst}:{src}:{ts_in.isoformat()}:{seq}"
        record_hash_in = hashlib.sha256(content_in.encode()).hexdigest()

        records.append(MeshAuditLog(
            tenant_id=tenant_id,
            timestamp=ts_in,
            source_agent_name=src,
            dest_agent_name=dst,
            task_id=task_id,
            a2a_method=method,
            message_hash=hashlib.sha256(f"msg-{i}-in".encode()).hexdigest()[:16],
            direction="inbound",
            decision=decision,
            outcome=outcome,
            sidecar_id=f"sidecar-{dst.lower().replace(' ', '-')}",
            record_hash=record_hash_in,
            previous_record_hash=prev_hash,
            sequence_number=seq,
            details={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model_name": model,
                "estimated_cost_usd": round(cost_usd, 8),
                "latency_ms": round(random.lognormvariate(4.5, 0.8), 1),
            },
        ))
        prev_hash = record_hash_in
        seq += 1

    return records


def generate_anomalies(tenant_id: str, num_anomalies: int, days_back: int) -> list:
    """Generate anomaly records."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)
    anomalies = []

    types = ["traffic_spike", "error_burst", "policy_violation_surge", "latency_spike"]
    severities = ["low", "medium", "high", "critical"]
    severity_weights = [30, 40, 20, 10]

    for i in range(num_anomalies):
        ts = start + timedelta(seconds=random.uniform(0, days_back * 86400))
        agent = random.choice(AGENTS)
        atype = random.choice(types)
        severity = random.choices(severities, weights=severity_weights, k=1)[0]

        resolved_at = None
        if random.random() < 0.6:
            resolved_at = ts + timedelta(minutes=random.uniform(5, 120))

        anomalies.append(MeshAnomaly(
            tenant_id=tenant_id,
            anomaly_type=atype,
            severity=severity,
            agent_name=agent,
            description=f"{atype.replace('_', ' ').title()} detected for {agent}",
            details={
                "threshold": round(random.uniform(1.5, 5.0), 2),
                "observed_value": round(random.uniform(5.0, 50.0), 2),
                "window_seconds": 300,
            },
            detected_at=ts,
            resolved_at=resolved_at,
            is_acknowledged=resolved_at is not None or random.random() < 0.3,
        ))

    return anomalies


def generate_guardrail_events(
    tenant_id: str, num_events: int, days_back: int,
    guardrail_ids: dict[str, str],
) -> list:
    """Generate guardrail events linked to real guardrail IDs."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    # Build pool from real guardrail IDs
    pool = []
    for gdef in GUARDRAIL_DEFS:
        gid = guardrail_ids.get(gdef["name"])
        if gid:
            pool.append({
                "id": gid,
                "name": gdef["name"],
                "type": gdef["type"].value,
                "mechanism": gdef["mechanism"].value,
            })

    if not pool:
        print("  WARNING: No guardrails found, using synthetic IDs")
        pool = [
            {"id": str(uuid.uuid4()), "name": "PII Detection", "type": "pre_processing", "mechanism": "regex"},
            {"id": str(uuid.uuid4()), "name": "Prompt Injection Filter", "type": "pre_processing", "mechanism": "regex"},
        ]

    action_weights = {"pass": 65, "block": 20, "warn": 10, "redact": 5}
    actions = []
    for action, weight in action_weights.items():
        actions.extend([action] * weight)

    latency_params = {
        "regex": (1.5, 0.5),
        "vector_lookup": (3.0, 0.6),
        "llm_judge": (5.5, 0.7),
        "ml_classifier": (2.5, 0.5),
    }

    patterns = [
        "SSN pattern detected", "Credit card number", "Email address",
        "Prompt injection attempt", "Ignore previous instructions",
        "System prompt extraction", "Jailbreak attempt",
        "Toxic language detected", "Data exfiltration URL",
    ]

    events = []
    for i in range(num_events):
        ts = start + timedelta(seconds=random.uniform(0, days_back * 86400))
        if ts.hour < 7 or ts.hour > 20:
            if random.random() > 0.3:
                ts = ts.replace(hour=random.randint(8, 18))

        g = random.choice(pool)
        # Pick an agent that actually has this guardrail assigned
        assigned_agents = GUARDRAIL_ASSIGNMENTS.get(g["name"], AGENTS)
        agent = random.choice(assigned_agents)
        action = random.choice(actions)
        mu, sigma = latency_params.get(g["mechanism"], (2.0, 0.5))

        matched_pattern = None
        if action != "pass":
            matched_pattern = random.choice(patterns)

        events.append(GuardrailEvent(
            tenant_id=tenant_id,
            guardrail_id=g["id"],
            guardrail_name=g["name"],
            guardrail_type=g["type"],
            mechanism=g["mechanism"],
            agent_name=agent,
            sidecar_id=f"sidecar-{agent.lower().replace(' ', '-')}",
            action=action,
            reasoning=f"{'Blocked: ' + matched_pattern if matched_pattern else 'Passed checks'}",
            latency_ms=round(random.lognormvariate(mu, sigma), 2),
            matched_pattern=matched_pattern,
            input_hash=hashlib.sha256(f"input-{i}".encode()).hexdigest(),
            is_error=random.random() < 0.02,
            timestamp=ts,
            is_false_positive=True if action == "block" and random.random() < 0.08 else None,
        ))

    return events


def main():
    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        tenant_id = os.environ.get("TENANT_ID", "default")
        num_traces = int(os.environ.get("NUM_TRACES", "200"))
        num_anomalies = int(os.environ.get("NUM_ANOMALIES", "25"))
        num_guardrail_events = int(os.environ.get("NUM_GUARDRAIL_EVENTS", "500"))
        days_back = int(os.environ.get("DAYS_BACK", "7"))

        # Ensure tables exist
        db.create_all()

        # --- Guardrails ---
        print("\n--- Seeding Guardrails ---")
        guardrail_ids = seed_guardrails(tenant_id)
        print(f"  {len(guardrail_ids)} guardrails ready")

        # --- Guardrail assignments ---
        print("\n--- Seeding Guardrail Assignments ---")
        num_assignments = seed_guardrail_assignments(tenant_id, guardrail_ids)
        print(f"  {num_assignments} new assignments created")

        # --- Mesh registrations ---
        print("\n--- Seeding Mesh Registrations ---")
        num_regs = seed_registrations(tenant_id)
        print(f"  {num_regs} new registrations created")

        # --- Compliance rules ---
        print("\n--- Seeding Compliance Rules ---")
        num_rules = seed_compliance_rules(tenant_id)
        print(f"  {num_rules} new compliance rules created")

        # --- Audit traces ---
        print(f"\n--- Generating {num_traces} audit traces ({num_traces * 2} records) ---")
        records = generate_audit_traces(tenant_id, num_traces, days_back)
        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            db.session.add_all(batch)
            db.session.commit()
            print(f"  Audit records: {min(i + batch_size, len(records))}/{len(records)}")

        # --- Anomalies ---
        print(f"\n--- Generating {num_anomalies} anomalies ---")
        anomalies = generate_anomalies(tenant_id, num_anomalies, days_back)
        db.session.add_all(anomalies)
        db.session.commit()
        print(f"  Anomalies: {len(anomalies)} inserted")

        # --- Guardrail events ---
        print(f"\n--- Generating {num_guardrail_events} guardrail events ---")
        events = generate_guardrail_events(tenant_id, num_guardrail_events, days_back, guardrail_ids)
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            db.session.add_all(batch)
            db.session.commit()
            print(f"  Guardrail events: {min(i + batch_size, len(events))}/{len(events)}")

        # --- Summary ---
        from app.services.security_posture_service import SecurityPostureService
        posture = SecurityPostureService.compute_posture(tenant_id)

        open_anomalies = MeshAnomaly.query.filter_by(tenant_id=tenant_id, resolved_at=None).count()
        total_audit = MeshAuditLog.query.filter_by(tenant_id=tenant_id).count()
        total_guardrail = GuardrailEvent.query.filter_by(tenant_id=tenant_id).count()
        total_assignments = GuardrailAssignment.query.filter_by(tenant_id=tenant_id).count()
        total_regs = MeshRegistration.query.filter_by(tenant_id=tenant_id).count()

        print(f"\n--- Summary ---")
        print(f"  Guardrails: {len(guardrail_ids)} active")
        print(f"  Guardrail assignments: {total_assignments}")
        print(f"  Mesh registrations: {total_regs}")
        print(f"  Audit records: {total_audit}")
        print(f"  Guardrail events: {total_guardrail}")
        print(f"  Anomalies: {len(anomalies)} ({open_anomalies} open)")
        print(f"\n--- Security Posture ---")
        print(f"  Composite score: {posture['composite_score']}")
        for key, value in posture['components'].items():
            print(f"    {key}: {value}")
        print(f"\nObservability data seeded successfully.")


if __name__ == "__main__":
    main()
