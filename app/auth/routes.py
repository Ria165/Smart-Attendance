from flask import Blueprint, render_template, redirect, url_for, flash, request, session as login_session
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models.user import User, Student, StaffProfile
from app.models.academic import Class, Enrollment
from app.auth.utils import login_required, log_audit, get_current_user

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and "user_id" in login_session:
        role = login_session.get("role")
        if role == "staff":
            return redirect(url_for("staff.dashboard"))
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or request.form.get("email") or "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip().lower()

        if not identifier or not password or role not in ("staff", "student"):
            flash("Please provide user ID or email, password, and select your role.", "danger")
            return render_template("auth/login.html")

        try:
            # 1. Match by email address
            user = User.query.filter_by(email=identifier.lower(), role=role).first()

            # 2. Match by Student ID if role is student
            if not user and role == "student":
                student = Student.query.filter_by(student_id=identifier.upper()).first()
                if student and student.user:
                    user = student.user

            # 3. Match by Staff ID if role is staff
            if not user and role == "staff":
                staff_prof = StaffProfile.query.filter_by(staff_id=identifier.upper()).first()
                if staff_prof and staff_prof.user:
                    user = staff_prof.user

            # Authenticate credentials
            if not user or not user.check_password(password):
                flash("Incorrect user ID or password.", "danger")
                return render_template("auth/login.html")

            # Check if account was rejected
            if getattr(user, "is_rejected", False):
                flash("Your account registration was not approved. Contact an authorized staff member.", "danger")
                return render_template("auth/login.html")

            # Check if account is still awaiting approval
            if not user.is_approved:
                login_session["pending_user_id"] = user.id
                login_session["pending_role"] = user.role
                flash("Your account is awaiting approval.", "warning")
                return redirect(url_for("auth.approval_pending"))

            # Successful Authentication & Approved Status
            login_session.clear()
            login_session["user_id"] = user.id
            login_session["role"] = user.role
            login_session["full_name"] = user.full_name
            login_session["email"] = user.email

            if user.role == "staff" and user.staff_profile:
                login_session["staff_id"] = user.staff_profile.id
                login_session["staff_code"] = user.staff_profile.staff_id
                log_audit("STAFF_LOGIN", "users", user.id, f"Staff logged in: {user.email}", user.id)
                flash(f"Welcome back, Prof. {user.full_name}!", "success")
                next_url = request.args.get("next")
                return redirect(next_url or url_for("staff.dashboard"))

            elif user.role == "student" and user.student_profile:
                login_session["student_pk"] = user.student_profile.id
                login_session["student_id"] = user.student_profile.student_id
                log_audit("STUDENT_LOGIN", "users", user.id, f"Student logged in: {user.email}", user.id)
                flash(f"Welcome, {user.full_name}!", "success")
                next_url = request.args.get("next")
                return redirect(next_url or url_for("student.dashboard"))

            flash("Profile setup incomplete. Please contact faculty.", "warning")
            return redirect(url_for("auth.login"))

        except SQLAlchemyError as db_err:
            db.session.rollback()
            flash("A database connection error occurred. Please try again later.", "danger")
            return render_template("auth/login.html")
        except Exception:
            flash("A server error occurred. Please try again later.", "danger")
            return render_template("auth/login.html")

    return render_template("auth/login.html")


@auth_bp.route("/register/staff", methods=["GET", "POST"])
def register_staff():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        staff_id = request.form.get("staff_id", "").strip().upper()
        department = request.form.get("department", "").strip()
        designation = request.form.get("designation", "").strip() or "Faculty"

        if not full_name or not email or not password or not staff_id or not department:
            flash("All fields are required.", "danger")
            return render_template("auth/register_staff.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register_staff.html")

        if StaffProfile.query.filter_by(staff_id=staff_id).first():
            flash("A staff member with this Staff ID is already registered.", "danger")
            return render_template("auth/register_staff.html")

        user = User(
            email=email,
            role="staff",
            full_name=full_name,
            is_approved=False,
            is_rejected=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        staff_profile = StaffProfile(
            user_id=user.id,
            staff_id=staff_id,
            department=department,
            designation=designation
        )
        db.session.add(staff_profile)
        db.session.commit()

        log_audit("STAFF_REGISTERED", "users", user.id, f"Staff registered: {email} (ID: {staff_id})", user.id)
        flash("Registration submitted! Your staff account is awaiting approval by an authorized faculty member or through the setup command.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_staff.html")


@auth_bp.route("/register/student", methods=["GET", "POST"])
def register_student():
    classes = Class.query.order_by(Class.name).all()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        student_id = request.form.get("student_id", "").strip().upper()
        class_id = request.form.get("class_id")

        if not full_name or not email or not password or not student_id or not class_id:
            flash("All fields are required.", "danger")
            return render_template("auth/register_student.html", classes=classes)

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register_student.html", classes=classes)

        if Student.query.filter_by(student_id=student_id).first():
            flash("A student with this Student ID is already registered.", "danger")
            return render_template("auth/register_student.html", classes=classes)

        selected_class = db.session.get(Class, class_id)
        if not selected_class:
            flash("Invalid class selection.", "danger")
            return render_template("auth/register_student.html", classes=classes)

        user = User(
            email=email,
            role="student",
            full_name=full_name,
            is_approved=False,
            is_rejected=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        student = Student(
            user_id=user.id,
            student_id=student_id,
            class_id=selected_class.id,
            face_enrolled=False
        )
        db.session.add(student)
        db.session.flush()

        enrollment = Enrollment(
            student_id=student.id,
            class_id=selected_class.id
        )
        db.session.add(enrollment)
        db.session.commit()

        log_audit("STUDENT_REGISTERED", "users", user.id, f"Student registered: {email} (ID: {student_id})", user.id)
        flash("Registration submitted! Your student account is awaiting approval by your department faculty.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_student.html", classes=classes)


@auth_bp.route("/approval-pending")
def approval_pending():
    return render_template("auth/approval_pending.html")


@auth_bp.route("/logout")
def logout():
    user_id = login_session.get("user_id")
    if user_id:
        log_audit("LOGOUT", "users", user_id, "User logged out", user_id)
    login_session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for("auth.login"))
