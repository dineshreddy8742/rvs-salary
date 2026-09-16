import sqlite3
import json
import os
from typing import Dict, List, Any, Optional

DB_FILE = "rvs_attendance.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they do not exist."""
    conn = get_db()
    cursor = conn.cursor()

    # Employees Master Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        emp_code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        designation TEXT,
        department TEXT NOT NULL,
        annual_cl_quota REAL DEFAULT 12.0,
        annual_od_quota REAL DEFAULT 15.0,
        attendance_policy TEXT DEFAULT 'standard',
        is_manual INTEGER DEFAULT 0
    )
    """)

    # Monthly Attendance Records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_code TEXT NOT NULL,
        month_year TEXT NOT NULL,
        biometric_days REAL NOT NULL,
        holiday REAL NOT NULL,
        availed_leaves REAL,
        sv_od REAL,
        total_pay_days REAL NOT NULL,
        remarks TEXT,
        needs_review INTEGER DEFAULT 0,
        missed_punches_json TEXT,
        absent_days_json TEXT,
        late_punches_json TEXT,
        UNIQUE(emp_code, month_year),
        FOREIGN KEY(emp_code) REFERENCES employees(emp_code)
    )
    """)

    # Daily Punch Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_code TEXT NOT NULL,
        month_year TEXT NOT NULL,
        day_num INTEGER NOT NULL,
        date_str TEXT,
        in_time TEXT,
        out_time TEXT,
        duration TEXT,
        status TEXT,
        override_status TEXT,
        UNIQUE(emp_code, month_year, day_num),
        FOREIGN KEY(emp_code) REFERENCES employees(emp_code)
    )
    """)

    conn.commit()
    conn.close()

def get_available_months() -> List[str]:
    """Return all distinct month_years stored in database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [r['month_year'] for r in rows] if rows else ["August -2026"]

def seed_from_engine(engine, month_year: str = "August -2026"):
    """Populate database from an AttendanceEngine instance if empty."""
    conn = get_db()
    cursor = conn.cursor()

    # Check if month already seeded
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    if cursor.fetchone()['cnt'] > 0:
        conn.close()
        return

    print(f"Seeding database for {month_year}...")
    for emp_code, emp in engine.employees.items():
        # Set Principal and certain VIPs to exempt_full by default
        policy = 'exempt_full' if emp_code in ('101',) or 'principal' in str(emp.get('designation', '')).lower() else 'standard'
        
        cursor.execute("""
        INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
        VALUES (?, ?, ?, ?, 12.0, 15.0, ?, 0)
        """, (emp_code, emp['name'], emp['designation'], emp['department'], policy))

        summary = engine.calculate_employee_summary(emp)
        
        # If policy is exempt_full, give 31 full days
        if policy == 'exempt_full':
            total_days = 31.0
            bio_days = 25.0
            holidays = 6.0
            leaves = None
            od = None
            remarks = "Full Attendance (Exempt / Principal)"
            needs_review = 0
        else:
            total_days = summary['total_pay_days']
            bio_days = summary['biometric_days']
            holidays = summary['holiday']
            leaves = summary['availed_leaves']
            od = summary['sv_od']
            remarks = summary['remarks']
            needs_review = 1 if summary['needs_review'] else 0

        cursor.execute("""
        INSERT OR REPLACE INTO monthly_records 
        (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, missed_punches_json, absent_days_json, late_punches_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            emp_code, month_year, bio_days, holidays, leaves, od, total_days, remarks, needs_review,
            json.dumps(summary.get('missed_out_punches', [])),
            json.dumps(summary.get('absent_days', [])),
            json.dumps(summary.get('late_punches', []))
        ))

        # Seed daily logs
        for day in emp['days']:
            cursor.execute("""
            INSERT OR REPLACE INTO daily_logs (emp_code, month_year, day_num, date_str, in_time, out_time, duration, status, override_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emp_code, month_year, day['day'], day['date'], day['in_time'], day['out_time'],
                day['duration'], day['status'], day.get('override_status')
            ))

    # Also ensure any reference metadata employees (like Principal 101) exist
    if hasattr(engine, 'reference_metadata'):
        for ec, meta in engine.reference_metadata.items():
            cursor.execute("SELECT COUNT(*) as cnt FROM employees WHERE emp_code = ?", (ec,))
            if cursor.fetchone()['cnt'] == 0:
                is_principal = 'principal' in str(meta.get('designation', '')).lower() or ec == '101'
                pol = 'exempt_full' if is_principal else 'standard'
                cursor.execute("""
                INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
                VALUES (?, ?, ?, ?, 12.0, 15.0, ?, 1)
                """, (ec, meta['name'], meta['designation'], meta['dept'], pol))

                cursor.execute("""
                INSERT OR REPLACE INTO monthly_records 
                (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review)
                VALUES (?, ?, 25.0, 6.0, NULL, NULL, 31.0, ?, 0)
                """, (ec, month_year, "Full Attendance (VIP / Principal)" if is_principal else "Reference Staff"))

    conn.commit()
    conn.close()
    print(f"Database seeded successfully for {month_year}.")

