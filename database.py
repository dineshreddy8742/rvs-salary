import sqlite3
import json
import os
import re
from typing import Dict, List, Any, Optional
import payroll_engine

DB_FILE = "rvs_attendance.db"

# Canonical mapping for department normalization to eliminate duplicate/fragmented departments
DEPARTMENT_CANONICAL_MAP = {
    'ADMIN': 'Administration',
    'ADMINISTRATION': 'Administration',
    'SECURITY': 'Security & Water Staff',
    'SECURITY & WATER STAFF': 'Security & Water Staff',
    'SECURITY AND WATER STAFF': 'Security & Water Staff',
    'TRANSPORT': 'Transport',
    'MECH': 'ME',
    'MECHANICAL': 'ME',
    'EXAM SECTION': 'Exam Section',
    'EXAM': 'Exam Section',
    'ELECTRIATIONS': 'Electriations',
    'ELECTRICIAN': 'Electriations',
    'ELECTRICIANS': 'Electriations',
    'HOUSKEEPING': 'Attender',
    'HOUSE KEEPING': 'Attender',
    'HOUSEKEEPING': 'Attender',
    'ATTENDER': 'Attender',
    'ATTENDERS': 'Attender',
    'SBF-SLH': 'SLH',
    'SLH': 'SLH',
    'GARDEN': 'Garden Staff',
    'GARDEN STAFF': 'Garden Staff',
    'MANAGEMENT': 'Management Staff',
    'MANAGEMENT STAFF': 'Management Staff',
}

def normalize_dept(dept_name: str) -> str:
    """Normalize raw department string to official institutional department name."""
    if not dept_name:
        return 'General'
    cleaned = str(dept_name).strip()
    return DEPARTMENT_CANONICAL_MAP.get(cleaned.upper(), cleaned)

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
        default_bus REAL DEFAULT 0.0,
        default_mess REAL DEFAULT 0.0,
        default_hostel_eb REAL DEFAULT 0.0,
        default_arrears REAL DEFAULT 0.0,
        FOREIGN KEY(emp_code) REFERENCES employees(emp_code)
    )
    """)

    # Ensure profile columns exist in salary_profiles
    cursor.execute("PRAGMA table_info(salary_profiles)")
    existing_prof_cols = [r['name'] for r in cursor.fetchall()]
    prof_cols = {
        'default_bus': 'REAL DEFAULT 0.0',
        'default_mess': 'REAL DEFAULT 0.0',
        'default_hostel_eb': 'REAL DEFAULT 0.0'
    }
    for col_name, col_type in prof_cols.items():
        if col_name not in existing_prof_cols:
            cursor.execute(f"ALTER TABLE salary_profiles ADD COLUMN {col_name} {col_type}")

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
        'bus_deduction': 'REAL DEFAULT 0.0',
        'mess_deduction': 'REAL DEFAULT 0.0',
        'hostel_eb_deduction': 'REAL DEFAULT 0.0',
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
    """Return all distinct month_years stored in database, prioritizing August -2026."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records ORDER BY CASE WHEN month_year LIKE 'August%2026%' THEN 0 ELSE 1 END, id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [r['month_year'] for r in rows]

def has_monthly_records() -> bool:
    """Check if monthly_records table has any rows."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records")
    cnt = cursor.fetchone()['cnt']
    conn.close()
    return cnt > 0

def delete_month_data(month_year: str) -> dict:
    """Delete all monthly records and daily logs for the specified month."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    rec_count = cursor.fetchone()['cnt']
    cursor.execute("DELETE FROM monthly_records WHERE month_year = ?", (month_year,))
    cursor.execute("DELETE FROM daily_logs WHERE month_year = ?", (month_year,))
    conn.commit()
    conn.close()
    return {
        'status': 'success',
        'message': f'Successfully deleted {rec_count} records for {month_year}',
        'deleted_count': rec_count
    }

