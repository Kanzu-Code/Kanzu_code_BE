
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from config.extensions import db

from models.apprenticeship import Apprenticeship
from models.user import User
from models.milestone import Milestone
from models.milestone import MilestoneSubmission
from models.mentor_feedback import MentorFeedback
from models.milestone_payment import MilestonePayment


apprenticeship_bp = Blueprint( "apprenticeships", __name__, url_prefix="/api",)

MILESTONES = [
    (1, "Onboarding complete", "Complete onboarding requirements."),
    (3, "First task delivered", "Deliver the first assigned task."),
    (6, "A feature shipped", "Complete and ship a feature."),
    (8, "Final review", "Complete the final apprenticeship review."),
]


# Shared helpers

def error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def success(data, status=200):
    return jsonify({"success": True, "data": data}), status


def parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def current_user():
    user_id = parse_uuid(get_jwt_identity())
    if not user_id:
        return None
    return db.session.get(User, user_id)


def require_roles(*roles):
    """Call inside a JWT-protected route."""
    user = current_user()

    if not user:
        return None, error("User not found.", 401)

    if not user.is_active:
        return None, error("Account is inactive.", 403)

    if user.role not in roles:
        return None, error("You are not authorized.", 403)

    return user, None


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")


def get_apprenticeship_access(user, apprenticeship):
    """Check whether a user can access an apprenticeship."""
    if user.role == "admin":
        return True

    if user.role == "employer":
        return apprenticeship.employer_id == user.id

    if user.role == "apprentice":
        return apprenticeship.apprentice_id == user.id

    return False


def get_milestone_access(user, milestone):
    apprenticeship = db.session.get(
        Apprenticeship, milestone.apprenticeship_id
    )
    if not apprenticeship:
        return None, False

    return apprenticeship, get_apprenticeship_access(
        user, apprenticeship
    )


def get_submission_access(user, submission):
    milestone = db.session.get(Milestone, submission.milestone_id)
    if not milestone:
        return None, None, False

    apprenticeship, allowed = get_milestone_access(user, milestone)
    return milestone, apprenticeship, allowed


def overdue(milestone):
    """More than 14 days overdue and not yet approved."""
    return (
        milestone.status != "completed"
        and (date.today() - milestone.due_date).days > 14
    )


def commit_or_error():
    try:
        db.session.commit()
        return None
    except IntegrityError:
        db.session.rollback()
        return error(
            "The operation conflicts with existing records or constraints.",
            409,
        )


# Apprenticeship routes
@apprenticeship_bp.post("/apprenticeships")
@jwt_required()
def create_apprenticeship():
    """
    Create an apprenticeship.

    ---
    tags:
      - Apprenticeships
    summary: Create an apprenticeship and its four milestones
    description: >
      Employers can create apprenticeships for themselves.
      Admins can select an employer. Automatically creates
      four milestones and a UGX 100,000 payment record for
      each milestone.
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - apprentice_id
              - start_date
            properties:
              apprentice_id:
                type: string
                format: uuid
                description: Existing user with the apprentice role
              employer_id:
                type: string
                format: uuid
                description: Required when an admin creates the record
              start_date:
                type: string
                format: date
                example: "2026-10-29"
              end_date:
                type: string
                format: date
                nullable: true
                example: "2026-12-24"
    responses:
      201:
        description: Apprenticeship created successfully
      400:
        description: Invalid or missing input
      401:
        description: Missing or invalid JWT
      403:
        description: Insufficient permissions
      409:
        description: Database constraint conflict
    """
    user, denied = require_roles("employer", "admin")
    if denied:
        return denied

    data = request.get_json(silent=True) or {}

    apprentice_id = parse_uuid(data.get("apprentice_id"))
    if not apprentice_id:
        return error("A valid apprentice_id is required.")

    apprentice = db.session.get(User, apprentice_id)
    if not apprentice or apprentice.role != "apprentice":
        return error("Select a valid apprentice.")

    if not apprentice.is_active:
        return error("The apprentice account is inactive.", 409)

    # Employers may assign apprentices only to themselves.
    employer_id = user.id
    if user.role == "admin":
        employer_id = parse_uuid(data.get("employer_id"))
        if not employer_id:
            return error("A valid employer_id is required.")

    employer = db.session.get(User, employer_id)
    if not employer or employer.role != "employer":
        return error("Select a valid employer.")

    if not employer.is_active:
        return error("The employer account is inactive.", 409)

    try:
        start_date = parse_date(data.get("start_date"), "start_date")
        end_date = (
            parse_date(data["end_date"], "end_date")
            if data.get("end_date") else None
        )
    except ValueError as exc:
        return error(str(exc))

    if end_date and end_date < start_date:
        return error("end_date cannot be before start_date.")

    apprenticeship = Apprenticeship(
        apprentice_id=apprentice.id,
        employer_id=employer.id,
        start_date=start_date,
        end_date=end_date,
        status="active",
    )

    try:
        db.session.add(apprenticeship)
        db.session.flush()

        # Generate the four milestone and payment records.
        for week, title, description in MILESTONES:
            milestone = Milestone(
                apprenticeship_id=apprenticeship.id,
                title=title,
                description=description,
                week_number=week,
                due_date=start_date + timedelta(weeks=week),
                status="not_started",
            )
            db.session.add(milestone)
            db.session.flush()

            db.session.add(
                MilestonePayment(
                    milestone_id=milestone.id,
                    amount=100000,
                    status="not_yet_due",
                )
            )

        db.session.commit()
    except (IntegrityError, ValueError):
        db.session.rollback()
        return error("Could not create the apprenticeship.", 409)

    return success(apprenticeship.to_dict(), 201)


