from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session as login_session
from app import db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject, Enrollment
from app.models.classroom import Classroom
from app.models.attendance import AttendanceSession, AttendanceRecord, QRToken
from app.models.verification import VerificationEvent, AuditLog
from app.auth.utils import staff_required, get_current_user, log_audit
from app.qr.generator import generate_session_qr

staff_bp = Blueprint("staff", __name__)

@staff_bp.route("/dashboard")
@staff_required
def dashboard():
    user = get_current_user()
    staff = user.staff_profile

    # Total sessions conducted by this staff member
    total_sessions = AttendanceSession.query.filter_by(staff_id=staff.id).count()

    # Staff's assigned subjects
    subjects = Subject.query.filter_by(staff_id=staff.id).all()
    subject_ids = [s.id for s in subjects]
    class_ids = list({s.class_id for s in subjects})

    # Total students across assigned classes
    total_students = Enrollment.query.filter(Enrollment.class_id.in_(class_ids)).count() if class_ids else 0

    # Total present records across assigned subjects
    total_present = AttendanceRecord.query.filter(
        AttendanceRecord.subject_id.in_(subject_ids),
        AttendanceRecord.final_status == "PRESENT"
    ).count() if subject_ids else 0

    # Today's sessions
    today = datetime.now(timezone.utc).date()
    today_sessions = AttendanceSession.query.filter(
        AttendanceSession.staff_id == staff.id,
        db.func.date(AttendanceSession.start_time) == today
    ).all()
    today_session_ids = [s.id for s in today_sessions]

    today_present = AttendanceRecord.query.filter(
        AttendanceRecord.session_id.in_(today_session_ids),
        AttendanceRecord.final_status == "PRESENT"
    ).count() if today_session_ids else 0

    # Unreviewed alerts for this staff member's subjects/classes
    recent_alerts = VerificationEvent.query.filter(
        VerificationEvent.class_id.in_(class_ids) if class_ids else False,
        VerificationEvent.is_reviewed == False
    ).order_by(VerificationEvent.recorded_at.desc()).limit(8).all() if class_ids else []

    # Recent attendance records
    recent_records = AttendanceRecord.query.filter(
        AttendanceRecord.subject_id.in_(subject_ids)
    ).order_by(AttendanceRecord.marked_timestamp.desc()).limit(10).all() if subject_ids else []

    # Pending approvals count (only users awaiting review: role student or staff, not approved and not rejected)
    pending_approvals_count = User.query.filter(
        User.role.in_(["student", "staff"]),
        User.is_approved == False,
        User.is_rejected == False
    ).count()

    # Active running sessions
    active_sessions = AttendanceSession.query.filter_by(staff_id=staff.id, is_active=True).all()

    return render_template(
        "staff/dashboard.html",
        staff=staff,
        total_sessions=total_sessions,
        total_students=total_students,
        total_present=total_present,
        today_sessions_count=len(today_sessions),
        today_present=today_present,
        recent_alerts=recent_alerts,
        recent_records=recent_records,
        pending_students_count=pending_approvals_count,
        pending_approvals_count=pending_approvals_count,
        active_sessions=active_sessions
    )


# --- CLASSROOM LOCATIONS ---

@staff_bp.route("/classrooms", methods=["GET", "POST"])
@staff_required
def classrooms():
    user = get_current_user()
    staff = user.staff_profile

    if request.method == "POST":
        classroom_name = request.form.get("classroom_name", "").strip()
        building_name = request.form.get("building_name", "").strip()
        room_number = request.form.get("room_number", "").strip()
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        allowed_radius = request.form.get("allowed_radius_meters", "50")

        if not classroom_name or not building_name or not room_number or not latitude or not longitude:
            flash("All classroom fields and coordinates are required.", "danger")
            return redirect(url_for("staff.classrooms"))

        try:
            lat = float(latitude)
            lon = float(longitude)
            radius = float(allowed_radius)
        except ValueError:
            flash("Latitude, longitude, and radius must be valid numbers.", "danger")
            return redirect(url_for("staff.classrooms"))

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            flash("Coordinates are out of physical bounds.", "danger")
            return redirect(url_for("staff.classrooms"))

        classroom = Classroom(
            classroom_name=classroom_name,
            building_name=building_name,
            room_number=room_number,
            latitude=lat,
            longitude=lon,
            allowed_radius_meters=max(10.0, radius),
            created_by_staff_id=staff.id
        )
        db.session.add(classroom)
        db.session.commit()

        log_audit("CLASSROOM_CREATED", "classrooms", classroom.id, f"Created classroom {classroom_name}", user.id)
        flash(f"Classroom '{classroom_name}' registered successfully!", "success")
        return redirect(url_for("staff.classrooms"))

    saved_classrooms = Classroom.query.filter_by(created_by_staff_id=staff.id).order_by(Classroom.created_at.desc()).all()
    return render_template("staff/classrooms.html", classrooms=saved_classrooms)


