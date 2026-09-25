import os
import re
import json
from typing import Dict, List, Any, Optional
import payroll_engine

# Try loading dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DB_FILE = "rvs_attendance.db"

# Database Configuration (Supabase PostgreSQL / Turso SQLite / Local SQLite)
SUPABASE_DB_URL = os.environ.get('SUPABASE_DB_URL') or os.environ.get('DATABASE_URL') or "postgresql://postgres.nfqtqgqbuaotkljrsmpb:Reddy%407989604033@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"
TURSO_DATABASE_URL = os.environ.get('TURSO_DATABASE_URL', '')
TURSO_AUTH_TOKEN = os.environ.get('TURSO_AUTH_TOKEN', '')

_USE_SUPABASE = False
_USE_TURSO = False
_pg_pool = None

class PgCursorProxy:
    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn

    def _translate_sql(self, sql, params=None):
        # 1. Handle PRAGMA table_info(x)
        pragma_m = re.match(r'^\s*PRAGMA\s+table_info\(([^)]+)\)', sql, re.I)
        if pragma_m:
            tbl = pragma_m.group(1).strip('"\'; ')
            return f"SELECT column_name as name, data_type as type FROM information_schema.columns WHERE table_name = '{tbl}'"

        # 2. Handle SQLite CREATE TABLE AUTOINCREMENT
        if 'AUTOINCREMENT' in sql.upper():
            sql = re.sub(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', 'SERIAL PRIMARY KEY', sql, flags=re.I)

        # 3. Handle INSERT OR REPLACE
        if 'INSERT OR REPLACE' in sql.upper():
            m_emp = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+employees\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)', sql, re.I | re.S)
            if m_emp:
                cols = [c.strip() for c in m_emp.group(1).split(',')]
                updates = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in cols if c != 'emp_code'])
                cols_str = ", ".join([f'"{c}"' for c in cols])
                sql = f'INSERT INTO employees ({cols_str}) VALUES ({m_emp.group(2)}) ON CONFLICT (emp_code) DO UPDATE SET {updates}'
            else:
                m_prof = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+salary_profiles\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)', sql, re.I | re.S)
                if m_prof:
                    cols = [c.strip() for c in m_prof.group(1).split(',')]
                    updates = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in cols if c != 'emp_code'])
                    cols_str = ", ".join([f'"{c}"' for c in cols])
                    sql = f'INSERT INTO salary_profiles ({cols_str}) VALUES ({m_prof.group(2)}) ON CONFLICT (emp_code) DO UPDATE SET {updates}'
                else:
                    m_logs = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+daily_logs\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)', sql, re.I | re.S)
                    if m_logs:
                        cols = [c.strip() for c in m_logs.group(1).split(',')]
                        updates = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in ('emp_code', 'month_year', 'day_num')])
                        cols_str = ", ".join([f'"{c}"' for c in cols])
                        sql = f'INSERT INTO daily_logs ({cols_str}) VALUES ({m_logs.group(2)}) ON CONFLICT (emp_code, month_year, day_num) DO UPDATE SET {updates}'
                    else:
                        m_mon = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+monthly_records\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)', sql, re.I | re.S)
                        if m_mon:
                            cols = [c.strip() for c in m_mon.group(1).split(',')]
                            updates = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in ('emp_code', 'month_year', 'id')])
                            cols_str = ", ".join([f'"{c}"' for c in cols])
                            sql = f'INSERT INTO monthly_records ({cols_str}) VALUES ({m_mon.group(2)}) ON CONFLICT (emp_code, month_year) DO UPDATE SET {updates}'

        # 4. Handle ? placeholder to %s and % escaping for psycopg2
        if params is not None and len(params) > 0:
            sql = sql.replace('%', '%%').replace('?', '%s')
        else:
            sql = sql.replace('?', '%s')
        return sql

    def execute(self, sql, params=None):
        translated = self._translate_sql(sql, params)
        try:
            if params is not None:
                return self._cur.execute(translated, params)
            else:
                return self._cur.execute(translated)
        except Exception as e:
            try:
                self._conn._raw_conn.rollback()
            except Exception:
                pass
            raise e

    def executemany(self, sql, seq_of_params):
        if not seq_of_params:
            return
        sample_params = seq_of_params[0] if seq_of_params else None
        translated = self._translate_sql(sql, sample_params)
        import psycopg2.extras
        # Use high-speed execute_values for multi-row INSERTs to prevent TLS timeouts and SSL errors
        if 'VALUES' in translated.upper() and 'INSERT' in translated.upper():
            val_sql = re.sub(r'VALUES\s*\([^)]+\)', 'VALUES %s', translated, flags=re.I)
            try:
                psycopg2.extras.execute_values(self._cur, val_sql, seq_of_params, page_size=2000)
                return
            except Exception as e:
                print(f"[DB] execute_values fallback: {e}")
        try:
            psycopg2.extras.execute_batch(self._cur, translated, seq_of_params, page_size=500)
        except Exception as e:
            try:
                self._conn._raw_conn.rollback()
            except Exception:
                pass
            raise e

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size)

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    @property
    def lastrowid(self):
        return getattr(self._cur, 'lastrowid', None)

    def close(self):
        return self._cur.close()

    def __iter__(self):
        return iter(self._cur)

