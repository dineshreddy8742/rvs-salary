import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import SummaryKpis from './components/SummaryKpis';
import StaffTable from './components/StaffTable';

import SalaryPinModal from './components/modals/SalaryPinModal';
import EditStaffModal from './components/modals/EditStaffModal';
import UploadProgressModal from './components/modals/UploadProgressModal';
import AddStaffModal from './components/modals/AddStaffModal';
import FormalPaySlipModal from './components/modals/FormalPaySlipModal';

import * as api from './api';

export default function App() {
  // Navigation & Month
  const [availableMonths, setAvailableMonths] = useState([]);
  const [currentMonth, setCurrentMonth] = useState('aug2026');
  const [loading, setLoading] = useState(false);

  // Data Stores
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [salaryRecordsMap, setSalaryRecordsMap] = useState({});

  // UI Modes & Filters
  const [dashboardMode, setDashboardMode] = useState('unified'); // 'unified' | 'attendance' | 'salary'
  const [activeFilter, setActiveFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCodes, setSelectedCodes] = useState(new Set());

  // Security / PIN Lock
  const [isSalaryUnlocked, setIsSalaryUnlocked] = useState(() => {
    return sessionStorage.getItem('rvs_salary_unlocked') === 'true';
  });

  // Modals
  const [isPinModalOpen, setIsPinModalOpen] = useState(false);
  const [editingStaff, setEditingStaff] = useState(null);
  const [payslipStaff, setPayslipStaff] = useState(null);
  const [isAddStaffOpen, setIsAddStaffOpen] = useState(false);
  const [uploadJob, setUploadJob] = useState(null); // { jobId, fileName }

  // Initial Fetch: Available Months
  useEffect(() => {
    async function initMonths() {
      try {
        const res = await api.fetchMonths();
        if (res && res.months && res.months.length > 0) {
          setAvailableMonths(res.months);
          // Default to first month or 'aug2026'
          const def = res.months.includes('aug2026') ? 'aug2026' : res.months[0];
          setCurrentMonth(def);
        }
      } catch (err) {
        console.error('Failed to load months:', err);
      }
    }
    initMonths();
  }, []);

  // Fetch Attendance and Salary data whenever month changes
  const loadData = useCallback(async (monthToLoad) => {
    const month = monthToLoad || currentMonth;
    if (!month) return;

    setLoading(true);
    try {
      // 1. Fetch Attendance Data
      const attData = await api.fetchData(month);
      const attList = Array.isArray(attData) ? attData : (attData.records || []);
      setAttendanceRecords(attList);

      // 2. Fetch Salary Data in parallel
      try {
        const salData = await api.fetchSalaryAll(month);
        const map = {};
        if (salData && salData.employees) {
          salData.employees.forEach((s) => {
            map[s.emp_code] = s;
          });
        }
        setSalaryRecordsMap(map);
      } catch (salErr) {
        console.warn('Salary fetch warning:', salErr);
      }
    } catch (err) {
      console.error('Data fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [currentMonth]);

  useEffect(() => {
    loadData(currentMonth);
  }, [currentMonth, loadData]);

  // Merge Attendance + Salary records for fast, unified rendering
  const mergedRecords = useMemo(() => {
    return attendanceRecords.map((att) => {
      const sal = salaryRecordsMap[att.emp_code] || {};
      const gross = sal.gross_salary !== undefined ? sal.gross_salary : (att.gross_salary || 0);
      const net = sal.net_salary !== undefined ? sal.net_salary : (att.net_salary || 0);
      const pkg = sal.package_amount !== undefined ? sal.package_amount : (att.package_amount || 0);

      return {
        ...att,
        ...sal,
        // Guaranteed consistent keys
        emp_code: att.emp_code,
        name: att.name || sal.name || 'Staff',
        department: att.department || sal.department || 'General',
        designation: att.designation || sal.designation || 'Staff',
        category: att.category || sal.category || 'Non-Teaching',
        salary_policy: sal.salary_policy || att.salary_policy || 'Standard Biometric',
        month_days: att.month_days || 30,
        present_days: att.present_days !== undefined ? att.present_days : 0,
        wo_days: att.wo_days !== undefined ? att.wo_days : 0,
        holiday_days: att.holiday_days !== undefined ? att.holiday_days : 0,
        cl_days: att.cl_days !== undefined ? att.cl_days : 0,
        od_days: att.od_days !== undefined ? att.od_days : 0,
        payable_days: att.payable_days !== undefined ? att.payable_days : att.present_days || 0,
        lop_days: att.lop_days !== undefined ? att.lop_days : 0,
        package_amount: pkg,
        gross_salary: gross,
        net_salary: net,
        total_deductions: sal.total_deductions || 0,
        bank_account: sal.bank_account || att.bank_account || '',
        ifsc_code: sal.ifsc_code || att.ifsc_code || '',
        origin: att.origin || sal.origin || 'biometric'
      };
    });
  }, [attendanceRecords, salaryRecordsMap]);

  // Calculate live KPI statistics
  const stats = useMemo(() => {
    let totalCount = mergedRecords.length;
    let teachingCount = 0;
    let nonTeachingCount = 0;
    let supportCount = 0;
    let transportCount = 0;
    let vipCount = 0;
    let lopStaffCount = 0;
    let missingBankCount = 0;
    let hasDeductionsCount = 0;

    let totalPresent = 0;
    let totalCl = 0;
    let totalOd = 0;
    let totalGross = 0;
    let totalNet = 0;
    let totalDeductions = 0;

    for (let r of mergedRecords) {
      const cat = (r.category || '').toLowerCase();
      if (cat.includes('teach') && !cat.includes('non')) teachingCount++;
      else if (cat.includes('non')) nonTeachingCount++;
      else if (cat.includes('support') || cat.includes('attender')) supportCount++;
      else if (cat.includes('transport') || cat.includes('driver')) transportCount++;

      if (r.is_fixed_salary || (r.salary_policy && (r.salary_policy.includes('VIP') || r.salary_policy.includes('Full Pay')))) {
        vipCount++;
      }
      if (Number(r.lop_days || 0) > 0) lopStaffCount++;
      if (!r.bank_account || r.bank_account.trim() === '') missingBankCount++;
      if (Number(r.total_deductions || 0) > 0) hasDeductionsCount++;

      totalPresent += Number(r.present_days || 0);
      totalCl += Number(r.cl_days || 0);
      totalOd += Number(r.od_days || 0);
      totalGross += Number(r.gross_salary || 0);
      totalNet += Number(r.net_salary || 0);
      totalDeductions += Number(r.total_deductions || 0);
    }

    return {
      totalCount,
      teachingCount,
      nonTeachingCount,
      supportCount,
      transportCount,
      vipCount,
      lopStaffCount,
      missingBankCount,
      hasDeductionsCount,
      attentionCount: lopStaffCount + missingBankCount,
      totalPresent,
      avgPresent: totalCount > 0 ? totalPresent / totalCount : 0,
      totalCl,
      totalOd,
      totalGross,
      totalNet,
      totalDeductions
    };
  }, [mergedRecords]);

  // Sidebar Counts object
  const sidebarCounts = useMemo(() => ({
    total: stats.totalCount,
    teaching: stats.teachingCount,
    non_teaching: stats.nonTeachingCount,
    support: stats.supportCount,
    transport: stats.transportCount,
    vip: stats.vipCount,
    attention: stats.attentionCount,
    missing_bank: stats.missingBankCount,
    has_lop: stats.lopStaffCount,
    has_deductions: stats.hasDeductionsCount
  }), [stats]);

  // Salary Lock Toggle
  const handleToggleSalaryLock = () => {
    if (isSalaryUnlocked) {
      // Re-lock
      setIsSalaryUnlocked(false);
      sessionStorage.removeItem('rvs_salary_unlocked');
    } else {
      // Open PIN modal
      setIsPinModalOpen(true);
    }
  };

  const handlePinSuccess = () => {
    setIsSalaryUnlocked(true);
    sessionStorage.setItem('rvs_salary_unlocked', 'true');
    setIsPinModalOpen(false);
  };

  // Inline Cell Update Handler (CL, OD, etc.)
  const handleInlineUpdate = async (empCode, field, value) => {
    try {
      await api.updateEmployeeField(empCode, field, value, currentMonth);
      // Optimistically update local attendance records
      setAttendanceRecords((prev) =>
        prev.map((r) => {
          if (r.emp_code === empCode) {
            const updated = { ...r, [field]: value };
            // Auto recompute payable days if CL/OD changed
            if (field === 'cl_days' || field === 'od_days') {
              const cl = field === 'cl_days' ? value : (r.cl_days || 0);
              const od = field === 'od_days' ? value : (r.od_days || 0);
              const pr = Number(r.present_days || 0);
              const wo = Number(r.wo_days || 0);
              const hol = Number(r.holiday_days || 0);
              const monthDays = Number(r.month_days || 30);
              const payable = Math.min(monthDays, pr + wo + hol + cl + od);
              updated.payable_days = payable;
              updated.lop_days = Math.max(0, monthDays - payable);
            }
            return updated;
          }
          return r;
        })
      );
    } catch (err) {
      console.error('Inline update failed:', err);
      alert('Failed to update: ' + err.message);
    }
  };

  // Revert Staff to Biometric
  const handleRevertBiometric = async (empCode) => {
    if (!confirm(`Revert ${empCode} back to raw biometric machine record?`)) return;
    try {
      await api.revertToBiometric(empCode, currentMonth);
      await loadData(currentMonth);
    } catch (err) {
      alert('Revert failed: ' + err.message);
    }
  };

  // Biometric / Excel File Upload with Percentage Modal
  const handleFileUpload = async (file) => {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('month_year', currentMonth);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok || data.status !== 'success') {
        throw new Error(data.message || 'Upload initialization failed');
      }

      // Open Progress Modal with Job ID
      setUploadJob({
        jobId: data.job_id,
        fileName: file.name
      });
    } catch (err) {
      alert('Upload failed: ' + err.message);
    }
  };

  // Export handlers
  const handleExportCsv = () => {
    window.open(`/api/export-attendance?month=${encodeURIComponent(currentMonth)}`, '_blank');
  };

  const handleExportBank = () => {
    window.open(`/api/export-bank-disbursal?month=${encodeURIComponent(currentMonth)}`, '_blank');
  };

  // Multi-select handlers
  const handleToggleSelect = (code) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const handleToggleSelectAll = (codes) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      const allSelected = codes.every((c) => next.has(c));
      if (allSelected) {
        codes.forEach((c) => next.delete(c));
      } else {
        codes.forEach((c) => next.add(c));
      }
      return next;
    });
  };

  return (
    <div className="app-container">
      {/* 1. Left Sidebar */}
      <Sidebar
        dashboardMode={dashboardMode}
        onModeChange={setDashboardMode}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        counts={sidebarCounts}
        isSalaryUnlocked={isSalaryUnlocked}
      />

      {/* 2. Main Work Area */}
      <main className="app-main">
        {/* Top Navbar */}
        <Navbar
          currentMonth={currentMonth}
          availableMonths={availableMonths}
          onMonthChange={setCurrentMonth}
          isSalaryUnlocked={isSalaryUnlocked}
          onToggleSalaryLock={handleToggleSalaryLock}
          onOpenAddStaff={() => setIsAddStaffOpen(true)}
          onFileUpload={handleFileUpload}
          onRefresh={() => loadData(currentMonth)}
          loading={loading}
          onExportCsv={handleExportCsv}
          onExportBank={handleExportBank}
        />

        {/* Dynamic Summary KPIs Bar */}
        <SummaryKpis
          stats={stats}
          isSalaryUnlocked={isSalaryUnlocked}
          onUnlockClick={() => setIsPinModalOpen(true)}
        />

        {/* Master Staff Data Table */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <StaffTable
            records={mergedRecords}
            dashboardMode={dashboardMode}
            isSalaryUnlocked={isSalaryUnlocked}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            activeFilter={activeFilter}
            onOpenEdit={(staff) => setEditingStaff(staff)}
            onOpenPaySlip={(staff) => setPayslipStaff(staff)}
            onRevertBiometric={handleRevertBiometric}
            onInlineUpdate={handleInlineUpdate}
            selectedCodes={selectedCodes}
            onToggleSelect={handleToggleSelect}
            onToggleSelectAll={handleToggleSelectAll}
          />
        </div>
      </main>

      {/* 3. Interactive Modals */}
      {/* PIN Unlock Modal */}
      <SalaryPinModal
        isOpen={isPinModalOpen}
        onClose={() => setIsPinModalOpen(false)}
        onSuccess={handlePinSuccess}
      />

      {/* Edit Staff Modal (Unified 360° Profile & Package Editor) */}
      <EditStaffModal
        isOpen={!!editingStaff}
        onClose={() => setEditingStaff(null)}
        employee={editingStaff}
        currentMonth={currentMonth}
        onSuccess={() => {
          setEditingStaff(null);
          loadData(currentMonth);
        }}
      />

      {/* Add Staff Modal (Single, Bulk CSV, Manage/Delete) */}
      <AddStaffModal
        isOpen={isAddStaffOpen}
        onClose={() => setIsAddStaffOpen(false)}
        allStaff={mergedRecords}
        currentMonth={currentMonth}
        onSuccess={() => {
          loadData(currentMonth);
        }}
      />

      {/* Formal Pay Slip Modal */}
      <FormalPaySlipModal
        isOpen={!!payslipStaff}
        onClose={() => setPayslipStaff(null)}
        staff={payslipStaff}
        currentMonth={currentMonth}
      />

      {/* Biometric Upload Progress Modal */}
      <UploadProgressModal
        isOpen={!!uploadJob}
        jobId={uploadJob?.jobId}
        fileName={uploadJob?.fileName}
        onClose={() => setUploadJob(null)}
        onCompleted={() => {
          setUploadJob(null);
          loadData(currentMonth);
        }}
      />
    </div>
  );
}
