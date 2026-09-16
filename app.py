import os
import tempfile
import json
from flask import Flask, request, jsonify, send_file, send_from_directory
import database
from attendance_engine import AttendanceEngine
from export_excel import export_to_xls

app = Flask(__name__, static_folder='static', static_url_path='')

# Initialize database
database.init_db()

RAW_FILE = 'raw input from biometric.xls'
REF_FILE = 'output.xls'

# Seed database if empty
if not os.path.exists(database.DB_FILE) or len(database.get_available_months()) == 0:
    if os.path.exists(RAW_FILE):
        engine = AttendanceEngine(RAW_FILE, REF_FILE if os.path.exists(REF_FILE) else None)
        database.seed_from_engine(engine, "August -2026")

# Cache reference employee codes for active_only filter
REFERENCE_CODES = set()
if os.path.exists(REF_FILE):
    try:
        import pandas as pd
        df_ref = pd.read_excel(REF_FILE, sheet_name='New', header=None)
        for i in range(len(df_ref)):
            val0 = df_ref.iloc[i, 0]
            if pd.to_numeric(val0, errors='coerce') is not None and pd.notna(pd.to_numeric(val0, errors='coerce')):
                REFERENCE_CODES.add(str(df_ref.iloc[i, 1]).strip())
    except Exception as e:
        print("Error reading reference codes:", e)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/months', methods=['GET'])
def get_months():
    """Return all available months in database."""
    months = database.get_available_months()
    return jsonify({
        'status': 'success',
        'months': months
    })

@app.route('/api/data', methods=['GET'])
def get_data():
    """Return attendance records for a specific month."""
    month_year = request.args.get('month', 'August -2026')
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    records = database.get_month_records(month_year, active_only=active_only, reference_codes=REFERENCE_CODES)

    # Compute high-level stats
    total_staff = len(records)
    needs_review_count = sum(1 for s in records if s['needs_review'])
    total_pay_days = sum(s['total_pay_days'] for s in records)
    total_leaves = sum(s['availed_leaves'] or 0.0 for s in records)
    total_od = sum(s['sv_od'] or 0.0 for s in records)
    vip_count = sum(1 for s in records if s['attendance_policy'] != 'standard')

    departments = sorted(list(set(s['department'] for s in records)))

    return jsonify({
        'status': 'success',
        'month_year': month_year,
        'stats': {
            'total_staff': total_staff,
            'needs_review_count': needs_review_count,
            'total_pay_days': round(total_pay_days, 1),
            'total_leaves': round(total_leaves, 1),
            'total_od': round(total_od, 1),
            'vip_count': vip_count,
            'active_only': active_only
        },
        'departments': departments,
        'employees': records
    })

@app.route('/api/portfolio/<emp_code>', methods=['GET'])
def get_portfolio(emp_code):
    """Option: 360° Employee Dossier & Leave Passbook."""
    pf = database.get_employee_portfolio(emp_code)
    if not pf:
        return jsonify({'status': 'error', 'message': f'Employee {emp_code} not found'}), 404
    return jsonify({
        'status': 'success',
        'portfolio': pf
    })

@app.route('/api/employee/<emp_code>/daily', methods=['GET'])
def get_employee_daily(emp_code):
    """Fetch 31-day punch logs for calendar modal."""
    month_year = request.args.get('month', 'August -2026')
    days = database.get_employee_daily_logs(emp_code, month_year)
    pf = database.get_employee_portfolio(emp_code)
    
    return jsonify({
        'status': 'success',
        'employee': pf,
        'days': days
    })