def get_month_summary_info(month_year: str) -> dict:
    """Return record count and punch log count for a given month."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    rec_count = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) as cnt FROM daily_logs WHERE month_year = ?", (month_year,))
    log_count = cursor.fetchone()['cnt']
    conn.close()
    return {
        'month_year': month_year,
        'records_count': rec_count,
        'logs_count': log_count
    }

def seed_from_engine(engine, month_year: str = "August -2026", overwrite: bool = False):
    """Populate database from an AttendanceEngine instance."""
    conn = get_db()
    cursor = conn.cursor()

    # Check if month already seeded
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    already_exists = cursor.fetchone()['cnt'] > 0
    if already_exists and not overwrite:
        conn.close()
        return

    if already_exists and overwrite:
        print(f"Overwriting existing records for {month_year}...")
        cursor.execute("DELETE FROM monthly_records WHERE month_year = ?", (month_year,))
        cursor.execute("DELETE FROM daily_logs WHERE month_year = ?", (month_year,))

    print(f"Seeding database for {month_year}...")
    vip_full_pay_codes = {'101', '707', '900', '1060', '1015', '1019', '1021', '4001', '1030', 'SHAJAHAN', 'SHIVA_DRIVER'}

    for emp_code, emp in engine.employees.items():
        name_l = str(emp.get('name', '')).lower()
        desig_l = str(emp.get('designation', '')).lower()
        dept_l = str(emp.get('department', '')).lower()

        is_vip = (emp_code in vip_full_pay_codes or 
                  'principal' in desig_l or 
                  any(k in name_l for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'bishal kumar', 'shajahan']) or
                  ('siva' in name_l and ('driver' in desig_l or 'transport' in dept_l)))
        policy = 'exempt_full' if is_vip else 'standard'
        
        cursor.execute("""
        INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
        VALUES (?, ?, ?, ?, 12.0, 15.0, ?, 0)
        """, (emp_code, emp['name'], emp['designation'], normalize_dept(emp['department']), policy))

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
    apply_principal_rules_to_db(month_year)

def apply_principal_rules_to_db(month_year: str = "August -2026"):
    """
    Enforce Principal Sir's 21 attendance rules directly on database records:
    - 101, 707, 900, 1060, 1015, 1019, 1021, 4001, 1030, Shajahan, Siva driver: 31 full days.
    - 1053: >=12 days -> 31 full days.
    - 1203: >=14 days -> 31 full days.
    - 536: CSE Bala Subramanyam before 12:10 = full day.
    - 109: Civil M. Lilaakar before 11:00 am = full day.
    - Transport IDs: no late penalties, no out punch counted as present.
    - Electricians: 8:30 in, 16:30 out full day no penalty.
    - Attenders / Garden: 8:35 in threshold.
    - Admission: 6 days/week, Sunday work offsets absent.
    """
    conn = get_db()
    cursor = conn.cursor()

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 31)
    holidays = 6.0
    bio_days = max(0.0, m_days - holidays)

    # Known VIP / Exempt staff who may not exist in raw biometric machines
    NON_BIOMETRIC_STAFF = {
        '101': {'name': 'Dr .M. Mohan Babu', 'dept': 'General', 'desig': 'Principal'},
        '707': {'name': 'R. Gunasekaran', 'dept': 'IT', 'desig': 'Asst.Prof'},
        '900': {'name': 'I. Sudarsan Kumar', 'dept': 'HAS', 'desig': 'Professor & DAP'},
        '1060': {'name': 'Vivekanand Adhikari', 'dept': 'Administration', 'desig': 'IR Officer'},
        '1015': {'name': 'R Hari Krishna', 'dept': 'Exam Section', 'desig': 'Clerk'},
        '1019': {'name': 'Bishal Kumar Sha', 'dept': 'TAP', 'desig': 'Executive Assistant'},
        '1021': {'name': 'M P Balaji', 'dept': 'Management Staff', 'desig': 'Accounts Officer'},
        '4001': {'name': 'R. Poorna Chandra', 'dept': 'Management Staff', 'desig': 'Administrative officer'},
        '1030': {'name': 'Thangeeru Surendera', 'dept': 'Transport', 'desig': 'VC Driver'},
        'SHAJAHAN': {'name': 'S Shajahan', 'dept': 'Management Staff', 'desig': 'P A To Chairman'},
        'SHIVA_DRIVER': {'name': 'Shiva', 'dept': 'Transport', 'desig': 'Principal Diver'},
    }

    # 1. Ensure all designated VIP staff exist in employees table & monthly_records for this month
    for vc, meta in NON_BIOMETRIC_STAFF.items():
        # Ensure employee row exists
        cursor.execute("SELECT COUNT(*) as cnt FROM employees WHERE emp_code = ?", (vc,))
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute("""
            INSERT INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
            VALUES (?, ?, ?, ?, 12.0, 15.0, 'exempt_full', 1)
            """, (vc, meta['name'], meta['desig'], meta['dept']))
        else:
            cursor.execute("UPDATE employees SET attendance_policy = 'exempt_full' WHERE emp_code = ?", (vc,))

        # Ensure monthly_records row exists for this specific month (even if absent from uploaded Excel)
        cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE emp_code = ? AND month_year = ?", (vc, month_year))
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute("""
            INSERT INTO monthly_records 
            (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, absent_days_json, missed_punches_json, late_punches_json)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, 'Full Attendance (Principal Override)', 0, '[]', '[]', '[]')
            """, (vc, month_year, bio_days, holidays, m_days))
        else:
            cursor.execute("""
            UPDATE monthly_records 
            SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = 'Full Attendance (Principal Override)', needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
            WHERE emp_code = ? AND month_year = ?
            """, (bio_days, holidays, m_days, vc, month_year))

    # Name-based checks for other VIPs in database
    cursor.execute("SELECT emp_code, name, designation, department FROM employees")
    emps = cursor.fetchall()
    for e in emps:
        ec = e['emp_code']
        nl = (e['name'] or '').lower()
        dl = (e['designation'] or '').lower()
        deptl = (e['department'] or '').lower()
        
        if (any(k in nl for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'shajahan']) or 
            ('siva' in nl and ('driver' in dl or 'transport' in deptl))):
            cursor.execute("UPDATE employees SET attendance_policy = 'exempt_full' WHERE emp_code = ?", (ec,))
            cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE emp_code = ? AND month_year = ?", (ec, month_year))
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute("""
                INSERT INTO monthly_records 
                (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, absent_days_json, missed_punches_json, late_punches_json)
                VALUES (?, ?, ?, ?, NULL, NULL, ?, 'Full Attendance (Principal Override)', 0, '[]', '[]', '[]')
                """, (ec, month_year, bio_days, holidays, m_days))
            else:
                cursor.execute("""
                UPDATE monthly_records 
                SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = 'Full Attendance (Principal Override)', needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
                WHERE emp_code = ? AND month_year = ?
                """, (bio_days, holidays, m_days, ec, month_year))

    # Also ensure any other employee marked as 'exempt_full' gets full pay for this month
    cursor.execute("SELECT emp_code FROM employees WHERE attendance_policy = 'exempt_full'")
    exempt_rows = cursor.fetchall()
    for row in exempt_rows:
        x_ec = row['emp_code']
        cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE emp_code = ? AND month_year = ?", (x_ec, month_year))
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute("""
            INSERT INTO monthly_records 
            (emp_code, month_year, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, absent_days_json, missed_punches_json, late_punches_json)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, 'Full Attendance (VIP / Exempt)', 0, '[]', '[]', '[]')
            """, (x_ec, month_year, bio_days, holidays, m_days))

    # 2. 1053 (S. Pachaiyappan) - >=12 days
    cursor.execute("SELECT biometric_days, total_pay_days FROM monthly_records WHERE emp_code = '1053' AND month_year = ?", (month_year,))
    r1053 = cursor.fetchone()
    if r1053 and (float(r1053['biometric_days'] or 0) >= 12 or float(r1053['total_pay_days'] or 0) >= 12):
        cursor.execute("""
        UPDATE monthly_records 
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = 'Full Attendance (Principal Override)', needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
        WHERE emp_code = '1053' AND month_year = ?
        """, (bio_days, holidays, m_days, month_year))

    # 3. 1203 (Dr J Velmurugan, IT HOD) - >=14 days
    cursor.execute("SELECT biometric_days, total_pay_days FROM monthly_records WHERE emp_code = '1203' AND month_year = ?", (month_year,))
    r1203 = cursor.fetchone()
    if r1203 and (float(r1203['biometric_days'] or 0) >= 14 or float(r1203['total_pay_days'] or 0) >= 14):
        cursor.execute("""
        UPDATE monthly_records 
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = 'Full Attendance (Principal Override)', needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
        WHERE emp_code = '1203' AND month_year = ?
        """, (bio_days, holidays, m_days, month_year))

    # 4. 109 (Civil M. Leelakar) - daily punch before 11 am is handled by attendance engine
    # (Do not blindly set to 31.0; preserve actual attendance calculated from punches)

    # 5. Transport Dept: remove late punch penalties & credit full days for in+out punches
    transport_ids = ['625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613']
    for tid in transport_ids:
        cursor.execute("SELECT * FROM daily_logs WHERE emp_code = ? AND month_year = ? ORDER BY day_num", (tid, month_year))
        tdays = cursor.fetchall()
        if tdays:
            in_out_count = sum(1.0 for d in tdays if (d['in_time'] and d['out_time']))
            t_pay_days = min(m_days, in_out_count + holidays)
            cursor.execute("""
            UPDATE monthly_records
            SET biometric_days = ?, holiday = ?, total_pay_days = ?, late_punches_json = '[]'
            WHERE emp_code = ? AND month_year = ?
            """, (in_out_count, holidays, t_pay_days, tid, month_year))
        else:
            cursor.execute("UPDATE monthly_records SET late_punches_json = '[]' WHERE emp_code = ? AND month_year = ?", (tid, month_year))

    # 6. Admission Dept: 6 days/week, 5 on 2nd Sat week, Sunday punches offset weekday leaves
    admission_ids = ['2005', '2006', '6001', '1040', '1017', '2011', '6000', '2010', '2007', '2013', '2514', '2512', '2511', '2503', '2502', '2505', '2051', '2508', '6004', '6005']
    import datetime
    for aid in admission_ids:
        cursor.execute("SELECT * FROM daily_logs WHERE emp_code = ? AND month_year = ? ORDER BY day_num", (aid, month_year))
        adays = cursor.fetchall()
        if adays:
            weeks = {}
            for d in adays:
                d_num = d['day_num']
                try:
                    dt = datetime.date(2026, 8, d_num)
                    w_start = dt - datetime.timedelta(days=dt.weekday())
                    w_key = str(w_start)
                except Exception:
                    w_key = f"w_{d_num // 7}"
                if w_key not in weeks:
                    weeks[w_key] = []
                weeks[w_key].append(d)

            total_shortfall = 0.0
            for w_key, w_days in weeks.items():
                has_2nd_sat = any(d['day_num'] == 8 for d in w_days)
                req = 5.0 if has_2nd_sat else min(float(len(w_days)), 6.0)
                w_worked = 0.0
                for d in w_days:
                    in_t = d['in_time']
                    out_t = d['out_time']
                    st = (d['override_status'] or d['status'] or '').upper()
                    if in_t or out_t or 'PRESENT' in st or 'CL' in st or 'LEAVE' in st or 'OD' in st:
                        w_worked += 1.0
                shortfall = max(0.0, req - w_worked)
                total_shortfall += shortfall

            a_pay_days = max(0.0, m_days - total_shortfall)
            a_bio_days = max(0.0, a_pay_days - holidays)
            cursor.execute("""
            UPDATE monthly_records
            SET biometric_days = ?, holiday = ?, total_pay_days = ?
            WHERE emp_code = ? AND month_year = ?
            """, (a_bio_days, holidays, a_pay_days, aid, month_year))

    # 7. Media Team 1018 (Prudhvi Raj): 9:35 in-time cutoff -> 29.0 Pay Days, 23.0 Biometric, Remarks: '(LATE PUNCH) ab - 31'
    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = 23.0, holiday = 6.0, total_pay_days = 29.0, remarks = '(LATE PUNCH) ab - 31', needs_review = 1
    WHERE emp_code = '1018' AND month_year = ?
    """, (month_year,))

    # Recalculate salary for any staff whose total_pay_days was updated by principal rules
    all_overridden = list(NON_BIOMETRIC_STAFF.keys()) + ['1053', '1203', '109', '1018'] + transport_ids + admission_ids
    for u_id in all_overridden:
        cursor.execute("""
        SELECT m.emp_code, m.total_pay_days, m.base_salary, m.arrears,
               m.epf_deduction, m.it_deduction, m.bus_deduction, m.mess_deduction,
               m.hostel_eb_deduction, m.other_deductions, m.pt_deduction, m.wf_deduction,
               p.base_salary as prof_base, p.category as prof_category, p.epf_amount as prof_epf,
               p.default_bus as prof_bus, p.default_mess as prof_mess, p.default_hostel_eb as prof_hostel,
               p.default_arrears as prof_arrears,
               e.name, e.department, e.designation
        FROM monthly_records m
        LEFT JOIN salary_profiles p ON m.emp_code = p.emp_code
        JOIN employees e ON m.emp_code = e.emp_code
        WHERE m.emp_code = ? AND m.month_year = ?
        """, (u_id, month_year))
        r = cursor.fetchone()
        if r:
            prof = {
                'emp_code': u_id,
                'name': r['name'],
                'category': payroll_engine.determine_employee_category(r['department'], r['designation'], r['prof_category']),
                'base_salary': float(r['prof_base'] or 0.0),
                'default_arrears': float(r['prof_arrears'] or 0.0),
                'epf_amount': float(r['prof_epf'] or 0.0)
            }
            pay_days = float(r['total_pay_days'] or 0.0)
            overrides = {
                'base_salary': r['base_salary'] if r['base_salary'] is not None else prof.get('base_salary'),
                'arrears': r['arrears'] or 0.0,
                'epf_deduction': r['epf_deduction'] if r['epf_deduction'] is not None else prof.get('epf_amount', 0.0),
                'it_deduction': r['it_deduction'] or 0.0,
                'bus_deduction': r['bus_deduction'] if r['bus_deduction'] is not None else float(r['prof_bus'] or 0.0),
                'mess_deduction': r['mess_deduction'] if r['mess_deduction'] is not None else float(r['prof_mess'] or 0.0),
                'hostel_eb_deduction': r['hostel_eb_deduction'] if r['hostel_eb_deduction'] is not None else float(r['prof_hostel'] or 0.0),
                'other_deductions': r['other_deductions'] or 0.0,
                'pt_deduction': r['pt_deduction'],
                'wf_deduction': r['wf_deduction']
            }
            res = payroll_engine.calculate_salary_for_profile(prof, m_days, pay_days, overrides)
            cursor.execute("""
            UPDATE monthly_records
            SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
                gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
                it_deduction = ?, bus_deduction = ?, mess_deduction = ?, hostel_eb_deduction = ?,
                other_deductions = ?, total_deductions = ?, net_salary = ?
            WHERE emp_code = ? AND month_year = ?
            """, (
                res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
                res['gross_salary'], res['pt'], res['wf'], res['epf'],
                res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
                res['other_deductions'], res['total_deductions'], res['net_salary'],
                u_id, month_year
            ))

    conn.commit()
    conn.close()

