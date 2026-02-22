"""Settings blueprint - User account settings, password change, backup management."""

from flask import Blueprint, render_template, request, redirect, session, flash, send_file, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
import os

from utils import get_db, login_required, sanitize_input, create_backup, list_backups, restore_backup

settings_bp = Blueprint('settings', __name__)


@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """User settings page - change username and password."""
    conn = None
    message = None
    error = None
    current_username = ""
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Get current user info
        user_id = session.get("user_id")
        cur.execute("SELECT username FROM users WHERE id=?", (user_id,))
        user = cur.fetchone()
        current_username = user["username"] if user else ""
        
        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "change_username":
                new_username = sanitize_input(request.form.get("new_username", ""), 50)
                current_password = request.form.get("current_password", "")
                
                if not new_username or not current_password:
                    error = "Please fill in all fields"
                else:
                    # Verify current password
                    cur.execute("SELECT password_hash FROM users WHERE id=?", (user_id,))
                    user_data = cur.fetchone()
                    
                    if user_data and check_password_hash(user_data["password_hash"], current_password):
                        # Check if username already exists
                        cur.execute("SELECT id FROM users WHERE username=? AND id!=?", (new_username, user_id))
                        if cur.fetchone():
                            error = "Username already taken"
                        else:
                            try:
                                cur.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
                                conn.commit()
                                session["user"] = new_username
                                current_username = new_username
                                message = "Username updated successfully!"
                            except Exception as e:
                                conn.rollback()
                                error = f"Failed to update username: {str(e)}"
                    else:
                        error = "Current password is incorrect"
            
            elif action == "change_password":
                current_password = request.form.get("current_password_pwd", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")
                
                if not current_password or not new_password or not confirm_password:
                    error = "Please fill in all password fields"
                elif new_password != confirm_password:
                    error = "New passwords do not match"
                elif len(new_password) < 4:
                    error = "Password must be at least 4 characters"
                else:
                    # Verify current password
                    cur.execute("SELECT password_hash FROM users WHERE id=?", (user_id,))
                    user_data = cur.fetchone()
                    
                    if user_data and check_password_hash(user_data["password_hash"], current_password):
                        try:
                            new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                            cur.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
                            conn.commit()
                            message = "Password updated successfully!"
                        except Exception as e:
                            conn.rollback()
                            error = f"Failed to update password: {str(e)}"
                    else:
                        error = "Current password is incorrect"
    
    except Exception as e:
        error = f"Database error: {str(e)}"
    
    finally:
        if conn:
            conn.close()
    
    return render_template(
        "settings.html",
        current_username=current_username,
        message=message,
        error=error
    )


# ================= BACKUP MANAGEMENT ROUTES =================

@settings_bp.route("/backups")
@login_required
def backups():
    """View all available database backups."""
    backup_list = list_backups()
    return render_template("backups.html", backups=backup_list)


@settings_bp.route("/backups/create", methods=["POST"])
@login_required
def create_backup_route():
    """Create a manual backup."""
    reason = sanitize_input(request.form.get("reason", "manual"), 50)
    reason = reason.replace(" ", "_").replace("/", "_")  # Clean filename
    backup_path = create_backup(reason)
    
    if backup_path:
        flash(f"Backup created successfully: {os.path.basename(backup_path)}", "success")
    else:
        flash("Failed to create backup", "error")
    
    return redirect("/backups")


@settings_bp.route("/backups/restore/<path:filename>", methods=["POST"])
@login_required
def restore_backup_route(filename):
    """Restore database from a backup file."""
    backup_path = os.path.join("backups", filename)
    
    if restore_backup(backup_path):
        flash(f"Database restored from {filename}. Please restart the application.", "success")
    else:
        flash("Failed to restore backup", "error")
    
    return redirect("/backups")


@settings_bp.route("/backups/download/<path:filename>")
@login_required
def download_backup(filename):
    """Download a backup file."""
    backup_path = os.path.join("backups", filename)
    
    if os.path.exists(backup_path):
        return send_file(
            os.path.abspath(backup_path),
            as_attachment=True,
            download_name=filename
        )
    else:
        flash("Backup file not found", "error")
        return redirect("/backups")


# ================= DATA IMPORT/EXPORT ROUTES =================

@settings_bp.route("/import-data", methods=["GET", "POST"])
@login_required
def import_data():
    """Import data from JSON."""
    message = None
    error = None
    
    if request.method == "POST":
        try:
            json_data = request.form.get("json_data", "")
            if not json_data:
                error = "Please paste JSON data"
            else:
                import json
                data = json.loads(json_data)
                
                conn = get_db()
                cur = conn.cursor()
                
                # Import centers (skip id=1 which is default)
                for center in data.get("centers", []):
                    if center["id"] != 1 and center["name"]:
                        cur.execute("INSERT INTO centers(name) VALUES(?)", (center["name"],))
                
                # Get new center ID mapping (simplified - assumes sequential)
                cur.execute("SELECT id, name FROM centers")
                center_map = {row["name"]: row["id"] for row in cur.fetchall()}
                
                # Import coaches
                for coach in data.get("coaches", []):
                    # Find center by looking at original data
                    orig_center = next((c for c in data["centers"] if c["id"] == coach["center_id"]), None)
                    if orig_center and orig_center["name"] in center_map:
                        new_center_id = center_map[orig_center["name"]]
                        cur.execute("INSERT INTO coaches(center_id, name) VALUES(?, ?)", 
                                   (new_center_id, coach["name"]))
                
                # Import monthly data
                for md in data.get("monthly_data", []):
                    orig_center = next((c for c in data["centers"] if c["id"] == md["center_id"]), None)
                    if orig_center and orig_center["name"] in center_map:
                        new_center_id = center_map[orig_center["name"]]
                        cur.execute("""INSERT INTO monthly_data(center_id, month, year, revenue, target) 
                                      VALUES(?, ?, ?, ?, ?)""",
                                   (new_center_id, md["month"], md["year"], md["revenue"], md["target"]))
                
                conn.commit()
                conn.close()
                message = "Data imported successfully!"
                
        except json.JSONDecodeError:
            error = "Invalid JSON format"
        except Exception as e:
            error = f"Import failed: {str(e)}"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Import Data</title>
        <style>
            body {{ font-family: Arial; background: #1a1a2e; color: #eee; padding: 40px; }}
            .container {{ max-width: 800px; margin: auto; }}
            textarea {{ width: 100%; height: 400px; background: #16213e; color: #eee; border: 1px solid #0f3460; padding: 15px; font-family: monospace; }}
            button {{ background: #e94560; color: white; padding: 15px 30px; border: none; cursor: pointer; font-size: 16px; margin-top: 15px; }}
            .message {{ padding: 15px; margin: 15px 0; border-radius: 5px; }}
            .success {{ background: #1b4332; }}
            .error {{ background: #7f1d1d; }}
            a {{ color: #e94560; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📥 Import Data</h1>
            <p><a href="/dashboard">← Back to Dashboard</a></p>
            {"<div class='message success'>✅ " + message + "</div>" if message else ""}
            {"<div class='message error'>❌ " + error + "</div>" if error else ""}
            <form method="POST">
                <p>Paste your exported JSON data below:</p>
                <textarea name="json_data" placeholder="Paste JSON here..."></textarea>
                <br>
                <button type="submit">Import Data</button>
            </form>
        </div>
    </body>
    </html>
    '''
