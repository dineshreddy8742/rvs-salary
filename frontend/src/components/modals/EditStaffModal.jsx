import React, { useState, useEffect } from 'react';
import { X, User, Calendar, DollarSign, CreditCard, Trash2, Save } from 'lucide-react';
import { updateEmployeePackage, deleteEmployee } from '../../api';

export default function EditStaffModal({
  isOpen,
  employee,
  month,
  onClose,
  onSaved,
  onDeleted,
}) {
  const [formData, setFormData] = useState({
    name: '',
    category: 'Teaching',
    designation: '',
    department: '',
    attendance_policy: 'standard',
    bio_days: 25,
    holidays: 4,
    cl: 0,
    od: 0,
    pay_days: 30,
    base_salary: 0,
    arrears: 0,
    pt: 200,
    wf: 75,
    epf: 0,
    it: 0,
    bus: 0,
    hostel: 0,
    mess: 0,
    other: 0,
    bank_name: 'PNB',
    account_no: '',
    ifsc_code: 'PUNB0401700',
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (employee) {
      setFormData({
        name: employee.name || '',
        category: employee.category || 'Teaching',
        designation: employee.designation || '',
        department: employee.department || '',
        attendance_policy: employee.attendance_policy || 'standard',
        bio_days: employee.present_days ?? employee.biometric_days ?? 25,
        holidays: employee.holiday ?? 4,
        cl: employee.cl_days ?? employee.availed_leaves ?? 0,
        od: employee.od_days ?? employee.sv_od ?? 0,
        pay_days: employee.total_pay_days ?? 30,
        base_salary: employee.base_salary || 0,
        arrears: employee.arrears || 0,
        pt: employee.pt_deduction ?? 200,
        wf: employee.wf_deduction ?? (employee.category === 'Teaching' ? 75 : 30),
        epf: employee.epf_deduction || 0,
        it: employee.it_deduction || 0,
        bus: employee.bus_deduction || 0,
        hostel: employee.hostel_eb_deduction || 0,
        mess: employee.mess_deduction || 0,
        other: employee.other_deductions || 0,
        bank_name: employee.bank_name || 'PNB',
        account_no: employee.account_no && employee.account_no !== 'Pending' ? employee.account_no : '',
        ifsc_code: employee.ifsc_code || 'PUNB0401700',
      });
    }
  }, [employee]);

  if (!isOpen || !employee) return null;

  const monthDays = employee.month_days || 31;
  const lopDays = Math.max(0, Math.round((monthDays - formData.pay_days) * 10) / 10);

  // Live Gross Calculation
  let gross = 0;
  if (formData.base_salary > 0 && formData.pay_days > 0 && monthDays > 0) {
    if (formData.category.toLowerCase().includes('teaching') && !formData.category.toLowerCase().includes('non')) {
      const basic = Math.round(formData.base_salary / 1.5331);
      const earnedBasic = (basic / monthDays) * formData.pay_days;
      const da = Math.round(earnedBasic * 0.3731);
      const hra = Math.round(earnedBasic * 0.16);
      gross = Math.round(earnedBasic + da + hra + Number(formData.arrears));
    } else {
      gross = Math.ceil((formData.base_salary / monthDays) * formData.pay_days + Number(formData.arrears));
    }
  } else if (formData.arrears > 0) {
    gross = Number(formData.arrears);
  }

  // Total Deductions & Net
  const totalDeductions =
    Number(formData.pt) +
    Number(formData.wf) +
    Number(formData.epf) +
    Number(formData.it) +
    Number(formData.bus) +
    Number(formData.hostel) +
    Number(formData.mess) +
    Number(formData.other);

  const netSalary = Math.max(0, gross - totalDeductions);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await updateEmployeePackage({
        emp_code: employee.emp_code,
        month_year: month,
        name: formData.name,
        category: formData.category,
        designation: formData.designation,
        department: formData.department,
        attendance_policy: formData.attendance_policy,
        biometric_days: parseFloat(formData.bio_days),
        holiday: parseFloat(formData.holidays),
        availed_leaves: parseFloat(formData.cl),
        sv_od: parseFloat(formData.od),
        total_pay_days: parseFloat(formData.pay_days),
        base_salary: parseFloat(formData.base_salary),
        arrears: parseFloat(formData.arrears),
        pt_deduction: parseFloat(formData.pt),
        wf_deduction: parseFloat(formData.wf),
        epf_deduction: parseFloat(formData.epf),
        it_deduction: parseFloat(formData.it),
        bus_deduction: parseFloat(formData.bus),
        hostel_eb_deduction: parseFloat(formData.hostel),
        mess_deduction: parseFloat(formData.mess),
        other_deductions: parseFloat(formData.other),
        bank_name: formData.bank_name,
        account_no: formData.account_no,
        ifsc_code: formData.ifsc_code,
      });
      onSaved();
      onClose();
    } catch (err) {
      alert(`Error saving package: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to permanently delete staff member "${formData.name}" (${employee.emp_code})?`)) return;
    try {
      await deleteEmployee(employee.emp_code);
      onDeleted();
      onClose();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  return (
    <div className="react-modal-overlay" onClick={onClose}>
      <div
        className="react-modal-card"
        style={{ width: '840px', maxWidth: '94vw' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <div
              style={{
                fontSize: '0.68rem',
                fontWeight: 800,
                textTransform: 'uppercase',
                color: '#4338ca',
                background: '#e0e7ff',
                padding: '2px 8px',
                borderRadius: '9999px',
                display: 'inline-block',
                marginBottom: '4px',
              }}
            >
              Unified 360° Master Editor
            </div>
            <h3 className="modal-title">Edit Staff Profile: {employee.name}</h3>
            <p style={{ margin: 0, fontSize: '0.78rem', color: '#64748b' }}>
              Emp Code: <strong>{employee.emp_code}</strong> | Dept: <strong>{formData.department || 'General'}</strong> | Month: <strong>{month}</strong>
            </p>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSave} className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Section 1: Profile & Designation */}
          <div style={{ background: '#f8fafc', padding: '14px 16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', fontWeight: 800, fontSize: '0.85rem', color: '#1e3a8a' }}>
              <User size={16} /> 1. Staff Profile & Classification
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Full Name:</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                  required
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Category:</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                >
                  <option value="Teaching">Teaching Faculty</option>
                  <option value="Non-Teaching">Non-Teaching Staff</option>
                  <option value="Support">Support & Attenders</option>
                  <option value="Transport">Transport</option>
                  <option value="Management">Management</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Designation:</label>
                <input
                  type="text"
                  value={formData.designation}
                  onChange={(e) => setFormData({ ...formData, designation: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Department:</label>
                <input
                  type="text"
                  value={formData.department}
                  onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                />
              </div>
            </div>
          </div>

          {/* Section 2: Attendance Days & LOP */}
          <div style={{ background: '#f8fafc', padding: '14px 16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, fontSize: '0.85rem', color: '#1e3a8a' }}>
                <Calendar size={16} /> 2. Biometric Attendance Days ({monthDays} Month Days)
              </div>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 800,
                  padding: '3px 9px',
                  borderRadius: '9999px',
                  background: lopDays > 0 ? '#fee2e2' : '#ecfdf5',
                  color: lopDays > 0 ? '#dc2626' : '#059669',
                }}
              >
                {lopDays > 0 ? `⚠️ ${lopDays}d Loss of Pay (LOP)` : '✓ Full Attendance'}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Biometric Punch:</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.bio_days}
                  onChange={(e) => setFormData({ ...formData, bio_days: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700 }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Holidays / Sundays:</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.holidays}
                  onChange={(e) => setFormData({ ...formData, holidays: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700 }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>Casual Leaves (CL):</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.cl}
                  onChange={(e) => setFormData({ ...formData, cl: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700, color: '#9333ea' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: '4px' }}>On-Duty (OD):</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.od}
                  onChange={(e) => setFormData({ ...formData, od: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700, color: '#0d9488' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.74rem', fontWeight: 800, color: '#15803d', display: 'block', marginBottom: '4px' }}>Eligible Pay Days:</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.pay_days}
                  onChange={(e) => setFormData({ ...formData, pay_days: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '6px', border: '1.5px solid #16a34a', textAlign: 'right', fontWeight: 800, color: '#15803d', background: '#f0fdf4' }}
                />
              </div>
            </div>
          </div>

          {/* Section 3: Salary & Deductions */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            {/* Earnings */}
            <div style={{ background: '#f8fafc', padding: '14px 16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', fontWeight: 800, fontSize: '0.85rem', color: '#1e3a8a' }}>
                <DollarSign size={16} /> 3. Salary & Earnings
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600 }}>Monthly Base Package (₹):</label>
                  <input
                    type="number"
                    value={formData.base_salary}
                    onChange={(e) => setFormData({ ...formData, base_salary: e.target.value })}
                    style={{ width: '120px', padding: '5px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700 }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600 }}>Arrears / Incentive (₹):</label>
                  <input
                    type="number"
                    value={formData.arrears}
                    onChange={(e) => setFormData({ ...formData, arrears: e.target.value })}
                    style={{ width: '120px', padding: '5px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', textAlign: 'right', fontWeight: 700 }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 800, color: '#4338ca' }}>Earned Gross Pay:</span>
                  <span style={{ fontSize: '1.05rem', fontWeight: 900, color: '#4338ca' }}>₹{gross.toLocaleString('en-IN')}</span>
                </div>
              </div>
            </div>

            {/* Deductions & Net */}
            <div style={{ background: '#f8fafc', padding: '14px 16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, fontSize: '0.85rem', color: '#1e3a8a' }}>
                  <CreditCard size={16} /> 4. Deductions & Net Pay
                </div>
                <span style={{ fontSize: '0.78rem', fontWeight: 800, color: '#b45309' }}>
                  Total: ₹{totalDeductions.toLocaleString('en-IN')}
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px', marginBottom: '10px' }}>
                <div>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', display: 'block' }}>PT (₹200)</span>
                  <input
                    type="number"
                    value={formData.pt}
                    onChange={(e) => setFormData({ ...formData, pt: e.target.value })}
                    style={{ width: '100%', padding: '4px', textAlign: 'right', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.78rem' }}
                  />
                </div>
                <div>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', display: 'block' }}>WF (₹75)</span>
                  <input
                    type="number"
                    value={formData.wf}
                    onChange={(e) => setFormData({ ...formData, wf: e.target.value })}
                    style={{ width: '100%', padding: '4px', textAlign: 'right', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.78rem' }}
                  />
                </div>
                <div>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', display: 'block' }}>Bus Fee</span>
                  <input
                    type="number"
                    value={formData.bus}
                    onChange={(e) => setFormData({ ...formData, bus: e.target.value })}
                    style={{ width: '100%', padding: '4px', textAlign: 'right', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.78rem' }}
                  />
                </div>
                <div>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', display: 'block' }}>Hostel / EB</span>
                  <input
                    type="number"
                    value={formData.hostel}
                    onChange={(e) => setFormData({ ...formData, hostel: e.target.value })}
                    style={{ width: '100%', padding: '4px', textAlign: 'right', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.78rem' }}
                  />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.84rem', fontWeight: 800, color: '#15803d' }}>Final Net Pay:</span>
                <span style={{ fontSize: '1.2rem', fontWeight: 900, color: '#15803d' }}>₹{netSalary.toLocaleString('en-IN')}</span>
              </div>
            </div>
          </div>

          {/* Footer Buttons */}
          <div className="modal-footer" style={{ margin: '-20px -24px -20px -24px', padding: '14px 24px' }}>
            <button
              type="button"
              onClick={handleDelete}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 14px',
                borderRadius: '8px',
                border: '1px solid #fecaca',
                background: '#fef2f2',
                color: '#dc2626',
                fontWeight: 700,
                fontSize: '0.8rem',
                cursor: 'pointer',
                marginRight: 'auto',
              }}
            >
              <Trash2 size={14} /> Delete Staff
            </button>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '7px 16px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                background: 'white',
                fontWeight: 600,
                fontSize: '0.82rem',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 18px',
                borderRadius: '8px',
                border: 'none',
                background: '#2563eb',
                color: 'white',
                fontWeight: 700,
                fontSize: '0.82rem',
                cursor: 'pointer',
              }}
            >
              <Save size={14} /> {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
