import sqlite3
import json
import os
import re
from typing import Dict, List, Any, Optional
import payroll_engine

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

    # Salary Profiles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salary_profiles (
        emp_code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'Non-Teaching',
        designation TEXT,
        department TEXT,
        base_salary REAL DEFAULT 0.0,
        bank_name TEXT DEFAULT 'PNB',
        account_no TEXT,
        ifsc_code TEXT,
        epf_amount REAL DEFAULT 0.0,
        default_arrears REAL DEFAULT 0.0,
        FOREIGN KEY(emp_code) REFERENCES employees(emp_code)
    )
    """)

    # Ensure salary columns exist in monthly_records
    cursor.execute("PRAGMA table_info(monthly_records)")
    existing_cols = [r['name'] for r in cursor.fetchall()]
    salary_cols = {
        'base_salary': 'REAL',
        'earned_basic': 'REAL',
        'earned_da': 'REAL',
        'earned_hra': 'REAL',
        'arrears': 'REAL DEFAULT 0.0',
        'gross_salary': 'REAL',
        'pt_deduction': 'REAL',
        'wf_deduction': 'REAL',
        'epf_deduction': 'REAL',
        'it_deduction': 'REAL',
        'other_deductions': 'REAL DEFAULT 0.0',
        'total_deductions': 'REAL',
        'net_salary': 'REAL'
    }
    for col_name, col_type in salary_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE monthly_records ADD COLUMN {col_name} {col_type}")

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

    try:
        recalculate_monthly_salary(emp_code, month_year, 31.0)
    except Exception as e:
        print(f"Error recalculating salary: {e}")

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

    try:
        recalculate_monthly_salary(emp_code, month_year, total)
    except Exception as e:
        print(f"Error recalculating salary: {e}")

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

    # Recalculate salary with new pay days
    try:
        recalculate_monthly_salary(emp_code, month_year, total)
    except Exception as e:
        print(f"Error recalculating salary for {emp_code}: {e}")

# =============================================================================
# PAYROLL & SALARY PROFILE MANAGEMENT
# =============================================================================

def seed_salary_profiles_from_reference(database_dir: str = 'database'):
    """
    Seed salary_profiles table using historical records extracted from database/
    and link them to employees in rvs_attendance.db.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Check how many profiles already exist
    cursor.execute("SELECT COUNT(*) as cnt FROM salary_profiles")
    if cursor.fetchone()['cnt'] > 50:
        conn.close()
        return

    print("Seeding salary profiles from historical reference documents...")
    extracted = payroll_engine.extract_historical_salary_profiles(database_dir)

    cursor.execute("SELECT emp_code, name, designation, department FROM employees")
    employees = cursor.fetchall()

    def norm(s):
        if not s: return ''
        s = s.lower().replace('.', ' ').replace(',', ' ')
        s = re.sub(r'\b(dr|prof|mr|ms|mrs|assoc|asst)\b', '', s)
        return re.sub(r'[^a-z0-9]', '', s)

    matched_count = 0
    for emp in employees:
        ec = emp['emp_code']
        raw_name = emp['name']
        dept = emp['department']
        desig = emp['designation'] or ''
        n_key = norm(raw_name)

        # Check match in extracted historical salary sheets
        prof = extracted.get(n_key)
        if not prof:
            # Try matching by checking if any key in extracted is substring
            for k, p in extracted.items():
                if len(k) >= 5 and (k in n_key or n_key in k):
                    prof = p
                    break

        dept_lower = (dept or '').lower()
        if prof:
            category = prof['category']
            base_sal = float(prof['base_salary'])
            bank_acc = prof['account_no']
            ifsc = prof['ifsc_code']
            epf = float(prof.get('epf_amount', 0.0))
            matched_count += 1
        else:
            # Fallback based on department / designation
            if any(k in dept_lower for k in ['garden']):
                category = 'Garden Staff'
                base_sal = 12000.0
            elif any(k in dept_lower for k in ['security']):
                category = 'Security'
                base_sal = 15000.0
            elif any(k in dept_lower for k in ['attender']):
                category = 'Attender'
                base_sal = 10000.0
            elif any(k in dept_lower for k in ['transport', 'driver']):
                category = 'Transport'
                base_sal = 16000.0
            elif any(k in dept_lower for k in ['admission']):
                category = 'Admission'
                base_sal = 25000.0
            elif any(k in dept_lower for k in ['management', 'administration']):
                category = 'Management' if 'management' in dept_lower else 'Non-Teaching'
                base_sal = 35000.0 if 'principal' in desig.lower() or ec == '101' else 22000.0
            else:
                category = 'Teaching'
                base_sal = 160000.0 if ec == '101' or 'principal' in desig.lower() else (45000.0 if 'assoc' in desig.lower() else 35000.0)

            bank_acc = ''
            ifsc = 'PUNB0401700'
            epf = 0.0

        cursor.execute("""
        INSERT OR REPLACE INTO salary_profiles 
        (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount, default_arrears)
        VALUES (?, ?, ?, ?, ?, ?, 'PNB', ?, ?, ?, 0.0)
        """, (ec, raw_name, category, desig, dept, base_sal, bank_acc, ifsc, epf))

    conn.commit()
    conn.close()
    print(f"Seeded {matched_count} salary profiles matched from reference files.")

    # Populate monthly salary for all available months
    for m in get_available_months():
        populate_month_salaries_if_empty(m)

