import enum
import uuid
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class GroupType(enum.Enum):
    """Group types that determine access level."""
    ADMINISTRATOR = 'administrator'
    APPROVER = 'approver'
    USER = 'user'


# Hierarchy: higher number = more privilege
GROUP_TYPE_RANK = {
    GroupType.USER: 1,
    GroupType.APPROVER: 2,
    GroupType.ADMINISTRATOR: 3,
}


# Association table for user <-> group many-to-many
user_groups = db.Table(
    'user_groups',
    db.Column('user_id', UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True),
    db.Column('group_id', UUID(as_uuid=True), db.ForeignKey('groups.id'), primary_key=True),
    db.Column('created_at', db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    groups = db.relationship('Group', secondary=user_groups, back_populates='users', lazy='joined')

    __table_args__ = (
        Index('ix_users_username_unique', 'username', unique=True,
              postgresql_where=db.text('deleted_at IS NULL')),
        Index('ix_users_email_unique', 'email', unique=True,
              postgresql_where=db.text('deleted_at IS NULL')),
    )

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )

    @property
    def effective_role(self) -> GroupType:
        """Return the highest-privilege group type across all groups."""
        if not self.groups:
            return GroupType.USER
        return max(
            (g.group_type for g in self.groups if g.deleted_at is None),
            key=lambda gt: GROUP_TYPE_RANK.get(gt, 0),
            default=GroupType.USER,
        )

    @property
    def role_names(self) -> list:
        """Return list of group type values for JWT."""
        return list({g.group_type.value for g in self.groups if g.deleted_at is None})

    def __repr__(self):
        return f'<User {self.username}>'


class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    group_type = db.Column(db.Enum(GroupType, name='grouptype'), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    users = db.relationship('User', secondary=user_groups, back_populates='groups', lazy='joined')

    __table_args__ = (
        Index('ix_groups_name_unique', 'name', unique=True,
              postgresql_where=db.text('deleted_at IS NULL')),
    )

    def __repr__(self):
        return f'<Group {self.name} ({self.group_type.value})>'
