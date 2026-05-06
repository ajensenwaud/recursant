"""Marshmallow schemas for User and Group models."""

from marshmallow import Schema, fields, validate, validates, ValidationError

from app.models.user import GroupType


# Valid group type values for validation
VALID_GROUP_TYPES = [gt.value for gt in GroupType]


class GroupListSchema(Schema):
    """Compact group schema for lists."""
    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True)
    group_type = fields.Method('get_group_type')

    def get_group_type(self, obj):
        return obj.group_type.value if obj.group_type else None


class GroupSchema(Schema):
    """Full group schema with members."""
    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True)
    group_type = fields.Method('get_group_type')
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    members = fields.Method('get_members')

    def get_group_type(self, obj):
        return obj.group_type.value if obj.group_type else None

    def get_members(self, obj):
        return [
            {
                'id': str(u.id),
                'username': u.username,
                'first_name': u.first_name,
                'last_name': u.last_name,
            }
            for u in obj.users if u.deleted_at is None
        ]


class GroupCreateSchema(Schema):
    """Schema for creating a group."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, load_default=None)
    group_type = fields.String(required=True, validate=validate.OneOf(VALID_GROUP_TYPES))


class GroupUpdateSchema(Schema):
    """Schema for updating a group."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    group_type = fields.String(validate=validate.OneOf(VALID_GROUP_TYPES))


class UserGroupSchema(Schema):
    """Compact group info embedded in user responses."""
    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    group_type = fields.String(dump_only=True)


class UserListSchema(Schema):
    """Compact user schema for lists."""
    id = fields.UUID(dump_only=True)
    username = fields.String(dump_only=True)
    email = fields.String(dump_only=True)
    first_name = fields.String(dump_only=True)
    last_name = fields.String(dump_only=True)
    department = fields.String(dump_only=True)
    is_active = fields.Boolean(dump_only=True)
    effective_role = fields.Method('get_effective_role')
    groups = fields.Method('get_groups')
    created_at = fields.DateTime(dump_only=True)

    def get_effective_role(self, obj):
        return obj.effective_role.value

    def get_groups(self, obj):
        return [
            {'id': str(g.id), 'name': g.name, 'group_type': g.group_type.value}
            for g in obj.groups if g.deleted_at is None
        ]


class UserSchema(Schema):
    """Full user detail schema."""
    id = fields.UUID(dump_only=True)
    username = fields.String(dump_only=True)
    email = fields.String(dump_only=True)
    first_name = fields.String(dump_only=True)
    last_name = fields.String(dump_only=True)
    department = fields.String(dump_only=True)
    is_active = fields.Boolean(dump_only=True)
    effective_role = fields.Method('get_effective_role')
    groups = fields.Method('get_groups')
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    def get_effective_role(self, obj):
        return obj.effective_role.value

    def get_groups(self, obj):
        return [
            {'id': str(g.id), 'name': g.name, 'group_type': g.group_type.value}
            for g in obj.groups if g.deleted_at is None
        ]


class UserCreateSchema(Schema):
    """Schema for creating a user."""
    username = fields.String(required=True, validate=validate.Length(min=1, max=150))
    email = fields.Email(required=True, validate=validate.Length(max=255))
    first_name = fields.String(required=True, validate=validate.Length(min=1, max=150))
    last_name = fields.String(required=True, validate=validate.Length(min=1, max=150))
    department = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=255))
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    group_ids = fields.List(fields.UUID(), load_default=[])


class UserUpdateSchema(Schema):
    """Schema for updating a user."""
    email = fields.Email(validate=validate.Length(max=255))
    first_name = fields.String(validate=validate.Length(min=1, max=150))
    last_name = fields.String(validate=validate.Length(min=1, max=150))
    department = fields.String(allow_none=True, validate=validate.Length(max=255))
    password = fields.String(validate=validate.Length(min=8, max=128))
    is_active = fields.Boolean()


class UserGroupAssignSchema(Schema):
    """Schema for setting user group memberships."""
    group_ids = fields.List(fields.UUID(), required=True)
