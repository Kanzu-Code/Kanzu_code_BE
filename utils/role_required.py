
from functools import wraps
from uuid import UUID

from flask import jsonify
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import SQLAlchemyError

from config.extensions import db
from models import User


def roles_required(*allowed_roles):
    """
    Allow access only to authenticated users whose current
    database role is in allowed_roles.
    """

    valid_roles = {"apprentice", "employer", "admin"}

    if not allowed_roles or not set(allowed_roles).issubset(valid_roles):
        raise ValueError("Invalid or missing allowed roles.")

    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            identity = get_jwt_identity()

            try:
                user_id = UUID(identity)
            except (ValueError, TypeError, AttributeError):
                return jsonify(
                    success=False,
                    message="Invalid authentication identity.",
                ), 401

            try:
                user = db.session.get(User, user_id)

                if user is None:
                    return jsonify(
                        success=False,
                        message="User account not found.",
                    ), 401

                if not user.is_active:
                    return jsonify(
                        success=False,
                        message="This account is inactive.",
                    ), 403

                if user.role not in allowed_roles:
                    return jsonify(
                        success=False,
                        message="You do not have permission to access this resource.",
                    ), 403

                return view_function(*args, **kwargs)

            except SQLAlchemyError:
                db.session.rollback()

                return jsonify(
                    success=False,
                    message="Unable to verify user permissions.",
                ), 500

        return wrapper

    return decorator
