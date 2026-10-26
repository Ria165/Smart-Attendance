import os
import sys
import argparse
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models.academic import Subject
from app.reports.generator import generate_monthly_report_data
from app.reports.excel_export import build_excel_attendance_report
from app.reports.pdf_export import build_pdf_attendance_report

def run_monthly_reports(app, year=None, month=None, output_dir=None):
    with app.app_context():
        now = datetime.now(timezone.utc)
        if year is None:
            # Default to previous month if run at start of new month
            if now.month == 1:
                year = now.year - 1
                month = 12
            else:
                year = now.year
                month = now.month - 1

        if output_dir is None:
            output_dir = os.path.join(app.config.get("BASE_DIR", os.getcwd()), "exports", f"{year}_{month:02d}")

        os.makedirs(output_dir, exist_ok=True)
        print(f"\n[CRON / SCHEDULER] Generating Monthly Attendance Reports for {year}-{month:02d}")
        print(f"[DESTINATION] {output_dir}")

        subjects = Subject.query.all()
        count = 0

        for sub in subjects:
            report_data = generate_monthly_report_data(sub.id, year, month)
            if not report_data:
                continue

            # Generate Excel
            excel_bytes = build_excel_attendance_report(report_data)
            excel_path = os.path.join(output_dir, f"Attendance_{sub.subject_code}_{sub.assigned_class.name}_{year}_{month:02d}.xlsx")
            with open(excel_path, "wb") as f:
                f.write(excel_bytes)

            # Generate PDF
            pdf_bytes = build_pdf_attendance_report(report_data)
            pdf_path = os.path.join(output_dir, f"Attendance_{sub.subject_code}_{sub.assigned_class.name}_{year}_{month:02d}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            print(f"  -> Generated: {sub.subject_code} ({sub.assigned_class.name}) | Enrolled: {report_data['total_enrolled']} | Held: {report_data['total_sessions']}")
            count += 1

        print(f"[COMPLETED] Successfully exported reports for {count} subjects.\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Scheduled Monthly Attendance Report Generator")
    parser.add_argument("--year", type=int, help="Target calendar year (default: previous month)")
    parser.add_argument("--month", type=int, help="Target calendar month 1-12 (default: previous month)")
    parser.add_argument("--out", type=str, help="Output destination folder")

    args = parser.parse_args()
    flask_app = create_app()
    run_monthly_reports(flask_app, year=args.year, month=args.month, output_dir=args.out)
