import io
import base64
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from flask import current_app
import qrcode
from app import db
from app.models.attendance import QRToken, AttendanceSession

def generate_session_qr(session_id):
    """
    Generates a cryptographically secure, short-lived QR token for an attendance session.
    Invalidates previous active tokens for this session, saves the new token with SHA256 hash,
    and returns the base64-encoded QR image along with token metadata.
    """
    attendance_session = db.session.get(AttendanceSession, session_id)
    if not attendance_session or not attendance_session.is_active or attendance_session.is_cancelled:
        return None, None, "Session is inactive or closed"

    # Generate cryptographically secure random token (48 bytes URL safe)
    raw_token = f"SAS_{secrets.token_urlsafe(36)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    refresh_interval = attendance_session.refresh_interval_seconds or current_app.config.get("QR_REFRESH_INTERVAL_SECONDS", 30)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=refresh_interval)

    # Deactivate previous active tokens for this session
    QRToken.query.filter_by(session_id=session_id, is_active=True).update({"is_active": False})

    # Create new QR token record
    qr_token = QRToken(
        session_id=session_id,
        token_value=raw_token,
        token_hash=token_hash,
        expires_at=expires_at,
        is_active=True
    )
    db.session.add(qr_token)
    db.session.commit()

    # Generate QR Code image as base64 string
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    # The QR payload contains only the unpredictable short-lived token and session ID
    qr_payload = raw_token
    qr.add_data(qr_payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0F2027", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    data_uri = f"data:image/png;base64,{img_b64}"

    metadata = {
        "session_id": session_id,
        "token_hash": token_hash,
        "expires_at": expires_at.isoformat(),
        "remaining_seconds": refresh_interval,
        "refresh_interval": refresh_interval,
    }

    return data_uri, metadata, None
