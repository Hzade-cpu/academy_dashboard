"""
Academy Dashboard - Main Application

A Flask application for managing academy centers, coaches, and revenue tracking.

Architecture:
- blueprints/auth.py      - Login/Logout routes
- blueprints/dashboard.py - Dashboard and center management
- blueprints/coaches.py   - Coach and salary management
- blueprints/analytics.py - Analytics and reporting
- utils.py                - Shared utilities (DB, decorators, etc.)
"""

from flask import Flask
import os
import secrets
from datetime import timedelta
from werkzeug.security import generate_password_hash

from utils import get_db, generate_csrf_token, create_backup, IS_POSTGRES
from blueprints import auth_bp, dashboard_bp, coaches_bp, analytics_bp, settings_bp, leaves_bp


# ================= APP CONFIGURATION =================
app = Flask(__name__)

# Secure secret key - from env or auto-generate
SECRET_KEY_FILE = "instance/.secret_key"

def get_secret_key():
    """Generate or retrieve the application secret key."""
    # Use environment variable in production (Render, Railway, etc.)
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    # Fall back to file-based key for local development
    os.makedirs("instance", exist_ok=True)
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(key)
    return key

app.secret_key = get_secret_key()

# Check if running in production
IS_PRODUCTION = os.environ.get('RENDER') or os.environ.get('PRODUCTION')

# Secure session configuration
app.config.update(
    SESSION_COOKIE_SECURE=IS_PRODUCTION,  # True in production with HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),  # Default session
    REMEMBER_ME_LIFETIME=timedelta(days=30)  # Extended session when "Remember Me" is checked
)


# ================= CSRF TOKEN FOR TEMPLATES =================
@app.context_processor
def inject_csrf_token():
    """Make csrf_token available in all templates."""
    return dict(csrf_token=generate_csrf_token)


# ================= REGISTER BLUEPRINTS =================
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(coaches_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(leaves_bp)


# ================= DATABASE INITIALIZATION =================
def init_db():
    """Initialize the database with required tables."""
    conn = get_db()
    cur = conn.cursor()

    if IS_POSTGRES:
        # PostgreSQL schema
        cur.execute("""
            CREATE TABLE IF NOT EXISTS centers(
                id SERIAL PRIMARY KEY,
                name TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS monthly_data(
                id SERIAL PRIMARY KEY,
                center_id INTEGER,
                month TEXT,
                year INTEGER DEFAULT 2026,
                revenue REAL DEFAULT 0,
                target REAL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coaches(
                id SERIAL PRIMARY KEY,
                center_id INTEGER,
                name TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coach_salaries(
                id SERIAL PRIMARY KEY,
                coach_id INTEGER,
                month TEXT,
                year INTEGER DEFAULT 2026,
                salary REAL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coach_leaves(
                id SERIAL PRIMARY KEY,
                coach_id INTEGER,
                from_date DATE,
                to_date DATE,
                leave_type TEXT DEFAULT 'Casual',
                remarks TEXT,
                year INTEGER DEFAULT 2026,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Ensure at least one center exists
        cur.execute("SELECT COUNT(*) FROM centers")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO centers(name) VALUES('Center 1')")

        # Create default admin user if NO users exist
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            default_hash = generate_password_hash("admin", method='pbkdf2:sha256')
            cur.execute("INSERT INTO users(username, password_hash) VALUES(%s, %s)", 
                       ("admin", default_hash))

    else:
        # SQLite schema (local development)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS centers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS monthly_data(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                center_id INTEGER,
                month TEXT,
                year INTEGER DEFAULT 2026,
                revenue REAL DEFAULT 0,
                target REAL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coaches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                center_id INTEGER,
                name TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coach_salaries(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coach_id INTEGER,
                month TEXT,
                year INTEGER DEFAULT 2026,
                salary REAL DEFAULT 0,
                FOREIGN KEY(coach_id) REFERENCES coaches(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS coach_leaves(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coach_id INTEGER,
                from_date DATE NOT NULL,
                to_date DATE NOT NULL,
                leave_type TEXT DEFAULT 'Casual',
                remarks TEXT,
                year INTEGER DEFAULT 2026,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(coach_id) REFERENCES coaches(id)
            )
        """)
        
        # Migration: Add from_date and to_date columns if they don't exist (for existing databases)
        cur.execute("PRAGMA table_info(coach_leaves)")
        columns = [col[1] for col in cur.fetchall()]
        
        if 'leave_date' in columns and 'from_date' not in columns:
            cur.execute("ALTER TABLE coach_leaves ADD COLUMN from_date DATE")
            cur.execute("ALTER TABLE coach_leaves ADD COLUMN to_date DATE")
            cur.execute("UPDATE coach_leaves SET from_date = leave_date, to_date = leave_date WHERE from_date IS NULL")
        elif 'from_date' not in columns:
            cur.execute("ALTER TABLE coach_leaves ADD COLUMN from_date DATE")
            cur.execute("ALTER TABLE coach_leaves ADD COLUMN to_date DATE")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add year column to existing tables if not exists
        try:
            cur.execute("ALTER TABLE monthly_data ADD COLUMN year INTEGER DEFAULT 2026")
        except:
            pass
        try:
            cur.execute("ALTER TABLE coach_salaries ADD COLUMN year INTEGER DEFAULT 2026")
        except:
            pass

        # Ensure at least one center exists
        cur.execute("SELECT COUNT(*) FROM centers")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO centers(name) VALUES('Center 1')")

        # Create default admin user if NO users exist (first time setup only)
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            default_hash = generate_password_hash("admin", method='pbkdf2:sha256')
            cur.execute("INSERT INTO users(username, password_hash) VALUES(?, ?)", 
                       ("admin", default_hash))

    conn.commit()
    conn.close()


# Create automatic backup on startup
create_backup("startup")

# Initialize database on startup
init_db()


# ================= RUN APPLICATION =================
if __name__ == "__main__":
    # In production, use gunicorn (wsgi.py) instead
    # This runs only for local development
    port = int(os.environ.get('PORT', 5000))
    debug = not IS_PRODUCTION
    app.run(host='0.0.0.0', port=port, debug=debug)
