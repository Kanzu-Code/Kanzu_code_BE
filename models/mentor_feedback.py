
import uuid
from datetime import datetime, timezone

from config.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class MentorFeedback(db.Model):
    __tablename__ = "mentor_feedback"

    __table_args__ = (
        db.CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="ck_feedback_valid_rating",
        ),
        db.CheckConstraint(
            "length(trim(comment)) > 0",
            name="ck_feedback_comment_required",
        ),
        db.CheckConstraint(
            "decision IN ('approved', 'changes_requested')",
            name="ck_feedback_valid_decision",
        ),
    )

    id = db.Column( db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)
    submission_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("milestone_submissions.id", ondelete="CASCADE"), nullable=False, index=True,)
    mentor_id = db.Column( db.UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,)
    rating = db.Column( db.Integer, nullable=False,)
    comment = db.Column( db.String(1000), nullable=False,)
    decision = db.Column( db.String(30), nullable=False,)
    created_at = db.Column( db.DateTime(timezone=True), nullable=False, default=utc_now,)
    submission = db.relationship( "MilestoneSubmission", back_populates="feedback_entries",)
    mentor = db.relationship( "User", foreign_keys=[mentor_id],)

    def to_dict(self):
        return {
            "id": str(self.id),
            "submission_id": str(self.submission_id),
            "mentor_id": str(self.mentor_id),
            "mentor_name": self.mentor.full_name,
            "rating": self.rating,
            "comment": self.comment,
            "decision": self.decision,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            ),
        }

    def __repr__(self):
        return f"<MentorFeedback {self.id} decision={self.decision}>"
