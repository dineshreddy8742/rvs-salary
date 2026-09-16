import re
import os
import openpyxl
from typing import Dict, List, Any, Optional

# =============================================================================
# STATUTORY RULES & CONSTANTS (RVS & Andhra Pradesh State Guidelines)
# =============================================================================

# Professional Tax (AP Slab)
def calculate_pt(gross_salary: float) -> float:
    """
    Andhra Pradesh Professional Tax Slab:
    - Gross > Rs. 20,000  => Rs. 200
    - Gross > Rs. 15,000  => Rs. 150
    - Gross <= Rs. 15,000 => Rs. 0
    """
    if gross_salary > 20000:
        return 200.0
    elif gross_salary > 15000:
        return 150.0
    return 0.0

# Welfare Fund (WF)
def calculate_wf(category: str, gross_salary: float) -> float:
    """
    Welfare Fund:
    - Teaching Staff: Rs. 75
    - Non-Teaching / Support Staff: Rs. 30
    (Only applied if gross_salary > 0)
    """
    if gross_salary <= 0:
        return 0.0
    cat_lower = (category or '').lower()
    if 'teaching' in cat_lower and 'non' not in cat_lower:
        return 75.0
    return 30.0

# Days in month helper
def get_days_in_month_str(month_year_str: str) -> int:
    """Extract total days in month (e.g. 'August -2026' -> 31, 'June 2026' -> 30)."""
    m_lower = month_year_str.lower()
    if 'feb' in m_lower:
        # Check leap year if year present
        m = re.search(r'\d{4}', month_year_str)
        year = int(m.group(0)) if m else 2026
        return 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    if any(k in m_lower for k in ['apr', 'jun', 'sep', 'nov']):
        return 30
    return 31

# =============================================================================
# SALARY CALCULATION FUNCTIONS
# =============================================================================

def calculate_teaching_salary(
    total_salary: float,
    days_in_month: int,
    total_pay_days: float,
    arrears: float = 0.0,
    fa: float = 0.0,
    ta: float = 0.0,
    epf: float = 0.0,
    it: float = 0.0,
    eb: float = 0.0,
    mess: float = 0.0,
    bus: float = 0.0,
    other_ded: float = 0.0
) -> Dict[str, Any]:
    """
    Calculates Teaching Staff Salary based on RVS / SVCET institutional formula:
    - Base Package = Total Salary
    - Basic = ROUND(Total Salary / 1.5331, 0)
    - Earned Basic = (Basic / Days In Month) * Total Pay Days
    - DA = ROUND(Earned Basic * 37.31%, 0)
    - HRA = ROUND(Earned Basic * 16%, 0)
    - Gross Total = ROUNDUP(Earned Basic + DA + HRA + Arrears + FA + TA, 0)
    - Deductions = PT + WF(75) + EPF + IT + EB + Mess + Bus + Other
    - Net Salary = Gross Total - Total Deductions
    """
    if total_salary <= 0 or total_pay_days <= 0 or days_in_month <= 0:
        return {
            'base_salary': total_salary,
            'days_in_month': days_in_month,
            'total_pay_days': total_pay_days,
            'basic': 0.0,
            'earned_basic': 0.0,
            'da': 0.0,
            'hra': 0.0,
            'arrears': arrears,
            'gross_salary': 0.0,
            'pt': 0.0,
            'wf': 0.0,
            'epf': epf,
            'it': it,
            'other_deductions': eb + mess + bus + other_ded,
            'total_deductions': 0.0,
            'net_salary': 0.0
        }

    # Institutional 1.5331 factor (1 + 0.3731 DA + 0.16 HRA)
    basic = round(total_salary / 1.5331, 0)
    earned_basic = (basic / days_in_month) * total_pay_days
    da = round(earned_basic * 0.3731, 0)
    hra = round(earned_basic * 0.16, 0)

    gross = round(earned_basic + da + hra + arrears + fa + ta)

    pt = calculate_pt(gross)
    wf = calculate_wf('Teaching', gross)

    other_total = eb + mess + bus + other_ded
    total_ded = epf + it + pt + wf + other_total
    net_salary = max(0.0, gross - total_ded)

    return {
        'base_salary': total_salary,
        'days_in_month': days_in_month,
        'total_pay_days': total_pay_days,
        'basic': basic,
        'earned_basic': round(earned_basic, 2),
        'da': da,
        'hra': hra,
        'arrears': arrears,
        'gross_salary': gross,
        'pt': pt,
        'wf': wf,
        'epf': epf,
        'it': it,
        'other_deductions': other_total,
        'total_deductions': total_ded,
        'net_salary': net_salary
    }