class PgConnectionProxy:
    def __init__(self, raw_conn, pool_ref=None):
        self._raw_conn = raw_conn
        self._pool_ref = pool_ref
        self.row_factory = None

    def cursor(self):
        return PgCursorProxy(self._raw_conn.cursor(), self)

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    def close(self):
        if self._pool_ref:
            try:
                if getattr(self._raw_conn, 'closed', 0) == 0:
                    self._raw_conn.commit()
                    self._pool_ref.putconn(self._raw_conn)
                else:
                    self._pool_ref.putconn(self._raw_conn, close=True)
            except Exception:
                try:
                    self._pool_ref.putconn(self._raw_conn, close=True)
                except Exception:
                    pass
        else:
            try:
                if getattr(self._raw_conn, 'closed', 0) == 0:
                    self._raw_conn.commit()
            except Exception:
                pass
            return self._raw_conn.close()

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

if SUPABASE_DB_URL and not os.environ.get('USE_LOCAL_SQLITE'):
    try:
        import psycopg2
        import psycopg2.extras
        from psycopg2 import pool
        _pg_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=SUPABASE_DB_URL
        )
        _USE_SUPABASE = True
        print(f"[DB] Using Supabase PostgreSQL Cloud Database")
    except Exception as e:
        print(f"[DB] Supabase connection failed ({e}), falling back to local database...")
        _USE_SUPABASE = False

if not _USE_SUPABASE:
    if TURSO_DATABASE_URL:
        try:
            import libsql_experimental as sqlite3
            _USE_TURSO = True
            print(f"[DB] Using Turso cloud SQLite: {TURSO_DATABASE_URL}")
        except ImportError:
            import sqlite3
            _USE_TURSO = False
            print("[DB] libsql_experimental not installed, falling back to local SQLite")
    else:
        import sqlite3
        _USE_TURSO = False
        print(f"[DB] Using local SQLite: {DB_FILE}")

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
        return "General"
    cleaned = re.sub(r'[\s\-_]+', ' ', str(dept_name)).strip().upper()
    return DEPARTMENT_CANONICAL_MAP.get(cleaned, str(dept_name).strip())

def normalize_month_year(month_year: str) -> str:
    """Normalize any month string (e.g. 'August -2026', 'August 2026', 'July-2026') to canonical 'Month Year'."""
    if not month_year:
        return "August 2026"
    m = re.sub(r'[\-_]+', ' ', str(month_year)).strip()
    return re.sub(r'\s+', ' ', m)

