"""Authentication blueprint - Login, Logout routes."""

import secrets
from flask import Blueprint, render_template, request, redirect, session, current_app
from werkzeug.security import check_password_hash

from utils import (
    get_db, sanitize_input, is_locked_out, 
    record_failed_attempt, clear_attempts
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    """Handle user login."""
    # Check if already logged in
    if "user" in session:
        return redirect("/dashboard")
    
    if request.method == "POST":
        ip = request.remote_addr
        
        # Check if locked out
        if is_locked_out(ip):
            return render_template("login.html", error="Too many attempts. Please wait 5 minutes.")
        
        username = sanitize_input(request.form.get("username", ""), 50)
        password = request.form.get("password", "")
        
        if not username or not password:
            return render_template("login.html", error="Please enter username and password")
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()
        
        if user and check_password_hash(user["password_hash"], password):
            clear_attempts(ip)
            session.permanent = True
            session["user"] = username
            session["user_id"] = user["id"]
            # Generate CSRF token
            session["csrf_token"] = secrets.token_hex(32)
            
            # Handle "Remember Me" - extend session to 30 days
            remember_me = request.form.get("remember_me")
            if remember_me:
                # Override session lifetime for this user
                current_app.permanent_session_lifetime = current_app.config.get(
                    'REMEMBER_ME_LIFETIME', 
                    current_app.config['PERMANENT_SESSION_LIFETIME']
                )
            else:
                # Use default session lifetime (8 hours)
                current_app.permanent_session_lifetime = current_app.config['PERMANENT_SESSION_LIFETIME']
            
            return redirect("/dashboard")
        
        record_failed_attempt(ip)
        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    """Handle user logout."""
    session.clear()
    return redirect("/")