@apprenticeship_bp.get("/apprenticeships")
@jwt_required()
def list_apprenticeships():
    """
    List apprenticeships accessible to the authenticated user.
    ---
    tags:
      - Apprenticeships
    security:
      - Bearer: []
    responses:
      200:
        description: Apprenticeships retrieved successfully.
        schema:
          type: object
          properties:
            apprenticeships:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  apprentice_id:
                    type: string
                  employer_id:
                    type: string
                  status:
                    type: string
                    example: active
      401:
        description: Missing or invalid JWT.
      403:
        description: User is not authorized to access these apprenticeships.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    query = Apprenticeship.query

    if user.role == "apprentice":
        query = query.filter_by(apprentice_id=user.id)
    elif user.role == "employer":
        query = query.filter_by(employer_id=user.id)

    if request.args.get("status"):
        query = query.filter_by(status=request.args["status"])

    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)

    pagination = query.order_by(
        Apprenticeship.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return success({
        "items": [item.to_dict() for item in pagination.items],
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@apprenticeship_bp.get("/apprenticeships/<uuid:apprenticeship_id>")
@jwt_required()
def get_apprenticeship(apprenticeship_id):
    """
    Retrieve an apprenticeship by ID.
    ---
    tags:
      - Apprenticeships
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
        description: UUID of the apprenticeship.
    responses:
      200:
        description: Apprenticeship retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    apprenticeship = db.session.get(Apprenticeship, apprenticeship_id)
    if not apprenticeship:
        return error("Apprenticeship not found.", 404)

    if not get_apprenticeship_access(user, apprenticeship):
        return error("You cannot access this apprenticeship.", 403)

    return success(apprenticeship.to_dict())


@apprenticeship_bp.patch("/apprenticeships/<uuid:apprenticeship_id>")
@jwt_required()
def update_apprenticeship(apprenticeship_id):
    """
    Update an apprenticeship.
    ---
    tags:
      - Apprenticeships
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            start_date:
              type: string
              format: date
              example: "2026-10-01"
            end_date:
              type: string
              format: date
              example: "2027-04-01"
            status:
              type: string
              enum: [active, completed, paused]
    responses:
      200:
        description: Apprenticeship updated successfully.
      400:
        description: Invalid update data.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("employer", "admin")
    if denied:
        return denied

    apprenticeship = db.session.get(Apprenticeship, apprenticeship_id)
    if not apprenticeship:
        return error("Apprenticeship not found.", 404)

    if user.role == "employer" and apprenticeship.employer_id != user.id:
        return error("You cannot manage this apprenticeship.", 403)

    data = request.get_json(silent=True) or {}

    if "status" in data:
        if data["status"] not in {"active", "completed", "paused"}:
            return error("Invalid apprenticeship status.")
        apprenticeship.status = data["status"]

    if "end_date" in data:
        try:
            apprenticeship.end_date = (
                parse_date(data["end_date"], "end_date")
                if data["end_date"] else None
            )
        except ValueError as exc:
            return error(str(exc))

    if (
        apprenticeship.end_date
        and apprenticeship.end_date < apprenticeship.start_date
    ):
        return error("end_date cannot be before start_date.")

    db.session.commit()
    return success(apprenticeship.to_dict())


@apprenticeship_bp.delete("/apprenticeships/<uuid:apprenticeship_id>")
@jwt_required()
def delete_apprenticeship(apprenticeship_id):
    """
    Delete an apprenticeship.
    ---
    tags:
      - Apprenticeships
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Apprenticeship deleted successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    apprenticeship = db.session.get(Apprenticeship, apprenticeship_id)
    if not apprenticeship:
        return error("Apprenticeship not found.", 404)

    db.session.delete(apprenticeship)
    db.session.commit()
    return success({"message": "Apprenticeship deleted."})


