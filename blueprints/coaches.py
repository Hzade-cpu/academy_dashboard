"""Coaches blueprint - Coach management and salary routes."""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect

from utils import get_db, login_required, CALENDAR_MONTHS, create_backup

coaches_bp = Blueprint('coaches', __name__)


@coaches_bp.route("/coaches", methods=["GET", "POST"])
@login_required
def coaches():
    """Manage coaches and their salaries."""
    conn = get_db()
    cur = conn.cursor()
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = int(request.args.get("year", datetime.now().year))
    selected_center = request.args.get("center")
    if selected_center:
        selected_center = int(selected_center)
    
    if request.method == "POST":
        action = request.form.get("action")
        
        # Auto-backup before any data modification
        create_backup("auto_coaches")
        
        if action == "add_coach":
            _add_coach(cur, request.form)
            conn.commit()
            
        elif action == "update_salary":
            _update_salary(cur, request.form, year)
            conn.commit()
            
        elif action == "edit_coach":
            _edit_coach(cur, request.form)
            conn.commit()
        
        return redirect(f"/coaches?month={month}&year={year}")

    # Get all coaches with their current month salary - only for centers in this month
    cur.execute("""
        SELECT c.id, c.name, c.center_id, 
               COALESCE(cs.salary, 0) as salary
        FROM coaches c
        LEFT JOIN coach_salaries cs ON c.id = cs.coach_id AND cs.month = ? AND cs.year = ?
        WHERE c.center_id IN (
            SELECT DISTINCT center_id FROM monthly_data WHERE month = ? AND year = ?
        )
    """, (month, year, month, year))
    coaches_list = cur.fetchall()
    
    # Only show centers that have data for this month
    cur.execute("""
        SELECT * FROM centers 
        WHERE id IN (SELECT DISTINCT center_id FROM monthly_data WHERE month = ? AND year = ?)
    """, (month, year))
    centers = cur.fetchall()
    salary_by_coach = _get_salary_by_coach(cur, year)
    monthly_salary = _get_monthly_salary(cur, year)

    conn.close()

    return render_template(
        "coaches.html",
        coaches=coaches_list,
        centers=centers,
        month=month,
        year=year,
        monthly_salary=monthly_salary,
        calendar_months=CALENDAR_MONTHS,
        salary_by_coach=salary_by_coach,
        selected_center=selected_center,
    )


def _add_coach(cur, form):
    """Add a new coach."""
    cur.execute("""
        INSERT INTO coaches(name, center_id)
        VALUES(?,?)
    """, (form["name"], form["center_id"]))


def _edit_coach(cur, form):
    """Edit coach name and center."""
    coach_id = form.get("coach_id")
    cur.execute("""
        UPDATE coaches SET name=?, center_id=?
        WHERE id=?
    """, (form["name"], form["center_id"], coach_id))


def _update_salary(cur, form, year):
    """Update salary for a coach and auto-update targets."""
    coach_id = form.get("coach_id")
    salary_month = form.get("salary_month")
    salary_year = int(form.get("salary_year", year))
    salary = float(form.get("salary") or 0)
    
    # Check if salary record exists
    cur.execute("""
        SELECT id FROM coach_salaries 
        WHERE coach_id=? AND month=? AND year=?
    """, (coach_id, salary_month, salary_year))
    existing = cur.fetchone()
    
    if existing:
        cur.execute("""
            UPDATE coach_salaries SET salary=?
            WHERE coach_id=? AND month=? AND year=?
        """, (salary, coach_id, salary_month, salary_year))
    else:
        cur.execute("""
            INSERT INTO coach_salaries(coach_id, month, year, salary)
            VALUES(?,?,?,?)
        """, (coach_id, salary_month, salary_year, salary))
    
    # Auto-update target based on total salary for the center
    cur.execute("SELECT center_id FROM coaches WHERE id=?", (coach_id,))
    coach_row = cur.fetchone()
    if coach_row:
        center_id = coach_row["center_id"]
        _update_center_targets(cur, center_id, salary_year)


def _update_center_targets(cur, center_id, year):
    """Update targets for months that already have data for this center."""
    # Only update months that already exist for this center (don't create new entries)
    cur.execute("""
        SELECT DISTINCT month FROM monthly_data 
        WHERE center_id=? AND year=?
    """, (center_id, year))
    existing_months = [row["month"] for row in cur.fetchall()]
    
    for m in existing_months:
        cur.execute("""
            SELECT SUM(cs.salary) as total_salary
            FROM coach_salaries cs
            JOIN coaches co ON cs.coach_id = co.id
            WHERE co.center_id=? AND cs.month=? AND cs.year=?
        """, (center_id, m, year))
        total_salary = cur.fetchone()["total_salary"] or 0
        
        # Calculate target (salary should be <= 29.9% of target)
        calc_target = round(total_salary / 0.299, 2) if total_salary > 0 else 0
        
        if calc_target > 0:
            cur.execute("""
                UPDATE monthly_data SET target=?
                WHERE center_id=? AND month=? AND year=?
            """, (calc_target, center_id, m, year))


def _get_salary_by_coach(cur, year):
    """Build salary lookup by coach and month."""
    cur.execute("""
        SELECT coach_id, month, salary FROM coach_salaries WHERE year=?
    """, (year,))
    all_salaries = cur.fetchall()
    
    salary_by_coach = {}
    for row in all_salaries:
        cid = row["coach_id"]
        if cid not in salary_by_coach:
            salary_by_coach[cid] = {}
        salary_by_coach[cid][row["month"]] = row["salary"]
    
    return salary_by_coach


def _get_monthly_salary(cur, year):
    """Get total salary per month - only for existing coaches with valid centers."""
    cur.execute("""
        SELECT cs.month, SUM(cs.salary) AS total_salary
        FROM coach_salaries cs
        JOIN coaches c ON cs.coach_id = c.id
        JOIN centers ct ON c.center_id = ct.id
        WHERE cs.year=?
        GROUP BY cs.month
    """, (year,))
    sal_rows = cur.fetchall()
    salary_by_month = {row["month"]: row["total_salary"] or 0 for row in sal_rows}

    monthly_salary = []
    for m in CALENDAR_MONTHS:
        total_salary = salary_by_month.get(m, 0) or 0
        monthly_salary.append({
            "month": m,
            "total_salary": round(total_salary, 2),
        })
    
    return monthly_salary


@coaches_bp.route("/delete_coach/<int:coach_id>")
@login_required
def delete_coach(coach_id):
    """Delete a coach and their salary records."""
    month = request.args.get("month", datetime.now().strftime("%B"))
    year = request.args.get("year", datetime.now().year)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM coach_salaries WHERE coach_id=?", (coach_id,))
    cur.execute("DELETE FROM coaches WHERE id=?", (coach_id,))
    conn.commit()
    conn.close()
    
    return redirect(f"/coaches?month={month}&year={year}")
