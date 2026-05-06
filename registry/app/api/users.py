"""
User and Group management API endpoints.

All endpoints require ADMINISTRATOR role.
"""

from datetime import datetime, timezone

from flask import request, jsonify
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app import db
from app.models.user import User, Group, GroupType
from app.services.audit_service import AuditService
from app.schemas.user import (
    UserSchema,
    UserCreateSchema,
    UserUpdateSchema,
    UserListSchema,
    UserGroupAssignSchema,
    GroupSchema,
    GroupCreateSchema,
    GroupUpdateSchema,
    GroupListSchema,
)


# Schema instances
user_schema = UserSchema()
user_create_schema = UserCreateSchema()
user_update_schema = UserUpdateSchema()
user_list_schema = UserListSchema(many=True)
user_group_assign_schema = UserGroupAssignSchema()

group_schema = GroupSchema()
group_create_schema = GroupCreateSchema()
group_update_schema = GroupUpdateSchema()
group_list_schema = GroupListSchema(many=True)


# ============================================================================
# Users
# ============================================================================

@api_bp.route('/users', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_users():
    """List users with pagination."""
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    query = User.query.filter(User.deleted_at.is_(None))
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))

    query = query.order_by(User.username)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'users': user_list_schema.dump(pagination.items),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        }
    })


@api_bp.route('/users', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_user():
    """Create a new user."""
    try:
        data = user_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    # Check for duplicate username
    existing = User.query.filter(
        User.username == data['username'],
        User.deleted_at.is_(None),
    ).first()
    if existing:
        return jsonify({'error': f"Username '{data['username']}' already exists"}), 409

    # Check for duplicate email
    existing_email = User.query.filter(
        User.email == data['email'],
        User.deleted_at.is_(None),
    ).first()
    if existing_email:
        return jsonify({'error': f"Email '{data['email']}' already exists"}), 409

    user = User(
        username=data['username'],
        email=data['email'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        department=data.get('department'),
        is_active=True,
    )
    user.set_password(data['password'])

    # Assign groups
    group_ids = data.get('group_ids', [])
    if group_ids:
        groups = Group.query.filter(
            Group.id.in_(group_ids),
            Group.deleted_at.is_(None),
        ).all()
        user.groups = groups

    db.session.add(user)
    db.session.commit()

    AuditService.log('user.created', 'user', user.id, user.username)
    return jsonify(user_schema.dump(user)), 201


@api_bp.route('/users/<uuid:user_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_user(user_id):
    """Get user details."""
    user = User.query.filter(
        User.id == user_id,
        User.deleted_at.is_(None),
    ).first()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(user_schema.dump(user))


@api_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_user(user_id):
    """Update a user (including password reset)."""
    try:
        data = user_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    user = User.query.filter(
        User.id == user_id,
        User.deleted_at.is_(None),
    ).first()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    if 'email' in data:
        existing = User.query.filter(
            User.email == data['email'],
            User.id != user_id,
            User.deleted_at.is_(None),
        ).first()
        if existing:
            return jsonify({'error': f"Email '{data['email']}' already exists"}), 409
        user.email = data['email']

    if 'first_name' in data:
        user.first_name = data['first_name']
    if 'last_name' in data:
        user.last_name = data['last_name']
    if 'department' in data:
        user.department = data['department']
    if 'is_active' in data:
        user.is_active = data['is_active']
    if 'password' in data:
        user.set_password(data['password'])

    db.session.commit()
    AuditService.log('user.updated', 'user', user.id, user.username)
    return jsonify(user_schema.dump(user))


@api_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_user(user_id):
    """Soft-delete a user."""
    user = User.query.filter(
        User.id == user_id,
        User.deleted_at.is_(None),
    ).first()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    db.session.commit()

    AuditService.log('user.deleted', 'user', user.id, user.username)
    return '', 204


@api_bp.route('/users/<uuid:user_id>/groups', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def set_user_groups(user_id):
    """Set user's group memberships (replaces all)."""
    try:
        data = user_group_assign_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    user = User.query.filter(
        User.id == user_id,
        User.deleted_at.is_(None),
    ).first()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    groups = Group.query.filter(
        Group.id.in_(data['group_ids']),
        Group.deleted_at.is_(None),
    ).all()

    user.groups = groups
    db.session.commit()

    AuditService.log('user.groups_updated', 'user', user.id, user.username,
                     detail={'group_ids': [str(g.id) for g in groups]})
    return jsonify(user_schema.dump(user))


# ============================================================================
# Groups
# ============================================================================

@api_bp.route('/groups', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_groups():
    """List groups."""
    groups = Group.query.filter(
        Group.deleted_at.is_(None),
    ).order_by(Group.name).all()

    return jsonify({
        'groups': group_list_schema.dump(groups),
    })


@api_bp.route('/groups', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_group():
    """Create a new group."""
    try:
        data = group_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    existing = Group.query.filter(
        Group.name == data['name'],
        Group.deleted_at.is_(None),
    ).first()
    if existing:
        return jsonify({'error': f"Group '{data['name']}' already exists"}), 409

    group = Group(
        name=data['name'],
        description=data.get('description'),
        group_type=GroupType(data['group_type']),
    )
    db.session.add(group)
    db.session.commit()

    AuditService.log('group.created', 'group', group.id, group.name)
    return jsonify(group_schema.dump(group)), 201


@api_bp.route('/groups/<uuid:group_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_group(group_id):
    """Get group details with member list."""
    group = Group.query.filter(
        Group.id == group_id,
        Group.deleted_at.is_(None),
    ).first()

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    return jsonify(group_schema.dump(group))


@api_bp.route('/groups/<uuid:group_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_group(group_id):
    """Update a group."""
    try:
        data = group_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    group = Group.query.filter(
        Group.id == group_id,
        Group.deleted_at.is_(None),
    ).first()

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    if 'name' in data:
        existing = Group.query.filter(
            Group.name == data['name'],
            Group.id != group_id,
            Group.deleted_at.is_(None),
        ).first()
        if existing:
            return jsonify({'error': f"Group '{data['name']}' already exists"}), 409
        group.name = data['name']

    if 'description' in data:
        group.description = data['description']
    if 'group_type' in data:
        group.group_type = GroupType(data['group_type'])

    db.session.commit()
    AuditService.log('group.updated', 'group', group.id, group.name)
    return jsonify(group_schema.dump(group))


@api_bp.route('/groups/<uuid:group_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_group(group_id):
    """Soft-delete a group."""
    group = Group.query.filter(
        Group.id == group_id,
        Group.deleted_at.is_(None),
    ).first()

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    group.deleted_at = datetime.now(timezone.utc)
    db.session.commit()

    AuditService.log('group.deleted', 'group', group.id, group.name)
    return '', 204