# Milestone routes
@apprenticeship_bp.post("/milestones")
@jwt_required()
def create_milestone():
    """
    Create a milestone for an apprenticeship.
    ---
    tags:
      - Milestones
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - title
            - week_number
            - due_date
          properties:
            title:
              type: string
              example: Build the authentication API
            description:
              type: string
              example: Implement registration and JWT login.
            week_number:
              type: integer
              enum: [1, 3, 6, 8]
            due_date:
              type: string
              format: date
              example: "2026-11-05"
    responses:
      201:
        description: Milestone created successfully.
      400:
        description: Invalid milestone data.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("admin", "employer")
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    apprenticeship_id = parse_uuid(data.get("apprenticeship_id"))
    if not apprenticeship_id:
        return error("A valid apprenticeship_id is required.")

    apprenticeship = db.session.get(Apprenticeship, apprenticeship_id)
    if not apprenticeship:
        return error("Apprenticeship not found.", 404)

    if user.role == "employer" and apprenticeship.employer_id != user.id:
        return error("You cannot manage this apprenticeship.", 403)

    # The four standard milestones are created with the apprenticeship.
    # Only admins may create custom milestones.
    if user.role != "admin":
        return error("Only admins can add additional milestones.", 403)

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return error("title is required.")

    try:
        week = int(data.get("week_number"))
        due_date = parse_date(data.get("due_date"), "due_date")
    except (ValueError, TypeError):
        return error("A valid week_number and due_date are required.")

    if week not in {1, 3, 6, 8}:
        return error("week_number must be 1, 3, 6, or 8.")

    milestone = Milestone(
        apprenticeship_id=apprenticeship.id,
        title=title.strip(),
        description=data.get("description"),
        week_number=week,
        due_date=due_date,
        status="not_started",
    )

    db.session.add(milestone)
    db.session.flush()
    db.session.add(
        MilestonePayment(milestone_id=milestone.id, amount=100000)
    )

    failure = commit_or_error()
    if failure:
        return failure

    return success(milestone.to_dict(), 201)


@apprenticeship_bp.get("/milestones")
@jwt_required()
def list_milestones():
    """
    List milestones belonging to an apprenticeship.
    ---
    tags:
      - Milestones
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Milestones retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    query = Milestone.query.join(
        Apprenticeship,
        Milestone.apprenticeship_id == Apprenticeship.id,
    )

    if user.role == "apprentice":
        query = query.filter(Apprenticeship.apprentice_id == user.id)
    elif user.role == "employer":
        query = query.filter(Apprenticeship.employer_id == user.id)

    if request.args.get("apprenticeship_id"):
        aid = parse_uuid(request.args["apprenticeship_id"])
        if not aid:
            return error("Invalid apprenticeship_id.")
        query = query.filter(Milestone.apprenticeship_id == aid)

    if request.args.get("status"):
        query = query.filter_by(status=request.args["status"])

    return success([m.to_dict() for m in query.order_by(
        Milestone.due_date.asc()
    ).all()])


@apprenticeship_bp.get("/milestones/<uuid:milestone_id>")
@jwt_required()
def get_milestone(milestone_id):
    """
    Retrieve a milestone by ID.
    ---
    tags:
      - Milestones
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Milestone retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Milestone not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    milestone = db.session.get(Milestone, milestone_id)
    if not milestone:
        return error("Milestone not found.", 404)

    _, allowed = get_milestone_access(user, milestone)
    if not allowed:
        return error("You cannot access this milestone.", 403)

    result = milestone.to_dict()
    result["overdue"] = overdue(milestone)
    return success(result)


@apprenticeship_bp.patch("/milestones/<uuid:milestone_id>")
@jwt_required()
def update_milestone(milestone_id):
    """
    Update a milestone.
    ---
    tags:
      - Milestones
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
            description:
              type: string
            due_date:
              type: string
              format: date
            status:
              type: string
              enum:
                - not_started
                - in_progress
                - awaiting_review
                - changes_requested
                - completed
    responses:
      200:
        description: Milestone updated successfully.
      400:
        description: Invalid milestone data.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Milestone not found.
    """
    user, denied = require_roles("admin", "employer")
    if denied:
        return denied

    milestone = db.session.get(Milestone, milestone_id)
    if not milestone:
        return error("Milestone not found.", 404)

    apprenticeship, allowed = get_milestone_access(user, milestone)
    if not allowed:
        return error("You cannot manage this milestone.", 403)

    # Employers cannot manually approve milestones or edit completion state.
    if user.role == "employer":
        data = request.get_json(silent=True) or {}
        if any(k in data for k in ("status", "completed_at", "week_number")):
            return error("Only the review process can change milestone status.")
    else:
        data = request.get_json(silent=True) or {}
        if "status" in data and data["status"] not in {
            "not_started", "in_progress", "awaiting_review",
            "changes_requested", "completed",
        }:
            return error("Invalid milestone status.")

        # Admins cannot mark a milestone complete without a review either.
        if data.get("status") == "completed":
            return error("Milestones must be completed through mentor review.")

    if "title" in data:
        if not isinstance(data["title"], str) or not data["title"].strip():
            return error("title cannot be empty.")
        milestone.title = data["title"].strip()

    if "description" in data:
        milestone.description = data["description"]

    if "due_date" in data:
        try:
            milestone.due_date = parse_date(data["due_date"], "due_date")
        except ValueError as exc:
            return error(str(exc))

    if user.role == "admin":
        if "status" in data:
            milestone.status = data["status"]

    db.session.commit()
    return success(milestone.to_dict())


@apprenticeship_bp.delete("/milestones/<uuid:milestone_id>")
@jwt_required()
def delete_milestone(milestone_id):
    """
    Delete a milestone.
    ---
    tags:
      - Milestones
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Milestone deleted successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Milestone not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    milestone = db.session.get(Milestone, milestone_id)
    if not milestone:
        return error("Milestone not found.", 404)

    if milestone.submissions:
        return error("Cannot delete a milestone with submission history.", 409)

    db.session.delete(milestone)
    db.session.commit()
    return success({"message": "Milestone deleted."})


