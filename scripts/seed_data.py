import sys
import os
from datetime import datetime, timezone, timedelta
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Subject, Enrollment
from app.models.classroom import Classroom
from app.models.attendance import AttendanceSession, AttendanceRecord, QRToken
from app.models.verification import FaceTemplate, VerificationEvent, AuditLog
from app.face.recognizer import extract_face_embedding

def seed_database():
    app = create_app()
    with app.app_context():
        print("\n[SEED] Initializing database schema...")
        db.create_all()

        # Check if already seeded
        if User.query.filter_by(email="alan.turing@college.edu").first():
            print("[INFO] Database already seeded. Skipping initial seeding.")
            return

        print("[SEED] Creating Academic Classes...")
        class_cse = Class(department="CSE", year=3, semester=5, section="A", name="CSE-Y3S5-A")
        class_ece = Class(department="ECE", year=2, semester=3, section="B", name="ECE-Y2S3-B")
        db.session.add_all([class_cse, class_ece])
        db.session.commit()

        print("[SEED] Creating Staff Accounts...")
        # Staff 1: Prof. Alan Turing (Approved)
        user_turing = User(
            email="alan.turing@college.edu",
            role="staff",
            full_name="Alan Turing",
            is_approved=True
        )
        user_turing.set_password("StaffPass123!")
        db.session.add(user_turing)
        db.session.flush()

        staff_turing = StaffProfile(
            user_id=user_turing.id,
            staff_id="STAFF101",
            department="Computer Science",
            designation="Professor & HOD"
        )
        db.session.add(staff_turing)

        # Staff 2: Prof. Grace Hopper (Approved)
        user_hopper = User(
            email="grace.hopper@college.edu",
            role="staff",
            full_name="Grace Hopper",
            is_approved=True
        )
        user_hopper.set_password("StaffPass123!")
        db.session.add(user_hopper)
        db.session.flush()

        staff_hopper = StaffProfile(
            user_id=user_hopper.id,
            staff_id="STAFF102",
            department="Electronics & Computing",
            designation="Associate Professor"
        )
        db.session.add(staff_hopper)

        # Staff 3: Unapproved staff (For testing CLI approval)
        user_pending_staff = User(
            email="pending.staff@college.edu",
            role="staff",
            full_name="Dr. Pending Staff",
            is_approved=False
        )
        user_pending_staff.set_password("StaffPass123!")
        db.session.add(user_pending_staff)
        db.session.flush()

        staff_pending = StaffProfile(
            user_id=user_pending_staff.id,
            staff_id="STAFF103",
            department="Computer Science",
            designation="Assistant Professor"
        )
        db.session.add(staff_pending)
        db.session.commit()

        print("[SEED] Creating Classrooms with GPS Coordinates...")
        # Turing Lecture Hall (Bangalore College Campus sample coords: 12.9716, 77.5946)
        classroom_lh101 = Classroom(
            classroom_name="Turing Lecture Hall 101",
            building_name="Computer Science Block",
            room_number="CS-101",
            latitude=12.971600,
            longitude=77.594600,
            allowed_radius_meters=50.0,
            created_by_staff_id=staff_turing.id
        )
        classroom_lab204 = Classroom(
            classroom_name="Ada Lovelace AI Computing Lab",
            building_name="Advanced Technology Annex",
            room_number="TECH-204",
            latitude=12.972050,
            longitude=77.595100,
            allowed_radius_meters=45.0,
            created_by_staff_id=staff_turing.id
        )
        db.session.add_all([classroom_lh101, classroom_lab204])
        db.session.commit()

        print("[SEED] Creating Subjects...")
        sub_cloud = Subject(
            subject_code="CS501",
            subject_name="Distributed & Cloud Computing",
            class_id=class_cse.id,
            staff_id=staff_turing.id
        )
        sub_ai = Subject(
            subject_code="CS502",
            subject_name="Artificial Intelligence & Computer Vision",
            class_id=class_cse.id,
            staff_id=staff_turing.id
        )
        sub_embedded = Subject(
            subject_code="EC301",
            subject_name="Microcontrollers & Embedded Systems",
            class_id=class_ece.id,
            staff_id=staff_hopper.id
        )
        db.session.add_all([sub_cloud, sub_ai, sub_embedded])
        db.session.commit()

        print("[SEED] Creating Student Accounts and Biometric Enrolments...")
        students_data = [
            ("Alice Johnson", "alice.johnson@college.edu", "STU2026001", class_cse.id, True, True),
            ("Bob Smith", "bob.smith@college.edu", "STU2026002", class_cse.id, True, True),
            ("Charlie Brown", "charlie.brown@college.edu", "STU2026003", class_cse.id, True, True),
            ("Diana Prince", "diana.prince@college.edu", "STU2026004", class_cse.id, True, True),
            ("Evan Wright", "evan.wright@college.edu", "STU2026005", class_cse.id, False, False), # Pending approval
        ]

        student_objs = []
        for name, email, sid, cid, approved, face_enrolled in students_data:
            u = User(
                email=email,
                role="student",
                full_name=name,
                is_approved=approved
            )
            u.set_password("StudentPass123!")
            db.session.add(u)
            db.session.flush()

            now = datetime.now(timezone.utc)
            s = Student(
                user_id=u.id,
                student_id=sid,
                class_id=cid,
                face_enrolled=face_enrolled,
                face_enrolled_at=now if face_enrolled else None
            )
            db.session.add(s)
            db.session.flush()

            # Class enrollment
            enr = Enrollment(student_id=s.id, class_id=cid)
            db.session.add(enr)

            if face_enrolled:
                # Generate deterministic 128-d pseudo-embedding for testing
                np.random.seed(int(sid.replace("STU", "")))
                vec = np.random.randn(128).astype(np.float32)
                vec = (vec / np.linalg.norm(vec)).tolist()

                ft = FaceTemplate(
                    student_id=s.id,
                    model_name="sface_spatial_v1",
                    vector_dimension=128
                )
                ft.set_embedding(vec)
                db.session.add(ft)

            student_objs.append((s, approved))

        db.session.commit()

        print("[SEED] Generating Historical Attendance Sessions & Records...")
        now = datetime.now(timezone.utc)
        alice = Student.query.filter_by(student_id="STU2026001").first()
        bob = Student.query.filter_by(student_id="STU2026002").first()
        charlie = Student.query.filter_by(student_id="STU2026003").first()
        diana = Student.query.filter_by(student_id="STU2026004").first()

        # Create 10 lecture sessions held over recent weeks
        for i in range(10):
            session_date = now - timedelta(days=(12 - i))
            start_t = session_date.replace(hour=10, minute=0, second=0)
            end_t = session_date.replace(hour=11, minute=0, second=0)

            sess = AttendanceSession(
                subject_id=sub_cloud.id,
                class_id=class_cse.id,
                classroom_id=classroom_lh101.id,
                staff_id=staff_turing.id,
                start_time=start_t,
                end_time=end_t,
                refresh_interval_seconds=30,
                is_active=False
            )
            db.session.add(sess)
            db.session.flush()

            # Alice attends all 10 (100%)
            r1 = AttendanceRecord(
                student_id=alice.id,
                subject_id=sub_cloud.id,
                class_id=class_cse.id,
                session_id=sess.id,
                classroom_id=classroom_lh101.id,
                attendance_date=start_t.date(),
                marked_timestamp=start_t + timedelta(minutes=5),
                qr_verification_result="PASSED",
                location_verification_result="PASSED",
                face_verification_result="PASSED",
                final_status="PRESENT"
            )
            db.session.add(r1)

            # Bob attends 8 out of 10 (80%)
            if i not in (2, 7):
                r2 = AttendanceRecord(
                    student_id=bob.id,
                    subject_id=sub_cloud.id,
                    class_id=class_cse.id,
                    session_id=sess.id,
                    classroom_id=classroom_lh101.id,
                    attendance_date=start_t.date(),
                    marked_timestamp=start_t + timedelta(minutes=6),
                    qr_verification_result="PASSED",
                    location_verification_result="PASSED",
                    face_verification_result="PASSED",
                    final_status="PRESENT"
                )
                db.session.add(r2)

            # Charlie attends only 5 out of 10 (50% - low attendance alert!)
            if i in (0, 3, 5, 8, 9):
                r3 = AttendanceRecord(
                    student_id=charlie.id,
                    subject_id=sub_cloud.id,
                    class_id=class_cse.id,
                    session_id=sess.id,
                    classroom_id=classroom_lh101.id,
                    attendance_date=start_t.date(),
                    marked_timestamp=start_t + timedelta(minutes=8),
                    qr_verification_result="PASSED",
                    location_verification_result="PASSED",
                    face_verification_result="PASSED",
                    final_status="PRESENT"
                )
                db.session.add(r3)

            # Diana attends 9 out of 10 (90%)
            if i != 4:
                r4 = AttendanceRecord(
                    student_id=diana.id,
                    subject_id=sub_cloud.id,
                    class_id=class_cse.id,
                    session_id=sess.id,
                    classroom_id=classroom_lh101.id,
                    attendance_date=start_t.date(),
                    marked_timestamp=start_t + timedelta(minutes=7),
                    qr_verification_result="PASSED",
                    location_verification_result="PASSED",
                    face_verification_result="PASSED",
                    final_status="PRESENT"
                )
                db.session.add(r4)

        # Create one ACTIVE session today for immediate testing in the UI
        active_sess = AttendanceSession(
            subject_id=sub_cloud.id,
            class_id=class_cse.id,
            classroom_id=classroom_lh101.id,
            staff_id=staff_turing.id,
            start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(minutes=50),
            refresh_interval_seconds=30,
            is_active=True
        )
        db.session.add(active_sess)
        db.session.commit()

        print("[SEED] Creating Sample Suspicious Verification Events...")
        evt1 = VerificationEvent(
            student_id=bob.id,
            session_id=active_sess.id,
            subject_id=sub_cloud.id,
            class_id=class_cse.id,
            failure_category="LOCATION_OUT_OF_BOUNDS",
            details="Reported GPS distance 210.4m exceeds 50.0m radius (Accuracy: 15.0m)",
            client_ip="192.168.1.45",
            recorded_at=now - timedelta(minutes=8),
            is_reviewed=False
        )
        evt2 = VerificationEvent(
            student_id=charlie.id,
            session_id=active_sess.id,
            subject_id=sub_cloud.id,
            class_id=class_cse.id,
            failure_category="FACE_MISMATCH",
            details="Cosine similarity 0.41 fell below 0.65 threshold.",
            client_ip="192.168.1.88",
            recorded_at=now - timedelta(minutes=6),
            is_reviewed=False
        )
        evt3 = VerificationEvent(
            student_id=None,
            session_id=active_sess.id,
            subject_id=sub_cloud.id,
            class_id=class_cse.id,
            failure_category="EXPIRED_QR",
            details="Scanned token was 42 seconds older than refresh window.",
            client_ip="192.168.1.102",
            recorded_at=now - timedelta(minutes=4),
            is_reviewed=True,
            reviewed_by_staff_id=staff_turing.id,
            reviewed_at=now - timedelta(minutes=2)
        )
        db.session.add_all([evt1, evt2, evt3])
        db.session.commit()

        print("\n========================================================")
        print(" [SEED COMPLETE] SMART ATTENDANCE TEST DATA READY")
        print("========================================================")
        print(" STAFF ACCOUNTS:")
        print("   - Prof. Alan Turing : alan.turing@college.edu  / StaffPass123! (Approved)")
        print("   - Prof. Grace Hopper: grace.hopper@college.edu / StaffPass123! (Approved)")
        print("   - Dr. Pending Staff : pending.staff@college.edu/ StaffPass123! (Pending Approval)")
        print(" STUDENT ACCOUNTS:")
        print("   - Alice Johnson (STU2026001): alice.johnson@college.edu / StudentPass123! (100% Att)")
        print("   - Bob Smith     (STU2026002): bob.smith@college.edu     / StudentPass123! (80% Att)")
        print("   - Charlie Brown (STU2026003): charlie.brown@college.edu / StudentPass123! (50% Low Att)")
        print("   - Diana Prince  (STU2026004): diana.prince@college.edu  / StudentPass123! (90% Att)")
        print("   - Evan Wright   (STU2026005): evan.wright@college.edu   / StudentPass123! (Pending Approval)")
        print("========================================================\n")

if __name__ == "__main__":
    seed_database()
