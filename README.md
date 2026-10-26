# Smart Attendance System
### Anti-Proxy College Classroom Attendance Using Dynamic QR, Face Recognition & GPS Verification

A production-grade, secure, responsive full-stack web application designed for higher education institutions to eliminate proxy attendance. The system enforces multi-factor verification: an unpredictable short-lived dynamic QR code, authoritative server-side Haversine GPS location verification, and 128-dimensional facial biometric embedding verification.

---

## 1. Key Features & Architecture

```
                  +-----------------------------------+
                  |        Student Mobile Device      |
                  +-----------------------------------+
                                    |
          1. Scan Dynamic QR Code   |  (Refreshes every 30 seconds)
                                    v
                  +-----------------------------------+
                  |    Server-Side QR Token Check     |
                  |  - Expiration & Replay Leeway     |
                  |  - Class Enrollment Eligibility   |
                  +-----------------------------------+
                                    |
          2. Browser GPS Geolocation|  (Haversine Distance <= Configured Radius)
                                    v
                  +-----------------------------------+
                  |  Server-Side Location Verifier    |
                  |  - Distance Calculation (m)       |
                  |  - Accuracy Tolerance Evaluation  |
                  +-----------------------------------+
                                    |
          3. Camera Face Capture    |  (128-d Normalized Embedding Vector)
                                    v
                  +-----------------------------------+
                  |  Biometric Face Verification      |
                  |  - Cosine Similarity Matching     |
                  |  - Passive Liveness Check         |
                  +-----------------------------------+
                                    |
                                    v
                  +-----------------------------------+
                  | Final Database Attendance Decision|
                  | [PRESENT / REJECTED_QR /          |
                  |  LOCATION_FAILED / FACE_MISMATCH] |
                  +-----------------------------------+
```

- **Exactly Two User Roles:** **Staff** and **Student**. No admin role or dashboard.
- **Initial Setup CLI:** Staff approval is managed through an institutional CLI command (`py scripts/approve_staff.py` or `flask approve-staff <email>`).
- **Student Approval Workflow:** Faculty review student account requests inside the staff dashboard.
- **Dynamic QR Generation:** Cryptographically generated unpredictable tokens (`secrets` module + SHA-256 hash). Dynamic countdown timer and real-time projector mode.
- **GPS Location Geofencing:** Leaflet.js interactive classroom location picker + "Use My Current Location" button. Server independently calculates great-circle Haversine distance.
- **Facial Biometric Matching:** Normalized 128-dimensional facial feature embeddings compared with cosine similarity. Raw photographs are not retained.
- **Suspicious Attempt Alerts:** Automated logging of anomalies (expired QR, location out of bounds, face mismatch) for faculty review.
- **Audit Logging & Manual Correction:** Manual attendance adjustments require explicit justification and are permanently recorded in institutional audit logs.
- **Automated Monthly Reports:**
  - Formula: $\text{Attendance \%} = \left(\frac{\text{Present Sessions}}{\text{Total Scheduled Eligible Sessions}}\right) \times 100$
  - Low-attendance alerts ($< 75\%$) with mathematical consecutive sessions needed planning estimate.
  - Interactive web reports, openpyxl Excel exports, and ReportLab landscape print-ready PDF exports.
  - Scheduled monthly batch report generator CLI (`py scripts/generate_monthly_reports.py`).

---

## 2. Technology Stack

- **Backend:** Python 3.10+, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-WTF (CSRF Protection)
- **Database:** MySQL (Primary in production via `mysql+pymysql`), SQLite (zero-config local development and testing)
- **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons, Leaflet.js, OpenStreetMap, html5-qrcode
- **Computer Vision & Biometrics:** OpenCV / NumPy spatial gradient orientation vectors (128-d L2-normalized embeddings), Pillow
- **Reporting:** Pandas, OpenPyXL (Excel), ReportLab (PDF)

---

## 3. Installation & Setup Instructions

### Prerequisites
- Python 3.10 or later
- (Optional) MySQL Server 8.0+ (SQLite fallback is enabled by default for rapid development)

### Step 1: Clone or Navigate to the Project
```bash
cd smart-attendance
```

### Step 2: Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Environment Configuration
Copy the example environment file:
```bash
cp .env.example .env
```
To configure MySQL, edit `.env`:
```ini
DATABASE_URL=mysql+pymysql://root:yourpassword@localhost:3306/smart_attendance
SECRET_KEY=generate-a-strong-random-key-here
LOW_ATTENDANCE_THRESHOLD_PERCENT=75.0
```
*(If `DATABASE_URL` is commented out or set to SQLite, the system automatically uses a local `smart_attendance.db` SQLite database).*

---

## 4. Database Seeding & Initial Accounts

Run the database seeder to create sample academic classes, classrooms, faculty, students, and 10 historical lectures with varying attendance percentages:

```bash
python scripts/seed_data.py
```

### Seeded Test Credentials

