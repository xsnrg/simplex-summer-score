from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, current_app as app
)
from collections import defaultdict
from .client_auth import admin_required
from . import db
from .models import Submission, ScoreMultiplier, User
from .scoring import score_submissions_for_operator

bp = Blueprint("main", __name__)


# -------------------------------------------------------
# PUBLIC ROUTES
# -------------------------------------------------------

@bp.route("/")
def index():
    return render_template("index.html", title="Summer of Simplex")


@bp.route("/submit", methods=["GET", "POST"])
def submit():
    """Public submission form."""
    if request.method == "POST":
        submitted_by = request.form.get("submitted_by", "").strip().upper()
        contact_call = request.form.get("contact_call", "").strip().upper()
        mode_type    = request.form.get("mode_type", "").strip()
        frequency    = request.form.get("frequency", "").strip()
        notes        = request.form.get("notes", "").strip()

        is_pota      = request.form.get("is_pota") == "yes"
        pota_park    = request.form.get("pota_park", "").strip().upper() if is_pota else None
        digital_mode = request.form.get("digital_mode", "").strip() if mode_type == "digital" else None

        errors = []
        if not submitted_by:
            errors.append("Your callsign is required.")
        if not contact_call:
            errors.append("Their callsign is required.")
        if mode_type not in ("voice", "digital"):
            errors.append("Please select a mode (Voice Simplex or Digital).")
        if mode_type == "digital" and not digital_mode:
            errors.append("Please select a digital mode.")
        if is_pota and not pota_park:
            errors.append("Please enter the POTA park reference (e.g. K-1234).")

        freq_val = None
        if frequency:
            try:
                freq_val = float(frequency)
            except ValueError:
                errors.append("Frequency must be a number (e.g. 146.520).")

        if errors:
            return render_template(
                "submit.html", title="Submit a Contact",
                errors=errors, form=request.form,
            )

        sub = Submission(
            submitted_by = submitted_by,
            contact_call = contact_call,
            mode_type    = mode_type,
            is_pota      = is_pota,
            pota_park    = pota_park,
            digital_mode = digital_mode,
            frequency    = freq_val,
            notes        = notes,
        )
        db.session.add(sub)
        db.session.commit()

        return render_template(
            "submit.html", title="Submit a Contact",
            success=f"Contact between {submitted_by} and {contact_call} submitted successfully!",
            form={},
        )

    return render_template("submit.html", title="Submit a Contact", form={})


@bp.route("/leaders")
def leaderboard():
    """Public leaderboard."""
    subs = Submission.query.filter_by(is_deleted=False).all()

    by_operator = defaultdict(list)
    for sub in subs:
        if sub.submitted_by:
            by_operator[sub.submitted_by.upper()].append(sub)

    results = []
    for operator, op_subs in by_operator.items():
        scored = score_submissions_for_operator(op_subs, operator_name=operator)
        summary = scored["by_operator"]
        results.append({
            "operator":       operator,
            "total_score":    summary["total_score"],
            "total_contacts": summary["total_contacts"],
        })

    results.sort(key=lambda r: r["total_score"], reverse=True)
    return render_template("leaderboard.html", title="Leaderboard", operators=results)


@bp.route("/operator/<callsign>")
def operator_page(callsign):
    """Page showing all submissions for a specific operator."""
    subs = Submission.query.filter(
        db.func.upper(Submission.submitted_by) == callsign.upper(),
        Submission.is_deleted == False,
    ).order_by(Submission.submitted_at.desc()).all()
    return render_template("operator.html", title=f"Operator: {callsign}", operator=callsign, submissions=subs)


# -------------------------------------------------------
# AUTH ROUTES  (login hidden from nav — go to /login directly)
# -------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    """Local login — not linked in the nav."""
    # Already logged in? Go straight to admin.
    if session.get('authenticated'):
        return redirect(url_for('main.admin_home'))

    error = None

    if request.method == "POST":
        callsign = request.form.get("callsign", "").strip().upper()
        password = request.form.get("password", "")

        user = User.query.filter_by(callsign=callsign, is_active=True).first()

        if user and user.check_password(password):
            session.clear()
            session['authenticated']  = True
            session['user']           = user.callsign
            session['user_id']        = user.id
            session['user_is_admin']  = user.is_admin
            session.permanent         = True

            next_page = session.pop('next_page', None)
            return redirect(next_page or url_for('main.admin_home'))
        else:
            error = "Invalid callsign or password."

    return render_template("login.html", title="Admin Login", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('main.index'))


# -------------------------------------------------------
# ADMIN ROUTES
# -------------------------------------------------------

@bp.route("/admin")
@admin_required
def admin_home():
    total_subs   = Submission.query.filter_by(is_deleted=False).count()
    deleted_subs = Submission.query.filter(Submission.is_deleted == True).count()
    return render_template(
        "admin_home.html", title="Admin Dashboard",
        total_subs=total_subs, deleted_subs=deleted_subs,
    )