def calculate_non_teaching_salary(
    consolidated_salary: float,
    days_in_month: int,
    total_pay_days: float,
    category: str = 'Non-Teaching',
    arrears: float = 0.0,
    fa: float = 0.0,
    ta: float = 0.0,
    epf: float = 0.0,
    it: float = 0.0,
    cell: float = 0.0,
    eb: float = 0.0,
    mess: float = 0.0,
    bus: float = 0.0,
    other_ded: float = 0.0
) -> Dict[str, Any]:
    """
    Calculates Non-Teaching, Admin, Transport, Attenders, Garden, and Management Salary:
    - Gross = ROUNDUP((Consolidated Salary / Days In Month) * Total Pay Days + Arrears + FA + TA, 0)
    - Deductions = PT (AP slab) + WF (Rs. 30) + EPF + IT + Cell + EB + Mess + Bus + Other
    - Net Salary = Gross - Total Deductions
    """
    if consolidated_salary <= 0 or total_pay_days <= 0 or days_in_month <= 0:
        return {
            'base_salary': consolidated_salary,
            'days_in_month': days_in_month,
            'total_pay_days': total_pay_days,
            'basic': 0.0,
            'earned_basic': 0.0,
            'da': 0.0,
            'hra': 0.0,
            'arrears': arrears,
            'gross_salary': 0.0,
            'pt': 0.0,
            'wf': 0.0,
            'epf': epf,
            'it': it,
            'other_deductions': cell + eb + mess + bus + other_ded,
            'total_deductions': 0.0,
            'net_salary': 0.0
        }

    # Pro-rata computation matching Excel formula: ROUNDUP(E6/I$5*I6 + M6, 0)
    raw_gross = (consolidated_salary / days_in_month) * total_pay_days + arrears + fa + ta
    # Excel ROUNDUP
    import math
    gross = float(math.ceil(raw_gross))

    pt = calculate_pt(gross)
    wf = calculate_wf(category, gross)

    other_total = cell + eb + mess + bus + other_ded
    total_ded = epf + it + pt + wf + other_total
    net_salary = max(0.0, gross - total_ded)

    return {
        'base_salary': consolidated_salary,
        'days_in_month': days_in_month,
        'total_pay_days': total_pay_days,
        'basic': 0.0,
        'earned_basic': round((consolidated_salary / days_in_month) * total_pay_days, 2),
        'da': 0.0,
        'hra': 0.0,
        'arrears': arrears,
        'gross_salary': gross,
        'pt': pt,
        'wf': wf,
        'epf': epf,
        'it': it,
        'other_deductions': other_total,
        'total_deductions': total_ded,
        'net_salary': net_salary
    }

