"""
Authentication API endpoints.

Provides JWT-based authentication with role-based access control.
"""

import jwt
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, current_app, g

from app import db
from app.models.user import User, GroupType, GROUP_TYPE_RANK


auth_bp = Blueprint('auth', __name__)


def create_token(user: User) -> str:
    """Create a JWT token for the given user."""
    payload = {
        'sub': str(user.id),
        'username': user.username,
        'roles': user.role_names,
        'effective_role': user.effective_role.value,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(
            seconds=current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        ),
    }
    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    return jwt.decode(
        token,
        current_app.config['JWT_SECRET_KEY'],
        algorithms=['HS256']
    )


def jwt_required(f):
    """Decorator to require valid JWT token for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Missing authorization header'}), 401

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Invalid authorization header format'}), 401

        token = parts[1]

        try:
            payload = decode_token(token)
            g.current_user = {
                'id': payload['sub'],
                'username': payload['username'],
                'roles': payload.get('roles', []),
                'effective_role': payload.get('effective_role', 'user'),
            }
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)

    return decorated


def role_required(*group_types):
    """
    Decorator to require a minimum role level.

    Usage:
        @role_required(GroupType.APPROVER)  -- approver or admin
        @role_required(GroupType.ADMINISTRATOR)  -- admin only
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # jwt_required must have already run
            user_info = getattr(g, 'current_user', None)
            if not user_info:
                return jsonify({'error': 'Authentication required'}), 401

            user_role_str = user_info.get('effective_role', 'user')
            try:
                user_role = GroupType(user_role_str)
            except ValueError:
                user_role = GroupType.USER

            user_rank = GROUP_TYPE_RANK.get(user_role, 0)

            # Check if user meets any of the required roles (minimum rank)
            min_rank = min(GROUP_TYPE_RANK.get(gt, 0) for gt in group_types)
            if user_rank < min_rank:
                return jsonify({'error': 'Insufficient permissions'}), 403

            return f(*args, **kwargs)

        return decorated
    return decorator


@auth_bp.route('/auth/login', methods=['POST'])
def login():
    """
    Authenticate with username and password.

    Request body:
        {
            "username": "admin",
            "password": "secret"
        }

    Returns:
        {
            "token": "jwt.token.here",
            "username": "admin",
            "expires_in": 86400
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Missing request body'}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    # Look up user in database
    user = User.query.filter(
        User.username == username,
        User.deleted_at.is_(None),
        User.is_active.is_(True),
    ).first()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid username or password'}), 401

    # Generate JWT token
    token = create_token(user)

    # Audit log — set g.current_user manually since jwt_required hasn't run
    g.current_user = {'id': str(user.id), 'username': user.username}
    from app.services.audit_service import AuditService
    AuditService.log('user.login', 'user', user.id, user.username)

    return jsonify({
        'token': token,
        'username': user.username,
        'expires_in': current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    })


@auth_bp.route('/auth/logout', methods=['POST'])
@jwt_required
def logout():
    """
    Log out the current user.

    For JWT, this is a no-op on the server side since tokens are stateless.
    The client should discard the token.

    Returns:
        {"message": "Logged out successfully"}
    """
    from app.services.audit_service import AuditService
    AuditService.log('user.logout', 'user')
    return jsonify({'message': 'Logged out successfully'})


@auth_bp.route('/auth/me', methods=['GET'])
@jwt_required
def me():
    """
    Get current user information.

    Returns user profile with role information.
    """
    user_info = g.current_user

    # Fetch full user from DB for fresh data
    user = db.session.get(User, user_info['id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'id': str(user.id),
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'effective_role': user.effective_role.value,
        'roles': user.role_names,
    })
