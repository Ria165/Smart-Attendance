from functools import wraps
from flask import session as login_session, redirect, url_for, flash, request, abort, jsonify
from app import db
from app.models.user import User
from app.models.verification import AuditLog

def get_current_user():
    user_id = login_session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in login_session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        user = get_current_user()
        if not user:
            login_session.clear()
            flash("Session expired. Please log in again.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in login_session:
            flash("Staff login required.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        if login_session.get("role") != "staff":
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"status": "error", "message": "Access forbidden: Staff role required"}), 403
            abort(403)
        user = get_current_user()
        if not user:
            login_session.clear()
            flash("Session expired. Please log in again.", "warning")
            return redirect(url_for("auth.login"))
        if getattr(user, "is_rejected", False):
            login_session.clear()
            flash("Your account registration was not approved. Contact an authorized staff member.", "danger")
            return redirect(url_for("auth.login"))
        if not user.is_approved:
            flash("Your account is awaiting approval.", "warning")
            return redirect(url_for("auth.approval_pending"))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in login_session:
            flash("Student login required.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        if login_session.get("role") != "student":
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"status": "error", "message": "Access forbidden: Student role required"}), 403
            abort(403)
        user = get_current_user()
        if not user:
            login_session.clear()
            flash("Session expired. Please log in again.", "warning")
            return redirect(url_for("auth.login"))
        if getattr(user, "is_rejected", False):
            login_session.clear()
            flash("Your account registration was not approved. Contact an authorized staff member.", "danger")
            return redirect(url_for("auth.login"))
        if not user.is_approved:
            flash("Your account is awaiting approval.", "warning")
            return redirect(url_for("auth.approval_pending"))
        return f(*args, **kwargs)
    return decorated_function

def log_audit(action, entity_type, entity_id=None, details=None, user_id=None):
    try:
        if user_id is None:
            user_id = login_session.get("user_id")
        ip = request.remote_addr if request else "system"
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Suppress logging failures from interrupting primary transactions
        print(f"Audit log failed: {e}")
