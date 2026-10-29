from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_jwt_extended import create_access_token


from config.extensions import db
from models.user import User


employer_auth_bp = Blueprint( "employer_auth", __name__, url_prefix="/api/employer",)
@employer_auth_bp.post("/register")
def register_employer():
    """
    Register an employer.
    ---
    tags:
      - Employer Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - first_name
            - email
            - password
          properties:
            first_name:
              type: string
              example: Grace
            last_name:
              type: string
              example: Namutebi
            email:
              type: string
              format: email
              example: grace@example.com
            phone:
              type: string
              example: "+256700000000"
            password:
              type: string
              format: password
              minLength: 8
              example: "SecurePass123!"
    responses:
      201:
        description: Employer registered successfully.
      400:
        description: Invalid or missing input.
      409:
        description: Email already registered.
      415:
        description: Content-Type must be application/json.
      500:
        description: Registration failed.
    """
    if not request.is_json:
        return jsonify(
            success=False,
            message="Content-Type must be application/json.",
        ), 415

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            success=False,
            message="Provide a valid JSON object.",
        ), 400

    try:
        first_name = data.get("first_name")
        email = data.get("email")
        password = data.get("password")

        # Validate password before creating the user.
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

        optional_fields = {}

        for field, max_length in (("last_name", 100), ("phone", 30)):
            value = data.get(field)

            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"{field} must be a string.")

                value = value.strip() or None

                if value and len(value) > max_length:
                    raise ValueError(
                        f"{field} must not exceed {max_length} characters."
                    )

            optional_fields[field] = value

        employer = User(
            first_name=first_name,
            last_name=optional_fields["last_name"],
            email=email,
            phone=optional_fields["phone"],
            role="employer",
        )

        # Store only the hashed password, never the plaintext password.
        employer.set_password(password)

        existing_user = db.session.execute(
            db.select(User).where(User.email == employer.email)
        ).scalar_one_or_none()

        if existing_user:
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        db.session.add(employer)
        db.session.commit()

        return jsonify(
            success=True,
            message="Employer registered successfully.",
            data=employer.to_dict(),
        ), 201

    except ValueError as error:
        db.session.rollback()

        return jsonify(
            success=False,
            message=str(error),
        ), 400

    except IntegrityError as error:
        db.session.rollback()

        if getattr(error.orig, "sqlstate", None) == "23505":
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        current_app.logger.exception(
            "Employer registration constraint error"
        )

        return jsonify(
            success=False,
            message="Unable to register employer.",
        ), 500

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Employer registration failed")

        return jsonify(
            success=False,
            message="Unable to register employer.",
        ), 500


admin_auth_bp = Blueprint( "admin_auth", __name__, url_prefix="/api/admin",)
@admin_auth_bp.post("/register")
def register_admin():
    """
    Register an admin.
    ---
    tags:
      - Admin Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - first_name
            - email
            - password
          properties:
            first_name:
              type: string
              example: John
            last_name:
              type: string
              example: Doe
            email:
              type: string
              format: email
              example: admin@example.com
            phone:
              type: string
              example: "+256700000000"
            password:
              type: string
              format: password
              minLength: 8
              example: "SecurePass123!"
    responses:
      201:
        description: Admin registered successfully.
      400:
        description: Invalid or missing input.
      409:
        description: Email already registered.
      415:
        description: Content-Type must be application/json.
      500:
        description: Registration failed.
    """
    if not request.is_json:
        return jsonify(
            success=False,
            message="Content-Type must be application/json.",
        ), 415

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            success=False,
            message="Provide a valid JSON object.",
        ), 400

    try:
        first_name = data.get("first_name")
        email = data.get("email")
        password = data.get("password")

        # Validate optional fields.
        optional_fields = {}

        for field, max_length in (
            ("last_name", 100),
            ("phone", 30),
        ):
            value = data.get(field)

            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(
                        f"{field} must be a string."
                    )

                value = value.strip() or None

                if value and len(value) > max_length:
                    raise ValueError(
                        f"{field} must not exceed "
                        f"{max_length} characters."
                    )

            optional_fields[field] = value

        # The User model validates and normalizes email
        # and first_name.
        admin = User(
            first_name=first_name,
            last_name=optional_fields["last_name"],
            email=email,
            phone=optional_fields["phone"],
            role="admin",
        )

        # Required: validate and hash the password.
        admin.set_password(password)

        # Check for an existing account.
        existing_user = db.session.execute(
            db.select(User).where(
                User.email == admin.email
            )
        ).scalar_one_or_none()

        if existing_user:
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        db.session.add(admin)
        db.session.commit()

        return jsonify(
            success=True,
            message="Admin registered successfully.",
            data=admin.to_dict(),
        ), 201

    except ValueError as error:
        db.session.rollback()

        return jsonify(
            success=False,
            message=str(error),
        ), 400

    except IntegrityError as error:
        db.session.rollback()

        if getattr(error.orig, "sqlstate", None) == "23505":
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        current_app.logger.exception(
            "Admin registration constraint error"
        )

        return jsonify(
            success=False,
            message="Unable to register admin.",
        ), 500

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Admin registration failed"
        )

        return jsonify(
            success=False,
            message="Unable to register admin.",
        ), 500


