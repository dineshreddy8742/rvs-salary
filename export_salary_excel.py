import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, GradientFill
from openpyxl.utils import get_column_letter
from itertools import groupby
from typing import List, Dict, Any

# ─── Institutional department order ────────────────────────────────────────────
DEPT_ORDER = [
    'General', 'Management Staff', 'Administration', 'Exam Section',
    'CSE', 'ECE', 'EEE', 'ME', 'Civil', 'IT', 'MCA', 'MBA', 'S&H',
    'HAS', 'TAP', 'Library', 'Physical Education',
    'Transport', 'Electriations', 'Security & Water Staff',
    'Attender', 'Garden Staff', 'SLH', 'Admission',
]

TEACHING_DEPTS = {'CSE', 'ECE', 'EEE', 'ME', 'Civil', 'IT', 'MCA', 'MBA',
                   'S&H', 'HAS', 'TAP', 'Library', 'Physical Education'}

SUPPORT_DEPTS  = {'Transport', 'Electriations', 'Security & Water Staff',
                   'Attender', 'Garden Staff', 'SLH'}

ADMIN_DEPTS    = {'General', 'Management Staff', 'Administration',
                   'Exam Section', 'Admission'}


def _dept_sort_key(r: dict) -> tuple:
    dept = (r.get('department') or 'General').strip()
    try:
        idx = DEPT_ORDER.index(dept)
    except ValueError:
        idx = len(DEPT_ORDER)
    return (idx, dept, (r.get('name') or '').upper())


def _n(v, default=0.0) -> float:
    try:
        return float(v or default)
    except Exception:
        return default


def _fmt(v) -> str:
    """Format number: integer if whole, else 1 decimal."""
    f = _n(v)
    return int(f) if f == int(f) else round(f, 2)


# ─── Style helpers ─────────────────────────────────────────────────────────────
def _bd():
    s = Side(style='thin', color='B0BEC5')
    return Border(left=s, right=s, top=s, bottom=s)


def _hd_bd():
    s = Side(style='medium', color='1E3A8A')
    return Border(left=s, right=s, top=s, bottom=s)


def _fill(hex_color: str):
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type='solid')


def _font(size=9, bold=False, color='0F172A', italic=False):
    return Font(name='Arial', size=size, bold=bold, color=color, italic=italic)


def _align(h='left', v='center', wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


# ─── Column auto-width helper ──────────────────────────────────────────────────
def _auto_width(ws, min_w=10, max_w=50):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, min_w), max_w)


