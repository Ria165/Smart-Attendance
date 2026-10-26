from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from app import db
from app.models.user import Student, User
from app.models.academic import Class, Subject, Enrollment
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.verification import FaceTemplate, AuditLog
from app.auth.utils import student_required, get_current_user, log_audit
from app.face.detector import detect_face
from app.face.recognizer import extract_face_embedding
from app.reports.generator import calculate_student_statistics

student_bp = Blueprint("student", __name__)

@student_bp.route("/dashboard")
@student_required
def dashboard():
    user = get_current_user()
    student = user.student_profile

    # Fetch enrolled class and subjects
    student_class = student.assigned_class
    subjects = Subject.query.filter_by(class_id=student.class_id).all() if student.class_id else []

    # Calculate current month attendance statistics
    now = datetime.now(timezone.utc)
    current_year = now.year
    current_month = now.month

    subject_stats = []
    total_eligible_all = 0
    total_present_all = 0

    for sub in subjects:
        stats = calculate_student_statistics(student.id, sub.id, current_year, current_month)
        subject_stats.append(stats)
        if stats["sessions_held"] > 0:
            total_eligible_all += stats["sessions_held"]
            total_present_all += stats["present_count"]

    overall_percentage = round((total_present_all / total_eligible_all) * 100.0, 1) if total_eligible_all > 0 else None
    low_attendance_threshold = current_app.config.get("LOW_ATTENDANCE_THRESHOLD_PERCENT", 75.0)

    # Recent personal records
    recent_records = AttendanceRecord.query.filter_by(
        student_id=student.id
    ).order_by(AttendanceRecord.marked_timestamp.desc()).limit(8).all()

    return render_template(
        "student/dashboard.html",
        student=student,
        user=user,
        student_class=student_class,
        subject_stats=subject_stats,
        overall_percentage=overall_percentage,
        low_threshold=low_attendance_threshold,
        recent_records=recent_records
    )


@student_bp.route("/scan")
@student_required
def scan_page():
    user = get_current_user()
    student = user.student_profile
    return render_template("student/scan.html", student=student)


@student_bp.route("/face-enroll", methods=["GET"])
@student_required
def face_enroll_page():
    user = get_current_user()
    student = user.student_profile
    existing_template = FaceTemplate.query.filter_by(student_id=student.id).first()
    return render_template("student/face_enroll.html", student=student, template=existing_template)


@student_bp.route("/api/enroll-face", methods=["POST"])
@student_required
def enroll_face_api():
    """
    Captures and stores the student's 128-d normalized facial biometric embedding.
    Never exposes raw biometric vectors to client or unauthorized users.
    """
    user = get_current_user()
    student = user.student_profile
    data = request.get_json() or {}
    image_b64 = data.get("face_image")

    if not image_b64:
        return jsonify({"status": "error", "message": "No face image received."}), 400

    # Detect face
    found, face_crop, err_msg = detect_face(image_b64)
    if not found:
        return jsonify({"status": "error", "message": err_msg or "Face detection failed. Ensure good lighting."}), 400

    # Extract embedding
    embedding = extract_face_embedding(face_crop)
    if not embedding:
        return jsonify({"status": "error", "message": "Could not extract facial features. Try again."}), 400

    now = datetime.now(timezone.utc)
    template = FaceTemplate.query.filter_by(student_id=student.id).first()
    if not template:
        template = FaceTemplate(
            student_id=student.id,
            model_name="sface_spatial_v1",
            vector_dimension=len(embedding)
        )
        db.session.add(template)

    template.set_embedding(embedding)
    template.updated_at = now
    student.face_enrolled = True
    student.face_enrolled_at = now
    db.session.commit()

    log_audit("FACE_ENROLLED", "students", student.id, f"Face enrolled for {student.student_id}", user.id)

    return jsonify({
        "status": "success",
        "message": "Face profile successfully enrolled! You can now participate in attendance verification."
    })


@student_bp.route("/history")
@student_required
def history():
    user = get_current_user()
    student = user.student_profile

    records = AttendanceRecord.query.filter_by(
        student_id=student.id
    ).order_by(AttendanceRecord.marked_timestamp.desc()).all()

    return render_template("student/history.html", records=records, student=student)
