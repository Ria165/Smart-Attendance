from datetime import datetime, timezone
from app import db

class Classroom(db.Model):
    __tablename__ = "classrooms"

    id = db.Column(db.Integer, primary_key=True)
    classroom_name = db.Column(db.String(100), nullable=False)
    building_name = db.Column(db.String(100), nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    allowed_radius_meters = db.Column(db.Float, default=50.0, nullable=False)
    created_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    sessions = db.relationship("AttendanceSession", backref="classroom", lazy="dynamic")
    records = db.relationship("AttendanceRecord", backref="classroom", lazy="dynamic")

    def __repr__(self):
        return f"<Classroom {self.classroom_name} ({self.building_name} - {self.room_number})>"
