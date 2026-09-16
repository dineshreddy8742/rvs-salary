import io
import os
import csv
import zipfile
import tempfile
from typing import List, Dict, Any, Optional

import payroll_engine
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


# =============================================================================
# 1. BANK CORPORATE NEFT / RTGS TRANSFER FILE (.csv)
# =============================================================================

def generate_bank_neft_csv(records: List[Dict[str, Any]], month_year: str, bank_filter: Optional[str] = None) -> str:
    """
    Generates a corporate banking NEFT/RTGS upload CSV formatted as:
    Account Number,Net Amount,Beneficiary Name,IFSC Code,Transaction Narration
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Standard Corporate Net Banking Header
    writer.writerow(["Account Number", "Net Amount", "Beneficiary Name", "IFSC Code", "Transaction Narration"])

    clean_month = month_year.replace('-', ' ').strip().upper()
    narration = f"SALARY {clean_month}"

    for r in records:
        net = float(r.get('net_salary') or 0.0)
        acc = str(r.get('account_no') or '').strip()
        if acc.endswith('.0'):
            acc = acc[:-2]

        # Filter out invalid, zero or cash records
        if net <= 0 or not acc or acc.lower() in ('pending', 'none', 'nan', '0', ''):
            continue

        b_name = r.get('bank_name', 'PNB')
        if bank_filter and bank_filter.upper() != 'ALL' and bank_filter.upper() not in b_name.upper():
            continue

        ifsc = str(r.get('ifsc_code') or '').strip()
        if not ifsc or ifsc.lower() in ('none', 'nan', ''):
            ifsc = 'PUNB0401700' if acc.startswith('4017') else 'SBIN0000000'

        name = str(r.get('name') or '').strip()
        writer.writerow([acc, int(round(net)), name, ifsc, narration])

    return output.getvalue()


# =============================================================================
# 2. CASH DENOMINATION REQUISITION (ATTENDERS, GARDEN & CASH STAFF)
# =============================================================================

def calculate_cash_denominations(records: List[Dict[str, Any]], target_categories: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Calculates the exact currency note breakdown (Rs. 500, 200, 100, 50, 20, 10)
    for staff receiving cash or lacking bank accounts.
    """
    if target_categories is None:
        target_categories = ['Attender', 'Garden Staff', 'Security', 'Transport']

    notes_denoms = [500, 200, 100, 50, 20, 10]
    staff_breakdown = []
    tot_notes = {500: 0, 200: 0, 100: 0, 50: 0, 20: 0, 10: 0, 'coins': 0}
    tot_cash = 0

    for r in records:
        cat = r.get('category', '')
        acc = str(r.get('account_no') or '').strip()
        net = float(r.get('net_salary') or 0.0)

        is_cash_target = (
            cat in target_categories or
            not acc or
            acc.lower() in ('pending', 'none', 'nan', '0', '') or
            acc.endswith('.0')
        )

        if not is_cash_target or net <= 0:
            continue

        amount = int(round(net))
        tot_cash += amount
        rem = amount

        row_notes = {}
        for d in notes_denoms:
            count = rem // d
            row_notes[d] = count
            tot_notes[d] += count
            rem = rem % d

        row_notes['coins'] = rem
        tot_notes['coins'] += rem

        staff_breakdown.append({
            'emp_code': r.get('emp_code'),
            'name': r.get('name'),
            'category': cat,
            'department': r.get('department'),
            'net_salary': amount,
            'n500': row_notes[500],
            'n200': row_notes[200],
            'n100': row_notes[100],
            'n50': row_notes[50],
            'n20': row_notes[20],
            'n10': row_notes[10],
            'coins': row_notes['coins']
        })

    return {
        'status': 'success',
        'staff_count': len(staff_breakdown),
        'total_cash_amount': tot_cash,
        'denomination_summary': [
            {'denom': 500, 'count': tot_notes[500], 'total': tot_notes[500] * 500},
            {'denom': 200, 'count': tot_notes[200], 'total': tot_notes[200] * 200},
            {'denom': 100, 'count': tot_notes[100], 'total': tot_notes[100] * 100},
            {'denom': 50, 'count': tot_notes[50], 'total': tot_notes[50] * 50},
            {'denom': 20, 'count': tot_notes[20], 'total': tot_notes[20] * 20},
            {'denom': 10, 'count': tot_notes[10], 'total': tot_notes[10] * 10},
            {'denom': 'Coins', 'count': tot_notes['coins'], 'total': tot_notes['coins']}
        ],
        'staff_records': staff_breakdown
    }