def calculate_salary_for_profile(
    profile: Dict[str, Any],
    days_in_month: int,
    total_pay_days: float,
    overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Calculate salary for any employee given their profile and monthly pay days."""
    ov = overrides or {}
    cat = profile.get('category') or 'Non-Teaching'
    base_sal = float(ov.get('base_salary') or profile.get('base_salary') or 0.0)
    arrears = float(ov.get('arrears') or profile.get('default_arrears') or 0.0)
    epf = float(ov.get('epf_deduction') or profile.get('epf_amount') or 0.0)
    it = float(ov.get('it_deduction') or 0.0)
    other_ded = float(ov.get('other_deductions') or 0.0)

    cat_lower = cat.lower()
    if 'teaching' in cat_lower and 'non' not in cat_lower:
        return calculate_teaching_salary(
            total_salary=base_sal,
            days_in_month=days_in_month,
            total_pay_days=total_pay_days,
            arrears=arrears,
            epf=epf,
            it=it,
            other_ded=other_ded
        )
    else:
        return calculate_non_teaching_salary(
            consolidated_salary=base_sal,
            days_in_month=days_in_month,
            total_pay_days=total_pay_days,
            category=cat,
            arrears=arrears,
            epf=epf,
            it=it,
            other_ded=other_ded
        )

# =============================================================================
# INGESTION / AUTO-SEEDING FROM DATABASE EXCEL FILES
# =============================================================================

def extract_historical_salary_profiles(database_dir: str = 'database') -> Dict[str, Dict[str, Any]]:
    """
    Extracts all staff salary packages, categories, designations, and bank details
    from historical salary workbooks in the database/ directory.
    """
    files_map = [
        ('Teaching', 'SVCET July2026 - Teaching Staff (ID).xlsx'),
        ('Non-Teaching', 'SVCET July 2026 - NT Staff Salary Bill.xlsx'),
        ('Support/Transport', 'SVCET July 2026 - NT GS, WS, Attender  Transport.xlsx'),
        ('Admission', 'SVCET July 2026 - NT Admission.xlsx'),
        ('Management', 'SVCET July2026 - MGT Staff Salary Bill.xlsx'),
        ('Teaching', 'SVCET June 2026 - Teaching Staff (ID).xlsx'),
        ('Non-Teaching', 'SVCET June 2026 - NT Staff Salary Bill.xlsx')
    ]

    extracted_by_name = {}

    for cat_hint, fname in files_map:
        fpath = os.path.join(database_dir, fname)
        if not os.path.exists(fpath):
            continue

        try:
            wb = openpyxl.load_workbook(fpath, data_only=True)
            for sname in wb.sheetnames:
                ws = wb[sname]
                rows = list(ws.iter_rows(values_only=True))
                if len(rows) < 4:
                    continue

                # Locate header row
                header_idx = -1
                for idx, r in enumerate(rows[:7]):
                    txts = [str(c).lower() for c in r if c]
                    if any('name' in t for t in txts) and any('salary' in t for t in txts):
                        header_idx = idx
                        break
                if header_idx == -1:
                    continue

                headers = [str(c).strip().replace('\n', ' ') if c else '' for c in rows[header_idx]]

                name_i = next((i for i, h in enumerate(headers) if 'name' in h.lower()), -1)
                desig_i = next((i for i, h in enumerate(headers) if 'designation' in h.lower()), -1)
                tot_sal_i = next((i for i, h in enumerate(headers) if 'total salary' in h.lower()), -1)
                if tot_sal_i == -1:
                    tot_sal_i = next((i for i, h in enumerate(headers) if 'consolidated' in h.lower()), -1)
                if tot_sal_i == -1:
                    tot_sal_i = next((i for i, h in enumerate(headers) if 'salary' in h.lower()), -1)

                bank_i = next((i for i, h in enumerate(headers) if 'account' in h.lower()), -1)
                ifsc_i = next((i for i, h in enumerate(headers) if 'ifsc' in h.lower()), -1)
                epf_i = next((i for i, h in enumerate(headers) if 'epf' in h.lower()), -1)

                # Determine category
                sheet_lower = sname.lower()
                cat = 'Teaching' if ('teaching' in sheet_lower or 'prof' in sheet_lower) else cat_hint
                if 'transport' in sheet_lower or 'driver' in sheet_lower: cat = 'Transport'
                elif 'security' in sheet_lower: cat = 'Security'
                elif 'garden' in sheet_lower: cat = 'Garden Staff'
                elif 'attender' in sheet_lower: cat = 'Attender'
                elif 'admission' in sheet_lower: cat = 'Admission'
                elif 'management' in sheet_lower: cat = 'Management'

                for r in rows[header_idx + 1:]:
                    if not r or len(r) <= max(name_i, tot_sal_i):
                        continue
                    name_raw = r[name_i] if name_i >= 0 else None
                    if not name_raw:
                        continue
                    name_str = str(name_raw).strip()
                    if any(skip in name_str.lower() for skip in ['department', 'staff', 'office', 'total', 'section', 'none']):
                        continue

                    tot_sal = r[tot_sal_i] if tot_sal_i >= 0 else None
                    if tot_sal is None or not str(tot_sal).replace('.', '', 1).isdigit():
                        continue
                    sal_val = float(tot_sal)
                    if sal_val < 1000:
                        continue

                    desig_val = str(r[desig_i]).strip() if desig_i >= 0 and r[desig_i] else 'Staff'
                    bank_acc = str(r[bank_i]).strip() if bank_i >= 0 and r[bank_i] else ''
                    if bank_acc.endswith('.0'):
                        bank_acc = bank_acc[:-2]
                    ifsc = str(r[ifsc_i]).strip() if ifsc_i >= 0 and r[ifsc_i] else ''
                    epf_val = float(r[epf_i]) if epf_i >= 0 and r[epf_i] and str(r[epf_i]).replace('.', '', 1).isdigit() else 0.0

                    norm_key = re.sub(r'[^a-zA-Z0-9]', '', name_str.lower())
                    if norm_key and (norm_key not in extracted_by_name or sal_val > extracted_by_name[norm_key]['base_salary']):
                        extracted_by_name[norm_key] = {
                            'name': name_str,
                            'category': cat,
                            'designation': desig_val,
                            'base_salary': sal_val,
                            'bank_name': 'PNB' if bank_acc.startswith('4017') else 'Canara/SBI/Other',
                            'account_no': bank_acc,
                            'ifsc_code': ifsc or ('PUNB0401700' if bank_acc.startswith('4017') else ''),
                            'epf_amount': epf_val,
                            'default_arrears': 0.0
                        }
        except Exception as e:
            print(f"Warning reading {fname}: {e}")

    return extracted_by_name
