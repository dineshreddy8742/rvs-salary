import React, { useState, useMemo } from 'react';
import {
  Search,
  Edit2,
  FileText,
  RotateCcw,
  Crown,
  AlertCircle,
  CheckCircle,
  Building,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Filter,
  CheckSquare,
  Square
} from 'lucide-react';

export default function StaffTable({
  records = [],
  dashboardMode = 'unified', // 'unified' | 'attendance' | 'salary'
  isSalaryUnlocked = false,
  searchQuery = '',
  onSearchChange,
  activeFilter = 'all',
  onOpenEdit,
  onOpenPaySlip,
  onRevertBiometric,
  onInlineUpdate, // (empCode, field, value)
  selectedCodes = new Set(),
  onToggleSelect,
  onToggleSelectAll
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [savingCell, setSavingCell] = useState(null); // 'empCode-field'

  // Filter records by search query and category/attention flags
  const filteredRecords = useMemo(() => {
    return records.filter((r) => {
      // 1. Text Search Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const code = String(r.emp_code || '').toLowerCase();
        const name = String(r.name || '').toLowerCase();
        const dept = String(r.department || '').toLowerCase();
        const desig = String(r.designation || '').toLowerCase();
        if (!code.includes(q) && !name.includes(q) && !dept.includes(q) && !desig.includes(q)) {
          return false;
        }
      }

      // 2. Category / Sidebar Filter
      if (activeFilter === 'teaching') {
        return (r.category || '').toLowerCase().includes('teach') && !(r.category || '').toLowerCase().includes('non');
      }
      if (activeFilter === 'non_teaching') {
        return (r.category || '').toLowerCase().includes('non-teach') || (r.category || '').toLowerCase().includes('non teach');
      }
      if (activeFilter === 'support') {
        return (r.category || '').toLowerCase().includes('support') || (r.category || '').toLowerCase().includes('attender');
      }
      if (activeFilter === 'transport') {
        return (r.category || '').toLowerCase().includes('transport') || (r.category || '').toLowerCase().includes('driver');
      }
      if (activeFilter === 'vip') {
        return r.is_fixed_salary || (r.salary_policy && r.salary_policy.includes('VIP')) || (r.salary_policy && r.salary_policy.includes('Full Pay'));
      }
      if (activeFilter === 'has_lop') {
        return Number(r.lop_days || 0) > 0;
      }
      if (activeFilter === 'attention') {
        return Number(r.lop_days || 0) > 0 || !r.bank_account || Number(r.total_deductions || 0) > 0;
      }
      if (activeFilter === 'missing_bank') {
        return !r.bank_account || r.bank_account.trim() === '';
      }
      if (activeFilter === 'has_deductions') {
        return Number(r.total_deductions || 0) > 0;
      }

      return true;
    });
  }, [records, searchQuery, activeFilter]);

  // Pagination calculation
  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / pageSize));
  const effectivePage = Math.min(currentPage, totalPages);
  const pagedRecords = useMemo(() => {
    if (pageSize === -1) return filteredRecords;
    const start = (effectivePage - 1) * pageSize;
    return filteredRecords.slice(start, start + pageSize);
  }, [filteredRecords, effectivePage, pageSize]);

  // Handle cell blur / edit
  const handleCellBlur = async (empCode, field, originalVal, newVal) => {
    const numNew = parseFloat(newVal);
    const numOrig = parseFloat(originalVal);
    if (isNaN(numNew) || numNew === numOrig) return;

    const cellKey = `${empCode}-${field}`;
    setSavingCell(cellKey);
    try {
      await onInlineUpdate(empCode, field, numNew);
    } finally {
      setTimeout(() => setSavingCell(null), 600);
    }
  };

  const isAllSelected = pagedRecords.length > 0 && pagedRecords.every((r) => selectedCodes.has(r.emp_code));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Controls Strip: Search + Filter status + Page controls */}
      <div className="table-controls-strip">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="search-box">
            <Search size={16} color="#94a3b8" />
            <input
              type="text"
              className="search-input"
              placeholder="Search by Emp Code, Name, Dept..."
              value={searchQuery}
              onChange={(e) => {
                onSearchChange(e.target.value);
                setCurrentPage(1);
              }}
            />
          </div>

          <span style={{ fontSize: '0.82rem', color: '#64748b', fontWeight: 600 }}>
            Showing {filteredRecords.length} staff {activeFilter !== 'all' ? `(Filtered: ${activeFilter})` : ''}
          </span>
        </div>

        {/* Pagination buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ fontSize: '0.76rem', color: '#64748b' }}>Per page:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.78rem',
                fontWeight: 600,
                color: '#334155'
              }}
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={-1}>All ({filteredRecords.length})</option>
            </select>
          </div>

          {pageSize !== -1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                className="btn-pill"
                style={{ padding: '5px 8px', background: 'white', border: '1px solid #cbd5e1' }}
                disabled={effectivePage <= 1}
                onClick={() => setCurrentPage(1)}
              >
                <ChevronsLeft size={14} />
              </button>
              <button
                className="btn-pill"
                style={{ padding: '5px 8px', background: 'white', border: '1px solid #cbd5e1' }}
                disabled={effectivePage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft size={14} />
              </button>
              <span style={{ fontSize: '0.8rem', fontWeight: 700, padding: '0 6px', color: '#334155' }}>
                Page {effectivePage} of {totalPages}
              </span>
              <button
                className="btn-pill"
                style={{ padding: '5px 8px', background: 'white', border: '1px solid #cbd5e1' }}
                disabled={effectivePage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              >
                <ChevronRight size={14} />
              </button>
              <button
                className="btn-pill"
                style={{ padding: '5px 8px', background: 'white', border: '1px solid #cbd5e1' }}
                disabled={effectivePage >= totalPages}
                onClick={() => setCurrentPage(totalPages)}
              >
                <ChevronsRight size={14} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main Table Scroll Container */}
      <div className="table-scroll-container">
        <table className="master-table">
          <thead>
            <tr>
              <th style={{ width: '36px', textAlign: 'center' }}>
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={() => onToggleSelectAll(pagedRecords.map((r) => r.emp_code))}
                  style={{ cursor: 'pointer' }}
                />
              </th>
              <th>Emp Code</th>
              <th>Full Name & Designation</th>
              <th>Department</th>
              <th>Category</th>

              {/* Attendance Columns (Unified or Attendance Mode) */}
              {(dashboardMode === 'unified' || dashboardMode === 'attendance') && (
                <>
                  <th style={{ textAlign: 'right' }}>Month Days</th>
                  <th style={{ textAlign: 'right' }}>Present</th>
                  <th style={{ textAlign: 'right' }}>WO</th>
                  <th style={{ textAlign: 'right' }}>Holidays</th>
                  <th style={{ textAlign: 'right' }}>CL (Casual)</th>
                  <th style={{ textAlign: 'right' }}>OD (On Duty)</th>
                  <th style={{ textAlign: 'right' }}>Payable Days</th>
                  <th style={{ textAlign: 'right' }}>LOP Days</th>
                </>
              )}

              {/* Salary Columns (Unified + Unlocked, or Salary Mode) */}
              {(dashboardMode === 'salary' || (dashboardMode === 'unified' && isSalaryUnlocked)) && (
                <>
                  <th style={{ textAlign: 'right' }}>Base Package</th>
                  <th style={{ textAlign: 'right' }}>Gross Pay</th>
                  <th style={{ textAlign: 'right' }}>PF / ESI</th>
                  <th style={{ textAlign: 'right' }}>Bus / Mess / EB</th>
                  <th style={{ textAlign: 'right' }}>Other Ded.</th>
                  <th style={{ textAlign: 'right', background: '#ecfdf5', color: '#065f46' }}>Net Payable</th>
                  <th>Bank A/C & IFSC</th>
                </>
              )}

              <th style={{ textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pagedRecords.length === 0 ? (
              <tr>
                <td colSpan={20} style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                  No staff records found matching your filters.
                </td>
              </tr>
            ) : (
              pagedRecords.map((r) => {
                const isSelected = selectedCodes.has(r.emp_code);
                const hasLop = Number(r.lop_days || 0) > 0;
                const isVip =
                  r.is_fixed_salary ||
                  (r.salary_policy && (r.salary_policy.includes('VIP') || r.salary_policy.includes('Full Pay')));

                return (
                  <tr
                    key={r.emp_code}
                    style={{
                      backgroundColor: isSelected ? '#eff6ff' : undefined,
                      transition: 'background-color 0.15s'
                    }}
                  >
                    {/* Checkbox */}
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleSelect(r.emp_code)}
                        style={{ cursor: 'pointer' }}
                      />
                    </td>

                    {/* Emp Code */}
                    <td style={{ fontWeight: 800, color: '#1e3a8a' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span>{r.emp_code}</span>
                        {isVip && (
                          <span title="Full Pay VIP Policy" style={{ cursor: 'help' }}>
                            <Crown size={13} color="#d97706" />
                          </span>
                        )}
                        {r.origin === 'manual' && (
                          <span
                            style={{
                              fontSize: '0.62rem',
                              background: '#fef3c7',
                              color: '#92400e',
                              padding: '1px 5px',
                              borderRadius: '4px',
                              fontWeight: 700
                            }}
                          >
                            New
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Full Name & Designation */}
                    <td>
                      <div style={{ fontWeight: 700, color: '#0f172a' }}>{r.name || 'Unnamed Staff'}</div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{r.designation || 'Staff'}</div>
                    </td>

                    {/* Department */}
                    <td>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          background: '#f1f5f9',
                          color: '#334155',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontWeight: 600
                        }}
                      >
                        {r.department || 'General'}
                      </span>
                    </td>

                    {/* Category */}
                    <td>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: '9999px',
                          fontWeight: 700,
                          background: (r.category || '').toLowerCase().includes('teach')
                            ? '#dbeafe'
                            : '#f3e8ff',
                          color: (r.category || '').toLowerCase().includes('teach')
                            ? '#1d4ed8'
                            : '#7e22ce'
                        }}
                      >
                        {r.category || 'Non-Teaching'}
                      </span>
                    </td>

                    {/* Attendance Columns */}
                    {(dashboardMode === 'unified' || dashboardMode === 'attendance') && (
                      <>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: '#64748b' }}>
                          {r.month_days || 30}
                        </td>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: '#047857' }}>
                          {r.present_days !== undefined ? Number(r.present_days).toFixed(1) : '0.0'}
                        </td>
                        <td style={{ textAlign: 'right', color: '#475569' }}>
                          {r.wo_days !== undefined ? Number(r.wo_days).toFixed(1) : '0.0'}
                        </td>
                        <td style={{ textAlign: 'right', color: '#475569' }}>
                          {r.holiday_days !== undefined ? Number(r.holiday_days).toFixed(1) : '0.0'}
                        </td>

                        {/* Editable CL */}
                        <td style={{ textAlign: 'right' }}>
                          <input
                            type="number"
                            step="0.5"
                            min="0"
                            max="31"
                            defaultValue={r.cl_days !== undefined ? r.cl_days : 0}
                            className={`inline-input ${savingCell === `${r.emp_code}-cl_days` ? 'saved' : ''}`}
                            onBlur={(e) => handleCellBlur(r.emp_code, 'cl_days', r.cl_days, e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') e.target.blur();
                            }}
                          />
                        </td>

                        {/* Editable OD */}
                        <td style={{ textAlign: 'right' }}>
                          <input
                            type="number"
                            step="0.5"
                            min="0"
                            max="31"
                            defaultValue={r.od_days !== undefined ? r.od_days : 0}
                            className={`inline-input ${savingCell === `${r.emp_code}-od_days` ? 'saved' : ''}`}
                            onBlur={(e) => handleCellBlur(r.emp_code, 'od_days', r.od_days, e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') e.target.blur();
                            }}
                          />
                        </td>

                        {/* Payable Days */}
                        <td style={{ textAlign: 'right', fontWeight: 800, color: '#1e3a8a' }}>
                          {r.payable_days !== undefined ? Number(r.payable_days).toFixed(1) : '0.0'}
                        </td>

                        {/* LOP Days */}
                        <td
                          style={{
                            textAlign: 'right',
                            fontWeight: 800,
                            color: hasLop ? '#e11d48' : '#94a3b8'
                          }}
                        >
                          {hasLop ? (
                            <span style={{ background: '#fee2e2', padding: '2px 6px', borderRadius: '4px' }}>
                              {Number(r.lop_days).toFixed(1)}
                            </span>
                          ) : (
                            '0.0'
                          )}
                        </td>
                      </>
                    )}

                    {/* Salary Columns */}
                    {(dashboardMode === 'salary' || (dashboardMode === 'unified' && isSalaryUnlocked)) && (
                      <>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: '#334155' }}>
                          ₹{Math.round(r.base_rate || r.package_amount || 0).toLocaleString('en-IN')}
                        </td>
                        <td style={{ textAlign: 'right', fontWeight: 800, color: '#1e3a8a' }}>
                          ₹{Math.round(r.gross_salary || 0).toLocaleString('en-IN')}
                        </td>
                        <td style={{ textAlign: 'right', color: '#64748b' }}>
                          ₹{Math.round((r.pf_deduction || 0) + (r.esi_deduction || 0)).toLocaleString('en-IN')}
                        </td>
                        <td style={{ textAlign: 'right', color: '#64748b' }}>
                          ₹{Math.round((r.bus_fee || 0) + (r.mess_fee || 0) + (r.hostel_fee || 0)).toLocaleString('en-IN')}
                        </td>
                        <td style={{ textAlign: 'right', color: '#64748b' }}>
                          ₹{Math.round(r.other_deductions || 0).toLocaleString('en-IN')}
                        </td>
                        <td
                          style={{
                            textAlign: 'right',
                            fontWeight: 900,
                            fontSize: '0.88rem',
                            color: '#065f46',
                            background: '#ecfdf5'
                          }}
                        >
                          ₹{Math.round(r.net_salary || 0).toLocaleString('en-IN')}
                        </td>
                        <td>
                          {r.bank_account ? (
                            <div style={{ fontSize: '0.72rem' }}>
                              <div style={{ fontWeight: 700, color: '#1e293b' }}>{r.bank_account}</div>
                              <div style={{ color: '#64748b' }}>{r.ifsc_code || 'IFSC: NA'}</div>
                            </div>
                          ) : (
                            <span style={{ fontSize: '0.7rem', color: '#dc2626', fontWeight: 600 }}>
                              ⚠️ Missing Bank A/C
                            </span>
                          )}
                        </td>
                      </>
                    )}

                    {/* Action Buttons */}
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                        {/* Edit Button - DIRECTLY OPENS EDIT MODAL WITHOUT REQUIRING PIN FIRST! */}
                        <button
                          onClick={() => onOpenEdit(r)}
                          className="btn-pill"
                          title="Edit Full Staff Profile & Salary Package"
                          style={{
                            padding: '4px 8px',
                            background: '#eff6ff',
                            color: '#1d4ed8',
                            border: '1px solid #bfdbfe'
                          }}
                        >
                          <Edit2 size={13} />
                          <span>Edit</span>
                        </button>

                        {/* Pay Slip Button */}
                        <button
                          onClick={() => onOpenPaySlip(r)}
                          className="btn-pill"
                          title="Generate Formal RVS Pay Slip"
                          style={{
                            padding: '4px 8px',
                            background: '#f8fafc',
                            color: '#475569',
                            border: '1px solid #cbd5e1'
                          }}
                        >
                          <FileText size={13} />
                          <span>Slip</span>
                        </button>

                        {/* Revert Button */}
                        <button
                          onClick={() => onRevertBiometric(r.emp_code)}
                          className="btn-pill"
                          title="Revert Manual Edits back to Biometric Machine Data"
                          style={{
                            padding: '4px 6px',
                            background: '#f8fafc',
                            color: '#94a3b8',
                            border: '1px solid #e2e8f0'
                          }}
                        >
                          <RotateCcw size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
