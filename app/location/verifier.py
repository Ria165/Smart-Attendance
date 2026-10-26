import math
from datetime import datetime, timezone
from flask import current_app
from app import db
from app.models.classroom import Classroom
from app.models.verification import VerificationEvent

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in meters between two points
    on the earth (specified in decimal degrees).
    """
    # Earth radius in meters
    R = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    
    # Numerical stability clamp
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = R * c
    return round(distance, 2)


def verify_student_location(student, session_obj, latitude, longitude, accuracy_meters, client_ip=None):
    """
    Performs server-side Haversine verification against the classroom assigned to the session.
    Returns:
        (passed: bool, status_code: str, calculated_distance: float, message: str)
    """
    classroom = session_obj.classroom
    if not classroom:
        return False, "LOCATION_UNVERIFIED", 0.0, "Classroom location not configured."

    # Validate coordinate ranges
    try:
        lat = float(latitude)
        lon = float(longitude)
        acc = float(accuracy_meters) if accuracy_meters is not None else 999.0
    except (ValueError, TypeError):
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="LOCATION_UNAVAILABLE",
            details="Invalid or unparseable coordinates received from device.",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "LOCATION_UNVERIFIED", 0.0, "Invalid GPS coordinates."

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="LOCATION_UNAVAILABLE",
            details=f"Coordinates out of physical bounds: lat={lat}, lon={lon}",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "LOCATION_UNVERIFIED", 0.0, "GPS coordinates are out of bounds."

    # Check horizontal accuracy threshold
    max_accuracy = current_app.config.get("MAX_GPS_ACCURACY_THRESHOLD_METERS", 80.0)
    if acc > max_accuracy:
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="LOCATION_UNAVAILABLE",
            details=f"GPS accuracy too poor: {acc:.1f}m (limit: {max_accuracy:.1f}m).",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "LOCATION_UNVERIFIED", 0.0, f"GPS accuracy ({acc:.0f}m) is too low. Move near a window or check location services."

    # Server independently computes great circle distance
    dist = haversine_distance(lat, lon, classroom.latitude, classroom.longitude)
    allowed_radius = classroom.allowed_radius_meters or current_app.config.get("DEFAULT_CLASSROOM_RADIUS_METERS", 50.0)

    # Note: we allow a small buffer matching device accuracy if within acceptable bounds
    effective_tolerance = allowed_radius + min(acc * 0.5, 20.0)

    if dist <= effective_tolerance:
        return True, "PASSED", dist, f"Location verified within {dist:.1f}m of classroom (radius: {allowed_radius:.0f}m)."
    else:
        # Distance violation
        event = VerificationEvent(
            student_id=student.id if student else None,
            session_id=session_obj.id,
            subject_id=session_obj.subject_id,
            class_id=session_obj.class_id,
            failure_category="LOCATION_OUT_OF_BOUNDS",
            details=f"Distance {dist:.1f}m exceeds allowed radius {allowed_radius:.0f}m (Accuracy: {acc:.1f}m).",
            client_ip=client_ip
        )
        db.session.add(event)
        db.session.commit()
        return False, "LOCATION_FAILED", dist, f"Location outside classroom boundary ({dist:.0f}m away, allowed: {allowed_radius:.0f}m)."
