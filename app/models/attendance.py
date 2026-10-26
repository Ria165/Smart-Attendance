from datetime import datetime, timezone
from app import db

class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_cancelled = db.Column(db.Boolean, default=False, nullable=False)
    refresh_interval_seconds = db.Column(db.Integer, default=30, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    qr_tokens = db.relationship("QRToken", backref="session", cascade="all, delete-orphan", lazy="dynamic")
    attendance_records = db.relationship("AttendanceRecord", backref="session", cascade="all, delete-orphan", lazy="dynamic")
    verification_events = db.relationship("VerificationEvent", backref="session", lazy="dynamic")

    def __repr__(self):
        return f"<AttendanceSession {self.id} (Subject: {self.subject_id})>"


class QRToken(db.Model):
    __tablename__ = "qr_tokens"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    token_value = db.Column(db.String(128), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def is_expired(self):
        now = datetime.now(timezone.utc)
        # Note: timezone handling
        if self.expires_at.tzinfo is None:
            return datetime.utcnow() > self.expires_at
        return now > self.expires_at

    def __repr__(self):
        return f"<QRToken for Session {self.session_id}>"


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False, index=True)
    marked_timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Verification details
    qr_verification_result = db.Column(db.String(30), default="NOT_CHECKED", nullable=False)
    location_verification_result = db.Column(db.String(30), default="NOT_CHECKED", nullable=False)
    face_verification_result = db.Column(db.String(30), default="NOT_CHECKED", nullable=False)
    
    # Final Status: PRESENT, ABSENT, REJECTED_QR, LOCATION_FAILED, LOCATION_UNVERIFIED, FACE_MISMATCH, FACE_REVIEW_REQUIRED, etc.
    final_status = db.Column(db.String(40), default="PRESENT", nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint("student_id", "session_id", name="uq_student_session_attendance"),
    )

    # Corrections
    corrections = db.relationship("AttendanceCorrection", backref="record", cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self):
        return f"<AttendanceRecord Student:{self.student_id} Session:{self.session_id} Status:{self.final_status}>"


class AttendanceCorrection(db.Model):
    __tablename__ = "attendance_corrections"

    id = db.Column(db.Integer, primary_key=True)
    attendance_record_id = db.Column(db.Integer, db.ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False)
    previous_status = db.Column(db.String(40), nullable=False)
    new_status = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    corrected_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id"), nullable=False)
    corrected_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    staff_member = db.relationship("StaffProfile", foreign_keys=[corrected_by_staff_id])

    def __repr__(self):
        return f"<AttendanceCorrection Record:{self.attendance_record_id} {self.previous_status}->{self.new_status}>"
