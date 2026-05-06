"""Seed guardrail Phase 2 demo data.

Creates guardrails, observability events, and adversarial test suites
so the dashboard and adversarial testing pages have realistic data.

Run inside the registry container or with FLASK_APP/DATABASE_URL set.
"""

import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Bootstrap Flask app context
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models.guardrail import (
    Guardrail, GuardrailEvent, GuardrailStatus,
    GuardrailType, GuardrailMechanism, EnforcementMode,
)

app = create_app()

TENANT_ID = "default"

# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

GUARDRAILS = [
    {
        "name": "Prompt Injection Shield",
        "description": "Detects and blocks prompt injection attempts including jailbreaks, ignore-previous patterns, and role-play exploits.",
        "type": "pre_processing",
        "mechanism": "regex",
        "enforcement_mode": "block",
        "config": {
            "patterns": [
                {"name": "ignore_previous", "pattern": r"ignore\s+(all\s+)?previous", "action": "block"},
                {"name": "system_override", "pattern": r"you\s+are\s+now\s+", "action": "block"},
                {"name": "jailbreak_dan", "pattern": r"DAN\s+mode|developer\s+mode", "action": "block"},
                {"name": "role_play_exploit", "pattern": r"pretend\s+you\s+are|act\s+as\s+if", "action": "warn"},
            ],
        },
        "priority": 1,
        "version": "2.1.0",
    },
    {
        "name": "PII Data Guard",
        "description": "Scans for and redacts personally identifiable information including SSNs, credit cards, email addresses, and phone numbers.",
        "type": "post_processing",
        "mechanism": "regex",
        "enforcement_mode": "redact",
        "config": {
            "patterns": [
                {"name": "ssn", "pattern": r"\b\d{3}-\d{2}-\d{4}\b", "action": "redact"},
                {"name": "credit_card", "pattern": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "action": "redact"},
                {"name": "email", "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "action": "warn"},
                {"name": "phone_uk", "pattern": r"\b0\d{4}\s?\d{6}\b", "action": "redact"},
            ],
        },
        "priority": 2,
        "version": "1.3.0",
    },
    {
        "name": "Toxicity Filter",
        "description": "Blocks toxic, abusive, or discriminatory language in agent outputs using keyword and pattern matching.",
        "type": "post_processing",
        "mechanism": "llm_judge",
        "enforcement_mode": "block",
        "config": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "system_prompt": "Evaluate the following text for toxicity, bias, or discriminatory content. Respond BLOCK if toxic, PASS if safe.",
            "threshold": 0.7,
        },
        "priority": 3,
        "version": "1.0.0",
    },
    {
        "name": "Hallucination Guard",
        "description": "Detects potential hallucinations by checking responses against known factual patterns and flagging unverifiable claims.",
        "type": "post_processing",
        "mechanism": "llm_judge",
        "enforcement_mode": "warn",
        "config": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "system_prompt": "Check if the response contains fabricated facts, invented citations, or claims that cannot be verified. Respond WARN if suspicious, PASS if grounded.",
            "threshold": 0.6,
        },
        "priority": 5,
        "version": "1.1.0",
    },
    {
        "name": "Output Format Enforcer",
        "description": "Ensures agent responses conform to expected JSON schema and structural requirements.",
        "type": "post_processing",
        "mechanism": "regex",
        "enforcement_mode": "block",
        "config": {
            "patterns": [
                {"name": "markdown_injection", "pattern": r"<script|javascript:|on\w+=", "action": "block"},
                {"name": "sql_in_output", "pattern": r"(DROP|DELETE|INSERT|UPDATE)\s+(TABLE|FROM|INTO)", "action": "block"},
            ],
        },
        "priority": 10,
        "version": "1.0.0",
    },
]

# Agent names for realistic events
AGENTS = [
    "customer-360-agent",
    "kyc-verification-agent",
    "credit-scoring-agent",
    "compliance-checker-agent",
    "mortgage-processor-agent",
    "document-analyzer-agent",
    "fraud-detection-agent",
    "account-lookup-agent",
]


def seed_guardrails():
    """Create guardrails and activate them."""
    created = []
    for gdata in GUARDRAILS:
        existing = Guardrail.query.filter_by(
            tenant_id=TENANT_ID, name=gdata["name"]
        ).first()
        if existing:
            print(f"  Guardrail '{gdata['name']}' already exists, skipping")
            created.append(existing)
            continue

        type_map = {"pre_processing": GuardrailType.PRE_PROCESSING, "post_processing": GuardrailType.POST_PROCESSING, "structural": GuardrailType.STRUCTURAL}
        mech_map = {"regex": GuardrailMechanism.REGEX, "llm_judge": GuardrailMechanism.LLM_JUDGE, "vector_lookup": GuardrailMechanism.VECTOR_LOOKUP, "ml_classifier": GuardrailMechanism.ML_CLASSIFIER}
        mode_map = {"block": EnforcementMode.BLOCK, "warn": EnforcementMode.WARN, "redact": EnforcementMode.REDACT}

        g = Guardrail(
            tenant_id=TENANT_ID,
            name=gdata["name"],
            description=gdata["description"],
            type=type_map[gdata["type"]],
            mechanism=mech_map[gdata["mechanism"]],
            enforcement_mode=mode_map[gdata["enforcement_mode"]],
            config=gdata["config"],
            priority=gdata["priority"],
            version=gdata["version"],
            status=GuardrailStatus.ACTIVE,
            created_by="admin",
        )
        db.session.add(g)
        db.session.flush()
        created.append(g)
        print(f"  Created guardrail: {gdata['name']} (id={g.id})")

    db.session.commit()
    return created


