"""Shared utilities for the Academy Dashboard application."""

import sqlite3
import os
import secrets
import re
import shutil
import glob
from datetime import datetime
from functools import wraps
from flask import session, redirect, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "instance/academy.db"
BACKUP_DIR = "backups"  # Dedicated backup folder - DO NOT DELETE
MAX_BACKUPS = 20  # Keep last 20 backups


def create_backup(reason="manual"):
    """
    Create a timestamped backup of the database.
    Backups are stored in the 'backups' folder with timestamp and reason.
    Returns the backup file path if successful, None otherwise.
    """
    if not os.path.exists(DB_PATH):
        return None
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"academy_db_{timestamp}_{reason}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    try:
        # Use shutil.copy2 to preserve metadata
        shutil.copy2(DB_PATH, backup_path)
        
        # Also copy WAL files if they exist
        if os.path.exists(DB_PATH + "-wal"):
            shutil.copy2(DB_PATH + "-wal", backup_path + "-wal")
        if os.path.exists(DB_PATH + "-shm"):
            shutil.copy2(DB_PATH + "-shm", backup_path + "-shm")
        
        # Cleanup old backups, keep only MAX_BACKUPS
        cleanup_old_backups()
        
        print(f"[BACKUP] Created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[BACKUP ERROR] Failed to create backup: {e}")
        return None


def cleanup_old_backups():
    """Remove old backups, keeping only the most recent MAX_BACKUPS."""
    backup_files = glob.glob(os.path.join(BACKUP_DIR, "academy_db_*.db"))
    # Sort by modification time (oldest first)
    backup_files.sort(key=os.path.getmtime)
    
    # Remove oldest backups if we have too many
    while len(backup_files) > MAX_BACKUPS:
        old_backup = backup_files.pop(0)
        try:
            os.remove(old_backup)
            # Also remove associated WAL/SHM files
            if os.path.exists(old_backup + "-wal"):
                os.remove(old_backup + "-wal")
            if os.path.exists(old_backup + "-shm"):
                os.remove(old_backup + "-shm")
            print(f"[BACKUP] Removed old backup: {old_backup}")
        except:
            pass


def list_backups():
    """List all available backups with their timestamps."""
    if not os.path.exists(BACKUP_DIR):
        return []
    
    backup_files = glob.glob(os.path.join(BACKUP_DIR, "academy_db_*.db"))
    backup_files.sort(key=os.path.getmtime, reverse=True)  # Newest first
    
    backups = []
    for f in backup_files:
        stat = os.stat(f)
        backups.append({
            'path': f,
            'filename': os.path.basename(f),
            'size_kb': round(stat.st_size / 1024, 2),
            'created': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        })
    return backups


def restore_backup(backup_path):
    """
    Restore database from a backup file.
    Creates a backup of current state before restoring.
    Returns True if successful, False otherwise.
    """
    if not os.path.exists(backup_path):
        print(f"[RESTORE ERROR] Backup file not found: {backup_path}")
        return False
    
    # First, backup the current state
    create_backup("before_restore")
    
    try:
        shutil.copy2(backup_path, DB_PATH)
        if os.path.exists(backup_path + "-wal"):
            shutil.copy2(backup_path + "-wal", DB_PATH + "-wal")
        if os.path.exists(backup_path + "-shm"):
            shutil.copy2(backup_path + "-shm", DB_PATH + "-shm")
        print(f"[RESTORE] Successfully restored from: {backup_path}")
        return True
    except Exception as e:
        print(f"[RESTORE ERROR] Failed to restore: {e}")
        return False

# Login attempt tracking (simple in-memory rate limiting)
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 300  # 5 minutes in seconds


def get_db():
    """Get database connection with Row factory."""
    os.makedirs("instance", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)  # 30 second timeout to prevent locking
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
    return conn


def is_locked_out(ip):
    """Check if IP is locked out due to too many login attempts."""
    if ip in login_attempts:
        attempts, lockout_time = login_attempts[ip]
        if lockout_time and datetime.now().timestamp() < lockout_time:
            return True
        if lockout_time and datetime.now().timestamp() >= lockout_time:
            login_attempts[ip] = (0, None)
    return False


def record_failed_attempt(ip):
    """Record a failed login attempt."""
    attempts, _ = login_attempts.get(ip, (0, None))
    attempts += 1
    if attempts >= MAX_LOGIN_ATTEMPTS:
        login_attempts[ip] = (attempts, datetime.now().timestamp() + LOCKOUT_TIME)
    else:
        login_attempts[ip] = (attempts, None)


def clear_attempts(ip):
    """Clear login attempts for an IP."""
    if ip in login_attempts:
        del login_attempts[ip]


def sanitize_input(value, max_length=255):
    """Sanitize string input."""
    if value is None:
        return None
    value = str(value).strip()
    value = value[:max_length]
    value = re.sub(r'[<>]', '', value)
    return value


def sanitize_number(value, default=0):
    """Safely convert value to number."""
    try:
        return float(value) if value not in (None, "") else default
    except (ValueError, TypeError):
        return default


def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated_function


def generate_csrf_token():
    """Generate or retrieve CSRF token."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf(f):
    """Decorator to validate CSRF token on POST requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not token or token != session.get('csrf_token'):
                return jsonify({"error": "Invalid CSRF token"}), 403
        return f(*args, **kwargs)
    return decorated_function


# Calendar months constant
CALENDAR_MONTHS = [
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December",
]
