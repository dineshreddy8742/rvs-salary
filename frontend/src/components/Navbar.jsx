import React, { useRef, useState } from 'react';
import {
  Lock,
  Unlock,
  UserPlus,
  UploadCloud,
  FileSpreadsheet,
  Download,
  RefreshCw,
  ChevronDown,
  Building2,
  CheckCircle2,
  Calendar
} from 'lucide-react';

export default function Navbar({
  currentMonth,
  availableMonths,
  onMonthChange,
  isSalaryUnlocked,
  onToggleSalaryLock,
  onOpenAddStaff,
  onFileUpload,
  onRefresh,
  loading,
  onExportCsv,
  onExportBank
}) {
  const fileInputRef = useRef(null);
  const [showExportMenu, setShowExportMenu] = useState(false);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileUpload(file);
      e.target.value = ''; // reset so same file can be re-selected
    }
  };

  return (
    <header className="app-topbar">
      {/* Brand & Left Context */}
      <div className="topbar-left">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 10px rgba(37, 99, 235, 0.25)'
            }}
          >
            <Building2 size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.96rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.01em' }}>
                RVS UNIVERSITY
              </span>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  background: '#eff6ff',
                  color: '#2563eb',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  border: '1px solid #bfdbfe'
                }}
              >
                Payroll Hub
              </span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 500 }}>
              Faculty & Staff Biometric · Salary Ledger
            </div>
          </div>
        </div>

        {/* Academic Month Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '16px' }}>
          <Calendar size={15} color="#475569" />
          <select
            value={currentMonth}
            onChange={(e) => onMonthChange(e.target.value)}
            className="month-select"
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontWeight: 700,
              fontSize: '0.82rem',
              color: '#1e3a8a',
              background: '#f8fafc',
              cursor: 'pointer'
            }}
          >
            {availableMonths && availableMonths.length > 0 ? (
              availableMonths.map((m) => (
                <option key={m} value={m}>
                  📅 {m}
                </option>
              ))
            ) : (
              <option value={currentMonth}>{currentMonth}</option>
            )}
          </select>
        </div>
      </div>

      {/* Right Action Buttons */}
      <div className="topbar-actions">
        {/* Refresh Button */}
        <button
          className="btn-pill"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh Data from Server"
          style={{
            background: '#f1f5f9',
            color: '#334155',
            border: '1px solid #e2e8f0',
            padding: '7px 10px'
          }}
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>

        {/* Salary PIN Gated Lock/Unlock */}
        <button
          onClick={onToggleSalaryLock}
          className={`btn-pill ${isSalaryUnlocked ? 'btn-salary-revealed' : 'btn-salary-lock'}`}
          title={isSalaryUnlocked ? 'Click to re-lock salary figures' : 'Click to enter PIN & unlock salary view'}
        >
          {isSalaryUnlocked ? (
            <>
              <Unlock size={15} color="#059669" />
              <span>Salary: Unlocked</span>
            </>
          ) : (
            <>
              <Lock size={15} color="#b45309" />
              <span>Salary: Locked (PIN)</span>
            </>
          )}
        </button>

        {/* Add Staff Button */}
        <button className="btn-pill btn-primary" onClick={onOpenAddStaff}>
          <UserPlus size={15} />
          <span>Add Staff</span>
        </button>

        {/* Hidden File Input for Biometric Upload */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".xlsx,.xls,.csv"
          style={{ display: 'none' }}
        />

        {/* Upload Biometric / Excel Button */}
        <button
          className="btn-pill btn-upload"
          onClick={() => fileInputRef.current?.click()}
          title="Upload Biometric Attendance Dump or Staff Excel"
        >
          <UploadCloud size={15} />
          <span>Upload File</span>
        </button>

        {/* Export Tools Dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            className="btn-pill"
            onClick={() => setShowExportMenu(!showExportMenu)}
            style={{
              background: '#f8fafc',
              border: '1px solid #cbd5e1',
              color: '#334155'
            }}
          >
            <Download size={15} />
            <span>Exports</span>
            <ChevronDown size={14} />
          </button>

          {showExportMenu && (
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: '110%',
                background: 'white',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
                padding: '6px',
                width: '210px',
                zIndex: 100,
                display: 'flex',
                flexDirection: 'column',
                gap: '2px'
              }}
            >
              <button
                className="nav-item"
                onClick={() => {
                  setShowExportMenu(false);
                  onExportCsv();
                }}
                style={{ fontSize: '0.8rem', padding: '8px 10px' }}
              >
                <FileSpreadsheet size={15} color="#2563eb" />
                <span>Export Attendance CSV</span>
              </button>
              <button
                className="nav-item"
                onClick={() => {
                  setShowExportMenu(false);
                  onExportBank();
                }}
                style={{ fontSize: '0.8rem', padding: '8px 10px' }}
              >
                <CheckCircle2 size={15} color="#059669" />
                <span>Export Bank Disbursal</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
