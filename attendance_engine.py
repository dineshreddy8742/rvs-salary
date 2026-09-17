import re
import os
import pandas as pd
from typing import Dict, List, Any, Optional

# Standard Department Order matching RVS output.xls
STANDARD_DEPARTMENT_ORDER = [
    'CE', 'EEE', 'ME', 'ECE', 'CSE', 'CSM', 'CSD', 'CAI', 'IT', 'MCA', 'MBA',
    'HAS', 'PD', 'Administration', 'Accounts', 'Media', 'Exam Section', 'Library',
    'Maintenance', 'TAP', 'Electriations', 'SLH', 'Admissions', 'Management Staff',
    'Transport', 'Attender', 'Garden Staff', 'Security & Water Staff'
]

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
            df = pd.read_excel(filepath, sheet_name='New', header=None)
            curr_dept = 'General'
            depts_found = []
            for i in range(len(df)):
                r = df.iloc[i]
                val1 = str(r[1]) if pd.notna(r[1]) else ''
                val2 = str(r[2]) if pd.notna(r[2]) else ''
                if 'Department:' in val1:
                    curr_dept = val2.strip()
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
                self.department_order = depts_found
        except Exception as e:
            print(f"Warning loading reference metadata: {e}")

    def load_raw_biometric(self, filepath: str):
        """Parse all sheets from the raw biometric report."""
        xl = pd.ExcelFile(filepath)
        parsed_emps = {}

        # Sheet7 usually has the consolidated academic data; other sheets have hostel/security
        # We process all sheets, keeping the latest/best record per employee
        for sheet_name in xl.sheet_names:
            try:
                df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
                self._parse_sheet(df, parsed_emps, sheet_name)
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
                curr_dept = str(row[3]).strip() if pd.notna(row[3]) else str(row[2]).strip()
                i += 1
                continue
            elif 'Department:' in col0:
                curr_dept = str(row[1]).strip()
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
                i += 1
                while i < num_rows:
                    sub_row = df.iloc[i]
                    sub_col1 = str(sub_row[1]) if pd.notna(sub_row[1]) else ''
                    sub_col0 = str(sub_row[0]) if pd.notna(sub_row[0]) else ''

                    # Summary row starts with "Total Duration="
                    if 'Total Duration=' in sub_col1 or 'Total Duration=' in sub_col0:
                        summary_text = sub_col1 if 'Total Duration=' in sub_col1 else sub_col0
                        i += 1
                        break
                    
                    # Next employee / department boundary without summary
                    if 'Employee Code:' in sub_col1 or 'Department:' in sub_col1 or 'Employee Code:' in sub_col0:
                        break

                    # Header row inside block: "Date", "InTime", etc.
                    if 'Date' in sub_col1 or 'Date' in sub_col0:
                        i += 1
                        continue

                    # Daily record row (check for date-like string)
                    date_val = sub_col1 if pd.notna(sub_row[1]) else sub_col0
                    if re.search(r'\d{1,2}-[A-Za-z]{3}-\d{4}', str(date_val)):
                        # Extract columns: Date, InTime, OutTime, Shift, Duration, Status, Remarks
                        # In Sheet1-7: col1=Date, col3=InTime, col4=OutTime, col6=Shift, col7=Duration, col8=Status
                        in_time = str(sub_row[3]).strip() if len(sub_row) > 3 and pd.notna(sub_row[3]) else ''
                        out_time = str(sub_row[4]).strip() if len(sub_row) > 4 and pd.notna(sub_row[4]) else ''
                        duration = str(sub_row[7]).strip() if len(sub_row) > 7 and pd.notna(sub_row[7]) else ''
                        status = str(sub_row[8]).strip() if len(sub_row) > 8 and pd.notna(sub_row[8]) else ''
                        
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
                final_dept = meta.get('dept', curr_dept)
                final_name = meta.get('name', emp_name if emp_name else f"Employee {emp_code}")
                final_desig = meta.get('designation', 'Staff')

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
        """Calculate Biometric Days, Holidays, Leaves, OD, Total Pay Days and Remarks."""
        dept_lower = emp['department'].lower()
        
        # 1. Base Holiday allocation: 2 for security/garden, 6 for regular academic
        if emp.get('manual_holiday_override') is not None:
            holiday = float(emp['manual_holiday_override'])
        else:
            if any(k in dept_lower for k in LOW_HOLIDAY_DEPTS):
                holiday = 2.0
            else:
                holiday = 6.0

        # 2. Daily calculations
        present_count = 0.0
        cl_count = 0.0
        od_count = 0.0
        absent_days = []
        missed_out_punches = []
        late_punches = []
        half_days = []

        # Parse from raw summary if available
        raw_leaves = 0.0
        if emp.get('raw_summary'):
            m_l = re.search(r'Leaves=([\d\.]+)', emp['raw_summary'])
            if m_l:
                raw_leaves = float(m_l.group(1))

        # Apply Principal Sir's time overrides on daily records
        code = str(emp.get('emp_code', '')).strip()
        dept_lower_str = str(emp.get('department', '')).lower()
        desig_lower = str(emp.get('designation', '')).lower()
        name_lower = str(emp.get('name', '')).lower()

        transport_ids = {'625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613'}
        electrician_ids = {'206', '243', '218', '217', '213'}
        admission_ids = {'2005', '2006', '6001', '1040', '1017', '2011', '6000', '2010', '2007', '2013', '2514', '2512', '2511', '2503', '2502', '2505', '2051', '2508', '6004', '6005'}

        is_transport = (code in transport_ids or 'transport' in dept_lower_str)
        is_electrician = (code in electrician_ids)
        is_admission = (code in admission_ids or 'admission' in dept_lower_str)

        for day in emp['days']:
            d_num = day['day']
            st = day.get('override_status') or day['status']
            in_t = day['in_time']
            out_t = day['out_time']
            
            # Helper to parse HH:MM
            def get_time(t_str):
                if t_str and re.match(r'^\d{2}:\d{2}$', t_str):
                    parts = t_str.split(':')
                    return int(parts[0]), int(parts[1])
                return -1, -1

            in_h, in_m = get_time(in_t)
            out_h, out_m = get_time(out_t)

            st_upper = st.upper()
            
            # Admission dept: work on Sunday is credited as a present working day (August 2, 9, 16, 23, 30)
            if is_admission and d_num in (2, 9, 16, 23, 30) and (in_t or out_t):
                st_upper = 'PRESENT'

            # Principal Overrides for Presence
            if in_t or out_t: # Has some punch
                if is_transport:
                    # Transport: no time limit, any punch is full day
                    if in_t and out_t:
                        st_upper = 'PRESENT'
                elif code == '536' and in_h != -1:
                    # CSE Bala Subramanyam: before 12:10 = full day
                    if in_h < 12 or (in_h == 12 and in_m <= 10):
                        st_upper = 'PRESENT'
                elif code == '109' and in_h != -1:
                    # Civil M. Lilaakar: before 11:00 = full day
                    if in_h < 11:
                        st_upper = 'PRESENT'
                elif is_electrician:
                    # Electrician: in 8:30, out 16:30 -> full day
                    if in_h != -1 and out_h != -1:
                        if (in_h < 8 or (in_h == 8 and in_m <= 35)) and (out_h >= 16 and (out_h > 16 or out_m >= 30)):
                            st_upper = 'PRESENT'
                elif 'attender' in dept_lower_str:
                    # Attenders: in 8:35, out 17:30
                    if in_h != -1 and out_h != -1:
                        if (in_h < 8 or (in_h == 8 and in_m <= 35)) and (out_h >= 17 and (out_h > 17 or out_m >= 30)):
                            st_upper = 'PRESENT'
                elif 'garden' in dept_lower_str:
                    # Garden staff: in 8:35, out 17:10
                    if in_h != -1 and out_h != -1:
                        if (in_h < 8 or (in_h == 8 and in_m <= 35)) and (out_h >= 17 and (out_h > 17 or out_m >= 10)):
                            st_upper = 'PRESENT'

            # Standard late check
            target_in_h, target_in_m = 9, 25
            if code == '1018': # Media Purdvi Raj
                target_in_h, target_in_m = 9, 35
            elif code == '109': # Civil M. Lilaakar: before 11:00 am
                target_in_h, target_in_m = 11, 0
            elif code == '536': # CSE Bala Subramanyam: before 12:10
                target_in_h, target_in_m = 12, 10
            elif 'attender' in dept_lower_str or 'garden' in dept_lower_str:
                target_in_h, target_in_m = 8, 35
                
            # No late punch penalties for Transport Dept
            if in_h != -1 and not is_transport:
                # Electrician: if they come early by 8:35, no late penalty
                if is_electrician and (in_h < 8 or (in_h == 8 and in_m <= 35)):
                    pass
                elif in_h == target_in_h and in_m > target_in_m:
                    late_punches.append(f"{in_h}.{in_m:02d}")
                elif in_h > target_in_h and in_h < 13:
                    late_punches.append(f"{in_h}.{in_m:02d}")

            if 'CL' in st_upper or 'LEAVE' in st_upper:
                if '1/2' in st or 'HALF' in st_upper:
                    cl_count += 0.5
                    if 'PRESENT' in st_upper:
                        present_count += 0.5
                else:
                    cl_count += 1.0
            elif 'OD' in st_upper or 'ON DUTY' in st_upper:
                od_count += 1.0
            elif 'PRESENT' in st_upper:
                if '1/2' in st or 'HALF' in st_upper:
                    present_count += 0.5
                    half_days.append(f"{d_num}(1/2)")
                elif 'HOLIDAY' in st_upper:
                    present_count += 1.0
                else:
                    present_count += 1.0
            elif 'NO OUTPUNCH' in st_upper or 'NO OUT PUNCH' in st_upper:
                if is_transport:
                    present_count += 1.0 # Transport rule overrides NO OUTPUNCH
                else:
                    missed_out_punches.append(d_num)
            elif 'ABSENT' in st_upper and 'HOLIDAY' not in st_upper:
                absent_days.append(d_num)
            elif 'HOLIDAY' in st_upper:
                pass

        # If raw summary recorded leaves and daily didn't have explicit CL, use raw_leaves
        if raw_leaves > 0 and cl_count == 0:
            cl_count = raw_leaves

        # Admission dept: 6 days a week, Sunday punches offset absences
        if is_admission and (present_count + holiday >= 26):
            absent_days = []

        # Apply manual overrides (Option 1 / Option 3)
        if emp.get('manual_cl_override') is not None:
            cl_count = float(emp['manual_cl_override'])
        if emp.get('manual_od_override') is not None:
            od_count = float(emp['manual_od_override'])
        
        # Biometric days override or auto-count
        if emp.get('manual_biometric_override') is not None:
            biometric_days = float(emp['manual_biometric_override'])
        else:
            # Baseline biometric days
            biometric_days = present_count
            # Late arrival penalty: 4 or more late arrivals = -0.5 day
            if len(late_punches) >= 4:
                biometric_days = max(0.0, biometric_days - 0.5)

        # Full Pay Overrides per Principal Instructions
        full_pay_ids = {'101', '707', '1015', '1019', '1021', '4001', '1030', '900', '1060', 'SHAJAHAN', 'SHIVA_DRIVER'}
        is_full_pay = False
        
        if code in full_pay_ids:
            is_full_pay = True
        elif any(k in name_lower for k in ['mohan babu', 'gunasekaran', 'gunaskaran', 'veveka', 'adhikari', 'hari krishna', 'visal kumar', 'bishal kumar', 'shajahan', 'surendera']):
            is_full_pay = True
        elif 'siva' in name_lower and ('driver' in desig_lower or 'driver' in dept_lower_str or 'transport' in dept_lower_str):
            is_full_pay = True
            
        if code == '1053' and (biometric_days >= 12 or present_count >= 12):
            is_full_pay = True
            
        if code == '1203' and (biometric_days >= 14 or present_count >= 14):
            is_full_pay = True
            
        if is_full_pay:
            holiday = 6.0
            biometric_days = 25.0
            total_pay_days = 31.0
            absent_days = []
            missed_out_punches = []
            late_punches = []
            remarks_parts = ["Full Attendance (Principal Override)"]
        else:
            # Build Remarks
            remarks_parts = []
            if emp.get('manual_remarks_override'):
                remarks_parts.append(emp['manual_remarks_override'])
            else:
                if absent_days:
                    # Group consecutive absent days into ranges
                    ranges = self._format_day_ranges(absent_days)
                    remarks_parts.append(f"ab-{ranges}")
                if missed_out_punches:
                    p_str = ", ".join(str(d) for d in missed_out_punches)
                    remarks_parts.append(f"{p_str} no out punch")
                if late_punches:
                    # Show up to 6 late times
                    remarks_parts.append(f"({','.join(late_punches[:6])})")
                if half_days:
                    remarks_parts.append(", ".join(half_days[:3]))

        remarks_str = ", ".join(remarks_parts) if remarks_parts else ""

        # Total Pay Days = Biometric Days + Holiday + Availed Leaves + SV/OD
        total_pay_days = biometric_days + holiday + cl_count + od_count
        # Cap at total days in August (31)
        total_pay_days = min(31.0, total_pay_days)

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
            dept = item['department']
            dept_idx = self.department_order.index(dept) if dept in self.department_order else 999
            try:
                code_num = int(item['emp_code'])
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
