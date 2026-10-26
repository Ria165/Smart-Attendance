import sys
import os
import argparse
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models.user import User, StaffProfile
from app.models.verification import AuditLog

def list_staff(app):
    with app.app_context():
        staff_users = User.query.filter_by(role="staff").order_by(User.id.asc()).all()
        print("\n=== REGISTERED STAFF ACCOUNTS ===")
        print(f"{'ID':<6} {'Name':<22} {'Email':<30} {'Staff ID':<12} {'Status':<12}")
        print("-" * 86)
        for u in staff_users:
            profile = u.staff_profile
            sid = profile.staff_id if profile else "N/A"
            if getattr(u, "is_rejected", False):
                status = "REJECTED"
            elif u.is_approved:
                status = "APPROVED"
            else:
                status = "PENDING"
            print(f"{u.id:<6} {u.full_name:<22} {u.email:<30} {sid:<12} {status:<12}")
        print("-" * 86 + "\n")

def approve_staff_account(app, identifier):
    """
    Authorizes an existing pending staff account by email, staff ID, or numeric user ID.
    Never elevates student accounts to staff or approves arbitrary roles.
    """
    with app.app_context():
        ident = identifier.strip() if identifier else ""
        if not ident:
            print("[ERROR] An identifier (email or Staff ID) is required.")
            return False

        # Match by email
        user = User.query.filter(
            (User.email == ident.lower()) & (User.role == "staff")
        ).first()

        # Match by Staff ID
        if not user:
            profile = StaffProfile.query.filter_by(staff_id=ident.upper()).first()
            if profile and profile.user:
                user = profile.user

        # Match by User ID
        if not user and ident.isdigit():
            user = db.session.get(User, int(ident))
            if user and user.role != "staff":
                print(f"[ERROR] User ID {ident} is a student account. Only faculty/staff accounts can be approved via this command.")
                return False

        if not user or user.role != "staff":
            print(f"[ERROR] No staff account found matching '{ident}'.")
            return False

        if user.is_approved and not getattr(user, "is_rejected", False):
            print(f"[INFO] Staff account '{user.email}' is already approved and active.")
            return True

        user.is_approved = True
        user.is_rejected = False
        user.approved_at = datetime.now(timezone.utc)

        log = AuditLog(
            user_id=user.id,
            action="STAFF_CLI_APPROVED",
            entity_type="users",
            entity_id=user.id,
            details=f"Staff account approved via setup CLI by system administrator/operator",
            ip_address="127.0.0.1"
        )
        db.session.add(log)
        db.session.commit()

        sid = user.staff_profile.staff_id if user.staff_profile else "N/A"
        print(f"\n[SUCCESS] Staff account '{user.full_name}' ({user.email}, ID: {sid}) is now APPROVED!")
        print(f"-> This staff member can now log in at http://127.0.0.1:5000/auth/login and access the Faculty Dashboard.\n")
        return True

