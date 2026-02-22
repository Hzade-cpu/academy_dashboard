"""Dashboard blueprint - Main dashboard and center management routes."""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, jsonify, flash

from utils import get_db, sanitize_input, login_required, CALENDAR_MONTHS, create_backup

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    """Main dashboard view with KPIs and revenue tracking."""
    conn = get_db()
    cur = conn.cursor()
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = int(request.args.get("year", datetime.now().year))

    # ================= SAFE SAVE =================
    if request.method == "POST":
        # Auto-backup before any data modification
        create_backup("auto_dashboard")
        
        # Update center names safely
        for key, val in request.form.items():
            if key.startswith("name"):
                cid = key.replace("name", "")
                cur.execute("UPDATE centers SET name=? WHERE id=?", (val, cid))

        # Save revenue / target ONLY for centers that have data for this month
        cur.execute("""
            SELECT DISTINCT center_id FROM monthly_data 
            WHERE month=? AND year=?
        """, (month, year))
        centers_in_month = cur.fetchall()

        for c in centers_in_month:
            cid = c["center_id"]

            revenue_raw = request.form.get(f"revenue{cid}")
            target_raw = request.form.get(f"target{cid}")

            cur.execute("""
                SELECT revenue, target FROM monthly_data
                WHERE center_id=? AND month=? AND year=?
            """, (cid, month, year))
            existing = cur.fetchone()

            old_revenue = existing["revenue"] if existing else 0
            old_target = existing["target"] if existing else 0

            revenue = float(revenue_raw) if revenue_raw not in (None, "") else old_revenue
            target = float(target_raw) if target_raw not in (None, "") else old_target

            cur.execute("""
                UPDATE monthly_data
                SET revenue=?, target=?
                WHERE center_id=? AND month=? AND year=?
            """, (revenue, target, cid, month, year))

        conn.commit()
        
        # If AJAX request, return JSON with updated data
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            centers_data = _calculate_centers_data(cur, year, month)
            monthly_kpis = _calculate_monthly_kpis(cur, year)
            conn.close()
            return jsonify({
                "ok": True,
                "centers": centers_data,
                "monthly_kpis": monthly_kpis
            })
        
        return redirect(f"/dashboard?month={month}&year={year}")

    # ================= LOAD =================
    centers_data = _calculate_centers_data(cur, year, month)
    monthly_kpis = _calculate_monthly_kpis(cur, year)
    conn.close()

    return render_template(
        "dashboard.html",
        centers=centers_data,
        month=month,
        year=year,
        monthly_kpis=monthly_kpis
    )


def _calculate_centers_data(cur, year, month):
    """Calculate centers data with auto-target formula applied."""
    centers_data = []
    
    # Only show centers that have data for this specific month
    cur.execute("""
        SELECT c.* FROM centers c
        WHERE c.id IN (
            SELECT center_id FROM monthly_data WHERE month=? AND year=?
        )
    """, (month, year))
    centers = cur.fetchall()

    for c in centers:
        cid = c["id"]
        name = c["name"]
        
        # Apply target formula only to months that already have data for this center
        cur.execute("""
            SELECT DISTINCT month FROM monthly_data 
            WHERE center_id=? AND year=?
        """, (cid, year))
        center_months = [row["month"] for row in cur.fetchall()]
        
        for m in center_months:
            cur.execute("""
                SELECT id, revenue, target FROM monthly_data
                WHERE center_id=? AND month=? AND year=?
            """, (cid, m, year))
            md_row = cur.fetchone()
            
            cur.execute("""
                SELECT SUM(cs.salary) FROM coach_salaries cs
                JOIN coaches co ON cs.coach_id = co.id
                WHERE co.center_id=? AND cs.month=? AND cs.year=?
            """, (cid, m, year))
            m_salary = cur.fetchone()[0] or 0
            
            # Auto-calculate target (salary should be <= 29.9% of target)
            calc_target = round(m_salary / 0.299, 2) if m_salary > 0 else 0
            
            if md_row and calc_target > 0:
                cur.execute("""
                    UPDATE monthly_data SET target=?
                    WHERE center_id=? AND month=? AND year=?
                """, (calc_target, cid, m, year))
        
        cur.connection.commit()

        # Get current month data for display
        cur.execute("""
            SELECT revenue, target FROM monthly_data
            WHERE center_id=? AND month=? AND year=?
        """, (cid, month, year))
        row = cur.fetchone()

        revenue = row["revenue"] if row else 0
        target = row["target"] if row else 0

        cur.execute("""
            SELECT SUM(cs.salary) FROM coach_salaries cs
            JOIN coaches c ON cs.coach_id = c.id
            WHERE c.center_id=? AND cs.month=? AND cs.year=?
        """, (cid, month, year))
        salary = cur.fetchone()[0] or 0

        achievement = (revenue / target * 100) if target > 0 else 0
        salary_percent = (salary / revenue * 100) if revenue > 0 else 0

        centers_data.append({
            "id": cid,
            "name": name,
            "revenue": revenue,
            "target": target,
            "achievement": round(achievement, 1),
            "salary_percent": round(salary_percent, 1)
        })
    
    return centers_data


