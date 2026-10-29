
import uuid
from datetime import datetime, timezone

from config.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class Milestone(db.Model):
    __tablename__ = "milestones"

    __table_args__ = (
        db.CheckConstraint(
            "week_number IN (1, 3, 6, 8)",
            name="ck_milestones_valid_week",
        ),
        db.CheckConstraint(
            "status IN ('not_started', 'in_progress', "
            "'awaiting_review', 'changes_requested', 'completed')",
            name="ck_milestones_valid_status",
        ),
        db.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_milestones_title_required",
        ),
        db.UniqueConstraint(
            "apprenticeship_id",
            "week_number",
            name="uq_milestones_apprenticeship_week",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    apprenticeship_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("apprenticeships.id", ondelete="CASCADE"), nullable=False, index=True,)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    week_number = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column( db.String(30), nullable=False, default="not_started", server_default="not_started",)
    completed_at = db.Column( db.DateTime(timezone=True), nullable=True,)
    created_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now,)
    updated_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,)
    apprenticeship = db.relationship( "Apprenticeship", backref=db.backref(     "milestones",     lazy=True,     cascade="all, delete-orphan", ),)
    submissions = db.relationship( "MilestoneSubmission", back_populates="milestone", lazy=True, cascade="all, delete-orphan", order_by="MilestoneSubmission.submitted_at.desc()",)
    payment = db.relationship( "MilestonePayment", back_populates="milestone", uselist=False, cascade="all, delete-orphan",)

    def to_dict(self):
        return {
            "id": str(self.id),
            "apprenticeship_id": str(self.apprenticeship_id),
            "title": self.title,
            "description": self.description,
            "week_number": self.week_number,
            "due_date": self.due_date.isoformat(),
            "status": self.status,
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at else None
            ),
            "payment": self.payment.to_dict() if self.payment else None,
        }

    def __repr__(self):
        return f"<Milestone {self.title} status={self.status}>"


class MilestoneSubmission(db.Model):
    __tablename__ = "milestone_submissions"

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'changes_requested')",
            name="ck_submissions_valid_status",
        ),
        db.CheckConstraint(
            "length(trim(submission_text)) > 0",
            name="ck_submissions_text_required",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    milestone_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False, index=True,)
    submitted_by = db.Column( db.UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,)
    submission_text = db.Column(db.Text,nullable=False,)
    submitted_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utc_now,)
    status = db.Column( db.String(30), nullable=False, default="pending", server_default="pending",)
    milestone = db.relationship( "Milestone", back_populates="submissions",)
    apprentice = db.relationship("User",foreign_keys=[submitted_by],)
    feedback_entries = db.relationship( "MentorFeedback", back_populates="submission", lazy=True, cascade="all, delete-orphan", order_by="MentorFeedback.created_at.desc()",)

    def to_dict(self):
        return {
            "id": str(self.id),
            "milestone_id": str(self.milestone_id),
            "submitted_by": str(self.submitted_by),
            "apprentice_name": self.apprentice.full_name,
            "submission_text": self.submission_text,
            "submitted_at": (
                self.submitted_at.isoformat()
                if self.submitted_at else None
            ),
            "status": self.status,
            "feedback": [
                feedback.to_dict()
                for feedback in self.feedback_entries
            ],
        }

    def __repr__(self):
        return f"<MilestoneSubmission {self.id} status={self.status}>"