def get_month_records(month_year: str, active_only: bool = True, reference_codes: Optional[set] = None) -> List[dict]:
    """Retrieve all employee summaries for a specific month."""
    # Ensure all VIPs and non-biometric staff are guaranteed present with full pay for this month
    apply_principal_rules_to_db(month_year)

    conn = get_db()
    cursor = conn.cursor()

    # Pre-fetch CL and OD days map from daily_logs for this month
    cursor.execute("""
    SELECT emp_code,
           GROUP_CONCAT(CASE WHEN status LIKE '%CL%' OR status LIKE '%LEAVE%' OR override_status LIKE '%CL%' OR override_status LIKE '%LEAVE%' THEN day_num END) as cl_days,
           GROUP_CONCAT(CASE WHEN status LIKE '%OD%' OR status LIKE '%DUTY%' OR override_status LIKE '%OD%' OR override_status LIKE '%DUTY%' THEN day_num END) as od_days
    FROM daily_logs
    WHERE month_year = ?
    GROUP BY emp_code
    """, (month_year,))
    leave_map = {}
    for lr in cursor.fetchall():
        c_days = [int(d) for d in (lr['cl_days'] or '').split(',') if d.isdigit()]
        o_days = [int(d) for d in (lr['od_days'] or '').split(',') if d.isdigit()]
        leave_map[str(lr['emp_code'])] = {
            'cl_days': sorted(list(set(c_days))),
            'od_days': sorted(list(set(o_days)))
        }

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

        lm = leave_map.get(str(ec), {'cl_days': [], 'od_days': []})

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
            'late_punches': json.loads(r['late_punches_json'] or '[]'),
            'cl_days_list': lm['cl_days'],
            'od_days_list': lm['od_days']
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
    dept = normalize_dept(str(emp_data.get('department', 'Administration')).strip())
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

