"""
Bulk Staff Enrollment Service for SVCET Salary Estimation System.
Handles template generation, multi-format Excel/CSV parsing, multi-sheet inspection,
deep header-row scanning, content-based column inference (for headerless sheets),
and batch staff ingestion.
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
        'emp no', 'e code', 'ecode', 'faculty code', 'token', 'token no', 'card no', 'badge no',
        's no', 'sl no', 's.no', 'sr no'
    ],
    'name': [
        'full name', 'name', 'employee name', 'staff name', 'faculty name',
        'emp name', 'member name', 'candidate name', 'name of the staff',
        'name of staff', 'name of the employee', 'name of employee',
        'staff', 'employee', 'faculty', 'teacher', 'person'
    ],
    'designation': [
        'designation', 'desig', 'role', 'position', 'title', 'post', 'cadre',
        'occupation', 'job title', 'job', 'work', 'working as'
    ],
    'department': [
        'department', 'dept', 'branch', 'stream', 'division', 'dept name',
        'department name', 'section', 'discipline'
    ],
    'category': [
        'staff category', 'category', 'cat', 'staff type', 'type', 'faculty type',
        'teaching / non teaching', 'teaching/non teaching', 'cadre category', 'classification'
    ],
    'base_salary': [
        'monthly base package', 'base package', 'base salary', 'monthly salary',
        'package', 'salary', 'gross salary', 'rate', 'basic pay', 'basic',
        'monthly package', 'base pay', 'fixed pay', 'total salary', 'gross',
        'pay', 'amount', 'remuneration', 'stipend', 'wages'
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
        'days', 'duty days', 'monthly days', 'pay days'
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

# Known college designation words for content inference
DESIGNATION_KEYWORDS = {
    'prof', 'professor', 'lecturer', 'assistant', 'associate', 'hod', 'dean',
    'technician', 'driver', 'guard', 'watchman', 'attender', 'peon', 'clerk',
    'principal', 'director', 'officer', 'mechanic', 'helper', 'sweeper',
    'electrician', 'plumber', 'carpenter', 'operator', 'instructor', 'programmer',
    'librarian', 'superintendent', 'accountant', 'cashier', 'receptionist',
    'security', 'faculty', 'pa to'
}

# Known college departments for content inference
DEPARTMENT_KEYWORDS = {
    'cse', 'ece', 'mech', 'civil', 'ce', 'eee', 'it', 'mba', 'mca', 'aiml',
    'admin', 'administration', 'transport', 'security', 'exam', 'examination',
    'library', 'placement', 'general', 'maths', 'mathematics', 'physics',
    'chemistry', 'english', 'humanities', 'h&s', 'management', 'accounts', 'stores'
}

def normalize_header(header_str: str) -> str:
    """Normalize string for fuzzy header matching."""
    if not header_str:
        return ""
    clean = str(header_str).lower().strip()
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'[\(\)\[\]\{\}\_\-\.\:\/]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def map_column_name(header_str: str) -> str:
    """Map arbitrary header string to canonical field name."""
    norm = normalize_header(header_str)
    if not norm:
        return ""

    for field, synonyms in COLUMN_MAPPINGS.items():
        if norm in synonyms:
            return field
        for syn in synonyms:
            if syn == norm or f" {syn} " in f" {norm} ":
                return field
            # Partial token match for compound headers like "total salary ()"
            if len(syn) >= 4 and syn in norm:
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

def normalize_category_value(val: str, desig: str = "", dept: str = "") -> str:
    """Determine staff category cleanly from category text, designation, or department."""
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

    # Check designation
    desig_lower = str(desig or '').lower()
    if any(k in desig_lower for k in ['prof', 'hod', 'dean', 'lecturer', 'faculty', 'assoc', 'asst', 'teacher', 'instructor']):
        return 'Teaching'
    if any(k in desig_lower for k in ['driver', 'cleaner', 'bus', 'transport']):
        return 'Transport'
    if any(k in desig_lower for k in ['guard', 'watchman', 'security', 'waterman']):
        return 'Security'
    if any(k in desig_lower for k in ['attender', 'peon', 'helper', 'sweeper', 'scavenger', 'ayyah']):
        return 'Attender'
    if any(k in desig_lower for k in ['principal', 'director', 'chairman', 'manager', 'ao', 'registrar', 'p a to']):
        return 'Management'

    # Check department
    dept_lower = str(dept or '').lower()
    if any(k in dept_lower for k in ['cse', 'ece', 'mech', 'civil', 'eee', 'it', 'mba', 'mca', 'aiml', 'humanities', 'physics', 'maths']):
        return 'Teaching'
    if 'transport' in dept_lower:
        return 'Transport'
    if 'security' in dept_lower:
        return 'Security'

    return 'Non-Teaching'

def generate_staff_excel_template() -> io.BytesIO:
    """
    Generate an elegant Excel template with pre-styled headers,
    column explanations, sample rows, and dropdown data hints.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Staff Enrollment Template"

    navy_header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    sample_font = Font(name="Calibri", size=10, color="1E293B")
    
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

    for col_idx, (header_text, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header_text)
        cell.fill = navy_header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 28

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
        ("Employee Code *", "Unique employee identifier (e.g. 101, V-102, NT-301)."),
        ("Full Name *", "Official employee name with title/initials (e.g. Dr. M. Mohan Babu)."),
        ("Designation", "Job title (Professor, Assistant Professor, Lab Technician, Driver, etc.)."),
        ("Department", "Department name (CSE, ECE, MECH, CE, MBA, Administration, Transport, etc.)."),
        ("Staff Category", "Options: Teaching, Non-Teaching, Transport, Security, Attender, Management."),
        ("Monthly Base Package", "Gross monthly package in Rupees (e.g. 25000, 45000)."),
        ("Attendance Policy", "Options: 'Standard Biometric', 'Full Attendance (VIP / Exempt)', or 'Visiting Faculty'."),
        ("Annual CL Quota", "Annual Casual Leave allotment (Default: 12 days)."),
        ("Base Working Days", "Standard monthly duty days (Default: 25 days)."),
        ("Bank Name", "Salary disbursement bank name (Default: PNB)."),
        ("Account Number", "Employee bank account number."),
        ("IFSC Code", "Bank branch IFSC code.")
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

