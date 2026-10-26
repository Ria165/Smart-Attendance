import unittest
from app import create_app, db
from app.models.classroom import Classroom
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject
from app.models.attendance import AttendanceSession
from app.location.verifier import haversine_distance, verify_student_location

class LocationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed staff, class, subject, classroom, and student
        user_staff = User(full_name="Prof. Geo", email="geo@college.edu", role="staff", is_approved=True)
        user_staff.set_password("Pass123!")
        db.session.add(user_staff)
        db.session.flush()

        staff_prof = StaffProfile(user_id=user_staff.id, staff_id="STAFF_GEO", department="CSE")
        db.session.add(staff_prof)
        db.session.flush()

        self.classroom = Classroom(
            classroom_name="Test Hall",
            building_name="Block A",
            room_number="101",
            latitude=12.971600,
            longitude=77.594600,
            allowed_radius_meters=50.0,
            created_by_staff_id=staff_prof.id
        )
        db.session.add(self.classroom)

        ac_class = Class(department="CSE", year=3, semester=5, section="A", name="CSE-3A")
        db.session.add(ac_class)
        db.session.flush()

        sub = Subject(subject_code="CS101", subject_name="Intro CS", class_id=ac_class.id, staff_id=staff_prof.id)
        db.session.add(sub)
        db.session.flush()

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        self.session_obj = AttendanceSession(
            subject_id=sub.id,
            class_id=ac_class.id,
            classroom_id=self.classroom.id,
            staff_id=staff_prof.id,
            start_time=now,
            end_time=now + timedelta(hours=1),
            is_active=True
        )
        db.session.add(self.session_obj)

        user_stu = User(full_name="Bob Geo", email="bob.geo@college.edu", role="student", is_approved=True)
        user_stu.set_password("Pass123!")
        db.session.add(user_stu)
        db.session.flush()
        self.student = Student(user_id=user_stu.id, student_id="STU_GEO", class_id=ac_class.id)
        db.session.add(self.student)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_haversine_formula(self):
        # Distance from point to itself should be 0
        d0 = haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
        self.assertEqual(d0, 0.0)

        # Distance between Bangalore coordinates (approx 111 meters per 0.001 deg lat)
        d = haversine_distance(12.9716, 77.5946, 12.9726, 77.5946)
        self.assertAlmostEqual(d, 111.19, delta=2.0)

    def test_location_acceptance_within_radius(self):
        # 15 meters offset from classroom
        student_lat = 12.971600 + 0.00010
        student_lon = 77.594600 + 0.00005
        passed, outcome, dist, msg = verify_student_location(
            self.student, self.session_obj, student_lat, student_lon, accuracy_meters=10.0
        )
        self.assertTrue(passed)
        self.assertEqual(outcome, "PASSED")
        self.assertLess(dist, 50.0)

    def test_location_rejection_outside_radius(self):
        # 250 meters away from classroom
        student_lat = 12.971600 + 0.0022
        student_lon = 77.594600 + 0.0010
        passed, outcome, dist, msg = verify_student_location(
            self.student, self.session_obj, student_lat, student_lon, accuracy_meters=10.0
        )
        self.assertFalse(passed)
        self.assertEqual(outcome, "LOCATION_FAILED")
        self.assertGreater(dist, 50.0)

    def test_poor_gps_accuracy_handling(self):
        # Student is at exact coordinates, but GPS reported accuracy is poor (150m > 80m threshold)
        passed, outcome, dist, msg = verify_student_location(
            self.student, self.session_obj, 12.9716, 77.5946, accuracy_meters=150.0
        )
        self.assertFalse(passed)
        self.assertEqual(outcome, "LOCATION_UNVERIFIED")
        self.assertIn("accuracy", msg.lower())

    def test_out_of_bounds_coordinates(self):
        passed, outcome, dist, msg = verify_student_location(
            self.student, self.session_obj, 95.0, 77.5946, accuracy_meters=10.0
        )
        self.assertFalse(passed)
        self.assertEqual(outcome, "LOCATION_UNVERIFIED")

if __name__ == "__main__":
    unittest.main()