def _calculate_monthly_kpis(cur, year):
    """Calculate monthly KPIs for calendar view."""
    # Aggregate total revenue and target per month
    cur.execute("""
        SELECT month, SUM(revenue) AS total_revenue, SUM(target) AS total_target
        FROM monthly_data
        WHERE year=?
        GROUP BY month
    """, (year,))
    rt_rows = cur.fetchall()

    revenue_target_by_month = {}
    for row in rt_rows:
        revenue_target_by_month[row["month"]] = {
            "total_revenue": row["total_revenue"] or 0,
            "total_target": row["total_target"] or 0,
        }

    # Aggregate total salary per month
    cur.execute("""
        SELECT month, SUM(salary) AS total_salary
        FROM coach_salaries
        WHERE year=?
        GROUP BY month
    """, (year,))
    sal_rows = cur.fetchall()

    salary_by_month = {row["month"]: row["total_salary"] or 0 for row in sal_rows}

    monthly_kpis = []
    for m in CALENDAR_MONTHS:
        totals = revenue_target_by_month.get(m, {"total_revenue": 0, "total_target": 0})
        total_revenue = totals["total_revenue"] or 0
        total_target = totals["total_target"] or 0
        total_salary = salary_by_month.get(m, 0) or 0

        achieved_percent = (total_revenue / total_target * 100) if total_target > 0 else 0
        salary_percent = (total_salary / total_revenue * 100) if total_revenue > 0 else 0

        monthly_kpis.append({
            "month": m,
            "total_revenue": round(total_revenue, 2),
            "total_target": round(total_target, 2),
            "achieved_percent": round(achieved_percent, 1),
            "salary_percent": round(salary_percent, 1),
        })
    
    return monthly_kpis


# ================= CENTERS MANAGEMENT =================
@dashboard_bp.route("/center/add", methods=["POST"])
@login_required
def add_center():
    """Add a new center for the current month only."""
    # Auto-backup before adding center
    create_backup("auto_add_center")
    
    name = sanitize_input(request.form.get("name")) or "New Center"
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = int(request.args.get("year", datetime.now().year))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO centers(name) VALUES(?)", (name,))
    center_id = cur.lastrowid
    
    # Create monthly_data entry so center only appears in this month
    cur.execute("""
        INSERT INTO monthly_data(center_id, month, year, revenue, target)
        VALUES(?, ?, ?, 0, 0)
    """, (center_id, month, year))
    
    conn.commit()
    conn.close()

    return redirect(f"/dashboard?month={month}&year={year}")


@dashboard_bp.route("/center/delete/<int:center_id>")
@login_required
def delete_center(center_id):
    """Delete a center and all related data (permanent)."""
    # Auto-backup before deleting center (CRITICAL!)
    create_backup("auto_delete_center")
    
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = request.args.get("year", datetime.now().year)

    conn = get_db()
    cur = conn.cursor()

    # Cascade delete - removes center entirely
    cur.execute("DELETE FROM monthly_data WHERE center_id=?", (center_id,))
    cur.execute("""
        DELETE FROM coach_salaries WHERE coach_id IN 
        (SELECT id FROM coaches WHERE center_id=?)
    """, (center_id,))
    cur.execute("DELETE FROM coaches WHERE center_id=?", (center_id,))
    cur.execute("DELETE FROM centers WHERE id=?", (center_id,))

    conn.commit()
    conn.close()

    return redirect(f"/dashboard?month={month}&year={year}")


@dashboard_bp.route("/center/remove-month/<int:center_id>")
@login_required
def remove_center_month(center_id):
    """Remove center data for a specific month only (keeps center and other months)."""
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = int(request.args.get("year", datetime.now().year))

    conn = get_db()
    cur = conn.cursor()
    
    # Get center name for flash message
    cur.execute("SELECT name FROM centers WHERE id=?", (center_id,))
    center_row = cur.fetchone()
    center_name = center_row[0] if center_row else "Unknown"

    # Delete only this month's revenue/target data for this center
    cur.execute("""
        DELETE FROM monthly_data 
        WHERE center_id=? AND month=? AND year=?
    """, (center_id, month, year))
    deleted_monthly = cur.rowcount

    # Delete coach salaries for this center's coaches for this month only
    cur.execute("""
        DELETE FROM coach_salaries 
        WHERE coach_id IN (SELECT id FROM coaches WHERE center_id=?)
        AND month=? AND year=?
    """, (center_id, month, year))
    deleted_salaries = cur.rowcount

    conn.commit()
    conn.close()
    
    flash(f"✅ Removed {center_name} from {month} {year} (center will still appear in other months)", "success")

    return redirect(f"/dashboard?month={month}&year={year}")