def find_header_row_in_sheet(df_raw: pd.DataFrame) -> tuple[int, dict, list]:
    """
    Scan the first 25 rows of df_raw to identify the actual header row.
    Returns (header_row_index, column_map, detected_fields).
    If no header row is detected, returns (-1, {}, []).
    """
    max_scan = min(25, len(df_raw))
    best_row = -1
    best_score = 0
    best_map = {}
    best_fields = []

    for r_idx in range(max_scan):
        row = df_raw.iloc[r_idx]
        current_map = {}
        current_fields = []
        score = 0

        for col_idx, cell_val in enumerate(row):
            if pd.isna(cell_val):
                continue
            text = str(cell_val).strip()
            if not text:
                continue

            mapped = map_column_name(text)
            if mapped in COLUMN_MAPPINGS:
                current_map[col_idx] = mapped
                if mapped not in current_fields:
                    current_fields.append(mapped)
                    # Score weights
                    if mapped == 'name':
                        score += 5
                    elif mapped == 'emp_code':
                        score += 4
                    elif mapped in ['designation', 'department']:
                        score += 3
                    elif mapped in ['base_salary', 'category']:
                        score += 2
                    else:
                        score += 1

        if score > best_score:
            best_score = score
            best_row = r_idx
            best_map = current_map
            best_fields = current_fields

    # Threshold for a confident header row: score >= 3 or both (emp_code/s.no and name/desig)
    if best_score >= 3:
        return best_row, best_map, best_fields
    return -1, {}, []

