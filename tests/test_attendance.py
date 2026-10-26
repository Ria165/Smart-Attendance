import unittest
import io
import base64
import numpy as np
from PIL import Image
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject, Enrollment
from app.models.classroom import Classroom
from app.models.attendance import AttendanceSession, QRToken, AttendanceRecord, AttendanceCorrection
from app.models.verification import FaceTemplate
from app.qr.generator import generate_session_qr
from app.attendance.services import process_attendance_submission

class AttendanceWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed staff
        staff_u = User(full_name="Prof. Attendance", email="att.staff@college.edu", role="staff", is_approved=True)
        staff_u.set_password("Pass123!")
        db.session.add(staff_u)
        db.session.flush()

        self.staff_prof = StaffProfile(user_id=staff_u.id, staff_id="STF_ATT", department="CSE")
        db.session.add(self.staff_prof)
        db.session.flush()

        # Classroom (Bangalore: 12.9716, 77.5946, 50m radius)
        self.classroom = Classroom(
            classroom_name="Hall 101",
            building_name="Block A",
            room_number="101",
            latitude=12.971600,
            longitude=77.594600,
            allowed_radius_meters=50.0,
            created_by_staff_id=self.staff_prof.id
        )
        db.session.add(self.classroom)

        self.ac_class = Class(department="CSE", year=3, semester=5, section="A", name="CSE-3A")
        db.session.add(self.ac_class)
        db.session.flush()

        self.subject = Subject(subject_code="CS501", subject_name="Cloud", class_id=self.ac_class.id, staff_id=self.staff_prof.id)
        db.session.add(self.subject)
        db.session.flush()

        now = datetime.now(timezone.utc)
        self.session_obj = AttendanceSession(
            subject_id=self.subject.id,
            class_id=self.ac_class.id,
            classroom_id=self.classroom.id,
            staff_id=self.staff_prof.id,
            start_time=now,
            end_time=now + timedelta(hours=1),
            refresh_interval_seconds=30,
            is_active=True
        )
        db.session.add(self.session_obj)

        # Student with enrolled face template
        stu_u = User(full_name="Alice Student", email="alice.att@college.edu", role="student", is_approved=True)
        stu_u.set_password("Pass123!")
        db.session.add(stu_u)
        db.session.flush()

        self.student = Student(user_id=stu_u.id, student_id="STU_ATT_01", class_id=self.ac_class.id, face_enrolled=True)
        db.session.add(self.student)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student.id, class_id=self.ac_class.id))

        # Generate synthetic realistic face crop and corresponding embedding
        # Create a textured portrait face image for mock camera
        img_arr = np.random.randint(60, 200, (120, 120, 3), dtype=np.uint8)
        pil_img = Image.fromarray(img_arr)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG")
        self.mock_face_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

        from app.face.detector import detect_face
        from app.face.recognizer import extract_face_embedding
        found, crop, _ = detect_face(self.mock_face_b64)
        embedding = extract_face_embedding(crop)

        self.face_template = FaceTemplate(
            student_id=self.student.id,
            model_name="sface_spatial_v1",
            vector_dimension=len(embedding)
        )
        self.face_template.set_embedding(embedding)
        db.session.add(self.face_template)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_successful_multi_factor_attendance(self):
        # 1. Generate active QR
        qr_b64, meta, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # 2. Process submission with valid token, within 15m GPS, and matching face
        res = process_attendance_submission(
            student=self.student,
            qr_token=token.token_value,
            latitude=12.971610,
            longitude=77.594610,
            accuracy_meters=8.0,
            face_image_data=self.mock_face_b64
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["outcome"], "PRESENT")

        # Verify record in database
        rec = AttendanceRecord.query.filter_by(student_id=self.student.id, session_id=self.session_obj.id).first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.final_status, "PRESENT")
        self.assertEqual(rec.qr_verification_result, "PASSED")
        self.assertEqual(rec.location_verification_result, "PASSED")
        self.assertEqual(rec.face_verification_result, "PASSED")

    def test_duplicate_attendance_prevention(self):
        # First attendance submission succeeds
        qr_b64, meta, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        res1 = process_attendance_submission(
            student=self.student,
            qr_token=token.token_value,
            latitude=12.971610,
            longitude=77.594610,
            accuracy_meters=8.0,
            face_image_data=self.mock_face_b64
        )
        self.assertEqual(res1["status"], "SUCCESS")

        # Second attendance submission for same session and student MUST be rejected
        res2 = process_attendance_submission(
            student=self.student,
            qr_token=token.token_value,
            latitude=12.971610,
            longitude=77.594610,
            accuracy_meters=8.0,
            face_image_data=self.mock_face_b64
        )
        self.assertEqual(res2["status"], "FAILED")
        self.assertEqual(res2["outcome"], "ALREADY_MARKED")
        self.assertIn("already", res2["message"].lower())

    def test_gps_violation_rejection(self):
        qr_b64, meta, err = generate_session_qr(self.session_obj.id)
        token = QRToken.query.filter_by(session_id=self.session_obj.id, is_active=True).first()

        # Coordinates 400m away
        res = process_attendance_submission(
            student=self.student,
            qr_token=token.token_value,
            latitude=12.975000,
            longitude=77.594600,
            accuracy_meters=8.0,
            face_image_data=self.mock_face_b64
        )
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(res["outcome"], "LOCATION_FAILED")

        # No PRESENT record should exist
        rec = AttendanceRecord.query.filter_by(student_id=self.student.id, session_id=self.session_obj.id).first()
        self.assertIsNone(rec)

    def test_staff_manual_attendance_correction(self):
        # Create existing record
        now = datetime.now(timezone.utc)
        rec = AttendanceRecord(
            student_id=self.student.id,
            subject_id=self.subject.id,
            class_id=self.ac_class.id,
            session_id=self.session_obj.id,
            classroom_id=self.classroom.id,
            attendance_date=now.date(),
            marked_timestamp=now,
            qr_verification_result="PASSED",
            location_verification_result="PASSED",
            face_verification_result="PASSED",
            final_status="ABSENT"
        )
        db.session.add(rec)
        db.session.commit()

        # Log in as authorized staff
        self.client.post("/auth/login", data={"email": "att.staff@college.edu", "password": "Pass123!", "role": "staff"})

        # Submit manual correction
        resp = self.client.post(f"/attendance/correct/{rec.id}", json={
            "new_status": "PRESENT",
            "reason": "Student device network timeout; verified physical attendance"
        })
        self.assertEqual(resp.status_code, 200)

        db.session.refresh(rec)
        self.assertEqual(rec.final_status, "PRESENT")

        # Verify audit log and correction entry
        correction = AttendanceCorrection.query.filter_by(attendance_record_id=rec.id).first()
        self.assertIsNotNone(correction)
        self.assertEqual(correction.previous_status, "ABSENT")
        self.assertEqual(correction.new_status, "PRESENT")
        self.assertIn("verified physical attendance", correction.reason)

    def test_live_session_route_render_qr_regression(self):
        """
        REGRESSION TEST:
        Ensure that accessing the live session route renders session_live.html and base.html
        without raising 'jinja2.exceptions.UndefinedError: AttendanceSession object has no attribute get'.
        Verifies that the dynamic QR code is rendered and user session in base.html works properly.
        """
        # Unauthenticated request should be redirected to login
        unauth_resp = self.client.get(f"/staff/sessions/{self.session_obj.id}/live")
        self.assertEqual(unauth_resp.status_code, 302)
        self.assertIn("/auth/login", unauth_resp.headers.get("Location", ""))

        # Log in as authorized staff
        login_resp = self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # Access live session
        live_resp = self.client.get(f"/staff/sessions/{self.session_obj.id}/live")
        self.assertEqual(live_resp.status_code, 200)
        html = live_resp.data.decode("utf-8")

        # Verify page rendered properly without Jinja UndefinedError
        self.assertIn("Live Attendance Session", html)
        self.assertIn(self.subject.subject_code, html)
        self.assertIn(self.classroom.classroom_name, html)
        self.assertIn("active-qr-image", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("Prof. Attendance", html)

    def test_staff_create_session_and_view_live_qr(self):
        """
        Full workflow test:
        Staff creates session, enters classroom location, generates QR, and views live QR page.
        """
        # Log in as authorized staff
        self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)

        # Create session
        create_resp = self.client.post("/staff/sessions/create", data={
            "subject_id": self.subject.id,
            "classroom_id": self.classroom.id,
            "duration_minutes": 45,
            "refresh_interval": 20
        }, follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)

        # Should land on the live session page
        html = create_resp.data.decode("utf-8")
        self.assertIn("active-qr-image", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("Anti-Proxy Dynamic QR", html)

    def test_attendance_session_model_attributes_direct_access(self):
        """
        Model sanity test:
        SQLAlchemy model instance does not have a .get() method and attributes must be accessed directly.
        """
        self.assertFalse(hasattr(self.session_obj, "get"))
        self.assertEqual(self.session_obj.subject_id, self.subject.id)
        self.assertEqual(self.session_obj.classroom_id, self.classroom.id)
        self.assertEqual(self.session_obj.refresh_interval_seconds, 30)

    def test_staff_attendance_records_page_rendering_with_records_regression(self):
        """
        REGRESSION TEST:
        Ensure that accessing the staff attendance records page (/staff/records)
        renders records.html without raising 'jinja2.exceptions.UndefinedError:
        app.models.attendance.AttendanceRecord object has no attribute academic_class'.
        Verifies that student class name, subject code, and student details render correctly.
        """
        # Create an attendance record for the student
        now = datetime.now(timezone.utc)
        record = AttendanceRecord(
            student_id=self.student.id,
            subject_id=self.subject.id,
            class_id=self.ac_class.id,
            session_id=self.session_obj.id,
            classroom_id=self.classroom.id,
            attendance_date=now.date(),
            marked_timestamp=now,
            qr_verification_result="PASSED",
            location_verification_result="PASSED",
            face_verification_result="PASSED",
            final_status="PRESENT"
        )
        db.session.add(record)
        db.session.commit()

        # Log in as authorized staff
        login_resp = self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # Access records page
        records_resp = self.client.get("/staff/records")
        self.assertEqual(records_resp.status_code, 200)
        html = records_resp.data.decode("utf-8")

        # Verify page rendered properly with student details, class name, and subject code
        self.assertIn("Attendance Verification Records", html)
        self.assertIn("Alice Student", html)
        self.assertIn(self.ac_class.name, html)
        self.assertIn(self.subject.subject_code, html)
        self.assertIn("STU_ATT_01", html)
        self.assertIn("PRESENT", html)

    def test_dashboard_cards_navigation_destinations(self):
        """
        REGRESSION TEST:
        Ensure that all 4 dashboard metric cards are clickable links and navigate
        to the appropriate existing pages:
        1. Total Sessions -> /staff/sessions
        2. Assigned Students -> /staff/subjects
        3. Total Present -> /staff/records?status=PRESENT
        4. Pending Approvals -> /staff/approvals
        """
        # Log in as authorized staff
        self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)

        dashboard_resp = self.client.get("/staff/dashboard")
        self.assertEqual(dashboard_resp.status_code, 200)
        html = dashboard_resp.data.decode("utf-8")

        # 1. Total Sessions card link
        self.assertIn("/staff/sessions", html)
        sess_resp = self.client.get("/staff/sessions")
        self.assertEqual(sess_resp.status_code, 200)
        self.assertIn("Attendance Sessions", sess_resp.data.decode("utf-8"))

        # 2. Assigned Students card link
        self.assertIn("/staff/subjects", html)
        subj_resp = self.client.get("/staff/subjects")
        self.assertEqual(subj_resp.status_code, 200)
        self.assertIn("Subjects & Academic Classes", subj_resp.data.decode("utf-8"))
        self.assertIn("Assigned Class Student Rosters", subj_resp.data.decode("utf-8"))

        # 3. Total Present card link
        self.assertIn("/staff/records?status=PRESENT", html)
        rec_resp = self.client.get("/staff/records?status=PRESENT")
        self.assertEqual(rec_resp.status_code, 200)
        self.assertIn("Attendance Verification Records", rec_resp.data.decode("utf-8"))

        # 4. Pending Approvals card link
        self.assertIn("/staff/approvals", html)
        appr_resp = self.client.get("/staff/approvals")
        self.assertEqual(appr_resp.status_code, 200)
        self.assertIn("Account Approvals & Verification", appr_resp.data.decode("utf-8"))

    def test_total_present_filtering(self):
        """
        REGRESSION TEST:
        Verify that /staff/records?status=PRESENT filters to only show records with final_status=PRESENT.
        """
        now = datetime.now(timezone.utc)
        # Create second student for absent record
        u_absent = User(full_name="Bob Absent", email="bob.absent@college.edu", role="student", is_approved=True)
        u_absent.set_password("Pass123!")
        db.session.add(u_absent)
        db.session.flush()
        stu_absent = Student(user_id=u_absent.id, student_id="STU_ABSENT_02", class_id=self.ac_class.id)
        db.session.add(stu_absent)
        db.session.flush()

        rec_present = AttendanceRecord(
            student_id=self.student.id,
            subject_id=self.subject.id,
            class_id=self.ac_class.id,
            session_id=self.session_obj.id,
            classroom_id=self.classroom.id,
            attendance_date=now.date(),
            marked_timestamp=now,
            qr_verification_result="PASSED",
            location_verification_result="PASSED",
            face_verification_result="PASSED",
            final_status="PRESENT"
        )
        rec_absent = AttendanceRecord(
            student_id=stu_absent.id,
            subject_id=self.subject.id,
            class_id=self.ac_class.id,
            session_id=self.session_obj.id,
            classroom_id=self.classroom.id,
            attendance_date=now.date(),
            marked_timestamp=now,
            qr_verification_result="FAILED",
            location_verification_result="FAILED",
            face_verification_result="FAILED",
            final_status="ABSENT"
        )
        db.session.add_all([rec_present, rec_absent])
        db.session.commit()

        # Log in as authorized staff
        self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)

        resp = self.client.get("/staff/records?status=PRESENT")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Alice Student", html)
        self.assertNotIn("Bob Absent", html)

    def test_pending_approvals_count_and_rejection_exclusion(self):
        """
        REGRESSION TEST:
        Ensure that the dashboard pending approvals count accurately reflects
        only users awaiting approval (is_approved=False, is_rejected=False),
        and strictly excludes rejected accounts (is_rejected=True) and approved accounts.
        Also verifies count displays 0 when there are zero pending records.
        """
        # Create a rejected student
        u_rej = User(full_name="Rejected Student", email="rejected@college.edu", role="student", is_approved=False, is_rejected=True)
        u_rej.set_password("Pass123!")
        db.session.add(u_rej)
        db.session.commit()

        # Log in as staff
        self.client.post("/auth/login", data={
            "identifier": "att.staff@college.edu",
            "password": "Pass123!",
            "role": "staff"
        }, follow_redirects=True)

        # 0 pending records (existing students are approved, u_rej is rejected)
        resp_zero = self.client.get("/staff/dashboard")
        self.assertEqual(resp_zero.status_code, 200)
        html_zero = resp_zero.data.decode("utf-8")
        self.assertIn('aria-label="Pending Approvals: 0"', html_zero)

        # Now add one pending student
        u_pen = User(full_name="Pending Student", email="pending.stu@college.edu", role="student", is_approved=False, is_rejected=False)
        u_pen.set_password("Pass123!")
        db.session.add(u_pen)
        db.session.commit()

        resp_one = self.client.get("/staff/dashboard")
        self.assertEqual(resp_one.status_code, 200)
        html_one = resp_one.data.decode("utf-8")
        self.assertIn('aria-label="Pending Approvals: 1"', html_one)

        # Navigate to approvals page
        appr_resp = self.client.get("/staff/approvals")
        self.assertEqual(appr_resp.status_code, 200)
        appr_html = appr_resp.data.decode("utf-8")
        self.assertIn("Pending Student", appr_html)

if __name__ == "__main__":
    unittest.main()


