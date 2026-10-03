"""
Bulk Staff Enrollment Service for SVCET Salary Estimation System.
Handles template generation, Excel/CSV parsing, column normalization,
department-wise breakdown analysis, and batch staff ingestion.
"""

import io
import re
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import database

# Synonyms for intelligent column mapping
COLUMN_MAPPINGS = {
    'emp_code': [
        'emp code', 'employee code', 'emp_code', 'emp id', 'empid', 'code',
        'id', 'staff id', 'employee id', 'staff code', 'id no', 'id number',
        'sl no', 's.no'
    ],
    'name': [
        'full name', 'name', 'employee name', 'staff name', 'faculty name',
        'emp name', 'member name', 'candidate name'
    ],
    'designation': [
        'designation', 'desig', 'role', 'position', 'title', 'post', 'cadre'
    ],
    'department': [
        'department', 'dept', 'branch', 'stream', 'division', 'dept name', 'department name'
    ],
    'category': [
        'staff category', 'category', 'cat', 'staff type', 'type', 'faculty type',
        'teaching / non teaching', 'teaching/non teaching'
    ],
    'base_salary': [
        'monthly base package', 'base package', 'base salary', 'monthly salary',
        'package', 'salary', 'gross salary', 'rate', 'basic pay', 'basic',
        'monthly package', 'base pay', 'fixed pay'
    ],
    'attendance_policy': [
        'attendance policy', 'policy', 'attendance type', 'biometric policy',
        'attendance rule', 'status'
    ],
    'annual_cl_quota': [
        'annual cl quota', 'cl quota', 'annual cl', 'cl', 'leaves quota',
        'annual leaves', 'casual leaves'
    ],
    'biometric_days': [
        'base working days', 'working days', 'biometric days', 'base days',
        'days', 'duty days', 'monthly days'
    ],
    'bank_name': [
        'bank name', 'bank', 'banker'
    ],
    'account_no': [
        'account number', 'account no', 'ac no', 'acc no', 'bank ac', 'a/c no', 'account'
    ],
    'ifsc_code': [
        'ifsc code', 'ifsc', 'ifsc no', 'branch ifsc'
    ]
}