def setup_or_create_staff(app, full_name, email, password, staff_id, department, designation="Faculty"):
    """
    Creates a new approved staff account OR authorizes an existing pending staff account.
    Validates all inputs, securely hashes passwords, and logs audit entries.
    """
    with app.app_context():
        email = email.strip().lower() if email else ""
        staff_id = staff_id.strip().upper() if staff_id else ""
        full_name = full_name.strip() if full_name else ""
        department = department.strip() if department else "General"
        designation = designation.strip() if designation else "Faculty"

        if not email or "@" not in email:
            print("[ERROR] A valid college email address is required.")
            return False
        if not staff_id:
            print("[ERROR] A Staff ID is required.")
            return False
        if not full_name:
            print("[ERROR] Full name is required.")
            return False

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            if existing_user.role != "staff":
                print(f"[ERROR] User '{email}' is registered as a student. Role conflict.")
                return False

            # Existing staff account found -> authorize and update
            print(f"[INFO] Existing staff account found for '{email}'. Authorizing account...")
            existing_user.full_name = full_name or existing_user.full_name
            existing_user.is_approved = True
            existing_user.is_rejected = False
            existing_user.approved_at = datetime.now(timezone.utc)

            if password:
                existing_user.set_password(password)

            if not existing_user.staff_profile:
                profile = StaffProfile(
                    user_id=existing_user.id,
                    staff_id=staff_id,
                    department=department,
                    designation=designation
                )
                db.session.add(profile)
            else:
                existing_user.staff_profile.staff_id = staff_id or existing_user.staff_profile.staff_id
                existing_user.staff_profile.department = department or existing_user.staff_profile.department
                existing_user.staff_profile.designation = designation or existing_user.staff_profile.designation

            log = AuditLog(
                user_id=existing_user.id,
                action="STAFF_CLI_APPROVED",
                entity_type="users",
                entity_id=existing_user.id,
                details=f"Staff account authorized via CLI setup: {staff_id}",
                ip_address="127.0.0.1"
            )
            db.session.add(log)
            db.session.commit()

            print(f"\n[SUCCESS] Existing staff account '{existing_user.full_name}' ({email}) has been successfully AUTHORIZED!")
            print("-> You can now log in at http://127.0.0.1:5000/auth/login and approve pending students.\n")
            return True

        # Check if staff_id is taken
        existing_profile = StaffProfile.query.filter_by(staff_id=staff_id).first()
        if existing_profile:
            print(f"[ERROR] Staff ID '{staff_id}' is already registered to user '{existing_profile.user.email}'.")
            return False

        if not password or len(password) < 6:
            print("[ERROR] Password must be at least 6 characters.")
            return False

        # Create new approved staff user
        user = User(
            email=email,
            role="staff",
            full_name=full_name,
            is_approved=True,
            is_rejected=False,
            approved_at=datetime.now(timezone.utc)
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        profile = StaffProfile(
            user_id=user.id,
            staff_id=staff_id,
            department=department,
            designation=designation
        )
        db.session.add(profile)

        log = AuditLog(
            user_id=user.id,
            action="STAFF_CLI_CREATED",
            entity_type="users",
            entity_id=user.id,
            details=f"Authorized staff created directly via setup CLI: {staff_id}",
            ip_address="127.0.0.1"
        )
        db.session.add(log)
        db.session.commit()

        print(f"\n[SUCCESS] New authorized staff account '{full_name}' ({staff_id}) created successfully!")
        print("-> You can now log in at http://127.0.0.1:5000/auth/login and approve pending students.\n")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Attendance - Secure Staff Account Approval CLI")
    parser.add_argument("--list", action="store_true", help="List all staff accounts and their approval status")
    parser.add_argument("--approve", metavar="IDENTIFIER", help="Approve staff account by Email, Staff ID, or User ID")
    parser.add_argument("--create", action="store_true", help="Create or authorize a staff member")
    parser.add_argument("--name", help="Staff full name")
    parser.add_argument("--email", help="Staff college email")
    parser.add_argument("--password", help="Staff password")
    parser.add_argument("--staff-id", help="Staff identification ID (e.g. STAFF01)")
    parser.add_argument("--dept", help="Department (e.g. Computer Science)")
    parser.add_argument("--designation", default="Faculty", help="Designation (default: Faculty)")

    args = parser.parse_args()
    flask_app = create_app()

    if args.list:
        list_staff(flask_app)
    elif args.approve:
        approve_staff_account(flask_app, args.approve)
    elif args.create:
        if args.email:
            name = args.name or input("Full Name: ")
            email = args.email
            sid = args.staff_id or input("Staff ID: ")
            dept = args.dept or input("Department: ")
            pw = args.password or input("Password: ")
            setup_or_create_staff(flask_app, name, email, pw, sid, dept, args.designation)
        else:
            print("\n=== CREATE / AUTHORIZE FACULTY ACCOUNT ===")
            name = input("Full Name: ")
            email = input("College Email: ")
            sid = input("Staff ID (e.g. STAFF01): ")
            dept = input("Department (e.g. Computer Science): ")
            desig = input("Designation [Faculty]: ") or "Faculty"
            import getpass
            pw = getpass.getpass("Password: ")
            setup_or_create_staff(flask_app, name, email, pw, sid, dept, desig)
    else:
        parser.print_help()
