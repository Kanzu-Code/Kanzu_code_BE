
import uuid
from datetime import datetime, timezone

from config.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class MilestonePayment(db.Model):
    __tablename__ = "milestone_payments"

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('not_yet_due', 'due', 'paid')",
            name="ck_payments_valid_status",
        ),
        db.CheckConstraint(
            "amount > 0",
            name="ck_payments_positive_amount",
        ),
        db.CheckConstraint(
            "(status != 'paid') OR paid_at IS NOT NULL",
            name="ck_payments_paid_requires_timestamp",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    milestone_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False, unique=True, index=True,)
    amount = db.Column( db.Integer, nullable=False, default=100000, server_default="100000",)
    status = db.Column( db.String(30), nullable=False, default="not_yet_due", server_default="not_yet_due",)
    due_at = db.Column( db.DateTime(timezone=True), nullable=True,)
    paid_at = db.Column( db.DateTime(timezone=True), nullable=True,)
    created_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now,)
    updated_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,)
    milestone = db.relationship( "Milestone", back_populates="payment",)

    def to_dict(self):
        return {
            "id": str(self.id),
            "milestone_id": str(self.milestone_id),
            "amount": self.amount,
            "currency": "UGX",
            "status": self.status,
            "due_at": (
                self.due_at.isoformat() if self.due_at else None
            ),
            "paid_at": (
                self.paid_at.isoformat() if self.paid_at else None
            ),
        }

    def __repr__(self):
        return f"<MilestonePayment {self.id} status={self.status}>"