def normalize_header(header_str: str) -> str:
    """Normalize column header for fuzzy matching."""
    if not header_str:
        return ""
    clean = str(header_str).lower().strip()
    clean = re.sub(r'[\(\)\[\]\{\}\_\-\.\:\/]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def map_column_name(header_str: str) -> str:
    """Map arbitrary header string to canonical field name."""
    norm = normalize_header(header_str)
    
    # Exact / substring checks against dictionary
    for field, synonyms in COLUMN_MAPPINGS.items():
        if norm in synonyms:
            return field
        for syn in synonyms:
            if syn in norm or norm in syn:
                return field
    return norm

def normalize_policy_value(val: str) -> str:
    """Map user policy input to canonical database keys."""
    if not val:
        return 'standard'
    val_str = str(val).lower().strip()
    if any(k in val_str for k in ['exempt', 'full', 'vip', 'principal', '100%']):
        return 'exempt_full'
    if any(k in val_str for k in ['visit', 'twice', 'lecture', 'week']):
        return 'visiting_twice_weekly'
    return 'standard'

def normalize_category_value(val: str, desig: str = "") -> str:
    """Determine staff category cleanly."""
    if val:
        val_str = str(val).lower().strip()
        if 'teach' in val_str and 'non' not in val_str:
            return 'Teaching'
        if 'non' in val_str:
            return 'Non-Teaching'
        if 'trans' in val_str or 'driver' in val_str:
            return 'Transport'
        if 'sec' in val_str or 'water' in val_str:
            return 'Security'
        if 'attend' in val_str or 'peon' in val_str:
            return 'Attender'
        if 'manage' in val_str or 'admin' in val_str or 'direct' in val_str:
            return 'Management'
    
    # Fallback based on designation
    desig_lower = str(desig).lower()
    if any(k in desig_lower for k in ['prof', 'hod', 'dean', 'lecturer', 'faculty', 'assoc', 'asst']):
        return 'Teaching'
    if any(k in desig_lower for k in ['driver', 'cleaner', 'bus']):
        return 'Transport'
    if any(k in desig_lower for k in ['guard', 'watchman', 'security']):
        return 'Security'
    if any(k in desig_lower for k in ['attender', 'peon', 'helper', 'sweeper', 'scavenger']):
        return 'Attender'
    if any(k in desig_lower for k in ['principal', 'director', 'chairman', 'manager', 'ao', 'registrar']):
        return 'Management'
        
    return 'Non-Teaching'

def generate_staff_excel_template() -> io.BytesIO:
    """
    Generate an elegant, audit-grade Excel template with pre-styled headers,
    column explanations, sample rows, and dropdown data hints.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Staff Enrollment Template"

    # Color Palette: SVCET Navy & Slate
    navy_header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    sample_font = Font(name="Calibri", size=10, color="1E293B")
    hint_font = Font(name="Calibri", size=9, italic=True, color="64748B")
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = [
        ("Employee Code *", 18),
        ("Full Name *", 26),
        ("Designation", 22),
        ("Department", 18),
        ("Staff Category", 18),
        ("Monthly Base Package (₹)", 24),
        ("Attendance Policy", 25),
        ("Annual CL Quota", 16),
        ("Base Working Days", 18),
        ("Bank Name", 14),
        ("Account Number", 20),
        ("IFSC Code", 16)
    ]

    # Write Headers
    for col_idx, (header_text, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header_text)
        cell.fill = navy_header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 28

    # Realistic demo sample rows
    sample_data = [
        ("101", "Dr. M. Mohan Babu", "Principal & Director", "Administration", "Management", 125000, "Full Attendance (VIP / Exempt)", 15, 25, "PNB", "9876543210123", "PUNB0123400"),
        ("T-201", "Dr. R. Rajesh Kumar", "Professor & HOD", "CSE", "Teaching", 85000, "Standard Biometric", 12, 25, "PNB", "9876543210456", "PUNB0123400"),
        ("T-202", "P. Anitha", "Assistant Professor", "ECE", "Teaching", 45000, "Standard Biometric", 12, 25, "PNB", "9876543210789", "PUNB0123400"),
        ("NT-301", "S. Suresh", "Lab Technician", "ECE", "Non-Teaching", 22000, "Standard Biometric", 12, 25, "PNB", "9876543210999", "PUNB0123400"),
        ("TR-401", "K. Venkatesh", "Bus Driver", "Transport", "Transport", 20000, "Standard Biometric", 12, 25, "PNB", "9876543210888", "PUNB0123400"),
        ("V-501", "Dr. K. Srinivas", "Visiting Professor", "MECH", "Teaching", 40000, "Visiting Faculty (2 Days/Week)", 12, 8, "SBI", "1122334455667", "SBIN0001234")
    ]

    for row_idx, row_values in enumerate(sample_data, 2):
        ws.row_dimensions[row_idx].height = 20
        # Light zebra row fill
        row_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid") if row_idx % 2 == 0 else PatternFill(fill_type=None)
        
        for col_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = sample_font
            cell.border = thin_border
            if row_fill.fill_type:
                cell.fill = row_fill
            if col_idx in [1, 7, 8, 9, 10, 12]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [6]:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = '#,##0'
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Add instructions / notes sheet
    guide_ws = wb.create_sheet(title="Column Guidelines")
    guide_ws.column_dimensions['A'].width = 24
    guide_ws.column_dimensions['B'].width = 65

    guide_headers = ["Field Name", "Accepted Values / Explanation"]
    for c_idx, h_text in enumerate(guide_headers, 1):
        c = guide_ws.cell(row=1, column=c_idx, value=h_text)
        c.fill = navy_header_fill
        c.font = header_font
        c.border = thin_border

    guidelines = [
        ("Employee Code *", "Unique employee identifier (e.g. 101, V-102, NT-301). Mandatory field."),
        ("Full Name *", "Official employee name with title/initials (e.g. Dr. M. Mohan Babu). Mandatory."),
        ("Designation", "Job title (Professor, Assistant Professor, Lab Technician, Driver, etc.)."),
        ("Department", "Department name (CSE, ECE, MECH, CE, MBA, Administration, Transport, etc.)."),
        ("Staff Category", "Options: Teaching, Non-Teaching, Transport, Security, Attender, Management."),
        ("Monthly Base Package", "Gross monthly package in Rupees (e.g. 25000, 45000). Numbers only."),
        ("Attendance Policy", "Options: 'Standard Biometric', 'Full Attendance (VIP / Exempt)', or 'Visiting Faculty'."),
        ("Annual CL Quota", "Annual Casual Leave allotment (Default: 12 days)."),
        ("Base Working Days", "Standard monthly duty days (Default: 25 days for regular, 8 for visiting)."),
        ("Bank Name", "Salary disbursement bank name (Default: PNB)."),
        ("Account Number", "Employee bank account number for electronic transfer."),
        ("IFSC Code", "Bank branch IFSC code (e.g. PUNB0123400).")
    ]

    for r_idx, (field, note) in enumerate(guidelines, 2):
        guide_ws.row_dimensions[r_idx].height = 22
        c1 = guide_ws.cell(row=r_idx, column=1, value=field)
        c2 = guide_ws.cell(row=r_idx, column=2, value=note)
        c1.font = Font(name="Calibri", size=10, bold=True, color="1E3A8A")
        c2.font = sample_font
        c1.border = thin_border
        c2.border = thin_border

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

def parse_and_validate_bulk_staff(file_stream, filename: str) -> dict:
    """
    Parse uploaded Excel or CSV file, detect columns flexibly,
    validate every row, and generate summary statistics.
    """
    fn_lower = filename.lower()
    df = None
    try:
        if fn_lower.endswith('.csv'):
            try:
                df = pd.read_csv(file_stream)
            except Exception:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, encoding='latin1')
        elif fn_lower.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_stream)
        else:
            return {'status': 'error', 'message': f'Unsupported file format: {filename}. Please upload .xlsx, .xls, or .csv'}
    except Exception as e:
        return {'status': 'error', 'message': f'Failed to parse file: {str(e)}'}

    if df is None or df.empty:
        return {'status': 'error', 'message': 'The uploaded file is empty.'}

    # Clean DataFrame: drop entirely empty rows
    df = df.dropna(how='all')
    if df.empty:
        return {'status': 'error', 'message': 'No data found in the uploaded file.'}

    # Map columns
    column_map = {}
    detected_fields = []
    for col in df.columns:
        canonical = map_column_name(str(col))
        if canonical in COLUMN_MAPPINGS:
            column_map[col] = canonical
            if canonical not in detected_fields:
                detected_fields.append(canonical)

    if 'emp_code' not in detected_fields and 'name' not in detected_fields:
        return {
            'status': 'error',
            'message': 'Could not detect Employee Code or Name columns. Please ensure your file has headers like "Employee Code" and "Full Name". Download the sample template for exact format.'
        }

    parsed_rows = []
    dept_counts = {}
    cat_counts = {}
    valid_count = 0
    invalid_count = 0

    for idx, row in df.iterrows():
        row_dict = {}
        for col, val in row.items():
            field = column_map.get(col)
            if field:
                row_dict[field] = val

        # Clean values
        raw_code = row_dict.get('emp_code', '')
        if pd.isna(raw_code) or raw_code is None:
            emp_code = ''
        elif isinstance(raw_code, float) and raw_code.is_integer():
            emp_code = str(int(raw_code)).strip()
        else:
            emp_code = str(raw_code).strip()

        raw_name = row_dict.get('name', '')
        name = '' if (pd.isna(raw_name) or raw_name is None) else str(raw_name).strip()

        raw_desig = row_dict.get('designation', '')
        desig = 'Staff' if (pd.isna(raw_desig) or not raw_desig) else str(raw_desig).strip()

        raw_dept = row_dict.get('department', '')
        raw_dept_str = 'Administration' if (pd.isna(raw_dept) or not raw_dept) else str(raw_dept).strip()
        dept = database.normalize_dept(raw_dept_str)

        raw_cat = row_dict.get('category', '')
        category = normalize_category_value('' if pd.isna(raw_cat) else str(raw_cat), desig)

        # Base salary
        raw_sal = row_dict.get('base_salary', 0)
        try:
            if pd.isna(raw_sal):
                base_sal = 0.0
            elif isinstance(raw_sal, (int, float)):
                base_sal = float(raw_sal)
            else:
                cleaned_sal = re.sub(r'[^\d\.]', '', str(raw_sal))
                base_sal = float(cleaned_sal) if cleaned_sal else 0.0
        except Exception:
            base_sal = 0.0

        # Policy
        raw_pol = row_dict.get('attendance_policy', '')
        policy = normalize_policy_value('' if pd.isna(raw_pol) else str(raw_pol))

        # CL Quota
        raw_cl = row_dict.get('annual_cl_quota', 12.0)
        try:
            cl_quota = float(raw_cl) if not pd.isna(raw_cl) else 12.0
        except Exception:
            cl_quota = 12.0

        # Working days
        raw_days = row_dict.get('biometric_days', 25.0)
        try:
            biometric_days = float(raw_days) if not pd.isna(raw_days) else (8.0 if policy == 'visiting_twice_weekly' else 25.0)
        except Exception:
            biometric_days = 25.0

        # Bank details
        raw_bank = row_dict.get('bank_name', 'PNB')
        bank_name = 'PNB' if (pd.isna(raw_bank) or not raw_bank) else str(raw_bank).strip()

        raw_acc = row_dict.get('account_no', '')
        account_no = '' if pd.isna(raw_acc) else str(raw_acc).strip()

        raw_ifsc = row_dict.get('ifsc_code', '')
        ifsc_code = '' if pd.isna(raw_ifsc) else str(raw_ifsc).strip()

        # Validation
        is_valid = bool(emp_code and name)
        error_msg = ""
        if not emp_code and not name:
            error_msg = "Missing Employee Code and Full Name"
        elif not emp_code:
            error_msg = "Missing Employee Code"
        elif not name:
            error_msg = "Missing Full Name"

        if is_valid:
            valid_count += 1
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
            cat_counts[category] = cat_counts.get(category, 0) + 1
        else:
            invalid_count += 1

        parsed_rows.append({
            'row_num': idx + 1,
            'emp_code': emp_code,
            'name': name,
            'designation': desig,
            'department': dept,
            'category': category,
            'base_salary': base_sal,
            'attendance_policy': policy,
            'annual_cl_quota': cl_quota,
            'biometric_days': biometric_days,
            'bank_name': bank_name,
            'account_no': account_no,
            'ifsc_code': ifsc_code,
            'is_valid': is_valid,
            'error': error_msg
        })

    return {
        'status': 'success',
        'total_rows': len(parsed_rows),
        'valid_rows': valid_count,
        'invalid_rows': invalid_count,
        'departments': dept_counts,
        'categories': cat_counts,
        'detected_columns': detected_fields,
        'rows': parsed_rows
    }
