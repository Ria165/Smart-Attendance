import unittest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject, Enrollment
from app.models.classroom import Classroom
from app.models.attendance import AttendanceSession, QRToken, AttendanceRecord
from app.qr.generator import generate_session_qr
from app.qr.validator import validate_qr_token

class QRTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed staff, classroom, classes, subjects
        staff_u = User(full_name="Prof. QR", email="qr@college.edu", role="staff", is_approved=True)
        staff_u.set_password("Pass123!")
        db.session.add(staff_u)
        db.session.flush()

        staff_prof = StaffProfile(user_id=staff_u.id, staff_id="STF_QR", department="CSE")
        db.session.add(staff_prof)
        db.session.flush()

        classroom = Classroom(
            classroom_name="Hall 1",
            building_name="A",
            room_number="1",
            latitude=12.9716,
            longitude=77.5946,
            allowed_radius_meters=50.0,
            created_by_staff_id=staff_prof.id
        )
        db.session.add(classroom)

        self.class1 = Class(department="CSE", year=3, semester=5, section="A", name="CSE-3A")
        self.class2 = Class(department="ECE", year=2, semester=3, section="B", name="ECE-2B")
        db.session.add_all([self.class1, self.class2])
        db.session.flush()

        self.subject = Subject(subject_code="CS501", subject_name="Cloud", class_id=self.class1.id, staff_id=staff_prof.id)
        db.session.add(self.subject)
        db.session.flush()

        now = datetime.now(timezone.utc)
        self.session_obj = AttendanceSession(
            subject_id=self.subject.id,
            class_id=self.class1.id,
            classroom_id=classroom.id,
            staff_id=staff_prof.id,
            start_time=now,
            end_time=now + timedelta(hours=1),
            refresh_interval_seconds=30,
            is_active=True
        )
        db.session.add(self.session_obj)

        # Enrolled student in class1
        stu_u1 = User(full_name="Enrolled Alice", email="alice.qr@college.edu", role="student", is_approved=True)
        stu_u1.set_password("Pass123!")
        db.session.add(stu_u1)
        db.session.flush()
        self.student_enrolled = Student(user_id=stu_u1.id, student_id="STU_ENROLLED", class_id=self.class1.id)
        db.session.add(self.student_enrolled)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student_enrolled.id, class_id=self.class1.id))

        # Not enrolled student (class2)
        stu_u2 = User(full_name="Outsider Bob", email="bob.qr@college.edu", role="student", is_approved=True)
        stu_u2.set_password("Pass123!")
        db.session.add(stu_u2)
        db.session.flush()
        self.student_outsider = Student(user_id=stu_u2.id, student_id="STU_OUTSIDER", class_id=self.class2.id)
        db.session.add(self.student_outsider)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student_outsider.id, class_id=self.class2.id))

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_qr_generation_and_validation(self):
        qr_b64, metadata, err = generate_session_qr(self.session_obj.id)
        self.assertIsNone(err)
        self.assertIsNotNone(qr_b64)
        self.assertTrue(qr_b64.startswith("data:image/png;base64,"))

        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()
        self.assertIsNotNone(token)

        # Validate with enrolled student
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_enrolled)
        self.assertTrue(valid)
        self.assertEqual(outcome, "PASSED")
        self.assertEqual(sess.id, self.session_obj.id)

    def test_qr_expiry(self):
        qr_b64, metadata, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # Manually backdate expiry beyond leeway
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=20)
        db.session.commit()

        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_enrolled)
        self.assertFalse(valid)
        self.assertEqual(outcome, "REJECTED_QR")
        self.assertIn("expired", msg.lower())

    def test_unauthorized_class_enrollment(self):
        qr_b64, metadata, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # Validate with student not enrolled in CS501
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_outsider)
        self.assertFalse(valid)
        self.assertEqual(outcome, "SESSION_NOT_ALLOWED")
        self.assertIn("not enrolled", msg.lower())

    def test_closed_session_rejection(self):
        qr_b64, metadata, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # Close session
        self.session_obj.is_active = False
        db.session.commit()

        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_enrolled)
        self.assertFalse(valid)
        self.assertEqual(outcome, "REJECTED_QR")

    def test_class_assignment_roster_and_verification_alignment(self):
        # Verify subject roster count uses the academic class enrollments
        roster_count = self.subject.assigned_class.enrollments.count()
        self.assertEqual(roster_count, 1)

        qr_b64, metadata, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # Enrolled student in class1 can proceed
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_enrolled)
        self.assertTrue(valid)
        self.assertEqual(outcome, "PASSED")

        # Student enrolled in class2 remains blocked
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_outsider)
        self.assertFalse(valid)
        self.assertEqual(outcome, "SESSION_NOT_ALLOWED")
        self.assertIn("not enrolled", msg.lower())

    def test_multi_staff_subject_assignment(self):
        # Create second staff member
        staff2_u = User(full_name="Prof. Second", email="second@college.edu", role="staff", is_approved=True)
        staff2_u.set_password("Pass123!")
        db.session.add(staff2_u)
        db.session.flush()

        staff2_prof = StaffProfile(user_id=staff2_u.id, staff_id="STF_2", department="CSE")
        db.session.add(staff2_prof)
        db.session.flush()

        # Second staff member can also be assigned CS501 for class1 without unique constraint violation
        sub2 = Subject(subject_code="CS501", subject_name="Cloud", class_id=self.class1.id, staff_id=staff2_prof.id)
        db.session.add(sub2)
        db.session.flush()

        # Verify both subjects point to class1 and have same roster count
        self.assertEqual(sub2.assigned_class.id, self.class1.id)
        self.assertEqual(sub2.assigned_class.enrollments.count(), 1)

        # Session created by second staff member
        now = datetime.now(timezone.utc)
        sess2 = AttendanceSession(
            subject_id=sub2.id,
            class_id=sub2.class_id,
            classroom_id=self.session_obj.classroom_id,
            staff_id=staff2_prof.id,
            start_time=now,
            end_time=now + timedelta(hours=1),
            refresh_interval_seconds=30,
            is_active=True
        )
        db.session.add(sess2)
        db.session.commit()

        qr_b64, metadata, err = generate_session_qr(sess2.id)
        token = QRToken.query.filter_by(session_id=sess2.id, is_active=True).first()

        # Enrolled student in class1 can proceed with second staff's session
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_enrolled)
        self.assertTrue(valid)
        self.assertEqual(outcome, "PASSED")

        # Outsider remains blocked
        valid, outcome, sess, msg = validate_qr_token(token.token_value, self.student_outsider)
        self.assertFalse(valid)
        self.assertEqual(outcome, "SESSION_NOT_ALLOWED")

if __name__ == "__main__":
    unittest.main()