def get_month_records(month_year: str, active_only: bool = True, reference_codes: Optional[set] = None) -> List[dict]:
    """Retrieve all employee summaries for a specific month."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT e.emp_code, e.name, e.designation, e.department, e.annual_cl_quota, e.annual_od_quota, e.attendance_policy, e.is_manual,
           m.biometric_days, m.holiday, m.availed_leaves, m.sv_od, m.total_pay_days, m.remarks, m.needs_review,
           m.missed_punches_json, m.absent_days_json, m.late_punches_json
    FROM monthly_records m
    JOIN employees e ON m.emp_code = e.emp_code
    WHERE m.month_year = ?
    """
    cursor.execute(query, (month_year,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        ec = r['emp_code']
        if active_only and reference_codes and ec not in reference_codes and not r['is_manual']:
            continue

        results.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'attendance_policy': r['attendance_policy'],
            'is_manual': bool(r['is_manual']),
            'biometric_days': r['biometric_days'],
            'holiday': r['holiday'],
            'availed_leaves': r['availed_leaves'],
            'sv_od': r['sv_od'],
            'total_pay_days': r['total_pay_days'],
            'remarks': r['remarks'] or '',
            'needs_review': bool(r['needs_review']),
            'missed_out_punches': json.loads(r['missed_punches_json'] or '[]'),
            'absent_days': json.loads(r['absent_days_json'] or '[]'),
            'late_punches': json.loads(r['late_punches_json'] or '[]')
        })

    return results

