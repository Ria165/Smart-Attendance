from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from app import db
from app.models.user import Student, StaffProfile
from app.models.attendance import AttendanceRecord, AttendanceCorrection, AttendanceSession
from app.auth.utils import student_required, staff_required, log_audit, get_current_user
from app.attendance.services import process_attendance_submission
from app.qr.validator import validate_qr_token

attendance_bp = Blueprint("attendance", __name__)

@attendance_bp.route("/validate-qr", methods=["POST"])
@student_required
def validate_qr_endpoint():
    """
    Step 1 Pre-flight check: validates the scanned QR token quickly,
    allowing the client to confirm lecture details before requesting camera & GPS permissions.
    """
    data = request.get_json() or {}
    raw_token = data.get("qr_token", "").strip()

    user = get_current_user()
    student = user.student_profile
    client_ip = request.remote_addr

    is_valid, outcome, session_obj, message = validate_qr_token(raw_token, student, client_ip)

    if not is_valid:
        return jsonify({
            "status": "error",
            "outcome": outcome,
            "message": message
        }), 400

    return jsonify({
        "status": "success",
        "outcome": "VALID_QR",
        "message": "QR validated. Please proceed to location and face verification.",
        "session": {
            "id": session_obj.id,
            "subject_name": session_obj.subject.subject_name,
            "subject_code": session_obj.subject.subject_code,
            "class_name": session_obj.academic_class.name,
            "classroom_name": session_obj.classroom.classroom_name,
            "allowed_radius_meters": session_obj.classroom.allowed_radius_meters
        }
    })


@attendance_bp.route("/submit", methods=["POST"])
@student_required
def submit_attendance():
    """
    Step 2 Full verification submission: executes the complete pipeline:
    QR + GPS Haversine distance + Face verification -> Attendance marking.
    """
    data = request.get_json() or {}
    qr_token = data.get("qr_token")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")
    face_image = data.get("face_image")

    if not qr_token:
        return jsonify({"status": "error", "message": "Missing QR token"}), 400
    if latitude is None or longitude is None:
        return jsonify({"status": "error", "message": "Missing GPS coordinates"}), 400
    if not face_image:
        return jsonify({"status": "error", "message": "Missing face image data"}), 400

    user = get_current_user()
    student = user.student_profile
    client_ip = request.remote_addr

    result = process_attendance_submission(
        student=student,
        qr_token=qr_token,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy,
        face_image_data=face_image,
        client_ip=client_ip
    )

    http_status = 200 if result["status"] == "SUCCESS" else 422
    return jsonify(result), http_status


@attendance_bp.route("/correct/<int:record_id>", methods=["POST"])
@staff_required
def correct_attendance_record(record_id):
    """
    Staff manual correction workflow:
    Modifies an existing attendance record status with an audit trail and required reason.
    """
    data = request.form if request.form else (request.get_json() or {})
    new_status = data.get("new_status")
    reason = data.get("reason", "").strip()

    if new_status not in ("PRESENT", "ABSENT"):
        return jsonify({"status": "error", "message": "New status must be PRESENT or ABSENT"}), 400
    if not reason or len(reason) < 5:
        return jsonify({"status": "error", "message": "A detailed reason (min 5 characters) is required for audit logs."}), 400

    record = db.session.get(AttendanceRecord, record_id)
    if not record:
        return jsonify({"status": "error", "message": "Attendance record not found"}), 404

    user = get_current_user()
    staff = user.staff_profile

    # Verify authorization: staff can only correct records for sessions they own
    session_obj = db.session.get(AttendanceSession, record.session_id)
    if session_obj.staff_id != staff.id:
        return jsonify({"status": "error", "message": "Unauthorized: You can only modify records for your own sessions."}), 403

    previous_status = record.final_status
    record.final_status = new_status

    correction = AttendanceCorrection(
        attendance_record_id=record.id,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
        corrected_by_staff_id=staff.id,
        corrected_at=datetime.now(timezone.utc)
    )
    db.session.add(correction)
    db.session.commit()

    log_audit(
        action="ATTENDANCE_CORRECTION",
        entity_type="attendance_records",
        entity_id=record.id,
        details=f"Status changed from {previous_status} to {new_status}. Reason: {reason}",
        user_id=user.id
    )

    return jsonify({
        "status": "success",
        "message": f"Attendance updated to {new_status}.",
        "record_id": record.id,
        "new_status": new_status
    })
