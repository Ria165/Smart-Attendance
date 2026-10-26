import math
from datetime import datetime, timezone
import calendar
from flask import current_app
from app import db
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.academic import Subject, Class, Enrollment
from app.models.user import Student, User

def calculate_student_statistics(student_id, subject_id, year, month):
    """
    Calculates monthly attendance metrics for an individual student in a specific subject:
    - Counts only active, non-cancelled sessions held in the requested calendar month.
    - Resolves duplicate attempts and approved corrections.
    - Evaluates attendance percentage and calculates additional sessions needed if below threshold.
    """
    threshold_percent = current_app.config.get("LOW_ATTENDANCE_THRESHOLD_PERCENT", 75.0)

    # Date range for the requested month
    _, last_day = calendar.monthrange(year, month)
    start_date = datetime(year, month, 1, 0, 0, 0)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    subject = db.session.get(Subject, subject_id)
    student = db.session.get(Student, student_id)
    if not subject or not student:
        return {
            "student_id": student.student_id if student else "",
            "student_name": student.user.full_name if student else "",
            "subject_code": subject.subject_code if subject else "",
            "subject_name": subject.subject_name if subject else "",
            "sessions_held": 0,
            "present_count": 0,
            "absent_count": 0,
            "percentage": None,
            "percentage_display": "N/A",
            "is_low": False,
            "sessions_needed": 0
        }

    # Verify student is enrolled in the subject's class
    is_enrolled = Enrollment.query.filter_by(student_id=student.id, class_id=subject.class_id).first()
    if not is_enrolled:
        return {
            "student_id": student.student_id,
            "student_name": student.user.full_name,
            "subject_code": subject.subject_code,
            "subject_name": subject.subject_name,
            "sessions_held": 0,
            "present_count": 0,
            "absent_count": 0,
            "percentage": None,
            "percentage_display": "Not Enrolled",
            "is_low": False,
            "sessions_needed": 0
        }

    # Query valid, non-cancelled sessions held for this subject in the given month
    eligible_sessions = AttendanceSession.query.filter(
        AttendanceSession.subject_id == subject_id,
        AttendanceSession.is_cancelled == False,
        AttendanceSession.start_time >= start_date,
        AttendanceSession.start_time <= end_date
    ).all()
    sessions_held = len(eligible_sessions)
    eligible_session_ids = [s.id for s in eligible_sessions]

    if sessions_held == 0:
        return {
            "student_id": student.student_id,
            "student_name": student.user.full_name,
            "subject_code": subject.subject_code,
            "subject_name": subject.subject_name,
            "sessions_held": 0,
            "present_count": 0,
            "absent_count": 0,
            "percentage": None,
            "percentage_display": "N/A (No Sessions)",
            "is_low": False,
            "sessions_needed": 0
        }

    # Query distinct attendance records marked as PRESENT for this student
    present_records_count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.subject_id == subject_id,
        AttendanceRecord.session_id.in_(eligible_session_ids),
        AttendanceRecord.final_status == "PRESENT"
    ).count()

    absent_count = max(0, sessions_held - present_records_count)
    percentage = round((present_records_count / sessions_held) * 100.0, 1)
    is_low = percentage < threshold_percent

    # Calculate additional sessions needed to reach threshold:
    # (P + X) / (T + X) >= r  =>  X >= (r*T - P) / (1 - r)
    sessions_needed = 0
    if is_low and percentage < threshold_percent:
        r = threshold_percent / 100.0
        if r < 1.0:
            numerator = (r * sessions_held) - present_records_count
            if numerator > 0:
                sessions_needed = int(math.ceil(numerator / (1.0 - r)))

    return {
        "student_id": student.student_id,
        "student_name": student.user.full_name,
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "sessions_held": sessions_held,
        "present_count": present_records_count,
        "absent_count": absent_count,
        "percentage": percentage,
        "percentage_display": f"{percentage:.1f}%",
        "is_low": is_low,
        "sessions_needed": sessions_needed
    }


def generate_monthly_report_data(subject_id, year, month):
    """
    Generates structured report dataset for an entire class/subject for a specific month.
    """
    subject = db.session.get(Subject, subject_id)
    if not subject:
        return None

    academic_class = subject.assigned_class
    staff = subject.staff

    # Get all enrolled students in this class
    enrollments = Enrollment.query.filter_by(class_id=subject.class_id).all()
    students = [e.student for e in enrollments]

    student_rows = []
    total_present_sum = 0
    total_held_sum = 0
    low_attendance_students = []

    for s in students:
        stats = calculate_student_statistics(s.id, subject.id, year, month)
        student_rows.append(stats)
        if stats["percentage"] is not None:
            total_present_sum += stats["present_count"]
            total_held_sum += stats["sessions_held"]
            if stats["is_low"]:
                low_attendance_students.append(stats)

    # Class average percentage
    class_average = round((total_present_sum / total_held_sum) * 100.0, 1) if total_held_sum > 0 else None
    month_name = calendar.month_name[month]

    # Total distinct sessions conducted
    _, last_day = calendar.monthrange(year, month)
    total_sessions_count = AttendanceSession.query.filter(
        AttendanceSession.subject_id == subject.id,
        AttendanceSession.is_cancelled == False,
        AttendanceSession.start_time >= datetime(year, month, 1),
        AttendanceSession.start_time <= datetime(year, month, last_day, 23, 59, 59)
    ).count()

    threshold = current_app.config.get("LOW_ATTENDANCE_THRESHOLD_PERCENT", 75.0)

    return {
        "subject": subject,
        "class": academic_class,
        "staff": staff,
        "year": year,
        "month": month,
        "month_name": month_name,
        "generated_at": datetime.now(timezone.utc),
        "total_enrolled": len(students),
        "total_sessions": total_sessions_count,
        "class_average": class_average,
        "threshold": threshold,
        "students": sorted(student_rows, key=lambda x: x["student_id"]),
        "low_attendance_students": low_attendance_students,
        "above_threshold_count": len(student_rows) - len(low_attendance_students),
        "below_threshold_count": len(low_attendance_students)
    }