# --- SUBJECTS AND CLASSES ---

@staff_bp.route("/subjects", methods=["GET", "POST"])
@staff_required
def subjects():
    user = get_current_user()
    staff = user.staff_profile
    classes = Class.query.order_by(Class.name).all()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_subject":
            code = request.form.get("subject_code", "").strip().upper()
            name = request.form.get("subject_name", "").strip()
            class_id = request.form.get("class_id")

            if not code or not name or not class_id:
                flash("Subject code, name, and class assignment are required.", "danger")
                return redirect(url_for("staff.subjects"))

            existing = Subject.query.filter_by(subject_code=code, class_id=class_id, staff_id=staff.id).first()
            if existing:
                flash("You have already configured this subject for the selected class.", "warning")
                return redirect(url_for("staff.subjects"))

            sub = Subject(
                subject_code=code,
                subject_name=name,
                class_id=class_id,
                staff_id=staff.id
            )
            db.session.add(sub)
            db.session.commit()
            flash(f"Subject {code} - {name} created successfully!", "success")

        elif action == "create_class":
            dept = request.form.get("department", "").strip().upper()
            year = int(request.form.get("year", 1))
            semester = int(request.form.get("semester", 1))
            section = request.form.get("section", "A").strip().upper()
            class_name = f"{dept}-Y{year}S{semester}-{section}"

            existing = Class.query.filter_by(name=class_name).first()
            if existing:
                flash(f"Class {class_name} already exists.", "warning")
            else:
                new_class = Class(
                    department=dept,
                    year=year,
                    semester=semester,
                    section=section,
                    name=class_name
                )
                db.session.add(new_class)
                db.session.commit()
                flash(f"Class {class_name} registered successfully!", "success")

        return redirect(url_for("staff.subjects"))

    staff_subjects = Subject.query.filter_by(staff_id=staff.id).order_by(Subject.subject_code).all()
    return render_template("staff/subjects.html", subjects=staff_subjects, classes=classes)


# --- SESSIONS & DYNAMIC QR CODES ---

@staff_bp.route("/sessions")
@staff_required
def sessions():
    user = get_current_user()
    staff = user.staff_profile

    staff_sessions = AttendanceSession.query.filter_by(
        staff_id=staff.id
    ).order_by(AttendanceSession.start_time.desc()).all()

    return render_template(
        "staff/sessions.html",
        sessions=staff_sessions
    )


@staff_bp.route("/sessions/create", methods=["GET", "POST"])
@staff_required
def create_session():
    user = get_current_user()
    staff = user.staff_profile
    subjects = Subject.query.filter_by(staff_id=staff.id).all()
    classrooms = Classroom.query.filter_by(created_by_staff_id=staff.id).all()

    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        classroom_id = request.form.get("classroom_id")
        refresh_interval = int(request.form.get("refresh_interval_seconds", 30))
        duration_minutes = int(request.form.get("duration_minutes", 60))

        if not subject_id or not classroom_id:
            flash("Please select both a subject and classroom.", "danger")
            return render_template("staff/create_session.html", subjects=subjects, classrooms=classrooms)

        subject = db.session.get(Subject, subject_id)
        classroom = db.session.get(Classroom, classroom_id)

        if not subject or subject.staff_id != staff.id:
            flash("Unauthorized subject selection.", "danger")
            return redirect(url_for("staff.create_session"))

        now = datetime.now(timezone.utc)
        end_time = now + timedelta(minutes=duration_minutes)

        session_obj = AttendanceSession(
            subject_id=subject.id,
            class_id=subject.class_id,
            classroom_id=classroom.id,
            staff_id=staff.id,
            start_time=now,
            end_time=end_time,
            refresh_interval_seconds=refresh_interval,
            is_active=True
        )
        db.session.add(session_obj)
        db.session.commit()

        log_audit("SESSION_CREATED", "attendance_sessions", session_obj.id, f"Session created for {subject.subject_code}", user.id)
        flash("Attendance session started! Present the dynamic QR code to students.", "success")
        return redirect(url_for("staff.live_session", session_id=session_obj.id))

    return render_template("staff/create_session.html", subjects=subjects, classrooms=classrooms)