@app.route('/api/manual-employee', methods=['POST'])
def add_manual_employee():
    """Manually add an employee (Principal, visiting faculty, consultant) with policy."""
    data = request.json or {}
    emp_code = data.get('emp_code')
    name = data.get('name')
    if not emp_code or not name:
        return jsonify({'status': 'error', 'message': 'emp_code and name are required'}), 400

    month_year = data.get('month_year', 'August -2026')
    try:
        portfolio = database.create_or_update_manual_employee(data, current_month=month_year)
        return jsonify({
            'status': 'success',
            'message': f'Staff {name} ({emp_code}) added successfully',
            'portfolio': portfolio
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/set-policy', methods=['POST'])
def set_policy():
    """Update attendance policy (exempt_full, visiting_twice_weekly, standard)."""
    data = request.json or {}
    emp_code = data.get('emp_code')
    policy = data.get('policy')
    month_year = data.get('month_year', 'August -2026')

    if not emp_code or not policy:
        return jsonify({'status': 'error', 'message': 'emp_code and policy required'}), 400

    try:
        database.set_employee_policy(emp_code, policy, month_year)
        pf = database.get_employee_portfolio(emp_code)
        return jsonify({
            'status': 'success',
            'portfolio': pf
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/grant-full-attendance', methods=['POST'])
def grant_full_attendance():
    """1-Click button to grant 31 full pay days to an employee."""
    data = request.json or {}
    emp_code = data.get('emp_code')
    month_year = data.get('month_year', 'August -2026')

    if not emp_code:
        return jsonify({'status': 'error', 'message': 'emp_code required'}), 400

    try:
        database.grant_full_attendance(emp_code, month_year)
        pf = database.get_employee_portfolio(emp_code)
        return jsonify({
            'status': 'success',
            'portfolio': pf
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/update-employee', methods=['POST'])
def update_employee():
    """Option 1: Inline edit for leaves, OD, holiday, or biometric days."""
    data = request.json or {}
    emp_code = data.get('emp_code')
    field = data.get('field')
    value = data.get('value')
    month_year = data.get('month_year', 'August -2026')

    if not emp_code or not field:
        return jsonify({'status': 'error', 'message': 'emp_code and field required'}), 400

    try:
        database.update_monthly_field(emp_code, month_year, field, value)
        pf = database.get_employee_portfolio(emp_code)
        return jsonify({
            'status': 'success',
            'portfolio': pf
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/regularize-day', methods=['POST'])
def regularize_day():
    """Option 2: Day-level regularization from punch calendar modal."""
    data = request.json or {}
    emp_code = data.get('emp_code')
    day_num = data.get('day_num')
    action = data.get('action')
    month_year = data.get('month_year', 'August -2026')

    if not emp_code or not day_num or not action:
        return jsonify({'status': 'error', 'message': 'emp_code, day_num, and action required'}), 400

    try:
        database.regularize_day_in_db(emp_code, month_year, int(day_num), action)
        days = database.get_employee_daily_logs(emp_code, month_year)
        pf = database.get_employee_portfolio(emp_code)
        return jsonify({
            'status': 'success',
            'portfolio': pf,
            'days': days
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/bulk-slips', methods=['POST'])
def bulk_slips():
    """Option 3: Apply multiple leave or OD slips in batch."""
    data = request.json or {}
    text_paste = data.get('text', '')
    month_year = data.get('month_year', 'August -2026')

    applied_count = 0
    if text_paste:
        lines = text_paste.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            ec = parts[0]
            if len(parts) == 3:
                # e.g. 105, 21, CL
                if parts[1].isdigit() and int(parts[1]) <= 31:
                    day_num = int(parts[1])
                    act = 'cl' if 'CL' in parts[2].upper() else ('od' if 'OD' in parts[2].upper() else 'present')
                    database.regularize_day_in_db(ec, month_year, day_num, act)
                    applied_count += 1
                else:
                    # EmpCode, CL_qty, OD_qty
                    try:
                        database.update_monthly_field(ec, month_year, 'availed_leaves', float(parts[1]))
                        database.update_monthly_field(ec, month_year, 'sv_od', float(parts[2]))
                        applied_count += 1
                    except Exception:
                        pass
            elif len(parts) == 2:
                try:
                    val = float(parts[1])
                    database.update_monthly_field(ec, month_year, 'availed_leaves', val)
                    applied_count += 1
                except Exception:
                    pass

    return jsonify({
        'status': 'success',
        'applied_count': applied_count
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload new biometric raw excel file for any designated month."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
    
    f = request.files['file']
    month_name = request.form.get('month_name', 'August -2026')
    
    save_path = os.path.join(tempfile.gettempdir(), f.filename)
    f.save(save_path)

    engine = AttendanceEngine(save_path, REF_FILE if os.path.exists(REF_FILE) else None)
    database.seed_from_engine(engine, month_name)

    return jsonify({
        'status': 'success',
        'message': f'Successfully loaded {f.filename} for {month_name}'
    })

@app.route('/api/export', methods=['GET'])
def export_file():
    """Generate and download finalized output.xls for chosen month."""
    month_year = request.args.get('month', 'August -2026')
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    records = database.get_month_records(month_year, active_only=active_only, reference_codes=REFERENCE_CODES)

    temp_out = os.path.join(tempfile.gettempdir(), f'RVS_Monthly_Salary_{month_year}.xls')
    export_to_xls(records, temp_out, month_year_str=month_year)

    return send_file(temp_out, as_attachment=True, download_name=f'RVS_Monthly_Salary_{month_year}.xls')

if __name__ == '__main__':
    print("Starting RVS Multi-Month Salary Platform on http://localhost:5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
