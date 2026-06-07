from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, current_app as app, jsonify
)
from collections import defaultdict
from .client_auth import admin_required
from . import db
from .models import Submission, ScoreMultiplier, User
from .scoring import score_submissions_for_operator
from .adi_parser import parse_adi_file, ADIFRecord


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


@bp.route("/submit/adi_preview", methods=["POST"])
def adi_preview():
    """Parse uploaded ADI file and return JSON preview for the client."""
    f = request.files.get("adi_file")
    if not f or not f.filename:
        return jsonify({"success": False, "errors": ["No file provided."]}), 400

    try:
        content = f.read().decode("utf-8", errors="replace").upper()
    except Exception as e:
        return jsonify({"success": False, "errors": [f"Could not read file: {e}"]}), 400

    result = parse_adi_file(content)

    # Apply user-declared POTA flag to records that have a POTA park field
    is_pota_flag = request.form.get("adi_is_pota", "no") == "yes"
    if is_pota_flag:
        for r in result.records:
            if r.pota_park:
                r.is_pota = True

    # Build preview payload — only include up to 20 records for the table
    has_digital = any(r.digital_mode for r in result.records)
    has_pota = any(r.is_pota for r in result.records)

    return jsonify({
        "success":       result.success,
        "count":         len(result.records),
        "errors":        result.errors,
        "warnings":      result.warnings,
        "records": [
            {
                "my_call":      r.submitted_by or "",
                "call":         r.contact_call or "",
                "qso_date":     r.qso_date or "",
                "time_on":      r.time_on or "",
                "mode_type":    r.mode_type or "",
                "is_pota":      r.is_pota,
                "pota_park":    r.pota_park or "",
                "digital_mode": r.digital_mode or "",
                "freq":         str(r.frequency) if r.frequency else "",
                "notes":        r.notes or "",
            }
            for r in result.records[:20]
        ],
        "has_digital": has_digital,
        "has_pota":    has_pota,
    }), 200


@bp.route("/submit/adi_batch", methods=["POST"])
def adi_batch():
    """Accept parsed ADI records (from the preview step) and batch-create submissions."""
    # Build list of dicts from the hidden inputs
    contacts = []
    i = 0
    while True:
        # Check if this record key exists before processing
        if f"adi_records[{i}][call]" not in request.form:
            break

        my_call = request.form.get(f"adi_records[{i}][my_call]", "").strip().upper()
        call    = request.form.get(f"adi_records[{i}][call]", "").strip().upper()
        qso_date= request.form.get(f"adi_records[{i}][qso_date]", "").strip()
        time_on = request.form.get(f"adi_records[{i}][time_on]", "").strip()
        mode    = request.form.get(f"adi_records[{i}][mode_type]", "voice").strip()
        is_pota = request.form.get(f"adi_records[{i}][is_pota]") == "yes"
        pota_park = request.form.get(f"adi_records[{i}][pota_park]", "").strip().upper() if is_pota else None
        digital_mode = request.form.get(f"adi_records[{i}][digital_mode]", "").strip() or None
        frequency_str = request.form.get(f"adi_records[{i}][frequency]", "").strip()
        notes     = request.form.get(f"adi_records[{i}][notes]", "").strip()

        if not call:
            i += 1
            continue

        freq_val = None
        if frequency_str:
            try:
                freq_val = float(frequency_str)
            except ValueError:
                pass

        contacts.append({
            "submitted_by": my_call or call,
            "contact_call": call,
            "qso_date":     qso_date,
            "time_on":      time_on,
            "mode_type":    mode if mode in ("voice", "digital") else "voice",
            "is_pota":      is_pota,
            "pota_park":    pota_park,
            "digital_mode": digital_mode,
            "frequency":    freq_val,
            "notes":        notes,
        })

        i += 1
        if f"adi_records[{i}][call]" not in request.form:
            break

    if not contacts:
        return render_template(
            "submit.html", title="Submit ADI Contacts",
            errors=["No contact records received from the file parser."],
            form={},
        )

    errors = []
    created = 0
    for c in contacts:
        errs = []
        if not c["contact_call"]:
            errs.append("Missing callsign.")
        if c["mode_type"] == "digital" and not c["digital_mode"]:
            errs.append(f"{c['contact_call']}: Digital contact requires a digital mode.")
        if c["is_pota"] and not c["pota_park"]:
            errs.append(f"{c['contact_call']}: POTA contact requires a park reference.")

        if errs:
            errors.extend(errs)
            continue

        sub = Submission(
            submitted_by   = c["submitted_by"],
            contact_call   = c["contact_call"],
            mode_type      = c["mode_type"],
            is_pota        = c["is_pota"],
            pota_park      = c["pota_park"],
            digital_mode   = c["digital_mode"],
            frequency      = c["frequency"],
            notes          = c["notes"],
        )
        db.session.add(sub)
        created += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        errors.append(f"Database error: {e}")

    if errors and created == 0:
        return render_template(
            "submit.html", title="Submit ADI Contacts",
            errors=errors, form={},
        )

    msg = f"{created} contact(s) from the ADI file submitted successfully."
    if errors:
        msg += f" {len(errors)} record(s) were skipped due to validation errors."

    return render_template(
        "submit.html", title="Submit ADI Contacts",
        success=msg, form={},
    )


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