# Submission routes
@apprenticeship_bp.post("/milestones/<uuid:milestone_id>/submissions")
@jwt_required()
def submit_milestone(milestone_id):
    """
    Submit milestone work for mentor review.

    ---
    tags:
      - Submissions
    summary: Submit work for a milestone
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - submission_text
            properties:
              submission_text:
                type: string
                minLength: 1
                example: "Completed onboarding and documented the setup."
    responses:
      201:
        description: Submission created and milestone awaiting review
      400:
        description: Missing or invalid submission text
      403:
        description: User is not the assigned apprentice
      404:
        description: Milestone not found
      409:
        description: Milestone already completed or awaiting review
    """
    user, denied = require_roles("apprentice")
    if denied:
        return denied

    milestone = db.session.get(Milestone, milestone_id)
    if not milestone:
        return error("Milestone not found.", 404)

    apprenticeship = db.session.get(
        Apprenticeship, milestone.apprenticeship_id
    )
    if apprenticeship.apprentice_id != user.id:
        return error("You cannot submit work for another apprentice.", 403)

    if milestone.status == "completed":
        return error("This milestone is already completed.", 409)

    if milestone.status == "awaiting_review":
        return error("This milestone is already awaiting review.", 409)

    data = request.get_json(silent=True) or {}
    text = data.get("submission_text")

    if not isinstance(text, str) or not text.strip():
        return error("submission_text is required.")

    submission = MilestoneSubmission(
        milestone_id=milestone.id,
        submitted_by=user.id,
        submission_text=text.strip(),
        status="pending",
    )

    milestone.status = "awaiting_review"
    db.session.add(submission)
    db.session.commit()

    return success(submission.to_dict(), 201)


@apprenticeship_bp.get("/milestones/<uuid:milestone_id>/submissions")
@jwt_required()
def list_submissions(milestone_id):
    """
    List submissions for a milestone.
    ---
    tags:
      - Submissions
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Submissions retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Milestone not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    milestone = db.session.get(Milestone, milestone_id)
    if not milestone:
        return error("Milestone not found.", 404)

    _, allowed = get_milestone_access(user, milestone)
    if not allowed:
        return error("You cannot access these submissions.", 403)

    return success([
        s.to_dict() for s in MilestoneSubmission.query.filter_by(
            milestone_id=milestone.id
        ).order_by(MilestoneSubmission.submitted_at.desc()).all()
    ])


@apprenticeship_bp.get("/submissions/<uuid:submission_id>")
@jwt_required()
def get_submission(submission_id):
    """
    Retrieve a milestone submission by ID.
    ---
    tags:
      - Submissions
    security:
      - Bearer: []
    parameters:
      - name: submission_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Submission retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Submission not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    submission = db.session.get(MilestoneSubmission, submission_id)
    if not submission:
        return error("Submission not found.", 404)

    _, _, allowed = get_submission_access(user, submission)
    if not allowed:
        return error("You cannot access this submission.", 403)

    return success(submission.to_dict())


