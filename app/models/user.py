from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'staff' or 'student'
    full_name = db.Column(db.String(100), nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    is_rejected = db.Column(db.Boolean, default=False, nullable=False)
    approved_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id", use_alter=True, name="fk_users_approved_by_staff"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    student_profile = db.relationship("Student", backref="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = db.relationship("StaffProfile", backref="user", uselist=False, cascade="all, delete-orphan", foreign_keys="StaffProfile.user_id")
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic", foreign_keys="AuditLog.user_id")
    approved_by = db.relationship("StaffProfile", foreign_keys=[approved_by_staff_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    student_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    face_enrolled = db.Column(db.Boolean, default=False, nullable=False)
    face_enrolled_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    assigned_class = db.relationship("Class", backref="students", foreign_keys=[class_id])
    enrollments = db.relationship("Enrollment", backref="student", cascade="all, delete-orphan", lazy="dynamic")
    face_template = db.relationship("FaceTemplate", backref="student", uselist=False, cascade="all, delete-orphan")
    attendance_records = db.relationship("AttendanceRecord", backref="student", cascade="all, delete-orphan", lazy="dynamic")
    verification_events = db.relationship("VerificationEvent", backref="student", lazy="dynamic")

    def __repr__(self):
        return f"<Student {self.student_id}>"


class StaffProfile(db.Model):
    __tablename__ = "staff_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    department = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(100), default="Faculty", nullable=False)

    # Relationships
    subjects = db.relationship("Subject", backref="staff", lazy="dynamic")
    created_classrooms = db.relationship("Classroom", backref="created_by", lazy="dynamic")
    conducted_sessions = db.relationship("AttendanceSession", backref="staff", lazy="dynamic")

    def __repr__(self):
        return f"<StaffProfile {self.staff_id}>"
