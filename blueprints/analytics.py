"""Analytics blueprint - Analytics and reporting routes."""

from datetime import datetime
from flask import Blueprint, render_template, request

from utils import get_db, login_required, CALENDAR_MONTHS

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route("/analytics")
@login_required
def analytics():
    """Analytics dashboard with charts and tables."""
    conn = get_db()
    cur = conn.cursor()
    year = int(request.args.get("year", datetime.now().year))
    
    # Get selected center (0 = All Centers)
    selected_center = request.args.get("center", "0")
    selected_center = int(selected_center) if selected_center else 0
    
    # Get selected months (comma-separated or empty for all)
    selected_months_str = request.args.get("months", "")
    if selected_months_str:
        selected_months = selected_months_str.split(",")
    else:
        selected_months = CALENDAR_MONTHS.copy()
    
    # Get all centers for dropdown
    centers = cur.execute("SELECT id, name FROM centers ORDER BY name").fetchall()
    
    # Get selected center name
    selected_center_name = "All Centers"
    if selected_center != 0:
        for c in centers:
            if c[0] == selected_center:
                selected_center_name = c[1]
                break
    
    # Build query based on center selection
    if selected_center == 0:
        # All centers
        cur.execute("""
            SELECT month, SUM(revenue) AS total_revenue, SUM(target) AS total_target
            FROM monthly_data
            WHERE year=?
            GROUP BY month
        """, (year,))
    else:
        # Specific center
        cur.execute("""
            SELECT month, SUM(revenue) AS total_revenue, SUM(target) AS total_target
            FROM monthly_data
            WHERE year=? AND center_id=?
            GROUP BY month
        """, (year, selected_center))
    
    rt_rows = cur.fetchall()
    revenue_target_by_month = {}
    for row in rt_rows:
        revenue_target_by_month[row["month"]] = {
            "total_revenue": row["total_revenue"] or 0,
            "total_target": row["total_target"] or 0,
        }

    # Get salary per month (filtered by center if needed)
    if selected_center == 0:
        cur.execute("""
            SELECT cs.month, SUM(cs.salary) AS total_salary
            FROM coach_salaries cs
            JOIN coaches c ON cs.coach_id = c.id
            WHERE cs.year=?
            GROUP BY cs.month
        """, (year,))
    else:
        cur.execute("""
            SELECT cs.month, SUM(cs.salary) AS total_salary
            FROM coach_salaries cs
            JOIN coaches c ON cs.coach_id = c.id
            WHERE cs.year=? AND c.center_id=?
            GROUP BY cs.month
        """, (year, selected_center))
    
    sal_rows = cur.fetchall()
    salary_by_month = {row["month"]: row["total_salary"] or 0 for row in sal_rows}

    # Build analytics data
    analytics_data = []
    total_revenue = 0
    total_target = 0
    total_salary = 0
    
    # For selected months calculation
    selected_revenue = 0
    selected_target = 0
    selected_count = 0

    for m in CALENDAR_MONTHS:
        totals = revenue_target_by_month.get(m, {"total_revenue": 0, "total_target": 0})
        revenue = totals["total_revenue"] or 0
        target = totals["total_target"] or 0
        salary = salary_by_month.get(m, 0) or 0

        achieved = round((revenue / target * 100), 1) if target > 0 else 0
        salary_ratio = round((salary / revenue * 100), 1) if revenue > 0 else 0
        profit = revenue - salary

        total_revenue += revenue
        total_target += target
        total_salary += salary
        
        # Track selected months data
        is_selected = m in selected_months
        if is_selected:
            selected_revenue += revenue
            selected_target += target
            selected_count += 1

        analytics_data.append({
            "month": m,
            "revenue": revenue,
            "target": target,
            "achieved": achieved,
            "salary_ratio": salary_ratio,
            "profit": profit,
            "is_selected": is_selected,
        })

    # Calculate averages for selected months
    avg_revenue = round(selected_revenue / selected_count, 2) if selected_count > 0 else 0
    avg_target = round(selected_target / selected_count, 2) if selected_count > 0 else 0
    avg_achievement = round((selected_revenue / selected_target * 100), 1) if selected_target > 0 else 0

    # Calculate growth data (month-to-month)
    growth_data = _calculate_growth(analytics_data)

    conn.close()

    return render_template(
        "analytics.html",
        analytics_data=analytics_data,
        growth_data=growth_data,
        total_revenue=total_revenue,
        total_target=total_target,
        avg_achievement=avg_achievement,
        year=year,
        centers=centers,
        selected_center=selected_center,
        selected_center_name=selected_center_name,
        selected_months=selected_months,
        calendar_months=CALENDAR_MONTHS,
        avg_revenue=avg_revenue,
        avg_target=avg_target,
        selected_revenue=selected_revenue,
        selected_target=selected_target,
        selected_count=selected_count,
    )


def _calculate_growth(analytics_data):
    """Calculate month-to-month growth percentages."""
    growth_data = []
    for i, data in enumerate(analytics_data):
        if i == 0:
            growth = 0
        else:
            prev_revenue = analytics_data[i - 1]["revenue"]
            if prev_revenue > 0:
                growth = round(((data["revenue"] - prev_revenue) / prev_revenue) * 100, 1)
            else:
                growth = 0

        direction = "📈" if growth > 0 else ("📉" if growth < 0 else "➡️")
        growth_data.append({
            "month": data["month"],
            "growth": growth,
            "direction": direction,
        })
    
    return growth_data
