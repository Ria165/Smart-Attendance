from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from flask import current_app
from app import db
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.verification import VerificationEvent, FaceTemplate
from app.qr.validator import validate_qr_token
from app.location.verifier import verify_student_location
from app.face.detector import detect_face
from app.face.recognizer import extract_face_embedding, compare_embeddings
from app.face.liveness import evaluate_liveness

def process_attendance_submission(student, qr_token, latitude, longitude, accuracy_meters, face_image_data, client_ip=None):
    """
    Executes the multi-stage verification pipeline for a student attendance submission:
    1. QR Token validation & class enrollment check
    2. GPS Location verification & Haversine distance
    3. Face detection, embedding generation & matching against enrolled template
    4. Database transaction to record attendance and prevent duplicate submission
    
    Returns:
        dict with keys: {
            "status": "SUCCESS" | "FAILED",
            "outcome": final_status_code,
            "message": user_readable_explanation,
            "session_id": int or None,
            "subject_name": str or None,
            "classroom": str or None,
            "distance_meters": float or None,
            "face_similarity": float or None,
            "details": dict
        }
    """
    if not student.user.is_approved:
        return {
            "status": "FAILED",
            "outcome": "UNAUTHORIZED",
            "message": "Your account is not approved by faculty."
        }

    # --- STAGE 1: QR CODE VALIDATION ---
    qr_valid, qr_outcome, session_obj, qr_msg = validate_qr_token(qr_token, student, client_ip)
    if not qr_valid:
        return {
            "status": "FAILED",
            "outcome": qr_outcome,
            "message": qr_msg,
            "session_id": session_obj.id if session_obj else None
        }

    # --- STAGE 2: GPS LOCATION VERIFICATION ---
    loc_passed, loc_outcome, distance, loc_msg = verify_student_location(
        student, session_obj, latitude, longitude, accuracy_meters, client_ip
    )
    if not loc_passed:
        return {
            "status": "FAILED",
            "outcome": loc_outcome,
            "message": loc_msg,
            "distance_meters": distance,
            "session_id": session_obj.id
        }

    # --- STAGE 3: FACE VERIFICATION ---
    # Check if student has enrolled their face
    face_template = FaceTemplate.query.filter_by(student_id=student.id).first()
    if not face_template:
        return {
            "status": "FAILED",
            "outcome": "FACE_NOT_ENROLLED",
            "message": "You must enroll your face profile before marking attendance.",
            "session_id": session_obj.id
        }

    # Detect face in submitted image
    detected, face_crop, det_err = detect_face(face_image_data)
    if not detected:
        event = VerificationEvent(
            student_id=student.id,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="INCONCLUSIVE_FACE",
            details=f"Face detection failure: {det_err}",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return {
            "status": "FAILED",
            "outcome": "FACE_REVIEW_REQUIRED",
            "message": det_err or "No face detected in submitted frame. Please align your face.",
            "session_id": session_obj.id
        }

    # Liveness heuristic evaluation
    is_live, liveness_score, liveness_msg = evaluate_liveness(face_crop)

    # Extract 128-d normalized embedding
    current_embedding = extract_face_embedding(face_crop)
    stored_embedding = face_template.get_embedding()

    similarity_threshold = current_app.config.get("FACE_SIMILARITY_THRESHOLD", 0.65)
    match_outcome, similarity, match_details = compare_embeddings(
        current_embedding, stored_embedding, threshold=similarity_threshold
    )

    if match_outcome == "MISMATCH":
        event = VerificationEvent(
            student_id=student.id,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="FACE_MISMATCH",
            details=f"Similarity: {similarity:.2f} (Threshold: {similarity_threshold:.2f})",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return {
            "status": "FAILED",
            "outcome": "FACE_MISMATCH",
            "message": "Face verification mismatch. Attempt logged for faculty review.",
            "face_similarity": round(similarity, 3),
            "session_id": session_obj.id
        }

    elif match_outcome == "INCONCLUSIVE" or not is_live:
        event = VerificationEvent(
            student_id=student.id,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="INCONCLUSIVE_FACE",
            details=f"Inconclusive sample: {match_details}. Liveness: {liveness_msg}",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return {
            "status": "FAILED",
            "outcome": "FACE_REVIEW_REQUIRED",
            "message": "Face sample was inconclusive or low quality. Please retry with better lighting.",
            "face_similarity": round(similarity, 3),
            "session_id": session_obj.id
        }

    # --- STAGE 4: ALL CHECKS PASSED -> PERSIST ATTENDANCE RECORD ---
    try:
        now = datetime.now(timezone.utc)
        record = AttendanceRecord(
            student_id=student.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            session_id=session_obj.id,
            classroom_id=session_obj.classroom_id,
            attendance_date=now.date(),
            marked_timestamp=now,
            qr_verification_result="PASSED",
            location_verification_result="PASSED",
            face_verification_result="PASSED",
            final_status="PRESENT"
        )
        db.session.add(record)
        db.session.commit()

        return {
            "status": "SUCCESS",
            "outcome": "PRESENT",
            "message": "Attendance marked successfully! All verifications passed.",
            "session_id": session_obj.id,
            "subject_name": session_obj.subject.subject_name,
            "classroom": session_obj.classroom.classroom_name,
            "distance_meters": distance,
            "face_similarity": round(similarity, 3),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC")
        }

    except IntegrityError:
        db.session.rollback()
        return {
            "status": "FAILED",
            "outcome": "ALREADY_MARKED",
            "message": "Attendance has already been marked for this session.",
            "session_id": session_obj.id
        }
    except Exception as e:
        db.session.rollback()
        return {
            "status": "FAILED",
            "outcome": "ERROR",
            "message": f"Server error while marking attendance: {str(e)}",
            "session_id": session_obj.id
        }