def seed_observability_events(guardrails):
    """Generate realistic guardrail evaluation events over the past 7 days."""
    now = datetime.now(timezone.utc)
    events = []

    for day_offset in range(7):
        date = now - timedelta(days=day_offset)
        # More events on weekdays
        events_per_day = random.randint(80, 200) if date.weekday() < 5 else random.randint(20, 60)

        for _ in range(events_per_day):
            guardrail = random.choice(guardrails)
            agent = random.choice(AGENTS)

            # Vary the action distribution by guardrail
            mode = guardrail.enforcement_mode.value if hasattr(guardrail.enforcement_mode, 'value') else guardrail.enforcement_mode
            if mode == "block":
                action = random.choices(
                    ["pass", "block", "warn"],
                    weights=[70, 20, 10],
                )[0]
            elif mode == "redact":
                action = random.choices(
                    ["pass", "redact", "warn"],
                    weights=[60, 30, 10],
                )[0]
            else:
                action = random.choices(
                    ["pass", "warn", "block"],
                    weights=[75, 20, 5],
                )[0]

            # Latency varies by mechanism
            mech = guardrail.mechanism.value if hasattr(guardrail.mechanism, 'value') else guardrail.mechanism
            if mech == "regex":
                latency = random.uniform(1, 15)
            elif mech == "llm_judge":
                latency = random.uniform(200, 1500)
            else:
                latency = random.uniform(5, 50)

            # Matched pattern for blocked/warned events
            matched_pattern = None
            if action in ("block", "warn", "redact") and guardrail.config.get("patterns"):
                pattern = random.choice(guardrail.config["patterns"])
                matched_pattern = pattern["name"]

            # Small error rate
            is_error = random.random() < 0.02
            error_message = "Timeout waiting for LLM response" if is_error and mech == "llm_judge" else None

            timestamp = date.replace(
                hour=random.randint(6, 22),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            )

            event = GuardrailEvent(
                tenant_id=TENANT_ID,
                guardrail_id=str(guardrail.id),
                guardrail_name=guardrail.name,
                guardrail_type=guardrail.type.value if hasattr(guardrail.type, 'value') else guardrail.type,
                mechanism=guardrail.mechanism.value if hasattr(guardrail.mechanism, 'value') else guardrail.mechanism,
                agent_name=agent,
                sidecar_id=f"sidecar-{agent}",
                action=action,
                reasoning=f"{'Matched' if matched_pattern else 'No match'}: {matched_pattern or 'clean input'}",
                latency_ms=round(latency, 1),
                matched_pattern=matched_pattern,
                input_hash=uuid.uuid4().hex[:16],
                is_error=is_error,
                error_message=error_message,
                timestamp=timestamp,
            )
            events.append(event)

    db.session.bulk_save_objects(events)
    db.session.commit()
    print(f"  Created {len(events)} guardrail events over 7 days")
    return len(events)


