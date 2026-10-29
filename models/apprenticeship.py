
import uuid
from datetime import datetime, timezone
from config.extensions import db

def utc_now():
    return datetime.now(timezone.utc)

class Apprenticeship(db.Model):
    __tablename__ = "apprenticeships"

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'completed', 'paused')",
            name="ck_apprenticeships_valid_status",
        ),
        db.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_apprenticeships_valid_dates",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    apprentice_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,)
    employer_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,)
    start_date = db.Column( db.Date, nullable=False,)
    end_date = db.Column( db.Date, nullable=True,)
    status = db.Column( db.String(20), nullable=False, default="active", server_default="active",)
    created_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now,)
    updated_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,)
    
    # Relationships to User
    apprentice = db.relationship( "User", foreign_keys=[apprentice_id], backref=db.backref("apprenticeships_as_apprentice", lazy=True),)
    employer = db.relationship( "User", foreign_keys=[employer_id], backref=db.backref("apprenticeships_as_employer", lazy=True),)

    def to_dict(self):
        return {
            "id": str(self.id),
            "apprentice_id": str(self.apprentice_id),
            "apprentice_name": self.apprentice.full_name,
            "employer_id": str(self.employer_id),
            "employer_name": self.employer.full_name,
            "start_date": self.start_date.isoformat(),
            "end_date": (
                self.end_date.isoformat() if self.end_date else None
            ),
            "status": self.status,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
        }

    def __repr__(self):
        return (
            f"<Apprenticeship {self.id} "
            f"apprentice={self.apprentice_id} "
            f"employer={self.employer_id}>"
        )
