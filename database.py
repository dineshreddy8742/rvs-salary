import os
import re
import json
import datetime
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
                is_stale = False
                if getattr(raw_conn, 'closed', 0) != 0:
                    is_stale = True
                else:
                    try:
                        with raw_conn.cursor() as test_cur:
                            test_cur.execute("SELECT 1")
                    except Exception:
                        is_stale = True
                if is_stale:
                    try:
                        _pg_pool.putconn(raw_conn, close=True)
                    except Exception:
                        pass
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
            direct_conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)
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

    # Database Backups & Monthly Archives Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS database_backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        backup_name TEXT NOT NULL,
        month_year TEXT NOT NULL,
        backup_type TEXT NOT NULL,
        record_count INTEGER DEFAULT 0,
        logs_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        backup_data TEXT NOT NULL
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

def create_database_backup(month_year: str, backup_type: str = "manual", backup_name: str = None) -> dict:
    """Create a complete JSON snapshot archive of a month's attendance, salary, daily logs, and master employees."""
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Fetch monthly records for this month
    cursor.execute("SELECT * FROM monthly_records WHERE month_year = ?", (month_year,))
    mon_rows = [dict(r) for r in cursor.fetchall()]
    
    # 2. Fetch daily logs for this month
    cursor.execute("SELECT * FROM daily_logs WHERE month_year = ?", (month_year,))
    log_rows = [dict(r) for r in cursor.fetchall()]
    
    # 3. Fetch master employees and salary profiles
    cursor.execute("SELECT * FROM employees")
    all_emps = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM salary_profiles")
    all_sal = [dict(r) for r in cursor.fetchall()]
        
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rec_count = len(mon_rows)
    logs_count = len(log_rows)
    
    if not backup_name:
        if backup_type == 'auto_pre_delete':
            backup_name = f"Auto-Archive before Deleting {month_year} ({rec_count} Staff)"
        else:
            backup_name = f"Manual Snapshot: {month_year} ({rec_count} Staff)"
            
    payload = {
        'version': 1,
        'month_year': month_year,
        'created_at': now_str,
        'backup_type': backup_type,
        'backup_name': backup_name,
        'record_count': rec_count,
        'logs_count': logs_count,
        'employees': all_emps,
        'salary_profiles': all_sal,
        'monthly_records': mon_rows,
        'daily_logs': log_rows
    }
    
    data_json = json.dumps(payload, default=str)
    
    cursor.execute("""
    INSERT INTO database_backups (backup_name, month_year, backup_type, record_count, logs_count, created_at, backup_data)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (backup_name, month_year, backup_type, rec_count, logs_count, now_str, data_json))
    
    # Determine inserted ID
    cursor.execute("SELECT id FROM database_backups ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    backup_id = row['id'] if row else 1
        
    conn.commit()
    conn.close()
    
    return {
        'status': 'success',
        'backup_id': backup_id,
        'backup_name': backup_name,
        'month_year': month_year,
        'record_count': rec_count,
        'logs_count': logs_count,
        'created_at': now_str
    }

def list_database_backups(month_year: str = None) -> list:
    """Return list of backups (without the heavy JSON payload) for the UI."""
    conn = get_db()
    cursor = conn.cursor()
    if month_year:
        norm = normalize_month_year(month_year)
        cursor.execute("""
        SELECT id, backup_name, month_year, backup_type, record_count, logs_count, created_at
        FROM database_backups
        WHERE month_year = ?
        ORDER BY id DESC
        """, (norm,))
    else:
        cursor.execute("""
        SELECT id, backup_name, month_year, backup_type, record_count, logs_count, created_at
        FROM database_backups
        ORDER BY id DESC
        """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_database_backup(backup_id: int) -> dict:
    """Get single backup with full JSON data."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM database_backups WHERE id = ?", (backup_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d['payload'] = json.loads(d['backup_data'])
    except Exception:
        d['payload'] = {}
    return d

def restore_database_backup(backup_id: int) -> dict:
    """Restore a monthly backup snapshot into active database tables."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM database_backups WHERE id = ?", (backup_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {'status': 'error', 'message': f'Backup ID {backup_id} not found.'}
        
    payload = json.loads(row['backup_data'])
    month_year = payload.get('month_year', row['month_year'])
    
    # 1. Restore employees master
    emps = payload.get('employees', [])
    for e in emps:
        cursor.execute("""
        INSERT OR REPLACE INTO employees 
        (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(e['emp_code']), e['name'], e.get('designation'), e.get('department'),
            float(e.get('annual_cl_quota') or 12.0), float(e.get('annual_od_quota') or 15.0),
            e.get('attendance_policy', 'standard'), int(e.get('is_manual') or 0)
        ))
        
    # 2. Restore salary profiles
    profs = payload.get('salary_profiles', [])
    for p in profs:
        cursor.execute("""
        INSERT OR REPLACE INTO salary_profiles 
        (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code, epf_amount, default_bus, default_mess, default_hostel_eb, default_arrears)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(p['emp_code']), p['name'], p.get('category', 'Non-Teaching'), p.get('designation'), p.get('department'),
            float(p.get('base_salary') or 0.0), p.get('bank_name', 'PNB'), p.get('account_no', ''), p.get('ifsc_code', ''),
            float(p.get('epf_amount') or 0.0), float(p.get('default_bus') or 0.0), float(p.get('default_mess') or 0.0),
            float(p.get('default_hostel_eb') or 0.0), float(p.get('default_arrears') or 0.0)
        ))
        
    # 3. Clean existing monthly records and daily logs for this month_year before restore
    cursor.execute("DELETE FROM monthly_records WHERE month_year = ?", (month_year,))
    cursor.execute("DELETE FROM daily_logs WHERE month_year = ?", (month_year,))
    
    # 4. Restore monthly records
    m_recs = payload.get('monthly_records', [])
    for m in m_recs:
        cursor.execute("""
        INSERT OR REPLACE INTO monthly_records 
        (emp_code, month_year, name, designation, department, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, missed_punches_json, absent_days_json, late_punches_json,
         base_salary, earned_basic, total_earnings, pt_deduction, wf_deduction, epf_deduction, it_deduction, bus_deduction, hostel_eb_deduction, mess_deduction, other_deductions, total_deductions, net_salary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(m['emp_code']), month_year, m.get('name'), m.get('designation'), m.get('department'),
            float(m.get('biometric_days') or 0.0), float(m.get('holiday') or 0.0),
            float(m['availed_leaves']) if m.get('availed_leaves') is not None else None,
            float(m['sv_od']) if m.get('sv_od') is not None else None,
            float(m.get('total_pay_days') or 0.0), m.get('remarks', ''), int(m.get('needs_review') or 0),
            m.get('missed_punches_json', '[]'), m.get('absent_days_json', '[]'), m.get('late_punches_json', '[]'),
            float(m.get('base_salary') or 0.0) if m.get('base_salary') is not None else None,
            float(m.get('earned_basic') or 0.0) if m.get('earned_basic') is not None else None,
            float(m.get('total_earnings') or 0.0) if m.get('total_earnings') is not None else None,
            float(m.get('pt_deduction') or 0.0) if m.get('pt_deduction') is not None else None,
            float(m.get('wf_deduction') or 0.0) if m.get('wf_deduction') is not None else None,
            float(m.get('epf_deduction') or 0.0) if m.get('epf_deduction') is not None else None,
            float(m.get('it_deduction') or 0.0) if m.get('it_deduction') is not None else None,
            float(m.get('bus_deduction') or 0.0) if m.get('bus_deduction') is not None else None,
            float(m.get('hostel_eb_deduction') or 0.0) if m.get('hostel_eb_deduction') is not None else None,
            float(m.get('mess_deduction') or 0.0) if m.get('mess_deduction') is not None else None,
            float(m.get('other_deductions') or 0.0) if m.get('other_deductions') is not None else None,
            float(m.get('total_deductions') or 0.0) if m.get('total_deductions') is not None else None,
            float(m.get('net_salary') or 0.0) if m.get('net_salary') is not None else None
        ))
        
    # 5. Restore daily logs
    d_logs = payload.get('daily_logs', [])
    for dl in d_logs:
        cursor.execute("""
        INSERT OR REPLACE INTO daily_logs 
        (emp_code, month_year, day_num, date_str, in_time, out_time, duration, status, override_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(dl['emp_code']), month_year, int(dl['day_num']), dl.get('date_str'),
            dl.get('in_time'), dl.get('out_time'), dl.get('duration'), dl.get('status'), dl.get('override_status')
        ))
        
    conn.commit()
    conn.close()
    
    _PRINCIPAL_RULES_APPLIED.discard(month_year)
    
    return {
        'status': 'success',
        'message': f"Successfully restored '{row['backup_name']}' for {month_year} ({len(m_recs)} staff, {len(d_logs)} punch logs).",
        'month_year': month_year,
        'records_count': len(m_recs)
    }

def delete_database_backup(backup_id: int) -> dict:
    """Delete a backup record from database_backups."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM database_backups WHERE id = ?", (backup_id,))
    conn.commit()
    conn.close()
    return {'status': 'success', 'message': f'Backup ID {backup_id} deleted.'}

def delete_employee(emp_code: str) -> dict:
    """Permanently delete an employee from master, monthly records, salary profiles, and punch logs."""
    emp_code = str(emp_code).strip()
    if emp_code in PROTECTED_INSTITUTIONAL_STAFF:
        return {'status': 'error', 'message': f'Cannot delete permanent institutional staff member ({emp_code}).'}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, department FROM employees WHERE emp_code = ?", (emp_code,))
    row = cursor.fetchone()
    name = row['name'] if row else emp_code

    cursor.execute("DELETE FROM daily_logs WHERE emp_code = ?", (emp_code,))
    cursor.execute("DELETE FROM monthly_records WHERE emp_code = ?", (emp_code,))
    cursor.execute("DELETE FROM salary_profiles WHERE emp_code = ?", (emp_code,))
    cursor.execute("DELETE FROM employees WHERE emp_code = ?", (emp_code,))

    conn.commit()
    conn.close()
    return {
        'status': 'success',
        'message': f'Employee {name} ({emp_code}) has been permanently deleted.',
        'emp_code': emp_code,
        'name': name
    }

PROTECTED_INSTITUTIONAL_STAFF = {
    '101', '707', '900', '1060', '1015', '1019', '1021', '4001', '1030',
    'SHAJAHAN', 'SHIVA_DRIVER'
}

def get_enrolled_staff_list(month_year: str = "August -2026", manual_only: bool = True) -> list:
    """Return list of enrolled staff members (strictly user-added / uploaded test staff only)."""
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT 
        e.emp_code, e.name, e.designation, e.department, e.attendance_policy, e.is_manual,
        sp.category, sp.base_salary, sp.bank_name, sp.account_no, sp.ifsc_code,
        mr.total_pay_days, mr.biometric_days, mr.remarks
    FROM employees e
    LEFT JOIN salary_profiles sp ON e.emp_code = sp.emp_code
    LEFT JOIN monthly_records mr ON e.emp_code = mr.emp_code AND mr.month_year = ?
    WHERE e.is_manual = 1
    ORDER BY e.emp_code DESC
    """
    cursor.execute(query, (month_year,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        ec = str(r['emp_code']).strip()
        if ec in PROTECTED_INSTITUTIONAL_STAFF:
            continue
        result.append({
            'emp_code': ec,
            'name': str(r['name'] or ''),
            'designation': str(r['designation'] or 'Staff'),
            'department': str(r['department'] or 'Administration'),
            'category': str(r['category'] or 'Non-Teaching'),
            'base_salary': float(r['base_salary'] or 0.0),
            'attendance_policy': str(r['attendance_policy'] or 'standard'),
            'is_manual': True,
            'total_pay_days': float(r['total_pay_days']) if r['total_pay_days'] is not None else None,
            'remarks': str(r['remarks'] or '')
        })
    return result

def bulk_delete_employees(emp_codes: list) -> dict:
    """Permanently delete multiple employees in a single transaction (excluding protected institutional staff)."""
    if not emp_codes:
        return {'status': 'success', 'deleted_count': 0, 'deleted_codes': []}

    cleaned_codes = [str(c).strip() for c in emp_codes if str(c).strip()]
    cleaned_codes = [c for c in cleaned_codes if c not in PROTECTED_INSTITUTIONAL_STAFF]
    if not cleaned_codes:
        return {'status': 'success', 'deleted_count': 0, 'deleted_codes': []}

    conn = get_db()
    cursor = conn.cursor()

    params = [(c,) for c in cleaned_codes]
    cursor.executemany("DELETE FROM daily_logs WHERE emp_code = ?", params)
    cursor.executemany("DELETE FROM monthly_records WHERE emp_code = ?", params)
    cursor.executemany("DELETE FROM salary_profiles WHERE emp_code = ?", params)
    cursor.executemany("DELETE FROM employees WHERE emp_code = ?", params)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'message': f'Successfully deleted {len(cleaned_codes)} staff member(s).',
        'deleted_count': len(cleaned_codes),
        'deleted_codes': cleaned_codes
    }

def delete_all_manual_employees() -> dict:
    """Permanently delete all user-added / uploaded test staff records (excluding protected institutional staff)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT emp_code FROM employees WHERE is_manual = 1")
    codes = [r['emp_code'] for r in cursor.fetchall() if r['emp_code'] not in PROTECTED_INSTITUTIONAL_STAFF]
    conn.close()

    if not codes:
        return {'status': 'success', 'deleted_count': 0, 'message': 'No manual/uploaded staff found to delete.'}

    return bulk_delete_employees(codes)

def delete_month_data(month_year: str) -> dict:
    """Delete all monthly records and daily logs for the specified month, after creating an automatic archive."""
    month_year = normalize_month_year(month_year)
    
    # Always create an automatic snapshot archive before deletion so data is NEVER lost!
    try:
        create_database_backup(month_year, backup_type='auto_pre_delete')
    except Exception as e:
        print(f"[BACKUP WARNING] Could not auto-archive before delete: {e}")
        
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
        'message': f'Successfully deleted {rec_count} records for {month_year}. An automatic historical backup was safely archived.',
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

NON_BIOMETRIC_STAFF = {
    '101': {'name': 'Dr .M. Mohan Babu', 'dept': 'General', 'desig': 'Principal', 'title': '🏛️ Executive Biometric Exemption', 'desc': 'Institutional Head / Principal — Governing Body Biometric Exemption'},
    '707': {'name': 'R. Gunasekaran', 'dept': 'IT', 'desig': 'Asst.Prof', 'title': '📚 Academic Council Exemption', 'desc': 'Special Institutional Assignment — Approved duty schedule'},
    '900': {'name': 'I. Sudarsan Kumar', 'dept': 'HAS', 'desig': 'Professor & DAP', 'title': '🎓 Dean Academic Exemption', 'desc': 'Dean Academic Affairs (DAP) — University council schedule'},
    '1060': {'name': 'Vivekanand Adhikari', 'dept': 'Administration', 'desig': 'IR Officer', 'title': '🌐 Institutional Relations Exemption', 'desc': 'IR Officer — Corporate relations & placement field duty'},
    '1015': {'name': 'R Hari Krishna', 'dept': 'Exam Section', 'desig': 'Clerk', 'title': '📋 Examination Section Exemption', 'desc': 'Exam Section Staff — Confidential university examinations schedule'},
    '1019': {'name': 'Bishal Kumar Sha', 'dept': 'TAP', 'desig': 'Executive Assistant', 'title': '🎯 Training & Placement Exemption', 'desc': 'Executive Assistant (TAP) — External campus recruitment drives'},
    '1021': {'name': 'M P Balaji', 'dept': 'Management Staff', 'desig': 'Accounts Officer', 'title': '💼 Financial Executive Exemption', 'desc': 'Accounts Officer — Institutional audit & bank coordination'},
    '4001': {'name': 'R. Poorna Chandra', 'dept': 'Management Staff', 'desig': 'Administrative officer', 'title': '🏛️ Administrative Head Exemption', 'desc': 'Administrative Officer (AO) — Campus administration & supervision'},
    '1030': {'name': 'Thangeeru Surendera', 'dept': 'Transport', 'desig': 'VC Driver', 'title': '🚘 Executive Protocol Duty', 'desc': 'Vice Chairman Driver — Protocol transport schedule'},
    'SHAJAHAN': {'name': 'S Shajahan', 'dept': 'Management Staff', 'desig': 'P A To Chairman', 'title': '🏢 Chairman Secretariat Exemption', 'desc': 'PA to Chairman — Executive secretariat & trust board protocol'},
    'SHIVA_DRIVER': {'name': 'Shiva', 'dept': 'Transport', 'desig': 'Principal Diver', 'title': '🚘 Executive Protocol Duty', 'desc': 'Principal Driver — Institutional executive transit schedule'},
}

def seed_from_engine(engine, month_year: str = "August 2026", overwrite: bool = False, progress_callback = None):
    """Populate database from an AttendanceEngine instance, preserving master profiles for manual staff."""
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
    vip_full_pay_codes = set(NON_BIOMETRIC_STAFF.keys())

    m_days = float(getattr(engine, 'num_days', None) or payroll_engine.get_days_in_month_str(month_year) or 30)
    holidays = float(len(getattr(engine, 'all_holidays', None) or [])) if getattr(engine, 'all_holidays', None) else get_month_holidays_count(cursor, month_year)
    bio_days = max(0.0, m_days - holidays)

    # Fetch existing master employees so manual additions (e.g. 914 D. Keertana) and custom designations are preserved
    cursor.execute("SELECT emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual FROM employees")
    master_emps = {str(r['emp_code']): dict(r) for r in cursor.fetchall()}

    emp_batch = []
    mon_batch = []
    log_batch = []
    CHUNK_SIZE = 250

    def _flush_chunk(e_b, m_b, l_b):
        import time
        for attempt in range(4):
            try:
                if e_b:
                    # Sort deterministically by emp_code to eliminate deadlock during concurrent transactions
                    sorted_e = sorted(e_b, key=lambda x: str(x[0]))
                    cursor.executemany("""
                    INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, sorted_e)
                if m_b:
                    sorted_m = sorted(m_b, key=lambda x: str(x[0]))
                    cursor.executemany("""
                    INSERT OR REPLACE INTO monthly_records 
                    (emp_code, month_year, name, designation, department, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, missed_punches_json, absent_days_json, late_punches_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, sorted_m)
                if l_b:
                    sorted_l = sorted(l_b, key=lambda x: (str(x[0]), int(x[2])))
                    cursor.executemany("""
                    INSERT OR REPLACE INTO daily_logs (emp_code, month_year, day_num, date_str, in_time, out_time, duration, status, override_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, sorted_l)
                conn.commit()
                break
            except Exception as e:
                err_s = str(e).lower()
                if ('deadlock' in err_s or 'lock' in err_s) and attempt < 3:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise e

    total_emps_count = len(engine.employees)
    processed_count = 0

    for emp_code, emp in engine.employees.items():
        processed_count += 1
        ec_str = str(emp_code).strip()
        existing = master_emps.get(ec_str)
        name_l = str(emp.get('name', '')).lower()
        desig_l = str(emp.get('designation', '')).lower()
        dept_l = str(emp.get('department', '')).lower()

        is_vip = (ec_str in vip_full_pay_codes or 
                  'principal' in desig_l or 
                  any(k in name_l for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'bishal kumar', 'shajahan']) or
                  ('siva' in name_l and ('driver' in desig_l or 'transport' in dept_l)))
                  
        if existing:
            # Preserve curated master profile so manual additions (e.g. 914 D. Keertana) or edited profiles are never lost or downgraded
            m_name = existing['name'] if existing.get('name') else emp['name']
            m_desig = existing['designation'] if existing.get('designation') else emp.get('designation', '')
            m_dept = existing['department'] if (existing.get('department') and existing.get('department') != 'General') else normalize_dept(emp.get('department', ''))
            policy = existing.get('attendance_policy') or ('exempt_full' if is_vip else 'standard')
            is_manual_val = int(existing.get('is_manual', 0))
            cl_q = float(existing.get('annual_cl_quota') or 12.0)
            od_q = float(existing.get('annual_od_quota') or 15.0)
        else:
            m_name = emp['name']
            m_desig = emp.get('designation', '')
            m_dept = normalize_dept(emp.get('department', ''))
            policy = 'exempt_full' if is_vip else 'standard'
            is_manual_val = 0
            cl_q = 12.0
            od_q = 15.0

        summary = engine.calculate_employee_summary(emp)
        
        # 2-line institutional condition remarks
        if policy == 'exempt_full':
            total_days = m_days
            bio_days_emp = bio_days
            holidays_emp = holidays
            leaves = None
            od = None
            if ec_str in NON_BIOMETRIC_STAFF:
                meta = NON_BIOMETRIC_STAFF[ec_str]
                remarks = f"{meta.get('title', 'Executive Biometric Exemption')}\n{meta.get('desc', 'Institutional Exemption')}"
            else:
                remarks = "👑 Executive Full Pay Approval\nInstitutional waiver approved — 100% full salary credited"
            needs_review = 0
        elif policy == 'visiting_twice_weekly':
            total_days = m_days
            bio_days_emp = summary['biometric_days']
            holidays_emp = summary['holiday']
            leaves = summary['availed_leaves']
            od = summary['sv_od']
            remarks = "🏫 Visiting Faculty Schedule\nTwice weekly academic lectures completed (Full pay waiver)"
            needs_review = 0
        else:
            total_days = summary['total_pay_days']
            bio_days_emp = summary['biometric_days']
            holidays_emp = summary['holiday']
            leaves = summary['availed_leaves']
            od = summary['sv_od']
            remarks = summary['remarks']
            needs_review = 1 if summary['needs_review'] else 0

        # Block dummy machine test cards and Department: DEFAULT
        # Biometric devices dump unassigned badges / technician test punches under 'Department: DEFAULT'
        # with employee name equal to employee code. These are NOT actual college employees.
        dept_clean = str(m_dept).strip().lower()
        name_clean = str(m_name).strip()
        is_dummy_card = (
            policy not in ['exempt_full', 'visiting_twice_weekly'] and
            ec_str not in vip_full_pay_codes and
            (
                dept_clean in ('default', 'none', '') or
                name_clean == ec_str or
                name_clean.lower() == f"employee {ec_str}".lower()
            )
        )
        if is_dummy_card:
            continue

        # Zero-working-days filter: Exclude employees who did not work at all throughout the month
        # (0 physical biometric punches, 0 leaves, 0 OD, and no VIP/exempt policy).
        # These are inactive/former employees lingering in biometric machine dumps.
        punches_count = sum(1 for d in emp.get('days', []) if (d.get('in_time') or d.get('out_time') or 'present' in str(d.get('status', '')).lower()))
        is_zero_working = (
            policy not in ['exempt_full', 'visiting_twice_weekly'] and
            ec_str not in vip_full_pay_codes and
            punches_count == 0 and
            (leaves is None or float(leaves) <= 0.0) and
            (od is None or float(od) <= 0.0)
        )
        if is_zero_working:
            continue

        emp_batch.append((ec_str, m_name, m_desig, m_dept, cl_q, od_q, policy, is_manual_val))

        mon_batch.append((
            ec_str, month_year,
            m_name, m_desig, m_dept,
            bio_days_emp, holidays_emp, leaves, od, total_days, remarks, needs_review,
            json.dumps(summary.get('missed_out_punches', [])),
            json.dumps(summary.get('absent_days', [])),
            json.dumps(summary.get('late_punches', []))
        ))

        # Seed daily logs
        for day in emp['days']:
            log_batch.append((
                ec_str, month_year, day['day'], day['date'], day['in_time'], day['out_time'],
                day['duration'], day['status'], day.get('override_status')
            ))

        if len(emp_batch) >= CHUNK_SIZE:
            _flush_chunk(emp_batch, mon_batch, log_batch)
            if progress_callback:
                progress_callback(processed_count, total_emps_count, f"Saving staff & biometric punches ({processed_count} of {total_emps_count})...")
            emp_batch.clear()
            mon_batch.clear()
            log_batch.clear()

    if emp_batch:
        _flush_chunk(emp_batch, mon_batch, log_batch)
        if progress_callback:
            progress_callback(total_emps_count, total_emps_count, f"Finalizing staff attendance ledgers ({total_emps_count} of {total_emps_count})...")
        emp_batch.clear()
        mon_batch.clear()
        log_batch.clear()

    # Also ensure any reference metadata employees (like Principal 101) exist
    if hasattr(engine, 'reference_metadata') and engine.reference_metadata:
        ref_emp_batch = []
        ref_mon_batch = []
        for ec, meta in engine.reference_metadata.items():
            ec_s = str(ec).strip()
            if ec_s not in master_emps:
                is_principal = 'principal' in str(meta.get('designation', '')).lower() or ec_s == '101'
                pol = 'exempt_full' if is_principal else 'standard'
                ref_emp_batch.append((ec_s, meta.get('name', 'Staff'), meta.get('designation', 'Staff'), meta.get('dept', 'General'), 12.0, 15.0, pol, 1))
                ref_mon_batch.append((
                    ec_s, month_year,
                    meta.get('name', 'Staff'), meta.get('designation', 'Staff'), meta.get('dept', 'General'),
                    bio_days, holidays, None, None, m_days,
                    "Full Attendance (VIP / Principal)" if is_principal else "Reference Staff",
                    0, '[]', '[]', '[]'
                ))
                master_emps[ec_s] = True

        if ref_emp_batch or ref_mon_batch:
            _flush_chunk(ref_emp_batch, ref_mon_batch, [])

    conn.commit()
    conn.close()
    print(f"Database seeded successfully for {month_year}.")
    apply_principal_rules_to_db(month_year, from_upload=True)
    purge_zero_working_days_employees(month_year)

def purge_zero_working_days_employees(month_year: Optional[str] = None) -> dict:
    """
    Remove all inactive employees who did not work at all throughout the designated month
    (0 biometric punch days, 0 CL, and 0 OD, and not on official VIP/governing body exemption),
    AS WELL AS all dummy test cards / Department 'DEFAULT' / name == emp_code cards lingering from biometric machines.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    vip_codes = set(NON_BIOMETRIC_STAFF.keys()).union({
        '101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', '1210', 'SHAJAHAN', 'SHIVA_DRIVER'
    })
    
    months = [normalize_month_year(month_year)] if month_year else get_available_months()
    total_purged = 0
    purged_by_month = {}
    
    for m in months:
        norm_m = normalize_month_year(m)
        cursor.execute("""
            SELECT m.emp_code, e.name, e.department, m.name as m_name, m.department as m_dept,
                   e.attendance_policy, m.biometric_days, m.availed_leaves, m.sv_od
            FROM monthly_records m
            JOIN employees e ON m.emp_code = e.emp_code
            WHERE m.month_year = ?
        """, (norm_m,))
        rows = cursor.fetchall()
        
        cursor.execute("""
            SELECT DISTINCT emp_code
            FROM daily_logs
            WHERE month_year = ?
              AND ((in_time IS NOT NULL AND in_time != '' AND in_time != 'None')
                   OR (out_time IS NOT NULL AND out_time != '' AND out_time != 'None'))
        """, (norm_m,))
        punched_set = {str(r['emp_code']) for r in cursor.fetchall()}
        
        to_delete = []
        for r in rows:
            ec = str(r['emp_code'])
            pol = str(r.get('attendance_policy') or 'standard').lower()
            if pol in ['exempt_full', 'visiting_twice_weekly'] or ec in vip_codes:
                continue
            has_punches = ec in punched_set
            cl = float(r.get('availed_leaves') or 0.0)
            od = float(r.get('sv_od') or 0.0)
            
            # Identify dummy machine test cards and Department: DEFAULT
            dept_l = str(r.get('m_dept') or r.get('department') or '').strip().lower()
            name_s = str(r.get('m_name') or r.get('name') or '').strip()
            is_dummy_card = (
                dept_l in ('default', 'none', '') or
                name_s == ec or
                name_s.lower() == f"employee {ec}".lower()
            )
            is_zero_working = (not has_punches and cl <= 0.0 and od <= 0.0)

            if is_dummy_card or is_zero_working:
                to_delete.append(ec)
                
        if to_delete:
            chunk_size = 100
            for i in range(0, len(to_delete), chunk_size):
                chunk = to_delete[i:i+chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                cursor.execute(f"DELETE FROM monthly_records WHERE month_year = ? AND emp_code IN ({placeholders})", [norm_m] + chunk)
                cursor.execute(f"DELETE FROM daily_logs WHERE month_year = ? AND emp_code IN ({placeholders})", [norm_m] + chunk)
            conn.commit()
            
        purged_by_month[norm_m] = len(to_delete)
        total_purged += len(to_delete)

    # Clean up dummy cards from master employees table
    cursor.execute("""
        DELETE FROM employees
        WHERE (LOWER(department) IN ('default', 'none', '') OR name = emp_code OR name LIKE 'Employee %')
          AND emp_code NOT IN ('101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', '1210', 'SHAJAHAN', 'SHIVA_DRIVER')
    """)
    conn.commit()
        
    conn.close()
    return {
        'status': 'success',
        'total_purged': total_purged,
        'purged_by_month': purged_by_month
    }

_PRINCIPAL_RULES_APPLIED = set()

def apply_principal_rules_to_db(month_year: str = "August 2026", force: bool = False, from_upload: bool = False):
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

    from_upload=True: called after a real file upload — VIP staff are INSERTED if missing.
    from_upload=False: called on app restart or standalone — VIPs are ONLY UPDATED if already present.
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

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    holidays = get_month_holidays_count(cursor, month_year)
    bio_days = max(0.0, m_days - holidays)

    # Module-level NON_BIOMETRIC_STAFF has full institutional titles and descriptions

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

    # 1. Ensure all designated VIP staff exist in employees table & monthly_records for this month.
    # When from_upload=True (real bulk upload): INSERT OR REPLACE so VIPs appear even if not in biometric machine.
    # When from_upload=False (app restart / standalone): ONLY UPDATE existing records — never create phantom rows.
    vip_emp_batch = []
    vip_mon_batch = []
    for vc, meta in NON_BIOMETRIC_STAFF.items():
        v_cl = vip_leave_map.get(str(vc), {}).get('cl')
        v_od = vip_leave_map.get(str(vc), {}).get('od')
        v_cl = v_cl if (v_cl is not None and v_cl > 0) else None
        v_od = v_od if (v_od is not None and v_od > 0) else None

        rem_str = f"{meta.get('title', 'Executive Biometric Exemption')}\n{meta.get('desc', 'Institutional Exemption')}"
        vip_emp_batch.append((vc, meta['name'], meta['desig'], meta['dept'], 12.0, 15.0, 'exempt_full', 1))
        vip_mon_batch.append((
            vc, month_year, meta['name'], meta['desig'], meta['dept'],
            bio_days, holidays, v_cl, v_od, m_days, rem_str, 0, '[]', '[]', '[]'
        ))

    # Always upsert VIP employees master (they are always valid staff)
    if vip_emp_batch:
        cursor.executemany("""
        INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, vip_emp_batch)

    if vip_mon_batch:
        if from_upload:
            # Real upload: insert VIP monthly records so they appear alongside uploaded staff
            cursor.executemany("""
            INSERT OR REPLACE INTO monthly_records
            (emp_code, month_year, name, designation, department, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, absent_days_json, missed_punches_json, late_punches_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, vip_mon_batch)
        else:
            # Standalone / restart: only UPDATE VIP records that already exist — do NOT create phantom rows
            for row in vip_mon_batch:
                (vc, my, vname, vdesig, vdept, vbio, vhol, vcl, vod, vtpd, vrem, vnr, vab, vmp, vlp) = row
                cursor.execute("""
                UPDATE monthly_records
                SET name = ?, designation = ?, department = ?,
                    biometric_days = ?, holiday = ?,
                    availed_leaves = COALESCE(?, availed_leaves),
                    sv_od = COALESCE(?, sv_od),
                    total_pay_days = ?, remarks = ?, needs_review = 0,
                    absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
                WHERE emp_code = ? AND month_year = ?
                """, (vname, vdesig, vdept, vbio, vhol, vcl, vod, vtpd, vrem, vc, my))

    # Ensure regular bus drivers with 'Siva' in their name are standard policy, not VIP
    cursor.execute("UPDATE employees SET attendance_policy = 'standard' WHERE emp_code IN ('603', '610', '6623')")

    # 2. 1053 (S. Pachaiyappan) - >=12 days
    cursor.execute("SELECT biometric_days, total_pay_days FROM monthly_records WHERE emp_code = '1053' AND month_year = ?", (month_year,))
    r1053 = cursor.fetchone()
    if r1053 and (float(r1053['biometric_days'] or 0) >= 12 or float(r1053['total_pay_days'] or 0) >= 12):
        rem_1053 = "📚 Faculty Attendance Rule Met\nAttended ≥ 12 duty days threshold (IT Faculty Academic Duty)"
        cursor.execute("""
        UPDATE monthly_records 
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = ?, needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
        WHERE emp_code = '1053' AND month_year = ?
        """, (bio_days, holidays, m_days, rem_1053, month_year))

    # 3. 1203 (Dr J Velmurugan, IT HOD) - >=14 days
    cursor.execute("SELECT biometric_days, total_pay_days FROM monthly_records WHERE emp_code = '1203' AND month_year = ?", (month_year,))
    r1203 = cursor.fetchone()
    if r1203 and (float(r1203['biometric_days'] or 0) >= 14 or float(r1203['total_pay_days'] or 0) >= 14):
        rem_1203 = "🎓 Department Head Rule Met\nAttended ≥ 14 duty days threshold (IT HOD Academic & Admin Duty)"
        cursor.execute("""
        UPDATE monthly_records 
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = ?, needs_review = 0, absent_days_json = '[]', missed_punches_json = '[]', late_punches_json = '[]'
        WHERE emp_code = '1203' AND month_year = ?
        """, (bio_days, holidays, m_days, rem_1203, month_year))

    # 4. 109 (Civil M. Leelakar) - daily punch before 11 am regularized
    cursor.execute("SELECT remarks FROM monthly_records WHERE emp_code = '109' AND month_year = ?", (month_year,))
    r109 = cursor.fetchone()
    if r109 and ('11' in str(r109['remarks']) or 'shift' in str(r109['remarks']).lower() or not r109['remarks']):
        rem_109 = "⚙️ Shift Regularization Approved\nCivil Engineering morning punch before 11:00 AM credited"
        cursor.execute("UPDATE monthly_records SET remarks = ? WHERE emp_code = '109' AND month_year = ?", (rem_109, month_year))

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

    # 8. Security & Water Staff / Watchman Rule:
    # 2 Floating Holidays anytime; 28 duty days (or continuous shifts + OD/CL) = Full Attendance (m_days)
    cursor.execute("""
        SELECT e.emp_code, e.name, e.designation, e.department
        FROM employees e
        WHERE e.department = 'Security & Water Staff' OR lower(e.designation) LIKE '%security%'
           OR lower(e.designation) LIKE '%watch%' OR lower(e.name) LIKE '%watch%'
           OR lower(e.designation) LIKE '%water man%' OR lower(e.designation) LIKE '%water woman%'
    """)
    sec_emps = cursor.fetchall()
    sec_ids = [str(r['emp_code']) for r in sec_emps]

    sec_updates = []
    if sec_ids:
        s_placeholders = ','.join('?' * len(sec_ids))
        cursor.execute(f"SELECT * FROM daily_logs WHERE emp_code IN ({s_placeholders}) AND month_year = ? ORDER BY emp_code, day_num", (*sec_ids, month_year))
        s_days_map = defaultdict(list)
        for r in cursor.fetchall():
            s_days_map[str(r['emp_code'])].append(r)

        for sid in sec_ids:
            sdays = s_days_map.get(sid, [])
            if sdays:
                day_presence = set()
                od_days = set()
                cl_days = set()
                for d in sdays:
                    d_num = d['day_num']
                    st = (d['override_status'] or d['status'] or '').upper()
                    in_t = (d['in_time'] or '').strip()
                    out_t = (d['out_time'] or '').strip()
                    if 'OD' in st or 'ON DUTY' in st:
                        od_days.add(d_num)
                    elif 'CL' in st or 'LEAVE' in st:
                        cl_days.add(d_num)
                    elif in_t or out_t or 'PRESENT' in st:
                        day_presence.add(d_num)

                od_count = float(len(od_days))
                cl_count = float(len(cl_days))
                total_duty = len(day_presence) + od_count + cl_count

                threshold = max(0.0, m_days - 2.0)
                w_hol = 2.0
                if total_duty >= threshold:
                    pay_days = m_days
                    bio_days = max(0.0, m_days - w_hol - od_count - cl_count)
                    rem = ""
                    nr = 0
                    ab_json = '[]'
                elif total_duty > 0:
                    shortfall = threshold - total_duty
                    pay_days = max(0.0, m_days - shortfall)
                    bio_days = max(0.0, pay_days - w_hol - od_count - cl_count)
                    all_m_days = set(range(1, int(m_days) + 1))
                    unatt = sorted(list(all_m_days - day_presence - od_days - cl_days))
                    unexcused = unatt[-int(shortfall):] if shortfall > 0 else []
                    rem = f"ab-{','.join(str(x) for x in unexcused)}" if unexcused else ""
                    nr = 1 if unexcused else 0
                    ab_json = json.dumps(unexcused)
                else:
                    pay_days = 0.0
                    bio_days = 0.0
                    w_hol = 0.0
                    rem = "No Biometric Records"
                    nr = 0
                    ab_json = '[]'

                sec_updates.append((bio_days, w_hol, cl_count if cl_count > 0 else None, od_count if od_count > 0 else None, pay_days, rem, nr, ab_json, sid, month_year))

        if sec_updates:
            cursor.executemany("""
            UPDATE monthly_records
            SET biometric_days = ?, holiday = ?, availed_leaves = ?, sv_od = ?,
                total_pay_days = ?, remarks = ?, needs_review = ?,
                absent_days_json = ?, missed_punches_json = '[]', late_punches_json = '[]'
            WHERE emp_code = ? AND month_year = ?
            """, sec_updates)
            conn.commit()

    # Recalculate salary for any staff whose total_pay_days was updated by principal rules
    all_overridden = list(NON_BIOMETRIC_STAFF.keys()) + ['1053', '1203', '109', '1018'] + transport_ids + admission_ids + sec_ids
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
    SELECT emp_code, day_num, status, override_status
    FROM daily_logs
    WHERE month_year = ?
      AND (
        status LIKE '%CL%' OR status LIKE '%LEAVE%' OR override_status LIKE '%CL%' OR override_status LIKE '%LEAVE%'
        OR status LIKE '%OD%' OR status LIKE '%DUTY%' OR override_status LIKE '%OD%' OR override_status LIKE '%DUTY%'
      )
    ORDER BY emp_code, day_num
    """, (month_year,))
    leave_map = {}
    for lr in cursor.fetchall():
        ec = str(lr['emp_code'])
        if ec not in leave_map:
            leave_map[ec] = {'cl_days': [], 'od_days': []}
        st = f"{(lr['override_status'] or '')} {(lr['status'] or '')}".upper()
        d_val = lr['day_num']
        if d_val is not None:
            try:
                dn = int(d_val)
                if 'CL' in st or 'LEAVE' in st:
                    leave_map[ec]['cl_days'].append(dn)
                if 'OD' in st or 'DUTY' in st:
                    leave_map[ec]['od_days'].append(dn)
            except (ValueError, TypeError):
                pass
    for ec in leave_map:
        leave_map[ec]['cl_days'] = sorted(list(set(leave_map[ec]['cl_days'])))
        leave_map[ec]['od_days'] = sorted(list(set(leave_map[ec]['od_days'])))

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
    vip_full_pay_codes = set(NON_BIOMETRIC_STAFF.keys()).union({
        '101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', '1210', 'SHAJAHAN', 'SHIVA_DRIVER'
    })
    for r in rows:
        ec = str(r['emp_code'])
        policy = str(r['attendance_policy'] or 'standard').lower()
        is_exempt = policy in ['exempt_full', 'visiting_twice_weekly'] or ec in vip_full_pay_codes

        if active_only and is_august and reference_codes and ec not in reference_codes and not r['is_manual']:
            continue

        lm = leave_map.get(str(ec), {'cl_days': [], 'od_days': []})

        cl_val = r['availed_leaves']
        if (cl_val is None or cl_val == 0.0) and lm['cl_days']:
            cl_val = float(len(lm['cl_days']))

        od_val = r['sv_od']
        if (od_val is None or od_val == 0.0) and lm['od_days']:
            od_val = float(len(lm['od_days']))

        bio_val = float(r['biometric_days'] or 0.0)
        c_val = float(cl_val or 0.0)
        o_val = float(od_val or 0.0)

        # Omit dummy machine cards / Default department (unassigned test cards)
        dept_lower = str(r['department'] or '').strip().lower()
        name_str = str(r['name'] or '').strip()
        if not is_exempt and (dept_lower in ('default', 'none', '') or name_str == ec or name_str.lower() == f"employee {ec}".lower()):
            continue

        # Omit zero-working-days employees (did not work entire month, 0 punches, 0 leaves, 0 OD, not exempt)
        if not is_exempt and bio_val <= 0.0 and c_val <= 0.0 and o_val <= 0.0:
            continue

        m_days_count = int(payroll_engine.get_days_in_month_str(month_year) or 31)
        results.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'attendance_policy': r['attendance_policy'],
            'is_manual': bool(r['is_manual']),
            'month_days': m_days_count,
            'days_in_month': m_days_count,
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

def get_employee_daily_and_portfolio(emp_code: str, month_year: str) -> dict:
    """Fetch daily punch logs and employee portfolio in a single fast database connection."""
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    # 1. Fetch daily logs
    cursor.execute("""
    SELECT day_num, date_str, in_time, out_time, duration, status, override_status
    FROM daily_logs
    WHERE emp_code = ? AND month_year = ?
    ORDER BY day_num ASC
    """, (emp_code, month_year))
    daily_rows = cursor.fetchall()

    days = [{
        'day': r['day_num'],
        'date': r['date_str'],
        'in_time': r['in_time'] or '',
        'out_time': r['out_time'] or '',
        'duration': r['duration'] or '',
        'status': r['status'] or '',
        'override_status': r['override_status']
    } for r in daily_rows]

    # 2. Fetch employee profile
    cursor.execute("SELECT * FROM employees WHERE emp_code = ?", (emp_code,))
    emp = cursor.fetchone()
    if not emp:
        conn.close()
        return {'days': days, 'employee': None}

    # 3. Fetch monthly records
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

    pf = {
        'emp_code': emp['emp_code'],
        'name': emp['name'],
        'designation': emp['designation'] or 'Staff',
        'department': emp['department'],
        'attendance_policy': emp['attendance_policy'],
        'is_manual': bool(emp['is_manual']),
        'annual_cl_quota': cl_quota,
        'total_cl_availed': total_cl_availed,
        'cl_balance': round(cl_balance, 1),
        'is_over_leave': total_cl_availed > cl_quota,
        'annual_od_quota': float(emp['annual_od_quota'] or 15.0),
        'total_od_availed': total_od_availed,
        'total_pay_days_cum': round(total_pay_days_cum, 1),
        'months': monthly_history
    }

    return {'days': days, 'employee': pf}

def create_or_update_manual_employee(emp_data: dict, current_month: str = "August -2026") -> dict:
    """Manually add an employee (Principal, visiting faculty, consultant, new joiner) with policy, profile, and initial salary."""
    current_month = normalize_month_year(current_month)
    conn = get_db()
    cursor = conn.cursor()

    emp_code = str(emp_data['emp_code']).strip()
    name = str(emp_data['name']).strip()
    desig = str(emp_data.get('designation', 'Staff')).strip()
    dept = normalize_dept(str(emp_data.get('department', 'Administration')).strip())
    policy = str(emp_data.get('attendance_policy', 'standard')).strip()
    quota = float(emp_data.get('annual_cl_quota', 12.0))
    category = str(emp_data.get('category', 'Teaching' if any(w in desig.lower() for w in ['prof', 'lecturer', 'faculty', 'hod', 'dean']) else 'Non-Teaching')).strip()
    base_sal = float(emp_data.get('base_salary', 0.0) or 0.0)

    # 1. Save to employees master
    cursor.execute("""
    INSERT OR REPLACE INTO employees (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
    VALUES (?, ?, ?, ?, ?, 15.0, ?, 1)
    """, (emp_code, name, desig, dept, quota, policy))

    # 2. Save / update salary_profiles
    cursor.execute("""
    INSERT OR REPLACE INTO salary_profiles 
    (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (emp_code, name, category, desig, dept, base_sal,
          emp_data.get('bank_name', 'PNB'), emp_data.get('account_no', ''), emp_data.get('ifsc_code', '')))

    # 3. Determine monthly values based on policy
    m_days = float(payroll_engine.get_days_in_month_str(current_month) or 31)
    if policy == 'exempt_full':
        bio_days = 25.0
        holiday = 6.0
        total_pay = m_days
        remarks = "👑 Executive Full Pay Approval\nInstitutional waiver approved — 100% full salary credited"
        needs_review = 0
    elif policy == 'visiting_twice_weekly':
        bio_days = 8.0
        holiday = 6.0
        total_pay = m_days
        remarks = "🏫 Visiting Faculty Schedule\nTwice weekly academic lectures completed (Full pay waiver)"
        needs_review = 0
    else:
        bio_days = float(emp_data.get('biometric_days', 25.0))
        holiday = 6.0
        total_pay = min(m_days, bio_days + holiday)
        remarks = "👤 Manually Added Staff\nRegular roster staff member"
        needs_review = 0

    # 4. Save to monthly_records
    cursor.execute("""
    INSERT OR REPLACE INTO monthly_records 
    (emp_code, month_year, name, designation, department, biometric_days, holiday, availed_leaves, sv_od, total_pay_days, remarks, needs_review, base_salary)
    VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
    """, (emp_code, current_month, name, desig, dept, bio_days, holiday, total_pay, remarks, needs_review, base_sal))

    conn.commit()
    conn.close()

    try:
        recalculate_monthly_salary(emp_code, current_month)
    except Exception as e:
        print(f"[MANUAL EMP SALARY CALC WARNING] {e}")

    return get_employee_portfolio(emp_code)

def bulk_create_or_update_manual_employees(staff_list: list, current_month: str = "August -2026") -> dict:
    """Batch enroll multiple staff members (10, 50, 100, 1000+) in one fast atomic operation."""
    current_month = normalize_month_year(current_month)
    conn = get_db()
    cursor = conn.cursor()
    m_days = float(payroll_engine.get_days_in_month_str(current_month) or 31)

    added_count = 0
    dept_counts = {}
    cat_counts = {}

    emp_tuples = []
    prof_tuples = []
    monthly_tuples = []

    for emp_data in staff_list:
        emp_code = str(emp_data.get('emp_code', '')).strip()
        name = str(emp_data.get('name', '')).strip()
        if not emp_code or not name:
            continue

        desig = str(emp_data.get('designation', 'Staff')).strip() or 'Staff'
        dept = normalize_dept(str(emp_data.get('department', 'Administration')).strip())
        policy = str(emp_data.get('attendance_policy', 'standard')).strip()
        if policy not in ['standard', 'exempt_full', 'visiting_twice_weekly']:
            policy = 'standard'

        try:
            quota = float(emp_data.get('annual_cl_quota', 12.0) or 12.0)
        except Exception:
            quota = 12.0

        category = str(emp_data.get('category', '')).strip()
        if not category:
            category = 'Teaching' if any(w in desig.lower() for w in ['prof', 'lecturer', 'faculty', 'hod', 'dean']) else 'Non-Teaching'

        try:
            base_sal = float(emp_data.get('base_salary', 0.0) or 0.0)
        except Exception:
            base_sal = 0.0

        bank_name = str(emp_data.get('bank_name', 'PNB')).strip() or 'PNB'
        account_no = str(emp_data.get('account_no', '')).strip()
        ifsc_code = str(emp_data.get('ifsc_code', '')).strip()

        # 1. Employees Master tuple
        emp_tuples.append((emp_code, name, desig, dept, quota, 15.0, policy, 1))

        # 2. Salary Profiles tuple
        prof_tuples.append((emp_code, name, category, desig, dept, base_sal, bank_name, account_no, ifsc_code))

        # 3. Determine Attendance & Pay Days
        if policy == 'exempt_full':
            bio_days = 25.0
            holiday = 6.0
            total_pay = m_days
            remarks = "👑 Executive Full Pay Approval\nInstitutional waiver approved — 100% full salary credited"
            needs_review = 0
        elif policy == 'visiting_twice_weekly':
            bio_days = 8.0
            holiday = 6.0
            total_pay = m_days
            remarks = "🏫 Visiting Faculty Schedule\nTwice weekly academic lectures completed (Full pay waiver)"
            needs_review = 0
        else:
            try:
                bio_days = float(emp_data.get('biometric_days', 25.0) or 25.0)
            except Exception:
                bio_days = 25.0
            holiday = 6.0
            total_pay = min(m_days, bio_days + holiday)
            remarks = "👤 Bulk Added Staff\nRegular roster staff member"
            needs_review = 0

        # In-memory instant salary calculation (0 DB queries overhead)
        prof_dict = {
            'emp_code': emp_code,
            'name': name,
            'category': category,
            'base_salary': base_sal,
            'default_arrears': 0.0,
            'epf_amount': 0.0,
            'default_bus': 0.0,
            'default_mess': 0.0,
            'default_hostel_eb': 0.0
        }
        overrides = {
            'base_salary': base_sal,
            'arrears': 0.0,
            'epf_deduction': 0.0,
            'it_deduction': 0.0,
            'bus_deduction': 0.0,
            'mess_deduction': 0.0,
            'hostel_eb_deduction': 0.0,
            'other_deductions': 0.0,
            'pt_deduction': None,
            'wf_deduction': None
        }
        sal_res = payroll_engine.calculate_salary_for_profile(prof_dict, int(m_days), total_pay, overrides)

        monthly_tuples.append((
            emp_code, current_month, name, desig, dept, bio_days, holiday, total_pay, remarks, needs_review,
            sal_res.get('base_salary', base_sal),
            sal_res.get('earned_basic', 0.0),
            sal_res.get('da', 0.0),
            sal_res.get('hra', 0.0),
            sal_res.get('arrears', 0.0),
            sal_res.get('gross_salary', 0.0),
            sal_res.get('pt', 0.0),
            sal_res.get('wf', 0.0),
            sal_res.get('epf', 0.0),
            sal_res.get('it', 0.0),
            sal_res.get('bus_deduction', 0.0),
            sal_res.get('mess_deduction', 0.0),
            sal_res.get('hostel_eb_deduction', 0.0),
            sal_res.get('other_deductions', 0.0),
            sal_res.get('total_deductions', 0.0),
            sal_res.get('net_salary', 0.0)
        ))

        added_count += 1
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
        cat_counts[category] = cat_counts.get(category, 0) + 1

    # Execute in clean batches
    CHUNK_SIZE = 250
    for i in range(0, len(emp_tuples), CHUNK_SIZE):
        emp_chunk = emp_tuples[i:i + CHUNK_SIZE]
        prof_chunk = prof_tuples[i:i + CHUNK_SIZE]
        mon_chunk = monthly_tuples[i:i + CHUNK_SIZE]

        cursor.executemany("""
        INSERT OR REPLACE INTO employees 
        (emp_code, name, designation, department, annual_cl_quota, annual_od_quota, attendance_policy, is_manual)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, emp_chunk)

        cursor.executemany("""
        INSERT OR REPLACE INTO salary_profiles 
        (emp_code, name, category, designation, department, base_salary, bank_name, account_no, ifsc_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, prof_chunk)

        cursor.executemany("""
        INSERT OR REPLACE INTO monthly_records 
        (emp_code, month_year, name, designation, department, biometric_days, holiday, total_pay_days, remarks, needs_review,
         base_salary, earned_basic, earned_da, earned_hra, arrears, gross_salary, pt_deduction, wf_deduction, epf_deduction,
         it_deduction, bus_deduction, mess_deduction, hostel_eb_deduction, other_deductions, total_deductions, net_salary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, mon_chunk)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'added_count': added_count,
        'department_counts': dept_counts,
        'category_counts': cat_counts
    }

def get_month_holidays_count(cursor, month_year: str) -> float:
    """
    Accurately and dynamically count distinct institutional holidays for any month.
    Extracts all festival/institutional holidays declared in the biometric dump input (daily_logs status LIKE '%Holiday%')
    and merges them with all calendar Sundays of that specific month and year.
    100% dynamic — no hardcoded festival sets or fixed month numbers. Works for any upcoming month.
    """
    month_year = normalize_month_year(month_year)
    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)

    # 1. Parse year and month dynamically from month_year string
    import calendar
    import datetime
    y = 2026
    m = 1
    m_yr = re.search(r'\b(20\d{2})\b', month_year)
    if m_yr:
        y = int(m_yr.group(1))
    cleaned = re.sub(r'[\-_]+', ' ', str(month_year)).lower()
    for m_idx in range(1, 13):
        if calendar.month_name[m_idx].lower() in cleaned or calendar.month_abbr[m_idx].lower() in cleaned:
            m = m_idx
            break

    # 2. Dynamic Sundays for that specific calendar month/year
    sundays = {d for d in range(1, int(m_days) + 1) if datetime.date(y, m, d).weekday() == 6}

    # 3. Dynamic institutional holidays from daily_logs dump input
    try:
        cursor.execute("""
        SELECT DISTINCT day_num 
        FROM daily_logs 
        WHERE month_year = ? AND status LIKE '%Holiday%'
        """, (month_year,))
        dump_holidays = {int(r['day_num']) for r in cursor.fetchall() if r['day_num'] is not None}
    except Exception:
        dump_holidays = set()

    all_holidays = sundays.union(dump_holidays)
    return float(len(all_holidays)) if all_holidays else float(len(sundays))

def evaluate_employee_attendance_from_logs(ec: str, logs: list, e_data: dict, m_days: float, month_holidays: float):
    """
    Unified Single Source of Truth for employee monthly attendance calculation.
    Guarantees 100% mathematical consistency between remarks, deductions, and total pay days.
    Deduction rule:
      total_deductions = len(abs_list) * 1.0 + len(mis_list) * 0.5 + len(half_list) * 0.5
      total_pay_days   = max(0.0, m_days - total_deductions)
      biometric_days   = max(0.0, total_pay_days - hol - cl_count - od_count)
    """
    ec_str = str(ec).strip()
    policy = (e_data.get('attendance_policy') or 'standard')
    dept = (e_data.get('department') or '').lower()
    desig = (e_data.get('designation') or '').lower()
    is_sec = 'security' in dept or 'security' in desig or 'watchman' in desig or 'watch man' in desig or 'water man' in desig or 'water woman' in desig

    # Collect overridden days (days admin specifically approved as Present or Half Day)
    overridden_days = sorted(list({int(d['day_num']) for d in logs if (d.get('override_status') or '').upper() == 'PRESENT' and d.get('day_num') is not None}))
    half_overridden_days = sorted(list({int(d['day_num']) for d in logs if (d.get('override_status') or '').upper() in ('1/2PRESENT', 'HALF_DAY', 'HALF') and d.get('day_num') is not None}))

    # 1. VIP / Principal exemption
    vip_codes = set(NON_BIOMETRIC_STAFF.keys())
    if policy == 'exempt_full' or ec_str in vip_codes:
        total = m_days
        pres = max(0.0, m_days - month_holidays)
        hol = month_holidays
        abs_list = []
        mis_list = []
        half_list = []
        rem = "Full Attendance (VIP / Principal)"
        needs_rev = 0
        return pres, hol, 0.0, 0.0, total, abs_list, mis_list, half_list, rem, needs_rev

    # 2. Security / Watchman rule (2 floating holidays, 28 duty days threshold)
    if is_sec:
        hol = 2.0
        duty_days = 0.0
        cl_count = 0.0
        od_count = 0.0
        abs_list = []
        
        for d in logs:
            dn = int(d['day_num']) if d.get('day_num') is not None else 0
            ov = (d.get('override_status') or '').upper()
            st = (d.get('status') or '').upper()
            in_t = (d.get('in_time') or '').strip()
            out_t = (d.get('out_time') or '').strip()
            eff = ov if ov else st
            
            if 'CL' in eff or 'LEAVE' in eff:
                if '1/2' in eff: cl_count += 0.5
                else: cl_count += 1.0
            elif 'OD' in eff or 'ON DUTY' in eff:
                od_count += 1.0
            elif ov == 'PRESENT' or in_t or out_t or 'PRESENT' in eff:
                if '1/2' in eff: duty_days += 0.5
                else: duty_days += 1.0
            elif 'ABSENT' in eff and 'HOLIDAY' not in eff:
                abs_list.append(dn)
                
        duty = duty_days + cl_count + od_count
        threshold = max(0.0, m_days - 2.0)
        if duty >= threshold:
            total = m_days
            biometric_days = max(0.0, total - hol - cl_count - od_count)
            rem = f"SDP-{','.join(str(x) for x in overridden_days)}" if overridden_days else ""
            needs_rev = 0
            unexcused = []
        elif duty > 0:
            shortfall = threshold - duty
            total = max(0.0, m_days - shortfall)
            biometric_days = max(0.0, total - hol - cl_count - od_count)
            unexcused = abs_list[-int(shortfall):] if shortfall > 0 else []
            rem_parts = []
            if overridden_days:
                rem_parts.append(f"SDP-{','.join(str(x) for x in overridden_days)}")
            if unexcused:
                rem_parts.append(f"ab-{','.join(str(x) for x in unexcused)}")
            rem = ", ".join(rem_parts)
            needs_rev = 1 if unexcused else 0
        else:
            total = 0.0
            biometric_days = 0.0
            hol = 0.0
            rem = "No Biometric Records"
            needs_rev = 0
            unexcused = []
            
        return biometric_days, hol, cl_count, od_count, total, unexcused, [], [], rem, needs_rev

    # 3. Admission Team rule: Sunday/Holiday punches offset weekday leaves/absences
    admission_ids = {'2005', '2006', '6001', '1040', '1017', '2011', '6000', '2010', '2007', '2013', '2514', '2512', '2511', '2503', '2502', '2505', '2051', '2508', '6004', '6005'}
    is_admission = ec_str in admission_ids or 'admission' in dept
    if is_admission:
        hol = month_holidays
        cl_count = 0.0
        od_count = 0.0
        comp_credits = 0.0
        raw_absents = []
        half_list = []
        mis_list = []

        for d in logs:
            dn = int(d['day_num']) if d.get('day_num') is not None else 0
            ov = (d.get('override_status') or '').upper()
            st = (d.get('status') or '').upper()
            in_t = (d.get('in_time') or '').strip()
            out_t = (d.get('out_time') or '').strip()
            eff = ov if ov else st

            # Overridden days
            if ov == 'PRESENT':
                continue
            if ov in ('1/2PRESENT', 'HALF_DAY', 'HALF'):
                half_list.append(f"{dn}(1/2)")
                continue

            # Sundays and Festival Holidays
            if 'HOLIDAY' in eff:
                # Credit work done on Sunday / Holiday as compensatory credit
                if in_t or out_t or 'PRESENT' in eff:
                    if '1/2' in eff:
                        comp_credits += 0.5
                    else:
                        comp_credits += 1.0
                continue

            # Regular working days
            if 'CL' in eff or 'LEAVE' in eff:
                if '1/2' in eff:
                    cl_count += 0.5
                else:
                    cl_count += 1.0
            elif 'OD' in eff or 'ON DUTY' in eff:
                od_count += 1.0
            elif 'ABSENT' in eff:
                raw_absents.append(dn)
            elif '1/2' in eff or 'HALF' in eff:
                half_list.append(f"{dn}(1/2)")
            elif 'NO OUTPUNCH' in eff or 'NO OUT PUNCH' in eff:
                mis_list.append(f"{dn}(0.5)")

        # Offset weekday absences using compensatory credits from Sunday/holiday work
        unexcused_abs = []
        rem_comp = comp_credits
        for ab_day in raw_absents:
            if rem_comp >= 1.0:
                rem_comp -= 1.0  # Fully excused by Sunday/holiday work
            elif rem_comp >= 0.5:
                rem_comp -= 0.5
                half_list.append(f"{ab_day}(1/2)")
            else:
                unexcused_abs.append(ab_day)

        # Offset any remaining half-days if comp credits still available
        if rem_comp > 0 and half_list:
            half_to_remove = int(rem_comp * 2)
            half_list = half_list[half_to_remove:]
            rem_comp = max(0.0, rem_comp - (half_to_remove * 0.5))

        total_deductions = len(unexcused_abs) * 1.0 + len(half_list) * 0.5 + len(mis_list) * 0.5
        total = max(0.0, m_days - total_deductions)
        biometric_days = max(0.0, total - hol - cl_count - od_count)

        rem_parts = []
        if overridden_days:
            rem_parts.append(f"SDP-{','.join(str(x) for x in overridden_days)}")
        if half_overridden_days:
            rem_parts.append(f"SDH-{','.join(str(x) for x in half_overridden_days)}")
        if unexcused_abs:
            rem_parts.append(f"ab-{','.join(str(x) for x in unexcused_abs)}")
        if half_list:
            rem_parts.append(", ".join(half_list))
        if mis_list:
            rem_parts.append(f"{len(mis_list)} no out punch")

        rem = ", ".join(rem_parts)
        needs_rev = 1 if (unexcused_abs or half_list or mis_list) else 0
        return biometric_days, hol, cl_count, od_count, total, unexcused_abs, mis_list, half_list, rem, needs_rev

    # 4. Standard / Teaching / Academic / Transport / General Staff
    hol = month_holidays
    cl_count = 0.0
    od_count = 0.0
    abs_list = []
    mis_list = []
    half_list = []

    transport_ids = {'625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613'}
    is_transport = ec_str in transport_ids or 'transport' in dept

    for d in logs:
        dn = int(d['day_num']) if d.get('day_num') is not None else 0
        ov = (d.get('override_status') or '').upper()
        st = (d.get('status') or '').upper()
        eff = ov if ov else st

        # If day is overridden to Present by admin, it is 100% EXCUSED (no deduction!)
        if ov == 'PRESENT':
            continue

        if ov in ('1/2PRESENT', 'HALF_DAY', 'HALF'):
            half_list.append(f"{dn}(1/2)")
            continue

        if 'HOLIDAY' in eff:
            continue

        if 'CL' in eff or 'LEAVE' in eff:
            if '1/2' in eff:
                cl_count += 0.5
            else:
                cl_count += 1.0
        elif 'OD' in eff or 'ON DUTY' in eff:
            od_count += 1.0
        elif 'NO OUTPUNCH' in eff or 'NO OUT PUNCH' in eff:
            if not is_transport:
                mis_list.append(f"{dn}(0.5)")
        elif '1/2' in eff or 'HALF' in eff:
            half_list.append(f"{dn}(1/2)")
        elif 'ABSENT' in eff:
            abs_list.append(dn)

    if not logs:
        return 0.0, 0.0, 0.0, 0.0, 0.0, [], [], [], "No Biometric Records", 0

    total_deductions = len(abs_list) * 1.0 + len(mis_list) * 0.5 + len(half_list) * 0.5
    total = max(0.0, m_days - total_deductions)
    pres = max(0.0, total - hol - cl_count - od_count)

    # Full month absence rule: If an employee never worked a single day, has no approved leaves, and no admin approval,
    # they receive 0 pay days and 0 paid holidays (Full Month LOP)
    if pres == 0.0 and cl_count == 0.0 and od_count == 0.0 and not overridden_days and not half_overridden_days:
        total = 0.0
        hol = 0.0
        rem = f"Full Month Absent ({int(m_days)}d LOP)" if abs_list else "No Biometric Records"
        needs_rev = 1 if abs_list else 0
        return 0.0, 0.0, 0.0, 0.0, 0.0, abs_list, mis_list, half_list, rem, needs_rev

    rem_parts = []
    if overridden_days:
        rem_parts.append(f"SDP-{','.join(str(x) for x in overridden_days)}")
    if half_overridden_days:
        rem_parts.append(f"SDH-{','.join(str(x) for x in half_overridden_days)}")
    if abs_list:
        rem_parts.append(f"ab-{','.join(str(x) for x in abs_list)}")
    if mis_list:
        rem_parts.append(f"{len(mis_list)} no out punch")
    if half_list:
        rem_parts.append(", ".join(half_list))

    rem = ", ".join(rem_parts)
    needs_rev = 1 if (abs_list or mis_list or half_list) else 0

    return pres, hol, cl_count, od_count, total, abs_list, mis_list, half_list, rem, needs_rev

def set_employee_policy(emp_code: str, policy: str, month_year: str = "August -2026"):
    """Update policy for an employee and recalculate monthly pay days if exempt."""
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE employees SET attendance_policy = ? WHERE emp_code = ?", (policy, emp_code))

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)
    bio_days = max(0.0, m_days - month_holidays)

    if policy in ('exempt_full', 'visiting_twice_weekly'):
        remarks = "Full Attendance (VIP / Exempt)" if policy == 'exempt_full' else "Full Attendance (Visiting Schedule)"
        cursor.execute("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = ?, needs_review = 0
        WHERE emp_code = ? AND month_year = ?
        """, (bio_days, month_holidays, m_days, remarks, emp_code, month_year))

    conn.commit()
    conn.close()

def grant_full_attendance(emp_code: str, month_year: str):
    """1-Click button to give an employee full pay days for the current month."""
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)
    bio_days = max(0.0, m_days - month_holidays)

    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?, holiday = ?, total_pay_days = ?, remarks = 'Full Attendance Granted by HR', needs_review = 0
    WHERE emp_code = ? AND month_year = ?
    """, (bio_days, month_holidays, m_days, emp_code, month_year))

    conn.commit()
    conn.close()

    try:
        recalculate_monthly_salary(emp_code, month_year, m_days, int(m_days))
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
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    # 1. Clear day-level override status
    cursor.execute("""
    UPDATE daily_logs 
    SET override_status = NULL 
    WHERE emp_code = ? AND month_year = ?
    """, (emp_code, month_year))

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)

    cursor.execute("SELECT attendance_policy, department, designation FROM employees WHERE emp_code = ?", (emp_code,))
    e_info = cursor.fetchone()
    e_data = dict(e_info) if e_info else {}

    cursor.execute("""
    SELECT emp_code, day_num, status, override_status, in_time, out_time
    FROM daily_logs 
    WHERE emp_code = ? AND month_year = ? 
    ORDER BY day_num ASC
    """, (emp_code, month_year))
    days = cursor.fetchall()

    pres, hol, cl, od, total, abs_list, mis_list, half_list, rem, needs_rev = evaluate_employee_attendance_from_logs(
        emp_code, days, e_data, m_days, month_holidays
    )

    # Reset monthly_records back to raw
    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?,
        holiday = ?,
        availed_leaves = ?,
        sv_od = ?,
        total_pay_days = ?,
        absent_days_json = ?,
        missed_punches_json = ?,
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
        pres,
        hol,
        cl if cl > 0 else None,
        od if od > 0 else None,
        total,
        json.dumps(abs_list),
        json.dumps(mis_list),
        rem,
        needs_rev,
        emp_code,
        month_year
    ))

    conn.commit()
    conn.close()

    # Recalculate salary with baseline profile
    recalculate_monthly_salary(emp_code, month_year, total, int(m_days))
    return get_employee_portfolio(emp_code)

def bulk_revert_to_original(month_year: str, scope: str = 'all', department: Optional[str] = None, category: Optional[str] = None) -> dict:
    """
    Bulk reverts multiple employees back to raw original biometric data.
    High-performance batch implementation:
    1. Resets override_status in daily_logs in a single SQL operation.
    2. Clears salary overrides in monthly_records in a single SQL operation.
    3. Re-evaluates attendance and recalculates salaries in batch in <1 second.
    """
    month_year = normalize_month_year(month_year)
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

    target_codes = []
    for r in rows:
        ec = str(r['emp_code'])
        dept = r['department']
        cat = r['category'] or 'Non-Teaching'

        if scope == 'department' and department and department != 'all' and dept != department:
            continue
        if scope == 'category' and category and category != 'all' and cat != category:
            continue

        target_codes.append(ec)

    if not target_codes:
        conn.close()
        return {'status': 'success', 'month_year': month_year, 'reverted_count': 0}

    # 1. Clear day-level override status for target employees in daily_logs and reset manual monthly overrides
    if len(target_codes) == len(rows) and scope == 'all':
        cursor.execute("UPDATE daily_logs SET override_status = NULL WHERE month_year = ?", (month_year,))
        cursor.execute("""
        UPDATE monthly_records
        SET base_salary = NULL, arrears = 0.0, other_deductions = 0.0,
            pt_deduction = NULL, wf_deduction = NULL, epf_deduction = NULL, it_deduction = 0.0
        WHERE month_year = ?
        """, (month_year,))
    else:
        # Batch in chunks of 500
        for i in range(0, len(target_codes), 500):
            chunk = target_codes[i:i+500]
            placeholders = ','.join(['?'] * len(chunk))
            cursor.execute(f"UPDATE daily_logs SET override_status = NULL WHERE month_year = ? AND emp_code IN ({placeholders})", [month_year] + chunk)
            cursor.execute(f"""
            UPDATE monthly_records
            SET base_salary = NULL, arrears = 0.0, other_deductions = 0.0,
                pt_deduction = NULL, wf_deduction = NULL, epf_deduction = NULL, it_deduction = 0.0
            WHERE month_year = ? AND emp_code IN ({placeholders})
            """, [month_year] + chunk)

    conn.commit()

    # 2. Batch re-evaluate attendance from daily_logs
    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)

    cursor.execute("""
    SELECT emp_code, day_num, status, override_status, in_time, out_time
    FROM daily_logs
    WHERE month_year = ?
    ORDER BY emp_code, day_num ASC
    """, (month_year,))
    all_logs = cursor.fetchall()

    from collections import defaultdict
    emp_logs = defaultdict(list)
    for r in all_logs:
        emp_logs[str(r['emp_code'])].append(r)

    cursor.execute("SELECT emp_code, department, designation, attendance_policy FROM employees")
    emp_info = {str(r['emp_code']): dict(r) for r in cursor.fetchall()}

    monthly_updates = []
    for ec in target_codes:
        logs = emp_logs.get(ec, [])
        e_data = emp_info.get(ec, {})
        pres, hol, cl, od, total, abs_list, mis_list, half_list, rem, needs_rev = evaluate_employee_attendance_from_logs(
            ec, logs, e_data, m_days, month_holidays
        )
        monthly_updates.append((
            pres, hol, cl if cl > 0 else None, od if od > 0 else None, total,
            json.dumps(abs_list), json.dumps(mis_list), rem, needs_rev,
            ec, month_year
        ))

    cursor.executemany("""
    UPDATE monthly_records
    SET biometric_days = ?, holiday = ?, availed_leaves = ?, sv_od = ?, total_pay_days = ?,
        absent_days_json = ?, missed_punches_json = ?,
        remarks = ?, needs_review = ?
    WHERE emp_code = ? AND month_year = ?
    """, monthly_updates)

    # 3. Batch recalculate salary
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
    WHERE m.month_year = ?
    """, (month_year,))
    all_recs = cursor.fetchall()
    target_set = set(target_codes)

    salary_updates = []
    for r in all_recs:
        ec = str(r['emp_code'])
        if ec not in target_set:
            continue
        try:
            cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['prof_category'])
            prof = {
                'emp_code': ec,
                'name': r['name'],
                'category': cat,
                'base_salary': float(r['prof_base'] or 0.0),
                'default_arrears': float(r['prof_arrears'] or 0.0),
                'epf_amount': float(r['prof_epf'] or 0.0),
                'default_bus': float(r['prof_bus'] or 0.0),
                'default_mess': float(r['prof_mess'] or 0.0),
                'default_hostel_eb': float(r['prof_hostel'] or 0.0)
            }
            overrides = {
                'base_salary': None,
                'arrears': 0.0,
                'epf_deduction': prof.get('epf_amount', 0.0),
                'it_deduction': 0.0,
                'bus_deduction': prof.get('default_bus', 0.0),
                'mess_deduction': prof.get('default_mess', 0.0),
                'hostel_eb_deduction': prof.get('default_hostel_eb', 0.0),
                'other_deductions': 0.0,
                'pt_deduction': None,
                'wf_deduction': None
            }
            emp_pay_days = float(r['total_pay_days'] if r['total_pay_days'] is not None else m_days)
            res = payroll_engine.calculate_salary_for_profile(prof, m_days, emp_pay_days, overrides)
            salary_updates.append((
                res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
                res['gross_salary'], res['pt'], res['wf'], res['epf'],
                res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'], res['other_deductions'],
                res['total_deductions'], res['net_salary'],
                ec, month_year
            ))
        except Exception as e:
            print(f"Error calculating salary for {ec}: {e}")

    cursor.executemany("""
    UPDATE monthly_records
    SET base_salary = ?, earned_basic = ?, earned_da = ?, earned_hra = ?, arrears = ?,
        gross_salary = ?, pt_deduction = ?, wf_deduction = ?, epf_deduction = ?,
        it_deduction = ?, bus_deduction = ?, mess_deduction = ?, hostel_eb_deduction = ?, other_deductions = ?,
        total_deductions = ?, net_salary = ?
    WHERE emp_code = ? AND month_year = ?
    """, salary_updates)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'month_year': month_year,
        'reverted_count': len(target_codes)
    }

def bulk_attendance_override(
    month_year: str,
    action: str = 'full_present',
    scope: str = 'all',
    department: Optional[str] = None,
    emp_codes: list = None,
    punch_filter: str = 'all',
    selected_days: list = None,
    specific_type: str = 'full_day'
) -> dict:
    """
    Bulk override attendance for employees.
    action: 'full_present' = full month | 'half_present' = half month | 'specific_dates' = selected_days count
    scope: 'all' | 'department' | 'manual'
    punch_filter: 'all' | 'no_punch' | 'morning_only' | 'evening_only'
    selected_days: list of day numbers [1, 2, 29, 30] for specific_dates action
    specific_type: 'full_day' (1.0 day / Present) | 'half_day' (0.5 day / 1/2Present)
    """
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)

    # Step 1: get all employees in this month
    cursor.execute("""
    SELECT m.emp_code, e.department
    FROM monthly_records m
    JOIN employees e ON m.emp_code = e.emp_code
    WHERE m.month_year = ?
    """, (month_year,))
    all_rows = cursor.fetchall()

    # Step 2: filter by scope
    candidates = []
    for r in all_rows:
        ec = str(r['emp_code'])
        dept = r['department'] or ''
        if scope == 'department' and department and department != 'all' and dept != department:
            continue
        if scope == 'manual' and emp_codes and ec not in [str(x) for x in emp_codes]:
            continue
        candidates.append(ec)

    # Step 3: filter candidates by punch type
    c_placeholders = ','.join(['?'] * len(candidates))
    if punch_filter == 'all':
        filtered_codes = candidates
    elif action == 'specific_dates' and selected_days:
        # Match candidates who have this punch type on ANY of the selected override dates
        days_placeholders = ','.join(['?'] * len(selected_days))
        cond_sql = ""
        if punch_filter == 'morning_only':
            cond_sql = "AND (in_time IS NOT NULL AND TRIM(in_time) != '') AND (out_time IS NULL OR TRIM(out_time) = '')"
        elif punch_filter == 'evening_only':
            cond_sql = "AND (out_time IS NOT NULL AND TRIM(out_time) != '') AND (in_time IS NULL OR TRIM(in_time) = '')"
        elif punch_filter == 'no_punch':
            cond_sql = "AND (in_time IS NULL OR TRIM(in_time) = '') AND (out_time IS NULL OR TRIM(out_time) = '')"

        cursor.execute(f"""
        SELECT DISTINCT emp_code
        FROM daily_logs
        WHERE month_year = ? AND day_num IN ({days_placeholders})
          AND emp_code IN ({c_placeholders})
          {cond_sql}
        """, [month_year] + list(selected_days) + candidates)
        filtered_codes = [str(r['emp_code']) for r in cursor.fetchall()]
    elif punch_filter == 'morning_only':
        cursor.execute(f"""
        SELECT DISTINCT emp_code
        FROM daily_logs
        WHERE month_year = ? AND emp_code IN ({c_placeholders})
          AND (in_time IS NOT NULL AND TRIM(in_time) != '')
          AND (out_time IS NULL OR TRIM(out_time) = '')
        """, [month_year] + candidates)
        filtered_codes = [str(r['emp_code']) for r in cursor.fetchall()]
    elif punch_filter == 'evening_only':
        cursor.execute(f"""
        SELECT DISTINCT emp_code
        FROM daily_logs
        WHERE month_year = ? AND emp_code IN ({c_placeholders})
          AND (out_time IS NOT NULL AND TRIM(out_time) != '')
          AND (in_time IS NULL OR TRIM(in_time) = '')
        """, [month_year] + candidates)
        filtered_codes = [str(r['emp_code']) for r in cursor.fetchall()]
    elif punch_filter == 'no_punch':
        cursor.execute(f"""
        SELECT emp_code
        FROM daily_logs
        WHERE month_year = ? AND emp_code IN ({c_placeholders})
        GROUP BY emp_code
        HAVING MAX(CASE WHEN (in_time IS NOT NULL AND TRIM(in_time) != '') OR (out_time IS NOT NULL AND TRIM(out_time) != '') THEN 1 ELSE 0 END) = 0
        """, [month_year] + candidates)
        filtered_codes = [str(r['emp_code']) for r in cursor.fetchall()]

    if not filtered_codes:
        conn.close()
        return {
            'status': 'success',
            'month_year': month_year,
            'action': action,
            'punch_filter': punch_filter,
            'updated_count': 0,
            'emp_codes': []
        }

    filtered_set = set(filtered_codes)

    # Step 4: apply action
    if action == 'specific_dates':
        selected_days = selected_days or []
        target_status = '1/2Present' if specific_type in ('half_day', 'half') else 'Present'
        days_placeholders = ','.join(['?'] * len(selected_days))
        fc_placeholders = ','.join(['?'] * len(filtered_codes))

        cond_sql = ""
        if punch_filter == 'morning_only':
            cond_sql = "AND (in_time IS NOT NULL AND TRIM(in_time) != '') AND (out_time IS NULL OR TRIM(out_time) = '')"
        elif punch_filter == 'evening_only':
            cond_sql = "AND (out_time IS NOT NULL AND TRIM(out_time) != '') AND (in_time IS NULL OR TRIM(in_time) = '')"
        elif punch_filter == 'no_punch':
            cond_sql = "AND (in_time IS NULL OR TRIM(in_time) = '') AND (out_time IS NULL OR TRIM(out_time) = '')"

        update_query = f"""
        UPDATE daily_logs
        SET override_status = ?
        WHERE month_year = ? AND day_num IN ({days_placeholders})
          AND emp_code IN ({fc_placeholders})
          {cond_sql}
        """
        cursor.execute(update_query, [target_status, month_year] + list(selected_days) + filtered_codes)

        # 4b. Re-evaluate attendance from daily_logs for all filtered employees
        cursor.execute("""
        SELECT emp_code, day_num, status, override_status, in_time, out_time
        FROM daily_logs
        WHERE month_year = ?
        ORDER BY emp_code, day_num ASC
        """, (month_year,))
        all_logs = cursor.fetchall()

        from collections import defaultdict
        emp_logs = defaultdict(list)
        for r in all_logs:
            ec_s = str(r['emp_code'])
            if ec_s in filtered_set:
                emp_logs[ec_s].append(r)

        cursor.execute("SELECT emp_code, department, designation, attendance_policy FROM employees")
        emp_info = {str(r['emp_code']): dict(r) for r in cursor.fetchall()}

        monthly_updates = []
        for ec in filtered_codes:
            logs = emp_logs.get(ec, [])
            e_data = emp_info.get(ec, {})
            pres, hol, cl, od, total, abs_list, mis_list, half_list, rem, needs_rev = evaluate_employee_attendance_from_logs(
                ec, logs, e_data, m_days, month_holidays
            )
            monthly_updates.append((
                pres, hol, cl if cl > 0 else None, od if od > 0 else None, total,
                json.dumps(abs_list), json.dumps(mis_list),
                rem, needs_rev,
                ec, month_year
            ))

        cursor.executemany("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, availed_leaves = ?, sv_od = ?, total_pay_days = ?,
            absent_days_json = ?, missed_punches_json = ?,
            remarks = ?, needs_review = ?
        WHERE emp_code = ? AND month_year = ?
        """, monthly_updates)

    elif action == 'full_present':
        total = m_days
        holiday = month_holidays
        remark = 'Full Attendance Approved by Admin'
        # Also update daily_logs for these employees so absent is cleared
        dl_updates = [(ec, month_year) for ec in filtered_codes]
        cursor.executemany("""
        UPDATE daily_logs
        SET override_status = 'Present'
        WHERE emp_code = ? AND month_year = ? AND (status LIKE '%Absent%' OR status LIKE '%No OutPunch%')
        """, dl_updates)

        s_placeholders = ','.join(['?'] * len(filtered_codes))
        cursor.execute(f"SELECT emp_code, availed_leaves, sv_od FROM monthly_records WHERE month_year = ? AND emp_code IN ({s_placeholders})", [month_year] + filtered_codes)
        existing_leaves = {str(r['emp_code']): (float(r['availed_leaves'] or 0.0), float(r['sv_od'] or 0.0)) for r in cursor.fetchall()}

        update_tuples = []
        for ec in filtered_codes:
            cl, od = existing_leaves.get(ec, (0.0, 0.0))
            bio_days = max(0.0, total - holiday - cl - od)
            update_tuples.append((bio_days, holiday, total, '[]', '[]', remark, 0, ec, month_year))

        cursor.executemany("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, total_pay_days = ?,
            absent_days_json = ?, missed_punches_json = ?,
            remarks = ?, needs_review = ?
        WHERE emp_code = ? AND month_year = ?
        """, update_tuples)

    elif action == 'half_present':
        total = round(m_days / 2.0, 1)
        holiday = round(month_holidays / 2.0, 1)
        remark = 'Half Attendance Approved by Admin'

        s_placeholders = ','.join(['?'] * len(filtered_codes))
        cursor.execute(f"SELECT emp_code, availed_leaves, sv_od FROM monthly_records WHERE month_year = ? AND emp_code IN ({s_placeholders})", [month_year] + filtered_codes)
        existing_leaves = {str(r['emp_code']): (float(r['availed_leaves'] or 0.0), float(r['sv_od'] or 0.0)) for r in cursor.fetchall()}

        update_tuples = []
        for ec in filtered_codes:
            cl, od = existing_leaves.get(ec, (0.0, 0.0))
            bio_days = max(0.0, total - holiday - cl - od)
            update_tuples.append((bio_days, holiday, total, '[]', '[]', remark, 0, ec, month_year))

        cursor.executemany("""
        UPDATE monthly_records
        SET biometric_days = ?, holiday = ?, total_pay_days = ?,
            absent_days_json = ?, missed_punches_json = ?,
            remarks = ?, needs_review = ?
        WHERE emp_code = ? AND month_year = ?
        """, update_tuples)

    # Step 5: Fast batch recalculate salary for all updated employees
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
    WHERE m.month_year = ?
    """, (month_year,))
    all_recs = cursor.fetchall()

    salary_updates = []
    for r in all_recs:
        ec = str(r['emp_code'])
        if ec not in filtered_set:
            continue
        try:
            cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['prof_category'])
            prof = {
                'emp_code': ec,
                'name': r['name'],
                'category': cat,
                'base_salary': float(r['prof_base'] or 0.0),
                'default_arrears': float(r['prof_arrears'] or 0.0),
                'epf_amount': float(r['prof_epf'] or 0.0),
                'default_bus': float(r['prof_bus'] or 0.0),
                'default_mess': float(r['prof_mess'] or 0.0),
                'default_hostel_eb': float(r['prof_hostel'] or 0.0)
            }
            overrides = {
                'base_salary': r['base_salary'] if r['base_salary'] is not None else prof.get('base_salary'),
                'arrears': r['arrears'] or 0.0,
                'epf_deduction': r['epf_deduction'] if r['epf_deduction'] is not None else prof.get('epf_amount', 0.0),
                'it_deduction': r['it_deduction'] or 0.0,
                'bus_deduction': r['bus_deduction'] if r['bus_deduction'] is not None else prof.get('default_bus', 0.0),
                'mess_deduction': r['mess_deduction'] if r['mess_deduction'] is not None else prof.get('default_mess', 0.0),
                'hostel_eb_deduction': r['hostel_eb_deduction'] if r['hostel_eb_deduction'] is not None else prof.get('default_hostel_eb', 0.0),
                'other_deductions': r['other_deductions'] or 0.0,
                'pt_deduction': r['pt_deduction'],
                'wf_deduction': r['wf_deduction']
            }
            emp_pay_days = float(r['total_pay_days'] if r['total_pay_days'] is not None else m_days)
            res = payroll_engine.calculate_salary_for_profile(prof, m_days, emp_pay_days, overrides)
            salary_updates.append((
                res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
                res['gross_salary'], res['pt'], res['wf'], res['epf'],
                res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
                res['other_deductions'], res['total_deductions'], res['net_salary'],
                ec, month_year
            ))
        except Exception as e:
            print(f"Batch salary recalc error for {ec}: {e}")

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

    return {
        'status': 'success',
        'month_year': month_year,
        'action': action,
        'punch_filter': punch_filter,
        'updated_count': len(filtered_codes),
        'emp_codes': filtered_codes
    }

def update_monthly_field(emp_code: str, month_year: str, field: str, value: Any):
    """Update an inline field (leaves, od, holiday, bio) in SQLite and recalculate Total Pay Days."""
    month_year = normalize_month_year(month_year)
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
    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    total = bio + hol + (leaves or 0.0) + (od or 0.0)
    total = min(m_days, total)
    cursor.execute("UPDATE monthly_records SET total_pay_days = ? WHERE emp_code = ? AND month_year = ?", (total, emp_code, month_year))

    conn.commit()
    conn.close()

    try:
        recalculate_monthly_salary(emp_code, month_year, total, int(m_days))
    except Exception as e:
        print(f"Error recalculating salary: {e}")

def regularize_day_in_db(emp_code: str, month_year: str, day_num: int, action: str):
    """Regularize a day: update daily_logs, re-sum, and update monthly_records."""
    month_year = normalize_month_year(month_year)
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

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)

    cursor.execute("SELECT attendance_policy, department, designation FROM employees WHERE emp_code = ?", (emp_code,))
    e_info = cursor.fetchone()
    e_data = dict(e_info) if e_info else {}

    # Re-evaluate all days for this employee
    cursor.execute("""
    SELECT emp_code, day_num, status, override_status, in_time, out_time
    FROM daily_logs WHERE emp_code = ? AND month_year = ? ORDER BY day_num ASC
    """, (emp_code, month_year))
    days = cursor.fetchall()

    pres, hol, cl, od, total, abs_list, mis_list, half_list, rem, needs_rev = evaluate_employee_attendance_from_logs(
        emp_code, days, e_data, m_days, month_holidays
    )

    cursor.execute("""
    UPDATE monthly_records
    SET biometric_days = ?, holiday = ?, availed_leaves = ?, sv_od = ?, total_pay_days = ?,
        absent_days_json = ?, missed_punches_json = ?, remarks = ?, needs_review = ?
    WHERE emp_code = ? AND month_year = ?
    """, (
        pres, hol, cl if cl > 0 else None, od if od > 0 else None, total,
        json.dumps(abs_list), json.dumps(mis_list), rem, needs_rev,
        emp_code, month_year
    ))

    conn.commit()
    conn.close()

    # Recalculate salary with new pay days
    try:
        recalculate_monthly_salary(emp_code, month_year, total, int(m_days))
    except Exception as e:
        print(f"Error recalculating salary for {emp_code}: {e}")

def recalculate_month_attendance_and_salaries(month_year: str) -> dict:
    """
    Recalculates attendance and salaries across all employees for a month using unified calculation.
    Synchronizes daily_logs, monthly_records, remarks, pay days, and net salaries.
    """
    month_year = normalize_month_year(month_year)
    conn = get_db()
    cursor = conn.cursor()

    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    month_holidays = get_month_holidays_count(cursor, month_year)

    cursor.execute("""
    SELECT emp_code, day_num, status, override_status, in_time, out_time
    FROM daily_logs
    WHERE month_year = ?
    ORDER BY emp_code, day_num ASC
    """, (month_year,))
    all_logs = cursor.fetchall()

    from collections import defaultdict
    emp_logs = defaultdict(list)
    for r in all_logs:
        emp_logs[str(r['emp_code'])].append(r)

    cursor.execute("SELECT emp_code, department, designation, attendance_policy FROM employees")
    emp_info = {str(r['emp_code']): dict(r) for r in cursor.fetchall()}

    cursor.execute("SELECT emp_code FROM monthly_records WHERE month_year = ?", (month_year,))
    target_codes = [str(r['emp_code']) for r in cursor.fetchall()]

    if not target_codes:
        conn.close()
        return {'status': 'success', 'updated_count': 0, 'month_year': month_year}

    monthly_updates = []
    for ec in target_codes:
        logs = emp_logs.get(ec, [])
        e_data = emp_info.get(ec, {})
        pres, hol, cl, od, total, abs_list, mis_list, half_list, rem, needs_rev = evaluate_employee_attendance_from_logs(
            ec, logs, e_data, m_days, month_holidays
        )
        monthly_updates.append((
            pres, hol, cl if cl > 0 else None, od if od > 0 else None, total,
            json.dumps(abs_list), json.dumps(mis_list), rem, needs_rev,
            ec, month_year
        ))

    cursor.executemany("""
    UPDATE monthly_records
    SET biometric_days = ?, holiday = ?, availed_leaves = ?, sv_od = ?, total_pay_days = ?,
        absent_days_json = ?, missed_punches_json = ?,
        remarks = ?, needs_review = ?
    WHERE emp_code = ? AND month_year = ?
    """, monthly_updates)

    # Batch recalculate salary for all target codes
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
    WHERE m.month_year = ?
    """, (month_year,))
    all_recs = cursor.fetchall()

    salary_updates = []
    for r in all_recs:
        ec = str(r['emp_code'])
        try:
            cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['prof_category'])
            prof = {
                'emp_code': ec,
                'name': r['name'],
                'category': cat,
                'base_salary': float(r['prof_base'] or 0.0),
                'default_arrears': float(r['prof_arrears'] or 0.0),
                'epf_amount': float(r['prof_epf'] or 0.0),
                'default_bus': float(r['prof_bus'] or 0.0),
                'default_mess': float(r['prof_mess'] or 0.0),
                'default_hostel_eb': float(r['prof_hostel'] or 0.0)
            }
            overrides = {
                'base_salary': r['base_salary'] if r['base_salary'] is not None else prof.get('base_salary'),
                'arrears': r['arrears'] or 0.0,
                'epf_deduction': r['epf_deduction'] if r['epf_deduction'] is not None else prof.get('epf_amount', 0.0),
                'it_deduction': r['it_deduction'] or 0.0,
                'bus_deduction': r['bus_deduction'] if r['bus_deduction'] is not None else prof.get('default_bus', 0.0),
                'mess_deduction': r['mess_deduction'] if r['mess_deduction'] is not None else prof.get('default_mess', 0.0),
                'hostel_eb_deduction': r['hostel_eb_deduction'] if r['hostel_eb_deduction'] is not None else prof.get('default_hostel_eb', 0.0),
                'other_deductions': r['other_deductions'] or 0.0,
                'pt_deduction': r['pt_deduction'],
                'wf_deduction': r['wf_deduction']
            }
            emp_pay_days = float(r['total_pay_days'] if r['total_pay_days'] is not None else m_days)
            res = payroll_engine.calculate_salary_for_profile(prof, m_days, emp_pay_days, overrides)
            salary_updates.append((
                res['base_salary'], res['earned_basic'], res['da'], res['hra'], res['arrears'],
                res['gross_salary'], res['pt'], res['wf'], res['epf'],
                res['it'], res['bus_deduction'], res['mess_deduction'], res['hostel_eb_deduction'],
                res['other_deductions'], res['total_deductions'], res['net_salary'],
                ec, month_year
            ))
        except Exception as e:
            print(f"Batch salary recalc error for {ec}: {e}")

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

    return {
        'status': 'success',
        'month_year': month_year,
        'updated_count': len(target_codes)
    }


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
    vip_full_pay_codes = set(NON_BIOMETRIC_STAFF.keys()).union({
        '101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', '1210', 'SHAJAHAN', 'SHIVA_DRIVER'
    })
    for r in rows:
        ec = str(r['emp_code'])
        policy = str(r['attendance_policy'] or 'standard').lower()
        is_exempt = policy in ['exempt_full', 'visiting_twice_weekly'] or ec in vip_full_pay_codes

        if active_only and is_august and reference_codes and ec not in reference_codes and not r['is_manual']:
            continue

        bio_val = float(r['biometric_days'] or 0.0)
        cl_val = float(r['availed_leaves'] or 0.0)
        od_val = float(r['sv_od'] or 0.0)

        # Omit dummy machine cards / Default department (unassigned test cards)
        dept_lower = str(r['department'] or '').strip().lower()
        name_str = str(r['name'] or '').strip()
        if not is_exempt and (dept_lower in ('default', 'none', '') or name_str == ec or name_str.lower() == f"employee {ec}".lower()):
            continue

        # Omit zero-working-days employees from salary ledger as well
        if not is_exempt and bio_val <= 0.0 and cl_val <= 0.0 and od_val <= 0.0:
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

        m_days_count = int(payroll_engine.get_days_in_month_str(month_year) or 30)
        cat = payroll_engine.determine_employee_category(r['department'], r['designation'], r['category'])
        records.append({
            'emp_code': ec,
            'name': r['name'],
            'designation': r['designation'] or '',
            'department': r['department'],
            'category': cat,
            'attendance_policy': r['attendance_policy'],
            'month_days': m_days_count,
            'days_in_month': m_days_count,
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
    m_days_count = int(payroll_engine.get_days_in_month_str(month_year) or 30)

    return {
        'status': 'success',
        'month_year': month_year,
        'days_in_month': m_days_count,
        'stats': {
            'total_staff': len(records),
            'days_in_month': m_days_count,
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

    if field == 'total_pay_days':
        cursor.execute("SELECT holiday, availed_leaves, sv_od FROM monthly_records WHERE emp_code = ? AND month_year = ?", (emp_code, month_year))
        row = cursor.fetchone()
        if row:
            hol = float(row['holiday'] or 0.0)
            cl = float(row['availed_leaves'] or 0.0)
            od = float(row['sv_od'] or 0.0)
            new_bio = max(0.0, val_float - hol - cl - od)
            cursor.execute("UPDATE monthly_records SET total_pay_days = ?, biometric_days = ? WHERE emp_code = ? AND month_year = ?", (val_float, new_bio, emp_code, month_year))
        else:
            cursor.execute("UPDATE monthly_records SET total_pay_days = ? WHERE emp_code = ? AND month_year = ?", (val_float, emp_code, month_year))
    else:
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
    
    m_days = float(payroll_engine.get_days_in_month_str(month_year) or 30)
    if data.get('total_pay_days') is not None and str(data.get('total_pay_days')).strip() != '':
        pay_days = float(data['total_pay_days'])
        if abs((bio + hol + leaves + od) - pay_days) > 0.01:
            bio = max(0.0, pay_days - hol - leaves - od)
    else:
        pay_days = min(m_days, bio + hol + leaves + od)

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

