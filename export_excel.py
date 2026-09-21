import xlwt
from typing import List, Dict, Any

def export_to_xls(employees: List[Dict[str, Any]], output_filepath: str, month_year_str: str = "August -2026"):
    """
    Export the calculated attendance data into the exact legacy .xls (BIFF8) format
    matching output.xls with Department sections, headers, and formulas.
    """
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('New')

    # Fonts & Styles
    title_font = xlwt.Font()
    title_font.name = 'Arial'
    title_font.bold = True
    title_font.height = 240 # 12pt

    header_font = xlwt.Font()
    header_font.name = 'Arial'
    header_font.bold = True
    header_font.height = 200 # 10pt

    dept_font = xlwt.Font()
    dept_font.name = 'Arial'
    dept_font.bold = True
    dept_font.height = 220 # 11pt

    regular_font = xlwt.Font()
    regular_font.name = 'Arial'
    regular_font.height = 200 # 10pt

    # Borders
    thin_borders = xlwt.Borders()
    thin_borders.left = xlwt.Borders.THIN
    thin_borders.right = xlwt.Borders.THIN
    thin_borders.top = xlwt.Borders.THIN
    thin_borders.bottom = xlwt.Borders.THIN

    # Alignments
    align_center = xlwt.Alignment()
    align_center.horz = xlwt.Alignment.HORZ_CENTER
    align_center.vert = xlwt.Alignment.VERT_CENTER

    align_left = xlwt.Alignment()
    align_left.horz = xlwt.Alignment.HORZ_LEFT
    align_left.vert = xlwt.Alignment.VERT_CENTER

    align_right = xlwt.Alignment()
    align_right.horz = xlwt.Alignment.HORZ_RIGHT
    align_right.vert = xlwt.Alignment.VERT_CENTER

    # Styles
    title_style = xlwt.XFStyle()
    title_style.font = title_font
    title_style.alignment = align_left

    dept_style = xlwt.XFStyle()
    dept_style.font = dept_font
    dept_style.alignment = align_left

    header_style = xlwt.XFStyle()
    header_style.font = header_font
    header_style.alignment = align_center
    header_style.borders = thin_borders

    # Header style with light gray background
    header_pattern = xlwt.Pattern()
    header_pattern.pattern = xlwt.Pattern.SOLID_PATTERN
    header_pattern.pattern_fore_colour = xlwt.Style.colour_map['gray25']
    header_style.pattern = header_pattern

    cell_center_style = xlwt.XFStyle()
    cell_center_style.font = regular_font
    cell_center_style.alignment = align_center
    cell_center_style.borders = thin_borders

    cell_left_style = xlwt.XFStyle()
    cell_left_style.font = regular_font
    cell_left_style.alignment = align_left
    cell_left_style.borders = thin_borders

    cell_num_style = xlwt.XFStyle()
    cell_num_style.font = regular_font
    cell_num_style.alignment = align_right
    cell_num_style.borders = thin_borders

    # Set Column Widths (in 1/256th of character width)
    ws.col(0).width = 256 * 8   # S.No
    ws.col(1).width = 256 * 14  # Emp. Code
    ws.col(2).width = 256 * 32  # EmployeeName
    ws.col(3).width = 256 * 22  # Designation
    ws.col(4).width = 256 * 16  # Biometric Days
    ws.col(5).width = 256 * 12  # Holiday
    ws.col(6).width = 256 * 16  # Availed Leaves
    ws.col(7).width = 256 * 12  # SV/OD
    ws.col(8).width = 256 * 16  # Total Pay Days
    ws.col(9).width = 256 * 40  # Remarks

    regular_style = xlwt.XFStyle()
    regular_style.font = regular_font
    regular_style.alignment = align_left

    # Row 0: Title
    ws.write(0, 0, f"Monthly Status Report (Summary Report) - {month_year_str}", title_style)
    # Row 1: Company
    ws.write(1, 0, "Company:", regular_style)
    ws.write(1, 2, "SVCET", dept_style)
    ws.write(1, 4, "Printed On :01 September 2026 11:35", regular_style)

    columns = [
        "S.No", "Emp. Code", "EmployeeName", "Designation",
        "Biometric Days", "Holiday", "Availed Leaves", "SV/OD", "Total Pay Days", "Remarks"
    ]

    current_row = 3
    s_no = 1
    current_dept = None

    # If first employee is Principal Sir (101 / General), write header at row 3 and Principal at row 4
    has_principal_top = len(employees) > 0 and (str(employees[0].get('emp_code', '')).strip() == '101' or employees[0].get('department') == 'General')

    if has_principal_top:
        # Write top column headers
        for col_idx, col_name in enumerate(columns):
            ws.write(current_row, col_idx, col_name, header_style)
        current_row += 1

    for emp in employees:
        dept = emp.get('department', 'General')
        is_principal = (str(emp.get('emp_code', '')).strip() == '101' or dept == 'General')
        
        # When department changes
        if not is_principal and dept != current_dept:
            current_dept = dept
            # Department banner
            ws.write(current_row, 1, "Department:", dept_style)
            ws.write(current_row, 2, current_dept, dept_style)
            current_row += 1

            # Column header row
            for col_idx, col_name in enumerate(columns):
                ws.write(current_row, col_idx, col_name, header_style)
            current_row += 1
        elif is_principal:
            current_dept = 'General'

        # Write employee row
        ws.write(current_row, 0, s_no, cell_center_style)
        ws.write(current_row, 1, emp.get('emp_code', ''), cell_center_style)
        ws.write(current_row, 2, emp.get('name', ''), cell_left_style)
        ws.write(current_row, 3, emp.get('designation', ''), cell_left_style)
        
        # Biometric Days
        bio_val = emp.get('biometric_days', 0.0)
        bio_formatted = int(bio_val) if bio_val == int(bio_val) else bio_val
        ws.write(current_row, 4, bio_formatted, cell_num_style)

        # Holiday
        hol_val = emp.get('holiday', 6.0)
        hol_formatted = int(hol_val) if hol_val == int(hol_val) else hol_val
        ws.write(current_row, 5, hol_formatted, cell_num_style)

        # Availed Leaves
        leave_val = emp.get('availed_leaves')
        if leave_val is not None and leave_val > 0:
            l_formatted = int(leave_val) if leave_val == int(leave_val) else leave_val
            ws.write(current_row, 6, l_formatted, cell_num_style)
        else:
            ws.write(current_row, 6, "", cell_center_style)

        # SV/OD
        od_val = emp.get('sv_od')
        if od_val is not None and od_val > 0:
            od_formatted = int(od_val) if od_val == int(od_val) else od_val
            ws.write(current_row, 7, od_formatted, cell_num_style)
        else:
            ws.write(current_row, 7, "", cell_center_style)

        # Total Pay Days
        tot_val = emp.get('total_pay_days', 0.0)
        tot_formatted = int(tot_val) if tot_val == int(tot_val) else tot_val
        ws.write(current_row, 8, tot_formatted, cell_num_style)

        # Remarks
        ws.write(current_row, 9, emp.get('remarks', ''), cell_left_style)

        current_row += 1
        s_no += 1

    wb.save(output_filepath)
    print(f"Successfully exported {len(employees)} records to {output_filepath}")
