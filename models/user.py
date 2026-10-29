import uuid
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from config.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('apprentice', 'employer', 'admin')",
            name="ck_users_valid_role",
        ),
        db.CheckConstraint(
            "length(trim(first_name)) > 0",
            name="ck_users_first_name_required",
        ),
        db.CheckConstraint(
            "length(trim(email)) > 0",
            name="ck_users_email_required",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column( db.String(255), nullable=False, unique=True, index=True,)
    phone = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column( db.String(20), nullable=False, default="apprentice", server_default="apprentice",)
    is_active = db.Column( db.Boolean, nullable=False, default=True, server_default=db.true(),)
    created_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now,)
    updated_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,)

    @db.validates("email")
    def validate_email(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Email is required.")

        value = value.strip().lower()

        if (
            len(value) > 255
            or value.count("@") != 1
            or any(character.isspace() for character in value)
        ):
            raise ValueError("Provide a valid email address.")

        local_part, domain = value.split("@")

        if not local_part or not domain:
            raise ValueError("Provide a valid email address.")

        return value

    @db.validates("first_name")
    def validate_first_name(self, key, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("First name is required.")

        value = value.strip()

        if len(value) > 100:
            raise ValueError("First name must not exceed 100 characters.")

        return value

    @db.validates("role")
    def validate_role(self, key, value):
        allowed_roles = {"apprentice", "employer", "admin"}

        if value not in allowed_roles:
            raise ValueError(
                "Role must be apprentice, employer, or admin."
            )

        return value

    def set_password(self, password):
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")

        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not isinstance(password, str) or not self.password_hash:
            return False

        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return " ".join(
            part for part in (self.first_name, self.last_name) if part
        )

    def to_dict(self):
        return {
            "id": str(self.id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
        }

    def __repr__(self):
        return f"<User {self.id} role={self.role}>"