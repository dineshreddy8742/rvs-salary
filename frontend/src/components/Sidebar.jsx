import React from 'react';
import {
  LayoutDashboard,
  CalendarCheck2,
  ReceiptIndianRupee,
  AlertTriangle,
  Crown,
  Landmark,
  Users,
  GraduationCap,
  Briefcase,
  Sparkles,
  Bus,
  UtensilsCrossed,
  Home,
  TrendingDown,
  RotateCcw,
  Printer,
  ShieldCheck,
  CheckCircle,
  FileSpreadsheet
} from 'lucide-react';

export default function Sidebar({
  dashboardMode, // 'unified' | 'attendance' | 'salary'
  onModeChange,
  activeFilter,
  onFilterChange,
  counts = {},
  isSalaryUnlocked
}) {
  return (
    <aside className="app-sidebar">
      {/* Brand Header */}
      <div className="sidebar-header">
        <span className="brand-badge">RVS TRUST · ESTD 1993</span>
        <div className="brand-title">RVS University</div>
        <div className="brand-subtitle">Chittoor · Faculty & Staff Payroll</div>
      </div>

      <div className="sidebar-content">
        {/* SECTION 1: Workspace Ledgers */}
        <div className="nav-section">
          <div className="nav-section-title">
            <span>1. Workspace Ledgers</span>
          </div>
          <button
            className={`nav-item ${dashboardMode === 'unified' ? 'active' : ''}`}
            onClick={() => onModeChange('unified')}
          >
            <LayoutDashboard size={16} />
            <span>All-in-One Master View</span>
          </button>
          <button
            className={`nav-item ${dashboardMode === 'attendance' ? 'active' : ''}`}
            onClick={() => onModeChange('attendance')}
          >
            <CalendarCheck2 size={16} />
            <span>Attendance Biometric Grid</span>
          </button>
          <button
            className={`nav-item ${dashboardMode === 'salary' ? 'active' : ''}`}
            onClick={() => onModeChange('salary')}
          >
            <ReceiptIndianRupee size={16} />
            <span>Salary & Bank Ledger</span>
          </button>
        </div>

        {/* SECTION 2: Audit & Attention */}
        <div className="nav-section">
          <div className="nav-section-title">
            <span>2. Audit & Attention</span>
          </div>
          <button
            className={`nav-item ${activeFilter === 'attention' ? 'active' : ''}`}
            onClick={() => onFilterChange(activeFilter === 'attention' ? 'all' : 'attention')}
          >
            <AlertTriangle size={16} color="#e11d48" />
            <span>Needs Attention</span>
            {counts.attention > 0 && (
              <span className="nav-badge badge-warning">{counts.attention}</span>
            )}
          </button>
          <button
            className={`nav-item ${activeFilter === 'vip' ? 'active' : ''}`}
            onClick={() => onFilterChange(activeFilter === 'vip' ? 'all' : 'vip')}
          >
            <Crown size={16} color="#d97706" />
            <span>Full Pay Staff (VIP)</span>
            {counts.vip > 0 && <span className="nav-badge badge-vip">{counts.vip}</span>}
          </button>
          <button
            className={`nav-item ${activeFilter === 'missing_bank' ? 'active' : ''}`}
            onClick={() => onFilterChange(activeFilter === 'missing_bank' ? 'all' : 'missing_bank')}
          >
            <Landmark size={16} color="#64748b" />
            <span>Missing Bank A/C</span>
            {counts.missing_bank > 0 && (
              <span className="nav-badge badge-warning">{counts.missing_bank}</span>
            )}
          </button>
        </div>

        {/* SECTION 3: Roster by Category */}
        <div className="nav-section">
          <div className="nav-section-title">
            <span>3. Roster By Category</span>
          </div>
          <button
            className={`nav-item ${activeFilter === 'all' ? 'active' : ''}`}
            onClick={() => onFilterChange('all')}
          >
            <Users size={16} />
            <span>All Staff</span>
            <span className="nav-badge">{counts.total || 0}</span>
          </button>
          <button
            className={`nav-item ${activeFilter === 'teaching' ? 'active' : ''}`}
            onClick={() => onFilterChange('teaching')}
          >
            <GraduationCap size={16} color="#2563eb" />
            <span>Teaching Faculty</span>
            <span className="nav-badge">{counts.teaching || 0}</span>
          </button>
          <button
            className={`nav-item ${activeFilter === 'non_teaching' ? 'active' : ''}`}
            onClick={() => onFilterChange('non_teaching')}
          >
            <Briefcase size={16} color="#475569" />
            <span>Non-Teaching Staff</span>
            <span className="nav-badge">{counts.non_teaching || 0}</span>
          </button>
          <button
            className={`nav-item ${activeFilter === 'support' ? 'active' : ''}`}
            onClick={() => onFilterChange('support')}
          >
            <Sparkles size={16} color="#059669" />
            <span>Support & Attenders</span>
            <span className="nav-badge">{counts.support || 0}</span>
          </button>
          <button
            className={`nav-item ${activeFilter === 'transport' ? 'active' : ''}`}
            onClick={() => onFilterChange('transport')}
          >
            <Bus size={16} color="#d97706" />
            <span>Transport & Drivers</span>
            <span className="nav-badge">{counts.transport || 0}</span>
          </button>
        </div>

        {/* SECTION 4: Deductions & Flags */}
        <div className="nav-section">
          <div className="nav-section-title">
            <span>4. Flags & Deductions</span>
          </div>
          <button
            className={`nav-item ${activeFilter === 'has_lop' ? 'active' : ''}`}
            onClick={() => onFilterChange(activeFilter === 'has_lop' ? 'all' : 'has_lop')}
          >
            <TrendingDown size={16} color="#e11d48" />
            <span>Has LOP (Loss of Pay)</span>
            {counts.has_lop > 0 && (
              <span className="nav-badge badge-warning">{counts.has_lop}</span>
            )}
          </button>
          <button
            className={`nav-item ${activeFilter === 'has_deductions' ? 'active' : ''}`}
            onClick={() =>
              onFilterChange(activeFilter === 'has_deductions' ? 'all' : 'has_deductions')
            }
          >
            <ReceiptIndianRupee size={16} color="#0891b2" />
            <span>Has Deductions</span>
            {counts.has_deductions > 0 && (
              <span className="nav-badge">{counts.has_deductions}</span>
            )}
          </button>
        </div>
      </div>

      {/* Footer System Status */}
      <div
        style={{
          padding: '14px 18px',
          borderTop: '1px solid var(--border-color)',
          background: '#f8fafc',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}
      >
        <div
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#10b981',
            boxShadow: '0 0 0 3px rgba(16, 185, 129, 0.2)'
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#1e293b' }}>
            Supabase DB Connected
          </div>
          <div style={{ fontSize: '0.66rem', color: '#64748b' }}>
            {counts.total || 0} Staff Synced · Fast Cache
          </div>
        </div>
        <ShieldCheck size={16} color="#10b981" />
      </div>
    </aside>
  );
}