# =============================================================================
# 3. EXECUTIVE DEPARTMENT-WISE SUMMARY SHEET
# =============================================================================

def generate_executive_summary_data(records: List[Dict[str, Any]], month_year: str) -> Dict[str, Any]:
    """
    Computes Department-wise, Category-wise, and Statutory Remittance summaries.
    """
    dept_map = {}
    cat_map = {}
    tot_budget = 0.0
    tot_gross = 0.0
    tot_pt = 0.0
    tot_wf = 0.0
    tot_epf = 0.0
    tot_it = 0.0
    tot_other = 0.0
    tot_net = 0.0

    for r in records:
        dept = r.get('department') or 'General'
        cat = r.get('category') or 'Non-Teaching'

        base = float(r.get('base_salary') or 0.0)
        gross = float(r.get('gross_salary') or 0.0)
        pt = float(r.get('pt_deduction') or 0.0)
        wf = float(r.get('wf_deduction') or 0.0)
        epf = float(r.get('epf_deduction') or 0.0)
        it = float(r.get('it_deduction') or 0.0)
        other = float(r.get('other_deductions') or 0.0)
        net = float(r.get('net_salary') or 0.0)

        tot_budget += base
        tot_gross += gross
        tot_pt += pt
        tot_wf += wf
        tot_epf += epf
        tot_it += it
        tot_other += other
        tot_net += net

        # Dept aggregation
        if dept not in dept_map:
            dept_map[dept] = {
                'department': dept,
                'staff_count': 0,
                'base_salary': 0.0,
                'gross_salary': 0.0,
                'pt': 0.0,
                'wf': 0.0,
                'epf': 0.0,
                'it': 0.0,
                'other': 0.0,
                'net_salary': 0.0
            }
        d_item = dept_map[dept]
        d_item['staff_count'] += 1
        d_item['base_salary'] += base
        d_item['gross_salary'] += gross
        d_item['pt'] += pt
        d_item['wf'] += wf
        d_item['epf'] += epf
        d_item['it'] += it
        d_item['other'] += other
        d_item['net_salary'] += net

        # Category aggregation
        if cat not in cat_map:
            cat_map[cat] = {
                'category': cat,
                'staff_count': 0,
                'base_salary': 0.0,
                'gross_salary': 0.0,
                'net_salary': 0.0
            }
        c_item = cat_map[cat]
        c_item['staff_count'] += 1
        c_item['base_salary'] += base
        c_item['gross_salary'] += gross
        c_item['net_salary'] += net

    return {
        'status': 'success',
        'month_year': month_year,
        'grand_totals': {
            'total_staff': len(records),
            'total_budget': round(tot_budget, 2),
            'total_gross': round(tot_gross, 2),
            'total_pt': round(tot_pt, 2),
            'total_wf': round(tot_wf, 2),
            'total_epf': round(tot_epf, 2),
            'total_it': round(tot_it, 2),
            'total_other_deductions': round(tot_other, 2),
            'total_net_disbursed': round(tot_net, 2)
        },
        'statutory_remittances': [
            {'remittance_head': 'AP State Professional Tax (PT)', 'beneficiary': 'AP State Commercial Tax Dept', 'amount': round(tot_pt, 2)},
            {'remittance_head': 'Staff Welfare Fund (WF)', 'beneficiary': 'SVCET Staff Welfare Society', 'amount': round(tot_wf, 2)},
            {'remittance_head': 'Employees Provident Fund (EPF)', 'beneficiary': 'EPFO Regional Office', 'amount': round(tot_epf, 2)},
            {'remittance_head': 'Income Tax TDS', 'beneficiary': 'Central Board of Direct Taxes (CBDT)', 'amount': round(tot_it, 2)},
            {'remittance_head': 'Total Statutory Remittances', 'beneficiary': 'Statutory Authorities Total', 'amount': round(tot_pt + tot_wf + tot_epf + tot_it, 2)},
            {'remittance_head': 'Net Salary Bank Disbursement', 'beneficiary': 'PNB / Staff Bank Accounts', 'amount': round(tot_net, 2)}
        ],
        'department_summary': sorted(list(dept_map.values()), key=lambda x: x['net_salary'], reverse=True),
        'category_summary': sorted(list(cat_map.values()), key=lambda x: x['net_salary'], reverse=True)
    }


