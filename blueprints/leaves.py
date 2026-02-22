"""Leaves blueprint - Coach leave management and tracking."""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect

from utils import get_db, login_required, CALENDAR_MONTHS, create_backup

leaves_bp = Blueprint('leaves', __name__)

# Leave types
LEAVE_TYPES = ['Casual', 'Sick', 'Paid', 'Unpaid', 'Week Off', 'OT', 'Emergency', 'Other']


def calculate_days(from_date_str, to_date_str):
    """Calculate number of days between two dates (inclusive)."""
    try:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
        return (to_date - from_date).days + 1
    except:
        return 1


@leaves_bp.route("/leaves", methods=["GET", "POST"])
@login_required
def leaves():
    """Manage coach leaves."""
    conn = get_db()
    cur = conn.cursor()
    
    year = int(request.args.get("year", datetime.now().year))
    selected_month = request.args.get("month", "All")
    selected_coach = request.args.get("coach", "")
    selected_center = request.args.get("center", "")
    
    if request.method == "POST":
        action = request.form.get("action")
        
        # Auto-backup before any data modification
        create_backup("auto_leaves")
        
        if action == "add_leave":
            _add_leave(cur, request.form)
            conn.commit()
            
        elif action == "edit_leave":
            _edit_leave(cur, request.form)
            conn.commit()
            
        elif action == "delete_leave":
            leave_id = request.form.get("leave_id")
            cur.execute("DELETE FROM coach_leaves WHERE id=?", (leave_id,))
            conn.commit()
        
        # Preserve filters in redirect
        return redirect(f"/leaves?year={year}&month={selected_month}&coach={selected_coach}&center={selected_center}")

    # Build query with filters
    query = """
        SELECT cl.id, cl.coach_id, c.name as coach_name, ct.name as center_name,
               cl.from_date, cl.to_date, cl.leave_type, cl.remarks, cl.created_at,
               CAST(julianday(cl.to_date) - julianday(cl.from_date) + 1 AS INTEGER) as days
        FROM coach_leaves cl
        JOIN coaches c ON cl.coach_id = c.id
        JOIN centers ct ON c.center_id = ct.id
        WHERE cl.year = ?
    """
    params = [year]
    
    if selected_month and selected_month != "All":
        # Filter by month name from date
        query += " AND strftime('%m', cl.from_date) = ?"
        month_num = str(CALENDAR_MONTHS.index(selected_month) + 1).zfill(2)
        params.append(month_num)
    
    if selected_coach:
        query += " AND cl.coach_id = ?"
        params.append(int(selected_coach))
    
    if selected_center:
        query += " AND c.center_id = ?"
        params.append(int(selected_center))
    
    query += " ORDER BY cl.from_date DESC"
    
    cur.execute(query, params)
    leaves_list = cur.fetchall()
    
    # Get all coaches for dropdown
    cur.execute("""
        SELECT c.id, c.name, ct.name as center_name 
        FROM coaches c 
        JOIN centers ct ON c.center_id = ct.id
        ORDER BY ct.name, c.name
    """)
    coaches_list = cur.fetchall()
    
    # Get all centers for dropdown
    centers = cur.execute("SELECT * FROM centers ORDER BY name").fetchall()
    
    # Get leave statistics per coach for the year (with LOP count, excluding Week Off and OT from counts)
    cur.execute("""
        SELECT c.id, c.name, ct.name as center_name, 
               COUNT(cl.id) as total_leaves,
               SUM(CASE WHEN cl.leave_type = 'Unpaid' THEN julianday(cl.to_date) - julianday(cl.from_date) + 1 ELSE 0 END) as lop_days,
               SUM(CASE WHEN cl.leave_type NOT IN ('Unpaid', 'Week Off', 'OT') THEN julianday(cl.to_date) - julianday(cl.from_date) + 1 ELSE 0 END) as approved_days,
               SUM(CASE WHEN cl.leave_type NOT IN ('Week Off', 'OT') THEN julianday(cl.to_date) - julianday(cl.from_date) + 1 ELSE 0 END) as total_days,
               SUM(CASE WHEN cl.leave_type = 'Week Off' THEN julianday(cl.to_date) - julianday(cl.from_date) + 1 ELSE 0 END) as weekoff_days,
               SUM(CASE WHEN cl.leave_type = 'OT' THEN julianday(cl.to_date) - julianday(cl.from_date) + 1 ELSE 0 END) as ot_days
        FROM coaches c
        JOIN centers ct ON c.center_id = ct.id
        LEFT JOIN coach_leaves cl ON c.id = cl.coach_id AND cl.year = ?
        GROUP BY c.id
        ORDER BY total_days DESC
    """, (year,))
    leave_stats = cur.fetchall()
    
    # Get monthly leave count for chart (sum of days, not records)
    monthly_leaves = {}
    for month in CALENDAR_MONTHS:
        month_num = str(CALENDAR_MONTHS.index(month) + 1).zfill(2)
        cur.execute("""
            SELECT COALESCE(SUM(julianday(to_date) - julianday(from_date) + 1), 0) 
            FROM coach_leaves 
            WHERE year = ? AND strftime('%m', from_date) = ?
        """, (year, month_num))
        monthly_leaves[month] = int(cur.fetchone()[0])
    
    # Get leave type breakdown (with total days)
    cur.execute("""
        SELECT leave_type, 
               CAST(SUM(julianday(to_date) - julianday(from_date) + 1) AS INTEGER) as total_days
        FROM coach_leaves 
        WHERE year = ?
        GROUP BY leave_type
        ORDER BY total_days DESC
    """, (year,))
    leave_type_stats = [list(row) for row in cur.fetchall()]
    
    # Get total leave days and LOP days for the year (excluding Week Off and OT from totals)
    cur.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN leave_type NOT IN ('Week Off', 'OT') THEN julianday(to_date) - julianday(from_date) + 1 ELSE 0 END), 0) as total_days,
            COALESCE(SUM(CASE WHEN leave_type = 'Unpaid' THEN julianday(to_date) - julianday(from_date) + 1 ELSE 0 END), 0) as lop_days,
            COALESCE(SUM(CASE WHEN leave_type = 'Week Off' THEN julianday(to_date) - julianday(from_date) + 1 ELSE 0 END), 0) as weekoff_days,
            COALESCE(SUM(CASE WHEN leave_type = 'OT' THEN julianday(to_date) - julianday(from_date) + 1 ELSE 0 END), 0) as ot_days
        FROM coach_leaves 
        WHERE year = ?
    """, (year,))
    totals = cur.fetchone()
    total_leave_days = int(totals[0])
    total_lop_days = int(totals[1])
    total_weekoff_days = int(totals[2])
    total_ot_days = int(totals[3])
    
    conn.close()

    return render_template(
        "leaves.html",
        leaves=leaves_list,
        coaches=coaches_list,
        centers=centers,
        year=year,
        selected_month=selected_month,
        selected_coach=selected_coach,
        selected_center=selected_center,
        calendar_months=CALENDAR_MONTHS,
        leave_types=LEAVE_TYPES,
        leave_stats=leave_stats,
        monthly_leaves=monthly_leaves,
        leave_type_stats=leave_type_stats,
        total_leave_days=total_leave_days,
        total_lop_days=total_lop_days,
        total_weekoff_days=total_weekoff_days,
        total_ot_days=total_ot_days,
    )


def _add_leave(cur, form):
    """Add a new leave record."""
    coach_id = form.get("coach_id")
    from_date = form.get("from_date")
    to_date = form.get("to_date") or from_date  # Default to same date if not provided
    leave_type = form.get("leave_type", "Casual")
    remarks = form.get("remarks", "").strip()
    year = int(form.get("year", datetime.now().year))
    
    cur.execute("""
        INSERT INTO coach_leaves(coach_id, from_date, to_date, leave_type, remarks, year)
        VALUES(?, ?, ?, ?, ?, ?)
    """, (coach_id, from_date, to_date, leave_type, remarks, year))


def _edit_leave(cur, form):
    """Edit an existing leave record."""
    leave_id = form.get("leave_id")
    coach_id = form.get("coach_id")
    from_date = form.get("from_date")
    to_date = form.get("to_date") or from_date
    leave_type = form.get("leave_type", "Casual")
    remarks = form.get("remarks", "").strip()
    
    cur.execute("""
        UPDATE coach_leaves 
        SET coach_id=?, from_date=?, to_date=?, leave_type=?, remarks=?
        WHERE id=?
    """, (coach_id, from_date, to_date, leave_type, remarks, leave_id))