def get_employee_salary_profile(emp_code: str) -> Optional[dict]:
    """Retrieve an employee's salary profile."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salary_profiles WHERE emp_code = ?", (emp_code,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_employee_salary_profile(emp_code: str, data: dict):
    """Update base salary, category, or bank details."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE salary_profiles
    SET base_salary = ?, category = ?, account_no = ?, ifsc_code = ?, epf_amount = ?
    WHERE emp_code = ?
    """, (
        float(data.get('base_salary', 0.0)),
        data.get('category', 'Non-Teaching'),
        data.get('account_no', ''),
        data.get('ifsc_code', ''),
        float(data.get('epf_amount', 0.0)),
        emp_code
    ))
    conn.commit()
    conn.close()

def recalculate_monthly_salary(emp_code: str, month_year: str, total_pay_days: Optional[float] = None, month_days: Optional[int] = None) -> dict:
    """Calculate and save gross, deductions, and net salary for a given month."""
    conn = get_db()
    cursor = conn.cursor()

    # Get employee salary profile
    cursor.execute("SELECT * FROM salary_profiles WHERE emp_code = ?", (emp_code,))
    prof_row = cursor.fetchone()
    if not prof_row:
        # Fallback profile
        cursor.execute("SELECT * FROM employees WHERE emp_code = ?", (emp_code,))
        emp_row = cursor.fetchone()
        if not emp_row:
            conn.close()
            return {}
        prof = {
            'emp_code': emp_code,
            'name': emp_row['name'],
            'category': 'Teaching' if emp_row['department'] in ('CE','EEE','ME','ECE','CSE','CSM','CSD','CAI','IT','MCA','MBA','HAS') else 'Non-Teaching',
            'base_salary': 35000.0,
            'default_arrears': 0.0,
            'epf_amount': 0.0
        }
    else:
        prof = dict(prof_row)

    # Get monthly attendance record
    cursor.execute("SELECT * FROM monthly_records WHERE emp_code = ? AND month_year = ?", (emp_code, month_year))
    rec = cursor.fetchone()
    if not rec:
        conn.close()
        return {}

    pay_days = float(total_pay_days if total_pay_days is not None else rec['total_pay_days'])
    m_days = month_days or payroll_engine.get_days_in_month_str(month_year)

    # Apply any existing monthly overrides from record
    overrides = {
        'base_salary': rec['base_salary'] if rec['base_salary'] is not None else prof.get('base_salary'),
        'arrears': rec['arrears'] or 0.0,
        'epf_deduction': rec['epf_deduction'] if rec['epf_deduction'] is not None else prof.get('epf_amount', 0.0),
        'it_deduction': rec['it_deduction'] or 0.0,
        'other_deductions': rec['other_deductions'] or 0.0
    }

    res = payroll_engine.calculate_salary_for_profile(prof, m_days, pay_days, overrides)

    cursor.execute("""
    UPDATE monthly_records
    SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
        gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
        it_deduction = ?, other_deductions = ?, total_deductions = ?, net_salary = ?
    WHERE emp_code = ? AND month_year = ?
    """, (
        res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
        res['gross_salary'], res['pt'], res['wf'], res['epf'],
        res['it'], res['other_deductions'], res['total_deductions'], res['net_salary'],
        emp_code, month_year
    ))

    conn.commit()
    conn.close()
    return res

def populate_month_salaries_if_empty(month_year: str):
    """Ensure all employees in a month have computed salary figures."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT emp_code, total_pay_days, net_salary FROM monthly_records WHERE month_year = ?", (month_year,))
    rows = cursor.fetchall()
    conn.close()

    m_days = payroll_engine.get_days_in_month_str(month_year)
    for r in rows:
        if r['net_salary'] is None:
            recalculate_monthly_salary(r['emp_code'], month_year, float(r['total_pay_days']), m_days)