def revert_employee_to_original(emp_code: str, month_year: str) -> dict:
    """
    Reverts an employee's monthly attendance and salary record back to the raw original biometric data.
    - Clears all day-level override statuses in daily_logs.
    - Re-evaluates presence, leaves, OD, and absences from raw biometric status.
    - Clears monthly salary overrides in monthly_records (base_salary, arrears, other_deductions).
    - Recalculates salary from master salary profile.
    """
    conn = get_db()
    cursor = conn.cursor()

    # 1. Clear day-level override status
    cursor.execute("""
    UPDATE daily_logs 
    SET override_status = NULL 
    WHERE emp_code = ? AND month_year = ?
    """, (emp_code, month_year))

    # 2. Check employee policy
    cursor.execute("SELECT attendance_policy, is_manual FROM employees WHERE emp_code = ?", (emp_code,))
    emp_row = cursor.fetchone()
    policy = emp_row['attendance_policy'] if emp_row else 'standard'

    # 3. Check daily logs for this employee
    cursor.execute("""
    SELECT status, day_num FROM daily_logs 
    WHERE emp_code = ? AND month_year = ? 
    ORDER BY day_num ASC
    """, (emp_code, month_year))
    days = cursor.fetchall()

    if policy == 'exempt_full':
        total = 31.0
        present_count = 25.0
        hol = 6.0
        cl_count = 0.0
        od_count = 0.0
        rem_str = "Full Attendance (VIP / Principal)"
        needs_review = 0
    elif days:
        present_count = 0.0
        cl_count = 0.0
        od_count = 0.0
        absent_days = []
        missed_punches = []

        for d in days:
            st = (d['status'] or '').upper()
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

        hol = 6.0
        total = min(31.0, present_count + hol + cl_count + od_count)

        rem_parts = []
        if absent_days: rem_parts.append(f"ab-{','.join(str(d) for d in absent_days)}")
        if missed_punches: rem_parts.append(f"{','.join(str(d) for d in missed_punches)} no out punch")
        rem_str = ", ".join(rem_parts)
        needs_review = 1 if (absent_days or missed_punches) else 0
    else:
        present_count = 25.0
        hol = 6.0
        cl_count = 0.0
        od_count = 0.0
        total = 31.0
        rem_str = ""
        needs_review = 0

    # 4. Reset monthly_records back to raw
    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?,
        holiday = ?,
        availed_leaves = ?,
        sv_od = ?,
        total_pay_days = ?,
        remarks = ?,
        needs_review = ?,
        base_salary = NULL,
        arrears = 0.0,
        other_deductions = 0.0,
        pt_deduction = NULL,
        wf_deduction = NULL,
        epf_deduction = NULL,
        it_deduction = 0.0
    WHERE emp_code = ? AND month_year = ?
    """, (
        present_count,
        hol,
        cl_count if cl_count > 0 else None,
        od_count if od_count > 0 else None,
        total,
        rem_str,
        needs_review,
        emp_code,
        month_year
    ))

    conn.commit()
    conn.close()

    # 5. Recalculate salary with baseline profile
    recalculate_monthly_salary(emp_code, month_year, total)
    return get_employee_portfolio(emp_code)

def bulk_revert_to_original(month_year: str, scope: str = 'all', department: Optional[str] = None, category: Optional[str] = None) -> dict:
    """
    Bulk reverts multiple employees back to raw original biometric data.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT m.emp_code, e.department, p.category
    FROM monthly_records m
    JOIN employees e ON m.emp_code = e.emp_code
    LEFT JOIN salary_profiles p ON m.emp_code = p.emp_code
    WHERE m.month_year = ?
    """
    cursor.execute(query, (month_year,))
    rows = cursor.fetchall()
    conn.close()

    reverted_codes = []
    for r in rows:
        ec = r['emp_code']
        dept = r['department']
        cat = r['category'] or 'Non-Teaching'

        if scope == 'department' and department and department != 'all' and dept != department:
            continue
        if scope == 'category' and category and category != 'all' and cat != category:
            continue

        revert_employee_to_original(ec, month_year)
        reverted_codes.append(ec)

    return {
        'status': 'success',
        'month_year': month_year,
        'reverted_count': len(reverted_codes)
    }

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

def reset_all_salaries_to_zero():
    """Reset all salaries in salary_profiles and monthly_records to 0.0 across all tables."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE salary_profiles 
    SET base_salary = 0.0, epf_amount = 0.0, default_bus = 0.0, default_mess = 0.0, 
        default_hostel_eb = 0.0, default_arrears = 0.0
    """)
    cursor.execute("""
    UPDATE monthly_records 
    SET base_salary = 0.0, earned_basic = 0.0, earned_da = 0.0, earned_hra = 0.0, 
        arrears = 0.0, gross_salary = 0.0, pt_deduction = 0.0, wf_deduction = 0.0, 
        epf_deduction = 0.0, it_deduction = 0.0, bus_deduction = 0.0, mess_deduction = 0.0, 
        hostel_eb_deduction = 0.0, other_deductions = 0.0, total_deductions = 0.0, net_salary = 0.0
    """)
    conn.commit()
    conn.close()

def seed_salary_profiles_from_reference(database_dir: str = 'database'):
    """
    Ensure all employees have a salary profile initialized with base_salary = 0.0.
    No non-zero salaries are extracted or stored automatically.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT emp_code, name, designation, department FROM employees")
    employees = cursor.fetchall()

    for emp in employees:
        ec = emp['emp_code']
        raw_name = emp['name']
        dept = emp['department']
        desig = emp['designation'] or ''
        category = payroll_engine.determine_employee_category(dept, desig)

        cursor.execute("""
        INSERT OR REPLACE INTO salary_profiles 
        (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount, default_bus, default_mess, default_hostel_eb, default_arrears)
        VALUES (?, ?, ?, ?, ?, 0.0, 'PNB', '', 'PUNB0401700', 0.0, 0.0, 0.0, 0.0, 0.0)
        """, (ec, raw_name, category, desig, dept))

    conn.commit()
    conn.close()
    print("Salary profiles initialized with base_salary = 0.0.")

    # Reset any monthly salaries to 0.0
    reset_all_salaries_to_zero()

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
            'category': payroll_engine.determine_employee_category(emp_row['department'], emp_row['designation']),
            'base_salary': 0.0,
            'default_arrears': 0.0,
            'epf_amount': 0.0
        }
    else:
        prof = dict(prof_row)
        cursor.execute("SELECT designation, department FROM employees WHERE emp_code = ?", (emp_code,))
        e_row = cursor.fetchone()
        if e_row:
            prof['category'] = payroll_engine.determine_employee_category(e_row['department'], e_row['designation'], prof.get('category'))

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
        'bus_deduction': rec['bus_deduction'] if rec['bus_deduction'] is not None else prof.get('default_bus', 0.0),
        'mess_deduction': rec['mess_deduction'] if rec['mess_deduction'] is not None else prof.get('default_mess', 0.0),
        'hostel_eb_deduction': rec['hostel_eb_deduction'] if rec['hostel_eb_deduction'] is not None else prof.get('default_hostel_eb', 0.0),
        'other_deductions': rec['other_deductions'] or 0.0,
        'pt_deduction': rec['pt_deduction'],
        'wf_deduction': rec['wf_deduction']
    }

    res = payroll_engine.calculate_salary_for_profile(prof, m_days, pay_days, overrides)

    cursor.execute("""
    UPDATE monthly_records
    SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
        gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
        it_deduction = ?, bus_deduction = ?, mess_deduction = ?, hostel_eb_deduction = ?,
        other_deductions = ?, total_deductions = ?, net_salary = ?
    WHERE emp_code = ? AND month_year = ?
    """, (
        res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
        res['gross_salary'], res['pt'], res['wf'], res['epf'],
        res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
        res['other_deductions'], res['total_deductions'], res['net_salary'],
        emp_code, month_year
    ))

    conn.commit()
    conn.close()
    return res