apprentice_auth_bp = Blueprint( "apprentice_auth", __name__, url_prefix="/api/apprentice",)
@apprentice_auth_bp.post("/register")
def register_apprentice():
    """
    Register an apprentice.
    ---
    tags:
      - Apprentice Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - first_name
            - email
            - password
          properties:
            first_name:
              type: string
              example: Jane
            last_name:
              type: string
              example: Nakato
            email:
              type: string
              format: email
              example: jane@example.com
            phone:
              type: string
              example: "+256700000000"
            password:
              type: string
              format: password
              minLength: 8
              example: "SecurePass123!"
    responses:
      201:
        description: Apprentice registered successfully.
      400:
        description: Invalid or missing input.
      409:
        description: Email already registered.
      415:
        description: Content-Type must be application/json.
      500:
        description: Registration failed.
    """
    if not request.is_json:
        return jsonify(
            success=False,
            message="Content-Type must be application/json.",
        ), 415

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            success=False,
            message="Provide a valid JSON object.",
        ), 400

    try:
        # Required fields: first_name, email, password.
        first_name = data.get("first_name")
        email = data.get("email")
        password = data.get("password")

        if not isinstance(first_name, str) or not first_name.strip():
            raise ValueError("First name is required.")

        if not isinstance(email, str) or not email.strip():
            raise ValueError("Email is required.")

        if not isinstance(password, str) or len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

        # Validate optional fields.
        optional_fields = {}

        for field, max_length in (
            ("last_name", 100),
            ("phone", 30),
        ):
            value = data.get(field)

            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(
                        f"{field} must be a string."
                    )

                value = value.strip() or None

                if value and len(value) > max_length:
                    raise ValueError(
                        f"{field} must not exceed "
                        f"{max_length} characters."
                    )

            optional_fields[field] = value

        # Always assign the apprentice role on the server.
        apprentice = User(
            first_name=first_name,
            last_name=optional_fields["last_name"],
            email=email,
            phone=optional_fields["phone"],
            role="apprentice",
        )

        # Hash the password before saving it.
        apprentice.set_password(password)

        # Check for an existing account.
        existing_user = db.session.execute(
            db.select(User).where(
                User.email == apprentice.email
            )
        ).scalar_one_or_none()

        if existing_user:
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        db.session.add(apprentice)
        db.session.commit()

        return jsonify(
            success=True,
            message="Apprentice registered successfully.",
            data=apprentice.to_dict(),
        ), 201

    except ValueError as error:
        db.session.rollback()

        return jsonify(
            success=False,
            message=str(error),
        ), 400

    except IntegrityError as error:
        db.session.rollback()

        # PostgreSQL duplicate-key violation.
        if getattr(error.orig, "sqlstate", None) == "23505":
            return jsonify(
                success=False,
                message="An account with this email already exists.",
            ), 409

        current_app.logger.exception(
            "Apprentice registration constraint error"
        )

        return jsonify(
            success=False,
            message="Unable to register apprentice.",
        ), 500

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Apprentice registration failed"
        )

        return jsonify(
            success=False,
            message="Unable to register apprentice.",
        ), 500



auth_login_bp = Blueprint("auth_login", __name__)


def _login_user(expected_role):
    """Authenticate a user and issue a JWT access token."""

    if not request.is_json:
        return jsonify(
            success=False,
            message="Content-Type must be application/json.",
        ), 415

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            success=False,
            message="Provide a valid JSON object.",
        ), 400

    email = data.get("email")
    password = data.get("password")

    # Both email and password are required.
    if not isinstance(email, str) or not email.strip():
        return jsonify(
            success=False,
            message="Email is required.",
        ), 400

    if not isinstance(password, str) or not password:
        return jsonify(
            success=False,
            message="Password is required.",
        ), 400

    try:
        normalized_email = email.strip().lower()

        user = db.session.execute(
            db.select(User).where(
                User.email == normalized_email,
                User.role == expected_role,
            )
        ).scalar_one_or_none()

        # Use a generic error to avoid revealing which accounts exist.
        if user is None or not user.check_password(password):
            return jsonify(
                success=False,
                message="Invalid email or password.",
            ), 401

        if not user.is_active:
            return jsonify(
                success=False,
                message="This account is inactive.",
            ), 403

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": user.role,
            },
        )

        return jsonify(
            success=True,
            message="Login successful.",
            data={
                "access_token": access_token,
                "token_type": "Bearer",
                "user": user.to_dict(),
            },
        ), 200

    except SQLAlchemyError:
        current_app.logger.exception("Login database error")

        return jsonify(
            success=False,
            message="Unable to log in at this time.",
        ), 500


@auth_login_bp.post("/api/apprentice/login")
def login_apprentice():
    """
    Apprentice login.
    ---
    tags:
      - Apprentice Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              example: jane@example.com
            password:
              type: string
              format: password
              example: "SecurePass123!"
    responses:
      200:
        description: Login successful; returns a JWT access token.
      400:
        description: Email or password is missing.
      401:
        description: Invalid credentials.
      403:
        description: Account is inactive.
      415:
        description: Content-Type must be application/json.
    """
    return _login_user("apprentice")


@auth_login_bp.post("/api/employer/login")
def login_employer():
    """
    Employer login.
    ---
    tags:
      - Employer Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              example: grace@example.com
            password:
              type: string
              format: password
              example: "SecurePass123!"
    responses:
      200:
        description: Login successful; returns a JWT access token.
      400:
        description: Email or password is missing.
      401:
        description: Invalid credentials.
      403:
        description: Account is inactive.
      415:
        description: Content-Type must be application/json.
    """
    return _login_user("employer")


@auth_login_bp.post("/api/admin/login")
def login_admin():
    """
    Admin login.
    ---
    tags:
      - Admin Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              example: admin@example.com
            password:
              type: string
              format: password
              example: "SecurePass123!"
    responses:
      200:
        description: Login successful; returns a JWT access token.
      400:
        description: Email or password is missing.
      401:
        description: Invalid credentials.
      403:
        description: Account is inactive.
      415:
        description: Content-Type must be application/json.
    """
    return _login_user("admin")


