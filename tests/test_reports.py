import unittest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject, Enrollment
from app.models.classroom import Classroom
from app.models.attendance import AttendanceSession, AttendanceRecord
from app.reports.generator import calculate_student_statistics, generate_monthly_report_data
from app.reports.excel_export import build_excel_attendance_report
from app.reports.pdf_export import build_pdf_attendance_report

class ReportsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed Staff 1
        staff_u1 = User(full_name="Prof. Turing", email="turing@college.edu", role="staff", is_approved=True)
        staff_u1.set_password("Pass123!")
        db.session.add(staff_u1)
        db.session.flush()
        self.staff1 = StaffProfile(user_id=staff_u1.id, staff_id="STF_01", department="CSE")
        db.session.add(self.staff1)
        db.session.flush()

        # Seed Staff 2
        staff_u2 = User(full_name="Prof. Hopper", email="hopper@college.edu", role="staff", is_approved=True)
        staff_u2.set_password("Pass123!")
        db.session.add(staff_u2)
        db.session.flush()
        self.staff2 = StaffProfile(user_id=staff_u2.id, staff_id="STF_02", department="ECE")
        db.session.add(self.staff2)
        db.session.flush()

        # Classroom
        self.classroom = Classroom(
            classroom_name="Hall A", building_name="Main", room_number="1",
            latitude=12.9716, longitude=77.5946, allowed_radius_meters=50.0,
            created_by_staff_id=self.staff1.id
        )
        db.session.add(self.classroom)

        self.ac_class = Class(department="CSE", year=3, semester=5, section="A", name="CSE-3A")
        db.session.add(self.ac_class)
        db.session.flush()

        self.subject1 = Subject(subject_code="CS501", subject_name="Cloud", class_id=self.ac_class.id, staff_id=self.staff1.id)
        self.subject2 = Subject(subject_code="EC301", subject_name="Signals", class_id=self.ac_class.id, staff_id=self.staff2.id)
        db.session.add_all([self.subject1, self.subject2])
        db.session.flush()

        # Student 1: Alice (will attend 8 out of 10 sessions -> 80%)
        stu_u1 = User(full_name="Alice", email="alice@college.edu", role="student", is_approved=True)
        stu_u1.set_password("Pass123!")
        db.session.add(stu_u1)
        db.session.flush()
        self.student1 = Student(user_id=stu_u1.id, student_id="STU_001", class_id=self.ac_class.id, face_enrolled=True)
        db.session.add(self.student1)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student1.id, class_id=self.ac_class.id))

        # Student 2: Bob (will attend 4 out of 10 sessions -> 40% < 75% LOW)
        stu_u2 = User(full_name="Bob", email="bob@college.edu", role="student", is_approved=True)
        stu_u2.set_password("Pass123!")
        db.session.add(stu_u2)
        db.session.flush()
        self.student2 = Student(user_id=stu_u2.id, student_id="STU_002", class_id=self.ac_class.id, face_enrolled=True)
        db.session.add(self.student2)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student2.id, class_id=self.ac_class.id))

        # Create 10 sessions in October 2026
        # Plus 1 CANCELLED session (must be excluded from calculation!)
        self.year = 2026
        self.month = 10

        for i in range(10):
            sess_time = datetime(2026, 10, i + 1, 10, 0, 0)
            sess = AttendanceSession(
                subject_id=self.subject1.id,
                class_id=self.ac_class.id,
                classroom_id=self.classroom.id,
                staff_id=self.staff1.id,
                start_time=sess_time,
                end_time=sess_time + timedelta(hours=1),
                is_active=False,
                is_cancelled=False
            )
            db.session.add(sess)
            db.session.flush()

            # Alice attends first 8
            if i < 8:
                db.session.add(AttendanceRecord(
                    student_id=self.student1.id,
                    subject_id=self.subject1.id,
                    class_id=self.ac_class.id,
                    session_id=sess.id,
                    classroom_id=self.classroom.id,
                    attendance_date=sess_time.date(),
                    marked_timestamp=sess_time,
                    final_status="PRESENT"
                ))

            # Bob attends first 4
            if i < 4:
                db.session.add(AttendanceRecord(
                    student_id=self.student2.id,
                    subject_id=self.subject1.id,
                    class_id=self.ac_class.id,
                    session_id=sess.id,
                    classroom_id=self.classroom.id,
                    attendance_date=sess_time.date(),
                    marked_timestamp=sess_time,
                    final_status="PRESENT"
                ))

        # Add 1 CANCELLED session
        cancelled_time = datetime(2026, 10, 15, 10, 0, 0)
        sess_cancelled = AttendanceSession(
            subject_id=self.subject1.id,
            class_id=self.ac_class.id,
            classroom_id=self.classroom.id,
            staff_id=self.staff1.id,
            start_time=cancelled_time,
            end_time=cancelled_time + timedelta(hours=1),
            is_active=False,
            is_cancelled=True
        )
        db.session.add(sess_cancelled)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_percentage_calculation_and_cancelled_exclusion(self):
        # Alice attended 8 out of 10 held (11th was cancelled and must NOT count)
        stats1 = calculate_student_statistics(self.student1.id, self.subject1.id, self.year, self.month)
        self.assertEqual(stats1["sessions_held"], 10)
        self.assertEqual(stats1["present_count"], 8)
        self.assertEqual(stats1["absent_count"], 2)
        self.assertAlmostEqual(stats1["percentage"], 80.0, places=1)
        self.assertFalse(stats1["is_low"])
        self.assertEqual(stats1["sessions_needed"], 0)

    def test_low_attendance_and_sessions_needed_calculation(self):
        # Bob attended 4 out of 10 held -> 40.0% < 75%
        # Formula: (4 + X) / (10 + X) >= 0.75
        # 4 + X >= 7.5 + 0.75X => 0.25X >= 3.5 => X >= 14
        stats2 = calculate_student_statistics(self.student2.id, self.subject1.id, self.year, self.month)
        self.assertEqual(stats2["sessions_held"], 10)
        self.assertEqual(stats2["present_count"], 4)
        self.assertAlmostEqual(stats2["percentage"], 40.0, places=1)
        self.assertTrue(stats2["is_low"])
        self.assertEqual(stats2["sessions_needed"], 14)

    def test_zero_sessions_division_by_zero_safety(self):
        # CS502 has 0 sessions
        stats_zero = calculate_student_statistics(self.student1.id, self.subject2.id, self.year, self.month)
        self.assertEqual(stats_zero["sessions_held"], 0)
        self.assertIsNone(stats_zero["percentage"])
        self.assertIn("N/A", stats_zero["percentage_display"])
        self.assertFalse(stats_zero["is_low"])

    def test_monthly_report_dataset_structure(self):
        report_data = generate_monthly_report_data(self.subject1.id, self.year, self.month)
        self.assertIsNotNone(report_data)
        self.assertEqual(report_data["total_sessions"], 10)
        self.assertEqual(report_data["total_enrolled"], 2)
        self.assertEqual(report_data["below_threshold_count"], 1) # Bob
        self.assertEqual(report_data["above_threshold_count"], 1) # Alice
        # Class average: (8 + 4) / (10 + 10) = 12 / 20 = 60.0%
        self.assertAlmostEqual(report_data["class_average"], 60.0, places=1)

    def test_excel_export_generation(self):
        report_data = generate_monthly_report_data(self.subject1.id, self.year, self.month)
        excel_bytes = build_excel_attendance_report(report_data)
        self.assertIsInstance(excel_bytes, bytes)
        self.assertGreater(len(excel_bytes), 1000)
        # Check ZIP / XLSX magic header
        self.assertTrue(excel_bytes.startswith(b"PK"))

    def test_pdf_export_generation(self):
        report_data = generate_monthly_report_data(self.subject1.id, self.year, self.month)
        pdf_bytes = build_pdf_attendance_report(report_data)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        # Check PDF header
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_staff_report_access_isolation(self):
        # Staff 2 (Prof. Hopper) logs in
        self.client.post("/auth/login", data={"email": "hopper@college.edu", "password": "Pass123!", "role": "staff"})

        # Attempts to export report for CS501 owned by Staff 1 (Prof. Turing)
        resp = self.client.get(f"/reports/export/excel?subject_id={self.subject1.id}&year=2026&month=10", follow_redirects=True)
        # Redirected with flash error
        self.assertIn(b"Unauthorized", resp.data)

    def test_student_report_access_forbidden(self):
        # Student logs in
        self.client.post("/auth/login", data={"email": "alice@college.edu", "password": "Pass123!", "role": "student"})

        # Student attempts to access staff monthly reports page
        resp = self.client.get("/reports/")
        self.assertEqual(resp.status_code, 403)

if __name__ == "__main__":
    unittest.main()