@staff_bp.route("/sessions/<int:session_id>/live")
@staff_required
def live_session(session_id):
    user = get_current_user()
    staff = user.staff_profile
    session_obj = db.session.get(AttendanceSession, session_id)

    if not session_obj or session_obj.staff_id != staff.id:
        flash("Attendance session not found or unauthorized.", "danger")
        return redirect(url_for("staff.dashboard"))

    # Generate initial QR code
    qr_b64, metadata, err = generate_session_qr(session_id)

    total_enrolled = Enrollment.query.filter_by(class_id=session_obj.class_id).count()
    present_count = AttendanceRecord.query.filter_by(session_id=session_id, final_status="PRESENT").count()

    return render_template(
        "staff/session_live.html",
        attendance_session=session_obj,
        session_obj=session_obj,
        qr_image=qr_b64,
        metadata=metadata,
        total_enrolled=total_enrolled,
        present_count=present_count
    )


@staff_bp.route("/sessions/<int:session_id>/qr-poll")
@staff_required
def session_qr_poll(session_id):
    """
    AJAX endpoint called periodically by the live session dashboard
    to get the fresh dynamic QR code and present student counter.
    """
    user = get_current_user()
    staff = user.staff_profile
    session_obj = db.session.get(AttendanceSession, session_id)

    if not session_obj or session_obj.staff_id != staff.id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    if not session_obj.is_active or session_obj.is_cancelled:
        return jsonify({"status": "closed", "message": "Session is closed."})

    qr_b64, metadata, err = generate_session_qr(session_id)
    present_count = AttendanceRecord.query.filter_by(session_id=session_id, final_status="PRESENT").count()
    total_enrolled = Enrollment.query.filter_by(class_id=session_obj.class_id).count()

    recent_students = AttendanceRecord.query.filter_by(
        session_id=session_id, final_status="PRESENT"
    ).order_by(AttendanceRecord.marked_timestamp.desc()).limit(5).all()

    student_list = [{
        "student_id": r.student.student_id,
        "name": r.student.user.full_name,
        "time": r.marked_timestamp.strftime("%H:%M:%S")
    } for r in recent_students]

    return jsonify({
        "status": "active",
        "qr_image": qr_b64,
        "metadata": metadata,
        "present_count": present_count,
        "total_enrolled": total_enrolled,
        "recent_students": student_list
    })


@staff_bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@staff_required
def close_session(session_id):
    user = get_current_user()
    staff = user.staff_profile
    session_obj = db.session.get(AttendanceSession, session_id)

    if not session_obj or session_obj.staff_id != staff.id:
        flash("Session not found or unauthorized.", "danger")
        return redirect(url_for("staff.dashboard"))

    session_obj.is_active = False
    # Deactivate all active QR tokens
    QRToken.query.filter_by(session_id=session_id).update({"is_active": False})
    db.session.commit()

    log_audit("SESSION_CLOSED", "attendance_sessions", session_id, f"Session {session_id} manually closed", user.id)
    flash(f"Session {session_id} has been closed. Final records are locked.", "info")
    return redirect(url_for("staff.attendance_records", session_id=session_id))


# --- STUDENT & STAFF APPROVALS ---

@staff_bp.route("/approvals", methods=["GET", "POST"])
@staff_required
def student_approvals():
    user = get_current_user()
    staff = user.staff_profile

    if request.method == "POST":
        target_user_id = request.form.get("user_id")
        action = request.form.get("action")  # 'approve' or 'reject'
        reason = request.form.get("reason", "").strip()

        target_user = db.session.get(User, target_user_id)
        if not target_user:
            flash("Target user not found.", "danger")
            return redirect(url_for("staff.student_approvals"))

        if action == "approve":
            target_user.is_approved = True
            target_user.is_rejected = False
            target_user.approved_by_staff_id = staff.id
            target_user.approved_at = datetime.now(timezone.utc)
            log_audit(f"{target_user.role.upper()}_APPROVED", "users", target_user.id, f"{target_user.role.title()} {target_user.email} approved by Prof. {user.full_name}", user.id)
            flash(f"Account for {target_user.full_name} ({target_user.email}) approved successfully.", "success")
        elif action == "reject":
            target_user.is_approved = False
            target_user.is_rejected = True
            target_user.rejected_at = datetime.now(timezone.utc)
            target_user.rejection_reason = reason or "Registration not approved by department staff."
            log_audit(f"{target_user.role.upper()}_REJECTED", "users", target_user.id, f"{target_user.role.title()} {target_user.email} rejected by Prof. {user.full_name}. Reason: {target_user.rejection_reason}", user.id)
            flash(f"Account for {target_user.full_name} has been rejected.", "info")

        db.session.commit()
        return redirect(url_for("staff.student_approvals"))

    pending_students = User.query.filter_by(role="student", is_approved=False, is_rejected=False).order_by(User.created_at.desc()).all()
    approved_students = User.query.filter_by(role="student", is_approved=True).order_by(User.created_at.desc()).limit(30).all()
    rejected_students = User.query.filter_by(role="student", is_rejected=True).order_by(User.created_at.desc()).limit(20).all()

    pending_staff = User.query.filter_by(role="staff", is_approved=False, is_rejected=False).order_by(User.created_at.desc()).all()
    approved_staff = User.query.filter_by(role="staff", is_approved=True).order_by(User.created_at.desc()).limit(20).all()

    return render_template(
        "staff/approvals.html",
        pending_students=pending_students,
        approved_students=approved_students,
        rejected_students=rejected_students,
        pending_staff=pending_staff,
        approved_staff=approved_staff
    )


