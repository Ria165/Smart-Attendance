import io
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, Response
from app import db
from app.models.academic import Subject
from app.auth.utils import staff_required, get_current_user, log_audit
from app.reports.generator import generate_monthly_report_data
from app.reports.excel_export import build_excel_attendance_report
from app.reports.pdf_export import build_pdf_attendance_report

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/")
@staff_required
def index():
    user = get_current_user()
    staff = user.staff_profile

    subjects = Subject.query.filter_by(staff_id=staff.id).order_by(Subject.subject_code).all()

    now = datetime.now(timezone.utc)
    selected_subject_id = request.args.get("subject_id", type=int)
    selected_year = request.args.get("year", type=int) or now.year
    selected_month = request.args.get("month", type=int) or now.month

    report_data = None
    if selected_subject_id:
        target_subject = db.session.get(Subject, selected_subject_id)
        if not target_subject or target_subject.staff_id != staff.id:
            flash("Unauthorized: You cannot access reports for subjects assigned to other faculty.", "danger")
            return redirect(url_for("reports.index"))

        report_data = generate_monthly_report_data(selected_subject_id, selected_year, selected_month)

    available_years = [now.year - 1, now.year, now.year + 1]

    return render_template(
        "staff/reports.html",
        subjects=subjects,
        selected_subject_id=selected_subject_id,
        selected_year=selected_year,
        selected_month=selected_month,
        report_data=report_data,
        available_years=available_years
    )


@reports_bp.route("/export/excel")
@staff_required
def export_excel():
    user = get_current_user()
    staff = user.staff_profile

    subject_id = request.args.get("subject_id", type=int)
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if not subject_id or not year or not month:
        flash("Subject, year, and month are required to generate export.", "danger")
        return redirect(url_for("reports.index"))

    subject = db.session.get(Subject, subject_id)
    if not subject or subject.staff_id != staff.id:
        flash("Unauthorized subject report access.", "danger")
        return redirect(url_for("reports.index"))

    report_data = generate_monthly_report_data(subject_id, year, month)
    excel_bytes = build_excel_attendance_report(report_data)

    filename = f"Attendance_Report_{subject.subject_code}_{year}_{month:02d}.xlsx"
    log_audit("REPORT_EXPORT_EXCEL", "reports", subject_id, f"Excel exported for {subject.subject_code} {year}-{month:02d}", user.id)

    return Response(
        excel_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


@reports_bp.route("/export/pdf")
@staff_required
def export_pdf():
    user = get_current_user()
    staff = user.staff_profile

    subject_id = request.args.get("subject_id", type=int)
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if not subject_id or not year or not month:
        flash("Subject, year, and month are required to generate export.", "danger")
        return redirect(url_for("reports.index"))

    subject = db.session.get(Subject, subject_id)
    if not subject or subject.staff_id != staff.id:
        flash("Unauthorized subject report access.", "danger")
        return redirect(url_for("reports.index"))

    report_data = generate_monthly_report_data(subject_id, year, month)
    pdf_bytes = build_pdf_attendance_report(report_data)

    filename = f"Attendance_Report_{subject.subject_code}_{year}_{month:02d}.pdf"
    log_audit("REPORT_EXPORT_PDF", "reports", subject_id, f"PDF exported for {subject.subject_code} {year}-{month:02d}", user.id)

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )
