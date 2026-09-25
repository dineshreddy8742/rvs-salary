import xlwt
import calendar
from typing import List, Dict, Any

# Official department display order (matches RVS institutional format)
DEPT_ORDER = [
    'General', 'Management Staff', 'Administration', 'Exam Section',
    'CSE', 'ECE', 'EEE', 'ME', 'Civil', 'IT', 'MCA', 'MBA', 'S&H',
    'HAS', 'TAP', 'Library', 'Physical Education',
    'Transport', 'Electriations', 'Security & Water Staff',
    'Attender', 'Garden Staff', 'SLH', 'Admission',
]


def _sort_key(emp: dict) -> tuple:
    dept = (emp.get('department') or 'General').strip()
    try:
        d_idx = DEPT_ORDER.index(dept)
    except ValueError:
        d_idx = len(DEPT_ORDER)
    return (d_idx, dept, (emp.get('name') or '').upper())


def export_to_xls(employees: List[Dict[str, Any]], output_filepath: str, month_year_str: str = "August 2026"):
    """
    Export attendance data to legacy .xls format.
    Layout:
      - Page title & institution header
      - Department-wise sections (banner → column headers → staff rows → dept subtotal)
      - Grand total row at the end
    """
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('New')

    # ── Fonts ──────────────────────────────────────────────────────────────────
    def _font(bold=False, size_pt=10, italic=False):
        f = xlwt.Font()
        f.name = 'Arial'
        f.bold = bold
        f.height = size_pt * 20
        f.italic = italic
        return f

    # ── Alignments ─────────────────────────────────────────────────────────────
    def _align(horz='left', wrap=False):
        a = xlwt.Alignment()
        a.horz = {
            'center': xlwt.Alignment.HORZ_CENTER,
            'left':   xlwt.Alignment.HORZ_LEFT,
            'right':  xlwt.Alignment.HORZ_RIGHT,
        }[horz]
        a.vert = xlwt.Alignment.VERT_CENTER
        a.wrap = xlwt.Alignment.WRAP_AT_RIGHT if wrap else xlwt.Alignment.NOT_WRAP_AT_RIGHT
        return a

    # ── Borders ────────────────────────────────────────────────────────────────
    def _border(style=xlwt.Borders.THIN):
        b = xlwt.Borders()
        b.left = b.right = b.top = b.bottom = style
        return b

    # ── Patterns ───────────────────────────────────────────────────────────────
    def _pattern(colour_idx):
        p = xlwt.Pattern()
        p.pattern = xlwt.Pattern.SOLID_PATTERN
        p.pattern_fore_colour = colour_idx
        return p

    # ── Style builder ──────────────────────────────────────────────────────────
    def _style(bold=False, size_pt=10, horz='left', border=False,
               bg_colour=None, wrap=False, italic=False):
        s = xlwt.XFStyle()
        s.font = _font(bold, size_pt, italic)
        s.alignment = _align(horz, wrap)
        if border:
            s.borders = _border()
        if bg_colour is not None:
            s.pattern = _pattern(bg_colour)
        return s

    # Colour indices (xlwt built-in palette)
    NAVY   = 0x12  # dark blue
    GREY25 = 0x16
    YELLOW = 0x0D
    LIGHT_BLUE = 0x1F
    WHITE  = 0x01

    # Predefined styles
    sty_title    = _style(bold=True, size_pt=13)
    sty_sub      = _style(bold=True, size_pt=11)
    sty_normal   = _style(size_pt=10)
    sty_dept_ban = _style(bold=True, size_pt=11, bg_colour=LIGHT_BLUE)

    sty_hdr      = _style(bold=True, size_pt=9, horz='center',
                          border=True, bg_colour=NAVY)
    sty_hdr.font.colour_index = WHITE

    sty_cell_c   = _style(size_pt=9, horz='center', border=True)
    sty_cell_l   = _style(size_pt=9, horz='left',   border=True, wrap=True)
    sty_cell_r   = _style(size_pt=9, horz='right',  border=True)

    sty_sub_bold_r = _style(bold=True, size_pt=9, horz='right', border=True, bg_colour=YELLOW)
    sty_sub_bold_l = _style(bold=True, size_pt=9, horz='left',  border=True, bg_colour=YELLOW)
    sty_sub_bold_c = _style(bold=True, size_pt=9, horz='center', border=True, bg_colour=YELLOW)
    sty_grand_r    = _style(bold=True, size_pt=10, horz='right', border=True, bg_colour=GREY25)
    sty_grand_l    = _style(bold=True, size_pt=10, horz='left',  border=True, bg_colour=GREY25)
    sty_grand_c    = _style(bold=True, size_pt=10, horz='center', border=True, bg_colour=GREY25)

    # ── Column widths ──────────────────────────────────────────────────────────
    COL_WIDTHS = [
        256 * 6,   # 0: S.No
        256 * 10,  # 1: Emp Code
        256 * 34,  # 2: Name
        256 * 26,  # 3: Designation
        256 * 12,  # 4: Biometric Days
        256 * 10,  # 5: Holiday
        256 * 12,  # 6: Availed Leaves
        256 * 10,  # 7: SV/OD
        256 * 12,  # 8: Total Pay Days
        256 * 44,  # 9: Remarks
    ]
    for ci, w in enumerate(COL_WIDTHS):
        ws.col(ci).width = w

    COLUMNS = [
        "S.No", "Emp. Code", "Employee Name", "Designation",
        "Biometric\nDays", "Holidays", "Availed\nLeaves", "SV/OD",
        "Total Pay\nDays", "Remarks"
    ]

    # ── Sort employees dept-wise then by name ──────────────────────────────────
    employees = sorted(employees, key=_sort_key)

    # ── Helper: write a number cell (int if whole, else float) ─────────────────
    def _num(v):
        try:
            f = float(v or 0)
            return int(f) if f == int(f) else round(f, 1)
        except Exception:
            return 0

    def _write_num(row, col, val, style):
        ws.write(row, col, _num(val), style)

    # ── Header rows ────────────────────────────────────────────────────────────
    ws.write(0, 0, "RVS University – Chittoor | Sri Venkateswara College of Engineering & Technology", sty_title)
    ws.write(1, 0, f"Monthly Attendance Status Report  —  {month_year_str}", sty_sub)
    ws.write(2, 0, "Department-Wise Summary of Biometric Attendance, Leave, and Pay Days", sty_normal)

    current_row = 4
    s_no = 1
    current_dept = None

    grand_bio = grand_hol = grand_lv = grand_od = grand_pay = 0.0

    # Group employees by department maintaining sort order
    from itertools import groupby
    grouped = groupby(employees, key=lambda e: (e.get('department') or 'General').strip())

    for dept_name, dept_emps in grouped:
        dept_emps = list(dept_emps)

        # ── Department banner ───────────────────────────────────────────────────
        ws.write(current_row, 0, '', sty_dept_ban)
        ws.write(current_row, 1, 'Department:', sty_dept_ban)
        ws.write(current_row, 2, dept_name.upper(), sty_dept_ban)
        for c in range(3, 10):
            ws.write(current_row, c, '', sty_dept_ban)
        ws.row(current_row).height = 360  # 18pt
        current_row += 1

        # ── Column header row ───────────────────────────────────────────────────
        for ci, col_name in enumerate(COLUMNS):
            ws.write(current_row, ci, col_name, sty_hdr)
        ws.row(current_row).height = 480  # 24pt
        current_row += 1

        # ── Staff rows ──────────────────────────────────────────────────────────
        d_bio = d_hol = d_lv = d_od = d_pay = 0.0
        dept_start_sno = s_no

        for emp in dept_emps:
            bio  = _num(emp.get('biometric_days', 0))
            hol  = _num(emp.get('holiday', 0))
            lv   = _num(emp.get('availed_leaves') or 0)
            od   = _num(emp.get('sv_od') or 0)
            pay  = _num(emp.get('total_pay_days', 0))
            rem  = str(emp.get('remarks') or '')

            ws.write(current_row, 0, s_no,                           sty_cell_c)
            ws.write(current_row, 1, str(emp.get('emp_code', '')),   sty_cell_c)
            ws.write(current_row, 2, str(emp.get('name', '')),       sty_cell_l)
            ws.write(current_row, 3, str(emp.get('designation', '')),sty_cell_l)
            ws.write(current_row, 4, bio,                             sty_cell_r)
            ws.write(current_row, 5, hol,                             sty_cell_r)
            ws.write(current_row, 6, lv  if lv  else '',              sty_cell_r)
            ws.write(current_row, 7, od  if od  else '',              sty_cell_r)
            ws.write(current_row, 8, pay,                             sty_cell_r)
            ws.write(current_row, 9, rem,                             sty_cell_l)
            ws.row(current_row).height = 340

            d_bio += float(emp.get('biometric_days') or 0)
            d_hol += float(emp.get('holiday') or 0)
            d_lv  += float(emp.get('availed_leaves') or 0)
            d_od  += float(emp.get('sv_od') or 0)
            d_pay += float(emp.get('total_pay_days') or 0)

            current_row += 1
            s_no += 1

        # ── Department subtotal row ─────────────────────────────────────────────
        dept_count = s_no - dept_start_sno
        ws.write(current_row, 0, '',                                   sty_sub_bold_c)
        ws.write(current_row, 1, '',                                   sty_sub_bold_c)
        ws.write(current_row, 2, f'Sub-Total  ({dept_name}) — {dept_count} staff', sty_sub_bold_l)
        ws.write(current_row, 3, '',                                   sty_sub_bold_l)
        ws.write(current_row, 4, round(d_bio, 1),                     sty_sub_bold_r)
        ws.write(current_row, 5, round(d_hol, 1),                     sty_sub_bold_r)
        ws.write(current_row, 6, round(d_lv, 1)  if d_lv  else '',   sty_sub_bold_r)
        ws.write(current_row, 7, round(d_od, 1)  if d_od  else '',   sty_sub_bold_r)
        ws.write(current_row, 8, round(d_pay, 1),                     sty_sub_bold_r)
        ws.write(current_row, 9, '',                                   sty_sub_bold_l)
        ws.row(current_row).height = 360
        current_row += 1

        # Blank separator
        current_row += 1

        grand_bio += d_bio
        grand_hol += d_hol
        grand_lv  += d_lv
        grand_od  += d_od
        grand_pay += d_pay

    # ── Grand Total row ────────────────────────────────────────────────────────
    total_staff = s_no - 1
    ws.write(current_row, 0, '',                                      sty_grand_c)
    ws.write(current_row, 1, '',                                      sty_grand_c)
    ws.write(current_row, 2, f'GRAND TOTAL  —  {total_staff} Staff', sty_grand_l)
    ws.write(current_row, 3, '',                                      sty_grand_l)
    ws.write(current_row, 4, round(grand_bio, 1),                    sty_grand_r)
    ws.write(current_row, 5, round(grand_hol, 1),                    sty_grand_r)
    ws.write(current_row, 6, round(grand_lv, 1)  if grand_lv  else '', sty_grand_r)
    ws.write(current_row, 7, round(grand_od, 1)  if grand_od  else '', sty_grand_r)
    ws.write(current_row, 8, round(grand_pay, 1),                    sty_grand_r)
    ws.write(current_row, 9, '',                                      sty_grand_l)
    ws.row(current_row).height = 420
    current_row += 1

    # ── Footer ─────────────────────────────────────────────────────────────────
    ws.write(current_row + 1, 0,
             f"Generated by RVS Payroll System  ·  {month_year_str}  ·  Total Staff: {total_staff}",
             sty_normal)

    wb.save(output_filepath)
    print(f"[Export] Attendance report saved: {output_filepath}  ({total_staff} staff, {current_row} rows)")