def get_month_salary_records(month_year: str, active_only: bool = True, reference_codes: Optional[set] = None) -> dict:
    """Retrieve full payroll ledger with financial KPI totals for the active month."""
    populate_month_salaries_if_empty(month_year)

    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT m.emp_code, e.name, e.designation, e.department, e.attendance_policy, e.is_manual,
           m.biometric_days, m.holiday, m.availed_leaves, m.sv_od, m.total_pay_days, m.remarks,
           m.base_salary, m.earned_basic, m.earned_da, m.earned_hra, m.arrears,
           m.gross_salary, m.pt_deduction, m.wf_deduction, m.epf_deduction, m.it_deduction,
           m.other_deductions, m.total_deductions, m.net_salary,
           p.category, p.bank_name, p.account_no, p.ifsc_code
    FROM monthly_records m
    JOIN employees e ON m.emp_code = e.emp_code
    LEFT JOIN salary_profiles p ON m.emp_code = p.emp_code
    WHERE m.month_year = ?
    """
    cursor.execute(query, (month_year,))
    rows = cursor.fetchall()
    conn.close()

    records = []
    tot_budget = 0.0
    tot_gross = 0.0
    tot_pt = 0.0
    tot_wf = 0.0
    tot_epf = 0.0
    tot_it = 0.0
    tot_ded = 0.0
    tot_net = 0.0

    for r in rows:
        ec = r['emp_code']
        if active_only and reference_codes and ec not in reference_codes and not r['is_manual']:
            continue

        base_sal = float(r['base_salary'] or 0.0)
        gross = float(r['gross_salary'] or 0.0)
        pt = float(r['pt_deduction'] or 0.0)
        wf = float(r['wf_deduction'] or 0.0)
        epf = float(r['epf_deduction'] or 0.0)
        it = float(r['it_deduction'] or 0.0)
        ded = float(r['total_deductions'] or 0.0)
        net = float(r['net_salary'] or 0.0)

        tot_budget += base_sal
        tot_gross += gross
        tot_pt += pt
        tot_wf += wf
        tot_epf += epf
        tot_it += it
        tot_ded += ded
        tot_net += net

        records.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'category': r['category'] or 'Non-Teaching',
            'attendance_policy': r['attendance_policy'],
            'total_pay_days': r['total_pay_days'],
            'base_salary': base_sal,
            'earned_basic': r['earned_basic'] or 0.0,
            'earned_da': r['earned_da'] or 0.0,
            'earned_hra': r['earned_hra'] or 0.0,
            'arrears': r['arrears'] or 0.0,
            'gross_salary': gross,
            'pt_deduction': pt,
            'wf_deduction': wf,
            'epf_deduction': epf,
            'it_deduction': it,
            'other_deductions': r['other_deductions'] or 0.0,
            'total_deductions': ded,
            'net_salary': net,
            'bank_name': r['bank_name'] or 'PNB',
            'account_no': r['account_no'] or '',
            'ifsc_code': r['ifsc_code'] or '',
            'remarks': r['remarks'] or ''
        })

    departments = sorted(list(set(r['department'] for r in records)))
    categories = sorted(list(set(r['category'] for r in records)))

    return {
        'status': 'success',
        'month_year': month_year,
        'stats': {
            'total_staff': len(records),
            'total_payroll_budget': round(tot_budget, 2),
            'total_gross_disbursed': round(tot_gross, 2),
            'total_pt_deductions': round(tot_pt, 2),
            'total_wf_deductions': round(tot_wf, 2),
            'total_epf_deductions': round(tot_epf, 2),
            'total_it_deductions': round(tot_it, 2),
            'total_all_deductions': round(tot_ded, 2),
            'total_net_disbursed': round(tot_net, 2)
        },
        'departments': departments,
        'categories': categories,
        'records': records
    }

def update_monthly_salary_field(emp_code: str, month_year: str, field: str, value: Any) -> dict:
    """Update base salary, arrears, epf, it, or other deductions for an employee in a month."""
    conn = get_db()
    cursor = conn.cursor()

    val_float = float(value) if value is not None and str(value).strip() != '' else 0.0

    allowed_fields = {
        'base_salary': 'base_salary',
        'arrears': 'arrears',
        'epf_deduction': 'epf_deduction',
        'it_deduction': 'it_deduction',
        'other_deductions': 'other_deductions'
    }
    col = allowed_fields.get(field)
    if not col:
        conn.close()
        raise ValueError(f"Invalid salary field: {field}")

    cursor.execute(f"UPDATE monthly_records SET {col} = ? WHERE emp_code = ? AND month_year = ?", (val_float, emp_code, month_year))

    # Also update salary_profiles if base_salary changed
    if field == 'base_salary' and val_float > 0:
        cursor.execute("UPDATE salary_profiles SET base_salary = ? WHERE emp_code = ?", (val_float, emp_code))

    conn.commit()
    conn.close()

    # Recalculate salary for this employee
    return recalculate_monthly_salary(emp_code, month_year)