@apprenticeship_bp.patch("/submissions/<uuid:submission_id>")
@jwt_required()
def update_submission(submission_id):
    """
    Update a milestone submission.
    ---
    tags:
      - Submissions
    security:
      - Bearer: []
    parameters:
      - name: submission_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            submission_text:
              type: string
              example: "Implemented the required endpoints and tests."
    responses:
      200:
        description: Submission updated successfully.
      400:
        description: Invalid submission data.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Submission not found.
    """
    user, denied = require_roles("apprentice")
    if denied:
        return denied

    submission = db.session.get(MilestoneSubmission, submission_id)
    if not submission:
        return error("Submission not found.", 404)

    if submission.submitted_by != user.id:
        return error("You cannot edit another apprentice's submission.", 403)

    if submission.status != "pending":
        return error("Only pending submissions can be edited.", 409)

    data = request.get_json(silent=True) or {}
    text = data.get("submission_text")

    if not isinstance(text, str) or not text.strip():
        return error("submission_text is required.")

    submission.submission_text = text.strip()
    db.session.commit()
    return success(submission.to_dict())


@apprenticeship_bp.post("/submissions/<uuid:submission_id>/resubmit")
@jwt_required()
def resubmit_work(submission_id):
    """
    Resubmit a milestone after requested changes.
    ---
    tags:
      - Submissions
    security:
      - Bearer: []
    parameters:
      - name: milestone_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - submission_text
          properties:
            submission_text:
              type: string
              example: "Updated implementation addressing the mentor's feedback."
    responses:
      201:
        description: Milestone resubmitted successfully.
      400:
        description: Milestone cannot be resubmitted or request data is invalid.
      401:
        description: Missing or invalid JWT.
      403:
        description: Only the assigned apprentice may resubmit.
      404:
        description: Milestone not found.
    """
    user, denied = require_roles("apprentice")
    if denied:
        return denied

    previous = db.session.get(MilestoneSubmission, submission_id)
    if not previous:
        return error("Submission not found.", 404)

    if previous.submitted_by != user.id:
        return error("You cannot resubmit another apprentice's work.", 403)

    if previous.status != "changes_requested":
        return error("Only returned submissions can be resubmitted.", 409)

    data = request.get_json(silent=True) or {}
    text = data.get("submission_text")

    if not isinstance(text, str) or not text.strip():
        return error("submission_text is required.")

    milestone = db.session.get(Milestone, previous.milestone_id)

    new_submission = MilestoneSubmission(
        milestone_id=milestone.id,
        submitted_by=user.id,
        submission_text=text.strip(),
        status="pending",
    )

    milestone.status = "awaiting_review"
    db.session.add(new_submission)
    db.session.commit()

    return success(new_submission.to_dict(), 201)


