import re
import os
import pandas as pd
from typing import Dict, List, Any, Optional

# Standard Department Order matching RVS output.xls
STANDARD_DEPARTMENT_ORDER = [
    'General', 'CE', 'EEE', 'ME', 'ECE', 'CSE', 'CSM', 'CSD', 'CAI', 'IT', 'MCA', 'MBA',
    'HAS', 'PD', 'Administration', 'Accounts', 'Media', 'Exam Section', 'Library',
    'Maintenance', 'TAP', 'Electriations', 'SLH', 'Admissions', 'Management Staff',
    'Transport', 'Attender', 'Garden Staff', 'Security & Water Staff'
]

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

# Standard holidays by department
LOW_HOLIDAY_DEPTS = {'garden staff', 'security & water staff', 'security', 'slh'}

class AttendanceEngine:
    def __init__(self, raw_filepath: str, output_filepath: Optional[str] = None):
        self.raw_filepath = raw_filepath
        self.output_filepath = output_filepath
        self.employees: Dict[str, Dict[str, Any]] = {}
        self.department_order: List[str] = list(STANDARD_DEPARTMENT_ORDER)
        self.reference_metadata: Dict[str, Dict[str, str]] = {}
        
        # Load reference metadata (Designations, standard Depts) if output.xls exists
        if output_filepath and os.path.exists(output_filepath):
            self._load_reference_metadata(output_filepath)
            
        self.load_raw_biometric(raw_filepath)

    def _load_reference_metadata(self, filepath: str):
        """Extract designations and department order from reference output.xls if available."""
        try:
            with pd.ExcelFile(filepath) as xl:
                target_sheet = 'New' if 'New' in xl.sheet_names else xl.sheet_names[0]
                df = xl.parse(target_sheet, header=None)
            curr_dept = 'General'
            depts_found = []
            for i in range(len(df)):
                r = df.iloc[i]
                val1 = str(r[1]) if pd.notna(r[1]) else ''
                val2 = str(r[2]) if pd.notna(r[2]) else ''
                if 'Department:' in val1:
                    curr_dept = normalize_dept(val2.strip())
                    if curr_dept not in depts_found:
                        depts_found.append(curr_dept)
                elif pd.to_numeric(r[0], errors='coerce') is not None and pd.notna(pd.to_numeric(r[0], errors='coerce')):
                    raw_ec = str(r[1]).strip() if pd.notna(r[1]) else ''
                    name = str(r[2]).strip() if pd.notna(r[2]) else ''
                    desig = str(r[3]).strip() if pd.notna(r[3]) else ''
                    
                    if not raw_ec or raw_ec.lower() == 'nan':
                        if 'shajahan' in name.lower():
                            raw_ec = 'SHAJAHAN'
                        elif 'shiva' in name.lower() or 'siva' in name.lower():
                            raw_ec = 'SHIVA_DRIVER'
                        else:
                            raw_ec = f"REF_{int(r[0])}"

                    self.reference_metadata[raw_ec] = {
                        'name': name,
                        'designation': desig,
                        'dept': curr_dept
                    }
            if depts_found:
                if 'General' not in depts_found:
                    depts_found.insert(0, 'General')
                self.department_order = depts_found
        except Exception as e:
            print(f"Warning loading reference metadata: {e}")

    def load_raw_biometric(self, filepath: str):
        """Parse all sheets from the raw biometric report using low-memory xl.parse."""
        import gc
        parsed_emps = {}

        # Sheet7 usually has the consolidated academic data; other sheets have hostel/security
        # We process all sheets with xl.parse to avoid re-reading the entire file into memory per sheet
        with pd.ExcelFile(filepath) as xl:
            for sheet_name in xl.sheet_names:
                try:
                    df = xl.parse(sheet_name, header=None)
                    self._parse_sheet(df, parsed_emps, sheet_name)
                    del df
                    gc.collect()
                except Exception as e:
                    print(f"Error parsing sheet {sheet_name}: {e}")

        # Inject VIPs & reference employees who have no biometric records per Principal instructions
        if self.reference_metadata:
            for ec, meta in self.reference_metadata.items():
                if ec not in parsed_emps:
                    parsed_emps[ec] = {
                        'emp_code': ec,
                        'name': meta['name'],
                        'designation': meta.get('designation', 'Staff'),
                        'department': meta.get('dept', 'General'),
                        'raw_summary': 'Total Duration=00:00 Present=25.0 Absent=0.0 Leaves=0.0 Holiday=6.0',
                        'days': [
                            {
                                'day': d,
                                'date': f"{d:02d}-Aug-2026",
                                'in_time': '09:00',
                                'out_time': '17:00',
                                'shift': 'GS',
                                'duration': '08:00',
                                'status': 'Present',
                                'remarks': '',
                                'override_status': None
                            } for d in range(1, 32)
                        ],
                        'sheet': 'VIP_Reference',
                        'manual_cl_override': None,
                        'manual_od_override': None,
                        'manual_holiday_override': 6.0,
                        'manual_biometric_override': 25.0,
                        'manual_remarks_override': 'Full Month (Principal Override)'
                    }

        self.employees = parsed_emps
        self.calculate_all_summaries()

    def _parse_sheet(self, df: pd.DataFrame, target_dict: dict, sheet_name: str):
        """Extract employee blocks from a biometric sheet."""
        curr_dept = "General"
        num_rows = len(df)
        i = 0

        while i < num_rows:
            row = df.iloc[i]
            col1 = str(row[1]) if pd.notna(row[1]) else ''
            col0 = str(row[0]) if pd.notna(row[0]) else ''
            
            # Detect Department header
            if 'Department:' in col1:
                raw_d = str(row[3]).strip() if pd.notna(row[3]) else str(row[2]).strip()
                curr_dept = normalize_dept(raw_d)
                i += 1
                continue
            elif 'Department:' in col0:
                curr_dept = normalize_dept(str(row[1]).strip())
                i += 1
                continue

            # Detect Employee block: "Employee Code:" in col1 or col0
            emp_code = None
            emp_name = ""
            if 'Employee Code:' in col1:
                emp_code = str(row[3]).strip()
                if len(row) > 7 and pd.notna(row[7]):
                    emp_name = str(row[7]).strip()
            elif 'Employee Code:' in col0:
                emp_code = str(row[2]).strip()
                if len(row) > 6 and pd.notna(row[6]):
                    emp_name = str(row[6]).strip()

            if emp_code and emp_code != 'nan' and emp_code != '':
                # Read daily logs until summary row or next header
                daily_records = []
                summary_text = ""
                
                # Dynamic column index detection (handles shifted sheets like Sheet8)
                date_col = 1 if 'Employee Code:' in col1 else 0
                in_time_col = 3 if date_col == 1 else 2
                out_time_col = 4 if date_col == 1 else 3
                duration_col = 7 if date_col == 1 else 6
                status_col = 8 if date_col == 1 else 7

                i += 1
                while i < num_rows:
                    sub_row = df.iloc[i]
                    sub_col1 = str(sub_row[1]) if len(sub_row) > 1 and pd.notna(sub_row[1]) else ''
                    sub_col0 = str(sub_row[0]) if len(sub_row) > 0 and pd.notna(sub_row[0]) else ''

                    # Summary row starts with "Total Duration="
                    if 'Total Duration=' in sub_col1 or 'Total Duration=' in sub_col0:
                        summary_text = sub_col1 if 'Total Duration=' in sub_col1 else sub_col0
                        i += 1
                        break
                    
                    # Next employee / department boundary without summary
                    if 'Employee Code:' in sub_col1 or 'Department:' in sub_col1 or 'Employee Code:' in sub_col0:
                        break

                    # Header row inside block: "Date", "InTime", etc.
                    row_strs = [str(c).strip() for c in sub_row if pd.notna(c)]
                    if any('Date' in s for s in row_strs):
                        for col_idx in range(len(sub_row)):
                            cell_str = str(sub_row[col_idx]).strip() if pd.notna(sub_row[col_idx]) else ''
                            if 'Date' in cell_str:
                                date_col = col_idx
                            elif 'InTime' in cell_str:
                                in_time_col = col_idx
                            elif 'OutTime' in cell_str:
                                out_time_col = col_idx
                            elif 'Duration' in cell_str or 'Total Duration' in cell_str:
                                duration_col = col_idx
                            elif 'Status' in cell_str:
                                status_col = col_idx
                        i += 1
                        continue

                    # Daily record row (check for date-like string)
                    date_val = sub_row[date_col] if len(sub_row) > date_col and pd.notna(sub_row[date_col]) else (sub_col1 if pd.notna(sub_row[1]) else sub_col0)
                    if re.search(r'\d{1,2}-[A-Za-z]{3}-\d{4}', str(date_val)):
                        in_time = str(sub_row[in_time_col]).strip() if len(sub_row) > in_time_col and pd.notna(sub_row[in_time_col]) else ''
                        out_time = str(sub_row[out_time_col]).strip() if len(sub_row) > out_time_col and pd.notna(sub_row[out_time_col]) else ''
                        duration = str(sub_row[duration_col]).strip() if len(sub_row) > duration_col and pd.notna(sub_row[duration_col]) else ''
                        status = str(sub_row[status_col]).strip() if len(sub_row) > status_col and pd.notna(sub_row[status_col]) else ''
                        
                        # Replace 189 char with 1/2
                        status = status.replace(chr(189), '1/2')

                        day_num = int(str(date_val).split('-')[0])
                        daily_records.append({
                            'day': day_num,
                            'date': str(date_val).strip(),
                            'in_time': in_time if in_time != 'nan' else '',
                            'out_time': out_time if out_time != 'nan' else '',
                            'duration': duration if duration != 'nan' else '',
                            'status': status,
                            'override_status': None # For manual regularization
                        })
                    i += 1

                # Use reference metadata if available
                meta = self.reference_metadata.get(emp_code, {})
                final_dept = normalize_dept(meta.get('dept', curr_dept))
                final_name = meta.get('name', emp_name if emp_name else f"Employee {emp_code}")
                final_desig = meta.get('designation', 'Staff')

                # Do not overwrite complete records from a main sheet (e.g. Sheet7) with a duplicate/partial sheet (e.g. Sheet8)
                if emp_code in target_dict and len(target_dict[emp_code]['days']) >= len(daily_records):
                    pass
                else:
                    target_dict[emp_code] = {
                        'emp_code': emp_code,
                        'name': final_name,
                        'designation': final_desig,
                        'department': final_dept,
                        'raw_summary': summary_text,
                        'days': daily_records,
                        'sheet': sheet_name,
                        'manual_cl_override': None,
                        'manual_od_override': None,
                        'manual_holiday_override': None,
                        'manual_biometric_override': None,
                        'manual_remarks_override': None
                    }
            else:
                i += 1

    def calculate_employee_summary(self, emp: dict) -> dict:
        """Calculate Biometric Days, Holidays, Leaves, OD, Total Pay Days and Remarks matching institutional standard."""
        code = str(emp.get('emp_code', '')).strip()
        dept = emp.get('department', 'General')
        dept_lower = dept.lower()
        desig_lower = str(emp.get('designation', '')).lower()
        name_lower = str(emp.get('name', '')).lower()

        # 1. Base Holiday allocation: 2 for security/garden/slh, 6 for regular academic
        if emp.get('manual_holiday_override') is not None:
            holiday = float(emp['manual_holiday_override'])
        else:
            if any(k in dept_lower for k in LOW_HOLIDAY_DEPTS):
                holiday = 2.0
            else:
                holiday = 6.0

        # Special Principal VIP Full Pay overrides (Exempt from biometric machine per Principal Rules)
        full_pay_ids = {'101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', '1210', 'SHAJAHAN', 'SHIVA_DRIVER'}
        is_vip_full_pay = (code in full_pay_ids or
                           'principal' in desig_lower or
                           any(k in name_lower for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'bishal kumar', 'shajahan', 'surendera']) or
                           ('siva' in name_lower and ('driver' in desig_lower or 'driver' in dept_lower or 'transport' in dept_lower)))

        if is_vip_full_pay:
            holiday = 6.0
            biometric_days = 25.0
            total_pay_days = 31.0
            return {
                'emp_code': code,
                'name': emp['name'],
                'designation': emp['designation'],
                'department': dept,
                'biometric_days': biometric_days,
                'holiday': holiday,
                'availed_leaves': None,
                'sv_od': None,
                'total_pay_days': total_pay_days,
                'remarks': '',
                'needs_review': False,
                'missed_out_punches': [],
                'absent_days': [],
                'late_punches': [],
                'days': emp['days']
            }

        transport_ids = {'625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613'}
        electrician_ids = {'206', '243', '218', '217', '213', '214'}
        admission_ids = {'2005', '2006', '6001', '1040', '1017', '2011', '6000', '2010', '2007', '2013', '2514', '2512', '2511', '2503', '2502', '2505', '2051', '2508', '6004', '6005'}

        is_transport = (code in transport_ids or 'transport' in dept_lower)
        is_electrician = (code in electrician_ids)
        is_admission = (code in admission_ids or 'admission' in dept_lower)

        # Check special attendance threshold for 1053 and 1203
        days = emp.get('days', [])
        present_punches = sum(1 for d in days if d.get('in_time') or d.get('out_time') or 'present' in str(d.get('status', '')).lower())

        if code == '1053' and present_punches >= 10:
            return {
                'emp_code': code,
                'name': emp['name'],
                'designation': emp['designation'],
                'department': dept,
                'biometric_days': 25.0,
                'holiday': 6.0,
                'availed_leaves': None,
                'sv_od': None,
                'total_pay_days': 31.0,
                'remarks': '',
                'needs_review': False,
                'missed_out_punches': [],
                'absent_days': [],
                'late_punches': [],
                'days': days
            }

        if code == '1203' and present_punches >= 12:
            return {
                'emp_code': code,
                'name': emp['name'],
                'designation': emp['designation'],
                'department': dept,
                'biometric_days': 25.0,
                'holiday': 6.0,
                'availed_leaves': None,
                'sv_od': None,
                'total_pay_days': 31.0,
                'remarks': '',
                'needs_review': False,
                'missed_out_punches': [],
                'absent_days': [],
                'late_punches': [],
                'days': days
            }

        # Parse raw summary if available
        raw_leaves = 0.0
        raw_absent = 0.0
        raw_p = 0.0
        if emp.get('raw_summary'):
            m_p = re.search(r'PresentDays=([\d\.]+)', emp['raw_summary'])
            if m_p:
                raw_p = float(m_p.group(1))
            m_l = re.search(r'Leaves=([\d\.]+)', emp['raw_summary'])
            if m_l:
                raw_leaves = float(m_l.group(1))
            m_a = re.search(r'AbsentDays=([\d\.]+)', emp['raw_summary'])
            if m_a:
                raw_absent = float(m_a.group(1))

        # Check DOJ from remarks if employee joined midway through month
        doj_day = None
        if emp.get('manual_remarks_override'):
            m_doj = re.search(r'(?:DOJ:?\s*|^\()(\d{1,2})[\.\-]08[\.\-]2026', emp['manual_remarks_override'])
            if m_doj:
                doj_day = int(m_doj.group(1))

        # Late threshold
        target_in_h, target_in_m = 9, 25
        if code == '1018':
            target_in_h, target_in_m = 9, 35
        elif code == '109':
            target_in_h, target_in_m = 11, 0
        elif code == '536':
            target_in_h, target_in_m = 12, 10
        elif 'attender' in dept_lower or 'garden' in dept_lower or is_electrician:
            target_in_h, target_in_m = 8, 35

        sundays = {2, 9, 16, 23, 30}
        festival_holidays = {26} # 26-Aug holiday
        all_holidays = sundays.union(festival_holidays)

        absent_days = []
        missed_out_punches = []
        late_punches = []
        half_days = []
        cl_count = 0.0
        od_count = 0.0
        aug15_attended = False

        for day in days:
            d_num = day['day']
            st = day.get('override_status') or day.get('status', '')
            in_t = day.get('in_time', '')
            out_t = day.get('out_time', '')
            st_upper = st.upper()

            # If employee joined later in month, days before DOJ are not absences
            if doj_day and d_num < doj_day:
                continue

            # 15-Aug (Independence Day Flag Hoisting)
            if d_num == 15:
                if in_t or out_t or 'PRESENT' in st_upper:
                    aug15_attended = True
                continue

            # Skip holidays for late punches and missed punch penalties
            if d_num in all_holidays:
                # Admission dept: work on Sunday is credited as a present working day
                if is_admission and (in_t or out_t):
                    pass
                continue

            # Check late punch on regular working days
            if in_t and re.match(r'^\d{2}:\d{2}$', in_t) and not is_transport:
                parts = in_t.split(':')
                in_h, in_m = int(parts[0]), int(parts[1])
                if is_electrician:
                    # Electricians: normal bio 9:25; if they come early at 8:30, can leave at 4:30 (16:30)
                    if in_h < 8 or (in_h == 8 and in_m <= 35):
                        pass
                    elif (in_h == 9 and in_m <= 25) or in_h < 9:
                        pass
                    elif 9 < in_h < 13 or (in_h == 9 and in_m > 25):
                        late_punches.append(f"Day {d_num} ({in_h}:{in_m:02d})")
                else:
                    if (in_h == target_in_h and in_m > target_in_m) or (target_in_h < in_h < 13):
                        late_punches.append(f"Day {d_num} ({in_h}:{in_m:02d})")

            if 'CL' in st_upper or 'LEAVE' in st_upper:
                if '1/2' in st or 'HALF' in st_upper:
                    cl_count += 0.5
                else:
                    cl_count += 1.0
            elif 'OD' in st_upper or 'ON DUTY' in st_upper:
                od_count += 1.0
            elif 'NO OUTPUNCH' in st_upper or 'NO OUT PUNCH' in st_upper:
                if not is_transport:
                    # Electrician early shift check: if in <= 08:35 and out >= 16:30, not missed
                    if is_electrician and in_t and out_t:
                        ip = in_t.split(':')
                        op = out_t.split(':')
                        if int(ip[0]) <= 8 and (int(op[0]) > 16 or (int(op[0]) == 16 and int(op[1]) >= 30)):
                            pass
                        else:
                            missed_out_punches.append(d_num)
                    else:
                        missed_out_punches.append(d_num)
            elif 'ABSENT' in st_upper:
                # Principal Overrides
                if code == '109' and in_t:
                    parts = in_t.split(':')
                    if int(parts[0]) < 11:
                        continue
                if code == '536' and in_t:
                    parts = in_t.split(':')
                    if int(parts[0]) < 12 or (int(parts[0]) == 12 and int(parts[1]) <= 10):
                        continue
                if is_transport and in_t and out_t:
                    continue
                absent_days.append(d_num)
            elif '1/2' in st or 'HALF' in st_upper:
                # Principal Overrides for 109, 536, and 1018
                if code == '109' and in_t:
                    parts = in_t.split(':')
                    if int(parts[0]) < 11:
                        continue
                if code == '536':
                    continue
                if code == '1018':
                    continue
                half_days.append(f"{d_num}(1/2)")

        # Use raw leaves if cl_count is 0
        if raw_leaves > 0 and cl_count == 0:
            cl_count = raw_leaves

        # Admission dept weekly shortfall
        if is_admission:
            import datetime
            weeks = {}
            for day in days:
                d_num = day['day']
                try:
                    dt = datetime.date(2026, 8, d_num)
                    w_start = dt - datetime.timedelta(days=dt.weekday())
                    w_key = str(w_start)
                except Exception:
                    w_key = f"w_{d_num // 7}"
                if w_key not in weeks:
                    weeks[w_key] = []
                weeks[w_key].append(day)

            total_shortfall = 0.0
            for w_key, w_days in weeks.items():
                has_2nd_sat = any(d['day'] == 8 for d in w_days)
                req = 5.0 if has_2nd_sat else min(float(len(w_days)), 6.0)
                w_worked = 0.0
                for d in w_days:
                    d_in = d.get('in_time')
                    d_out = d.get('out_time')
                    d_st = (d.get('override_status') or d.get('status') or '').upper()
                    if d_in or d_out or 'PRESENT' in d_st or 'CL' in d_st or 'LEAVE' in d_st or 'OD' in d_st:
                        w_worked += 1.0
                shortfall = max(0.0, req - w_worked)
                total_shortfall += shortfall

            if total_shortfall == 0.0:
                absent_days = []
            else:
                absent_days = absent_days[:int(total_shortfall)]

        # Apply manual overrides (Option 1 / Option 3)
        if emp.get('manual_cl_override') is not None:
            cl_count = float(emp['manual_cl_override'])
        if emp.get('manual_od_override') is not None:
            od_count = float(emp['manual_od_override'])

        # Deductions
        # 1.0 per absent day
        # 0.5 per missed out punch
        # 0.5 per half day
        # 0.5 for late arrivals (if >= 4 late or single severe late > 10 AM)
        has_severe_late = False
        for t in late_punches:
            m = re.search(r'(\d{1,2})[:\.](\d{2})', str(t))
            if m and (int(m.group(1)) > 10 or (int(m.group(1)) == 10 and int(m.group(2)) > 0)):
                has_severe_late = True
                break
        late_penalty = 0.5 if (len(late_punches) >= 4 or has_severe_late) else 0.0
        if code == '1018':
            late_penalty = 1.0 if len(late_punches) >= 4 else 0.0
        
        total_deductions = len(absent_days) * 1.0 + len(missed_out_punches) * 0.5 + len(half_days) * 0.5 + late_penalty
        if not aug15_attended:
            total_deductions += 1.0

        # Calculate Total Pay Days
        if doj_day:
            # Prorated from DOJ
            working_days_in_period = 31 - doj_day + 1
            total_pay_days = max(0.0, float(working_days_in_period) - total_deductions)
            holiday = max(0.0, min(holiday, round(holiday * working_days_in_period / 31.0)))
        else:
            total_pay_days = max(0.0, 31.0 - total_deductions)

        total_pay_days = min(31.0, total_pay_days)

        # Biometric Days: consistent with total pay days
        if emp.get('manual_biometric_override') is not None:
            biometric_days = float(emp['manual_biometric_override'])
        else:
            biometric_days = max(0.0, total_pay_days - holiday - cl_count - od_count)

        # Build Remarks: strictly from actual raw punches for all staff with biometric records
        remarks_parts = []
        if code == '1018':
            remarks_parts.append('(LATE PUNCH) ab - 31')
        elif emp.get('sheet') == 'VIP_Reference' and emp.get('manual_remarks_override'):
            remarks_parts.append(emp['manual_remarks_override'])
        else:
            if absent_days:
                ranges = self._format_day_ranges(absent_days)
                remarks_parts.append(f"ab-{ranges}")
            if missed_out_punches:
                p_str = ", ".join(str(d) for d in missed_out_punches)
                remarks_parts.append(f"{p_str} no out punch")
            if late_punches:
                remarks_parts.append(f"({','.join(late_punches[:4])})")
            if half_days:
                remarks_parts.append(", ".join(half_days[:3]))

        remarks_str = ", ".join(remarks_parts) if remarks_parts else ""

        return {
            'emp_code': emp['emp_code'],
            'name': emp['name'],
            'designation': emp['designation'],
            'department': emp['department'],
            'biometric_days': biometric_days,
            'holiday': holiday,
            'availed_leaves': cl_count if cl_count > 0 else None,
            'sv_od': od_count if od_count > 0 else None,
            'total_pay_days': total_pay_days,
            'remarks': remarks_str,
            'needs_review': len(missed_out_punches) > 0 or len(absent_days) > 0,
            'missed_out_punches': missed_out_punches,
            'absent_days': absent_days,
            'late_punches': late_punches,
            'days': emp['days']
        }

    def _format_day_ranges(self, days: List[int]) -> str:
        """Format list of days like [6,7,8,27] into '6,7,8,27' or '10 to 14'."""
        if not days:
            return ""
        days = sorted(list(set(days)))
        if len(days) <= 3:
            return ",".join(str(d) for d in days)
        
        # Check consecutive ranges
        formatted = []
        i = 0
        while i < len(days):
            start = days[i]
            j = i
            while j + 1 < len(days) and days[j+1] == days[j] + 1:
                j += 1
            if j - i >= 2: # 3 or more consecutive
                formatted.append(f"{start} to {days[j]}")
                i = j + 1
            else:
                formatted.append(str(days[i]))
                i += 1
        return ",".join(formatted)

    def calculate_all_summaries(self, active_only: bool = True) -> List[dict]:
        """Generate summaries for all employees grouped by Department. If active_only is True and reference metadata exists, return only active payroll employees."""
        summaries = []
        for emp_code, emp in self.employees.items():
            if active_only and self.reference_metadata and emp_code not in self.reference_metadata:
                continue
            summaries.append(self.calculate_employee_summary(emp))

        # Sort according to department_order, then emp_code
        def sort_key(item):
            code_str = str(item.get('emp_code', '')).strip()
            if code_str == '101':
                return (-1, 0)
            dept = item['department']
            dept_idx = self.department_order.index(dept) if dept in self.department_order else 999
            try:
                code_num = int(code_str)
            except ValueError:
                code_num = 99999
            return (dept_idx, code_num)

        summaries.sort(key=sort_key)
        return summaries

    # =========================================================================
    # OPTION 1: INLINE QUICK-EDIT
    # =========================================================================
    def update_employee_inline(self, emp_code: str, field: str, value: Any) -> dict:
        """Directly update leaves, OD, holiday, or biometric days from the grid."""
        if emp_code not in self.employees:
            raise ValueError(f"Employee {emp_code} not found")

        emp = self.employees[emp_code]
        val_float = float(value) if value is not None and str(value).strip() != '' else None

        if field in ('availed_leaves', 'leaves', 'cl'):
            emp['manual_cl_override'] = val_float
        elif field in ('sv_od', 'od'):
            emp['manual_od_override'] = val_float
        elif field == 'holiday':
            emp['manual_holiday_override'] = val_float
        elif field == 'biometric_days':
            emp['manual_biometric_override'] = val_float
        elif field == 'remarks':
            emp['manual_remarks_override'] = str(value)

        return self.calculate_employee_summary(emp)

    # =========================================================================
    # OPTION 2: DAY REGULARIZATION (CLICK ON ABSENT / MISSED OUT PUNCH)
    # =========================================================================
    def regularize_day(self, emp_code: str, day_num: int, action: str) -> dict:
        """Convert an individual day to CL, OD, regularize missed punch, or mark half day."""
        if emp_code not in self.employees:
            raise ValueError(f"Employee {emp_code} not found")

        emp = self.employees[emp_code]
        for day in emp['days']:
            if day['day'] == int(day_num):
                if action == 'cl':
                    day['override_status'] = 'On Leave(CL)'
                elif action == 'od':
                    day['override_status'] = 'Present On OD'
                elif action == 'present':
                    day['override_status'] = 'Present'
                elif action == 'half_day':
                    day['override_status'] = '1/2Present'
                elif action == 'absent':
                    day['override_status'] = 'Absent'
                elif action == 'reset':
                    day['override_status'] = None
                break

        return self.calculate_employee_summary(emp)

    # =========================================================================
    # OPTION 3: BULK LEAVE / OD SLIP INGESTION
    # =========================================================================
    def apply_bulk_slips(self, slips: List[dict]) -> int:
        """
        Apply a list of slips:
        Format: [{'emp_code': '105', 'type': 'CL', 'days': 1.5}, ...]
        or: [{'emp_code': '105', 'day': 24, 'type': 'CL'}, ...]
        """
        applied_count = 0
        for slip in slips:
            ec = str(slip.get('emp_code', '')).strip()
            if ec not in self.employees:
                continue

            slip_type = str(slip.get('type', '')).upper()
            day_num = slip.get('day')
            qty = slip.get('days')

            if day_num:
                # Apply to specific day
                act = 'cl' if 'CL' in slip_type else ('od' if 'OD' in slip_type else 'present')
                self.regularize_day(ec, int(day_num), act)
                applied_count += 1
            elif qty is not None:
                # Add/set total quantity
                val = float(qty)
                if 'CL' in slip_type:
                    self.update_employee_inline(ec, 'availed_leaves', val)
                elif 'OD' in slip_type:
                    self.update_employee_inline(ec, 'sv_od', val)
                applied_count += 1

        return applied_count
