import json
from datetime import datetime, timezone
from app import db

class FaceTemplate(db.Model):
    __tablename__ = "face_templates"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding_json = db.Column(db.Text, nullable=False)  # JSON-serialized normalized vector
    model_name = db.Column(db.String(100), default="sface_yunet_v1", nullable=False)
    vector_dimension = db.Column(db.Integer, default=128, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def set_embedding(self, vector):
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        self.embedding_json = json.dumps(vector)

    def get_embedding(self):
        return json.loads(self.embedding_json)

    def __repr__(self):
        return f"<FaceTemplate Student:{self.student_id}>"


class VerificationEvent(db.Model):
    __tablename__ = "verification_events"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=True, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    
    # Categories: INVALID_QR, EXPIRED_QR, FACE_MISMATCH, INCONCLUSIVE_FACE, LOCATION_OUT_OF_BOUNDS, LOCATION_UNAVAILABLE, UNAUTHORIZED_CLASS, SUSPICIOUS_REPEATED
    failure_category = db.Column(db.String(50), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    client_ip = db.Column(db.String(64), nullable=True)
    recorded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    is_reviewed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    reviewed_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    reviewer = db.relationship("StaffProfile", foreign_keys=[reviewed_by_staff_id])

    def __repr__(self):
        return f"<VerificationEvent {self.failure_category} Student:{self.student_id}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog {self.action} User:{self.user_id} ({self.timestamp})>"