@bp.route("/admin/submissions")
@admin_required
def admin_submissions():
    submissions = (
        Submission.query
        .filter_by(is_deleted=False)
        .order_by(Submission.submitted_at.desc())
        .all()
    )
    return render_template(
        "admin_submissions.html", title="All Submissions",
        submissions=submissions,
    )


@bp.route("/admin/submissions/delete/<int:sub_id>", methods=["POST"])
@admin_required
def delete_submission(sub_id):
    sub = Submission.query.get_or_404(sub_id)
    from datetime import datetime
    sub.is_deleted    = True
    sub.deleted_at    = datetime.utcnow()
    sub.deleted_by    = session.get('user', 'admin')
    sub.delete_reason = request.form.get("reason", "").strip() or "Deleted by admin"
    db.session.commit()
    return redirect(url_for("main.admin_submissions"))


@bp.route("/admin/submissions/deleted")
@admin_required
def admin_deleted():
    submissions = (
        Submission.query
        .filter_by(is_deleted=True)
        .order_by(Submission.deleted_at.desc())
        .all()
    )
    return render_template(
        "admin_deleted.html", title="Deleted Submissions",
        submissions=submissions,
    )


@bp.route("/admin/submissions/restore/<int:sub_id>", methods=["POST"])
@admin_required
def restore_submission(sub_id):
    sub = Submission.query.get_or_404(sub_id)
    sub.is_deleted    = False
    sub.deleted_at    = None
    sub.deleted_by    = None
    sub.delete_reason = None
    db.session.commit()
    return redirect(url_for("main.admin_deleted"))


@bp.route("/admin/scoring")
@admin_required
def scoring_overview():
    subs = Submission.query.filter_by(is_deleted=False).all()
    by_operator = defaultdict(list)
    for sub in subs:
        if sub.submitted_by:
            by_operator[sub.submitted_by.upper()].append(sub)

    results = []
    for operator, op_subs in by_operator.items():
        scored  = score_submissions_for_operator(op_subs, operator_name=operator)
        summary = scored["by_operator"]
        results.append({
            "operator":         operator,
            "total_score":      summary["total_score"],
            "total_contacts":   summary["total_contacts"],
            "voice_contacts":   summary["voice_contacts"],
            "voice_score":      summary["voice_score"],
            "pota_contacts":    summary["pota_contacts"],
            "digital_contacts": summary["digital_contacts"],
            "digital_score":    summary["digital_score"],
            "days":             summary["days"],
            "daily":            scored["daily"],
        })

    results.sort(key=lambda r: r["total_score"], reverse=True)
    return render_template("scoring_overview.html", title="Scoring Overview", operators=results)


@bp.route("/admin/scoring/multiplier/<operator>/<date_str>", methods=["GET", "POST"])
@admin_required
def set_multiplier(operator, date_str):
    from datetime import datetime
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format", 400

    if request.method == "POST":
        if request.form.get("delete"):
            sm = ScoreMultiplier.query.filter_by(operator=operator, date=date_obj).first()
            if sm:
                db.session.delete(sm)
                db.session.commit()
            return redirect(url_for("main.scoring_overview"))

        multiplier = float(request.form.get("multiplier", 1.0))
        reason     = request.form.get("reason", "").strip()
        sm = ScoreMultiplier.query.filter_by(operator=operator, date=date_obj).first()
        if not sm:
            sm = ScoreMultiplier(operator=operator, date=date_obj)
            db.session.add(sm)
        sm.multiplier = multiplier
        sm.reason     = reason
        db.session.commit()
        return redirect(url_for("main.scoring_overview"))

    sm = ScoreMultiplier.query.filter_by(operator=operator, date=date_obj).first()
    return render_template(
        "set_multiplier.html", title="Set Bonus Multiplier",
        operator=operator, date=date_str,
        current_multiplier=sm.multiplier if sm else 1.0,
        current_reason=sm.reason if sm else "",
    )


@bp.route("/admin/reset", methods=["GET", "POST"])
@admin_required
def master_reset():
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "").strip()
        if confirmation.upper() != "DELETE EVERYTHING":
            return render_template(
                "admin_reset.html", title="Master Reset",
                error="You must type 'DELETE EVERYTHING' to confirm."
            )
        try:
            db.session.query(Submission).delete()
            db.session.query(ScoreMultiplier).delete()
            db.session.commit()
            return render_template(
                "admin_reset.html", title="Master Reset",
                success="All submissions and scores have been deleted."
            )
        except Exception as e:
            return render_template(
                "admin_reset.html", title="Master Reset",
                error=f"Error during reset: {e}"
            )
    return render_template("admin_reset.html", title="Master Reset")