def seed_adversarial_suites(guardrails):
    """Create adversarial test suites and completed runs."""
    from app.models.adversarial import AdversarialTestSuite, AdversarialTestRun
    from app.services.adversarial_service import AdversarialService

    now = datetime.now(timezone.utc)
    guardrail_ids = [str(g.id) for g in guardrails]

    suites_data = [
        {
            "name": "Encoding Evasion Suite",
            "description": "Tests guardrails against base64, rot13, leetspeak, unicode homoglyphs, zero-width characters, and reversed text encoding tricks.",
            "attack_types": ["encoding"],
            "target_guardrail_ids": guardrail_ids[:3],
            "evasion_rate_threshold": 0.15,
            "schedule_enabled": True,
            "schedule_interval_minutes": 1440,
        },
        {
            "name": "Jailbreak Resistance Suite",
            "description": "Evaluates resistance to DAN prompts, developer mode exploits, role-play attacks, language tricks, and instruction override attempts.",
            "attack_types": ["jailbreak"],
            "target_guardrail_ids": [guardrail_ids[0]],
            "evasion_rate_threshold": 0.05,
            "schedule_enabled": True,
            "schedule_interval_minutes": 720,
        },
        {
            "name": "Combined Attack Suite",
            "description": "Full adversarial evaluation combining encoding evasion and jailbreak techniques against all active guardrails.",
            "attack_types": ["encoding", "jailbreak"],
            "target_guardrail_ids": guardrail_ids,
            "evasion_rate_threshold": 0.10,
            "schedule_enabled": False,
        },
    ]

    for sdata in suites_data:
        existing = AdversarialTestSuite.query.filter_by(
            tenant_id=TENANT_ID, name=sdata["name"]
        ).filter(AdversarialTestSuite.deleted_at.is_(None)).first()
        if existing:
            print(f"  Suite '{sdata['name']}' already exists, skipping")
            continue

        suite = AdversarialTestSuite(
            tenant_id=TENANT_ID,
            name=sdata["name"],
            description=sdata["description"],
            attack_types=sdata["attack_types"],
            target_guardrail_ids=sdata["target_guardrail_ids"],
            evasion_rate_threshold=sdata["evasion_rate_threshold"],
            schedule_enabled=sdata.get("schedule_enabled", False),
            schedule_interval_minutes=sdata.get("schedule_interval_minutes"),
            next_run_at=now + timedelta(hours=random.randint(1, 24)) if sdata.get("schedule_enabled") else None,
            last_run_at=now - timedelta(hours=random.randint(2, 48)),
            alert_on_threshold_breach=True,
            status="active",
            created_by="admin",
        )
        db.session.add(suite)
        db.session.flush()
        print(f"  Created suite: {sdata['name']} (id={suite.id})")

        # Create 2-3 historical runs per suite
        num_runs = random.randint(2, 3)
        for run_idx in range(num_runs):
            run_time = now - timedelta(days=run_idx * 2, hours=random.randint(1, 12))
            total = random.randint(30, 80)
            evaded = random.randint(0, int(total * 0.25))
            blocked = total - evaded - random.randint(0, 3)
            errors = total - blocked - evaded
            if errors < 0:
                errors = 0
                blocked = total - evaded
            evasion_rate = round(evaded / total, 4) if total > 0 else 0.0
            threshold_breached = evasion_rate > sdata["evasion_rate_threshold"]

            # Generate plausible inputs and results
            generated_inputs = []
            results = []
            attack_type_choices = sdata["attack_types"]
            for i in range(total):
                at = random.choice(attack_type_choices)
                inp = {
                    "text": f"[{at}] adversarial input #{i+1}",
                    "attack_type": at,
                    "encoding": at if at == "encoding" else None,
                }
                generated_inputs.append(inp)

                gid = random.choice(sdata["target_guardrail_ids"])
                was_evaded = i < evaded
                results.append({
                    "input_index": i,
                    "guardrail_id": gid,
                    "expected_action": "block",
                    "actual_action": "pass" if was_evaded else "block",
                    "evaded": was_evaded,
                    "latency_ms": round(random.uniform(2, 800), 1),
                })

            # Sign the results
            import hashlib, hmac
            signing_key = b'adversarial-test-signing-key-v1'
            completed_at = run_time + timedelta(minutes=random.randint(1, 5))
            sig_data = f"{suite.id}|{total}|{blocked}|{evaded}|{evasion_rate}|{completed_at.isoformat()}"
            signature = hmac.new(signing_key, sig_data.encode(), hashlib.sha256).hexdigest()

            run = AdversarialTestRun(
                suite_id=suite.id,
                tenant_id=TENANT_ID,
                status="completed",
                triggered_by="admin" if run_idx == 0 else "scheduler",
                total_inputs=total,
                blocked_count=blocked,
                evaded_count=evaded,
                error_count=errors,
                evasion_rate=evasion_rate,
                generated_inputs=generated_inputs,
                results=results,
                threshold_breached=threshold_breached,
                alert_sent=threshold_breached,
                result_signature=signature,
                signature_algorithm="HMAC-SHA256",
                started_at=run_time,
                completed_at=completed_at,
            )
            db.session.add(run)

            status_str = "BREACHED" if threshold_breached else "ok"
            print(f"    Run {run_idx+1}: {total} inputs, {evaded} evaded ({evasion_rate:.1%}), threshold {status_str}")

    db.session.commit()


def main():
    with app.app_context():
        print("\n=== Seeding Guardrail Phase 2 Demo Data ===\n")

        print("1. Creating guardrails...")
        guardrails = seed_guardrails()
        active_guardrails = [g for g in guardrails if g.status == GuardrailStatus.ACTIVE]
        print(f"   {len(active_guardrails)} active guardrails\n")

        print("2. Generating observability events (7 days)...")
        count = seed_observability_events(active_guardrails)
        print(f"   {count} events created\n")

        print("3. Creating adversarial test suites and runs...")
        seed_adversarial_suites(active_guardrails)

        print("\n=== Seeding complete ===\n")


if __name__ == "__main__":
    main()