# =============================================================================
# 4. REPORTLAB PDF PAYSLIP GENERATION (INDIVIDUAL, ZIP & CONSOLIDATED)
# =============================================================================

def _build_payslip_flowables(r: Dict[str, Any], month_year: str, styles) -> List[Any]:
    """Generates ReportLab flowable elements for a single staff member."""
    flowables = []
    clean_month = month_year.replace('-', ' ').strip().upper()

    # Title & Header
    flowables.append(Paragraph("<b>SRI VENKATESWARA COLLEGE OF ENGINEERING & TECHNOLOGY</b>", styles['CollegeTitle']))
    flowables.append(Paragraph("(AUTONOMOUS) • RVS GROUP OF INSTITUTIONS • CHITTOOR, ANDHRA PRADESH", styles['CollegeSub']))
    flowables.append(Paragraph(f"<b>PAYSLIP FOR THE MONTH OF {clean_month}</b>", styles['SlipDocTitle']))
    flowables.append(Spacer(1, 10))

    # Meta Credentials Grid
    meta_data = [
        [
            Paragraph(f"<b>Employee Code:</b> {r.get('emp_code')}", styles['MetaText']),
            Paragraph(f"<b>Bank Name:</b> {r.get('bank_name', 'PNB')}", styles['MetaText'])
        ],
        [
            Paragraph(f"<b>Employee Name:</b> {r.get('name')}", styles['MetaText']),
            Paragraph(f"<b>Account No:</b> {r.get('account_no', 'Pending')}", styles['MetaText'])
        ],
        [
            Paragraph(f"<b>Designation:</b> {r.get('designation', 'Faculty / Staff')}", styles['MetaText']),
            Paragraph(f"<b>IFSC Code:</b> {r.get('ifsc_code', 'PUNB0401700')}", styles['MetaText'])
        ],
        [
            Paragraph(f"<b>Department:</b> {r.get('department')}", styles['MetaText']),
            Paragraph(f"<b>Total Pay Days:</b> {r.get('total_pay_days')} Days", styles['MetaText'])
        ],
        [
            Paragraph(f"<b>Staff Category:</b> {r.get('category')}", styles['MetaText']),
            Paragraph(f"<b>Base Package:</b> Rs. {int(round(float(r.get('base_salary') or 0))):,}", styles['MetaText'])
        ]
    ]
    meta_table = Table(meta_data, colWidths=[260, 240])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    flowables.append(meta_table)
    flowables.append(Spacer(1, 12))

    # Side-by-Side Tables: Earnings (Left) vs Deductions (Right)
    is_teaching = 'teaching' in str(r.get('category', '')).lower() and 'non' not in str(r.get('category', '')).lower()
    gross = float(r.get('gross_salary') or 0.0)
    pt = float(r.get('pt_deduction') or 0.0)
    wf = float(r.get('wf_deduction') or 0.0)
    epf = float(r.get('epf_deduction') or 0.0)
    it = float(r.get('it_deduction') or 0.0)
    other = float(r.get('other_deductions') or 0.0)
    total_ded = float(r.get('total_deductions') or 0.0)
    net = float(r.get('net_salary') or 0.0)

    f_curr = lambda x: f"Rs. {int(round(x)):,}"

    if is_teaching:
        earn_items = [
            ("Basic Pay (Earned)", f_curr(r.get('earned_basic') or 0)),
            ("Dearness Allowance (DA 37.31%)", f_curr(r.get('earned_da') or 0)),
            ("House Rent Allowance (HRA 16%)", f_curr(r.get('earned_hra') or 0)),
            ("Arrears / Allowance", f_curr(r.get('arrears') or 0)),
            ("GROSS EARNINGS (A)", f_curr(gross))
        ]
    else:
        arrears = float(r.get('arrears') or 0.0)
        earn_items = [
            ("Consolidated Monthly Pay", f_curr(r.get('base_salary') or 0)),
            ("Earned Gross Pay", f_curr(gross - arrears)),
            ("Arrears / Bonus", f_curr(arrears)),
            ("-", "-"),
            ("GROSS EARNINGS (A)", f_curr(gross))
        ]

    ded_items = [
        ("Professional Tax (PT)", f_curr(pt)),
        ("Staff Welfare Fund (WF)", f_curr(wf)),
        ("Provident Fund (EPF)", f_curr(epf)),
        ("Income Tax / TDS", f_curr(it)),
        ("TOTAL DEDUCTIONS (B)", f_curr(total_ded))
    ]

    combined_table_data = [
        ["EARNINGS HEAD", "AMOUNT", "DEDUCTIONS HEAD", "AMOUNT"],
        [earn_items[0][0], earn_items[0][1], ded_items[0][0], ded_items[0][1]],
        [earn_items[1][0], earn_items[1][1], ded_items[1][0], ded_items[1][1]],
        [earn_items[2][0], earn_items[2][1], ded_items[2][0], ded_items[2][1]],
        [earn_items[3][0], earn_items[3][1], ded_items[3][0], ded_items[3][1]],
        [earn_items[4][0], earn_items[4][1], ded_items[4][0], ded_items[4][1]],
    ]

    salary_table = Table(combined_table_data, colWidths=[170, 80, 170, 80])
    salary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, -1), (1, -1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2, -1), (3, -1), colors.HexColor('#fef3c7')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    flowables.append(salary_table)
    flowables.append(Spacer(1, 12))

    # Net Disbursed & In Words Box
    words = payroll_engine.number_to_words_inr(net)
    net_box_data = [
        [
            Paragraph(f"<b>NET PAYABLE AMOUNT:</b> <font size=12 color='#065f46'><b>{f_curr(net)}</b></font><br/><font size=8 color='#475569'><i>{words}</i></font>", styles['MetaText'])
        ]
    ]
    net_table = Table(net_box_data, colWidths=[500])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#059669')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    flowables.append(net_table)
    flowables.append(Spacer(1, 40))

    # Official Signatures
    sig_data = [
        ["________________________", "________________________", "________________________"],
        ["Employee Signature", "Checked by Accounts Officer", "Principal / Director Approval"]
    ]
    sig_table = Table(sig_data, colWidths=[166, 166, 166])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#475569')),
    ]))
    flowables.append(sig_table)
    return flowables