@apprenticeship_bp.delete("/submissions/<uuid:submission_id>")
@jwt_required()
def delete_submission(submission_id):
    """
    Delete a milestone submission.
    ---
    tags:
      - Submissions
    security:
      - Bearer: []
    parameters:
      - name: submission_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Submission deleted successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Submission not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    submission = db.session.get(MilestoneSubmission, submission_id)
    if not submission:
        return error("Submission not found.", 404)

    if submission.feedback_entries:
        return error("Cannot delete a submission with review history.", 409)

    db.session.delete(submission)
    db.session.commit()
    return success({"message": "Submission deleted."})


# Employer review / feedback routes
@apprenticeship_bp.post("/submissions/<uuid:submission_id>/reviews")
@jwt_required()
def review_submission(submission_id):
    """
    Review an apprentice submission.

    ---
    tags:
      - Mentor Feedback
    summary: Approve work or request changes
    description: >
      The assigned employer must provide a rating from 1 to 5,
      a non-empty comment, and a decision. Approval completes
      the milestone and makes its payment due. Requesting changes
      keeps the payment not yet due.
    security:
      - Bearer: []
    parameters:
      - name: submission_id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - rating
              - comment
              - decision
            properties:
              rating:
                type: integer
                minimum: 1
                maximum: 5
                example: 5
              comment:
                type: string
                minLength: 1
                example: "Great work. The milestone requirements are met."
              decision:
                type: string
                enum:
                  - approved
                  - changes_requested
                example: approved
    responses:
      200:
        description: Review saved and milestone/payment updated
      400:
        description: Invalid rating, comment, or decision
      403:
        description: Reviewer is not authorized
      404:
        description: Submission not found
      409:
        description: Submission has already been reviewed
    """
    user, denied = require_roles("employer", "admin")
    if denied:
        return denied

    submission = db.session.get(MilestoneSubmission, submission_id)
    if not submission:
        return error("Submission not found.", 404)

    milestone = db.session.get(Milestone, submission.milestone_id)
    apprenticeship = db.session.get(
        Apprenticeship, milestone.apprenticeship_id
    )

    if user.role == "employer" and apprenticeship.employer_id != user.id:
        return error("You cannot review this apprentice's work.", 403)

    if submission.status != "pending":
        return error("This submission has already been reviewed.", 409)

    data = request.get_json(silent=True) or {}

    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return error("rating must be an integer from 1 to 5.")

    comment = data.get("comment")
    decision = data.get("decision")

    if rating not in range(1, 6):
        return error("rating must be between 1 and 5.")

    if not isinstance(comment, str) or not comment.strip():
        return error("A feedback comment is required.")

    if len(comment.strip()) > 1000:
        return error("Comment cannot exceed 1000 characters.")

    if decision not in {"approved", "changes_requested"}:
        return error("decision must be approved or changes_requested.")

    feedback = MentorFeedback(
        submission_id=submission.id,
        mentor_id=user.id,
        rating=rating,
        comment=comment.strip(),
        decision=decision,
    )

    submission.status = decision
    payment = milestone.payment

    if decision == "approved":
        milestone.status = "completed"
        milestone.completed_at = datetime.now(timezone.utc)

        if payment:
            payment.status = "due"
            payment.due_at = datetime.now(timezone.utc)
            payment.paid_at = None
        else:
            payment = MilestonePayment(
                milestone_id=milestone.id,
                amount=100000,
                status="due",
                due_at=datetime.now(timezone.utc),
            )
            db.session.add(payment)
    else:
        milestone.status = "changes_requested"
        milestone.completed_at = None

        # A returned milestone must not have a payable amount.
        if payment and payment.status != "paid":
            payment.status = "not_yet_due"
            payment.due_at = None
            payment.paid_at = None

    db.session.add(feedback)

    failure = commit_or_error()
    if failure:
        return failure

    return success({
        "submission": submission.to_dict(),
        "milestone": milestone.to_dict(),
        "feedback": feedback.to_dict(),
        "payment": payment.to_dict() if payment else None,
    })


@apprenticeship_bp.get("/submissions/<uuid:submission_id>/reviews")
@jwt_required()
def list_reviews(submission_id):
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    submission = db.session.get(MilestoneSubmission, submission_id)
    if not submission:
        return error("Submission not found.", 404)

    _, _, allowed = get_submission_access(user, submission)
    if not allowed:
        return error("You cannot access these reviews.", 403)

    return success([
        f.to_dict() for f in MentorFeedback.query.filter_by(
            submission_id=submission.id
        ).order_by(MentorFeedback.created_at.desc()).all()
    ])


@apprenticeship_bp.get("/feedback/<uuid:feedback_id>")
@jwt_required()
def get_feedback(feedback_id):
    """
    Retrieve a mentor feedback record.
    ---
    tags:
      - Mentor Feedback
    security:
      - Bearer: []
    parameters:
      - name: feedback_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Feedback retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Feedback not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    feedback = db.session.get(MentorFeedback, feedback_id)
    if not feedback:
        return error("Feedback not found.", 404)

    _, _, allowed = get_submission_access(user, feedback.submission)
    if not allowed:
        return error("You cannot access this feedback.", 403)

    return success(feedback.to_dict())


@apprenticeship_bp.patch("/feedback/<uuid:feedback_id>")
@jwt_required()
def update_feedback(feedback_id):
    """
    Update mentor feedback.
    ---
    tags:
      - Mentor Feedback
    security:
      - Bearer: []
    parameters:
      - name: feedback_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            rating:
              type: integer
              minimum: 1
              maximum: 5
              example: 4
            comment:
              type: string
              example: "Good progress. Improve input validation."
            decision:
              type: string
              enum: [approved, changes_requested]
    responses:
      200:
        description: Feedback updated successfully.
      400:
        description: Invalid feedback data.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Feedback not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    feedback = db.session.get(MentorFeedback, feedback_id)
    if not feedback:
        return error("Feedback not found.", 404)

    data = request.get_json(silent=True) or {}

    if "rating" in data:
        try:
            rating = int(data["rating"])
        except (ValueError, TypeError):
            return error("rating must be an integer from 1 to 5.")
        if rating not in range(1, 6):
            return error("rating must be between 1 and 5.")
        feedback.rating = rating

    if "comment" in data:
        comment = data["comment"]
        if not isinstance(comment, str) or not comment.strip():
            return error("comment cannot be empty.")
        if len(comment.strip()) > 1000:
            return error("Comment cannot exceed 1000 characters.")
        feedback.comment = comment.strip()

    db.session.commit()
    return success(feedback.to_dict())


@apprenticeship_bp.delete("/feedback/<uuid:feedback_id>")
@jwt_required()
def delete_feedback(feedback_id):
    """
    Delete mentor feedback.
    ---
    tags:
      - Mentor Feedback
    security:
      - Bearer: []
    parameters:
      - name: feedback_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Feedback deleted successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Feedback not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    feedback = db.session.get(MentorFeedback, feedback_id)
    if not feedback:
        return error("Feedback not found.", 404)

    db.session.delete(feedback)
    db.session.commit()
    return success({"message": "Feedback deleted."})


