#!/usr/bin/env python3
"""
Wipe all agents and their related data from the database.

Deletes directly from the DB (not via API) so soft-deleted agents are
removed too. Does NOT delete seed data like evaluation suites, security
test cases, security policies, or users.

Usage:
    docker compose exec api python scripts/wipe_agents.py
    docker compose exec api python scripts/wipe_agents.py --yes
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


# Tables to wipe, in dependency order (children first).
TABLES_TO_WIPE = [
    'evaluation_results',
    'evaluations',
    'security_scan_results',
    'security_scans',
    'agent_versions',
    'capabilities',
    'agent_tools',
    'agent_upstream',
    'agent_downstream',
    'agents',
]


def wipe_agents(skip_confirm: bool = False) -> None:
    app = create_app()
    with app.app_context():
        # Count agents first
        result = db.session.execute(db.text("SELECT count(*) FROM agents"))
        count = result.scalar()

        if count == 0:
            print("No agents found. Nothing to wipe.")
            return

        if not skip_confirm:
            answer = input(f"This will permanently delete {count} agent(s) and all related data. Continue? [y/N] ")
            if answer.lower() != 'y':
                print("Aborted.")
                return

        for table in TABLES_TO_WIPE:
            result = db.session.execute(db.text(f"DELETE FROM {table}"))
            rows = result.rowcount
            if rows > 0:
                print(f"  {table}: {rows} rows deleted")

        db.session.commit()
        print(f"\nDone. All agent data wiped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wipe all agents from the database")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    wipe_agents(skip_confirm=args.yes)
