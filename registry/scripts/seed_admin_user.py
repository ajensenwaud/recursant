#!/usr/bin/env python3
"""
Seed the admin user and default groups.

Reads ADMIN_USERNAME and ADMIN_PASSWORD from environment (or .env).
Creates the three default groups (Administrators, Approvers, Users)
and the admin user assigned to the Administrators group.

Skips creation if the admin user or groups already exist.

Run with: python scripts/seed_admin_user.py
"""

import sys
import os

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models.user import User, Group, GroupType


DEFAULT_GROUPS = [
    {
        'name': 'Administrators',
        'description': 'Full access to all registry functions',
        'group_type': GroupType.ADMINISTRATOR,
    },
    {
        'name': 'Approvers',
        'description': 'Can approve submissions, view scans and evaluations',
        'group_type': GroupType.APPROVER,
    },
    {
        'name': 'Users',
        'description': 'Can view and browse approved agents',
        'group_type': GroupType.USER,
    },
]


def seed_groups():
    """Create default groups if they don't exist."""
    created = 0
    for group_data in DEFAULT_GROUPS:
        existing = Group.query.filter(
            Group.name == group_data['name'],
            Group.deleted_at.is_(None),
        ).first()
        if not existing:
            group = Group(**group_data)
            db.session.add(group)
            created += 1
            print(f"  Created group: {group_data['name']} ({group_data['group_type'].value})")
        else:
            print(f"  Group already exists: {group_data['name']}")
    db.session.flush()
    return created


def seed_admin_user():
    """Create the admin user from env vars if it doesn't exist."""
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD', 'admin')

    existing = User.query.filter(
        User.username == username,
        User.deleted_at.is_(None),
    ).first()

    if existing:
        existing.set_password(password)
        db.session.commit()
        print(f"  Admin user '{username}' already exists — password updated")
        return False

    admin_group = Group.query.filter(
        Group.name == 'Administrators',
        Group.deleted_at.is_(None),
    ).first()

    if not admin_group:
        print("  ERROR: Administrators group not found. Run seed_groups first.")
        return False

    user = User(
        username=username,
        email=f'{username}@recursant.local',
        first_name='Admin',
        last_name='User',
        is_active=True,
    )
    user.set_password(password)
    user.groups.append(admin_group)
    db.session.add(user)
    print(f"  Created admin user: {username}")
    return True


def main():
    app = create_app()
    with app.app_context():
        print("Seeding default groups...")
        seed_groups()

        print("Seeding admin user...")
        seed_admin_user()

        db.session.commit()
        print("Done.")


if __name__ == '__main__':
    main()
