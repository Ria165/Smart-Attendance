import hashlib
from datetime import datetime, timezone, timedelta
from flask import current_app
from app import db
from app.models.attendance import QRToken, AttendanceSession, AttendanceRecord
from app.models.academic import Enrollment
from app.models.classroom import Classroom
from app.models.verification import VerificationEvent

def validate_qr_token(raw_token, student, client_ip=None):
    """
    Validates a submitted QR token string for an authenticated student.
    Returns:
        (is_valid: bool, status_code: str, session_obj: AttendanceSession, message: str)
    """
    if not raw_token or not raw_token.strip():
        return False, "REJECTED_QR", None, "Missing or empty QR token."

    token_str = raw_token.strip()
    token_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()

    # Find token by value or hash
    qr_token = QRToken.query.filter(
        (QRToken.token_value == token_str) | (QRToken.token_hash == token_hash)
    ).order_by(QRToken.id.desc()).first()

    if not qr_token:
        # Log suspicious alert: invalid token
        event = VerificationEvent(
            student_id=student.id if student else None,
            failure_category="INVALID_QR",
            details="Token not found in database or invalid format.",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "REJECTED_QR", None, "Invalid QR code. Please scan the current code displayed on screen."

    session_obj = db.session.get(AttendanceSession, qr_token.session_id)
    if not session_obj or not session_obj.is_active or session_obj.is_cancelled:
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id if session_obj else None,
            failure_category="EXPIRED_QR",
            details="Attendance session is closed or cancelled.",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "REJECTED_QR", session_obj, "This attendance session is no longer active."

    # Check token expiry with leeway
    leeway = current_app.config.get("QR_TOKEN_VALIDITY_LEEWAY", 10)
    now = datetime.now(timezone.utc)
    token_expiry = qr_token.expires_at
    if token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    if now > (token_expiry + timedelta(seconds=leeway)):
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="EXPIRED_QR",
            details=f"Token expired at {token_expiry.isoformat()}, scan attempted at {now.isoformat()}",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "REJECTED_QR", session_obj, "QR code has expired. Please scan the newly refreshed QR code."

    # Verify student is enrolled in the session's class (align with subject roster)
    if student:
        target_class_id = session_obj.subject.class_id if (session_obj.subject_id and session_obj.subject) else session_obj.class_id
        enrollment = Enrollment.query.filter_by(
            student_id=student.id,
            class_id=target_class_id
        ).first()

        if not enrollment:
            event = VerificationEvent(
                student_id=student.id,
                session_id=session_obj.id,
                subject_id=session_obj.subject_id,
                class_id=target_class_id,
                failure_category="UNAUTHORIZED_CLASS",
                details=f"Student {student.student_id} is not enrolled in Class ID {target_class_id}",
                client_ip=client_ip
            )
            db.session.add(event)
            db.session.commit()
            return False, "SESSION_NOT_ALLOWED", session_obj, "You are not enrolled in the class assigned to this lecture."

        # Verify duplicate attendance
        existing = AttendanceRecord.query.filter_by(
            student_id=student.id,
            session_id=session_obj.id
        ).first()

        if existing and existing.final_status == "PRESENT":
            return False, "ALREADY_MARKED", session_obj, "Attendance has already been marked for this session."

    return True, "PASSED", session_obj, "QR code successfully verified."