def infer_columns_from_content(df_raw: pd.DataFrame) -> tuple[dict, list]:
    """
    Content-Based Column Classifier for files with NO headers or non-standard headers.
    Inspects sample cell values across rows to deduce which column represents which field.
    """
    col_map = {}
    detected_fields = []
    num_cols = df_raw.shape[1]
    
    # Gather non-empty sample rows (up to 30 rows)
    sample_rows = []
    for _, row in df_raw.head(35).iterrows():
        non_empty = [x for x in row if pd.notna(x) and str(x).strip()]
        if len(non_empty) >= 2:
            sample_rows.append(row)
    
    if not sample_rows:
        return {}, []

    col_scores = {col_idx: {
        'name': 0, 'emp_code': 0, 'designation': 0,
        'department': 0, 'base_salary': 0, 'category': 0
    } for col_idx in range(num_cols)}

    for row in sample_rows:
        for col_idx in range(num_cols):
            val = row[col_idx]
            if pd.isna(val):
                continue
            s = str(val).strip()
            if not s or s.lower() == 'nan':
                continue

            # 1. Check for Base Salary (Numeric in reasonable range)
            cleaned_num = re.sub(r'[^\d\.]', '', s)
            if cleaned_num:
                try:
                    num_val = float(cleaned_num)
                    if 2000 <= num_val <= 500000:
                        col_scores[col_idx]['base_salary'] += 3
                except Exception:
                    pass

            s_lower = s.lower()

            # 2. Check for Designation / Occupation keywords
            if any(k in s_lower for k in DESIGNATION_KEYWORDS):
                col_scores[col_idx]['designation'] += 5
                col_scores[col_idx]['emp_code'] -= 5

            # 3. Check for Department keywords
            clean_dept_word = re.sub(r'[^a-zA-Z\&]', '', s_lower)
            if clean_dept_word in DEPARTMENT_KEYWORDS or any(d in s_lower for d in ['administration', 'transport', 'security', 'engineering']):
                col_scores[col_idx]['department'] += 8
                col_scores[col_idx]['emp_code'] -= 10

            # 4. Check for Category
            if any(c in s_lower for c in ['teaching', 'non-teaching', 'non teaching', 'attender', 'transport', 'management']):
                col_scores[col_idx]['category'] += 6

            # 5. Check for Emp Code (Short alphanumeric token like 101, T-201, 1048)
            if re.match(r'^[a-zA-Z0-9\-\_]{1,10}$', s) and not any(k in s_lower for k in DESIGNATION_KEYWORDS) and clean_dept_word not in DEPARTMENT_KEYWORDS:
                if s.isdigit():
                    int_val = int(s)
                    if 1 <= int_val < 99999:
                        col_scores[col_idx]['emp_code'] += 5
                else:
                    col_scores[col_idx]['emp_code'] += 4

            # 6. Check for Name (Alphabetic with spaces, initials, titles, 2-5 words)
            words = s.split()
            has_letters = bool(re.search(r'[a-zA-Z]', s))
            not_keyword = not (any(k in s_lower for k in DESIGNATION_KEYWORDS) or clean_dept_word in DEPARTMENT_KEYWORDS)
            if has_letters and not_keyword:
                if any(t in s_lower for t in ['dr', 'mr', 'mrs', 'prof', 'kumari', 'shri', 'smt']):
                    col_scores[col_idx]['name'] += 8
                elif 1 <= len(words) <= 5 and len(s) >= 4:
                    col_scores[col_idx]['name'] += 4

    # Assign best column for each role greedily by highest score
    assigned_cols = set()
    role_priority = ['department', 'name', 'emp_code', 'designation', 'base_salary', 'category']

    for role in role_priority:
        best_col = None
        best_val = 0
        for col_idx in range(num_cols):
            if col_idx in assigned_cols:
                continue
            sc = col_scores[col_idx][role]
            if sc > best_val:
                best_val = sc
                best_col = col_idx

        threshold = 2 if role in ['name', 'emp_code', 'department'] else 1
        if best_col is not None and best_val >= threshold:
            col_map[best_col] = role
            detected_fields.append(role)
            assigned_cols.add(best_col)

    return col_map, detected_fields

def is_summary_or_banner_row(row_dict: dict) -> bool:
    """Detect and skip header banners or summary rows like 'Grand Total'."""
    text_corpus = " ".join([str(v) for v in row_dict.values() if v is not None]).lower()
    if any(k in text_corpus for k in ['grand total', 'sub total', 'total staff', 'page total', 'bank disbursement', 'cash denominations']):
        return True
    name = str(row_dict.get('name', '')).strip().lower()
    code = str(row_dict.get('emp_code', '')).strip().lower()
    if name in ['total', 'grand total', 'sub total', 's.no', 'emp code', 'name']:
        return True
    if code in ['total', 'grand total']:
        return True
    return False