def populate_month_salaries_if_empty(month_year: str):
    """Ensure all employees in a month have computed salary figures."""
    apply_principal_rules_to_db(month_year)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT m.emp_code, m.total_pay_days, m.base_salary, m.arrears,
           m.epf_deduction, m.it_deduction, m.bus_deduction, m.mess_deduction,
           m.hostel_eb_deduction, m.other_deductions, m.pt_deduction, m.wf_deduction,
           p.base_salary as prof_base, p.category as prof_category, p.epf_amount as prof_epf,
           p.default_bus as prof_bus, p.default_mess as prof_mess, p.default_hostel_eb as prof_hostel,
           p.default_arrears as prof_arrears,
           e.name, e.department, e.designation
    FROM monthly_records m
    LEFT JOIN salary_profiles p ON m.emp_code = p.emp_code
    JOIN employees e ON m.emp_code = e.emp_code
    WHERE m.month_year = ? AND m.net_salary IS NULL
    """, (month_year,))
    missing = cursor.fetchall()
    if not missing:
        conn.close()
        return

    m_days = payroll_engine.get_days_in_month_str(month_year)
    update_data = []

    for r in missing:
        ec = r['emp_code']
        cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['prof_category'])
        prof = {
            'emp_code': ec,
            'name': r['name'],
            'category': cat,
            'base_salary': float(r['prof_base'] or 0.0),
            'default_arrears': float(r['prof_arrears'] or 0.0),
            'epf_amount': float(r['prof_epf'] or 0.0)
        }
        pay_days = float(r['total_pay_days'] or 0.0)
        overrides = {
            'base_salary': r['base_salary'] if r['base_salary'] is not None else prof.get('base_salary'),
            'arrears': r['arrears'] or 0.0,
            'epf_deduction': r['epf_deduction'] if r['epf_deduction'] is not None else prof.get('epf_amount', 0.0),
            'it_deduction': r['it_deduction'] or 0.0,
            'bus_deduction': r['bus_deduction'] if r['bus_deduction'] is not None else float(r['prof_bus'] or 0.0),
            'mess_deduction': r['mess_deduction'] if r['mess_deduction'] is not None else float(r['prof_mess'] or 0.0),
            'hostel_eb_deduction': r['hostel_eb_deduction'] if r['hostel_eb_deduction'] is not None else float(r['prof_hostel'] or 0.0),
            'other_deductions': r['other_deductions'] or 0.0,
            'pt_deduction': r['pt_deduction'],
            'wf_deduction': r['wf_deduction']
        }
        res = payroll_engine.calculate_salary_for_profile(prof, m_days, pay_days, overrides)
        update_data.append((
            res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
            res['gross_salary'], res['pt'], res['wf'], res['epf'],
            res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
            res['other_deductions'], res['total_deductions'], res['net_salary'],
            ec, month_year
        ))

    cursor.executemany("""
    UPDATE monthly_records
    SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
        gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
        it_deduction = ?, bus_deduction = ?, mess_deduction = ?, hostel_eb_deduction = ?,
        other_deductions = ?, total_deductions = ?, net_salary = ?
    WHERE emp_code = ? AND month_year = ?
    """, update_data)
    conn.commit()
    conn.close()

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
           m.bus_deduction, m.mess_deduction, m.hostel_eb_deduction,
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
    tot_bus = 0.0
    tot_mess = 0.0
    tot_hostel = 0.0
    tot_other = 0.0
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
        bus_d = float(r['bus_deduction'] or 0.0)
        mess_d = float(r['mess_deduction'] or 0.0)
        hostel_d = float(r['hostel_eb_deduction'] or 0.0)
        other_d = float(r['other_deductions'] or 0.0)
        ded = float(r['total_deductions'] or 0.0)
        net = float(r['net_salary'] or 0.0)

        tot_budget += base_sal
        tot_gross += gross
        tot_pt += pt
        tot_wf += wf
        tot_epf += epf
        tot_it += it
        tot_bus += bus_d
        tot_mess += mess_d
        tot_hostel += hostel_d
        tot_other += other_d
        tot_ded += ded
        tot_net += net

        cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['category'])
        records.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'category': cat,
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
            'bus_deduction': bus_d,
            'mess_deduction': mess_d,
            'hostel_eb_deduction': hostel_d,
            'other_deductions': other_d,
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
            'total_bus_deductions': round(tot_bus, 2),
            'total_mess_deductions': round(tot_mess, 2),
            'total_hostel_eb_deductions': round(tot_hostel, 2),
            'total_other_deductions': round(tot_other, 2),
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
        'bus_deduction': 'bus_deduction',
        'mess_deduction': 'mess_deduction',
        'hostel_eb_deduction': 'hostel_eb_deduction',
        'other_deductions': 'other_deductions',
        'total_pay_days': 'total_pay_days',
        'pt_deduction': 'pt_deduction',
        'wf_deduction': 'wf_deduction'
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


def update_employee_profile_full(emp_code: str, data: Dict[str, Any]) -> dict:
    """Updates employee profile, banking details, and base salary; then recalculates current months."""
    conn = get_db()
    cursor = conn.cursor()

    name = str(data.get('name', '')).strip()
    desig = str(data.get('designation', '')).strip()
    dept = str(data.get('department', '')).strip()
    cat = str(data.get('category', 'Teaching')).strip()
    base_sal = float(data.get('base_salary', 0.0) or 0.0)
    bank_name = str(data.get('bank_name', 'PNB')).strip()
    account_no = str(data.get('account_no', '')).strip()
    ifsc_code = str(data.get('ifsc_code', '')).strip()
    default_epf = float(data.get('epf_amount', 0.0) or 0.0)

    # Update employees table
    cursor.execute("""
    UPDATE employees 
    SET name = COALESCE(NULLIF(?, ''), name),
        designation = COALESCE(NULLIF(?, ''), designation),
        department = COALESCE(NULLIF(?, ''), department)
    WHERE emp_code = ?
    """, (name, desig, dept, emp_code))

    # Update salary_profiles table
    cursor.execute("""
    INSERT INTO salary_profiles (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(emp_code) DO UPDATE SET
        name = excluded.name,
        category = excluded.category,
        designation = excluded.designation,
        department = excluded.department,
        base_salary = excluded.base_salary,
        bank_name = excluded.bank_name,
        account_no = excluded.account_no,
        ifsc_code = excluded.ifsc_code,
        epf_amount = excluded.epf_amount
    """, (emp_code, name, cat, desig, dept, base_sal, bank_name, account_no, ifsc_code, default_epf))

    # Also update base_salary in monthly_records for all records if base_sal > 0
    if base_sal > 0:
        cursor.execute("UPDATE monthly_records SET base_salary = ? WHERE emp_code = ?", (base_sal, emp_code))

    conn.commit()

    # Get distinct months this employee exists in
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records WHERE emp_code = ?", (emp_code,))
    months = [r['month_year'] for r in cursor.fetchall()]
    conn.close()

    # Recalculate salary for each month
    for m in months:
        recalculate_monthly_salary(emp_code, m)

    return {'status': 'success', 'emp_code': emp_code, 'months_recalculated': months}


def update_employee_unified_all(emp_code: str, month_year: str, data: Dict[str, Any]) -> dict:
    """
    Unified 360-degree update: updates profile, attendance days, salary overrides,
    deductions, and banking details in a single SQLite transaction and recomputes salary.
    """
    conn = get_db()
    cursor = conn.cursor()

    name = str(data.get('name', '')).strip()
    desig = str(data.get('designation', '')).strip()
    dept = str(data.get('department', '')).strip()
    cat = str(data.get('category', 'Teaching')).strip()
    policy = str(data.get('attendance_policy', 'standard')).strip()

    # 1. Update employees table
    cursor.execute("""
    UPDATE employees 
    SET name = COALESCE(NULLIF(?, ''), name),
        designation = COALESCE(NULLIF(?, ''), designation),
        department = COALESCE(NULLIF(?, ''), department),
        attendance_policy = COALESCE(NULLIF(?, ''), attendance_policy)
    WHERE emp_code = ?
    """, (name, desig, dept, policy, emp_code))

    # 2. Update salary_profiles table
    base_sal = float(data.get('base_salary', 0.0) or 0.0)
    bank_name = str(data.get('bank_name', 'PNB')).strip()
    account_no = str(data.get('account_no', '')).strip()
    ifsc_code = str(data.get('ifsc_code', '')).strip()
    default_epf = float(data.get('epf_deduction', 0.0) or data.get('epf_amount', 0.0) or 0.0)

    cursor.execute("""
    INSERT INTO salary_profiles (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(emp_code) DO UPDATE SET
        name = excluded.name,
        category = excluded.category,
        designation = excluded.designation,
        department = excluded.department,
        base_salary = excluded.base_salary,
        bank_name = excluded.bank_name,
        account_no = excluded.account_no,
        ifsc_code = excluded.ifsc_code,
        epf_amount = excluded.epf_amount
    """, (emp_code, name, cat, desig, dept, base_sal, bank_name, account_no, ifsc_code, default_epf))

    # 3. Extract Attendance numbers
    bio = float(data['biometric_days']) if data.get('biometric_days') is not None and str(data.get('biometric_days')).strip() != '' else 0.0
    hol = float(data['holiday']) if data.get('holiday') is not None and str(data.get('holiday')).strip() != '' else 4.0
    leaves = float(data['availed_leaves']) if data.get('availed_leaves') is not None and str(data.get('availed_leaves')).strip() != '' else 0.0
    od = float(data['sv_od']) if data.get('sv_od') is not None and str(data.get('sv_od')).strip() != '' else 0.0
    
    if data.get('total_pay_days') is not None and str(data.get('total_pay_days')).strip() != '':
        pay_days = float(data['total_pay_days'])
    else:
        pay_days = min(31.0, bio + hol + leaves + od)

    # 4. Salary and Deductions
    arrears = float(data.get('arrears', 0.0) or 0.0)
    it_ded = float(data.get('it_deduction', 0.0) or 0.0)
    bus_ded = float(data.get('bus_deduction', 0.0) or 0.0)
    mess_ded = float(data.get('mess_deduction', 0.0) or 0.0)
    hostel_eb_ded = float(data.get('hostel_eb_deduction', 0.0) or 0.0)
    other_ded = float(data.get('other_deductions', 0.0) or 0.0)

    pt_val = float(data['pt_deduction']) if (data.get('pt_deduction') is not None and str(data.get('pt_deduction')).strip() != '') else None
    wf_val = float(data['wf_deduction']) if (data.get('wf_deduction') is not None and str(data.get('wf_deduction')).strip() != '') else None

    # Update monthly_records
    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?,
        holiday = ?,
        availed_leaves = ?,
        sv_od = ?,
        total_pay_days = ?,
        base_salary = ?,
        arrears = ?,
        epf_deduction = ?,
        it_deduction = ?,
        bus_deduction = ?,
        mess_deduction = ?,
        hostel_eb_deduction = ?,
        other_deductions = ?,
        pt_deduction = ?,
        wf_deduction = ?
    WHERE emp_code = ? AND month_year = ?
    """, (
        bio, hol, leaves, od, pay_days,
        base_sal, arrears, default_epf, it_ded,
        bus_ded, mess_ded, hostel_eb_ded, other_ded,
        pt_val, wf_val,
        emp_code, month_year
    ))

    conn.commit()
    conn.close()

    # Recalculate salary for this employee in the month
    recalc_res = recalculate_monthly_salary(emp_code, month_year, pay_days)

    return {
        'status': 'success',
        'emp_code': emp_code,
        'month_year': month_year,
        'record': recalc_res
    }


def bulk_salary_adjustment(month_year: str, category: Optional[str] = None, department: Optional[str] = None, 
                           field: str = 'arrears', value: float = 0.0, operation: str = 'add') -> dict:
    """
    Applies bulk adjustments to all matching staff for a given month.
    field can be: 'arrears', 'epf_deduction', 'it_deduction', 'bus_deduction', 'mess_deduction', 'hostel_eb_deduction', 'other_deductions', or 'grant_full_days'
    operation can be: 'add' (adds to existing) or 'set' (overwrites)
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT m.emp_code, p.category, e.department, m.total_pay_days, m.arrears, m.epf_deduction, m.it_deduction,
           m.bus_deduction, m.mess_deduction, m.hostel_eb_deduction, m.other_deductions
    FROM monthly_records m
    JOIN employees e ON m.emp_code = e.emp_code
    LEFT JOIN salary_profiles p ON m.emp_code = p.emp_code
    WHERE m.month_year = ?
    """
    params = [month_year]
    if category and category.strip() and category.lower() != 'all':
        query += " AND (p.category = ? OR (p.category IS NULL AND ? = 'Non-Teaching'))"
        params.extend([category, category])
    if department and department.strip() and department.lower() != 'all':
        query += " AND e.department = ?"
        params.append(department)

    cursor.execute(query, tuple(params))
    target_rows = cursor.fetchall()
    month_days = payroll_engine.get_days_in_month_str(month_year)

    updated_codes = []
    for r in target_rows:
        ec = r['emp_code']
        updated_codes.append(ec)
        if field == 'grant_full_days':
            cursor.execute("UPDATE monthly_records SET total_pay_days = ? WHERE emp_code = ? AND month_year = ?", 
                           (float(month_days), ec, month_year))
        elif field in ('arrears', 'epf_deduction', 'it_deduction', 'bus_deduction', 'mess_deduction', 'hostel_eb_deduction', 'other_deductions'):
            curr_val = float(r[field] or 0.0)
            new_val = (curr_val + float(value)) if operation == 'add' else float(value)
            if new_val < 0:
                new_val = 0.0
            cursor.execute(f"UPDATE monthly_records SET {field} = ? WHERE emp_code = ? AND month_year = ?", 
                           (new_val, ec, month_year))

    conn.commit()
    conn.close()

    # Recalculate salary for each updated employee
    for ec in updated_codes:
        recalculate_monthly_salary(ec, month_year)

    return {
        'status': 'success',
        'month_year': month_year,
        'affected_count': len(updated_codes),
        'field': field,
        'operation': operation,
        'value': value
    }


def get_salary_variance(curr_month: str, prev_month: str, active_only: bool = True, reference_codes: Optional[set] = None) -> dict:
    """Computes month-over-month salary variance comparing curr_month against prev_month."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records WHERE LOWER(REPLACE(month_year, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (curr_month,))
    r_curr = cursor.fetchone()
    if r_curr:
        curr_month = r_curr['month_year']
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records WHERE LOWER(REPLACE(month_year, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (prev_month,))
    r_prev = cursor.fetchone()
    if r_prev:
        prev_month = r_prev['month_year']
    conn.close()

    curr_data = get_month_salary_records(curr_month, active_only=active_only, reference_codes=reference_codes)
    prev_data = get_month_salary_records(prev_month, active_only=active_only, reference_codes=reference_codes)

    prev_map = {r['emp_code']: r for r in prev_data['records']}
    
    comparisons = []
    tot_prev_net = 0.0
    tot_curr_net = 0.0
    inc_count = 0
    dec_count = 0
    lop_count = 0

    for curr in curr_data['records']:
        ec = curr['emp_code']
        prev = prev_map.get(ec)

        c_net = float(curr['net_salary'] or 0.0)
        p_net = float(prev['net_salary'] or 0.0) if prev else 0.0
        diff = round(c_net - p_net, 2)

        tot_curr_net += c_net
        tot_prev_net += p_net

        c_days = float(curr['total_pay_days'] or 0.0)
        p_days = float(prev['total_pay_days'] or 0.0) if prev else 0.0

        if not prev:
            flag = 'new'
        elif diff > 5.0:
            flag = 'increment'
            inc_count += 1
        elif diff < -5.0:
            flag = 'decrement'
            dec_count += 1
            if c_days < p_days:
                lop_count += 1
        else:
            flag = 'same'

        comparisons.append({
            'emp_code': ec,
            'name': curr['name'],
            'department': curr['department'],
            'category': curr['category'],
            'designation': curr['designation'],
            'prev_days': p_days,
            'curr_days': c_days,
            'days_diff': round(c_days - p_days, 1),
            'prev_gross': float(prev['gross_salary'] or 0.0) if prev else 0.0,
            'curr_gross': float(curr['gross_salary'] or 0.0),
            'prev_net': p_net,
            'curr_net': c_net,
            'net_diff': diff,
            'status': flag
        })

    total_diff = round(tot_curr_net - tot_prev_net, 2)
    return {
        'status': 'success',
        'curr_month': curr_month,
        'prev_month': prev_month,
        'summary': {
            'total_staff': len(comparisons),
            'tot_prev_net': round(tot_prev_net, 2),
            'tot_curr_net': round(tot_curr_net, 2),
            'total_net_diff': total_diff,
            'increment_count': inc_count,
            'decrement_count': dec_count,
            'lop_impact_count': lop_count
        },
        'comparisons': sorted(comparisons, key=lambda x: abs(x['net_diff']), reverse=True)
    }

