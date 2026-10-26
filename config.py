import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    
    # Database: MySQL primary, fallback to SQLite if MySQL is unavailable or configured as such
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
    MYSQL_DB = os.environ.get("MYSQL_DB", "smart_attendance")
    
    # Priority: explicit DATABASE_URL -> MySQL URI -> SQLite local file
    default_mysql_uri = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    default_sqlite_uri = f"sqlite:///{os.path.join(BASE_DIR, 'smart_attendance.db')}"
    
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", default_sqlite_uri)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    } if "sqlite" not in SQLALCHEMY_DATABASE_URI else {}

    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True when HTTPS is enabled in deployment
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1")
    
    # Application Verification Settings
    QR_REFRESH_INTERVAL_SECONDS = int(os.environ.get("QR_REFRESH_INTERVAL_SECONDS", "30"))
    QR_TOKEN_VALIDITY_LEEWAY = int(os.environ.get("QR_TOKEN_VALIDITY_LEEWAY", "10")) # extra seconds for scan delay
    
    DEFAULT_CLASSROOM_RADIUS_METERS = float(os.environ.get("DEFAULT_CLASSROOM_RADIUS_METERS", "50.0"))
    MAX_GPS_ACCURACY_THRESHOLD_METERS = float(os.environ.get("MAX_GPS_ACCURACY_THRESHOLD_METERS", "80.0"))
    
    FACE_SIMILARITY_THRESHOLD = float(os.environ.get("FACE_SIMILARITY_THRESHOLD", "0.65"))
    LOW_ATTENDANCE_THRESHOLD_PERCENT = float(os.environ.get("LOW_ATTENDANCE_THRESHOLD_PERCENT", "75.0"))
    
    # Upload folder for face models / templates if needed
    FACE_MODELS_DIR = os.path.join(BASE_DIR, "app", "face", "models")
    REPORTS_DIR = os.path.join(BASE_DIR, "exports")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    QR_REFRESH_INTERVAL_SECONDS = 30
    QR_TOKEN_VALIDITY_LEEWAY = 10
    DEFAULT_CLASSROOM_RADIUS_METERS = 50.0
    MAX_GPS_ACCURACY_THRESHOLD_METERS = 80.0
    FACE_SIMILARITY_THRESHOLD = 0.65

config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
