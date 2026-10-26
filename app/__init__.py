import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from config import config_by_name

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
        
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["default"]))
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Register Jinja custom filters
    @app.template_filter("status_badge")
    def status_badge_filter(status):
        badges = {
            "PRESENT": "bg-success",
            "ABSENT": "bg-danger",
            "REJECTED_QR": "bg-warning text-dark",
            "LOCATION_FAILED": "bg-danger",
            "LOCATION_UNVERIFIED": "bg-warning text-dark",
            "FACE_MISMATCH": "bg-danger",
            "FACE_REVIEW_REQUIRED": "bg-info text-dark",
            "ALREADY_MARKED": "bg-secondary",
            "SESSION_NOT_ALLOWED": "bg-danger",
        }
        return badges.get(status, "bg-secondary")
    
    # Register Blueprints
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    from app.student.routes import student_bp
    from app.attendance.routes import attendance_bp
    from app.reports.routes import reports_bp
    
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(staff_bp, url_prefix="/staff")
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    
    # Context processor to safely expose login session to templates without naming collisions
    @app.context_processor
    def inject_login_session():
        from flask import session as login_session
        return dict(login_session=login_session)

    # Root route redirects based on session or landing
    @app.route("/")
    def index():
        from flask import session as login_session, redirect, url_for
        if "user_id" in login_session:
            role = login_session.get("role")
            if role == "staff":
                return redirect(url_for("staff.dashboard"))
            elif role == "student":
                return redirect(url_for("student.dashboard"))
        return redirect(url_for("auth.login"))
    
    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html", error=e), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html", error=e), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("errors/500.html", error=e), 500

    return app