# Payment routes
@apprenticeship_bp.get("/payments")
@jwt_required()
def list_payments():
    """
    List milestone payments accessible to the authenticated user.
    ---
    tags:
      - Payments
    security:
      - Bearer: []
    parameters:
      - name: status
        in: query
        required: false
        type: string
        enum: [not_yet_due, due, paid]
        description: Optional payment status filter, if supported by the route.
    responses:
      200:
        description: Payments retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    query = MilestonePayment.query.join(
        Milestone,
        MilestonePayment.milestone_id == Milestone.id,
    ).join(
        Apprenticeship,
        Milestone.apprenticeship_id == Apprenticeship.id,
    )

    if user.role == "apprentice":
        query = query.filter(Apprenticeship.apprentice_id == user.id)
    elif user.role == "employer":
        query = query.filter(Apprenticeship.employer_id == user.id)

    if request.args.get("status"):
        status = request.args["status"]
        if status not in {"not_yet_due", "due", "paid"}:
            return error("Invalid payment status.")
        query = query.filter(MilestonePayment.status == status)

    return success([p.to_dict() for p in query.order_by(
        MilestonePayment.created_at.desc()
    ).all()])


@apprenticeship_bp.get("/payments/<uuid:payment_id>")
@jwt_required()
def get_payment(payment_id):
    """
    Retrieve a milestone payment by ID.
    ---
    tags:
      - Payments
    security:
      - Bearer: []
    parameters:
      - name: payment_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Payment retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Payment not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    payment = db.session.get(MilestonePayment, payment_id)
    if not payment:
        return error("Payment not found.", 404)

    _, allowed = get_milestone_access(user, payment.milestone)
    if not allowed:
        return error("You cannot access this payment.", 403)

    return success(payment.to_dict())


@apprenticeship_bp.post("/payments/<uuid:payment_id>/mark-paid")
@jwt_required()
def mark_payment_paid(payment_id):
    """
    Mark a milestone payment as paid.
    ---
    tags:
      - Payments
    security:
      - Bearer: []
    parameters:
      - name: payment_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Payment marked as paid successfully.
      400:
        description: Payment is not eligible to be marked as paid.
      401:
        description: Missing or invalid JWT.
      403:
        description: Only an authorized employer or administrator may perform this action.
      404:
        description: Payment not found.
    """
    user, denied = require_roles("employer", "admin")
    if denied:
        return denied

    payment = db.session.get(MilestonePayment, payment_id)
    if not payment:
        return error("Payment not found.", 404)

    apprenticeship = db.session.get(
        Apprenticeship, payment.milestone.apprenticeship_id
    )

    if user.role == "employer" and apprenticeship.employer_id != user.id:
        return error("You cannot record this payment.", 403)

    if payment.status != "due":
        return error("Only payments marked due can be recorded as paid.", 409)

    if payment.milestone.status != "completed":
        return error("The milestone must be approved before payment.", 409)

    payment.status = "paid"
    payment.paid_at = datetime.now(timezone.utc)

    db.session.commit()
    return success(payment.to_dict())


@apprenticeship_bp.patch("/payments/<uuid:payment_id>")
@jwt_required()
def update_payment(payment_id):
    """
    Update the amount assigned to a milestone payment.
    ---
    tags:
      - Payments
    security:
      - Bearer: []
    parameters:
      - name: payment_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - amount
          properties:
            amount:
              type: number
              minimum: 0
              example: 100000
    responses:
      200:
        description: Payment amount updated successfully.
      400:
        description: Invalid payment amount.
      401:
        description: Missing or invalid JWT.
      403:
        description: Only an administrator may update payment amounts.
      404:
        description: Payment not found.
    """
    user, denied = require_roles("admin")
    if denied:
        return denied

    payment = db.session.get(MilestonePayment, payment_id)
    if not payment:
        return error("Payment not found.", 404)

    data = request.get_json(silent=True) or {}

    if "amount" in data:
        try:
            amount = int(data["amount"])
        except (ValueError, TypeError):
            return error("amount must be a positive integer.")
        if amount <= 0:
            return error("amount must be a positive integer.")
        payment.amount = amount

    # Payment status is changed only through the review/payment workflow.
    if "status" in data or "paid_at" in data or "due_at" in data:
        return error(
            "Use the review and mark-paid endpoints to change payment status."
        )

    db.session.commit()
    return success(payment.to_dict())