| Role | Account | Status / Info |
| :--- | :--- | :--- |
| Staff | `alan.turing@college.edu` | Approved (HOD, CS Block) |
| Staff | `grace.hopper@college.edu` | Approved (Associate Prof) |
| Staff | `pending.staff@college.edu` | Pending (For testing CLI approval) |
| Student | `alice.johnson@college.edu` | Approved (STU2026001) |
| Student | `bob.smith@college.edu` | Approved (STU2026002) |
| Student | `charlie.brown@college.edu` | Approved (STU2026003) |
| Student | `diana.prince@college.edu` | Approved (STU2026004) |
| Student | `evan.wright@college.edu` | Pending Faculty Approval (STU2026005) |
---

## 5. Staff Account Approval Workflow (CLI)

Since the system intentionally excludes an administrative dashboard, staff authorization is performed via secure server commands:

### List all staff accounts:
```bash
python scripts/approve_staff.py --list
# or
flask list-staff
```

### Approve a staff account:
```bash
python scripts/approve_staff.py --approve pending.staff@college.edu
# or by staff ID:
python scripts/approve_staff.py --approve STAFF103
# or via flask CLI:
flask approve-staff pending.staff@college.edu
```

### Directly create a pre-approved faculty member:
```bash
python scripts/approve_staff.py --create --name "Dr. Ada Lovelace" --email "ada.lovelace@college.edu" --password "<CHOOSE_A_PASSWORD>" --staff-id "STAFF104" --dept "Computer Science"
```

---

## 6. Running the Application

Start the Flask development server:
```bash
python run.py
```
Open your browser at `http://127.0.0.1:5000`.

- **Faculty Access:** Log in using a seeded staff account and the password configured for that account.
- **Student Access:** Log in using a seeded student account and the password configured for that account.

---

## 7. Monthly Reports & Scheduled Automation

### On-Demand Generation
Faculty can navigate to **Monthly Reports** in the navigation bar, select a subject and month, view analytics, and click **Export Excel (.xlsx)** or **Download Official PDF**.

### Automated Scheduled Generation (Cron / Task Scheduler)
Reports can be automatically archived at the close of every academic month:
```bash
python scripts/generate_monthly_reports.py --year 2026 --month 10
```
Reports are saved to `exports/YYYY_MM/` in both `.xlsx` and `.pdf` formats.

#### Linux/macOS Cron configuration (Runs on 1st of every month at 01:00 AM):
```cron
0 1 1 * * /path/to/smart-attendance/venv/bin/python /path/to/smart-attendance/scripts/generate_monthly_reports.py
```

#### Windows Task Scheduler configuration:
```powershell
schtasks /create /tn "SmartAttendanceMonthlyReports" /tr "python C:\smart-attendance\scripts\generate_monthly_reports.py" /sc monthly /d 1 /st 01:00
```

---

## 8. Verification Pipeline Details

1. **Dynamic QR Refresh:** QR codes regenerate every 30 seconds (configurable from 15s to 120s). The QR contains an unpredictable cryptographic token; previous tokens are deactivated. A 10-second leeway allows for transmission delay.
2. **GPS Geolocation (Haversine Formula):**
   $$d = 2R \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$
   Where $R = 6,371,000 \text{ m}$.
   If reported horizontal accuracy exceeds $80\text{ m}$, the reading is rejected as `LOCATION_UNVERIFIED`. If the distance exceeds the allowed radius ($50\text{ m}$ default), it is marked `LOCATION_FAILED`.
3. **Face Biometric Cosine Similarity:**
   $$\text{Similarity} = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2}$$
   - Threshold $\ge 0.65$: Verified `MATCH`.
   - Between $0.57$ and $0.65$: `INCONCLUSIVE` (routes attempt for faculty review).
   - Below $0.57$: `MISMATCH`.

---

## 9. Automated Test Suite

A complete test suite covers authentication, role authorization, QR expiration, GPS Haversine accuracy, face recognition, duplicate prevention, concurrent submissions, and report generation:

```bash
python -m unittest discover tests -v
```

All 30 unit and integration tests run in under 12 seconds:
- `tests/test_auth.py`
- `tests/test_location.py`
- `tests/test_qr.py`
- `tests/test_face.py`
- `tests/test_attendance.py`
- `tests/test_reports.py`

---

## 10. Known Technical Limitations & Operating Notices

1. **Indoor GPS Accuracy:** Browser Geolocation relies on cellular towers and Wi-Fi networks when indoors, which may experience $15\text{m}$ to $50\text{m}$ drift. GPS alone does not prove a student is physically in a specific classroom chair; it ensures the device is within the building perimeter.
2. **Liveness Detection:** Passive software heuristic checks (chrominance variance and texture analysis) reduce basic printed photo spoofing, but are not guaranteed against high-resolution digital replay screens or 3D masks.
3. **HTTPS Secure Context:** Modern browsers require an **HTTPS (SSL/TLS)** origin to grant camera and geolocation access. For local development, `localhost` and `127.0.0.1` are treated as secure contexts by default.