# --- ATTENDANCE RECORDS & AUDIT ---

@staff_bp.route("/records")
@staff_required
def attendance_records():
    user = get_current_user()
    staff = user.staff_profile

    subjects = Subject.query.filter_by(staff_id=staff.id).all()
    subject_ids = [s.id for s in subjects]
    classes = Class.query.filter(Class.id.in_([s.class_id for s in subjects])).all() if subjects else []

    # Query params
    selected_subject_id = request.args.get("subject_id", type=int)
    selected_class_id = request.args.get("class_id", type=int)
    selected_status = request.args.get("status", "").strip()
    selected_date = request.args.get("date", "").strip()
    search_query = request.args.get("search", "").strip()
    session_id_filter = request.args.get("session_id", type=int)

    query = AttendanceRecord.query.filter(AttendanceRecord.subject_id.in_(subject_ids))

    if selected_subject_id and selected_subject_id in subject_ids:
        query = query.filter(AttendanceRecord.subject_id == selected_subject_id)
    if selected_class_id:
        query = query.filter(AttendanceRecord.class_id == selected_class_id)
    if selected_status:
        query = query.filter(AttendanceRecord.final_status == selected_status)
    if selected_date:
        try:
            d = datetime.strptime(selected_date, "%Y-%m-%d").date()
            query = query.filter(AttendanceRecord.attendance_date == d)
        except ValueError:
            pass
    if session_id_filter:
        query = query.filter(AttendanceRecord.session_id == session_id_filter)
    if search_query:
        query = query.join(Student).join(User).filter(
            (Student.student_id.ilike(f"%{search_query}%")) |
            (User.full_name.ilike(f"%{search_query}%"))
        )

    records = query.order_by(AttendanceRecord.marked_timestamp.desc()).limit(150).all()

    return render_template(
        "staff/records.html",
        records=records,
        subjects=subjects,
        classes=classes,
        selected_subject_id=selected_subject_id,
        selected_class_id=selected_class_id,
        selected_status=selected_status,
        selected_date=selected_date,
        search_query=search_query
    )


# --- SUSPICIOUS VERIFICATION ALERTS ---

@staff_bp.route("/alerts")
@staff_required
def alerts():
    user = get_current_user()
    staff = user.staff_profile

    subjects = Subject.query.filter_by(staff_id=staff.id).all()
    class_ids = [s.class_id for s in subjects]

    filter_mode = request.args.get("filter", "unreviewed")
    query = VerificationEvent.query.filter(VerificationEvent.class_id.in_(class_ids)) if class_ids else VerificationEvent.query.filter(False)

    if filter_mode == "unreviewed":
        query = query.filter(VerificationEvent.is_reviewed == False)
    elif filter_mode == "reviewed":
        query = query.filter(VerificationEvent.is_reviewed == True)

    events = query.order_by(VerificationEvent.recorded_at.desc()).limit(100).all()
    return render_template("staff/alerts.html", events=events, filter_mode=filter_mode)


@staff_bp.route("/alerts/<int:event_id>/review", methods=["POST"])
@staff_required
def review_alert(event_id):
    user = get_current_user()
    staff = user.staff_profile
    event = db.session.get(VerificationEvent, event_id)

    if not event:
        flash("Alert event not found.", "danger")
        return redirect(url_for("staff.alerts"))

    event.is_reviewed = True
    event.reviewed_by_staff_id = staff.id
    event.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Alert #{event.id} marked as reviewed.", "success")
    return redirect(url_for("staff.alerts"))
