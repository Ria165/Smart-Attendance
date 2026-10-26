import unittest
from datetime import datetime, timezone
from app import create_app, db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Enrollment
from app.models.verification import AuditLog
from scripts.approve_staff import approve_staff_account, setup_or_create_staff

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed basic class
        self.academic_class = Class(department="CSE", year=3, semester=5, section="A", name="CSE-3A")
        db.session.add(self.academic_class)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_staff_registration_and_cli_approval(self):
        # Register new staff
        resp = self.client.post("/auth/register/staff", data={
            "full_name": "Prof. Test Staff",
            "email": "test.staff@college.edu",
            "password": "Password123!",
            "staff_id": "STAFF999",
            "department": "Computer Science",
            "designation": "Assistant Professor"
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Verify staff exists but is unapproved
        staff_user = User.query.filter_by(email="test.staff@college.edu").first()
        self.assertIsNotNone(staff_user)
        self.assertFalse(staff_user.is_approved)

        # Attempt to login while unapproved -> redirected with "Your account is awaiting approval."
        login_resp = self.client.post("/auth/login", data={
            "identifier": "test.staff@college.edu",
            "password": "Password123!",
            "role": "staff"
        }, follow_redirects=True)
        self.assertIn(b"Your account is awaiting approval.", login_resp.data)

        # Pending staff with active session attempts to access staff dashboard
        with self.client.session_transaction() as sess:
            sess["user_id"] = staff_user.id
            sess["role"] = "staff"

        dash_resp = self.client.get("/staff/dashboard", follow_redirects=True)
        self.assertIn(b"Your account is awaiting approval.", dash_resp.data)

        # Authorize staff account via setup CLI helper
        approved = approve_staff_account(self.app, "test.staff@college.edu")
        self.assertTrue(approved)

        # Verify status in database
        db.session.refresh(staff_user)
        self.assertTrue(staff_user.is_approved)
        self.assertFalse(staff_user.is_rejected)
        self.assertIsNotNone(staff_user.approved_at)

        # Authorized staff logs in successfully
        login_resp2 = self.client.post("/auth/login", data={
            "identifier": "test.staff@college.edu",
            "password": "Password123!",
            "role": "staff"
        }, follow_redirects=True)
        self.assertEqual(login_resp2.status_code, 200)
        self.assertIn(b"Faculty Dashboard", login_resp2.data)

    def test_setup_or_create_staff_authorizes_pending_account(self):
        # Create a pending staff user
        staff_u = User(full_name="Prof. Pending", email="pending@college.edu", role="staff", is_approved=False)
        staff_u.set_password("OldPassword123!")
        db.session.add(staff_u)
        db.session.flush()
        db.session.add(StaffProfile(user_id=staff_u.id, staff_id="STAFF_PENDING", department="CSE"))
        db.session.commit()

        # Run setup_or_create_staff with same email
        res = setup_or_create_staff(
            self.app,
            full_name="Prof. Pending Updated",
            email="pending@college.edu",
            password="NewPassword123!",
            staff_id="STAFF_PENDING",
            department="Computer Science"
        )
        self.assertTrue(res)

        db.session.refresh(staff_u)
        self.assertTrue(staff_u.is_approved)
        self.assertTrue(staff_u.check_password("NewPassword123!"))

    def test_student_registration_and_staff_approval(self):
        # Register student
        resp = self.client.post("/auth/register/student", data={
            "full_name": "Student Test",
            "email": "student.test@college.edu",
            "password": "StudentPass123!",
            "student_id": "STU999",
            "class_id": self.academic_class.id
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        student_user = User.query.filter_by(email="student.test@college.edu").first()
        self.assertIsNotNone(student_user)
        self.assertFalse(student_user.is_approved)

        # Student login while pending fails with message
        stu_login = self.client.post("/auth/login", data={
            "identifier": "student.test@college.edu",
            "password": "StudentPass123!",
            "role": "student"
        }, follow_redirects=True)
        self.assertIn(b"Your account is awaiting approval.", stu_login.data)

        # Create approved staff to review student
        staff_user = User(full_name="Staff Reviewer", email="rev@college.edu", role="staff", is_approved=True)
        staff_user.set_password("Pass123!")
        db.session.add(staff_user)
        db.session.flush()
        staff_prof = StaffProfile(user_id=staff_user.id, staff_id="STAFF_REV", department="CSE")
        db.session.add(staff_prof)
        db.session.commit()

        # Staff logs in
        self.client.post("/auth/login", data={"identifier": "rev@college.edu", "password": "Pass123!", "role": "staff"})

        # Staff approves student
        appr_resp = self.client.post("/staff/approvals", data={
            "user_id": student_user.id,
            "action": "approve"
        }, follow_redirects=True)
        self.assertEqual(appr_resp.status_code, 200)

        # Refresh student status
        db.session.refresh(student_user)
        self.assertTrue(student_user.is_approved)
        self.assertEqual(student_user.approved_by_staff_id, staff_prof.id)
        self.assertIsNotNone(student_user.approved_at)

        # Student logs in with Student ID or Email
        stu_login_ok = self.client.post("/auth/login", data={
            "identifier": "STU999",
            "password": "StudentPass123!",
            "role": "student"
        }, follow_redirects=True)
        self.assertEqual(stu_login_ok.status_code, 200)
        self.assertIn(b"Student Dashboard", stu_login_ok.data)

    def test_student_cannot_approve_another_student_or_access_staff_pages(self):
        # Create approved student
        stu1 = User(full_name="Alice", email="alice@college.edu", role="student", is_approved=True)
        stu1.set_password("Pass123!")
        db.session.add(stu1)
        db.session.flush()
        db.session.add(Student(user_id=stu1.id, student_id="STU001", class_id=self.academic_class.id))

        # Create pending student
        stu2 = User(full_name="Bob", email="bob@college.edu", role="student", is_approved=False)
        stu2.set_password("Pass123!")
        db.session.add(stu2)
        db.session.flush()
        db.session.add(Student(user_id=stu2.id, student_id="STU002", class_id=self.academic_class.id))
        db.session.commit()

        # Alice (student) logs in
        self.client.post("/auth/login", data={"identifier": "alice@college.edu", "password": "Pass123!", "role": "student"})

        # Student attempts to access staff approvals page -> 403 Forbidden
        appr_page = self.client.get("/staff/approvals")
        self.assertEqual(appr_page.status_code, 403)

        # Student attempts to post an approval for Bob -> 403 Forbidden
        post_appr = self.client.post("/staff/approvals", data={
            "user_id": stu2.id,
            "action": "approve"
        })
        self.assertEqual(post_appr.status_code, 403)

        # Verify Bob remains unapproved
        db.session.refresh(stu2)
        self.assertFalse(stu2.is_approved)

    def test_pending_student_cannot_bypass_approval_via_api(self):
        # Create pending student
        stu = User(full_name="Pending Stu", email="pending.stu@college.edu", role="student", is_approved=False)
        stu.set_password("Pass123!")
        db.session.add(stu)
        db.session.flush()
        stu_prof = Student(user_id=stu.id, student_id="STU_PEND", class_id=self.academic_class.id)
        db.session.add(stu_prof)
        db.session.commit()

        # Simulate direct session spoofing or unapproved session
        with self.client.session_transaction() as sess:
            sess["user_id"] = stu.id
            sess["role"] = "student"
            sess["student_pk"] = stu_prof.id

        # Direct API call to face enrollment
        api_resp = self.client.post("/student/api/enroll-face", json={"face_image": "test"})
        # Must be rejected because student is not approved
        self.assertIn(api_resp.status_code, (302, 403))

    def test_login_credentials_and_rejection_messages(self):
        # 1. Invalid credentials test
        resp_bad = self.client.post("/auth/login", data={
            "identifier": "nonexistent@college.edu",
            "password": "wrongpassword",
            "role": "staff"
        }, follow_redirects=True)
        self.assertIn(b"Incorrect user ID or password.", resp_bad.data)

        # 2. Rejected user test
        rejected_u = User(full_name="Rejected User", email="rejected@college.edu", role="student", is_approved=False, is_rejected=True)
        rejected_u.set_password("Pass123!")
        db.session.add(rejected_u)
        db.session.flush()
        db.session.add(Student(user_id=rejected_u.id, student_id="STU_REJ", class_id=self.academic_class.id))
        db.session.commit()

        resp_rej = self.client.post("/auth/login", data={
            "identifier": "rejected@college.edu",
            "password": "Pass123!",
            "role": "student"
        }, follow_redirects=True)
        self.assertIn(b"Your account registration was not approved. Contact an authorized staff member.", resp_rej.data)

    def test_audit_logging(self):
        user = User(full_name="Audited User", email="audit@college.edu", role="staff", is_approved=True)
        user.set_password("Pass123!")
        db.session.add(user)
        db.session.flush()
        db.session.add(StaffProfile(user_id=user.id, staff_id="STF_AUD", department="CSE"))
        db.session.commit()

        # Login generates audit log
        self.client.post("/auth/login", data={"identifier": "audit@college.edu", "password": "Pass123!", "role": "staff"})

        log = AuditLog.query.filter_by(user_id=user.id, action="STAFF_LOGIN").first()
        self.assertIsNotNone(log)
        self.assertIn("Staff logged in", log.details)

if __name__ == "__main__":
    unittest.main()
