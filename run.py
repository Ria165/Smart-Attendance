import os
import click
from app import create_app, db
from app.models.user import User, StaffProfile
from app.models.verification import AuditLog
from scripts.seed_data import seed_database
from scripts.approve_staff import approve_staff_account, list_staff, setup_or_create_staff
from scripts.generate_monthly_reports import run_monthly_reports

app = create_app(os.environ.get("FLASK_ENV", "development"))

@app.cli.command("seed-db")
def seed_db_command():
    """Seed the database with initial classrooms, faculty, students and sessions."""
    seed_database()

@app.cli.command("create-staff")
@click.option("--name", prompt="Full Name", help="Staff full name", required=False)
@click.option("--email", prompt="College Email", help="Staff college email", required=False)
@click.option("--staff-id", prompt="Staff Identification ID (e.g. STAFF01)", help="Staff identification ID", required=False)
@click.option("--dept", prompt="Department (e.g. Computer Science)", default="Computer Science", help="Department", required=False)
@click.option("--designation", prompt="Designation", default="Faculty", help="Designation", required=False)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Staff login password", required=False)
def create_staff_command(name, email, staff_id, dept, designation, password):
    """Securely create an authorized faculty account or authorize an existing pending staff account."""
    setup_or_create_staff(
        app,
        full_name=name,
        email=email,
        password=password,
        staff_id=staff_id,
        department=dept,
        designation=designation
    )

@app.cli.command("approve-staff")
@click.argument("identifier", required=False)
def approve_staff_command(identifier):
    """Approve an existing pending staff account by email, Staff ID, or User ID."""
    if not identifier:
        identifier = click.prompt("Enter staff email or Staff ID to approve")
    approve_staff_account(app, identifier)

@app.cli.command("list-staff")
def list_staff_command():
    """List all registered staff accounts and their approval status."""
    list_staff(app)

@app.cli.command("generate-reports")
@click.option("--year", type=int, default=None, help="Target calendar year")
@click.option("--month", type=int, default=None, help="Target calendar month 1-12")
@click.option("--out", type=str, default=None, help="Output destination directory")
def generate_reports_command(year, month, out):
    """Generate scheduled monthly attendance PDF and Excel reports."""
    run_monthly_reports(app, year, month, out)

if __name__ == "__main__":
    import sys
    from scripts.generate_ssl_cert import generate_self_signed_cert, get_local_ip

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    local_ip = get_local_ip()

    # Determine if HTTPS should be enabled (default: True for mobile camera/secure context)
    use_http_flag = "--http" in sys.argv or os.environ.get("ENABLE_HTTPS", "1").lower() in ("0", "false", "no")
    use_https = not use_http_flag

    ssl_context = None
    if use_https:
        cert_path = os.path.join(os.path.dirname(__file__), "cert.pem")
        key_path = os.path.join(os.path.dirname(__file__), "key.pem")
        if not (os.path.exists(cert_path) and os.path.exists(key_path)):
            generate_self_signed_cert(cert_path, key_path)
        ssl_context = (cert_path, key_path)

        print("\n" + "=" * 65)
        print("  SMART ATTENDANCE SYSTEM - SECURE MOBILE SERVER (HTTPS)")
        print("=" * 65)
        print(f"  * Mobile Phone URL (Android Chrome): https://{local_ip}:{port}/")
        print(f"  * Localhost URL:                    https://localhost:{port}/")
        print("=" * 65)
        print("  [ANDROID PHONE ACCESS INSTRUCTIONS]:")
        print(f"  1. Ensure phone is on the same Wi-Fi / network ({local_ip})")
        print(f"  2. Open Chrome on Android and visit: https://{local_ip}:{port}/")
        print("  3. When Chrome displays 'Your connection is not private':")
        print("     Tap 'Advanced' -> Tap 'Proceed to ... (unsafe)'")
        print("  4. Chrome will now grant full camera & biometric access!")
        print("=" * 65 + "\n")
    else:
        print("\n" + "=" * 65)
        print("  SMART ATTENDANCE SYSTEM - HTTP MODE (Insecure Context)")
        print(f"  * URL: http://{local_ip}:{port}/")
        print("  * Warning: Mobile Chrome blocks camera access on HTTP.")
        print("    Run with HTTPS (default) or configure chrome://flags.")
        print("=" * 65 + "\n")

    app.run(host=host, port=port, ssl_context=ssl_context, debug=True)