# ──────────────────────────────────────────────────────────────────────────────
def export_salary_to_xlsx(
    records: List[Dict[str, Any]],
    output_filepath: str,
    month_year_str: str = "August 2026"
):
    """
    Generate a fully structured, department-wise Salary Bill in .xlsx format.

    Sheets produced:
      1. Teaching Faculty     — dept-wise sections with subtotals
      2. Non-Teaching Staff   — dept-wise sections with subtotals
      3. Support & Transport  — dept-wise sections with subtotals
      4. All Staff (Combined) — every record in one sheet for audit
      5. Bank Disbursement    — sorted by dept for NEFT upload
      6. Executive Summary    — dept-wise payroll KPIs + statutory
      7. Cash Denominations   — support staff cash breakdown
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    INSTITUTION = "Sri Venkateswara College of Engineering & Technology (Autonomous), Chittoor"

    # ── Sort all records department-wise then by name ──────────────────────────
    all_sorted = sorted(records, key=_dept_sort_key)

    # ── Split into category groups ─────────────────────────────────────────────
    def _cat(r):
        dept = (r.get('department') or '').strip()
        cat  = (r.get('category')   or '').lower()
        if dept in TEACHING_DEPTS or ('teaching' in cat and 'non' not in cat):
            return 'Teaching'
        if dept in SUPPORT_DEPTS or any(k in cat for k in ['transport', 'attender', 'garden', 'security']):
            return 'Support'
        return 'NonTeaching'

    teaching    = [r for r in all_sorted if _cat(r) == 'Teaching']
    non_teaching = [r for r in all_sorted if _cat(r) == 'NonTeaching']
    support      = [r for r in all_sorted if _cat(r) == 'Support']

    # ── Color palette ─────────────────────────────────────────────────────────
    C = {
        'navy':     '1E3A8A',
        'slate':    '334155',
        'indigo':   '3730A3',
        'green':    '065F46',
        'amber':    'D97706',
        'teal':     '0F766E',
        'dept_bg':  'DBEAFE',   # light blue — department banner bg
        'dept_txt': '1E40AF',   # dept text
        'sub_bg':   'FEF9C3',   # subtotal row bg
        'grand_bg': 'D1FAE5',   # grand total bg
        'zebra':    'F8FAFC',
        'white':    'FFFFFF',
        'hdr_txt':  'FFFFFF',
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: build a salary sheet with department-wise sections + subtotals
    # ─────────────────────────────────────────────────────────────────────────
    def _build_salary_sheet(ws, title_color: str, staff_list: list, sheet_title: str,
                             is_teaching: bool = False):
        """Write a full structured salary sheet with dept sections."""

        # ── Sheet title rows ────────────────────────────────────────────────
        LAST_COL = 26 if is_teaching else 22

        ws.append([INSTITUTION])
        ws.append([f"{sheet_title}  —  Salary Bill for {month_year_str}"])
        ws.append([])

        for row_num, row_text in [(1, INSTITUTION),
                                   (2, f"{sheet_title}  —  Salary Bill for {month_year_str}")]:
            ws.cell(row_num, 1).font = _font(13, bold=True, color='0F172A')
            ws.cell(row_num, 1).alignment = _align('center', wrap=True)
            merge_end = get_column_letter(LAST_COL)
            ws.merge_cells(f'A{row_num}:{merge_end}{row_num}')

        # ── Column headers ──────────────────────────────────────────────────
        if is_teaching:
            cols = [
                "S.No", "Emp\nCode", "Name of the Staff", "Designation", "Department",
                "Total\nSalary (₹)", "Basic\n(₹)", "Pay\nDays",
                "Earned\nBasic (₹)", "DA\n37.31% (₹)", "HRA\n16% (₹)",
                "Arrears\n(₹)", "Gross Total\n(₹)",
                "EPF (₹)", "IT (₹)", "PT (₹)", "WF (₹)",
                "Bus\nFee (₹)", "Hostel/EB\n(₹)", "Mess\nFee (₹)",
                "Other\nDed (₹)", "Total\nDed (₹)", "Net Salary\n(₹)",
                "Bank\nName", "Account\nNumber", "IFSC Code"
            ]
        else:
            cols = [
                "S.No", "Emp\nCode", "Name of the Staff", "Designation", "Department",
                "Consol.\nSalary (₹)", "Pay\nDays", "Arrears\n(₹)", "Gross Total\n(₹)",
                "EPF (₹)", "IT (₹)", "PT (₹)", "WF (₹)",
                "Bus\nFee (₹)", "Hostel/EB\n(₹)", "Mess\nFee (₹)",
                "Other\nDed (₹)", "Total\nDed (₹)", "Net Salary\n(₹)",
                "Bank\nName", "Account\nNumber", "IFSC Code"
            ]

        header_row_num = ws.max_row + 1

        # Group by department
        grouped = groupby(staff_list, key=lambda r: (r.get('department') or 'General').strip())

        # Grand total accumulators
        g_base = g_pay = g_arr = g_gross = g_epf = g_it = g_pt = g_wf = 0.0
        g_bus  = g_mess = g_heb = g_other = g_ded = g_net = 0.0
        g_basic_comp = 0.0  # teaching only
        grand_count = 0
        s_no = 1

        dept_sections = []
        for dept_name, dept_iter in grouped:
            dept_emps = list(dept_iter)
            if not dept_emps:
                continue
            dept_sections.append((dept_name, dept_emps))

        for dept_name, dept_emps in dept_sections:
            # ── Department banner ─────────────────────────────────────────
            banner_row = ws.max_row + 1
            ws.append([''] * LAST_COL)
            dept_cell = ws.cell(banner_row, 1)
            dept_cell.value = f'  DEPARTMENT :  {dept_name.upper()}'
            dept_cell.font = _font(10, bold=True, color=C['dept_txt'])
            dept_cell.fill = _fill(C['dept_bg'])
            dept_cell.alignment = _align('left')
            ws.row_dimensions[banner_row].height = 22
            ws.merge_cells(f'A{banner_row}:{get_column_letter(LAST_COL)}{banner_row}')

            # ── Column headers ────────────────────────────────────────────
            hdr_row = ws.max_row + 1
            ws.append(cols)
            for ci in range(1, len(cols) + 1):
                c = ws.cell(hdr_row, ci)
                c.font = _font(8, bold=True, color=C['hdr_txt'])
                c.fill = _fill(title_color)
                c.alignment = _align('center', wrap=True)
                c.border = _hd_bd()
            ws.row_dimensions[hdr_row].height = 42

            # ── Staff rows ────────────────────────────────────────────────
            d_base = d_pay = d_arr = d_gross = d_epf = d_it = d_pt = d_wf = 0.0
            d_bus  = d_mess = d_heb = d_other = d_ded = d_net = 0.0
            d_basic_comp = 0.0
            dept_count = 0

            for i, r in enumerate(dept_emps):
                base  = _n(r.get('base_salary'))
                pay   = _n(r.get('total_pay_days'))
                arr   = _n(r.get('arrears'))
                gross = _n(r.get('gross_salary'))
                epf   = _n(r.get('epf_deduction'))
                it    = _n(r.get('it_deduction'))
                pt    = _n(r.get('pt_deduction'))
                wf    = _n(r.get('wf_deduction'))
                bus   = _n(r.get('bus_deduction'))
                mess  = _n(r.get('mess_deduction'))
                heb   = _n(r.get('hostel_eb_deduction'))
                other = _n(r.get('other_deductions'))
                ded   = _n(r.get('total_deductions'))
                net   = _n(r.get('net_salary'))
                e_basic = _n(r.get('earned_basic'))
                e_da    = _n(r.get('earned_da'))
                e_hra   = _n(r.get('earned_hra'))
                bank    = r.get('bank_name', 'PNB') or 'PNB'
                acct    = r.get('account_no', '') or ''
                ifsc    = r.get('ifsc_code', '') or ''
                # Approx plain basic from total salary (base / 1.5331)
                basic_comp = round(base / 1.5331) if base else 0

                if is_teaching:
                    row_vals = [
                        s_no, r.get('emp_code', ''), r.get('name', ''),
                        r.get('designation', ''), r.get('department', ''),
                        _fmt(base), _fmt(basic_comp), _fmt(pay),
                        _fmt(e_basic), _fmt(e_da), _fmt(e_hra),
                        _fmt(arr), _fmt(gross),
                        _fmt(epf), _fmt(it), _fmt(pt), _fmt(wf),
                        _fmt(bus), _fmt(heb), _fmt(mess),
                        _fmt(other), _fmt(ded), _fmt(net),
                        bank, acct, ifsc
                    ]
                else:
                    row_vals = [
                        s_no, r.get('emp_code', ''), r.get('name', ''),
                        r.get('designation', ''), r.get('department', ''),
                        _fmt(base), _fmt(pay), _fmt(arr), _fmt(gross),
                        _fmt(epf), _fmt(it), _fmt(pt), _fmt(wf),
                        _fmt(bus), _fmt(heb), _fmt(mess),
                        _fmt(other), _fmt(ded), _fmt(net),
                        bank, acct, ifsc
                    ]

                ws.append(row_vals)
                data_row = ws.max_row
                ws.row_dimensions[data_row].height = 18

                for ci, val in enumerate(row_vals, start=1):
                    cell = ws.cell(data_row, ci)
                    cell.border = _bd()
                    if i % 2 == 1:
                        cell.fill = _fill(C['zebra'])
                    # Alignment
                    if ci <= 2:
                        cell.alignment = _align('center')
                        cell.font = _font(8, bold=False)
                    elif ci in [3, 4, 5]:
                        cell.alignment = _align('left')
                        cell.font = _font(8)
                    elif ci >= len(row_vals) - 2:  # Bank, Account, IFSC
                        cell.alignment = _align('left')
                        cell.font = _font(8)
                    else:
                        cell.alignment = _align('right')
                        cell.font = _font(8)
                        if isinstance(val, (int, float)):
                            cell.number_format = '#,##0.00'

                # Net salary highlighted
                net_col = 23 if is_teaching else 19
                ws.cell(data_row, net_col).font = _font(8, bold=True, color='065F46')

                d_base += base; d_pay += pay; d_arr  += arr;  d_gross += gross
                d_epf  += epf;  d_it  += it;  d_pt   += pt;   d_wf    += wf
                d_bus  += bus;  d_mess += mess; d_heb += heb;  d_other += other
                d_ded  += ded;  d_net  += net;  d_basic_comp += basic_comp
                dept_count += 1
                s_no += 1

            # ── Dept subtotal row ─────────────────────────────────────────
            sub_row_num = ws.max_row + 1
            if is_teaching:
                sub_vals = [
                    '', f'Sub-Total ({dept_count})', f'{dept_name}', '', '',
                    _fmt(d_base), _fmt(d_basic_comp), _fmt(d_pay),
                    '', '', '', _fmt(d_arr), _fmt(d_gross),
                    _fmt(d_epf), _fmt(d_it), _fmt(d_pt), _fmt(d_wf),
                    _fmt(d_bus), _fmt(d_heb), _fmt(d_mess),
                    _fmt(d_other), _fmt(d_ded), _fmt(d_net),
                    '', '', ''
                ]
            else:
                sub_vals = [
                    '', f'Sub-Total ({dept_count})', f'{dept_name}', '', '',
                    _fmt(d_base), _fmt(d_pay), _fmt(d_arr), _fmt(d_gross),
                    _fmt(d_epf), _fmt(d_it), _fmt(d_pt), _fmt(d_wf),
                    _fmt(d_bus), _fmt(d_heb), _fmt(d_mess),
                    _fmt(d_other), _fmt(d_ded), _fmt(d_net),
                    '', '', ''
                ]
            ws.append(sub_vals)
            sub_row = ws.max_row
            ws.row_dimensions[sub_row].height = 20
            for ci in range(1, len(sub_vals) + 1):
                cell = ws.cell(sub_row, ci)
                cell.fill = _fill(C['sub_bg'])
                cell.border = _bd()
                if ci in [2, 3]:
                    cell.font = _font(8, bold=True, color=C['dept_txt'])
                    cell.alignment = _align('left')
                elif ci <= 5:
                    cell.font = _font(8, bold=True)
                    cell.alignment = _align('left')
                else:
                    cell.font = _font(8, bold=True)
                    cell.alignment = _align('right')
                    if isinstance(sub_vals[ci - 1], (int, float)):
                        cell.number_format = '#,##0.00'

            ws.append([])  # blank separator

            g_base  += d_base;  g_pay  += d_pay;  g_arr   += d_arr
            g_gross += d_gross; g_epf  += d_epf;  g_it    += d_it
            g_pt    += d_pt;    g_wf   += d_wf;   g_bus   += d_bus
            g_mess  += d_mess;  g_heb  += d_heb;  g_other += d_other
            g_ded   += d_ded;   g_net  += d_net;  g_basic_comp += d_basic_comp
            grand_count += dept_count

        # ── Grand total row ───────────────────────────────────────────────────
        if is_teaching:
            grand_vals = [
                '', f'GRAND TOTAL', f'{grand_count} Staff', '', '',
                _fmt(g_base), _fmt(g_basic_comp), _fmt(g_pay),
                '', '', '', _fmt(g_arr), _fmt(g_gross),
                _fmt(g_epf), _fmt(g_it), _fmt(g_pt), _fmt(g_wf),
                _fmt(g_bus), _fmt(g_heb), _fmt(g_mess),
                _fmt(g_other), _fmt(g_ded), _fmt(g_net),
                '', '', ''
            ]
        else:
            grand_vals = [
                '', f'GRAND TOTAL', f'{grand_count} Staff', '', '',
                _fmt(g_base), _fmt(g_pay), _fmt(g_arr), _fmt(g_gross),
                _fmt(g_epf), _fmt(g_it), _fmt(g_pt), _fmt(g_wf),
                _fmt(g_bus), _fmt(g_heb), _fmt(g_mess),
                _fmt(g_other), _fmt(g_ded), _fmt(g_net),
                '', '', ''
            ]
        ws.append(grand_vals)
        grand_row = ws.max_row
        ws.row_dimensions[grand_row].height = 22
        for ci in range(1, len(grand_vals) + 1):
            cell = ws.cell(grand_row, ci)
            cell.fill = _fill(C['grand_bg'])
            cell.border = _hd_bd()
            if ci in [2, 3]:
                cell.font = _font(9, bold=True, color='065F46')
                cell.alignment = _align('left')
            else:
                cell.font = _font(9, bold=True, color='065F46')
                cell.alignment = _align('right')
                if isinstance(grand_vals[ci - 1], (int, float)):
                    cell.number_format = '#,##0.00'

        _auto_width(ws)
        # Freeze top 3 rows + first 3 cols
        ws.freeze_panes = 'D4'
        return grand_count, g_net

    # ─── Build the three category sheets ─────────────────────────────────────
    ws_teach = wb.create_sheet("Teaching Faculty")
    _build_salary_sheet(ws_teach, C['navy'], teaching,
                         "Teaching Faculty", is_teaching=True)

    ws_nt = wb.create_sheet("Non-Teaching Staff")
    _build_salary_sheet(ws_nt, C['slate'], non_teaching,
                         "Non-Teaching Staff", is_teaching=False)

    ws_sup = wb.create_sheet("Support & Transport")
    _build_salary_sheet(ws_sup, C['indigo'], support,
                         "Support, Transport & Attenders", is_teaching=False)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. ALL STAFF COMBINED SHEET (audit sheet with every employee)
    # ─────────────────────────────────────────────────────────────────────────
    ws_all = wb.create_sheet("All Staff (Audit)")
    ws_all.append([INSTITUTION])
    ws_all.append([f"Complete Staff Payroll Register  —  {month_year_str}"])
    ws_all.append([])
    ws_all.merge_cells('A1:X1')
    ws_all.merge_cells('A2:X2')
    ws_all['A1'].font = _font(13, bold=True)
    ws_all['A1'].alignment = _align('center')
    ws_all['A2'].font = _font(11, bold=True)
    ws_all['A2'].alignment = _align('center')

    all_cols = [
        "S.No", "Emp Code", "Name", "Designation", "Department", "Category",
        "Base Salary", "Pay Days", "Earned Basic", "DA", "HRA", "Arrears", "Gross",
        "EPF", "IT", "PT", "WF", "Bus", "Hostel/EB", "Mess", "Other Ded",
        "Total Ded", "Net Salary",
        "Bank", "Account No", "IFSC"
    ]
    ws_all.append(all_cols)
    hdr_r = ws_all.max_row
    for ci in range(1, len(all_cols) + 1):
        c = ws_all.cell(hdr_r, ci)
        c.font = _font(8, bold=True, color='FFFFFF')
        c.fill = _fill(C['teal'])
        c.alignment = _align('center', wrap=True)
        c.border = _hd_bd()
    ws_all.row_dimensions[hdr_r].height = 36

    for i, r in enumerate(all_sorted):
        row_vals = [
            i + 1, r.get('emp_code', ''), r.get('name', ''),
            r.get('designation', ''), r.get('department', ''),
            r.get('category', 'Non-Teaching'),
            _fmt(r.get('base_salary')), _fmt(r.get('total_pay_days')),
            _fmt(r.get('earned_basic')), _fmt(r.get('earned_da')),
            _fmt(r.get('earned_hra')), _fmt(r.get('arrears')),
            _fmt(r.get('gross_salary')), _fmt(r.get('epf_deduction')),
            _fmt(r.get('it_deduction')), _fmt(r.get('pt_deduction')),
            _fmt(r.get('wf_deduction')), _fmt(r.get('bus_deduction')),
            _fmt(r.get('hostel_eb_deduction')), _fmt(r.get('mess_deduction')),
            _fmt(r.get('other_deductions')), _fmt(r.get('total_deductions')),
            _fmt(r.get('net_salary')),
            r.get('bank_name', 'PNB') or 'PNB',
            r.get('account_no', '') or '',
            r.get('ifsc_code', '') or ''
        ]
        ws_all.append(row_vals)
        dr = ws_all.max_row
        ws_all.row_dimensions[dr].height = 16
        for ci, val in enumerate(row_vals, 1):
            c = ws_all.cell(dr, ci)
            c.border = _bd()
            c.font = _font(8)
            if i % 2 == 1:
                c.fill = _fill(C['zebra'])
            if ci in [1, 2, 8]:
                c.alignment = _align('center')
            elif ci in [3, 4, 5, 6, 24, 25, 26]:
                c.alignment = _align('left')
            else:
                c.alignment = _align('right')
                if isinstance(val, (int, float)):
                    c.number_format = '#,##0.00'
        ws_all.cell(dr, 23).font = _font(8, bold=True, color='065F46')

    _auto_width(ws_all)
    ws_all.freeze_panes = 'C5'

    # ─────────────────────────────────────────────────────────────────────────
    # 5. BANK DISBURSEMENT SHEET — sorted dept-wise
    # ─────────────────────────────────────────────────────────────────────────
    ws_bank = wb.create_sheet("Bank Disbursement")
    ws_bank.append([INSTITUTION])
    ws_bank.append([f"Bank Salary Disbursement Schedule  —  {month_year_str}"])
    ws_bank.append([])
    ws_bank.merge_cells('A1:I1')
    ws_bank.merge_cells('A2:I2')
    ws_bank['A1'].font = _font(13, bold=True)
    ws_bank['A1'].alignment = _align('center')
    ws_bank['A2'].font = _font(11, bold=True)
    ws_bank['A2'].alignment = _align('center')

    bank_cols = ["S.No", "Emp Code", "Beneficiary Name", "Department",
                  "Category", "Bank Name", "Account Number", "IFSC Code",
                  "Net Payable (₹)"]
    ws_bank.append(bank_cols)
    hdr_r = ws_bank.max_row
    for ci in range(1, len(bank_cols) + 1):
        c = ws_bank.cell(hdr_r, ci)
        c.font = _font(9, bold=True, color='FFFFFF')
        c.fill = _fill(C['green'])
        c.alignment = _align('center', wrap=True)
        c.border = _hd_bd()
    ws_bank.row_dimensions[hdr_r].height = 30

    total_net = 0.0
    for i, r in enumerate(all_sorted):
        net = _n(r.get('net_salary'))
        total_net += net
        row_vals = [
            i + 1, r.get('emp_code', ''), r.get('name', ''),
            r.get('department', ''), r.get('category', 'Non-Teaching'),
            r.get('bank_name', 'PNB') or 'PNB',
            r.get('account_no', '') or '',
            r.get('ifsc_code', '') or '',
            _fmt(net)
        ]
        ws_bank.append(row_vals)
        dr = ws_bank.max_row
        ws_bank.row_dimensions[dr].height = 16
        for ci, val in enumerate(row_vals, 1):
            c = ws_bank.cell(dr, ci)
            c.border = _bd()
            c.font = _font(8)
            if i % 2 == 1:
                c.fill = _fill(C['zebra'])
            if ci in [1, 2]:
                c.alignment = _align('center')
            elif ci == 9:
                c.alignment = _align('right')
                c.font = _font(8, bold=True, color='065F46')
                c.number_format = '₹#,##0.00'
            else:
                c.alignment = _align('left')

    # Total row
    ws_bank.append([])
    tot_r = ws_bank.max_row + 1
    ws_bank.append(['', 'TOTAL', f'{len(all_sorted)} Staff', '', '', '', '', '', _fmt(total_net)])
    tr = ws_bank.max_row
    ws_bank.merge_cells(f'A{tr}:H{tr}')
    for ci in range(1, 10):
        c = ws_bank.cell(tr, ci)
        c.fill = _fill(C['grand_bg'])
        c.border = _hd_bd()
        c.font = _font(10, bold=True, color='065F46')
    ws_bank.cell(tr, 2).alignment = _align('left')
    ws_bank.cell(tr, 9).alignment = _align('right')
    ws_bank.cell(tr, 9).number_format = '₹#,##0.00'
    ws_bank.row_dimensions[tr].height = 22
    _auto_width(ws_bank)
    ws_bank.freeze_panes = 'C5'

    # ─────────────────────────────────────────────────────────────────────────
    # 6. EXECUTIVE SUMMARY SHEET
    # ─────────────────────────────────────────────────────────────────────────
    try:
        import disbursement_engine
        exec_data = disbursement_engine.generate_executive_summary_data(all_sorted, month_year_str)

        ws_exec = wb.create_sheet("Executive Summary")
        ws_exec.append([INSTITUTION])
        ws_exec.append([f"Executive Salary & Statutory Remittance Summary  —  {month_year_str}"])
        ws_exec.append([])
        ws_exec.merge_cells('A1:G1')
        ws_exec.merge_cells('A2:G2')
        ws_exec['A1'].font = _font(13, bold=True)
        ws_exec['A1'].alignment = _align('center')
        ws_exec['A2'].font = _font(11, bold=True)
        ws_exec['A2'].alignment = _align('center')

        # Dept breakdown
        ws_exec.append(["1.  Department-Wise Payroll Allocation"])
        ws_exec.cell(ws_exec.max_row, 1).font = _font(10, bold=True)
        dept_hdr = ["Department", "Staff Count", "Budget (₹)",
                    "Gross Disbursed (₹)", "Total Deductions (₹)", "Net Disbursed (₹)"]
        ws_exec.append(dept_hdr)
        hr = ws_exec.max_row
        for ci in range(1, 7):
            c = ws_exec.cell(hr, ci)
            c.font = _font(9, bold=True, color='FFFFFF')
            c.fill = _fill(C['slate'])
            c.alignment = _align('center', wrap=True)
            c.border = _hd_bd()
        ws_exec.row_dimensions[hr].height = 30

        for d in exec_data.get('department_summary', []):
            row = [
                d['department'], d['staff_count'],
                _fmt(d['base_salary']), _fmt(d['gross_salary']),
                _fmt(d['pt'] + d['wf'] + d['epf'] + d['it'] + d.get('other', 0)),
                _fmt(d['net_salary'])
            ]
            ws_exec.append(row)
            dr = ws_exec.max_row
            for ci, val in enumerate(row, 1):
                c = ws_exec.cell(dr, ci)
                c.border = _bd()
                c.font = _font(9)
                if ci == 1:
                    c.alignment = _align('left')
                elif ci == 2:
                    c.alignment = _align('center')
                else:
                    c.alignment = _align('right')
                    c.number_format = '₹#,##0.00'
                    if ci == 6:
                        c.font = _font(9, bold=True, color='065F46')

        ws_exec.append([])
        ws_exec.append(["2.  Statutory & Regulatory Remittance Schedule"])
        ws_exec.cell(ws_exec.max_row, 1).font = _font(10, bold=True)
        stat_hdr = ["Remittance Head", "Designated Beneficiary", "Remittance Amount (₹)"]
        ws_exec.append(stat_hdr)
        hr = ws_exec.max_row
        for ci in range(1, 4):
            c = ws_exec.cell(hr, ci)
            c.font = _font(9, bold=True, color='FFFFFF')
            c.fill = _fill(C['navy'])
            c.alignment = _align('center')
            c.border = _hd_bd()

        for st in exec_data.get('statutory_remittances', []):
            row = [st['remittance_head'], st['beneficiary'], _fmt(st['amount'])]
            ws_exec.append(row)
            dr = ws_exec.max_row
            for ci, val in enumerate(row, 1):
                c = ws_exec.cell(dr, ci)
                c.border = _bd()
                c.font = _font(9)
                if ci < 3:
                    c.alignment = _align('left')
                else:
                    c.alignment = _align('right')
                    c.number_format = '₹#,##0.00'
                    c.font = _font(9, bold=True)

        _auto_width(ws_exec)
    except Exception as e:
        print(f"[Export] Executive summary skipped: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. CASH DENOMINATIONS SHEET
    # ─────────────────────────────────────────────────────────────────────────
    try:
        cash_data = disbursement_engine.calculate_cash_denominations(all_sorted)
        ws_cash = wb.create_sheet("Cash Denominations")
        ws_cash.append([INSTITUTION])
        ws_cash.append([f"Support Staff Cash Currency Notes Requisition  —  {month_year_str}"])
        ws_cash.append([])
        ws_cash.merge_cells('A1:L1')
        ws_cash.merge_cells('A2:L2')
        ws_cash['A1'].font = _font(13, bold=True)
        ws_cash['A1'].alignment = _align('center')
        ws_cash['A2'].font = _font(11, bold=True)
        ws_cash['A2'].alignment = _align('center')

        ws_cash.append(["Currency Denomination Summary (For Bank Withdrawal Slip):"])
        ws_cash.cell(ws_cash.max_row, 1).font = _font(10, bold=True)
        den_hdr = ["Denomination (₹)", "Required Notes", "Total Amount (₹)"]
        ws_cash.append(den_hdr)
        hr = ws_cash.max_row
        for ci in range(1, 4):
            c = ws_cash.cell(hr, ci)
            c.font = _font(9, bold=True, color='FFFFFF')
            c.fill = _fill(C['green'])
            c.alignment = _align('center')
            c.border = _hd_bd()

        for item in cash_data.get('denomination_summary', []):
            row = [
                f"₹ {item['denom']}" if str(item['denom']) != 'Coins' else 'Coins / Change',
                item['count'], _fmt(item['total'])
            ]
            ws_cash.append(row)
            dr = ws_cash.max_row
            for ci, val in enumerate(row, 1):
                c = ws_cash.cell(dr, ci)
                c.border = _bd()
                c.font = _font(9)
                if ci == 1:
                    c.alignment = _align('center')
                elif ci == 2:
                    c.alignment = _align('center')
                    c.font = _font(9, bold=True)
                else:
                    c.alignment = _align('right')
                    c.number_format = '₹#,##0.00'
                    c.font = _font(9, bold=True)

        ws_cash.append([])
        ws_cash.append(["Individual Staff Cash Pay-out Breakdown:"])
        ws_cash.cell(ws_cash.max_row, 1).font = _font(10, bold=True)
        staff_hdr = ["Emp Code", "Name", "Category", "Dept",
                      "Net (₹)", "₹500", "₹200", "₹100", "₹50", "₹20", "₹10", "Coins"]
        ws_cash.append(staff_hdr)
        hr = ws_cash.max_row
        for ci in range(1, 13):
            c = ws_cash.cell(hr, ci)
            c.font = _font(9, bold=True, color='FFFFFF')
            c.fill = _fill(C['slate'])
            c.alignment = _align('center', wrap=True)
            c.border = _hd_bd()
        ws_cash.row_dimensions[hr].height = 28

        for i, s in enumerate(cash_data.get('staff_records', [])):
            row_vals = [
                s['emp_code'], s['name'], s['category'], s['department'],
                _fmt(s['net_salary']),
                s['n500'], s['n200'], s['n100'], s['n50'], s['n20'], s['n10'], s['coins']
            ]
            ws_cash.append(row_vals)
            dr = ws_cash.max_row
            for ci, val in enumerate(row_vals, 1):
                c = ws_cash.cell(dr, ci)
                c.border = _bd()
                c.font = _font(8)
                if i % 2 == 1:
                    c.fill = _fill(C['zebra'])
                if ci <= 4:
                    c.alignment = _align('left')
                elif ci == 5:
                    c.alignment = _align('right')
                    c.number_format = '₹#,##0.00'
                    c.font = _font(8, bold=True, color='065F46')
                else:
                    c.alignment = _align('center')

        _auto_width(ws_cash)
    except Exception as e:
        print(f"[Export] Cash denominations sheet skipped: {e}")

    wb.save(output_filepath)
    print(f"[Export] Salary bill saved: {output_filepath}  ({len(all_sorted)} staff total)")