def _get_reportlab_styles():
    base = getSampleStyleSheet()
    styles = {
        'CollegeTitle': ParagraphStyle('CollegeTitle', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=12, alignment=1, textColor=colors.HexColor('#1e3a8a')),
        'CollegeSub': ParagraphStyle('CollegeSub', parent=base['Normal'], fontName='Helvetica', fontSize=7.5, alignment=1, textColor=colors.HexColor('#475569')),
        'SlipDocTitle': ParagraphStyle('SlipDocTitle', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=1, textColor=colors.HexColor('#0f172a'), spaceBefore=4),
        'MetaText': ParagraphStyle('MetaText', parent=base['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#0f172a')),
    }
    return styles


def generate_single_payslip_pdf(r: Dict[str, Any], month_year: str, output_path: str):
    """Generates an individual PDF payslip for one employee."""
    styles = _get_reportlab_styles()
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    flowables = _build_payslip_flowables(r, month_year, styles)
    doc.build(flowables)


def generate_consolidated_payslips_pdf(records: List[Dict[str, Any]], month_year: str, output_path: str):
    """Generates a single merged multi-page PDF of all payslips with page breaks."""
    styles = _get_reportlab_styles()
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    flowables = []

    valid_records = [r for r in records if float(r.get('net_salary') or 0) > 0]
    for i, r in enumerate(valid_records):
        flowables.extend(_build_payslip_flowables(r, month_year, styles))
        if i < len(valid_records) - 1:
            flowables.append(PageBreak())

    doc.build(flowables)


def generate_bulk_payslips_zip(records: List[Dict[str, Any]], month_year: str, output_zip_path: str):
    """Generates a ZIP archive containing individual PDF payslips for all staff."""
    valid_records = [r for r in records if float(r.get('net_salary') or 0) > 0]
    styles = _get_reportlab_styles()

    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        with tempfile.TemporaryDirectory() as tmpdir:
            for r in valid_records:
                ec = r.get('emp_code')
                name_clean = ''.join(c for c in r.get('name', 'Staff') if c.isalnum() or c in ' _-').strip()
                pdf_filename = f"PaySlip_{ec}_{name_clean}.pdf"
                pdf_path = os.path.join(tmpdir, pdf_filename)

                doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
                flowables = _build_payslip_flowables(r, month_year, styles)
                doc.build(flowables)

                zipf.write(pdf_path, arcname=pdf_filename)
