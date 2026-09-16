import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from typing import List, Dict, Any

def export_salary_to_xlsx(records: List[Dict[str, Any]], output_filepath: str, month_year_str: str = "August -2026"):
    """
    Generate an audit-grade Institutional Multi-Sheet Salary Bill in .xlsx format
    matching the RVS / SVCET standard.
    Sheets:
    1. Teaching Faculty
    2. Non-Teaching Staff
    3. Support & Transport
    4. Bank Disbursement Summary
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    font_title = Font(name='Arial', size=13, bold=True, color='0F172A')
    font_sub = Font(name='Arial', size=11, bold=True, color='334155')
    font_header = Font(name='Arial', size=9, bold=True, color='FFFFFF')
    font_data = Font(name='Arial', size=9)
    font_bold = Font(name='Arial', size=9, bold=True)
    font_currency = Font(name='Arial', size=9, bold=True, color='15803D')

    fill_navy = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
    fill_slate = PatternFill(start_color='334155', end_color='334155', fill_type='solid')
    fill_green = PatternFill(start_color='065F46', end_color='065F46', fill_type='solid')
    fill_zebra = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    fill_total = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')

    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_left = Alignment(horizontal='left', vertical='center')
    align_right = Alignment(horizontal='right', vertical='center')

    # Categorize records
    teaching = [r for r in records if 'teaching' in (r.get('category') or '').lower() and 'non' not in (r.get('category') or '').lower()]
    support = [r for r in records if any(k in (r.get('category') or '').lower() for k in ['transport', 'attender', 'garden', 'security'])]
    non_teaching = [r for r in records if r not in teaching and r not in support]

    # -------------------------------------------------------------------------
    # 1. TEACHING FACULTY SHEET
    # -------------------------------------------------------------------------
    ws_teach = wb.create_sheet(title="Teaching Faculty")
    ws_teach.append(["Sri Venkateswara College of Engineering and Technology"])
    ws_teach.append([f"Teaching Faculty - Salary Bill for the Month of {month_year_str}"])
    ws_teach.append([])

    ws_teach.merge_cells('A1:V1')
    ws_teach.merge_cells('A2:V2')
    ws_teach['A1'].font = font_title
    ws_teach['A1'].alignment = align_center
    ws_teach['A2'].font = font_sub
    ws_teach['A2'].alignment = align_center

    teach_cols = [
        "S.No", "Emp Code", "Name of the Staff", "Designation", "Dept",
        "Total Salary", "Basic", "No of Days", "Earned Basic", "DA (37.31%)", "HRA (16%)",
        "Arrears", "Gross Total", "EPF", "IT", "PT", "WF", "Bus Fee", "Hostel/EB", "Mess Fee", "Other Ded", "Tot Ded", "Net Salary",
        "Bank Name", "Account Number", "IFSC Code"
    ]
    ws_teach.append(teach_cols)
    h_row = ws_teach.max_row
    for col_idx in range(1, len(teach_cols) + 1):
        cell = ws_teach.cell(h_row, col_idx)
        cell.font = font_header
        cell.fill = fill_navy
        cell.alignment = align_center
        cell.border = border_thin

    s_no = 1
    for r in teaching:
        row_vals = [
            s_no,
            r.get('emp_code', ''),
            r.get('name', ''),
            r.get('designation', ''),
            r.get('department', ''),
            r.get('base_salary', 0.0),
            round(r.get('base_salary', 0.0) / 1.5331),
            r.get('total_pay_days', 0.0),
            r.get('earned_basic', 0.0),
            r.get('earned_da', 0.0),
            r.get('earned_hra', 0.0),
            r.get('arrears', 0.0),
            r.get('gross_salary', 0.0),
            r.get('epf_deduction', 0.0),
            r.get('it_deduction', 0.0),
            r.get('pt_deduction', 0.0),
            r.get('wf_deduction', 0.0),
            r.get('bus_deduction', 0.0),
            r.get('hostel_eb_deduction', 0.0),
            r.get('mess_deduction', 0.0),
            r.get('other_deductions', 0.0),
            r.get('total_deductions', 0.0),
            r.get('net_salary', 0.0),
            r.get('bank_name', 'PNB'),
            r.get('account_no', ''),
            r.get('ifsc_code', '')
        ]
        ws_teach.append(row_vals)
        curr_r = ws_teach.max_row
        for c_idx in range(1, len(row_vals) + 1):
            c = ws_teach.cell(curr_r, c_idx)
            c.border = border_thin
            c.font = font_data
            if s_no % 2 == 0:
                c.fill = fill_zebra
            if c_idx in [1, 2, 8]:
                c.alignment = align_center
            elif c_idx in [3, 4, 5, 24, 25, 26]:
                c.alignment = align_left
            else:
                c.alignment = align_right
                c.number_format = '#,##0.00'
            if c_idx == 23: # Net Salary
                c.font = font_currency
        s_no += 1

    # -------------------------------------------------------------------------
    # 2. NON-TEACHING STAFF SHEET
    # -------------------------------------------------------------------------
    ws_nt = wb.create_sheet(title="Non-Teaching Staff")
    ws_nt.append(["Sri Venkateswara College of Engineering and Technology"])
    ws_nt.append([f"Non-Teaching - Salary Bill for the Month of {month_year_str}"])
    ws_nt.append([])

    ws_nt.merge_cells('A1:U1')
    ws_nt.merge_cells('A2:U2')
    ws_nt['A1'].font = font_title
    ws_nt['A1'].alignment = align_center
    ws_nt['A2'].font = font_sub
    ws_nt['A2'].alignment = align_center

    nt_cols = [
        "Sl. No.", "Emp Code", "Name of the Staff", "Designation", "Dept",
        "Consolidated Salary", "No of Days", "Arrears", "Gross Total",
        "EPF", "IT", "PT", "WF", "Bus Fee", "Hostel/EB", "Mess Fee", "Other Ded", "Tot Ded", "Net Salary",
        "Bank Name", "Account Number", "IFSC Code"
    ]
    ws_nt.append(nt_cols)
    h_row = ws_nt.max_row
    for col_idx in range(1, len(nt_cols) + 1):
        cell = ws_nt.cell(h_row, col_idx)
        cell.font = font_header
        cell.fill = fill_slate
        cell.alignment = align_center
        cell.border = border_thin

    s_no = 1
    for r in non_teaching:
        row_vals = [
            s_no,
            r.get('emp_code', ''),
            r.get('name', ''),
            r.get('designation', ''),
            r.get('department', ''),
            r.get('base_salary', 0.0),
            r.get('total_pay_days', 0.0),
            r.get('arrears', 0.0),
            r.get('gross_salary', 0.0),
            r.get('epf_deduction', 0.0),
            r.get('it_deduction', 0.0),
            r.get('pt_deduction', 0.0),
            r.get('wf_deduction', 0.0),
            r.get('bus_deduction', 0.0),
            r.get('hostel_eb_deduction', 0.0),
            r.get('mess_deduction', 0.0),
            r.get('other_deductions', 0.0),
            r.get('total_deductions', 0.0),
            r.get('net_salary', 0.0),
            r.get('bank_name', 'PNB'),
            r.get('account_no', ''),
            r.get('ifsc_code', '')
        ]
        ws_nt.append(row_vals)
        curr_r = ws_nt.max_row
        for c_idx in range(1, len(row_vals) + 1):
            c = ws_nt.cell(curr_r, c_idx)
            c.border = border_thin
            c.font = font_data
            if s_no % 2 == 0:
                c.fill = fill_zebra
            if c_idx in [1, 2, 7]:
                c.alignment = align_center
            elif c_idx in [3, 4, 5, 20, 21, 22]:
                c.alignment = align_left
            else:
                c.alignment = align_right
                c.number_format = '#,##0.00'
            if c_idx == 19: # Net Salary
                c.font = font_currency
        s_no += 1

    # -------------------------------------------------------------------------
    # 3. SUPPORT & TRANSPORT STAFF SHEET
    # -------------------------------------------------------------------------
    ws_sup = wb.create_sheet(title="Support & Transport")
    ws_sup.append(["Sri Venkateswara College of Engineering and Technology"])
    ws_sup.append([f"Transport, Attenders, Security & Garden Staff - Salary Bill for {month_year_str}"])
    ws_sup.append([])

    ws_sup.merge_cells('A1:U1')
    ws_sup.merge_cells('A2:U2')
    ws_sup['A1'].font = font_title
    ws_sup['A1'].alignment = align_center
    ws_sup['A2'].font = font_sub
    ws_sup['A2'].alignment = align_center

    ws_sup.append(nt_cols)
    h_row = ws_sup.max_row
    for col_idx in range(1, len(nt_cols) + 1):
        cell = ws_sup.cell(h_row, col_idx)
        cell.font = font_header
        cell.fill = PatternFill(start_color='4338CA', end_color='4338CA', fill_type='solid')
        cell.alignment = align_center
        cell.border = border_thin

    s_no = 1
    for r in support:
        row_vals = [
            s_no,
            r.get('emp_code', ''),
            r.get('name', ''),
            r.get('designation', ''),
            r.get('department', ''),
            r.get('base_salary', 0.0),
            r.get('total_pay_days', 0.0),
            r.get('arrears', 0.0),
            r.get('gross_salary', 0.0),
            r.get('epf_deduction', 0.0),
            r.get('it_deduction', 0.0),
            r.get('pt_deduction', 0.0),
            r.get('wf_deduction', 0.0),
            r.get('bus_deduction', 0.0),
            r.get('hostel_eb_deduction', 0.0),
            r.get('mess_deduction', 0.0),
            r.get('other_deductions', 0.0),
            r.get('total_deductions', 0.0),
            r.get('net_salary', 0.0),
            r.get('bank_name', 'PNB'),
            r.get('account_no', ''),
            r.get('ifsc_code', '')
        ]
        ws_sup.append(row_vals)
        curr_r = ws_sup.max_row
        for c_idx in range(1, len(row_vals) + 1):
            c = ws_sup.cell(curr_r, c_idx)
            c.border = border_thin
            c.font = font_data
            if s_no % 2 == 0:
                c.fill = fill_zebra
            if c_idx in [1, 2, 7]:
                c.alignment = align_center
            elif c_idx in [3, 4, 5, 17, 18, 19]:
                c.alignment = align_left
            else:
                c.alignment = align_right
                c.number_format = '#,##0.00'
            if c_idx == 16:
                c.font = font_currency
        s_no += 1

    # -------------------------------------------------------------------------
    # 4. BANK DISBURSEMENT STATEMENT
    # -------------------------------------------------------------------------
    ws_bank = wb.create_sheet(title="Bank Disbursement List")
    ws_bank.append(["Sri Venkateswara College of Engineering and Technology"])
    ws_bank.append([f"Bank Salary Disbursement Schedule for {month_year_str}"])
    ws_bank.append([])

    ws_bank.merge_cells('A1:H1')
    ws_bank.merge_cells('A2:H2')
    ws_bank['A1'].font = font_title
    ws_bank['A1'].alignment = align_center
    ws_bank['A2'].font = font_sub
    ws_bank['A2'].alignment = align_center

    bank_cols = ["S.No", "Emp Code", "Beneficiary Name", "Department", "Bank Name", "Account Number", "IFSC Code", "Net Payable Amount (Rs.)"]
    ws_bank.append(bank_cols)
    h_row = ws_bank.max_row
    for col_idx in range(1, len(bank_cols) + 1):
        cell = ws_bank.cell(h_row, col_idx)
        cell.font = font_header
        cell.fill = fill_green
        cell.alignment = align_center
        cell.border = border_thin

    s_no = 1
    total_net_disbursed = 0.0
    for r in records:
        net = float(r.get('net_salary', 0.0))
        total_net_disbursed += net
        row_vals = [
            s_no,
            r.get('emp_code', ''),
            r.get('name', ''),
            r.get('department', ''),
            r.get('bank_name', 'PNB'),
            r.get('account_no', ''),
            r.get('ifsc_code', ''),
            net
        ]
        ws_bank.append(row_vals)
        curr_r = ws_bank.max_row
        for c_idx in range(1, len(row_vals) + 1):
            c = ws_bank.cell(curr_r, c_idx)
            c.border = border_thin
            c.font = font_data
            if s_no % 2 == 0:
                c.fill = fill_zebra
            if c_idx in [1, 2]:
                c.alignment = align_center
            elif c_idx in [3, 4, 5, 6, 7]:
                c.alignment = align_left
            elif c_idx == 8:
                c.alignment = align_right
                c.font = font_currency
                c.number_format = '#,##0.00'
        s_no += 1

    # Total Row
    tot_row = [
        "TOTAL", "", "", "", "", "", "",
        total_net_disbursed
    ]
    ws_bank.append(tot_row)
    curr_r = ws_bank.max_row
    ws_bank.merge_cells(f'A{curr_r}:G{curr_r}')
    ws_bank[f'A{curr_r}'].font = font_bold
    ws_bank[f'A{curr_r}'].alignment = align_center
    ws_bank[f'A{curr_r}'].fill = fill_total
    ws_bank[f'H{curr_r}'].font = Font(name='Arial', size=11, bold=True, color='15803D')
    ws_bank[f'H{curr_r}'].alignment = align_right
    ws_bank[f'H{curr_r}'].number_format = '₹#,##0.00'
    ws_bank[f'H{curr_r}'].fill = fill_total

    # -------------------------------------------------------------------------
    # 5. EXECUTIVE SUMMARY SHEET
    # -------------------------------------------------------------------------
    import disbursement_engine
    exec_data = disbursement_engine.generate_executive_summary_data(records, month_year_str)
    ws_exec = wb.create_sheet(title="Executive Summary")
    ws_exec.append(["Sri Venkateswara College of Engineering and Technology (Autonomous)"])
    ws_exec.append([f"Executive Salary & Statutory Remittance Summary - {month_year_str}"])
    ws_exec.append([])

    ws_exec.merge_cells('A1:G1')
    ws_exec.merge_cells('A2:G2')
    ws_exec['A1'].font = font_title
    ws_exec['A1'].alignment = align_center
    ws_exec['A2'].font = font_sub
    ws_exec['A2'].alignment = align_center

    # Section 1: Department Breakdown
    ws_exec.append(["1. Department-Wise Payroll Allocation"])
    ws_exec.cell(ws_exec.max_row, 1).font = font_bold
    dept_headers = ["Department", "Staff Count", "Monthly Budget", "Gross Disbursed", "Total Deductions", "Net Disbursed"]
    ws_exec.append(dept_headers)
    curr_r = ws_exec.max_row
    for c_idx in range(1, len(dept_headers) + 1):
        c = ws_exec.cell(curr_r, c_idx)
        c.font = font_header
        c.fill = fill_slate
        c.alignment = align_center
        c.border = border_thin

    for d in exec_data['department_summary']:
        row_vals = [
            d['department'],
            d['staff_count'],
            d['base_salary'],
            d['gross_salary'],
            (d['pt'] + d['wf'] + d['epf'] + d['it'] + d['other']),
            d['net_salary']
        ]
        ws_exec.append(row_vals)
        r_idx = ws_exec.max_row
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws_exec.cell(r_idx, c_idx)
            cell.border = border_thin
            cell.font = font_data
            if c_idx == 1: cell.alignment = align_left
            elif c_idx == 2: cell.alignment = align_center
            else:
                cell.alignment = align_right
                cell.number_format = '₹#,##0.00'
                if c_idx == 6: cell.font = font_currency

    ws_exec.append([])
    # Section 2: Statutory Remittances
    ws_exec.append(["2. Statutory & Regulatory Remittance Schedule"])
    ws_exec.cell(ws_exec.max_row, 1).font = font_bold
    stat_headers = ["Remittance Head", "Designated Beneficiary", "Remittance Amount (₹)"]
    ws_exec.append(stat_headers)
    curr_r = ws_exec.max_row
    for c_idx in range(1, len(stat_headers) + 1):
        c = ws_exec.cell(curr_r, c_idx)
        c.font = font_header
        c.fill = fill_navy
        c.alignment = align_center
        c.border = border_thin

    for st in exec_data['statutory_remittances']:
        row_vals = [st['remittance_head'], st['beneficiary'], st['amount']]
        ws_exec.append(row_vals)
        r_idx = ws_exec.max_row
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws_exec.cell(r_idx, c_idx)
            cell.border = border_thin
            cell.font = font_data
            if c_idx in [1, 2]: cell.alignment = align_left
            else:
                cell.alignment = align_right
                cell.number_format = '₹#,##0.00'
                cell.font = font_bold

    # -------------------------------------------------------------------------
    # 6. CASH DENOMINATIONS SHEET
    # -------------------------------------------------------------------------
    cash_data = disbursement_engine.calculate_cash_denominations(records)
    ws_cash = wb.create_sheet(title="Cash Denominations")
    ws_cash.append(["Sri Venkateswara College of Engineering and Technology"])
    ws_cash.append([f"Support Staff Cash Currency Notes Requisition - {month_year_str}"])
    ws_cash.append([])

    ws_cash.merge_cells('A1:L1')
    ws_cash.merge_cells('A2:L2')
    ws_cash['A1'].font = font_title
    ws_cash['A1'].alignment = align_center
    ws_cash['A2'].font = font_sub
    ws_cash['A2'].alignment = align_center

    # Bank note summary table
    ws_cash.append(["Currency Denomination Summary (For Bank Withdrawal Slip):"])
    ws_cash.cell(ws_cash.max_row, 1).font = font_bold
    den_headers = ["Denomination (₹)", "Required Notes Count", "Total Amount (₹)"]
    ws_cash.append(den_headers)
    curr_r = ws_cash.max_row
    for c_idx in range(1, len(den_headers) + 1):
        c = ws_cash.cell(curr_r, c_idx)
        c.font = font_header
        c.fill = fill_green
        c.alignment = align_center
        c.border = border_thin

    for item in cash_data['denomination_summary']:
        row_vals = [
            f"₹ {item['denom']}" if str(item['denom']) != 'Coins' else 'Coins / Change',
            item['count'],
            item['total']
        ]
        ws_cash.append(row_vals)
        r_idx = ws_cash.max_row
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws_cash.cell(r_idx, c_idx)
            cell.border = border_thin
            cell.font = font_data
            if c_idx == 1: cell.alignment = align_center
            elif c_idx == 2: cell.alignment = align_center; cell.font = font_bold
            else:
                cell.alignment = align_right
                cell.number_format = '₹#,##0.00'
                cell.font = font_bold

    ws_cash.append([])
    # Detailed staff breakdown
    ws_cash.append(["Individual Staff Cash Pay-out Breakdown:"])
    ws_cash.cell(ws_cash.max_row, 1).font = font_bold
    staff_headers = ["Emp Code", "Staff Name", "Category", "Department", "Net Payable", "₹500", "₹200", "₹100", "₹50", "₹20", "₹10", "Coins"]
    ws_cash.append(staff_headers)
    curr_r = ws_cash.max_row
    for c_idx in range(1, len(staff_headers) + 1):
        c = ws_cash.cell(curr_r, c_idx)
        c.font = font_header
        c.fill = fill_slate
        c.alignment = align_center
        c.border = border_thin

    for s in cash_data['staff_records']:
        row_vals = [
            s['emp_code'], s['name'], s['category'], s['department'], s['net_salary'],
            s['n500'], s['n200'], s['n100'], s['n50'], s['n20'], s['n10'], s['coins']
        ]
        ws_cash.append(row_vals)
        r_idx = ws_cash.max_row
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws_cash.cell(r_idx, c_idx)
            cell.border = border_thin
            cell.font = font_data
            if c_idx in [1, 2, 3, 4]: cell.alignment = align_left
            elif c_idx == 5:
                cell.alignment = align_right
                cell.number_format = '₹#,##0.00'
                cell.font = font_currency
            else:
                cell.alignment = align_center

    # Adjust column widths automatically
    for ws in [ws_teach, ws_nt, ws_sup, ws_bank, ws_exec, ws_cash]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row > 3 and cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 11)

    wb.save(output_filepath)
    print(f"Successfully exported Institutional Salary Bill to: {output_filepath}")