def get_employee_portfolio(emp_code: str) -> Optional[dict]:
    """
    Retrieve 360° Employee Dossier:
    - Profile & Policy
    - Annual CL quota, availed so far, and remaining balance
    - Annual OD days availed
    - Month-by-month salary pay days table
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM employees WHERE emp_code = ?", (emp_code,))
    emp = cursor.fetchone()
    if not emp:
        conn.close()
        return None

    # Get all monthly records
    cursor.execute("""
    SELECT month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks
    FROM monthly_records
    WHERE emp_code = ?
    ORDER BY id ASC
    """, (emp_code,))
    months = cursor.fetchall()
    conn.close()

    total_cl_availed = 0.0
    total_od_availed = 0.0
    total_pay_days_cum = 0.0
    monthly_history = []

    for m in months:
        cl = float(m['availed_leaves'] or 0.0)
        od = float(m['sv_od'] or 0.0)
        pay_days = float(m['total_pay_days'] or 0.0)

        total_cl_availed += cl
        total_od_availed += od
        total_pay_days_cum += pay_days

        monthly_history.append({
            'month_year': m['month_year'],
            'biometric_days': m['biometric_days'],
            'holiday': m['holiday'],
            'availed_leaves': cl,
            'sv_od': od,
            'total_pay_days': pay_days,
            'remarks': m['remarks'] or ''
        })

    cl_quota = float(emp['annual_cl_quota'] or 12.0)
    cl_balance = max(0.0, cl_quota - total_cl_availed)
    is_over_leave = total_cl_availed > cl_quota

    return {
        'emp_code': emp['emp_code'],
        'name': emp['name'],
        'designation': emp['designation'] or 'Staff',
        'department': emp['department'],
        'attendance_policy': emp['attendance_policy'],
        'is_manual': bool(emp['is_manual']),
        'annual_cl_quota': cl_quota,
        'total_cl_availed': total_cl_availed,
        'cl_balance': round(cl_balance, 1),
        'is_over_leave': is_over_leave,
        'annual_od_quota': float(emp['annual_od_quota'] or 15.0),
        'total_od_availed': total_od_availed,
        'total_pay_days_cum': round(total_pay_days_cum, 1),
        'months': monthly_history
    }

def get_employee_daily_logs(emp_code: str, month_year: str) -> List[dict]:
    """Fetch daily punch logs for an employee for a specific month."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT day_num, date_str, in_time, out_time, duration, status, override_status
    FROM daily_logs
    WHERE emp_code = ? AND month_year = ?
    ORDER BY day_num ASC
    """, (emp_code, month_year))
    rows = cursor.fetchall()
    conn.close()

    return [{
        'day': r['day_num'],
        'date': r['date_str'],
        'in_time': r['in_time'] or '',
        'out_time': r['out_time'] or '',
        'duration': r['duration'] or '',
        'status': r['status'] or '',
        'override_status': r['override_status']
    } for r in rows]

def create_or_update_manual_employee(emp_data: dict, current_month: str = "August -2026") -> dict:
    """Manually add an employee (Principal, visiting faculty, etc.) and give initial attendance."""
    conn = get_db()
    cursor = conn.cursor()

    emp_code = str(emp_data['emp_code']).strip()
    name = str(emp_data['name']).strip()
    desig = str(emp_data.get('designation', 'Staff')).strip()
    dept = str(emp_data.get('department', 'Administration')).strip()
    policy = str(emp_data.get('attendance_policy', 'exempt_full')).strip()
    quota = float(emp_data.get('annual_cl_quota', 12.0))

    cursor.execute("""
    INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
    VALUES (?, ?, ?, ?, ?, 15.0, ?, 1)
    """, (emp_code, name, desig, dept, quota, policy))

    # Determine monthly values based on policy
    if policy in ('exempt_full', 'visiting_twice_weekly'):
        bio_days = 25.0
        holiday = 6.0
        total_pay = 31.0
        remarks = "Full Attendance (VIP / Exempt)" if policy == 'exempt_full' else "Full Attendance (Visiting Schedule)"
        needs_review = 0
    else:
        bio_days = float(emp_data.get('biometric_days', 25.0))
        holiday = 6.0
        total_pay = bio_days + holiday
        remarks = "Manually Added Staff"
        needs_review = 0

    cursor.execute("""
    INSERT OR REPLACE INTO monthly_records 
    (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review)
    VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?)
    """, (emp_code, current_month, bio_days, holiday, total_pay, remarks, needs_review))

    conn.commit()
    conn.close()

    return get_employee_portfolio(emp_code)

def set_employee_policy(emp_code: str, policy: str, month_year: str = "August -2026"):
    """Update policy for an employee and recalculate monthly pay days if exempt."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE employees SET attendance_policy = ? WHERE emp_code = ?", (policy, emp_code))

    if policy in ('exempt_full', 'visiting_twice_weekly'):
        remarks = "Full Attendance (VIP / Exempt)" if policy == 'exempt_full' else "Full Attendance (Visiting Schedule)"
        cursor.execute("""
        UPDATE monthly_records
        SET biometric_days = 25.0, holiday = 6.0, total_pay_days = 31.0, remarks = ?, needs_review = 0
        WHERE emp_code = ? AND month_year = ?
        """, (remarks, emp_code, month_year))

    conn.commit()
    conn.close()

def grant_full_attendance(emp_code: str, month_year: str):
    """1-Click button to give an employee 31 full pay days for the current month."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = 25.0, holiday = 6.0, total_pay_days = 31.0, remarks = 'Full Attendance Granted by HR', needs_review = 0
    WHERE emp_code = ? AND month_year = ?
    """, (emp_code, month_year))

    conn.commit()
    conn.close()

