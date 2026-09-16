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
                    ec = str(r[1]).strip()
                    name = str(r[2]).strip()
                    desig = str(r[3]).strip() if pd.notna(r[3]) else ''
                    self.reference_metadata[ec] = {
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

        # If reference metadata has specific order / employees, filter or align
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

        for day in emp['days']:
            d_num = day['day']
            st = day.get('override_status') or day['status']
            in_t = day['in_time']
            out_t = day['out_time']

            # Check late arrivals (>09:25 AM)
            if in_t and re.match(r'^\d{2}:\d{2}$', in_t):
                try:
                    parts = in_t.split(':')
                    hh, mm = int(parts[0]), int(parts[1])
                    if hh == 9 and mm > 25:
                        late_punches.append(f"{hh}.{mm:02d}")
                    elif hh > 9 and hh < 13:
                        late_punches.append(f"{hh}.{mm:02d}")
                except Exception:
                    pass

            # Evaluate day status
            st_upper = st.upper()
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
                    # Attended holiday (15-Aug / Sunday / 26-Aug)
                    # Counted into presence
                    present_count += 1.0
                else:
                    present_count += 1.0
            elif 'NO OUTPUNCH' in st_upper or 'NO OUT PUNCH' in st_upper:
                missed_out_punches.append(d_num)
                # By default, raw machine counts as 0, but if morning punch is present, we log it
            elif 'ABSENT' in st_upper and 'HOLIDAY' not in st_upper:
                absent_days.append(d_num)
            elif 'HOLIDAY' in st_upper:
                # Regular holiday
                pass

        # If raw summary recorded leaves and daily didn't have explicit CL, use raw_leaves
        if raw_leaves > 0 and cl_count == 0:
            cl_count = raw_leaves

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
                # Show up to 4 late times
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