def get_db():
    """Get database connection — Supabase PostgreSQL if configured, Turso cloud if configured, else local SQLite."""
    if _USE_SUPABASE:
        import psycopg2.extras
        raw_conn = None
        if _pg_pool:
            try:
                raw_conn = _pg_pool.getconn()
                if getattr(raw_conn, 'closed', 0) != 0:
                    _pg_pool.putconn(raw_conn, close=True)
                    raw_conn = _pg_pool.getconn()
                raw_conn.cursor_factory = psycopg2.extras.DictCursor
                return PgConnectionProxy(raw_conn, _pg_pool)
            except Exception as e:
                print(f"[DB] Pool getconn notice: {e}, falling back to direct dedicated connection")
                try:
                    if raw_conn:
                        _pg_pool.putconn(raw_conn, close=True)
                except Exception:
                    pass
        try:
            direct_conn = psycopg2.connect(SUPABASE_DB_URL)
            direct_conn.cursor_factory = psycopg2.extras.DictCursor
            return PgConnectionProxy(direct_conn, None)
        except Exception as e:
            print(f"[DB] Direct Supabase connection failed ({e}), falling back to local SQLite")
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            return conn
    elif _USE_TURSO:
        conn = sqlite3.connect(
            database=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN
        )
        conn.row_factory = sqlite3.Row
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Create tables if they do not exist."""
    if _USE_SUPABASE:
        return
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

    # Ensure salary columns AND per-month identity columns exist in monthly_records
    cursor.execute("PRAGMA table_info(monthly_records)")
    existing_cols = [r['name'] for r in cursor.fetchall()]
    salary_cols = {
        # Per-month identity (name/designation/dept from raw file — NOT from global employees)
        'name': 'TEXT',
        'designation': 'TEXT',
        'department': 'TEXT',
        # Salary columns
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

    # Backfill name/designation/department from employees into monthly_records where missing
    cursor.execute("""
        UPDATE monthly_records SET
            name = (SELECT e.name FROM employees e WHERE e.emp_code = monthly_records.emp_code),
            designation = (SELECT e.designation FROM employees e WHERE e.emp_code = monthly_records.emp_code),
            department = (SELECT e.department FROM employees e WHERE e.emp_code = monthly_records.emp_code)
        WHERE name IS NULL
    """)

    conn.commit()
    conn.close()

def get_available_months() -> List[str]:
    """Return all distinct month_years stored in database, normalized and sorted chronologically."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT month_year FROM monthly_records")
    rows = cursor.fetchall()
    conn.close()
    
    unique_months = list(dict.fromkeys(normalize_month_year(r['month_year']) for r in rows if r['month_year']))
    
    import calendar
    def month_sort_key(m_str):
        parts = m_str.split()
        year = 2026
        month = 8
        for p in parts:
            if p.isdigit() and len(p) == 4:
                year = int(p)
            for m_idx in range(1, 13):
                if calendar.month_name[m_idx].lower() == p.lower() or calendar.month_abbr[m_idx].lower() == p.lower():
                    month = m_idx
        return (year, month)

    unique_months.sort(key=month_sort_key, reverse=True)
    return unique_months

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
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    rec_count = cursor.fetchone()['cnt']
    cursor.execute("DELETE FROM monthly_records WHERE month_year = ?", (month_year,))
    cursor.execute("DELETE FROM daily_logs WHERE month_year = ?", (month_year,))
    conn.commit()
    conn.close()
    _PRINCIPAL_RULES_APPLIED.discard(month_year)
    return {
        'status': 'success',
        'message': f'Successfully deleted {rec_count} records for {month_year}',
        'deleted_count': rec_count
    }

def get_month_summary_info(month_year: str) -> dict:
    """Return record count and punch log count for a given month."""
    month_year = normalize_month_year(month_year)
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

