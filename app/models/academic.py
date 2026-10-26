from datetime import datetime, timezone
from app import db

class Class(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    department = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)  # 1, 2, 3, 4
    semester = db.Column(db.Integer, nullable=False)  # 1 to 8
    section = db.Column(db.String(10), nullable=False)  # 'A', 'B', 'C'
    name = db.Column(db.String(120), nullable=False, unique=True)  # e.g. "CSE-3A (Sem 5)"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    subjects = db.relationship("Subject", backref="assigned_class", lazy="dynamic")
    enrollments = db.relationship("Enrollment", backref="academic_class", cascade="all, delete-orphan", lazy="dynamic")
    sessions = db.relationship("AttendanceSession", backref="academic_class", lazy="dynamic")

    def __repr__(self):
        return f"<Class {self.name}>"


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    subject_code = db.Column(db.String(30), nullable=False, index=True)
    subject_name = db.Column(db.String(150), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("subject_code", "class_id", "staff_id", name="uq_subject_class_staff"),
    )

    # Relationships
    sessions = db.relationship("AttendanceSession", backref="subject", cascade="all, delete-orphan", lazy="dynamic")
    attendance_records = db.relationship("AttendanceRecord", backref="subject", lazy="dynamic")

    def __repr__(self):
        return f"<Subject {self.subject_code} - {self.subject_name}>"


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("student_id", "class_id", name="uq_student_class_enrollment"),
    )

    def __repr__(self):
        return f"<Enrollment Student:{self.student_id} Class:{self.class_id}>"
