import React from 'react';
import {
  Users,
  CheckCircle2,
  CalendarDays,
  IndianRupee,
  MinusCircle,
  Banknote,
  Lock
} from 'lucide-react';

export default function SummaryKpis({ stats, isSalaryUnlocked, onUnlockClick }) {
  const formatCurrency = (val) => {
    if (!isSalaryUnlocked) return '••••••••';
    const num = Math.round(Number(val) || 0);
    return '₹' + num.toLocaleString('en-IN');
  };

  return (
    <div className="kpi-row">
      {/* 1. Total Staff */}
      <div className="kpi-card" style={{ borderLeft: '4px solid #2563eb' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Total Staff Roster</span>
          <Users size={16} color="#2563eb" />
        </div>
        <div className="kpi-val" style={{ color: '#1e3a8a' }}>
          {stats.totalCount || 0}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '2px' }}>
          {stats.teachingCount || 0} Faculty · {stats.nonTeachingCount || 0} Staff
        </div>
      </div>

      {/* 2. Total Present Days */}
      <div className="kpi-card" style={{ borderLeft: '4px solid #10b981' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Biometric Present</span>
          <CheckCircle2 size={16} color="#10b981" />
        </div>
        <div className="kpi-val" style={{ color: '#065f46' }}>
          {Math.round(stats.totalPresent || 0).toLocaleString('en-IN')}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '2px' }}>
          Avg: {stats.avgPresent ? stats.avgPresent.toFixed(1) : 0} days/staff
        </div>
      </div>

      {/* 3. Approved Leaves & OD */}
      <div className="kpi-card" style={{ borderLeft: '4px solid #06b6d4' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Leaves & On-Duty</span>
          <CalendarDays size={16} color="#06b6d4" />
        </div>
        <div className="kpi-val" style={{ color: '#0e7490' }}>
          {Math.round((stats.totalCl || 0) + (stats.totalOd || 0))}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '2px' }}>
          {Math.round(stats.totalCl || 0)} CL · {Math.round(stats.totalOd || 0)} OD
        </div>
      </div>

      {/* 4. Total Gross Salary */}
      <div
        className="kpi-card"
        style={{ borderLeft: '4px solid #f59e0b', cursor: !isSalaryUnlocked ? 'pointer' : 'default' }}
        onClick={!isSalaryUnlocked ? onUnlockClick : undefined}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Gross Salary Payout</span>
          {!isSalaryUnlocked ? <Lock size={15} color="#d97706" /> : <IndianRupee size={16} color="#d97706" />}
        </div>
        <div className="kpi-val" style={{ color: '#92400e' }}>
          {formatCurrency(stats.totalGross)}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#b45309', marginTop: '2px' }}>
          {!isSalaryUnlocked ? '🔒 Click to enter PIN & view' : 'Calculated on payable days'}
        </div>
      </div>

      {/* 5. Total Deductions */}
      <div
        className="kpi-card"
        style={{ borderLeft: '4px solid #e11d48', cursor: !isSalaryUnlocked ? 'pointer' : 'default' }}
        onClick={!isSalaryUnlocked ? onUnlockClick : undefined}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Deductions & Flags</span>
          {!isSalaryUnlocked ? <Lock size={15} color="#e11d48" /> : <MinusCircle size={16} color="#e11d48" />}
        </div>
        <div className="kpi-val" style={{ color: '#9f1239' }}>
          {formatCurrency(stats.totalDeductions)}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#be123c', marginTop: '2px' }}>
          {!isSalaryUnlocked ? '🔒 PIN Protected' : `${stats.lopStaffCount || 0} staff with LOP`}
        </div>
      </div>

      {/* 6. Net Disbursal */}
      <div
        className="kpi-card"
        style={{
          borderLeft: '4px solid #059669',
          background: isSalaryUnlocked ? '#f0fdf4' : 'white',
          cursor: !isSalaryUnlocked ? 'pointer' : 'default'
        }}
        onClick={!isSalaryUnlocked ? onUnlockClick : undefined}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="kpi-title">Net Bank Disbursal</span>
          {!isSalaryUnlocked ? <Lock size={15} color="#059669" /> : <Banknote size={16} color="#059669" />}
        </div>
        <div className="kpi-val" style={{ color: '#065f46' }}>
          {formatCurrency(stats.totalNet)}
        </div>
        <div style={{ fontSize: '0.68rem', color: '#047857', marginTop: '2px' }}>
          {!isSalaryUnlocked ? '🔒 PIN Protected' : 'Ready for Bank NEFT/RTGS'}
        </div>
      </div>
    </div>
  );
}