def seed_from_engine(engine, month_year: str = "August 2026", overwrite: bool = False):
    """Populate database from an AttendanceEngine instance."""
    month_year = normalize_month_year(month_year)
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

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 31)
    import calendar
    import datetime
    y, m = 2026, 8
    for p in month_year.split():
        if p.isdigit() and len(p) == 4: y = int(p)
        for m_idx in range(1, 13):
            if calendar.month_name[m_idx].lower() == p.lower(): m = m_idx
    sundays = {d for d in range(1, int(m_days) + 1) if datetime.date(y, m, d).weekday() == 6}
    fest_hol = {26} if m == 8 else set()
    holidays = float(len(sundays.union(fest_hol)))
    bio_days = max(0.0, m_days - holidays)

    emp_batch = []
    mon_batch = []
    log_batch = []
    CHUNK_SIZE = 40

    def _flush_chunk(e_b, m_b, l_b):
        if e_b:
            cursor.executemany("""
            INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, e_b)
        if m_b:
            cursor.executemany("""
            INSERT OR REPLACE INTO monthly_records 
            (emp_code, month_year, name, designation, department, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, missed_punches_json, absent_days_json, late_punches_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, m_b)
        if l_b:
            cursor.executemany("""
            INSERT OR REPLACE INTO daily_logs (emp_code, month_year, day_num, date_str, in_time, out_time, duration, status, override_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, l_b)
        conn.commit()

    for emp_code, emp in engine.employees.items():
        name_l = str(emp.get('name', '')).lower()
        desig_l = str(emp.get('designation', '')).lower()
        dept_l = str(emp.get('department', '')).lower()

        is_vip = (emp_code in vip_full_pay_codes or 
                  'principal' in desig_l or 
                  any(k in name_l for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'bishal kumar', 'shajahan']) or
                  ('siva' in name_l and ('driver' in desig_l or 'transport' in dept_l)))
        policy = 'exempt_full' if is_vip else 'standard'
        
        emp_batch.append((emp_code, emp['name'], emp.get('designation', ''), normalize_dept(emp.get('department', '')), 12.0, 15.0, policy, 0))

        summary = engine.calculate_employee_summary(emp)
        
        # If policy is exempt_full, give full month pay days
        if policy == 'exempt_full':
            total_days = m_days
            bio_days_emp = bio_days
            holidays_emp = holidays
            leaves = None
            od = None
            remarks = "Full Attendance (Exempt / Principal)"
            needs_review = 0
        else:
            total_days = summary['total_pay_days']
            bio_days_emp = summary['biometric_days']
            holidays_emp = summary['holiday']
            leaves = summary['availed_leaves']
            od = summary['sv_od']
            remarks = summary['remarks']
            needs_review = 1 if summary['needs_review'] else 0

        mon_batch.append((
            emp_code, month_year,
            emp['name'], emp.get('designation', ''), normalize_dept(emp.get('department', '')),
            bio_days_emp, holidays_emp, leaves, od, total_days, remarks, needs_review,
            json.dumps(summary.get('missed_out_punches', [])),
            json.dumps(summary.get('absent_days', [])),
            json.dumps(summary.get('late_punches', []))
        ))

        # Seed daily logs
        for day in emp['days']:
            log_batch.append((
                emp_code, month_year, day['day'], day['date'], day['in_time'], day['out_time'],
                day['duration'], day['status'], day.get('override_status')
            ))

        if len(emp_batch) >= CHUNK_SIZE:
            _flush_chunk(emp_batch, mon_batch, log_batch)
            emp_batch.clear()
            mon_batch.clear()
            log_batch.clear()

    if emp_batch:
        _flush_chunk(emp_batch, mon_batch, log_batch)
        emp_batch.clear()
        mon_batch.clear()
        log_batch.clear()

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
                VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 0)
                """, (ec, month_year, bio_days, holidays, m_days, "Full Attendance (VIP / Principal)" if is_principal else "Reference Staff"))

    conn.commit()
    conn.close()
    print(f"Database seeded successfully for {month_year}.")
    apply_principal_rules_to_db(month_year)

_PRINCIPAL_RULES_APPLIED = set()

def apply_principal_rules_to_db(month_year: str = "August 2026", force: bool = False):
    """
    Enforce Principal Sir's 21 attendance rules directly on database records:
    - 101, 707, 900, 1060, 1015, 1019, 1021, 4001, 1030, Shajahan, Siva driver: full days.
    - 1053: >=12 days -> full days.
    - 1203: >=14 days -> full days.
    - 536: CSE Bala Subramanyam before 12:10 = full day.
    - 109: Civil M. Lilaakar before 11:00 am = full day.
    - Transport IDs: no late penalties, no out punch counted as present.
    - Electricians: 8:30 in, 16:30 out full day no penalty.
    - Attenders / Garden: 8:35 in threshold.
    - Admission: 6 days/week, Sunday work offsets absent.
    """
    month_year = normalize_month_year(month_year)
    if not force and month_year in _PRINCIPAL_RULES_APPLIED:
        return
    conn = get_db()
    cursor = conn.cursor()

    # Guard: If no records exist for this month in monthly_records (e.g. month was deleted or not yet seeded),
    # do NOT create phantom VIP rows!
    cursor.execute("SELECT COUNT(*) as cnt FROM monthly_records WHERE month_year = ?", (month_year,))
    if cursor.fetchone()['cnt'] == 0:
        conn.close()
        return

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 31)
    import calendar
    import datetime
    y, m = 2026, 8
    for p in month_year.split():
        if p.isdigit() and len(p) == 4: y = int(p)
        for m_idx in range(1, 13):
            if calendar.month_name[m_idx].lower() == p.lower(): m = m_idx
    sundays = {d for d in range(1, int(m_days) + 1) if datetime.date(y, m, d).weekday() == 6}
    fest_hol = {26} if m == 8 else set()
    holidays = float(len(sundays.union(fest_hol)))
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

    # Pre-calculate availed leaves and OD for VIPs if they exist in daily_logs
    cursor.execute("""
    SELECT emp_code,
           SUM(CASE 
               WHEN (status LIKE '%1/2CL%' OR status LIKE '%HALF%CL%' OR override_status LIKE '%1/2CL%' OR override_status LIKE '%HALF%CL%') THEN 0.5
               WHEN (status LIKE '%CL%' OR status LIKE '%LEAVE%' OR override_status LIKE '%CL%' OR override_status LIKE '%LEAVE%') THEN 1.0
               ELSE 0.0 END) as cl_cnt,
           SUM(CASE 
               WHEN (status LIKE '%OD%' OR status LIKE '%DUTY%' OR override_status LIKE '%OD%' OR override_status LIKE '%DUTY%') THEN 1.0
               ELSE 0.0 END) as od_cnt
    FROM daily_logs
    WHERE month_year = ?
    GROUP BY emp_code
    """, (month_year,))
    vip_leave_map = {}
    for r in cursor.fetchall():
        vip_leave_map[str(r['emp_code'])] = {
            'cl': float(r['cl_cnt'] or 0.0),
            'od': float(r['od_cnt'] or 0.0)
        }

    # 1. Ensure all designated VIP staff exist in employees table & monthly_records for this month
    for vc, meta in NON_BIOMETRIC_STAFF.items():
        v_cl = vip_leave_map.get(str(vc), {}).get('cl')
        v_od = vip_leave_map.get(str(vc), {}).get('od')
        v_cl = v_cl if (v_cl is not None and v_cl > 0) else None
        v_od = v_od if (v_od is not None and v_od > 0) else None

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
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Full Attendance (Principal Override)', 0, '[]', '[]', '[]')
            """, (vc, month_year, bio_days, holidays, v_cl, v_od, m_days))
        else:
            cursor.execute("""
            UPDATE monthly_records 
            SET biometric_days = ?, holiday = ?, availed_leaves = COALESCE(?, availed_leaves), sv_od = COALESCE(?, sv_od), total_pay_days = ?, remarks = 'Full Attendance (Principal Override)', needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
            WHERE emp_code = ? AND month_year = ?
            """, (bio_days, holidays, v_cl, v_od, m_days, vc, month_year))

    # Name-based checks for other VIPs in database
    cursor.execute("SELECT emp_code, name, designation, department FROM employees")
    emps = cursor.fetchall()
    for e in emps:
        ec = e['emp_code']
        nl = (e['name'] or '').lower()
        dl = (e['designation'] or '').lower()
        deptl = (e['department'] or '').lower()
        
        if (any(k in nl for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'shajahan']) or 
            (ec == 'SHIVA_DRIVER' or 'principal diver' in dl or 'principal driver' in dl)):
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

    # Ensure regular bus drivers with 'Siva' in their name are standard policy, not VIP
    cursor.execute("UPDATE employees SET attendance_policy = 'standard' WHERE emp_code IN ('603', '610', '6623')")

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
    conn.commit()

    # 5. Transport Dept: remove late punch penalties & credit full days for in+out punches
    transport_ids = ['625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613']
    from collections import defaultdict
    t_placeholders = ','.join('?' * len(transport_ids))
    cursor.execute(f"SELECT * FROM daily_logs WHERE emp_code IN ({t_placeholders}) AND month_year = ? ORDER BY emp_code, day_num", (*transport_ids, month_year))
    t_days_map = defaultdict(list)
    for r in cursor.fetchall():
        t_days_map[str(r['emp_code'])].append(r)

    transport_updates = []
    transport_empty_updates = []
    for tid in transport_ids:
        tdays = t_days_map.get(tid, [])
        if tdays:
            in_out_count = sum(1.0 for d in tdays if (d['in_time'] and d['out_time']))
            t_pay_days = min(m_days, in_out_count + holidays)

            # Use dynamically computed sundays for this month
            t_absent = []
            t_half = []
            for d in tdays:
                d_num = d['day_num']
                if d_num in sundays:
                    continue
                in_t = d['in_time']
                out_t = d['out_time']
                st = (d['override_status'] or d['status'] or '').upper()
                if not in_t and not out_t and 'HOLIDAY' not in st:
                    t_absent.append(d_num)
                elif '1/2' in st or 'HALF' in st:
                    t_half.append(f"{d_num}(1/2)")

            rem_parts = []
            if t_absent:
                abs_str = ','.join(str(x) for x in t_absent)
                rem_parts.append(f"ab-{abs_str}")
            if t_half:
                rem_parts.extend(t_half)
            t_rem = ', '.join(rem_parts)

            transport_updates.append((in_out_count, holidays, t_pay_days, t_rem, json.dumps(t_absent), tid, month_year))
        else:
            transport_empty_updates.append((tid, month_year))

    if transport_updates:
        cursor.executemany("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = ?, absent_days_json = ?, late_punches_json = '[]'
        WHERE emp_code = ? AND month_year = ?
        """, transport_updates)
    if transport_empty_updates:
        cursor.executemany("UPDATE monthly_records SET late_punches_json = '[]' WHERE emp_code = ? AND month_year = ?", transport_empty_updates)
    conn.commit()

    # 6. Admission Dept: 6 days/week, 5 on 2nd Sat week, Sunday punches offset weekday leaves
    admission_ids = ['2005', '2006', '6001', '1040', '1017', '2011', '6000', '2010', '2007', '2013', '2514', '2512', '2511', '2503', '2502', '2505', '2051', '2508', '6004', '6005']
    import datetime
    # Compute actual 2nd Saturday of this month dynamically
    second_saturday_day = None
    sat_count = 0
    for _d in range(1, int(m_days) + 1):
        if datetime.date(y, m, _d).weekday() == 5:  # Saturday
            sat_count += 1
            if sat_count == 2:
                second_saturday_day = _d
                break

    a_placeholders = ','.join('?' * len(admission_ids))
    cursor.execute(f"SELECT * FROM daily_logs WHERE emp_code IN ({a_placeholders}) AND month_year = ? ORDER BY emp_code, day_num", (*admission_ids, month_year))
    a_days_map = defaultdict(list)
    for r in cursor.fetchall():
        a_days_map[str(r['emp_code'])].append(r)

    admission_updates = []
    for aid in admission_ids:
        adays = a_days_map.get(aid, [])
        if adays:
            weeks = {}
            for d in adays:
                d_num = d['day_num']
                try:
                    dt = datetime.date(y, m, d_num)
                    w_start = dt - datetime.timedelta(days=dt.weekday())
                    w_key = str(w_start)
                except Exception:
                    w_key = f"w_{d_num // 7}"
                if w_key not in weeks:
                    weeks[w_key] = []
                weeks[w_key].append(d)

            total_shortfall = 0.0
            for w_key, w_days in weeks.items():
                has_2nd_sat = second_saturday_day is not None and any(d['day_num'] == second_saturday_day for d in w_days)
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
            admission_updates.append((a_bio_days, holidays, a_pay_days, aid, month_year))

    if admission_updates:
        cursor.executemany("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, total_pay_days = ?
        WHERE emp_code = ? AND month_year = ?
        """, admission_updates)
    conn.commit()

    # 7. Media Team 1018 (Prudhvi Raj): 9:35 in-time cutoff
    emp1018_bio = max(0.0, m_days - holidays - 2.0)
    emp1018_pay = max(0.0, m_days - 2.0)
    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = '(LATE PUNCH) ab - 31', needs_review = 1
    WHERE emp_code = '1018' AND month_year = ?
    """, (emp1018_bio, holidays, emp1018_pay, month_year,))
    conn.commit()

    # Recalculate salary for any staff whose total_pay_days was updated by principal rules
    all_overridden = list(NON_BIOMETRIC_STAFF.keys()) + ['1053', '1203', '109', '1018'] + transport_ids + admission_ids
    o_placeholders = ','.join('?' * len(all_overridden))
    cursor.execute(f"""
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
    WHERE m.emp_code IN ({o_placeholders}) AND m.month_year = ?
    """, (*all_overridden, month_year))
    overridden_rows = cursor.fetchall()

    salary_updates = []
    for r in overridden_rows:
        u_id = str(r['emp_code'])
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
        salary_updates.append((
            res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
            res['gross_salary'], res['pt'], res['wf'], res['epf'],
            res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
            res['other_deductions'], res['total_deductions'], res['net_salary'],
            u_id, month_year
        ))

    if salary_updates:
        cursor.executemany("""
        UPDATE monthly_records
        SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
            gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
            it_deduction = ?, bus_deduction = ?, mess_deduction = ?, hostel_eb_deduction = ?,
            other_deductions = ?, total_deductions = ?, net_salary = ?
        WHERE emp_code = ? AND month_year = ?
        """, salary_updates)

    conn.commit()
    conn.close()
    _PRINCIPAL_RULES_APPLIED.add(month_year)