# Progress dashboard and overdue reports
@apprenticeship_bp.get("/apprenticeships/<uuid:apprenticeship_id>/progress")
@jwt_required()
def apprenticeship_progress(apprenticeship_id):
    """
    Retrieve milestone completion progress for an apprenticeship.
    ---
    tags:
      - Dashboard
    security:
      - Bearer: []
    parameters:
      - name: apprenticeship_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Apprenticeship progress retrieved successfully.
        schema:
          type: object
          properties:
            apprenticeship_id:
              type: string
            total_milestones:
              type: integer
              example: 4
            completed_milestones:
              type: integer
              example: 2
            progress_percentage:
              type: number
              example: 50.0
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
      404:
        description: Apprenticeship not found.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    apprenticeship = db.session.get(Apprenticeship, apprenticeship_id)
    if not apprenticeship:
        return error("Apprenticeship not found.", 404)

    if not get_apprenticeship_access(user, apprenticeship):
        return error("You cannot access this apprenticeship.", 403)

    milestones = Milestone.query.filter_by(
        apprenticeship_id=apprenticeship.id
    ).order_by(Milestone.due_date.asc()).all()

    payments = [
        m.payment for m in milestones if m.payment is not None
    ]

    latest_feedback = []
    for milestone in milestones:
        for submission in milestone.submissions:
            for feedback in submission.feedback_entries:
                latest_feedback.append(feedback)

    latest_feedback.sort(
        key=lambda f: f.created_at or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True,
    )

    return success({
        "apprenticeship": apprenticeship.to_dict(),
        "total_milestones": len(milestones),
        "completed_milestones": sum(
            m.status == "completed" for m in milestones
        ),
        "remaining_milestones": sum(
            m.status != "completed" for m in milestones
        ),
        "overdue_milestones": sum(overdue(m) for m in milestones),
        "payments_due": sum(
            p.amount for p in payments if p.status == "due"
        ),
        "payments_paid": sum(
            p.amount for p in payments if p.status == "paid"
        ),
        "milestones": [
            {**m.to_dict(), "overdue": overdue(m)}
            for m in milestones
        ],
        "latest_feedback": [
            f.to_dict() for f in latest_feedback[:5]
        ],
    })


@apprenticeship_bp.get("/dashboard")
@jwt_required()
def dashboard():
    """
    Retrieve dashboard statistics for the authenticated user.
    ---
    tags:
      - Dashboard
    security:
      - Bearer: []
    responses:
      200:
        description: Dashboard statistics retrieved successfully.
        schema:
          type: object
          properties:
            total_apprenticeships:
              type: integer
              example: 5
            total_milestones:
              type: integer
              example: 20
            completed_milestones:
              type: integer
              example: 8
            pending_payments:
              type: number
              example: 400000
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
    """
    user, denied = require_roles("apprentice", "employer", "admin")
    if denied:
        return denied

    query = Apprenticeship.query

    if user.role == "apprentice":
        query = query.filter_by(apprentice_id=user.id)
    elif user.role == "employer":
        query = query.filter_by(employer_id=user.id)

    apprenticeships = query.all()
    results = []

    for apprenticeship in apprenticeships:
        milestones = Milestone.query.filter_by(
            apprenticeship_id=apprenticeship.id
        ).all()

        payments = [
            m.payment for m in milestones if m.payment is not None
        ]

        results.append({
            "apprenticeship": apprenticeship.to_dict(),
            "completed_milestones": sum(
                m.status == "completed" for m in milestones
            ),
            "total_milestones": len(milestones),
            "remaining_milestones": sum(
                m.status != "completed" for m in milestones
            ),
            "overdue_milestones": sum(overdue(m) for m in milestones),
            "payments_due": sum(
                p.amount for p in payments if p.status == "due"
            ),
            "payments_paid": sum(
                p.amount for p in payments if p.status == "paid"
            ),
        })

    return success({"items": results})


@apprenticeship_bp.get("/milestones/overdue")
@jwt_required()
def list_overdue_milestones():
    """
    List overdue milestones accessible to the authenticated user.
    ---
    tags:
      - Dashboard
    security:
      - Bearer: []
    responses:
      200:
        description: Overdue milestones retrieved successfully.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient permissions.
    """
    user, denied = require_roles("employer", "admin")
    if denied:
        return denied

    query = Milestone.query.join(
        Apprenticeship,
        Milestone.apprenticeship_id == Apprenticeship.id,
    )

    if user.role == "employer":
        query = query.filter(Apprenticeship.employer_id == user.id)

    results = [
        m for m in query.order_by(Milestone.due_date.asc()).all()
        if overdue(m)
    ]

    return success([
        {
            **m.to_dict(),
            "days_overdue": (date.today() - m.due_date).days,
            "flagged_for_review": True,
        }
        for m in results
    ])
