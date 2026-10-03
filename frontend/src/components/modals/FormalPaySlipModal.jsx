import React, { useRef } from 'react';
import { Printer, X, Building2, CheckCircle2, ShieldCheck } from 'lucide-react';

export default function FormalPaySlipModal({ isOpen, onClose, staff, currentMonth }) {
  if (!isOpen || !staff) return null;

  // Convert numbers to words (Indian numbering system)
  function numberToWordsINR(amount) {
    const num = Math.round(Number(amount) || 0);
    if (num === 0) return 'Zero Rupees Only';

    const a = [
      '', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ',
      'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ',
      'Eighteen ', 'Nineteen '
    ];
    const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];

    function inWords(n) {
      if ((n = n.toString()).length > 9) return 'overflow';
      const nArray = ('000000000' + n).substr(-9).match(/^(\d{2})(\d{2})(\d{2})(\d{1})(\d{2})$/);
      if (!nArray) return '';
      let str = '';
      str += nArray[1] != 0 ? (a[Number(nArray[1])] || b[nArray[1][0]] + ' ' + a[nArray[1][1]]) + 'Crore ' : '';
      str += nArray[2] != 0 ? (a[Number(nArray[2])] || b[nArray[2][0]] + ' ' + a[nArray[2][1]]) + 'Lakh ' : '';
      str += nArray[3] != 0 ? (a[Number(nArray[3])] || b[nArray[3][0]] + ' ' + a[nArray[3][1]]) + 'Thousand ' : '';
      str += nArray[4] != 0 ? (a[Number(nArray[4])] || b[nArray[4][0]] + ' ' + a[nArray[4][1]]) + 'Hundred ' : '';
      str +=
        nArray[5] != 0
          ? (str != '' ? 'and ' : '') +
            (a[Number(nArray[5])] || b[nArray[5][0]] + ' ' + a[nArray[5][1]])
          : '';
      return str.trim();
    }

    return 'Rupees ' + inWords(num) + ' Only';
  }

  const basic = Math.round((staff.gross_salary || 0) * 0.5);
  const da = Math.round((staff.gross_salary || 0) * 0.2);
  const hra = Math.round((staff.gross_salary || 0) * 0.2);
  const allowance = Math.max(0, Math.round(staff.gross_salary || 0) - basic - da - hra);

  const pf = Math.round(staff.pf_deduction || 0);
  const esi = Math.round(staff.esi_deduction || 0);
  const bus = Math.round(staff.bus_fee || 0);
  const mess = Math.round(staff.mess_fee || 0);
  const hostel = Math.round(staff.hostel_fee || 0);
  const other = Math.round(staff.other_deductions || 0);
  const totalDeductions = pf + esi + bus + mess + hostel + other;
  const netPay = Math.round(staff.net_salary || Math.max(0, (staff.gross_salary || 0) - totalDeductions));

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="react-modal-overlay">
      <div
        className="react-modal-card"
        style={{
          width: '840px',
          maxHeight: '94vh',
          background: 'white',
          borderRadius: '16px'
        }}
      >
        {/* Actions Bar (Screen Only) */}
        <div
          className="no-print"
          style={{
            padding: '12px 24px',
            borderBottom: '1px solid #e2e8f0',
            background: '#f8fafc',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <div style={{ fontSize: '0.86rem', fontWeight: 800, color: '#1e3a8a' }}>
            Official RVS University Pay Slip Preview
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-pill btn-primary" onClick={handlePrint}>
              <Printer size={15} />
              <span>Print Slip</span>
            </button>
            <button className="modal-close-btn" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Printable Pay Slip Container */}
        <div
          id="printable-slip"
          style={{
            padding: '36px 40px',
            overflowY: 'auto',
            color: '#0f172a',
            fontFamily: 'Inter, sans-serif'
          }}
        >
          {/* Header */}
          <div
            style={{
              textAlign: 'center',
              borderBottom: '2px solid #1e3a8a',
              paddingBottom: '16px',
              marginBottom: '20px'
            }}
          >
            <div style={{ fontSize: '1.4rem', fontWeight: 900, color: '#1e3a8a', letterSpacing: '-0.02em' }}>
              RVS EDUCATIONAL TRUST
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#0f172a' }}>
              RVS UNIVERSITY & GROUP OF INSTITUTIONS
            </div>
            <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
              RVS Nagar, Tirupati Road, Chittoor - 517127, Andhra Pradesh
            </div>
            <div
              style={{
                display: 'inline-block',
                marginTop: '10px',
                padding: '4px 18px',
                borderRadius: '9999px',
                background: '#eff6ff',
                color: '#1e3a8a',
                fontSize: '0.82rem',
                fontWeight: 800,
                border: '1px solid #bfdbfe'
              }}
            >
              SALARY PAYSLIP FOR {currentMonth ? currentMonth.toUpperCase() : 'CURRENT MONTH'}
            </div>
          </div>

          {/* Employee & Attendance Meta Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px 24px',
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              padding: '16px 20px',
              marginBottom: '22px',
              fontSize: '0.82rem'
            }}
          >
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Employee Code:</span>{' '}
              <strong style={{ color: '#1e3a8a' }}>{staff.emp_code}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Designation:</span>{' '}
              <strong>{staff.designation || 'Faculty / Staff'}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Full Name:</span>{' '}
              <strong style={{ fontSize: '0.9rem' }}>{staff.name}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Department:</span>{' '}
              <strong>{staff.department || 'General'}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Bank Account:</span>{' '}
              <strong>{staff.bank_account || 'N/A (Check Accounts)'}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Bank IFSC:</span>{' '}
              <strong>{staff.ifsc_code || 'N/A'}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Payable Days:</span>{' '}
              <strong style={{ color: '#047857' }}>{staff.payable_days || staff.month_days || 30} Days</strong>
            </div>
            <div>
              <span style={{ color: '#64748b', fontWeight: 600 }}>Loss of Pay (LOP):</span>{' '}
              <strong style={{ color: staff.lop_days > 0 ? '#e11d48' : '#64748b' }}>
                {staff.lop_days || 0} Days
              </strong>
            </div>
          </div>

          {/* Earnings vs Deductions Dual Table */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '20px',
              marginBottom: '20px'
            }}
          >
            {/* Earnings Column */}
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', overflow: 'hidden' }}>
              <div
                style={{
                  background: '#eff6ff',
                  padding: '10px 16px',
                  fontWeight: 800,
                  fontSize: '0.84rem',
                  color: '#1e3a8a',
                  borderBottom: '1px solid #dbeafe'
                }}
              >
                EARNINGS
              </div>
              <table style={{ width: '100%', fontSize: '0.82rem', borderCollapse: 'collapse' }}>
                <tbody>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Basic Pay</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{basic.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Dearness Allowance (DA)</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{da.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>House Rent Allowance (HRA)</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{hra.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Special / Conveyance Allowance</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{allowance.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ background: '#f8fafc', fontWeight: 800 }}>
                    <td style={{ padding: '10px 14px', color: '#1e3a8a' }}>GROSS EARNINGS</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: '#1e3a8a' }}>
                      ₹{Math.round(staff.gross_salary || 0).toLocaleString('en-IN')}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Deductions Column */}
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', overflow: 'hidden' }}>
              <div
                style={{
                  background: '#fff1f2',
                  padding: '10px 16px',
                  fontWeight: 800,
                  fontSize: '0.84rem',
                  color: '#9f1239',
                  borderBottom: '1px solid #ffe4e6'
                }}
              >
                DEDUCTIONS
              </div>
              <table style={{ width: '100%', fontSize: '0.82rem', borderCollapse: 'collapse' }}>
                <tbody>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Provident Fund (PF)</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{pf.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>ESI / Health Insurance</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{esi.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Transport / Bus Fee</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{bus.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Mess & Hostel / EB</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{(mess + hostel).toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 14px' }}>Other Adjustments</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600 }}>
                      ₹{other.toLocaleString('en-IN')}
                    </td>
                  </tr>
                  <tr style={{ background: '#fff1f2', fontWeight: 800 }}>
                    <td style={{ padding: '10px 14px', color: '#9f1239' }}>TOTAL DEDUCTIONS</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: '#9f1239' }}>
                      ₹{totalDeductions.toLocaleString('en-IN')}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Net Salary Highlight Box */}
          <div
            style={{
              background: '#ecfdf5',
              border: '2px solid #a7f3d0',
              borderRadius: '12px',
              padding: '16px 24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '16px'
            }}
          >
            <div>
              <div style={{ fontSize: '0.76rem', fontWeight: 800, textTransform: 'uppercase', color: '#065f46' }}>
                NET SALARY DISBURSABLE
              </div>
              <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#047857', marginTop: '2px' }}>
                {numberToWordsINR(netPay)}
              </div>
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 900, color: '#065f46' }}>
              ₹{netPay.toLocaleString('en-IN')}
            </div>
          </div>

          {/* Signatures Footer */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 1fr',
              textAlign: 'center',
              marginTop: '50px',
              paddingTop: '20px',
              fontSize: '0.8rem',
              color: '#475569'
            }}
          >
            <div>
              <div style={{ borderTop: '1px dashed #94a3b8', width: '160px', margin: '0 auto 8px auto' }} />
              <strong>Prepared By (HR)</strong>
            </div>
            <div>
              <div style={{ borderTop: '1px dashed #94a3b8', width: '160px', margin: '0 auto 8px auto' }} />
              <strong>Checked By (Accounts)</strong>
            </div>
            <div>
              <div style={{ borderTop: '1px dashed #94a3b8', width: '160px', margin: '0 auto 8px auto' }} />
              <strong>Approved By (Principal / Registrar)</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
