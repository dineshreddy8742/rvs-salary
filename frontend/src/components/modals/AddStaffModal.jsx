import React, { useState } from 'react';
import {
  UserPlus,
  FileSpreadsheet,
  Trash2,
  X,
  Search,
  CheckCircle,
  AlertCircle,
  Upload,
  Crown,
  Building,
  Briefcase
} from 'lucide-react';
import * as api from '../../api';

export default function AddStaffModal({
  isOpen,
  onClose,
  allStaff = [],
  currentMonth,
  onSuccess
}) {
  const [activeTab, setActiveTab] = useState('single'); // 'single' | 'bulk' | 'manage'

  // Single Staff Form State
  const [singleForm, setSingleForm] = useState({
    emp_code: '',
    name: '',
    department: 'Administration',
    designation: 'Assistant Professor',
    category: 'Teaching',
    package_amount: 30000,
    salary_policy: 'Standard Biometric'
  });
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleMsg, setSingleMsg] = useState(null);

  // Bulk Import State
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkRows, setBulkRows] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkMsg, setBulkMsg] = useState(null);

  // Manage / Delete State
  const [manageSearch, setManageSearch] = useState('');
  const [selectedDeleteCodes, setSelectedDeleteCodes] = useState(new Set());
  const [deleteLoading, setDeleteLoading] = useState(false);

  if (!isOpen) return null;

  // Single staff submit
  const handleSingleSubmit = async (e) => {
    e.preventDefault();
    if (!singleForm.emp_code.trim() || !singleForm.name.trim()) {
      setSingleMsg({ type: 'error', text: 'Emp Code and Full Name are mandatory.' });
      return;
    }

    setSingleLoading(true);
    setSingleMsg(null);
    try {
      await api.addEmployee({
        emp_code: singleForm.emp_code.trim(),
        name: singleForm.name.trim(),
        department: singleForm.department,
        designation: singleForm.designation,
        category: singleForm.category,
        package_amount: parseFloat(singleForm.package_amount) || 0,
        salary_policy: singleForm.salary_policy,
        current_month: currentMonth
      });
      setSingleMsg({ type: 'success', text: `Staff ${singleForm.name} (${singleForm.emp_code}) added successfully!` });
      setSingleForm({
        emp_code: '',
        name: '',
        department: 'Administration',
        designation: 'Staff',
        category: 'Teaching',
        package_amount: 30000,
        salary_policy: 'Standard Biometric'
      });
      onSuccess?.();
    } catch (err) {
      setSingleMsg({ type: 'error', text: err.message || 'Failed to add staff member.' });
    } finally {
      setSingleLoading(false);
    }
  };

  // Bulk File Selection & CSV Parse
  const handleBulkFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBulkFile(file);
    setBulkMsg(null);

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const text = evt.target.result;
        const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
        if (lines.length <= 1) {
          setBulkMsg({ type: 'error', text: 'File is empty or contains only headers.' });
          return;
        }

        const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
        const codeIdx = headers.findIndex((h) => h.includes('code') || h.includes('id') || h.includes('emp'));
        const nameIdx = headers.findIndex((h) => h.includes('name'));
        const deptIdx = headers.findIndex((h) => h.includes('dept') || h.includes('department'));
        const desigIdx = headers.findIndex((h) => h.includes('desig'));
        const catIdx = headers.findIndex((h) => h.includes('cat'));
        const packIdx = headers.findIndex((h) => h.includes('sal') || h.includes('pack') || h.includes('rate'));

        const parsed = [];
        for (let i = 1; i < lines.length; i++) {
          const cols = lines[i].split(',').map((c) => c.trim().replace(/^["']|["']$/g, ''));
          const code = codeIdx >= 0 ? cols[codeIdx] : cols[0];
          const name = nameIdx >= 0 ? cols[nameIdx] : cols[1];
          if (!code || !name) continue;

          parsed.push({
            emp_code: code,
            name: name,
            department: deptIdx >= 0 && cols[deptIdx] ? cols[deptIdx] : 'General',
            designation: desigIdx >= 0 && cols[desigIdx] ? cols[desigIdx] : 'Staff',
            category: catIdx >= 0 && cols[catIdx] ? cols[catIdx] : 'Non-Teaching',
            package_amount: packIdx >= 0 && !isNaN(parseFloat(cols[packIdx])) ? parseFloat(cols[packIdx]) : 0,
            salary_policy: 'Standard Biometric'
          });
        }

        setBulkRows(parsed);
        setBulkMsg({ type: 'info', text: `Parsed ${parsed.length} staff records ready for import.` });
      } catch (err) {
        setBulkMsg({ type: 'error', text: 'Failed to parse CSV: ' + err.message });
      }
    };
    reader.readAsText(file);
  };

  // Bulk Import Submit
  const handleBulkSubmit = async () => {
    if (bulkRows.length === 0) return;
    setBulkLoading(true);
    setBulkMsg(null);
    try {
      const res = await api.bulkStaffImport(bulkRows);
      setBulkMsg({
        type: 'success',
        text: `Successfully imported ${res.imported_count || bulkRows.length} staff members!`
      });
      setBulkRows([]);
      setBulkFile(null);
      onSuccess?.();
    } catch (err) {
      setBulkMsg({ type: 'error', text: err.message || 'Bulk import failed.' });
    } finally {
      setBulkLoading(false);
    }
  };

  // Manage / Delete Handlers
  const filteredStaff = allStaff.filter((s) => {
    if (!manageSearch.trim()) return true;
    const q = manageSearch.toLowerCase().trim();
    return (
      (s.emp_code || '').toLowerCase().includes(q) ||
      (s.name || '').toLowerCase().includes(q) ||
      (s.department || '').toLowerCase().includes(q)
    );
  });

  const toggleDeleteSelect = (code) => {
    setSelectedDeleteCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const handleDeleteSelected = async () => {
    if (selectedDeleteCodes.size === 0) return;
    if (!confirm(`Are you sure you want to delete ${selectedDeleteCodes.size} selected staff members?`)) {
      return;
    }

    setDeleteLoading(true);
    try {
      await api.deleteManualStaff(Array.from(selectedDeleteCodes));
      setSelectedDeleteCodes(new Set());
      onSuccess?.();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDeleteAllUploaded = async () => {
    if (!confirm('⚠️ Are you sure you want to delete ALL uploaded/custom staff members? Base biometric roster will be preserved.')) {
      return;
    }
    setDeleteLoading(true);
    try {
      await api.deleteManualStaff(null); // delete_all: true
      onSuccess?.();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className="react-modal-overlay">
      <div className="react-modal-card" style={{ width: '920px', height: '680px' }}>
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                background: '#eff6ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#2563eb'
              }}
            >
              <UserPlus size={20} />
            </div>
            <div>
              <div className="modal-title">Staff Enrollment & Management</div>
              <div style={{ fontSize: '0.74rem', color: '#64748b' }}>
                Enroll single staff, bulk import via Excel/CSV, or manage enrolled roster
              </div>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid #e2e8f0',
            background: '#f8fafc',
            padding: '0 24px'
          }}
        >
          <button
            onClick={() => setActiveTab('single')}
            style={{
              padding: '12px 18px',
              border: 'none',
              background: 'transparent',
              fontSize: '0.84rem',
              fontWeight: 700,
              color: activeTab === 'single' ? '#2563eb' : '#64748b',
              borderBottom: activeTab === 'single' ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <UserPlus size={15} />
            <span>Single Staff Entry</span>
          </button>

          <button
            onClick={() => setActiveTab('bulk')}
            style={{
              padding: '12px 18px',
              border: 'none',
              background: 'transparent',
              fontSize: '0.84rem',
              fontWeight: 700,
              color: activeTab === 'bulk' ? '#2563eb' : '#64748b',
              borderBottom: activeTab === 'bulk' ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <FileSpreadsheet size={15} />
            <span>Bulk CSV / Excel Import</span>
          </button>

          <button
            onClick={() => setActiveTab('manage')}
            style={{
              padding: '12px 18px',
              border: 'none',
              background: 'transparent',
              fontSize: '0.84rem',
              fontWeight: 700,
              color: activeTab === 'manage' ? '#2563eb' : '#64748b',
              borderBottom: activeTab === 'manage' ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Trash2 size={15} />
            <span>Manage / Delete Staff ({allStaff.length})</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body" style={{ padding: '24px' }}>
          {/* TAB 1: Single Staff Entry */}
          {activeTab === 'single' && (
            <form onSubmit={handleSingleSubmit} style={{ maxWidth: '640px', margin: '0 auto' }}>
              {singleMsg && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: '8px',
                    marginBottom: '16px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    background: singleMsg.type === 'success' ? '#dcfce7' : '#fee2e2',
                    color: singleMsg.type === 'success' ? '#166534' : '#991b1b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  {singleMsg.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  <span>{singleMsg.text}</span>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    EMPLOYEE CODE *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. 1095, T_042"
                    value={singleForm.emp_code}
                    onChange={(e) => setSingleForm({ ...singleForm, emp_code: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem',
                      fontWeight: 700
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    FULL NAME *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Dr. John Doe"
                    value={singleForm.name}
                    onChange={(e) => setSingleForm({ ...singleForm, name: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem',
                      fontWeight: 600
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    DEPARTMENT
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Computer Science, Administration"
                    value={singleForm.department}
                    onChange={(e) => setSingleForm({ ...singleForm, department: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    DESIGNATION
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Associate Professor, Accountant"
                    value={singleForm.designation}
                    onChange={(e) => setSingleForm({ ...singleForm, designation: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    CATEGORY
                  </label>
                  <select
                    value={singleForm.category}
                    onChange={(e) => setSingleForm({ ...singleForm, category: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem',
                      background: 'white'
                    }}
                  >
                    <option value="Teaching">🎓 Teaching Faculty</option>
                    <option value="Non-Teaching">👔 Non-Teaching Staff</option>
                    <option value="Support">🧹 Support & Attenders</option>
                    <option value="Transport">🚌 Transport & Drivers</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    BASE PACKAGE RATE (₹/MONTH)
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="500"
                    placeholder="e.g. 35000"
                    value={singleForm.package_amount}
                    onChange={(e) => setSingleForm({ ...singleForm, package_amount: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem',
                      fontWeight: 700
                    }}
                  />
                </div>

                <div style={{ gridColumn: 'span 2' }}>
                  <label style={{ display: 'block', fontSize: '0.74rem', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>
                    SALARY & ATTENDANCE POLICY
                  </label>
                  <select
                    value={singleForm.salary_policy}
                    onChange={(e) => setSingleForm({ ...singleForm, salary_policy: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.86rem',
                      background: 'white'
                    }}
                  >
                    <option value="Standard Biometric">Standard Biometric (Pro-rated per payable days)</option>
                    <option value="👑 Full Pay (VIP)">👑 Full Pay (VIP / Fixed Monthly Payout)</option>
                  </select>
                </div>
              </div>

              <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="submit"
                  disabled={singleLoading}
                  className="btn-pill btn-primary"
                  style={{ padding: '10px 24px', fontSize: '0.88rem' }}
                >
                  <UserPlus size={16} />
                  <span>{singleLoading ? 'Enrolling...' : 'Enroll Staff Member'}</span>
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: Bulk CSV / Excel Import */}
          {activeTab === 'bulk' && (
            <div style={{ maxWidth: '780px', margin: '0 auto' }}>
              <div
                style={{
                  border: '2px dashed #cbd5e1',
                  borderRadius: '12px',
                  padding: '30px',
                  textAlign: 'center',
                  background: '#f8fafc',
                  marginBottom: '20px'
                }}
              >
                <Upload size={32} color="#2563eb" style={{ margin: '0 auto 10px auto' }} />
                <div style={{ fontWeight: 700, fontSize: '0.94rem', color: '#1e293b', marginBottom: '4px' }}>
                  Upload CSV or Excel with Staff Details
                </div>
                <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '14px' }}>
                  Supported headers: <code>emp_code</code>, <code>name</code>, <code>department</code>, <code>designation</code>, <code>category</code>, <code>package_amount</code>
                </div>
                <input
                  type="file"
                  id="bulkFileInput"
                  accept=".csv,.txt"
                  onChange={handleBulkFileChange}
                  style={{ display: 'none' }}
                />
                <button
                  type="button"
                  className="btn-pill btn-primary"
                  onClick={() => document.getElementById('bulkFileInput')?.click()}
                >
                  <FileSpreadsheet size={15} />
                  <span>Choose CSV File</span>
                </button>
              </div>

              {bulkMsg && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: '8px',
                    marginBottom: '16px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    background: bulkMsg.type === 'success' ? '#dcfce7' : bulkMsg.type === 'info' ? '#eff6ff' : '#fee2e2',
                    color: bulkMsg.type === 'success' ? '#166534' : bulkMsg.type === 'info' ? '#1d4ed8' : '#991b1b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  {bulkMsg.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  <span>{bulkMsg.text}</span>
                </div>
              )}

              {bulkRows.length > 0 && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.84rem', color: '#1e293b' }}>
                      Preview: {bulkRows.length} staff to import
                    </span>
                    <button
                      className="btn-pill btn-upload"
                      onClick={handleBulkSubmit}
                      disabled={bulkLoading}
                    >
                      <CheckCircle size={15} />
                      <span>{bulkLoading ? 'Importing...' : `Import All ${bulkRows.length} Staff`}</span>
                    </button>
                  </div>
                  <div style={{ maxHeight: '240px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                    <table className="master-table">
                      <thead>
                        <tr>
                          <th>Emp Code</th>
                          <th>Full Name</th>
                          <th>Department</th>
                          <th>Category</th>
                          <th style={{ textAlign: 'right' }}>Package</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bulkRows.slice(0, 50).map((r, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 700 }}>{r.emp_code}</td>
                            <td>{r.name}</td>
                            <td>{r.department}</td>
                            <td>{r.category}</td>
                            <td style={{ textAlign: 'right' }}>₹{r.package_amount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Manage / Delete Staff */}
          {activeTab === 'manage' && (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Filter and Bulk Delete Action Bar */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '14px',
                  gap: '12px'
                }}
              >
                <div className="search-box" style={{ width: '280px' }}>
                  <Search size={15} color="#94a3b8" />
                  <input
                    type="text"
                    className="search-input"
                    placeholder="Search enrolled staff..."
                    value={manageSearch}
                    onChange={(e) => setManageSearch(e.target.value)}
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="btn-pill"
                    onClick={handleDeleteSelected}
                    disabled={selectedDeleteCodes.size === 0 || deleteLoading}
                    style={{
                      background: selectedDeleteCodes.size > 0 ? '#fee2e2' : '#f1f5f9',
                      color: selectedDeleteCodes.size > 0 ? '#b91c1c' : '#94a3b8',
                      border: '1px solid #fca5a5'
                    }}
                  >
                    <Trash2 size={14} />
                    <span>Delete Selected ({selectedDeleteCodes.size})</span>
                  </button>

                  <button
                    className="btn-pill"
                    onClick={handleDeleteAllUploaded}
                    disabled={deleteLoading}
                    style={{
                      background: '#fff1f2',
                      color: '#e11d48',
                      border: '1px solid #fecdd3'
                    }}
                  >
                    <span>⚠️ Delete All Uploaded Staff</span>
                  </button>
                </div>
              </div>

              {/* Staff List Table */}
              <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '10px' }}>
                <table className="master-table">
                  <thead>
                    <tr>
                      <th style={{ width: '36px', textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={
                            filteredStaff.length > 0 &&
                            filteredStaff.every((s) => selectedDeleteCodes.has(s.emp_code))
                          }
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedDeleteCodes(new Set(filteredStaff.map((s) => s.emp_code)));
                            } else {
                              setSelectedDeleteCodes(new Set());
                            }
                          }}
                        />
                      </th>
                      <th>Emp Code</th>
                      <th>Full Name</th>
                      <th>Designation</th>
                      <th>Department</th>
                      <th>Category</th>
                      <th>Origin</th>
                      <th style={{ textAlign: 'center' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStaff.slice(0, 100).map((s) => {
                      const isSel = selectedDeleteCodes.has(s.emp_code);
                      const isManual = s.origin === 'manual';
                      return (
                        <tr key={s.emp_code} style={{ background: isSel ? '#eff6ff' : undefined }}>
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={isSel}
                              onChange={() => toggleDeleteSelect(s.emp_code)}
                            />
                          </td>
                          <td style={{ fontWeight: 800, color: '#1e3a8a' }}>{s.emp_code}</td>
                          <td style={{ fontWeight: 700 }}>{s.name}</td>
                          <td style={{ color: '#64748b' }}>{s.designation || 'Staff'}</td>
                          <td>{s.department}</td>
                          <td>{s.category}</td>
                          <td>
                            <span
                              style={{
                                fontSize: '0.68rem',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontWeight: 700,
                                background: isManual ? '#fef3c7' : '#e0f2fe',
                                color: isManual ? '#92400e' : '#0369a1'
                              }}
                            >
                              {isManual ? 'Uploaded / Test' : 'Base Roster'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              onClick={() => {
                                setSelectedDeleteCodes(new Set([s.emp_code]));
                                handleDeleteSelected();
                              }}
                              className="btn-pill"
                              style={{
                                padding: '3px 8px',
                                background: '#fee2e2',
                                color: '#b91c1c',
                                border: '1px solid #fca5a5'
                              }}
                            >
                              <Trash2 size={12} />
                              <span>Delete</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