def parse_and_validate_bulk_staff(file_stream, filename: str) -> dict:
    """
    Parse uploaded Excel or CSV file.
    Works seamlessly whether the file has:
    - Headers on Row 0, Row 3, Row 5, etc.
    - Multiple sheets (e.g. Teaching Faculty, Non-Teaching, Support)
    - Zero headers (content-based column inference)
    - Missing columns (auto-generates code, infers department/category)
    """
    fn_lower = filename.lower()
    sheets_data = {}

    try:
        if fn_lower.endswith('.csv'):
            try:
                df = pd.read_csv(file_stream, header=None)
            except Exception:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, encoding='latin1', header=None)
            sheets_data['CSV_Data'] = df
        elif fn_lower.endswith(('.xlsx', '.xls')):
            xl = pd.ExcelFile(file_stream)
            # Find best sheet(s)
            audit_sheets = [s for s in xl.sheet_names if any(k in s.lower() for k in ['all staff', 'audit', 'master', 'complete staff'])]
            if audit_sheets:
                # Prioritize comprehensive master sheet
                for s in audit_sheets:
                    sheets_data[s] = pd.read_excel(file_stream, sheet_name=s, header=None)
            else:
                # Read all sheets except summary/bank sheets
                for s in xl.sheet_names:
                    s_lower = s.lower()
                    if any(ign in s_lower for ign in ['executive summary', 'cash denomination', 'denomination', 'summary']):
                        continue
                    sheets_data[s] = pd.read_excel(file_stream, sheet_name=s, header=None)
        else:
            return {'status': 'error', 'message': f'Unsupported file format: {filename}. Please upload .xlsx, .xls, or .csv'}
    except Exception as e:
        return {'status': 'error', 'message': f'Failed to open file: {str(e)}'}

    if not sheets_data:
        return {'status': 'error', 'message': 'No readable data sheets found in uploaded file.'}

    all_parsed_rows = []
    overall_dept_counts = {}
    overall_cat_counts = {}
    overall_detected_fields = set()
    provisional_code_counter = 1

    for sheet_name, df_sheet in sheets_data.items():
        if df_sheet is None or df_sheet.empty:
            continue

        # Drop entirely empty rows and columns
        df_sheet = df_sheet.dropna(how='all').dropna(axis=1, how='all')
        if df_sheet.empty:
            continue

        # Reset column indices to 0..N
        df_sheet.columns = range(df_sheet.shape[1])

        # Step 1: Search for header row
        h_idx, col_map, detected_cols = find_header_row_in_sheet(df_sheet)

        if h_idx != -1:
            data_df = df_sheet.iloc[h_idx + 1:].copy()
        else:
            # Step 2: Content-based inference for headerless sheets
            col_map, detected_cols = infer_columns_from_content(df_sheet)
            data_df = df_sheet.copy()

        for f in detected_cols:
            overall_detected_fields.add(f)

        # Track contextual department banner (e.g. "DEPARTMENT : CSE")
        current_section_dept = ""
        # If sheet name is a specific staff category or dept
        sheet_dept_hint = ""
        for d in DEPARTMENT_KEYWORDS:
            if d in sheet_name.lower():
                sheet_dept_hint = d.upper()
                break

        for _, row in data_df.iterrows():
            # Check for section header row like "DEPARTMENT : CSE"
            row_str = " ".join([str(x) for x in row if pd.notna(x)])
            dept_match = re.search(r'department\s*[\:\-]\s*([a-zA-Z\s\&]+)', row_str, re.IGNORECASE)
            if dept_match:
                current_section_dept = dept_match.group(1).strip()
                continue

            # Build row dict from mapped columns
            row_dict = {}
            for col_idx, field in col_map.items():
                if col_idx < len(row):
                    row_dict[field] = row[col_idx]

            # If row is mostly empty, skip
            non_empty_vals = [v for v in row_dict.values() if pd.notna(v) and str(v).strip()]
            if len(non_empty_vals) < 1:
                continue

            if is_summary_or_banner_row(row_dict):
                continue

            # --- EMPLOYEE CODE ---
            raw_code = row_dict.get('emp_code', '')
            if pd.isna(raw_code) or raw_code is None:
                emp_code = ''
            elif isinstance(raw_code, float) and raw_code.is_integer():
                emp_code = str(int(raw_code)).strip()
            else:
                emp_code = str(raw_code).strip()

            # --- FULL NAME ---
            raw_name = row_dict.get('name', '')
            name = '' if (pd.isna(raw_name) or raw_name is None) else str(raw_name).strip()

            # If name is blank but we have a text value somewhere in row, try to extract name
            if not name:
                for v in row:
                    if pd.notna(v):
                        s_val = str(v).strip()
                        if len(s_val) >= 3 and not s_val.isdigit() and s_val != emp_code:
                            name = s_val
                            break

            # If still no name and no code, skip
            if not name and not emp_code:
                continue

            # If name looks like a code (e.g. "101") and code is empty
            if name.isdigit() and not emp_code:
                emp_code = name
                name = f"Staff Member ({emp_code})"

            # If code is missing, auto-generate provisional code so it NEVER blocks user!
            if not emp_code:
                emp_code = f"EMP-{provisional_code_counter:03d}"
                provisional_code_counter += 1

            # If name is missing, use Employee Code
            if not name:
                name = f"Staff ({emp_code})"

            # --- DESIGNATION ---
            raw_desig = row_dict.get('designation', '')
            desig = '' if pd.isna(raw_desig) else str(raw_desig).strip()
            if not desig or desig.lower() == 'nan':
                desig = 'Staff'

            # --- DEPARTMENT ---
            raw_dept = row_dict.get('department', '')
            raw_dept_str = '' if pd.isna(raw_dept) else str(raw_dept).strip()
            if not raw_dept_str or raw_dept_str.lower() in ['nan', 'general', 'staff']:
                # Inherit from section banner, sheet hint, or designation
                if current_section_dept:
                    raw_dept_str = current_section_dept
                elif sheet_dept_hint:
                    raw_dept_str = sheet_dept_hint
                elif any(k in desig.lower() for k in ['driver', 'bus']):
                    raw_dept_str = 'Transport'
                elif any(k in desig.lower() for k in ['guard', 'watchman']):
                    raw_dept_str = 'Security'
                else:
                    raw_dept_str = 'Administration'

            dept = database.normalize_dept(raw_dept_str)

            # --- CATEGORY ---
            raw_cat = row_dict.get('category', '')
            cat_str = '' if pd.isna(raw_cat) else str(raw_cat).strip()
            category = normalize_category_value(cat_str, desig=desig, dept=dept)

            # --- BASE SALARY ---
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

            # --- POLICY ---
            raw_pol = row_dict.get('attendance_policy', '')
            policy = normalize_policy_value('' if pd.isna(raw_pol) else str(raw_pol))

            # --- CL QUOTA ---
            raw_cl = row_dict.get('annual_cl_quota', 12.0)
            try:
                cl_quota = float(raw_cl) if not pd.isna(raw_cl) else 12.0
            except Exception:
                cl_quota = 12.0

            # --- WORKING DAYS ---
            raw_days = row_dict.get('biometric_days', 25.0)
            try:
                biometric_days = float(raw_days) if not pd.isna(raw_days) else (8.0 if policy == 'visiting_twice_weekly' else 25.0)
            except Exception:
                biometric_days = 25.0

            # --- BANK DETAILS ---
            raw_bank = row_dict.get('bank_name', 'PNB')
            bank_name = 'PNB' if (pd.isna(raw_bank) or not raw_bank) else str(raw_bank).strip()

            raw_acc = row_dict.get('account_no', '')
            account_no = '' if pd.isna(raw_acc) else str(raw_acc).strip()

            raw_ifsc = row_dict.get('ifsc_code', '')
            ifsc_code = '' if pd.isna(raw_ifsc) else str(raw_ifsc).strip()

            # Record is valid
            is_valid = bool(emp_code and name)

            overall_dept_counts[dept] = overall_dept_counts.get(dept, 0) + 1
            overall_cat_counts[category] = overall_cat_counts.get(category, 0) + 1

            all_parsed_rows.append({
                'row_num': len(all_parsed_rows) + 1,
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
                'error': '' if is_valid else 'Missing information'
            })

    if not all_parsed_rows:
        return {
            'status': 'error',
            'message': 'No staff records could be extracted from this file. Please verify the file contains staff data.'
        }

    valid_count = sum(1 for r in all_parsed_rows if r['is_valid'])
    invalid_count = len(all_parsed_rows) - valid_count

    # Always ensure core columns are listed as detected
    for core_field in ['emp_code', 'name', 'department', 'designation', 'category']:
        overall_detected_fields.add(core_field)

    return {
        'status': 'success',
        'total_rows': len(all_parsed_rows),
        'valid_rows': valid_count,
        'invalid_rows': invalid_count,
        'departments': overall_dept_counts,
        'categories': overall_cat_counts,
        'detected_columns': list(overall_detected_fields),
        'rows': all_parsed_rows
    }