def update_monthly_field(emp_code: str, month_year: str, field: str, value: Any):
    """Update an inline field (leaves, od, holiday, bio) in SQLite and recalculate Total Pay Days."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM monthly_records WHERE emp_code = ? AND month_year = ?", (emp_code, month_year))
    record = cursor.fetchone()
    if not record:
        conn.close()
        raise ValueError(f"Record for {emp_code} in {month_year} not found")

    val_float = float(value) if value is not None and str(value).strip() != '' else None

    bio = record['biometric_days']
    hol = record['holiday']
    leaves = record['availed_leaves']
    od = record['sv_od']

    if field in ('availed_leaves', 'cl', 'leaves'):
        leaves = val_float
        cursor.execute("UPDATE monthly_records SET availed_leaves = ? WHERE emp_code = ? AND month_year = ?", (val_float, emp_code, month_year))
    elif field in ('sv_od', 'od'):
        od = val_float
        cursor.execute("UPDATE monthly_records SET sv_od = ? WHERE emp_code = ? AND month_year = ?", (val_float, emp_code, month_year))
    elif field == 'holiday':
        hol = val_float or 6.0
        cursor.execute("UPDATE monthly_records SET holiday = ? WHERE emp_code = ? AND month_year = ?", (hol, emp_code, month_year))
    elif field == 'biometric_days':
        bio = val_float or 0.0
        cursor.execute("UPDATE monthly_records SET biometric_days = ? WHERE emp_code = ? AND month_year = ?", (bio, emp_code, month_year))

    # Recalculate total
    total = bio + hol + (leaves or 0.0) + (od or 0.0)
    total = min(31.0, total)
    cursor.execute("UPDATE monthly_records SET total_pay_days = ? WHERE emp_code = ? AND month_year = ?", (total, emp_code, month_year))

    conn.commit()
    conn.close()

def regularize_day_in_db(emp_code: str, month_year: str, day_num: int, action: str):
    """Regularize a day in SQLite: update daily_logs, re-sum, and update monthly_records."""
    conn = get_db()
    cursor = conn.cursor()

    status_map = {
        'cl': 'On Leave(CL)',
        'od': 'Present On OD',
        'present': 'Present',
        'half_day': '1/2Present',
        'absent': 'Absent',
        'reset': None
    }
    new_status = status_map.get(action)

    cursor.execute("""
    UPDATE daily_logs SET override_status = ? WHERE emp_code = ? AND month_year = ? AND day_num = ?
    """, (new_status, emp_code, month_year, day_num))

    # Re-evaluate all days for this employee
    cursor.execute("SELECT * FROM daily_logs WHERE emp_code = ? AND month_year = ? ORDER BY day_num ASC", (emp_code, month_year))
    days = cursor.fetchall()

    present_count = 0.0
    cl_count = 0.0
    od_count = 0.0
    absent_days = []
    missed_punches = []

    for d in days:
        st = (d['override_status'] or d['status'] or '').upper()
        d_num = d['day_num']
        if 'CL' in st or 'LEAVE' in st:
            if '1/2' in st:
                cl_count += 0.5
                if 'PRESENT' in st: present_count += 0.5
            else:
                cl_count += 1.0
        elif 'OD' in st or 'ON DUTY' in st:
            od_count += 1.0
        elif 'PRESENT' in st:
            if '1/2' in st: present_count += 0.5
            else: present_count += 1.0
        elif 'NO OUTPUNCH' in st or 'NO OUT PUNCH' in st:
            missed_punches.append(d_num)
        elif 'ABSENT' in st and 'HOLIDAY' not in st:
            absent_days.append(d_num)

    cursor.execute("SELECT holiday FROM monthly_records WHERE emp_code = ? AND month_year = ?", (emp_code, month_year))
    hol = cursor.fetchone()['holiday']

    total = present_count + hol + cl_count + od_count
    total = min(31.0, total)

    rem_parts = []
    if absent_days: rem_parts.append(f"ab-{','.join(str(d) for d in absent_days)}")
    if missed_punches: rem_parts.append(f"{','.join(str(d) for d in missed_punches)} no out punch")
    rem_str = ", ".join(rem_parts)

    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?, availed_leaves = ?, sv_od = ?, total_pay_days = ?, remarks = ?, needs_review = ?
    WHERE emp_code = ? AND month_year = ?
    """, (present_count, cl_count if cl_count > 0 else None, od_count if od_count > 0 else None, total, rem_str, 1 if (absent_days or missed_punches) else 0, emp_code, month_year))

    conn.commit()
    conn.close()