def get_month_records(month_year: str, active_only: bool = True, reference_codes: Optional[set] = None) -> List[dict]:
    """Retrieve all employee summaries for a specific month."""
    month_year = normalize_month_year(month_year)

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
    SELECT e.emp_code,
           COALESCE(m.name, e.name) AS name,
           COALESCE(m.designation, e.designation) AS designation,
           COALESCE(m.department, e.department) AS department,
           e.annual_cl_quota, e.annual_od_quota, e.attendance_policy, e.is_manual,
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
    is_august = 'august' in month_year.lower()
    for r in rows:
        ec = r['emp_code']
        if active_only and is_august and reference_codes and ec not in reference_codes and not r['is_manual']:
            continue

        lm = leave_map.get(str(ec), {'cl_days': [], 'od_days': []})

        cl_val = r['availed_leaves']
        if (cl_val is None or cl_val == 0.0) and lm['cl_days']:
            cl_val = float(len(lm['cl_days']))

        od_val = r['sv_od']
        if (od_val is None or od_val == 0.0) and lm['od_days']:
            od_val = float(len(lm['od_days']))

        results.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'attendance_policy': r['attendance_policy'],
            'is_manual': bool(r['is_manual']),
            'biometric_days': r['biometric_days'],
            'holiday': r['holiday'],
            'availed_leaves': cl_val,
            'sv_od': od_val,
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

    cursor.execute("SELECT count(*) as cnt FROM salary_profiles")
    r = cursor.fetchone()
    if r and r['cnt'] > 0:
        conn.close()
        return

    cursor.execute("SELECT emp_code, name, designation, department FROM employees")
    employees = cursor.fetchall()

    batch_data = []
    for emp in employees:
        ec = emp['emp_code']
        raw_name = emp['name']
        dept = emp['department']
        desig = emp['designation'] or ''
        category = payroll_engine.determine_employee_category(dept, desig)
        batch_data.append((ec, raw_name, category, desig, dept))

    if batch_data:
        cursor.executemany("""
        INSERT OR REPLACE INTO salary_profiles 
        (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount, default_bus, default_mess, default_hostel_eb, default_arrears)
        VALUES (?, ?, ?, ?, ?, 0.0, 'PNB', '', 'PUNB0401700', 0.0, 0.0, 0.0, 0.0, 0.0)
        """, batch_data)

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
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT count(*) as cnt FROM monthly_records WHERE month_year = ? AND net_salary IS NULL
    """, (month_year,))
    r_cnt = cursor.fetchone()
    if not r_cnt or r_cnt['cnt'] == 0:
        conn.close()
        return

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
    month_year = normalize_month_year(month_year)
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

    is_august = 'august' in month_year.lower()
    for r in rows:
        ec = r['emp_code']
        if active_only and is_august and reference_codes and ec not in reference_codes and not r['is_manual']:
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

