// =============================================================================
// RVS UNIVERSITY PORTAL — ANTI-INSPECT, ANTI-DEVTOOLS & CODE TAMPER SHIELD
// =============================================================================
(function() {
  'use strict';

  // 1. Disable Right-Click Context Menu (Prevents "Inspect Element")
  document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    return false;
  }, { capture: true });

  // 2. Disable DevTools & Source-Inspection Keyboard Shortcuts
  document.addEventListener('keydown', function(e) {
    if (e.keyCode === 123 || e.key === 'F12') {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
    if (e.ctrlKey && e.shiftKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
    if (e.ctrlKey && ['U', 'u', 'S', 's'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
    if (e.metaKey && e.altKey && ['I', 'i', 'J', 'j', 'C', 'c'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
    if (e.metaKey && ['U', 'u', 'S', 's'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
  }, { capture: true });

  // 3. Neutralize Console: Wipe out console output so internal data cannot be extracted
  try {
    const noop = function() {};
    ['log', 'debug', 'info', 'warn', 'error', 'dir', 'dirxml', 'table', 'trace', 'group', 'groupCollapsed', 'groupEnd'].forEach(function(m) {
      console[m] = noop;
    });
  } catch(err) {}

  // 4. Anti-Debugger Trap: If DevTools is opened, freeze execution via continuous debugger trap
  setInterval(function() {
    (function() {
      return false;
    })['constructor']('debugger')();
  }, 800);

})();

// Global Auth Interceptor: Redirect to /login if server returns 401 Unauthorized
const _originalFetch = window.fetch;
window.fetch = async function(...args) {
  const response = await _originalFetch.apply(this, args);
  if (response && response.status === 401) {
    window.location.href = '/login';
  }
  return response;
};

// Portal Logout Action
async function handleLogout() {
  if (confirm('Are you sure you want to log out of RVS University Payroll Portal?')) {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
  }
}

let allEmployees = [];
let allSalaryRecords = [];
let currentFilter = 'all';
let currentDept = 'all';
let currentCategory = 'all';
let currentSort = 'code_asc';
let activeOnly = true;
let currentMonth = 'August -2026';
let activePortfolioEmpCode = null;
let currentDashboardMode = 'unified'; // 'unified', 'attendance', or 'salary'
let unifiedRecords = [];
let showSalaryColumns = false;

// === OFFICIAL RVS INSTITUTIONAL DEPARTMENT ORDER ===
const OFFICIAL_DEPT_ORDER = [
  'Management Staff',
  'Administration',
  'General',
  'CE',
  'EEE',
  'ME',
  'ECE',
  'CSE',
  'CSM',
  'CSD',
  'CAI',
  'IT',
  'MCA',
  'MBA',
  'HAS',
  'PD',
  'Accounts',
  'Media',
  'Exam Section',
  'Library',
  'Maintenance',
  'TAP',
  'Electriations',
  'SLH',
  'Admissions',
  'Transport',
  'Attender',
  'Garden Staff',
  'Security & Water Staff'
];

function getDeptOrderIndex(dept) {
  const d = String(dept || '').trim();
  const idx = OFFICIAL_DEPT_ORDER.indexOf(d);
  return idx !== -1 ? idx : 999;
}

// === PIN LOCK SYSTEM ===
const SALARY_PIN_KEY = 'rvs_salary_pin';
let _pinBuffer = '';          // current digits entered
let _pinMode = 'unlock';      // 'unlock' | 'set-new' | 'confirm-new'
let _pinNewCandidate = '';    // temp for change-pin flow
function _getSavedPin() { return localStorage.getItem(SALARY_PIN_KEY) || '1234'; }
function _savePin(p) { localStorage.setItem(SALARY_PIN_KEY, p); }

function getCleanMonth() {
  return (currentMonth || 'August_2026').replace(/[\s\-]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');
}

function triggerFileDownload(url, filename) {
  fetch(url)
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.blob();
    })
    .then(blob => {
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      if (filename) link.setAttribute('download', filename);
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        try { document.body.removeChild(link); } catch(e) {}
        window.URL.revokeObjectURL(blobUrl);
      }, 1000);
    })
    .catch(error => {
      console.error('Download error:', error);
      alert('Error downloading file. Please try again.');
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  updateSalaryToggleUI();
  loadMonths();
});

function setupEventListeners() {
  // Search
  document.getElementById('search-input').addEventListener('input', renderTable);

  // Month Switcher
  document.getElementById('month-select').addEventListener('change', (e) => {
    currentMonth = e.target.value;
    showToast(`Switched to ${currentMonth}`);
    loadData();
  });

  // Department filter
  document.getElementById('dept-select').addEventListener('change', (e) => {
    currentDept = e.target.value;
    renderTable();
  });

  // Category filter (Salary mode)
  const catSelect = document.getElementById('category-select');
  if (catSelect) {
    catSelect.addEventListener('change', (e) => {
      currentCategory = e.target.value;
      renderTable();
    });
  }

  // Sort selector
  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderTable();
    });
  }

  // Filter Select Dropdown
  const filterSelect = document.getElementById('filter-select');
  if (filterSelect) {
    filterSelect.addEventListener('change', (e) => {
      setFilterPill(e.target.value);
    });
  }

  // Filter Clear Button
  const btnClearFilter = document.getElementById('btn-clear-filter');
  if (btnClearFilter) {
    btnClearFilter.addEventListener('click', () => {
      setFilterPill('all');
    });
  }

  // Filter tabs (if any remain)
  document.querySelectorAll('.filter-tabs .tab-pill').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const pill = e.currentTarget;
      document.querySelectorAll('.filter-tabs .tab-pill').forEach(b => b.classList.remove('active'));
      pill.classList.add('active');
      setFilterPill(pill.dataset.filter);
    });
  });

  // Nav link quick filters
  const navReview = document.getElementById('nav-filter-review');
  if (navReview) navReview.addEventListener('click', () => setFilterPill('review'));

  const navVip = document.getElementById('nav-filter-vip');
  if (navVip) navVip.addEventListener('click', () => setFilterPill('vip'));

  const navLeaves = document.getElementById('nav-filter-leaves');
  if (navLeaves) navLeaves.addEventListener('click', () => setFilterPill('leaves'));

  // 3-Way Mode Switcher (Unified Master vs Attendance Grid vs Salary & Bank Ledger)
  const modeCluster = document.getElementById('view-mode-cluster');
  if (modeCluster) {
    modeCluster.querySelectorAll('.view-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        modeCluster.querySelectorAll('.view-pill').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        switchDashboardMode(e.currentTarget.dataset.mode);
      });
    });
  }

  // Salary Visibility Toggle — PIN Gated (Principal Sir Request)
  const btnToggleSalary = document.getElementById('btn-toggle-salary-cols');
  if (btnToggleSalary) {
    btnToggleSalary.addEventListener('click', () => {
      if (showSalaryColumns) {
        // Already revealed → instantly lock
        showSalaryColumns = false;
        updateSalaryToggleUI();
        renderTable();
        showToast('🔒 Salary columns locked');
      } else {
        // Hidden → require PIN to reveal
        openPinModal();
      }
    });
  }

  // Dynamic Sidebar Drawer / Collapse Toggle & Backdrop
  const appLayout = document.querySelector('.app-layout');
  const sidebar = document.getElementById('app-sidebar');
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
  const btnCollapseSidebar = document.getElementById('btn-collapse-sidebar');
  const btnCloseSidebar = document.getElementById('btn-close-sidebar');

  function toggleSidebar() {
    if (window.innerWidth > 1024) {
      // Desktop: Toggle collapsed state for full-width table view
      if (appLayout) {
        appLayout.classList.toggle('sidebar-collapsed');
        const isCollapsed = appLayout.classList.contains('sidebar-collapsed');
        localStorage.setItem('rvs_sidebar_collapsed', isCollapsed ? '1' : '0');
        if (btnToggleSidebar) btnToggleSidebar.classList.toggle('active', isCollapsed);
      }
    } else {
      // Mobile / Tablet: Toggle off-canvas drawer
      if (sidebar) sidebar.classList.toggle('active');
      if (sidebarBackdrop) sidebarBackdrop.classList.toggle('active');
    }
  }

  function collapseSidebar() {
    if (window.innerWidth > 1024) {
      if (appLayout) {
        appLayout.classList.add('sidebar-collapsed');
        localStorage.setItem('rvs_sidebar_collapsed', '1');
        if (btnToggleSidebar) btnToggleSidebar.classList.add('active');
      }
    } else {
      if (sidebar) sidebar.classList.remove('active');
      if (sidebarBackdrop) sidebarBackdrop.classList.remove('active');
    }
  }

  if (btnToggleSidebar) btnToggleSidebar.addEventListener('click', toggleSidebar);
  if (btnCollapseSidebar) btnCollapseSidebar.addEventListener('click', collapseSidebar);
  if (btnCloseSidebar) btnCloseSidebar.addEventListener('click', collapseSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', collapseSidebar);

  // Restore saved desktop sidebar preference
  if (window.innerWidth > 1024 && localStorage.getItem('rvs_sidebar_collapsed') === '1') {
    if (appLayout) appLayout.classList.add('sidebar-collapsed');
    if (btnToggleSidebar) btnToggleSidebar.classList.add('active');
  }

  // Sidebar Quick Category Filter Buttons
  document.querySelectorAll('.sidebar-cat-pill').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const filter = e.currentTarget.dataset.sidebarFilter;
      setFilterPill(filter);
      if (window.innerWidth <= 1024 && sidebar) {
        sidebar.classList.remove('active');
        if (sidebarBackdrop) sidebarBackdrop.classList.remove('active');
      }
    });
  });

  // Active Only toggle
  document.getElementById('toggle-active-only').addEventListener('change', (e) => {
    activeOnly = e.target.checked;
    loadData();
  });

  // Export Attendance button (.xls)
  document.getElementById('btn-export').addEventListener('click', () => {
    const fn = `SVCET_Attendance_${getCleanMonth()}.xls`;
    showToast(`⚡ Exporting ${currentMonth} Attendance to ${fn}...`);
    triggerFileDownload(`/api/export?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`, fn);
  });

  // Export Salary Bill button (.xlsx)
  const btnExportSal = document.getElementById('btn-export-salary');
  if (btnExportSal) {
    btnExportSal.addEventListener('click', () => {
      const fn = `SVCET_Salary_Bill_${getCleanMonth()}.xlsx`;
      showToast(`⚡ Exporting ${currentMonth} Institutional Salary Bill (${fn})...`);
      triggerFileDownload(`/api/salary/export?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`, fn);
    });
  }

  // Upload file trigger
  const fileInput = document.getElementById('file-input');
  document.getElementById('btn-upload-trigger').addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const monthPrompt = prompt('Enter the Month & Year for this biometric file:', currentMonth);
    if (!monthPrompt) {
      fileInput.value = '';
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('month_name', monthPrompt);

    showToast(`⏳ Uploading & Analyzing ${file.name} for ${monthPrompt}... Please wait.`);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      let data = null;
      let rawText = '';
      try {
        const text = await res.text();
        rawText = text;
        data = JSON.parse(text);
      } catch (jsonErr) {
        if (res.status === 401) {
          alert('Session expired. Please log in again.');
          window.location.href = '/login';
          return;
        }
        console.error('Server non-JSON response:', rawText);
        throw new Error(
          res.status === 500
            ? 'Server memory/timeout error (HTTP 500). Please check your connection and retry.'
            : `Server returned HTTP ${res.status}: ${res.statusText || 'Upload failed'}`
        );
      }

      if (res.ok && data && data.status === 'success') {
        showToast('✅ File analyzed and saved to database successfully!');
        currentMonth = monthPrompt;
        await loadMonths();
      } else {
        alert('Upload Error: ' + ((data && data.message) || res.statusText || 'Failed to process file'));
      }
    } catch (err) {
      console.error('Upload error:', err);
      alert('Upload failed: ' + (err.message || 'Connection error. If the file is large, please allow 30 seconds.'));
    } finally {
      fileInput.value = '';
    }
  });

  // Add Staff Modal
  const addStaffModal = document.getElementById('modal-add-staff');
  document.getElementById('btn-add-staff-modal').addEventListener('click', () => {
    addStaffModal.classList.add('active');
  });
  document.getElementById('btn-close-add-staff').addEventListener('click', () => {
    addStaffModal.classList.remove('active');
  });
  document.getElementById('btn-cancel-add-staff').addEventListener('click', () => {
    addStaffModal.classList.remove('active');
  });

  document.getElementById('btn-save-add-staff').addEventListener('click', async (e) => {
    e.preventDefault();
    const code = document.getElementById('add-emp-code').value.trim();
    const name = document.getElementById('add-emp-name').value.trim();
    const desig = document.getElementById('add-emp-desig').value.trim();
    const dept = document.getElementById('add-emp-dept').value.trim();
    const policy = document.getElementById('add-emp-policy').value;
    const clQuota = parseFloat(document.getElementById('add-emp-cl-quota').value || 12);
    const baseDays = parseFloat(document.getElementById('add-emp-base-days').value || 25);

    if (!code || !name) {
      alert('Please fill in Employee Code and Full Name.');
      return;
    }

    try {
      const res = await fetch('/api/manual-employee', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          emp_code: code,
          name: name,
          designation: desig,
          department: dept,
          attendance_policy: policy,
          annual_cl_quota: clQuota,
          biometric_days: baseDays,
          month_year: currentMonth
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showToast(`✔ Added ${name} (${code}) to roster!`);
        addStaffModal.classList.remove('active');
        document.getElementById('form-add-staff').reset();
        loadData();
      } else {
        alert('Error: ' + data.message);
      }
    } catch (err) {
      alert('Network error adding staff member');
    }
  });

  // Bulk Slips Modal
  const bulkModal = document.getElementById('modal-bulk-slips');
  document.getElementById('btn-bulk-slips-modal').addEventListener('click', () => {
    bulkModal.classList.add('active');
  });
  document.getElementById('btn-close-bulk').addEventListener('click', () => {
    bulkModal.classList.remove('active');
  });
  document.getElementById('btn-cancel-bulk').addEventListener('click', () => {
    bulkModal.classList.remove('active');
  });

  document.getElementById('btn-apply-bulk').addEventListener('click', async () => {
    const text = document.getElementById('bulk-paste-text').value;
    if (!text.trim()) {
      alert('Please paste slip entries first.');
      return;
    }

    try {
      const res = await fetch('/api/bulk-slips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, month_year: currentMonth })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showToast(`✔ Applied ${data.applied_count} leave/OD slips for ${currentMonth}!`);
        bulkModal.classList.remove('active');
        document.getElementById('bulk-paste-text').value = '';
        loadData();
      } else {
        alert('Error applying slips: ' + data.message);
      }
    } catch (err) {
      alert('Network error applying bulk slips');
    }
  });

  // Portfolio Modal
  const portfolioModal = document.getElementById('modal-portfolio');
  document.getElementById('btn-close-portfolio').addEventListener('click', () => {
    portfolioModal.classList.remove('active');
  });
  document.getElementById('btn-done-portfolio').addEventListener('click', () => {
    portfolioModal.classList.remove('active');
  });

  document.getElementById('btn-save-policy').addEventListener('click', async () => {
    if (!activePortfolioEmpCode) return;
    const newPolicy = document.getElementById('pf-policy-select').value;
    try {
      const res = await fetch('/api/set-policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emp_code: activePortfolioEmpCode, policy: newPolicy, month_year: currentMonth })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showToast(`✔ Attendance Policy updated to: ${newPolicy}`);
        renderPortfolioModal(data.portfolio);
        loadData();
      }
    } catch (err) {
      alert('Error updating policy');
    }
  });

  // Timeline Modal
  const timelineModal = document.getElementById('modal-timeline');
  document.getElementById('btn-close-timeline').addEventListener('click', () => {
    timelineModal.classList.remove('active');
  });
  document.getElementById('btn-done-timeline').addEventListener('click', () => {
    timelineModal.classList.remove('active');
  });

  // Needs review card click
  const cardReview = document.getElementById('card-needs-review');
  if (cardReview) {
    cardReview.addEventListener('click', () => {
      setFilterPill('review');
    });
  }

  // Bulk Adjust Modal
  const bulkAdjustModal = document.getElementById('modal-bulk-adjust');
  const btnBulkOpen = document.getElementById('btn-bulk-adjust-modal');
  if (btnBulkOpen) btnBulkOpen.addEventListener('click', openBulkAdjustModal);
  const btnBulkClose = document.getElementById('btn-close-bulk-adjust');
  if (btnBulkClose) btnBulkClose.addEventListener('click', () => bulkAdjustModal.classList.remove('active'));
  const btnBulkCancel = document.getElementById('btn-cancel-bulk-adjust');
  if (btnBulkCancel) btnBulkCancel.addEventListener('click', () => bulkAdjustModal.classList.remove('active'));
  const btnBulkApply = document.getElementById('btn-apply-bulk-adjust');
  if (btnBulkApply) btnBulkApply.addEventListener('click', executeBulkAdjust);

  const bulkFieldSelect = document.getElementById('bulk-adj-field');
  if (bulkFieldSelect) {
    bulkFieldSelect.addEventListener('change', (e) => {
      const isGrant = e.target.value === 'grant_full_days';
      const opBox = document.getElementById('bulk-adj-op-box');
      const valBox = document.getElementById('bulk-adj-val-box');
      if (opBox) opBox.style.display = isGrant ? 'none' : 'block';
      if (valBox) valBox.style.display = isGrant ? 'none' : 'block';
    });
  }

  // Bulk Revert Modal
  const bulkRevertModal = document.getElementById('modal-bulk-revert');
  const btnBulkRevertOpen = document.getElementById('btn-bulk-revert-modal');
  if (btnBulkRevertOpen) btnBulkRevertOpen.addEventListener('click', openBulkRevertModal);
  const btnBulkRevertClose = document.getElementById('btn-close-bulk-revert');
  if (btnBulkRevertClose) btnBulkRevertClose.addEventListener('click', () => bulkRevertModal.classList.remove('active'));
  const btnBulkRevertCancel = document.getElementById('btn-cancel-bulk-revert');
  if (btnBulkRevertCancel) btnBulkRevertCancel.addEventListener('click', () => bulkRevertModal.classList.remove('active'));
  const btnBulkRevertApply = document.getElementById('btn-apply-bulk-revert');
  if (btnBulkRevertApply) btnBulkRevertApply.addEventListener('click', executeBulkRevert);

  const bulkRevertScopeSelect = document.getElementById('bulk-revert-scope');
  if (bulkRevertScopeSelect) {
    bulkRevertScopeSelect.addEventListener('change', (e) => {
      const scope = e.target.value;
      const deptBox = document.getElementById('bulk-revert-dept-box');
      const catBox = document.getElementById('bulk-revert-cat-box');
      if (deptBox) deptBox.style.display = scope === 'department' ? 'block' : 'none';
      if (catBox) catBox.style.display = scope === 'category' ? 'block' : 'none';
    });
  }

  // Variance Modal
  const varModal = document.getElementById('modal-salary-variance');
  const btnVarOpen = document.getElementById('btn-variance-modal');
  if (btnVarOpen) btnVarOpen.addEventListener('click', openSalaryVarianceModal);
  const btnVarClose = document.getElementById('btn-close-variance');
  if (btnVarClose) btnVarClose.addEventListener('click', () => varModal.classList.remove('active'));
  const btnVarDone = document.getElementById('btn-done-variance');
  if (btnVarDone) btnVarDone.addEventListener('click', () => varModal.classList.remove('active'));

  // Edit Employee Package Modal
  const pkgModal = document.getElementById('modal-employee-package');
  const btnPkgClose = document.getElementById('btn-close-edit-pkg');
  if (btnPkgClose) btnPkgClose.addEventListener('click', () => pkgModal.classList.remove('active'));
  const btnPkgCancel = document.getElementById('btn-cancel-edit-pkg');
  if (btnPkgCancel) btnPkgCancel.addEventListener('click', () => pkgModal.classList.remove('active'));
  const btnPkgSave = document.getElementById('btn-save-edit-pkg');
  if (btnPkgSave) btnPkgSave.addEventListener('click', saveEmployeePackage);

  // Live calculation listeners for Complete Unified 360 Master Editor Modal
  const editorLiveInputs = [
    'edit-pkg-pay-days', 'edit-pkg-base-sal', 'edit-pkg-arrears',
    'edit-pkg-pt', 'edit-pkg-wf', 'edit-pkg-epf', 'edit-pkg-it', 'edit-pkg-other-ded',
    'edit-pkg-category'
  ];
  editorLiveInputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', updateModalLivePreview);
      el.addEventListener('change', updateModalLivePreview);
    }
  });

  const attLiveInputs = ['edit-pkg-bio-days', 'edit-pkg-holidays', 'edit-pkg-cl', 'edit-pkg-od'];
  attLiveInputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', handleAttendanceDaysChange);
      el.addEventListener('change', handleAttendanceDaysChange);
    }
  });


  // Formal Pay Slip Modal
  const slipModal = document.getElementById('modal-pay-slip');
  const btnSlipClose = document.getElementById('btn-close-pay-slip');
  if (btnSlipClose) btnSlipClose.addEventListener('click', () => slipModal.classList.remove('active'));
  const btnPrintPayslip = document.getElementById('btn-print-payslip');
  if (btnPrintPayslip) btnPrintPayslip.addEventListener('click', () => openFormalPaySlip(activePortfolioEmpCode));
  const btnExecPrint = document.getElementById('btn-execute-print');
  if (btnExecPrint) btnExecPrint.addEventListener('click', () => window.print());

  // Banking & Treasury Dropdown
  const btnDisburseMenu = document.getElementById('btn-disburse-menu');
  const menuDisburse = document.getElementById('menu-disbursement');
  if (btnDisburseMenu && menuDisburse) {
    btnDisburseMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      if (menuOps) menuOps.classList.remove('show');
      menuDisburse.classList.toggle('show');
    });
    document.addEventListener('click', () => menuDisburse.classList.remove('show'));
  }

  // Tools & Operations Dropdown
  const btnOpsMenu = document.getElementById('btn-operations-menu');
  const menuOps = document.getElementById('menu-operations');
  if (btnOpsMenu && menuOps) {
    btnOpsMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      if (menuDisburse) menuDisburse.classList.remove('show');
      menuOps.classList.toggle('show');
    });
    document.addEventListener('click', () => menuOps.classList.remove('show'));
  }

  // Delete Month Modal Events
  const deleteModal = document.getElementById('modal-delete-data');
  const btnOpenDeleteSide = document.getElementById('btn-open-delete-modal-side');
  if (btnOpenDeleteSide) btnOpenDeleteSide.addEventListener('click', openDeleteMonthModal);
  const btnMenuDeleteMonth = document.getElementById('btn-menu-delete-month');
  if (btnMenuDeleteMonth) btnMenuDeleteMonth.addEventListener('click', openDeleteMonthModal);
  const btnCloseDelete = document.getElementById('btn-close-delete-data');
  if (btnCloseDelete) btnCloseDelete.addEventListener('click', () => deleteModal.classList.remove('active'));
  const btnCancelDelete = document.getElementById('btn-cancel-delete-data');
  if (btnCancelDelete) btnCancelDelete.addEventListener('click', () => deleteModal.classList.remove('active'));
  const btnExecuteDelete = document.getElementById('btn-execute-delete-data');
  if (btnExecuteDelete) btnExecuteDelete.addEventListener('click', executeDeleteMonth);

  const deleteConfirmInput = document.getElementById('delete-confirm-input');
  if (deleteConfirmInput) {
    deleteConfirmInput.addEventListener('input', (e) => {
      const match = e.target.value.trim().toUpperCase() === 'DELETE';
      if (btnExecuteDelete) {
        btnExecuteDelete.disabled = !match;
        btnExecuteDelete.style.opacity = match ? '1' : '0.45';
        btnExecuteDelete.style.cursor = match ? 'pointer' : 'not-allowed';
      }
    });
  }

  const deleteMonthSelect = document.getElementById('delete-month-select');
  if (deleteMonthSelect) {
    deleteMonthSelect.addEventListener('change', (e) => {
      updateDeleteMonthBadge(e.target.value);
    });
  }

  // Export NEFT CSV
  const itemExportNeft = document.getElementById('item-export-neft');
  if (itemExportNeft) {
    itemExportNeft.addEventListener('click', () => {
      const fn = `SVCET_Bank_NEFT_Transfer_${getCleanMonth()}.csv`;
      showToast(`⚡ Downloading Bank Corporate NEFT (${fn})...`);
      triggerFileDownload(`/api/salary/export-neft?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`, fn);
    });
  }

  // Export Bulk Pay Slips ZIP
  const itemExportZip = document.getElementById('item-export-slips-zip');
  if (itemExportZip) {
    itemExportZip.addEventListener('click', () => {
      const fn = `SVCET_PaySlips_${getCleanMonth()}.zip`;
      showToast(`📦 Generating Official PDF Pay Slips (${fn})...`);
      triggerFileDownload(`/api/salary/export-slips-zip?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`, fn);
    });
  }

  // Export Merged Pay Slips PDF
  const itemExportPdf = document.getElementById('item-export-slips-pdf');
  if (itemExportPdf) {
    itemExportPdf.addEventListener('click', () => {
      const fn = `SVCET_Consolidated_PaySlips_${getCleanMonth()}.pdf`;
      showToast(`📄 Generating Consolidated Multi-Page PDF (${fn})...`);
      triggerFileDownload(`/api/salary/export-slips-pdf?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`, fn);
    });
  }

  // Executive Summary Modal
  const execModal = document.getElementById('modal-executive-summary');
  const itemOpenExec = document.getElementById('item-open-exec-summary');
  if (itemOpenExec) itemOpenExec.addEventListener('click', openExecutiveSummaryModal);
  const btnCloseExec = document.getElementById('btn-close-exec-summary');
  if (btnCloseExec) btnCloseExec.addEventListener('click', () => execModal.classList.remove('active'));
  const btnDoneExec = document.getElementById('btn-done-exec-summary');
  if (btnDoneExec) btnDoneExec.addEventListener('click', () => execModal.classList.remove('active'));
  const btnPrintExec = document.getElementById('btn-print-exec-summary');
  if (btnPrintExec) btnPrintExec.addEventListener('click', () => window.print());

  // Cash Denominations Modal
  const cashModal = document.getElementById('modal-cash-denominations');
  const itemOpenCash = document.getElementById('item-open-cash-denominations');
  if (itemOpenCash) itemOpenCash.addEventListener('click', openCashDenominationsModal);
  const btnCloseCash = document.getElementById('btn-close-cash-denom');
  if (btnCloseCash) btnCloseCash.addEventListener('click', () => cashModal.classList.remove('active'));
  const btnDoneCash = document.getElementById('btn-done-cash-denom');
  if (btnDoneCash) btnDoneCash.addEventListener('click', () => cashModal.classList.remove('active'));
  const btnPrintCash = document.getElementById('btn-print-cash-denom');
  if (btnPrintCash) btnPrintCash.addEventListener('click', () => window.print());
}

// Switch Dashboard Mode: 'unified', 'attendance', or 'salary'
function switchDashboardMode(mode) {
  currentDashboardMode = mode || 'unified';

  // Highlight active pill in switcher cluster
  const modeCluster = document.getElementById('view-mode-cluster');
  if (modeCluster) {
    modeCluster.querySelectorAll('.view-pill').forEach(btn => {
      if (btn.dataset.mode === currentDashboardMode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }


  renderTable();
}

function setFilterPill(filterName) {
  const filterSelect = document.getElementById('filter-select');
  const btnClearFilter = document.getElementById('btn-clear-filter');

  if (filterSelect) {
    filterSelect.value = filterName;
    if (filterName !== 'all') {
      filterSelect.classList.add('filter-active');
      if (btnClearFilter) btnClearFilter.style.display = 'inline-flex';
    } else {
      filterSelect.classList.remove('filter-active');
      if (btnClearFilter) btnClearFilter.style.display = 'none';
    }
  }

  document.querySelectorAll('.filter-tabs .tab-pill').forEach(b => {
    if (b.dataset.filter === filterName) b.classList.add('active');
    else b.classList.remove('active');
  });

  // Keep sidebar category pills synchronized
  document.querySelectorAll('.sidebar-cat-pill').forEach(b => {
    if (b.dataset.sidebarFilter === filterName) b.classList.add('active');
    else b.classList.remove('active');
  });

  currentFilter = filterName;
  renderTable();
  const tableSec = document.getElementById('table-section');
  if (tableSec) tableSec.scrollIntoView({ behavior: 'smooth' });
}

function handleHeaderSort(type) {
  const sortSelect = document.getElementById('sort-select');
  if (type === 'bus') {
    currentSort = (currentSort === 'bus_desc') ? 'bus_asc' : 'bus_desc';
  } else if (type === 'mess') {
    currentSort = (currentSort === 'mess_desc') ? 'mess_asc' : 'mess_desc';
  } else if (type === 'hostel') {
    currentSort = (currentSort === 'hostel_desc') ? 'hostel_asc' : 'hostel_desc';
  } else if (type === 'ded') {
    currentSort = (currentSort === 'ded_desc') ? 'ded_asc' : 'ded_desc';
  } else if (type === 'net') {
    currentSort = (currentSort === 'net_desc') ? 'net_asc' : 'net_desc';
  } else if (type === 'gross') {
    currentSort = (currentSort === 'gross_desc') ? 'code_asc' : 'gross_desc';
  } else if (type === 'days') {
    currentSort = (currentSort === 'days_desc') ? 'code_asc' : 'days_desc';
  } else if (type === 'name') {
    currentSort = (currentSort === 'name_asc') ? 'code_asc' : 'name_asc';
  } else if (type === 'code') {
    currentSort = 'code_asc';
  }
  if (sortSelect) sortSelect.value = currentSort;
  renderTable();
}

// Load available months from DB
async function loadMonths() {
  try {
    const res = await fetch('/api/months');
    const data = await res.json();
    if (data.status === 'success' && data.months.length > 0) {
      const select = document.getElementById('month-select');
      select.innerHTML = '';
      data.months.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        if (m === currentMonth) opt.selected = true;
        select.appendChild(opt);
      });
      if (data.months.includes('August -2026')) {
        currentMonth = 'August -2026';
        select.value = 'August -2026';
      } else if (!data.months.includes(currentMonth)) {
        currentMonth = data.months[0];
        select.value = data.months[0];
      }
    }
    loadData();
  } catch (err) {
    console.error('Error loading months:', err);
    loadData();
  }
}

// Load both attendance and salary data concurrently for the Single Unified Dashboard
async function loadData() {
  try {
    const [resAtt, resSal] = await Promise.all([
      fetch(`/api/data?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`),
      fetch(`/api/salary/data?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`)
    ]);

    const dataAtt = await resAtt.json();
    let dataSal = {};
    try {
      dataSal = await resSal.json();
    } catch (e) {
      console.warn('Salary response parse notice:', e);
    }

    if (dataAtt && dataAtt.status === 'success') {
      allEmployees = dataAtt.employees || [];
      allSalaryRecords = (dataSal && dataSal.records) || [];
      buildUnifiedRecords(dataAtt.stats || {}, (dataSal && dataSal.stats) || {});
      populateDepartmentSelect(dataAtt.departments || []);
      if (dataSal && dataSal.categories) populateCategorySelect(dataSal.categories);
      renderTable();
    } else {
      showToast('No attendance records found for this month');
    }
  } catch (err) {
    console.error('Error fetching unified data:', err);
    showToast('Error loading platform data');
  }
}

// Merge Attendance & Salary data by emp_code into a Single Master Model
function buildUnifiedRecords(attStats, salStats) {
  const salMap = new Map();
  allSalaryRecords.forEach(s => salMap.set(String(s.emp_code), s));

  unifiedRecords = allEmployees.map(att => {
    const code = String(att.emp_code);
    const sal = salMap.get(code) || {};

    const monthDays = att.days_in_month || sal.days_in_month || 31;
    const payDays = (sal.total_pay_days !== undefined && sal.total_pay_days !== null) 
                    ? Number(sal.total_pay_days) 
                    : (att.total_pay_days !== undefined ? Number(att.total_pay_days) : monthDays);
    
    const baseSalary = Number(sal.base_salary || 0);
    const grossSalary = (sal.gross_salary !== undefined && sal.gross_salary !== null)
                        ? Number(sal.gross_salary) 
                        : Math.round((baseSalary / monthDays) * payDays);

    const pt = Number(sal.pt_deduction || 0);
    const wf = Number(sal.wf_deduction || 0);
    const epf = Number(sal.epf_deduction || 0);
    const it = Number(sal.it_deduction || 0);
    const bus = Number(sal.bus_deduction || 0);
    const hostel = Number(sal.hostel_eb_deduction || 0);
    const mess = Number(sal.mess_deduction || 0);
    const other = Number(sal.other_deductions || 0);
    const totalDed = (sal.total_deductions !== undefined && sal.total_deductions !== null) 
                     ? Number(sal.total_deductions) 
                     : (pt + wf + epf + it + bus + hostel + mess + other);
    
    const netSalary = (sal.net_salary !== undefined && sal.net_salary !== null)
                      ? Number(sal.net_salary)
                      : Math.max(0, grossSalary - totalDed);

    let cl = Number(att.availed_leaves !== undefined && att.availed_leaves !== null ? att.availed_leaves : (att.cl_days || 0));
    const clList = Array.isArray(att.cl_days_list) ? att.cl_days_list : [];
    if (cl === 0 && clList.length > 0) {
      cl = clList.length;
    }

    let od = Number(att.sv_od !== undefined && att.sv_od !== null ? att.sv_od : (att.od_days || 0));
    const odList = Array.isArray(att.od_days_list) ? att.od_days_list : [];
    if (od === 0 && odList.length > 0) {
      od = odList.length;
    }

    const present = Number(att.biometric_present_days !== undefined ? att.biometric_present_days : (att.present_days || payDays));
    const lopDays = Math.max(0, Math.round((monthDays - payDays) * 10) / 10);

    return {
      ...att,
      ...sal,
      emp_code: code,
      name: att.name || sal.name || 'Staff',
      department: att.department || sal.department || 'General',
      category: sal.category || att.category || 'Non-Teaching',
      designation: att.designation || sal.designation || 'Staff',
      month_days: monthDays,
      present_days: present,
      cl_days: cl,
      od_days: od,
      cl_days_list: Array.isArray(att.cl_days_list) ? att.cl_days_list : [],
      od_days_list: Array.isArray(att.od_days_list) ? att.od_days_list : [],
      lop_days: lopDays,
      total_pay_days: payDays,
      base_salary: baseSalary,
      gross_salary: grossSalary,
      pt_deduction: pt,
      wf_deduction: wf,
      epf_deduction: epf,
      it_deduction: it,
      bus_deduction: bus,
      hostel_eb_deduction: hostel,
      mess_deduction: mess,
      other_deductions: other,
      total_deductions: totalDed,
      net_salary: netSalary,
      account_no: sal.account_no || '',
      ifsc_code: sal.ifsc_code || '',
      bank_name: sal.bank_name || '',
      needs_review: Boolean(att.needs_review || (att.missed_punch_days > 0) || (lopDays > 0)),
      is_vip: Boolean(att.attendance_policy === 'exempt_full' || att.is_vip)
    };
  });

  renderUnifiedKPIs(attStats, salStats);
}

// Render the 6-Card Executive Master KPI Strip
function renderUnifiedKPIs(attStats, salStats) {
  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  const totalStaff = (attStats && attStats.total_staff) || unifiedRecords.length;
  const elStaff = document.getElementById('stat-total-staff');
  if (elStaff) elStaff.textContent = totalStaff;

  // Store raw salary values globally so we can mask/unmask without re-fetching
  window._kpiSalaryData = {
    budget:  salStats ? (salStats.total_payroll_budget || 0) : 0,
    gross:   salStats ? (salStats.total_gross_disbursed || 0) : 0,
    ded:     salStats ? (salStats.total_all_deductions || 0) : 0,
    net:     salStats ? (salStats.total_net_disbursed || 0) : 0
  };

  // Apply mask based on current lock state
  updateSalaryKPIMask();

  const elDays = document.getElementById('stat-total-pay-days');
  if (elDays) {
    const monthDays = (unifiedRecords.length > 0 && unifiedRecords[0].month_days) ? unifiedRecords[0].month_days : 31;
    elDays.textContent = `${monthDays} Days`;
  }
  const elSubDays = document.getElementById('stat-sub-month-days');
  if (elSubDays) {
    elSubDays.textContent = `${currentMonth || 'August -2026'}`;
  }

  const navReview = document.getElementById('nav-review-count');
  if (navReview) navReview.textContent = attStats.needs_review_count || 0;

  const navVip = document.getElementById('nav-vip-count');
  if (navVip) navVip.textContent = attStats.vip_count || 0;

  // Filter Counter Badges & Dropdown Options
  const busCount = unifiedRecords.filter(r => (Number(r.bus_deduction) || 0) > 0).length;
  const messCount = unifiedRecords.filter(r => (Number(r.mess_deduction) || 0) > 0).length;
  const hostelCount = unifiedRecords.filter(r => (Number(r.hostel_eb_deduction) || 0) > 0).length;
  const dedCount = unifiedRecords.filter(r => (Number(r.total_deductions) || 0) > 0).length;
  const teachCount = unifiedRecords.filter(r => r.category === 'Teaching').length;
  const nonTeachCount = unifiedRecords.filter(r => r.category === 'Non-Teaching').length;
  const suppCount = unifiedRecords.filter(r => ['Transport', 'Attender', 'Garden Staff', 'Security'].includes(r.category)).length;
  const lopCount = unifiedRecords.filter(r => r.needs_review || (Number(r.lop_days) || 0) > 0).length;
  const vipCount = unifiedRecords.filter(r => r.is_vip || r.attendance_policy !== 'standard').length;
  const noBankCount = unifiedRecords.filter(r => !r.account_no || r.account_no.trim() === '' || r.account_no === 'Pending').length;

  // Update Dropdown Options with Live Counts
  const optAll = document.getElementById('opt-all');
  if (optAll) optAll.textContent = `👥 All Staff (${unifiedRecords.length})`;
  const optTeaching = document.getElementById('opt-teaching');
  if (optTeaching) optTeaching.textContent = `🎓 Teaching (${teachCount})`;
  const optNonTeaching = document.getElementById('opt-non-teaching');
  if (optNonTeaching) optNonTeaching.textContent = `👔 Non-Teaching (${nonTeachCount})`;
  const optSupport = document.getElementById('opt-support');
  if (optSupport) optSupport.textContent = `🧹 Support (${suppCount})`;
  const optBus = document.getElementById('opt-bus');
  if (optBus) optBus.textContent = `🚌 Bus Fee (${busCount})`;
  const optMess = document.getElementById('opt-mess');
  if (optMess) optMess.textContent = `🍽️ Mess Fee (${messCount})`;
  const optHostel = document.getElementById('opt-hostel');
  if (optHostel) optHostel.textContent = `🏠 Hostel / EB (${hostelCount})`;
  const optDed = document.getElementById('opt-ded');
  if (optDed) optDed.textContent = `📉 Has Deductions (${dedCount})`;
  const optReview = document.getElementById('opt-review');
  if (optReview) optReview.textContent = `⚠️ Has LOP (${lopCount})`;
  const optVip = document.getElementById('opt-vip');
  if (optVip) optVip.textContent = `👑 Full Pay (${vipCount})`;
  const optMissingBank = document.getElementById('opt-missing-bank');
  if (optMissingBank) optMissingBank.textContent = `🏦 No Bank Details (${noBankCount})`;

  // Sidebar badges
  const elBus = document.getElementById('count-bus');
  if (elBus) elBus.textContent = busCount;
  const sideBus = document.getElementById('side-count-bus');
  if (sideBus) sideBus.textContent = busCount;

  const elMess = document.getElementById('count-mess');
  if (elMess) elMess.textContent = messCount;
  const sideMess = document.getElementById('side-count-mess');
  if (sideMess) sideMess.textContent = messCount;

  const elHostel = document.getElementById('count-hostel');
  if (elHostel) elHostel.textContent = hostelCount;
  const sideHostel = document.getElementById('side-count-hostel');
  if (sideHostel) sideHostel.textContent = hostelCount;

  const elDedPill = document.getElementById('count-ded');
  if (elDedPill) elDedPill.textContent = dedCount;
  const sideDed = document.getElementById('side-count-ded');
  if (sideDed) sideDed.textContent = dedCount;
}

// Mask or unmask salary KPI cards based on showSalaryColumns
function updateSalaryKPIMask() {
  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  const locked = !showSalaryColumns;
  const d = window._kpiSalaryData || {};

  const lockedHtml = '<span style="font-size:0.78rem;letter-spacing:0.5px;opacity:0.7;">🔒 Locked</span>';

  const elBudget = document.getElementById('stat-total-budget');
  if (elBudget) elBudget.innerHTML = locked ? lockedHtml : f(d.budget);

  const elGross = document.getElementById('stat-total-gross');
  if (elGross) elGross.innerHTML = locked ? lockedHtml : f(d.gross);

  const elDed = document.getElementById('stat-total-deductions');
  if (elDed) elDed.innerHTML = locked ? lockedHtml : f(d.ded);

  const elNet = document.getElementById('stat-total-net');
  if (elNet) elNet.innerHTML = locked ? lockedHtml : f(d.net);

  // Dim/highlight the stat cards visually
  ['stat-total-budget','stat-total-gross','stat-total-deductions','stat-total-net'].forEach(id => {
    const card = document.getElementById(id)?.closest('.stat-card');
    if (card) {
      card.style.opacity = locked ? '0.65' : '1';
      card.style.filter = locked ? 'grayscale(0.4)' : 'none';
      card.style.cursor = locked ? 'pointer' : '';
      card.title = locked ? 'Click 🔒 Salary Columns: Locked to reveal' : '';
      // Click to open PIN if locked
      card.onclick = locked ? openPinModal : null;
    }
  });

  // Hide / show salary-gated toolbar buttons (Banking, Export Salary, Bulk Adjust, Variance)
  document.querySelectorAll('.salary-gated').forEach(el => {
    el.style.display = locked ? 'none' : '';
  });
}

function populateDepartmentSelect(depts) {
  const select = document.getElementById('dept-select');
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = '<option value="all">All Departments</option>';
  const sortedDepts = [...depts].sort((a, b) => {
    const idxA = getDeptOrderIndex(a);
    const idxB = getDeptOrderIndex(b);
    if (idxA !== idxB) return idxA - idxB;
    return String(a || '').localeCompare(String(b || ''));
  });
  sortedDepts.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    if (d === currentVal) opt.selected = true;
    select.appendChild(opt);
  });
}

function populateCategorySelect(cats) {
  const select = document.getElementById('category-select');
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = '<option value="all">All Categories</option>';
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    if (c === currentVal) opt.selected = true;
    select.appendChild(opt);
  });
}

// -----------------------------------------------------------------------------
// SALARY COLUMNS VISIBILITY TOGGLE (PRINCIPAL SIR REQUEST)
// -----------------------------------------------------------------------------
function updateSalaryToggleUI() {
  const btn = document.getElementById('btn-toggle-salary-cols');
  const icon = document.getElementById('salary-toggle-icon');
  const text = document.getElementById('salary-toggle-text');
  if (!btn) return;

  if (showSalaryColumns) {
    btn.classList.add('salary-revealed');
    btn.title = 'Click to lock salary columns';
    if (icon) icon.textContent = '👁️';
    if (text) text.textContent = '🔓 Salary Visible';
    _showLockBanner();
  } else {
    btn.classList.remove('salary-revealed');
    btn.title = 'Enter PIN to reveal salary columns (Principal instruction)';
    if (icon) icon.textContent = '🔒';
    if (text) text.textContent = 'Salary Columns: Locked';
    _hideLockBanner();
  }

  // Sync KPI cards to lock/unlock state
  updateSalaryKPIMask();
}

// ─────────────────────────────────────────────────────────────────
// FLOATING LOCK BANNER — Small draggable pill
// ─────────────────────────────────────────────────────────────────
function _showLockBanner() {
  let pill = document.getElementById('salary-lock-banner');
  if (!pill) {
    pill = document.createElement('div');
    pill.id = 'salary-lock-banner';
    pill.innerHTML = `
      <span class="slb-drag-handle" title="Drag to move">⠿</span>
      <span class="slb-icon">🔓</span>
      <span class="slb-label">Salary Open</span>
      <button class="slb-btn" onclick="lockSalaryNow()" title="Click to lock salary">🔒 Lock</button>
    `;
    document.body.appendChild(pill);
    _makeDraggable(pill);
  }
  pill.classList.add('visible');
}

function _makeDraggable(el) {
  let startX, startY, startLeft, startTop, dragging = false;
  const handle = el.querySelector('.slb-drag-handle') || el;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = el.getBoundingClientRect();
    startLeft = rect.left;
    startTop = rect.top;
    el.style.transition = 'none';
    el.style.left = startLeft + 'px';
    el.style.top = startTop + 'px';
    el.style.bottom = 'auto';
    el.style.transform = 'none';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    el.style.left = (startLeft + dx) + 'px';
    el.style.top  = (startTop  + dy) + 'px';
  });

  document.addEventListener('mouseup', () => {
    dragging = false;
    document.body.style.userSelect = '';
    el.style.transition = '';
  });

  // Touch support
  handle.addEventListener('touchstart', (e) => {
    const t = e.touches[0];
    startX = t.clientX; startY = t.clientY;
    const rect = el.getBoundingClientRect();
    startLeft = rect.left; startTop = rect.top;
    el.style.transition = 'none';
    el.style.left = startLeft + 'px';
    el.style.top = startTop + 'px';
    el.style.bottom = 'auto';
    el.style.transform = 'none';
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (!el.classList.contains('visible')) return;
    const t = e.touches[0];
    el.style.left = (startLeft + t.clientX - startX) + 'px';
    el.style.top  = (startTop  + t.clientY - startY) + 'px';
  }, { passive: true });
}

function _hideLockBanner() {
  const pill = document.getElementById('salary-lock-banner');
  if (pill) pill.classList.remove('visible');
}

function lockSalaryNow() {
  showSalaryColumns = false;
  updateSalaryToggleUI();
  renderTable();
  showToast('🔒 Salary columns locked');
}

// ─────────────────────────────────────────────────────────────────
// PIN LOCK MODAL FUNCTIONS
// ─────────────────────────────────────────────────────────────────
function openPinModal() {
  _pinBuffer = '';
  _pinMode = 'unlock';
  _pinNewCandidate = '';
  const modal = document.getElementById('modal-salary-pin');
  if (!modal) return;
  document.getElementById('pin-lock-icon').textContent = '🔐';
  document.getElementById('pin-subtitle').textContent = 'Enter 4-digit PIN to reveal salary';
  document.getElementById('pin-error-msg').textContent = '';
  document.getElementById('btn-change-pin').style.display = '';
  _updatePinDots();
  modal.classList.add('active');
  // Keyboard support
  document.addEventListener('keydown', _pinKeyboardHandler);
}

function closePinModal() {
  const modal = document.getElementById('modal-salary-pin');
  if (modal) modal.classList.remove('active');
  _pinBuffer = '';
  document.removeEventListener('keydown', _pinKeyboardHandler);
}

function _pinKeyboardHandler(e) {
  if (e.key >= '0' && e.key <= '9') { pinKeyPress(parseInt(e.key)); }
  else if (e.key === 'Backspace') { pinDelete(); }
  else if (e.key === 'Escape') { closePinModal(); }
  else if (e.key === 'Delete') { pinClear(); }
}

function pinKeyPress(digit) {
  if (_pinBuffer.length >= 4) return;
  _pinBuffer += String(digit);
  _updatePinDots();
  if (_pinBuffer.length === 4) {
    setTimeout(_processPinSubmit, 180);
  }
}

function pinDelete() {
  _pinBuffer = _pinBuffer.slice(0, -1);
  _updatePinDots();
  document.getElementById('pin-error-msg').textContent = '';
}

function pinClear() {
  _pinBuffer = '';
  _updatePinDots();
  document.getElementById('pin-error-msg').textContent = '';
}

function _updatePinDots() {
  for (let i = 0; i < 4; i++) {
    const dot = document.getElementById(`pin-dot-${i}`);
    if (!dot) continue;
    dot.classList.toggle('filled', i < _pinBuffer.length);
    dot.classList.toggle('active', i === _pinBuffer.length);
  }
}

function _processPinSubmit() {
  const errEl = document.getElementById('pin-error-msg');
  const iconEl = document.getElementById('pin-lock-icon');

  if (_pinMode === 'unlock') {
    if (_pinBuffer === _getSavedPin()) {
      // ✅ Correct PIN
      iconEl.textContent = '✅';
      setTimeout(() => {
        closePinModal();
        showSalaryColumns = true;
        updateSalaryToggleUI();
        renderTable();
        showToast('👁️ Salary columns revealed — click the button again to lock');
      }, 300);
    } else {
      // ❌ Wrong PIN
      iconEl.textContent = '❌';
      errEl.textContent = '❌ Incorrect PIN. Please try again.';
      _pinBuffer = '';
      _updatePinDots();
      // Shake animation
      const card = document.querySelector('.salary-pin-card');
      if (card) { card.classList.add('pin-shake'); setTimeout(() => card.classList.remove('pin-shake'), 500); }
      setTimeout(() => { iconEl.textContent = '🔐'; }, 600);
    }

  } else if (_pinMode === 'set-new') {
    // First entry for change — store candidate
    _pinNewCandidate = _pinBuffer;
    _pinBuffer = '';
    _pinMode = 'confirm-new';
    _updatePinDots();
    document.getElementById('pin-subtitle').textContent = 'Re-enter new PIN to confirm';
    iconEl.textContent = '🔑';
    errEl.textContent = '';

  } else if (_pinMode === 'confirm-new') {
    if (_pinBuffer === _pinNewCandidate) {
      _savePin(_pinBuffer);
      iconEl.textContent = '✅';
      errEl.style.color = '#15803d';
      errEl.textContent = '✅ PIN changed successfully!';
      setTimeout(() => {
        closePinModal();
        showToast('🔑 Salary PIN updated successfully');
      }, 1000);
    } else {
      iconEl.textContent = '❌';
      errEl.style.color = '#dc2626';
      errEl.textContent = '❌ PINs do not match. Try again.';
      _pinBuffer = '';
      _pinMode = 'set-new';
      _pinNewCandidate = '';
      _updatePinDots();
      document.getElementById('pin-subtitle').textContent = 'Enter new 4-digit PIN';
      setTimeout(() => { iconEl.textContent = '🔑'; }, 600);
    }
  }
}

function showChangePinMode() {
  _pinMode = 'set-new';
  _pinBuffer = '';
  _pinNewCandidate = '';
  _updatePinDots();
  document.getElementById('pin-lock-icon').textContent = '🔑';
  document.getElementById('pin-subtitle').textContent = 'Enter new 4-digit PIN';
  document.getElementById('pin-error-msg').textContent = '';
  document.getElementById('btn-change-pin').style.display = 'none';
}

function toggleTableHeight() {
  const wrapper = document.getElementById('table-wrapper');
  const btnText = document.getElementById('table-height-text');
  const btnIcon = document.getElementById('table-height-icon');
  if (!wrapper) return;

  const isExpanded = wrapper.classList.toggle('expanded-view');
  if (isExpanded) {
    if (btnText) btnText.textContent = 'Lock to Screen';
    if (btnIcon) btnIcon.textContent = '🔒';
  } else {
    if (btnText) btnText.textContent = 'Full Expand';
    if (btnIcon) btnIcon.textContent = '⛶';
  }
}

// -----------------------------------------------------------------------------
// RENDER DYNAMIC MASTER TABLE (3 MODES: UNIFIED MASTER, ATTENDANCE, SALARY)
// -----------------------------------------------------------------------------
function renderTable() {
  const thead = document.getElementById('table-head');
  const tbody = document.getElementById('table-body');
  if (!thead || !tbody) return;
  tbody.innerHTML = '';

  const mode = currentDashboardMode || 'unified';

  // 1. Render Table Headers based on Active Dashboard Mode
  if (mode === 'unified') {
    if (showSalaryColumns) {
      thead.innerHTML = `
        <tr>
          <th style="width: 40px; text-align: center;" class="sticky-col-sno">#</th>
          <th style="width: 80px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
          <th style="min-width: 195px; cursor: pointer;" class="sticky-col-name" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
          <th style="width: 65px;">Dept</th>
          
          <!-- Biometric Attendance Columns -->
          <th style="width: 50px; text-align: center;" class="th-section-att" title="Total Calendar Days in Month">Month</th>
          <th style="width: 55px; text-align: center;" class="th-section-att" title="Biometric Punch Present Days">Present</th>
          <th style="width: 58px; text-align: center;" class="th-section-att" title="Casual Leave (CL) Slips - Click to edit directly">CL ✎</th>
          <th style="width: 58px; text-align: center;" class="th-section-att" title="On Duty (OD) Slips - Click to edit directly">OD ✎</th>
          <th style="width: 65px; text-align: center;" class="th-section-att" title="Loss of Pay (Unpaid Absent Days)">LOP</th>
          <th style="width: 68px; text-align: center; cursor: pointer;" class="th-section-att" onclick="handleHeaderSort('days')" title="Sort by Eligible Pay Days - Click to edit directly">Pay Days ✎ ↕</th>
          
          <!-- Financial Salary Columns (Revealed per User Toggle) -->
          <th style="width: 85px; text-align: right;" class="th-section-sal" title="Monthly Base Salary Package - Click to edit directly">Base Rate ✎</th>
          <th style="width: 85px; text-align: right; cursor: pointer;" class="th-section-sal" onclick="handleHeaderSort('gross')" title="Sort by Earned Gross salary computed from Pay Days">Earned Gross ↕</th>
          <th style="width: 65px; text-align: center;" class="th-section-sal" title="AP Statutory Professional Tax Slab (> ₹20,000 = ₹200)">PT (₹200)</th>
          <th style="width: 65px; text-align: center;" class="th-section-sal" title="SVCET Staff Welfare Fund (Teaching = ₹75, Non-Teaching = ₹30)">WF (₹75)</th>
          <th style="width: 68px; text-align: right; cursor: pointer;" class="th-section-sal" onclick="handleHeaderSort('bus')" title="Sort by Bus Transport Fee (Click to toggle High ↔ Low)">Bus ✎ ↕</th>
          <th style="width: 68px; text-align: right; cursor: pointer;" class="th-section-sal" onclick="handleHeaderSort('hostel')" title="Sort by Hostel & Electricity Fee (Click to toggle High ↔ Low)">Hostel ✎ ↕</th>
          <th style="width: 68px; text-align: right; cursor: pointer;" class="th-section-sal" onclick="handleHeaderSort('mess')" title="Sort by Mess & Food Charges (Click to toggle High ↔ Low)">Mess ✎ ↕</th>
          <th style="width: 65px; text-align: right;" class="th-section-sal" title="Other Deductions (Advance, Misc) - Click to edit directly">Other ✎</th>
          <th style="width: 105px; text-align: right; background: #ecfdf5; color: #047857; font-weight: 800; cursor: pointer;" onclick="handleHeaderSort('net')" title="Sort by Net Salary (Click to toggle High ↔ Low)">Net Pay (₹) ↕</th>
          
          <!-- Remarks Column -->
          <th style="min-width: 290px; text-align: left;" title="Biometric Remarks: Absences, Missed Out-Punches, Late Arrivals">Remarks / Policy</th>

          <th style="width: 185px; text-align: center;">Actions</th>
        </tr>
      `;
    } else {
      thead.innerHTML = `
        <tr>
          <th style="width: 40px; text-align: center;" class="sticky-col-sno">#</th>
          <th style="width: 80px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
          <th style="min-width: 195px; cursor: pointer;" class="sticky-col-name" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
          <th style="width: 65px;">Dept</th>
          
          <!-- Biometric Attendance Columns -->
          <th style="width: 50px; text-align: center;" class="th-section-att" title="Total Calendar Days in Month">Month</th>
          <th style="width: 55px; text-align: center;" class="th-section-att" title="Biometric Punch Present Days">Present</th>
          <th style="width: 58px; text-align: center;" class="th-section-att" title="Casual Leave (CL) Slips - Click to edit directly">CL ✎</th>
          <th style="width: 58px; text-align: center;" class="th-section-att" title="On Duty (OD) Slips - Click to edit directly">OD ✎</th>
          <th style="width: 65px; text-align: center;" class="th-section-att" title="Loss of Pay (Unpaid Absent Days)">LOP</th>
          <th style="width: 68px; text-align: center; cursor: pointer;" class="th-section-att" onclick="handleHeaderSort('days')" title="Sort by Eligible Pay Days - Click to edit directly">Pay Days ✎ ↕</th>
          
          <!-- Salary Hidden Placeholder Column (Default per Principal Request) -->
          <th style="width: 150px; text-align: center; background: #fffbeb; color: #b45309; font-size: 0.74rem;" title="Salary columns are hidden per Principal's instruction. Click 'Salary Columns: Hidden' to reveal.">
            🔒 Salary Hidden
          </th>
          
          <!-- Remarks Column -->
          <th style="min-width: 290px; text-align: left;" title="Biometric Remarks: Absences, Missed Out-Punches, Late Arrivals">Remarks / Policy</th>

          <th style="width: 185px; text-align: center;">Actions</th>
        </tr>
      `;
    }
  } else if (mode === 'attendance') {
    thead.innerHTML = `
      <tr>
        <th style="width: 40px; text-align: center;" class="sticky-col-sno">#</th>
        <th style="width: 80px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
        <th style="min-width: 210px; cursor: pointer;" class="sticky-col-name" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Employee Name ↕</th>
        <th style="width: 95px;">Designation</th>
        <th style="width: 75px;">Dept</th>
        <th style="width: 60px; text-align: center;" title="Total Days in Month">Month</th>
        <th style="width: 68px; text-align: center;" title="Biometric Punch Present Days">Biometric</th>
        <th style="width: 65px; text-align: center;" title="Sundays & Institutional Holidays">Holiday</th>
        <th style="width: 68px; text-align: center;" title="Casual Leave (CL) Slips - Click to edit directly">CL ✎</th>
        <th style="width: 68px; text-align: center;" title="On Duty (OD) Slips - Click to edit directly">OD ✎</th>
        <th style="width: 78px; text-align: center; cursor: pointer;" onclick="handleHeaderSort('days')" title="Total Payable Days - Click to edit directly">Pay Days ✎ ↕</th>
        <th style="min-width: 150px;">Remarks / Policy</th>
        <th style="width: 195px; text-align: center;">Actions</th>
      </tr>
    `;
  } else if (mode === 'salary') {
    thead.innerHTML = `
      <tr>
        <th style="width: 40px; text-align: center;" class="sticky-col-sno">#</th>
        <th style="width: 80px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
        <th style="min-width: 195px; cursor: pointer;" class="sticky-col-name" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
        <th style="width: 95px;">Category</th>
        <th style="width: 70px;">Dept</th>
        <th style="width: 70px; text-align: center; cursor: pointer;" onclick="handleHeaderSort('days')" title="Eligible Pay Days - Click to edit directly">Pay Days ✎ ↕</th>
        <th style="width: 90px; text-align: right;" title="Base Monthly Package - Click to edit directly">Base Rate ✎</th>
        <th style="width: 90px; text-align: right; cursor: pointer;" onclick="handleHeaderSort('gross')" title="Earned Gross Salary">Earned Gross ↕</th>
        <th style="width: 68px; text-align: center;" title="AP State Professional Tax">PT (₹200)</th>
        <th style="width: 68px; text-align: center;" title="SVCET Staff Welfare Fund">WF (₹75)</th>
        <th style="width: 70px; text-align: right; cursor: pointer;" onclick="handleHeaderSort('bus')" title="Sort by Bus / Transport Fee (Click to toggle High ↔ Low)">Bus ✎ ↕</th>
        <th style="width: 70px; text-align: right; cursor: pointer;" onclick="handleHeaderSort('hostel')" title="Sort by Hostel / EB Charges (Click to toggle High ↔ Low)">Hostel ✎ ↕</th>
        <th style="width: 70px; text-align: right; cursor: pointer;" onclick="handleHeaderSort('mess')" title="Sort by Mess / Food Charges (Click to toggle High ↔ Low)">Mess ✎ ↕</th>
        <th style="width: 70px; text-align: right;" title="Other / Advance Deductions - Click to edit directly">Other ✎</th>
        <th style="width: 80px; text-align: right; cursor: pointer;" onclick="handleHeaderSort('ded')" title="Sort by Total Statutory & Institutional Deductions">Total Ded ↕</th>
        <th style="width: 110px; text-align: right; background: #ecfdf5; color: #047857; font-weight: 800; cursor: pointer;" onclick="handleHeaderSort('net')" title="Sort by Net Salary (Click to toggle High ↔ Low)">Net Salary (₹) ↕</th>
        <th style="min-width: 150px;">Bank Account & IFSC</th>
        <th style="width: 145px; text-align: center;">Actions</th>
      </tr>
    `;
  }

  const query = (document.getElementById('search-input')?.value || '').toLowerCase().trim();

  const filtered = unifiedRecords.filter(emp => {
    if (currentDept !== 'all' && emp.department !== currentDept) return false;
    if (currentCategory !== 'all' && emp.category !== currentCategory) return false;

    if (currentFilter === 'teaching' && emp.category !== 'Teaching') return false;
    if (currentFilter === 'non-teaching' && emp.category !== 'Non-Teaching') return false;
    if (currentFilter === 'support' && !['Transport', 'Attender', 'Garden Staff', 'Security'].includes(emp.category)) return false;
    if (currentFilter === 'bus' && (!emp.bus_deduction || Number(emp.bus_deduction) <= 0)) return false;
    if (currentFilter === 'mess' && (!emp.mess_deduction || Number(emp.mess_deduction) <= 0)) return false;
    if (currentFilter === 'hostel' && (!emp.hostel_eb_deduction || Number(emp.hostel_eb_deduction) <= 0)) return false;
    if (currentFilter === 'deductions' && (!emp.total_deductions || Number(emp.total_deductions) <= 0)) return false;
    if (currentFilter === 'review' && !emp.needs_review && emp.lop_days <= 0) return false;
    if (currentFilter === 'vip' && !emp.is_vip && emp.attendance_policy === 'standard') return false;
    if (currentFilter === 'missing_bank') {
      const hasAcc = emp.account_no && emp.account_no.trim() !== '' && emp.account_no !== 'Pending';
      if (hasAcc) return false;
    }

    if (query) {
      const matchName = (emp.name || '').toLowerCase().includes(query);
      const matchCode = (emp.emp_code || '').toLowerCase().includes(query);
      const matchDesig = (emp.designation || '').toLowerCase().includes(query);
      if (!matchName && !matchCode && !matchDesig) return false;
    }
    return true;
  });

  // Apply Sorting
  filtered.sort((a, b) => {
    switch (currentSort) {
      case 'mess_desc':
        return (Number(b.mess_deduction) || 0) - (Number(a.mess_deduction) || 0);
      case 'mess_asc':
        return (Number(a.mess_deduction) || 0) - (Number(b.mess_deduction) || 0);
      case 'bus_desc':
        return (Number(b.bus_deduction) || 0) - (Number(a.bus_deduction) || 0);
      case 'bus_asc':
        return (Number(a.bus_deduction) || 0) - (Number(b.bus_deduction) || 0);
      case 'hostel_desc':
        return (Number(b.hostel_eb_deduction) || 0) - (Number(a.hostel_eb_deduction) || 0);
      case 'hostel_asc':
        return (Number(a.hostel_eb_deduction) || 0) - (Number(b.hostel_eb_deduction) || 0);
      case 'ded_desc':
        return (Number(b.total_deductions) || 0) - (Number(a.total_deductions) || 0);
      case 'ded_asc':
        return (Number(a.total_deductions) || 0) - (Number(b.total_deductions) || 0);
      case 'net_desc':
        return (Number(b.net_salary) || 0) - (Number(a.net_salary) || 0);
      case 'net_asc':
        return (Number(a.net_salary) || 0) - (Number(b.net_salary) || 0);
      case 'gross_desc':
        return (Number(b.gross_salary) || 0) - (Number(a.gross_salary) || 0);
      case 'days_desc':
        return (Number(b.total_pay_days) || 0) - (Number(a.total_pay_days) || 0);
      case 'name_asc':
        return (a.name || '').localeCompare(b.name || '');
      case 'code_asc':
      default: {
        const deptIndexA = getDeptOrderIndex(a.department);
        const deptIndexB = getDeptOrderIndex(b.department);
        if (deptIndexA !== deptIndexB) {
          return deptIndexA - deptIndexB;
        }
        if (a.department !== b.department) {
          return String(a.department || '').localeCompare(String(b.department || ''));
        }
        const numA = parseInt(String(a.emp_code).replace(/\D/g, '')) || 0;
        const numB = parseInt(String(b.emp_code).replace(/\D/g, '')) || 0;
        return numA !== numB ? numA - numB : String(a.emp_code).localeCompare(String(b.emp_code));
      }
    }
  });

  const countEl = document.getElementById('table-record-count');
  if (countEl) {
    countEl.textContent = `Master Payroll & Attendance Roster (${filtered.length} Staff)`;
  }

  const totalCols = (mode === 'unified') ? (showSalaryColumns ? 21 : 13) : ((mode === 'attendance') ? 13 : 18);

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${totalCols}" style="text-align: center; padding: 3rem; color: #94a3b8; font-weight: 500;">No employees found matching the selected filter.</td></tr>`;
    return;
  }

  let lastDept = null;
  let sNo = 1;
  const showDeptHeader = (currentSort === 'code_asc' && currentDept === 'all');

  // Pre-calculate count of staff per department in the filtered list
  const deptCounts = {};
  filtered.forEach(e => {
    deptCounts[e.department] = (deptCounts[e.department] || 0) + 1;
  });

  filtered.forEach(emp => {
    if (showDeptHeader && emp.department !== lastDept) {
      lastDept = emp.department;
      const count = deptCounts[lastDept] || 0;
      const deptRow = document.createElement('tr');
      deptRow.className = 'dept-section-row';
      deptRow.innerHTML = `
        <td colspan="${totalCols}" style="background: #f1f5f9; font-weight: 800; color: #1e3a8a; padding: 8px 14px; border-top: 2px solid #cbd5e1; border-bottom: 1px solid #e2e8f0; font-size: 0.85rem; letter-spacing: 0.5px;">
          🏛️ DEPARTMENT: ${lastDept} 
          <span style="font-size: 0.72rem; font-weight: 700; background: white; color: #475569; padding: 2px 8px; border-radius: 9999px; margin-left: 8px; border: 1px solid #cbd5e1;">
            ${count} Staff
          </span>
        </td>`;
      tbody.appendChild(deptRow);
    }

    const tr = document.createElement('tr');
    tr.id = `row-${emp.emp_code}`;

    let catBadge = 'badge-cat-nt';
    if (emp.category === 'Teaching') catBadge = 'badge-cat-teaching';
    else if (emp.category === 'Management') catBadge = 'badge-cat-mgt';
    else if (['Transport', 'Attender', 'Garden Staff', 'Security'].includes(emp.category)) catBadge = 'badge-cat-support';

    if (mode === 'unified') {
      // 🌟 UNIFIED MASTER ROW (Attendance + Salary side-by-side with full editability)
      tr.innerHTML = `
        <td style="text-align: center; color: #94a3b8; font-weight: 600;" class="sticky-col-sno">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;" class="sticky-col-code">${emp.emp_code}</td>
        <td class="sticky-col-name">
          <span class="emp-name-link" onclick="openPortfolio('${emp.emp_code}')" title="Click to view 360° Annual Profile & Leave Passbook">
            <strong>${emp.name}</strong>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
          </span>
          <div style="display:flex; align-items:center; gap: 4px; margin-top: 2px;">
            <span class="badge-pill ${catBadge}">${emp.category}</span>
            <span style="font-size: 0.7rem; color: #94a3b8;">${emp.designation || 'Staff'}</span>
          </div>
        </td>
        <td style="color: #64748b; font-weight: 600; font-size: 0.75rem;">${emp.department}</td>
        
        <!-- Biometric Attendance Columns -->
        <td style="text-align: center; color: #64748b; font-size: 0.8rem;">${emp.month_days}</td>
        <td style="text-align: center; font-weight: 700; color: #1e3a8a;">${emp.present_days}</td>
        
        <!-- Editable CL with exact day numbers & dates -->
        <td style="text-align: center;">
          <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
            <input type="number" step="0.5" min="0" max="31"
                   class="cell-sal-input input-cl" 
                   value="${emp.cl_days || 0}" 
                   title="Casual Leave (CL) Slips - Click to edit directly"
                   onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
            ${renderClDaysBadge(emp)}
          </div>
        </td>
        
        <!-- Editable OD with exact day numbers & dates -->
        <td style="text-align: center;">
          <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
            <input type="number" step="0.5" min="0" max="31"
                   class="cell-sal-input input-od" 
                   value="${emp.od_days || 0}" 
                   title="On Duty (OD) Slips - Click to edit directly"
                   onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'sv_od', this.value, this)">
            ${renderOdDaysBadge(emp)}
          </div>
        </td>
        
        <!-- LOP Badge with Exact Absent/Half/No-Out Breakdown -->
        <td style="text-align: center;">
          ${renderLopCell(emp)}
        </td>
        
        <!-- Directly Editable Payable Days -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-days" 
                 value="${emp.total_pay_days}" 
                 title="Override Payable Days directly"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'total_pay_days', this.value, this)">
        </td>

        ${showSalaryColumns ? `
        <!-- Directly Editable Base Package -->
        <td style="text-align: right;">
          <input type="number" step="500" min="0" 
                 class="cell-sal-input input-money" 
                 value="${emp.base_salary}" 
                 title="Edit monthly base salary package"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'base_salary', this.value, this)">
        </td>

        <!-- Earned Gross Salary -->
        <td style="text-align: right; font-weight: 700; color: #334155;" id="gross-${emp.emp_code}">
          ₹${Math.round(emp.gross_salary).toLocaleString('en-IN')}
        </td>

        <!-- Statutory PT (₹200) -->
        <td style="text-align: center;">
          <span class="statutory-pill statutory-pill-pt" title="Andhra Pradesh State Professional Tax (Gross > ₹20,000 = ₹200)" id="pt-${emp.emp_code}">
            ₹${emp.pt_deduction}
          </span>
        </td>

        <!-- Statutory WF (₹75) -->
        <td style="text-align: center;">
          <span class="statutory-pill statutory-pill-wf" title="SVCET Staff Welfare Fund (Teaching = ₹75, Non-Teaching = ₹30)" id="wf-${emp.emp_code}">
            ₹${emp.wf_deduction}
          </span>
        </td>

        <!-- Bus Transport Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.bus_deduction || 0}" 
                 title="Bus Transport Fee - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'bus_deduction', this.value, this)">
        </td>

        <!-- Hostel & EB Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.hostel_eb_deduction || 0}" 
                 title="Hostel & Electricity Fee - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'hostel_eb_deduction', this.value, this)">
        </td>

        <!-- Mess & Food Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.mess_deduction || 0}" 
                 title="Mess & Food Charges - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'mess_deduction', this.value, this)">
        </td>

        <!-- Editable Other Deductions -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.other_deductions || 0}" 
                 title="Other Deductions (Advance, Misc) - Click to edit directly"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'other_deductions', this.value, this)">
        </td>

        <!-- Net Salary -->
        <td style="text-align: right; background: #ecfdf5;">
          <strong id="net-${emp.emp_code}" style="color: #15803d; font-size: 0.85rem;">
            ₹${Math.round(emp.net_salary).toLocaleString('en-IN')}
          </strong>
        </td>
        ` : `
        <!-- Salary Hidden Placeholder Cell -->
        <td style="text-align: center; background: #fffdf5; color: #94a3b8; font-size: 0.74rem;">
          <span class="badge-pill" style="background:#fef3c7; color:#92400e; font-size:0.7rem; font-weight:700;">🔒 Hidden</span>
        </td>
        `}

        <!-- Remarks / Policy Column -->
        <td style="font-size: 0.75rem; vertical-align: middle;">
          ${renderRemarksBadges(emp)}
        </td>

        <!-- Actions Column -->
        <td style="text-align: center;">
          <div class="row-action-cluster">
            <button class="btn-row-action" style="color: #1e3a8a; font-weight: 800;" onclick="openFormalPaySlip('${emp.emp_code}')" title="Print Official Institutional Pay Slip">
              📄 Slip
            </button>
            <button class="btn-row-action" onclick="openTimelineModal('${emp.emp_code}')" title="View & regularize 1-31 punch logs">
              📅 Punches
            </button>
            <button class="btn-row-action" style="color: #15803d;" onclick="grantFullAttendance('${emp.emp_code}')" title="1-Click Grant 31 Full Pay Days">
              ✔ Full
            </button>
            <button class="btn-row-action btn-row-revert" onclick="revertToOriginal('${emp.emp_code}')" title="↺ Revert back to original raw biometric punches (clears accidental Full Pay / edits)">
              ↺ Revert
            </button>
            <button class="btn-row-action" onclick="openEditPackageModal('${emp.emp_code}')" title="Edit Package & Bank Details">
              ✏️ Edit
            </button>
          </div>
        </td>
      `;
    } else if (mode === 'attendance') {
      // 📋 ATTENDANCE GRID ROW (Dedicated Biometric & Leave focus)
      let remarkBadges = '';
      if (emp.is_vip || emp.attendance_policy === 'exempt_full') {
        remarkBadges = '<span class="badge-pill badge-vip" style="font-size:0.7rem;">👑 Full Pay VIP</span>';
      } else if (emp.remarks) {
        remarkBadges = `<span style="font-size:0.75rem; color:#64748b;">${emp.remarks}</span>`;
      } else {
        remarkBadges = '<span style="font-size:0.75rem; color:#10b981;">✔ Clean Record</span>';
      }

      tr.innerHTML = `
        <td style="text-align: center; color: #94a3b8; font-weight: 600;" class="sticky-col-sno">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;" class="sticky-col-code">${emp.emp_code}</td>
        <td class="sticky-col-name">
          <span class="emp-name-link" onclick="openPortfolio('${emp.emp_code}')" title="Click to view 360° Annual Leave Passbook">
            <strong>${emp.name}</strong>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
          </span>
          <div style="font-size: 0.7rem; color: #94a3b8;">${emp.category}</div>
        </td>
        <td style="font-size: 0.78rem; color: #475569;">${emp.designation || 'Staff'}</td>
        <td style="color: #64748b; font-weight: 600; font-size: 0.78rem;">${emp.department}</td>
        <td style="text-align: center; color: #64748b; font-size: 0.8rem;">${emp.month_days}</td>
        <td style="text-align: center; font-weight: 700; color: #1e3a8a;">${emp.present_days}</td>
        <td style="text-align: center; color: #0369a1; font-size: 0.8rem;">${emp.holiday || 6}</td>
        
        <!-- Editable CL with exact day numbers & dates -->
        <td style="text-align: center;">
          <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
            <input type="number" step="0.5" min="0" max="31"
                   class="cell-sal-input input-cl" 
                   value="${emp.cl_days || 0}" 
                   title="Edit Casual Leave (CL)"
                   onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
            ${renderClDaysBadge(emp)}
          </div>
        </td>
        
        <!-- Editable OD with exact day numbers & dates -->
        <td style="text-align: center;">
          <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
            <input type="number" step="0.5" min="0" max="31"
                   class="cell-sal-input input-od" 
                   value="${emp.od_days || 0}" 
                   title="Edit On-Duty (OD)"
                   onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'sv_od', this.value, this)">
            ${renderOdDaysBadge(emp)}
          </div>
        </td>
        
        <!-- Editable Pay Days -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-days" 
                 value="${emp.total_pay_days}" 
                 title="Directly override Payable Days"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'total_pay_days', this.value, this)">
        </td>

        <td>${remarkBadges}</td>

        <!-- Actions -->
        <td style="text-align: center;">
          <div class="row-action-cluster">
            <button class="btn-row-action" onclick="openTimelineModal('${emp.emp_code}')" title="View 1-31 Daily Punch Calendar">
              📅 Punches
            </button>
            <button class="btn-row-action" style="color: #15803d; font-weight: 700;" onclick="grantFullAttendance('${emp.emp_code}')" title="1-Click Grant 31 Full Days">
              ✔ Full Pay
            </button>
            <button class="btn-row-action btn-row-revert" onclick="revertToOriginal('${emp.emp_code}')" title="↺ Revert back to original raw biometric punches (clears accidental Full Pay / edits)">
              ↺ Revert
            </button>
            <button class="btn-row-action" onclick="openPortfolio('${emp.emp_code}')" title="Open 360° Leave Passbook">
              👤 360°
            </button>
          </div>
        </td>
      `;
    } else if (mode === 'salary') {
      // 💰 SALARY & BANK LEDGER ROW (Financial payroll focus)
      tr.innerHTML = `
        <td style="text-align: center; color: #94a3b8; font-weight: 600;" class="sticky-col-sno">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;" class="sticky-col-code">${emp.emp_code}</td>
        <td class="sticky-col-name">
          <span class="emp-name-link" onclick="openFormalPaySlip('${emp.emp_code}')" title="Click to view Official Printable Pay Slip">
            <strong>${emp.name}</strong>
          </span>
          <div style="font-size: 0.7rem; color: #94a3b8;">${emp.designation || 'Staff'}</div>
        </td>
        <td><span class="badge-pill ${catBadge}">${emp.category}</span></td>
        <td style="color: #64748b; font-weight: 600; font-size: 0.78rem;">${emp.department}</td>
        
        <!-- Editable Pay Days -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-days" 
                 value="${emp.total_pay_days}" 
                 title="Override Payable Days directly"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'total_pay_days', this.value, this)">
        </td>

        <!-- Editable Base Package -->
        <td style="text-align: right;">
          <input type="number" step="500" min="0" 
                 class="cell-sal-input input-money" 
                 value="${emp.base_salary}" 
                 title="Edit base salary package"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'base_salary', this.value, this)">
        </td>

        <!-- Earned Gross Salary -->
        <td style="text-align: right; font-weight: 700; color: #334155;" id="gross-${emp.emp_code}">
          ₹${Math.round(emp.gross_salary).toLocaleString('en-IN')}
        </td>

        <!-- Statutory PT (₹200) -->
        <td style="text-align: center;">
          <span class="statutory-pill statutory-pill-pt" title="Andhra Pradesh State Professional Tax (Gross > ₹20k = ₹200)">
            ₹${emp.pt_deduction}
          </span>
        </td>

        <!-- Statutory WF (₹75) -->
        <td style="text-align: center;">
          <span class="statutory-pill statutory-pill-wf" title="SVCET Staff Welfare Fund (Teaching = ₹75, Non-Teaching = ₹30)">
            ₹${emp.wf_deduction}
          </span>
        </td>

        <!-- Bus Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.bus_deduction || 0}" 
                 title="Bus Transport Fee - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'bus_deduction', this.value, this)">
        </td>

        <!-- Hostel & EB Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.hostel_eb_deduction || 0}" 
                 title="Hostel & Electricity Fee - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'hostel_eb_deduction', this.value, this)">
        </td>

        <!-- Mess Deduction -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.mess_deduction || 0}" 
                 title="Mess & Food Charges - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'mess_deduction', this.value, this)">
        </td>

        <!-- Editable Other Deductions -->
        <td style="text-align: right;">
          <input type="number" step="10" min="0" 
                 class="cell-sal-input input-ded" 
                 value="${emp.other_deductions || 0}" 
                 title="Other Deductions (Advance, Misc) - Click to edit"
                 onchange="handleUnifiedInlineEdit('${emp.emp_code}', 'other_deductions', this.value, this)">
        </td>

        <!-- Total Deductions -->
        <td style="text-align: right; font-weight: 700; color: #b45309;" id="ded-${emp.emp_code}">
          ₹${Math.round(emp.total_deductions).toLocaleString('en-IN')}
        </td>

        <!-- Net Salary -->
        <td style="text-align: right; background: #ecfdf5;">
          <strong id="net-${emp.emp_code}" style="color: #15803d; font-size: 0.88rem;">
            ₹${Math.round(emp.net_salary).toLocaleString('en-IN')}
          </strong>
        </td>

        <!-- Bank Account & IFSC -->
        <td>
          <div style="font-size: 0.76rem; font-weight: 700; color: #0f172a;">
            ${(emp.account_no && emp.account_no !== 'Pending') ? emp.account_no : '<span style="color:#ef4444;">Pending</span>'}
          </div>
          <div style="font-size: 0.68rem; color: #64748b;">
            ${emp.bank_name || 'PNB'} • ${emp.ifsc_code || 'PUNB0401700'}
          </div>
        </td>

        <!-- Actions Column -->
        <td style="text-align: center;">
          <div class="row-action-cluster">
            <button class="btn-row-action" style="color: #1e3a8a; font-weight: 800;" onclick="openFormalPaySlip('${emp.emp_code}')" title="Print Official Pay Slip">
              🖨️ Slip
            </button>
            <button class="btn-row-action btn-row-revert" onclick="revertToOriginal('${emp.emp_code}')" title="↺ Reset to standard package (clears temporary overrides)">
              ↺ Reset
            </button>
            <button class="btn-row-action" onclick="openEditPackageModal('${emp.emp_code}')" title="Edit Package & Bank Details">
              ⚙️ Edit
            </button>
          </div>
        </td>
      `;
    }

    tbody.appendChild(tr);
  });
}

// Inline Edit Handler for Attendance Fields (CL / OD)
async function handleAttendanceInlineEdit(empCode, field, value, inputEl) {
  try {
    inputEl.classList.remove('saved');
    const numVal = value === '' ? 0 : parseFloat(value);

    // 1. Send update to backend attendance engine
    const res = await fetch('/api/update-employee', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        emp_code: empCode,
        field: field,
        value: numVal,
        month_year: currentMonth
      })
    });
    const data = await res.json();

    if (data.status === 'success') {
      inputEl.classList.add('saved');
      setTimeout(() => inputEl.classList.remove('saved'), 1500);

      showToast(`✔ Updated ${field === 'availed_leaves' ? 'CL (Leaves)' : 'On-Duty (OD)'} for Emp ${empCode}`);
      await loadData();
    }
  } catch (err) {
    alert('Error saving attendance update');
  }
}

// Inline Edit Handler for Salary & Unified Dashboard (Pay Days, Base Rate, Other Deductions)
async function handleUnifiedInlineEdit(empCode, field, value, inputEl) {
  try {
    inputEl.classList.remove('saved');
    const numVal = value === '' ? 0 : parseFloat(value);

    // 1. Send update to backend
    const res = await fetch('/api/salary/update-monthly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        emp_code: empCode,
        field: field,
        value: numVal,
        month_year: currentMonth
      })
    });
    const data = await res.json();

    if (data.status === 'success') {
      inputEl.classList.add('saved');
      setTimeout(() => inputEl.classList.remove('saved'), 1500);

      // 2. Real-time update of local unified record
      const emp = unifiedRecords.find(r => String(r.emp_code) === String(empCode));
      if (emp) {
        if (field === 'total_pay_days') {
          emp.total_pay_days = numVal;
          emp.lop_days = Math.max(0, Math.round((emp.month_days - numVal) * 10) / 10);
          emp.gross_salary = Math.round((emp.base_salary / emp.month_days) * numVal);
          // Recalculate statutory PT and WF
          emp.pt_deduction = emp.gross_salary > 20000 ? 200 : (emp.gross_salary > 15000 ? 150 : 0);
          emp.wf_deduction = (emp.category === 'Teaching') ? (emp.gross_salary > 0 ? 75 : 0) : (emp.gross_salary > 0 ? 30 : 0);
        } else if (field === 'base_salary') {
          emp.base_salary = numVal;
          emp.gross_salary = Math.round((numVal / emp.month_days) * emp.total_pay_days);
          emp.pt_deduction = emp.gross_salary > 20000 ? 200 : (emp.gross_salary > 15000 ? 150 : 0);
          emp.wf_deduction = (emp.category === 'Teaching') ? (emp.gross_salary > 0 ? 75 : 0) : (emp.gross_salary > 0 ? 30 : 0);
        } else if (field === 'bus_deduction') {
          emp.bus_deduction = numVal;
        } else if (field === 'hostel_eb_deduction') {
          emp.hostel_eb_deduction = numVal;
        } else if (field === 'mess_deduction') {
          emp.mess_deduction = numVal;
        } else if (field === 'other_deductions') {
          emp.other_deductions = numVal;
        }

        emp.total_deductions = (emp.pt_deduction || 0) + (emp.wf_deduction || 0) + (emp.epf_deduction || 0) + (emp.it_deduction || 0) + (emp.bus_deduction || 0) + (emp.hostel_eb_deduction || 0) + (emp.mess_deduction || 0) + (emp.other_deductions || 0);
        emp.net_salary = Math.max(0, emp.gross_salary - emp.total_deductions);

        // Update DOM row elements directly for instant feedback
        const elGross = document.getElementById(`gross-${empCode}`);
        if (elGross) elGross.textContent = `₹${Math.round(emp.gross_salary).toLocaleString('en-IN')}`;

        const elDed = document.getElementById(`ded-${empCode}`);
        if (elDed) elDed.textContent = `₹${Math.round(emp.total_deductions).toLocaleString('en-IN')}`;

        const elNet = document.getElementById(`net-${empCode}`);
        if (elNet) elNet.textContent = `₹${Math.round(emp.net_salary).toLocaleString('en-IN')}`;
      }

      showToast(`✔ Updated ${field.replace('_', ' ')} for Emp ${empCode}`);
      loadData();
    }
  } catch (err) {
    alert('Error saving inline update');
  }
}

// 1-Click Grant Full Attendance
async function grantFullAttendance(empCode) {
  try {
    const res = await fetch('/api/grant-full-attendance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emp_code: empCode, month_year: currentMonth })
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(`✔ Granted 31 Full Pay Days to ${data.portfolio.name} for ${currentMonth}`);
      loadData();
    }
  } catch (err) {
    alert('Error granting full attendance');
  }
}

// 1-Click Revert Individual Employee Back to Raw Original Biometrics
async function revertToOriginal(empCode) {
  const emp = unifiedRecords.find(r => String(r.emp_code) === String(empCode));
  const empName = emp ? emp.name : `Emp ${empCode}`;
  const confirmMsg = `Revert ${empName} (${empCode}) back to raw biometric machine punch calculations?\n\nThis will clear any manual Full Pay, day overrides, or temporary edits for ${currentMonth}.`;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/revert-to-original', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emp_code: empCode, month_year: currentMonth })
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(`↺ Reverted ${empName} (${empCode}) to original biometrics!`);
      await loadData();
    } else {
      alert('Error reverting: ' + data.message);
    }
  } catch (err) {
    alert('Network error reverting employee');
  }
}

// -----------------------------------------------------------------------------
// BULK REVERT TO ORIGINAL BIOMETRICS MODAL
// -----------------------------------------------------------------------------
function openBulkRevertModal() {
  const deptSelect = document.getElementById('bulk-revert-dept');
  if (deptSelect) {
    const depts = Array.from(new Set(unifiedRecords.map(e => e.department))).sort((a, b) => {
      const idxA = getDeptOrderIndex(a);
      const idxB = getDeptOrderIndex(b);
      if (idxA !== idxB) return idxA - idxB;
      return String(a || '').localeCompare(String(b || ''));
    });
    deptSelect.innerHTML = '<option value="all">All Departments</option>';
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      deptSelect.appendChild(opt);
    });
  }
  document.getElementById('modal-bulk-revert').classList.add('active');
}

async function executeBulkRevert(e) {
  if (e) e.preventDefault();
  const scope = document.getElementById('bulk-revert-scope').value;
  const dept = document.getElementById('bulk-revert-dept').value;
  const cat = document.getElementById('bulk-revert-category').value;

  let targetDesc = 'Entire College (All Staff)';
  if (scope === 'department') targetDesc = `Department: ${dept}`;
  else if (scope === 'category') targetDesc = `Category: ${cat}`;

  const confirmMsg = `⚠️ ARE YOU SURE?\n\nBulk Revert Target: ${targetDesc} for ${currentMonth}\n\nThis will reset attendance, leaves, and salary back to raw biometric machine punches for all matching staff!`;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/bulk-revert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        month_year: currentMonth,
        scope: scope,
        department: dept,
        category: cat
      })
    });
    const data = await res.json();
    if (data.status === 'success') {
      document.getElementById('modal-bulk-revert').classList.remove('active');
      showToast(`↺ Successfully reverted ${data.reverted_count} staff back to original biometrics!`);
      await loadData();
    } else {
      alert('Error during bulk revert: ' + data.message);
    }
  } catch (err) {
    alert('Network error executing bulk revert');
  }
}

// =============================================================================
// EMPLOYEE 360° PORTFOLIO & LEAVE PASSBOOK MODAL
// =============================================================================

// Hides or reveals salary section inside the portfolio modal based on lock state
function _maskPortfolioSalary() {
  const salarySection = document.getElementById('pf-payslip-box');  // the full pay slip card
  const printBtn      = document.getElementById('btn-print-payslip');

  if (!showSalaryColumns) {
    if (salarySection) salarySection.style.display = 'none';
    if (printBtn) printBtn.style.display = 'none';

    // Show locked notice
    let notice = document.getElementById('pf-salary-locked-notice');
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 'pf-salary-locked-notice';
      notice.style.cssText = 'background:rgba(30,41,59,0.05);border:1.5px dashed #cbd5e1;border-radius:12px;padding:22px 24px;text-align:center;color:#64748b;font-size:0.88rem;margin:16px 0 8px;';
      notice.innerHTML = `
        <div style="font-size:2rem;margin-bottom:6px;">🔒</div>
        <strong style="font-size:1rem;color:#334155;">Salary data is locked</strong><br>
        <span style="opacity:0.75;font-size:0.82rem;">Enter PIN to view salary, deductions & net pay</span><br>
        <button onclick="openPinModal()" style="margin-top:12px;background:#1d4ed8;color:#fff;border:none;border-radius:8px;padding:8px 20px;font-weight:700;cursor:pointer;font-size:0.81rem;">🔑 Enter PIN to Unlock</button>
      `;
      if (salarySection && salarySection.parentNode) {
        salarySection.parentNode.insertBefore(notice, salarySection);
      }
    }
    notice.style.display = '';
  } else {
    if (salarySection) salarySection.style.display = '';
    if (printBtn) printBtn.style.display = '';
    const notice = document.getElementById('pf-salary-locked-notice');
    if (notice) notice.style.display = 'none';
  }
}

async function openPortfolio(empCode) {
  try {
    activePortfolioEmpCode = empCode;
    const res = await fetch(`/api/portfolio/${empCode}`);
    const data = await res.json();
    if (data.status !== 'success') return;

    renderPortfolioModal(data.portfolio);
    document.getElementById('modal-portfolio').classList.add('active');
    // Apply salary mask to portfolio sections
    _maskPortfolioSalary();
  } catch (err) {
    alert('Error loading employee portfolio');
  }
}

function renderPortfolioModal(pf) {
  document.getElementById('pf-emp-name').textContent = pf.name;
  document.getElementById('pf-emp-meta').textContent = 
    `Emp Code: ${pf.emp_code} | Department: ${pf.department} | Designation: ${pf.designation}`;

  // Policy Dropdown
  document.getElementById('pf-policy-select').value = pf.attendance_policy;

  // Quota Cards
  document.getElementById('pf-cl-quota').textContent = pf.annual_cl_quota.toFixed(1);
  document.getElementById('pf-cl-availed').textContent = pf.total_cl_availed.toFixed(1);
  document.getElementById('pf-cl-balance').textContent = pf.cl_balance.toFixed(1);
  document.getElementById('pf-od-availed').textContent = pf.total_od_availed.toFixed(1);
  document.getElementById('pf-pay-days-cum').textContent = pf.total_pay_days_cum.toFixed(1);

  const statusEl = document.getElementById('pf-cl-status');
  if (pf.is_over_leave) {
    statusEl.innerHTML = `<span style="color:#b91c1c; font-weight:800;">⚠️ Over-Leave (-${(pf.total_cl_availed - pf.annual_cl_quota).toFixed(1)} LOP)</span>`;
  } else if (pf.cl_balance <= 1.0) {
    statusEl.innerHTML = `<span style="color:#d97706; font-weight:700;">Low Balance</span>`;
  } else {
    statusEl.innerHTML = `<span style="color:#16a34a;">Quota Healthy</span>`;
  }

  // Current Month Pay Slip Breakdown
  const curSal = allSalaryRecords.find(s => s.emp_code === pf.emp_code) || {};
  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  const psMonth = document.getElementById('pf-payslip-month');
  if (psMonth) psMonth.textContent = currentMonth;

  const psBase = document.getElementById('pf-pay-base');
  if (psBase) psBase.textContent = f(curSal.base_salary);

  const psBasic = document.getElementById('pf-pay-basic');
  if (psBasic) psBasic.textContent = f(curSal.earned_basic);

  const psDa = document.getElementById('pf-pay-da');
  if (psDa) psDa.textContent = f(curSal.earned_da);

  const psHra = document.getElementById('pf-pay-hra');
  if (psHra) psHra.textContent = f(curSal.earned_hra);

  const psArr = document.getElementById('pf-pay-arrears');
  if (psArr) psArr.textContent = f(curSal.arrears);

  const psGross = document.getElementById('pf-pay-gross');
  if (psGross) psGross.textContent = f(curSal.gross_salary);

  const psPt = document.getElementById('pf-pay-pt');
  if (psPt) psPt.textContent = f(curSal.pt_deduction);

  const psWf = document.getElementById('pf-pay-wf');
  if (psWf) psWf.textContent = f(curSal.wf_deduction);

  const psEpf = document.getElementById('pf-pay-epf');
  if (psEpf) psEpf.textContent = f(curSal.epf_deduction);

  const psIt = document.getElementById('pf-pay-it');
  if (psIt) psIt.textContent = f(curSal.it_deduction || 0);

  const psBus = document.getElementById('pf-pay-bus');
  if (psBus) psBus.textContent = f(curSal.bus_deduction || 0);

  const psHostel = document.getElementById('pf-pay-hostel');
  if (psHostel) psHostel.textContent = f(curSal.hostel_eb_deduction || 0);

  const psMess = document.getElementById('pf-pay-mess');
  if (psMess) psMess.textContent = f(curSal.mess_deduction || 0);

  const psOther = document.getElementById('pf-pay-other');
  if (psOther) psOther.textContent = f(curSal.other_deductions || 0);

  // Hide zero institutional deductions rows in slip
  const rowBus = document.getElementById('pf-pay-bus-row');
  if (rowBus) rowBus.style.display = (curSal.bus_deduction > 0) ? 'flex' : 'none';
  const rowHostel = document.getElementById('pf-pay-hostel-row');
  if (rowHostel) rowHostel.style.display = (curSal.hostel_eb_deduction > 0) ? 'flex' : 'none';
  const rowMess = document.getElementById('pf-pay-mess-row');
  if (rowMess) rowMess.style.display = (curSal.mess_deduction > 0) ? 'flex' : 'none';
  const rowOther = document.getElementById('pf-pay-other-row');
  if (rowOther) rowOther.style.display = (curSal.other_deductions > 0) ? 'flex' : 'none';

  const psDed = document.getElementById('pf-pay-ded');
  if (psDed) psDed.textContent = f(curSal.total_deductions);

  const psNet = document.getElementById('pf-pay-net');
  if (psNet) psNet.textContent = f(curSal.net_salary);

  const psBank = document.getElementById('pf-pay-bank-meta');
  if (psBank) {
    psBank.textContent = `Bank: ${curSal.bank_name || 'PNB'} | Account: ${curSal.account_no || 'Pending'} | IFSC: ${curSal.ifsc_code || 'PUNB0401700'}`;
  }

  // Monthly History Table
  const tbody = document.getElementById('pf-history-body');
  tbody.innerHTML = '';
  pf.months.forEach(m => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-weight:700; color:var(--primary-navy);">${m.month_year}</td>
      <td style="text-align:right;">${m.biometric_days}</td>
      <td style="text-align:right;">${m.holiday}</td>
      <td style="text-align:right; color:#9333ea; font-weight:600;">${m.availed_leaves || '-'}</td>
      <td style="text-align:right; color:#0d9488; font-weight:600;">${m.sv_od || '-'}</td>
      <td style="text-align:right; font-weight:800; color:#16a34a;">${m.total_pay_days}</td>
      <td style="color:#64748b;">${m.remarks || 'Standard'}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Inline Attendance Quick-Edit
async function handleInlineEdit(empCode, field, value, inputEl) {
  try {
    inputEl.classList.remove('saved');
    const res = await fetch('/api/update-employee', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        emp_code: empCode,
        field: field,
        value: value === '' ? null : parseFloat(value),
        month_year: currentMonth
      })
    });
    const data = await res.json();
    if (data.status === 'success') {
      inputEl.classList.add('saved');
      setTimeout(() => inputEl.classList.remove('saved'), 1500);

      loadData();
      showToast(`✔ Updated pay days & recalculated salary for ${data.portfolio.name}`);
    }
  } catch (err) {
    alert('Error saving inline edit');
  }
}

// Helper to render simple CL day and date badge under CL input
function renderClDaysBadge(emp) {
  const clList = (Array.isArray(emp.cl_days_list) ? emp.cl_days_list : [])
    .map(n => parseInt(String(n).replace(/\D/g, ''), 10))
    .filter(n => !isNaN(n) && n > 0);

  if (clList.length === 0) return '';
  
  const daysStr = clList.join(', ');
  const titleStr = clList.map(d => `${String(d).padStart(2, '0')}-Aug`).join(', ');

  return `<span style="font-size:0.7rem; font-weight:800; color:#7e22ce; background:#fdf4ff; border:1px solid #f0abfc; padding:1px 5px; border-radius:4px; margin-top:2px; white-space:nowrap; cursor:default;" title="Approved CL on: ${titleStr}">[ Day ${daysStr} ]</span>`;
}

// Helper to render simple OD day and date badge under OD input
function renderOdDaysBadge(emp) {
  const odList = (Array.isArray(emp.od_days_list) ? emp.od_days_list : [])
    .map(n => parseInt(String(n).replace(/\D/g, ''), 10))
    .filter(n => !isNaN(n) && n > 0);

  if (odList.length === 0) return '';

  const daysStr = odList.join(', ');
  const titleStr = odList.map(d => `${String(d).padStart(2, '0')}-Aug`).join(', ');

  return `<span style="font-size:0.7rem; font-weight:800; color:#0f766e; background:#f0fdfa; border:1px solid #99f6e4; padding:1px 5px; border-radius:4px; margin-top:2px; white-space:nowrap; cursor:default;" title="Approved OD on: ${titleStr}">[ Day ${daysStr} ]</span>`;
}

// Helper to format ranges nicely (e.g. [1, 3 to 8, 10 to 14])
function formatRanges(nums) {
  if (!nums || nums.length === 0) return '';
  const cleanNums = nums
    .map(n => {
      if (typeof n === 'number') return isNaN(n) ? null : n;
      const parsed = parseInt(String(n).replace(/\D/g, ''), 10);
      return isNaN(parsed) ? null : parsed;
    })
    .filter(n => n !== null && n > 0);

  if (cleanNums.length === 0) return '';
  const sorted = [...new Set(cleanNums)].sort((a,b) => a - b);
  if (sorted.length <= 3) return sorted.join(', ');
  const parts = [];
  let i = 0;
  while (i < sorted.length) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j+1] === sorted[j] + 1) j++;
    if (j - i >= 2) {
      parts.push(`${sorted[i]} to ${sorted[j]}`);
      i = j + 1;
    } else {
      parts.push(sorted[i]);
      i++;
    }
  }
  return parts.join(', ');
}

// Helper to render LOP cell with exact breakdown of why user has loss of pay
function renderLopCell(emp) {
  if (emp.lop_days <= 0) {
    return `<span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">0</span>`;
  }

  const rem = String(emp.remarks || '');
  const halfMatches = [...rem.matchAll(/(\d+)\s*\(\s*1\/2\s*\)/gi)].map(m => m[1]);
  const absDays = Array.isArray(emp.absent_days) && emp.absent_days.length > 0 ? [...emp.absent_days] : [];
  const misDays = Array.isArray(emp.missed_out_punches) && emp.missed_out_punches.length > 0 ? [...emp.missed_out_punches] : [];

  if (absDays.length === 0) {
    const mAb = rem.match(/(?:ab\s*-\s*|absent\s*:?\s*)([0-9,\s\wto]+?)(?=(?:,\s*[\d\s,]+no out|\s*\(|\s*\d+\(1\/2\)|\Z))/i);
    if (mAb) {
      const parsed = mAb[1].split(',').map(s => s.trim()).filter(Boolean);
      parsed.forEach(p => absDays.push(p));
    }
  }

  if (misDays.length === 0) {
    const mNop = rem.match(/([\d\s,]+?)\s*no\s*out\s*punch/i);
    if (mNop) {
      const parsed = mNop[1].split(',').map(s => s.trim()).filter(Boolean);
      parsed.forEach(p => misDays.push(p));
    }
  }

  const lines = [];
  if (absDays.length > 0) {
    const absFmt = formatRanges(absDays);
    lines.push(`<span style="color:#b91c1c; font-size:0.72rem; font-weight:700; background:#fef2f2; padding:1px 5px; border-radius:3px; border:1px solid #fecaca;">❌ Full: [Day ${absFmt}]</span>`);
  }
  if (halfMatches.length > 0) {
    const halfFmt = formatRanges(halfMatches);
    lines.push(`<span style="color:#0369a1; font-size:0.72rem; font-weight:700; background:#f0f9ff; padding:1px 5px; border-radius:3px; border:1px solid #bae6fd;">🌓 Half: [Day ${halfFmt}]</span>`);
  }
  if (misDays.length > 0) {
    const misFmt = formatRanges(misDays);
    lines.push(`<span style="color:#92400e; font-size:0.72rem; font-weight:700; background:#fffbeb; padding:1px 5px; border-radius:3px; border:1px solid #fde68a;">⚠️ No Out: [Day ${misFmt}]</span>`);
  }

  return `
    <div style="display:flex; flex-direction:column; align-items:center; gap:3px; min-width:115px;">
      <span class="lop-badge" style="font-size:0.82rem; font-weight:800; padding:2px 8px; border-radius:5px; background:#fee2e2; color:#991b1b; border:1px solid #fca5a5;">
        ${emp.lop_days}d LOP
      </span>
      ${lines.length > 0 ? `<div style="display:flex; flex-direction:column; align-items:center; gap:2px; margin-top:2px; line-height:1.2;">${lines.join('')}</div>` : ''}
    </div>
  `;
}

// Helper to render colored badges for Remarks / Policy in the main Unified Master table
function renderRemarksBadges(emp) {
  if (emp.is_vip || emp.attendance_policy === 'exempt_full') {
    return `<div style="display:inline-flex; align-items:center; gap:6px; background:#ecfdf5; color:#047857; border:1px solid #86efac; padding:4px 10px; border-radius:6px; font-size:0.82rem; font-weight:700;">
      👑 <span>Full Month (Principal Override)</span>
    </div>`;
  }

  const rem = String(emp.remarks || '').trim();
  const absList = Array.isArray(emp.absent_days) && emp.absent_days.length > 0 ? emp.absent_days : null;
  const misList = Array.isArray(emp.missed_out_punches) && emp.missed_out_punches.length > 0 ? emp.missed_out_punches : null;
  const lateList = Array.isArray(emp.late_punches) && emp.late_punches.length > 0 ? emp.late_punches : null;

  if (!rem && !absList && !misList && !lateList) {
    if (emp.lop_days > 0) {
      return `<div style="display:inline-flex; align-items:center; gap:5px; background:#fef2f2; color:#b91c1c; border:1px solid #fca5a5; padding:3px 8px; border-radius:6px; font-size:0.82rem; font-weight:700;">
        ⚠️ <span>Loss of Pay: [${emp.lop_days} Days]</span>
      </div>`;
    }
    return `<div style="display:inline-flex; align-items:center; gap:5px; color:#10b981; font-size:0.82rem; font-weight:600;">
      ✔ <span>Clean Record</span>
    </div>`;
  }

  const badges = [];
        i = j + 1;
      } else {
        parts.push(sorted[i]);
        i++;
      }
    }
    return parts.join(', ');
  };

  // 1. ABSENT DAYS (Red Badge)
  let absStr = '';
  if (absList) {
    absStr = formatRanges(absList);
  } else {
    const mAb = rem.match(/(?:ab\s*-\s*|absent\s*:?\s*)([0-9,\s\wto]+?)(?=(?:,\s*[\d\s,]+no out|\s*\(|\s*\d+\(1\/2\)|\Z))/i);
    if (mAb) absStr = mAb[1].trim().replace(/,\s*$/, '');
  }
  if (absStr) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;">
        <span style="font-weight:700; color:#b91c1c;">❌ Absent:</span>
        <strong style="background:#ffffff; color:#991b1b; padding:1px 7px; border-radius:4px; border:1px solid #fecaca; font-size:0.82rem; font-weight:800;">[ ${absStr} ]</strong>
      </div>
    `);
  }

  // 2. NO OUT PUNCH (Amber/Yellow Badge)
  let nopStr = '';
  if (misList) {
    nopStr = misList.join(', ');
  } else {
    const mNop = rem.match(/([\d\s,]+?)\s*no\s*out\s*punch/i);
    if (mNop) nopStr = mNop[1].trim().replace(/,\s*$/, '');
  }
  if (nopStr) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#fef3c7; color:#92400e; border:1px solid #fde68a; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;">
        <span style="font-weight:700; color:#b45309;">⚠️ No Out-Punch:</span>
        <strong style="background:#ffffff; color:#92400e; padding:1px 7px; border-radius:4px; border:1px solid #fef08a; font-size:0.82rem; font-weight:800;">[ ${nopStr} ]</strong>
      </div>
    `);
  }

  // 4. HALF DAYS (Blue Badge)
  const halfMatches = [...rem.matchAll(/(\d+)\s*\(\s*1\/2\s*\)/gi)].map(m => m[1]);
  if (halfMatches.length > 0) {
    const halfDays = halfMatches.join(', ');
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;">
        <span style="font-weight:700; color:#0284c7;">🌓 Half Day:</span>
        <strong style="background:#ffffff; color:#0369a1; padding:1px 7px; border-radius:4px; border:1px solid #bfdbfe; font-size:0.82rem; font-weight:800;">[ ${halfDays} ]</strong>
      </div>
    `);
  }

  // 3. LATE ARRIVALS (Purple Badge)
  let lateStr = '';
  if (rem.toLowerCase().includes('(late punch)')) {
    lateStr = 'Penalty: >4 Late Punches';
  } else if (lateList && lateList.length > 0) {
    // Check if lateList entries have "Day" in them
    const formattedLateList = lateList.map((entry, idx) => {
      let str = String(entry).trim();
      if (/^Day\s*\d+/i.test(str)) {
        return str;
      }
      // If entry is a raw time like "11.12" or "09:36", pair with half day if available
      if (halfMatches[idx]) {
        return `Day ${halfMatches[idx]} (${str.replace('.', ':')})`;
      }
      return str;
    });
    lateStr = formattedLateList.slice(0, 4).join(', ');
  } else {
    // 1. Check if remarks has Day X (HH:MM)
    const dayLateMatches = [...rem.matchAll(/Day\s*(\d+)\s*\(([^)]+)\)/gi)];
    if (dayLateMatches.length > 0) {
      lateStr = dayLateMatches.slice(0, 4).map(m => `Day ${m[1]} (${m[2]})`).join(', ');
    } else {
      // 2. Check for raw times inside parentheses, e.g. (11.12, 9.36) or (9.26, 9.30)
      const mLate = rem.match(/\(([\d\.,\s]+)\)/);
      if (mLate) {
        const rawTimes = mLate[1].split(',').map(s => s.trim()).filter(Boolean);
        if (rawTimes.length > 0 && halfMatches.length >= rawTimes.length) {
          // Exactly map each late punch time to its corresponding day
          lateStr = rawTimes.map((t, idx) => `Day ${halfMatches[idx]} (${t.replace('.', ':')})`).join(', ');
        } else {
          lateStr = rawTimes.map(t => t.replace('.', ':')).join(', ');
        }
      }
    }
  }

  if (lateStr) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#f3e8ff; color:#6b21a8; border:1px solid #d8b4fe; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;" title="Click 📅 Punches to see daily in/out times and logs">
        <span style="font-weight:700; color:#7e22ce;">⏰ Late Punch:</span>
        <strong style="background:#ffffff; color:#6b21a8; padding:1px 7px; border-radius:4px; border:1px solid #e9d5ff; font-size:0.82rem; font-weight:800;">[ ${lateStr} ]</strong>
      </div>
    `);
  }

  // 5. CL LEAVES (Lavender Badge - with Days)
  const clDaysNum = Number(emp.cl_days || 0);
  const clDaysArr = (Array.isArray(emp.cl_days_list) ? emp.cl_days_list : [])
    .map(n => parseInt(String(n).replace(/\D/g, ''), 10))
    .filter(n => !isNaN(n) && n > 0);
  const clCleanStr = formatRanges(clDaysArr);

  if (clCleanStr) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#fdf4ff; color:#9333ea; border:1px solid #f0abfc; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;" title="Approved Casual Leave (CL) Days">
        <span style="font-weight:700; color:#a855f7;">📄 CL:</span>
        <strong style="background:#ffffff; color:#9333ea; padding:1px 7px; border-radius:4px; border:1px solid #fae8ff; font-size:0.82rem; font-weight:800;">[ Day ${clCleanStr} ]</strong>
      </div>
    `);
  } else if (clDaysNum > 0) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#fdf4ff; color:#9333ea; border:1px solid #f0abfc; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;" title="Approved Casual Leave (CL) Days">
        <span style="font-weight:700; color:#a855f7;">📄 CL:</span>
        <strong style="background:#ffffff; color:#9333ea; padding:1px 7px; border-radius:4px; border:1px solid #fae8ff; font-size:0.82rem; font-weight:800;">[ ${clDaysNum} Days ]</strong>
      </div>
    `);
  }

  // 6. OD (ON DUTY) (Teal Badge - with Days)
  const odDaysNum = Number(emp.od_days || 0);
  const odDaysArr = (Array.isArray(emp.od_days_list) ? emp.od_days_list : [])
    .map(n => parseInt(String(n).replace(/\D/g, ''), 10))
    .filter(n => !isNaN(n) && n > 0);
  const odCleanStr = formatRanges(odDaysArr);

  if (odCleanStr) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#f0fdfa; color:#0f766e; border:1px solid #99f6e4; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;" title="Official On Duty (OD) Days">
        <span style="font-weight:700; color:#0d9488;">✈️ OD:</span>
        <strong style="background:#ffffff; color:#0f766e; padding:1px 7px; border-radius:4px; border:1px solid #ccfbf1; font-size:0.82rem; font-weight:800;">[ Day ${odCleanStr} ]</strong>
      </div>
    `);
  } else if (odDaysNum > 0) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#f0fdfa; color:#0f766e; border:1px solid #99f6e4; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;" title="Official On Duty (OD) Days">
        <span style="font-weight:700; color:#0d9488;">✈️ OD:</span>
        <strong style="background:#ffffff; color:#0f766e; padding:1px 7px; border-radius:4px; border:1px solid #ccfbf1; font-size:0.82rem; font-weight:800;">[ ${odDaysNum} Days ]</strong>
      </div>
    `);
  }

  // 5. Fallback for other text (e.g. DOJ or custom remarks)
  if (badges.length === 0 && rem) {
    badges.push(`
      <div style="display:inline-flex; align-items:center; gap:6px; background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; padding:4px 9px; border-radius:6px; font-size:0.82rem; margin:2px 0;">
        <span style="font-weight:700;">📝 Remarks:</span>
        <strong style="background:#ffffff; color:#475569; padding:1px 7px; border-radius:4px; border:1px solid #e2e8f0; font-size:0.82rem;">[ ${rem} ]</strong>
      </div>
    `);
  }

  return `<div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start; min-width:280px; line-height:1.25;">${badges.join('')}</div>`;
}

let currentTimelineEmp = null;
let currentTimelineDays = [];
let currentTimelineViewMode = 'cards';

function switchTimelineView(mode) {
  currentTimelineViewMode = mode;
  const gridEl = document.getElementById('calendar-grid');
  const tableWrapEl = document.getElementById('timeline-table-wrap');
  const btnCards = document.getElementById('btn-timeline-cards');
  const btnTable = document.getElementById('btn-timeline-table');

  if (mode === 'cards') {
    if (gridEl) gridEl.style.display = 'grid';
    if (tableWrapEl) tableWrapEl.style.display = 'none';
    if (btnCards) {
      btnCards.style.background = 'white';
      btnCards.style.color = '#1e3a8a';
      btnCards.style.boxShadow = '0 1px 2px rgba(0,0,0,0.08)';
    }
    if (btnTable) {
      btnTable.style.background = 'transparent';
      btnTable.style.color = '#64748b';
      btnTable.style.boxShadow = 'none';
    }
  } else {
    if (gridEl) gridEl.style.display = 'none';
    if (tableWrapEl) tableWrapEl.style.display = 'block';
    if (btnTable) {
      btnTable.style.background = 'white';
      btnTable.style.color = '#1e3a8a';
      btnTable.style.boxShadow = '0 1px 2px rgba(0,0,0,0.08)';
    }
    if (btnCards) {
      btnCards.style.background = 'transparent';
      btnCards.style.color = '#64748b';
      btnCards.style.boxShadow = 'none';
    }
  }
}

// 31-Day Punch Timeline Modal
async function openTimelineModal(empCode) {
  try {
    const res = await fetch(`/api/employee/${empCode}/daily?month=${encodeURIComponent(currentMonth)}`);
    const data = await res.json();
    if (data.status !== 'success') return;

    const emp = data.employee;
    const days = data.days;
    currentTimelineEmp = emp;
    currentTimelineDays = days;

    document.getElementById('timeline-emp-name').textContent = emp.name;
    document.getElementById('timeline-emp-meta').textContent = 
      `Emp Code: ${emp.emp_code} | Department: ${emp.department} | Designation: ${emp.designation || 'Staff'} | Month: ${currentMonth}`;

    const bar = document.getElementById('timeline-summary-bar');
    const activeMonthData = emp.months.find(m => m.month_year === currentMonth) || {};
    bar.innerHTML = `
      <span class="badge-pill" style="background:#ecfdf5; color:#065f46; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Biometric Days: ${activeMonthData.biometric_days || 0}</span>
      <span class="badge-pill" style="background:#eff6ff; color:#1e40af; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Holidays: ${activeMonthData.holiday || 6}</span>
      <span class="badge-pill" style="background:#f5f3ff; color:#6b21a8; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Availed Leaves: ${activeMonthData.availed_leaves || 0}</span>
      <span class="badge-pill" style="background:#f0fdfa; color:#0f766e; font-size: 0.78rem; padding: 0.35rem 0.85rem;">SV/OD: ${activeMonthData.sv_od || 0}</span>
      <span class="badge-pill" style="background:#dcfce7; color:#15803d; font-size: 0.82rem; font-weight:800; padding: 0.35rem 0.85rem; border:1px solid #86efac;">Total Pay Days: ${activeMonthData.total_pay_days || 0}</span>
      ${activeMonthData.remarks ? `<span class="badge-pill" style="background:#fffbeb; color:#b45309; font-size: 0.78rem; padding: 0.35rem 0.85rem; border:1px solid #fde68a;">Remarks: ${activeMonthData.remarks}</span>` : ''}
    `;

    renderCalendarGrid(emp.emp_code, days, emp);
    renderTimelineTable(emp, days);
    switchTimelineView(currentTimelineViewMode);
    document.getElementById('modal-timeline').classList.add('active');
  } catch (err) {
    alert('Error loading employee punch details');
  }
}

// Check late status according to employee specific thresholds
function getPunchFlags(emp, day) {
  const code = String(emp.emp_code || '').trim();
  const deptLower = String(emp.department || '').toLowerCase();
  const inT = day.in_time || '';
  const outT = day.out_time || '';
  const st = (day.override_status || day.status || '').toUpperCase();

  const electricianIds = ['206', '243', '218', '217', '213', '214'];
  const isElectrician = electricianIds.includes(code);
  const isTransport = ['625', '26', '27', '626', '627', '648', '1198', '628', '622', '6621', '606', '623', '603', '653', '605', '6623', '607', '6633', '610', '613'].includes(code) || deptLower.includes('transport');

  let targetH = 9, targetM = 25;
  if (code === '1018') { targetH = 9; targetM = 35; }
  else if (code === '109') { targetH = 11; targetM = 0; }
  else if (code === '536') { targetH = 12; targetM = 10; }
  else if (deptLower.includes('attender') || deptLower.includes('garden') || isElectrician) { targetH = 8; targetM = 35; }

  let isLate = false;
  let isEarlyShift = false;
  let isMissedOut = false;
  let flagNote = '';
  let computedStatus = 'PRESENT';

  // 1. Institutional Holiday
  if (st.includes('HOLIDAY')) {
    computedStatus = 'HOLIDAY';
    flagNote = '🌴 Institutional Holiday / Sunday';
  } 
  // 2. Approved Leaves
  else if (st.includes('CL') || st.includes('LEAVE')) {
    computedStatus = 'CL';
    flagNote = '📄 Approved Casual Leave';
  } else if (st.includes('OD') || st.includes('ON DUTY')) {
    computedStatus = 'OD';
    flagNote = '✈️ Approved On Duty';
  } 
  // 3. Absent handling with overrides
  else if (st.includes('ABSENT')) {
    if (code === '109' && inT && inT.includes(':')) {
      const [ih] = inT.split(':').map(Number);
      if (ih < 11) {
        computedStatus = 'PRESENT';
        flagNote = '✔ Full Day Present (In before 11:00 AM per Principal Rule)';
      } else {
        computedStatus = 'ABSENT';
        flagNote = '❌ Unexcused Absence (1.0d LOP)';
      }
    } else if (code === '536' && inT && inT.includes(':')) {
      const [ih, im] = inT.split(':').map(Number);
      if (ih < 12 || (ih === 12 && im <= 10)) {
        computedStatus = 'PRESENT';
        flagNote = '✔ Full Day Present (In before 12:10 PM per Principal Rule)';
      } else {
        computedStatus = 'ABSENT';
        flagNote = '❌ Unexcused Absence (1.0d LOP)';
      }
    } else {
      computedStatus = 'ABSENT';
      flagNote = '❌ Unexcused Absence (1.0d LOP)';
    }
  } 
  // 4. In-Punch Present Evaluation
  else if (inT && inT.includes(':')) {
    const [ih, im] = inT.split(':').map(Number);
    const hasValidOut = Boolean(outT && outT.includes(':'));
    let outH = 0, outM = 0;
    if (hasValidOut) {
      [outH, outM] = outT.split(':').map(Number);
    }

    // A. Electrician Early Shift (8:30 - 16:30)
    if (isElectrician) {
      if (ih < 8 || (ih === 8 && im <= 35)) {
        isEarlyShift = true;
        if (hasValidOut && (outH > 16 || (outH === 16 && outM >= 30))) {
          flagNote = '⚡ Early Shift 8:30-4:30 Completed';
          computedStatus = 'PRESENT';
        } else if (!hasValidOut) {
          isMissedOut = true;
          computedStatus = 'NO_OUTPUNCH';
          flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
        } else {
          computedStatus = 'PRESENT';
          flagNote = '⚡ Early Shift Attended';
        }
      } else if (ih > 9 || (ih === 9 && im > 25)) {
        isLate = true;
        computedStatus = 'HALF_DAY';
        flagNote = `⚠️ Late Arrival (${inT} > 09:25) - Half Day`;
      } else {
        computedStatus = 'PRESENT';
        flagNote = '✔ Biometric Present On-Time';
      }
    }
    // B. Civil 109 (M. Leelakar): In before 11:00 AM & Out 5:00 PM -> Full Day; In after 11:00 AM -> Half Day
    else if (code === '109') {
      if (ih < 11) {
        // In before 11:00 AM
        if (hasValidOut && (outH >= 17 || (outH === 16 && outM >= 50))) {
          computedStatus = 'PRESENT';
          flagNote = '✔ Full Day Present (In before 11:00 AM & Out 5:00 PM)';
        } else if (!hasValidOut || st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
          isMissedOut = true;
          computedStatus = 'NO_OUTPUNCH';
          flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
        } else if (outH < 17) {
          computedStatus = 'HALF_DAY';
          flagNote = `⚠️ Left Early (${outT} < 17:00) - Marked Half Day`;
        } else {
          computedStatus = 'PRESENT';
          flagNote = '✔ Full Day Present (In before 11:00 AM)';
        }
      } else {
        // In after 11:00 AM -> Late & Half Day
        isLate = true;
        computedStatus = 'HALF_DAY';
        flagNote = `⏰ Late Arrival (${inT} > 11:00 AM) - Marked Half Day`;
      }
    }
    // C. CSE 536 (Bala Subramanyam): In before 12:10 PM -> Full Day
    else if (code === '536') {
      if (ih < 12 || (ih === 12 && im <= 10)) {
        if (!hasValidOut || st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
          isMissedOut = true;
          computedStatus = 'NO_OUTPUNCH';
          flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
        } else {
          computedStatus = 'PRESENT';
          flagNote = '✔ Full Day Present (In before 12:10 PM per Principal Rule)';
        }
      } else {
        isLate = true;
        computedStatus = 'HALF_DAY';
        flagNote = `⏰ Late Arrival (${inT} > 12:10 PM) - Marked Half Day`;
      }
    }
    // D. Media 1018 (Prudhvi Raj): In before 9:35 AM -> On-Time Full Day
    else if (code === '1018') {
      if (ih < 9 || (ih === 9 && im <= 35)) {
        if (!hasValidOut || st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
          isMissedOut = true;
          computedStatus = 'NO_OUTPUNCH';
          flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
        } else {
          computedStatus = 'PRESENT';
          flagNote = '✔ Full Day Present (In before 09:35 AM per Media Rule)';
        }
      } else {
        isLate = true;
        flagNote = `⏰ Late Arrival (${inT} > 09:35 AM)`;
        computedStatus = (st.includes('1/2') || st.includes('HALF')) ? 'HALF_DAY' : 'PRESENT';
      }
    }
    // E. General Staff
    else {
      if ((ih === targetH && im > targetM) || (ih > targetH && ih < 13)) {
        isLate = true;
        flagNote = `⚠️ Late Arrival (${inT} > ${String(targetH).padStart(2,'0')}:${String(targetM).padStart(2,'0')})`;
        if (st.includes('1/2') || st.includes('HALF')) {
          computedStatus = 'HALF_DAY';
        }
      }
      if (!isTransport && (!hasValidOut || st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH'))) {
        isMissedOut = true;
        computedStatus = 'NO_OUTPUNCH';
        flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
      } else if (!flagNote) {
        flagNote = '✔ Biometric Present On-Time';
        computedStatus = (st.includes('1/2') || st.includes('HALF')) ? 'HALF_DAY' : 'PRESENT';
      }
    }
  } else {
    // No in-punch
    if (st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
      isMissedOut = true;
      computedStatus = 'NO_OUTPUNCH';
      flagNote = '⚠️ Missing Evening Out-Punch (0.5d Penalty)';
    } else if (st.includes('1/2') || st.includes('HALF')) {
      computedStatus = 'HALF_DAY';
      flagNote = '½ Half Day Present';
    }
  }

  return { isLate, isEarlyShift, isMissedOut, flagNote, computedStatus, targetH, targetM };
}

// Render the Tabular Punch Log view inside the Punches Modal
function renderTimelineTable(emp, days) {
  const tbody = document.getElementById('timeline-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!days || days.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:2rem; color:#94a3b8;">No raw biometric records found for this month.</td></tr>';
    return;
  }

  days.forEach(day => {
    const flags = getPunchFlags(emp, day);
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid #f1f5f9';

    // Status pill based on computedStatus
    let statusPill = `<span class="badge-pill" style="background:#ecfdf5; color:#047857; font-weight:700;">✔ Present</span>`;
    if (flags.computedStatus === 'NO_OUTPUNCH') {
      statusPill = `<span class="badge-pill" style="background:#fef3c7; color:#92400e; font-weight:700;">⚠️ No Out-Punch</span>`;
    } else if (flags.computedStatus === 'CL') {
      statusPill = `<span class="badge-pill" style="background:#fdf4ff; color:#9333ea; font-weight:700;">📄 CL Leave</span>`;
    } else if (flags.computedStatus === 'OD') {
      statusPill = `<span class="badge-pill" style="background:#f0fdfa; color:#0f766e; font-weight:700;">✈️ On Duty</span>`;
    } else if (flags.computedStatus === 'HOLIDAY') {
      statusPill = `<span class="badge-pill" style="background:#f8fafc; color:#64748b; font-weight:600;">🌴 Holiday</span>`;
    } else if (flags.computedStatus === 'ABSENT') {
      statusPill = `<span class="badge-pill" style="background:#fee2e2; color:#b91c1c; font-weight:700;">❌ Absent</span>`;
    } else if (flags.computedStatus === 'HALF_DAY') {
      statusPill = `<span class="badge-pill" style="background:#e0f2fe; color:#0369a1; font-weight:700;">½ Present</span>`;
    }

    // Punch In display
    let inHtml = `<span style="color:#94a3b8;">--:--</span>`;
    if (day.in_time) {
      if (flags.isLate) {
        inHtml = `<span style="color:#c2410c; font-weight:700;">${day.in_time}</span> <span class="badge-pill" style="background:#ffedd5; color:#c2410c; font-size:0.68rem;">⚠️ Late</span>`;
      } else {
        inHtml = `<span style="font-weight:600; color:#0f172a;">${day.in_time}</span>`;
      }
    }

    // Punch Out display
    let outHtml = `<span style="color:#94a3b8;">--:--</span>`;
    if (day.out_time) {
      if (flags.isEarlyShift) {
        outHtml = `<span style="color:#047857; font-weight:600;">${day.out_time}</span> <span class="badge-pill" style="background:#dcfce7; color:#15803d; font-size:0.68rem;">⚡ Shift Done</span>`;
      } else {
        outHtml = `<span style="font-weight:600; color:#0f172a;">${day.out_time}</span>`;
      }
    } else if (flags.isMissedOut) {
      outHtml = `<span class="badge-pill" style="background:#fef3c7; color:#92400e; font-size:0.68rem; font-weight:700;">⚠️ No Out</span>`;
    }

    // Action buttons
    let actHtml = '';
    if (flags.computedStatus === 'NO_OUTPUNCH') {
      actHtml = `
        <button class="day-btn" style="background:#ecfdf5; color:#065f46; border-color:#86efac; font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'present')">✔ Full</button>
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'cl')">+ CL</button>
      `;
    } else if (flags.computedStatus === 'ABSENT') {
      actHtml = `
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'cl')">+ CL</button>
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'od')">+ OD</button>
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px; color:#15803d;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'present')">✔ Present</button>
      `;
    } else {
      actHtml = `
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'cl')">CL</button>
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'od')">OD</button>
        <button class="day-btn" style="font-size:0.72rem; padding:2px 6px; color:#ef4444;" onclick="applyDayAction('${emp.emp_code}', ${day.day}, 'absent')">Abs</button>
      `;
    }

    tr.innerHTML = `
      <td style="text-align:center; font-weight:700; color:#64748b; padding:6px;">${day.day}</td>
      <td style="color:#334155; font-size:0.75rem; padding:6px;">${day.date || ''}</td>
      <td style="text-align:center; padding:6px;">${inHtml}</td>
      <td style="text-align:center; padding:6px;">${outHtml}</td>
      <td style="text-align:center; color:#64748b; font-size:0.75rem; padding:6px;">${day.duration && day.duration !== '00:00' ? day.duration : '--'}</td>
      <td style="text-align:center; padding:6px;">${statusPill}</td>
      <td style="font-size:0.75rem; color:#475569; padding:6px;">${flags.flagNote}</td>
      <td style="text-align:center; padding:6px;"><div style="display:flex; gap:3px; justify-content:center;">${actHtml}</div></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCalendarGrid(empCode, days, emp) {
  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  if (!days || days.length === 0) {
    grid.innerHTML = '<div style="grid-column: 1/-1; padding:2rem; text-align:center; color:#94a3b8;">No biometric punch logs recorded for this month (Manual / Exempt Staff).</div>';
    return;
  }

  days.forEach(day => {
    const card = document.createElement('div');
    const flags = emp ? getPunchFlags(emp, day) : { isLate: false, isMissedOut: false, computedStatus: 'PRESENT' };

    let statusClass = 'status-present';
    let statusPill = 'Present';

    if (flags.computedStatus === 'NO_OUTPUNCH') {
      statusClass = 'status-missed';
      statusPill = 'No Out-Punch';
    } else if (flags.computedStatus === 'CL') {
      statusClass = 'status-cl';
      statusPill = 'CL Leave';
    } else if (flags.computedStatus === 'OD') {
      statusClass = 'status-od';
      statusPill = 'On Duty';
    } else if (flags.computedStatus === 'HOLIDAY') {
      statusClass = 'status-holiday';
      statusPill = 'Holiday';
    } else if (flags.computedStatus === 'ABSENT') {
      statusClass = 'status-absent';
      statusPill = 'Absent';
    } else if (flags.computedStatus === 'HALF_DAY') {
      statusClass = 'status-present';
      statusPill = '½ Present';
    }

    card.className = `day-card ${statusClass}`;

    let inTimeText = day.in_time ? `In: ${day.in_time}` : 'In: --';
    if (flags.isLate) inTimeText = `In: ${day.in_time} (Late)`;
    let outTimeText = day.out_time ? `Out: ${day.out_time}` : 'Out: --';
    if (flags.isMissedOut) outTimeText = `Out: ⚠️ Missing`;
    const dur = day.duration && day.duration !== '00:00' ? `Dur: ${day.duration}` : '';

    let actionButtons = '';
    if (flags.computedStatus === 'NO_OUTPUNCH') {
      actionButtons = `
        <div class="day-actions-menu">
          <button class="day-btn" style="background:#ecfdf5; color:#065f46; border-color:#86efac;" onclick="applyDayAction('${empCode}', ${day.day}, 'present')">✔ Approve Full</button>
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'cl')">+ Add CL Slip</button>
        </div>
      `;
    } else if (flags.computedStatus === 'ABSENT') {
      actionButtons = `
        <div class="day-actions-menu">
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'cl')">📄 Add CL Slip</button>
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'od')">✈ Add OD Slip</button>
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'present')">✔ Mark Present</button>
        </div>
      `;
    } else {
      actionButtons = `
        <div class="day-actions-menu">
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'cl')">CL Slip</button>
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'od')">OD Slip</button>
          <button class="day-btn" style="color:#ef4444;" onclick="applyDayAction('${empCode}', ${day.day}, 'absent')">Absent</button>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="day-card-header">
        <span class="day-num">${day.day} ${day.date ? day.date.split('-')[1] : ''}</span>
        <span class="day-status-pill">${statusPill}</span>
      </div>
      <div class="day-times">
        <span style="${flags.isLate ? 'color:#c2410c; font-weight:700;' : ''}">${inTimeText}</span>
        <span style="${flags.isMissedOut ? 'color:#b45309; font-weight:700;' : ''}">${outTimeText}</span>
        ${dur ? `<span>${dur}</span>` : ''}
      </div>
      ${actionButtons}
    `;

    grid.appendChild(card);
  });
}

// Regularize single day
async function applyDayAction(empCode, dayNum, action) {
  try {
    const res = await fetch('/api/regularize-day', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emp_code: empCode, day_num: dayNum, action: action, month_year: currentMonth })
    });
    const data = await res.json();
    if (data.status === 'success') {
      renderCalendarGrid(empCode, data.days);
      loadData();
      showToast(`✔ Updated Day ${dayNum}`);
    }
  } catch (err) {
    alert('Error regularizing day');
  }
}

// Toast helper
function showToast(msg) {
  const toast = document.getElementById('app-toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2500);
}

// -----------------------------------------------------------------------------
// 1. UNIFIED 360° MASTER PROFILE, ATTENDANCE & SALARY EDITOR
// -----------------------------------------------------------------------------
function openEditPackageModal(empCode) {
  // Block edit modal salary sections when locked — redirect to PIN
  if (!showSalaryColumns) {
    showToast('🔒 Unlock salary to access the full edit panel');
    openPinModal();
    return;
  }

  const emp = unifiedRecords.find(e => String(e.emp_code) === String(empCode)) || 
              allSalaryRecords.find(e => String(e.emp_code) === String(empCode));
  if (!emp) return;

  const monthDays = emp.month_days || 31;
  document.getElementById('edit-pkg-emp-code').value = emp.emp_code;
  document.getElementById('edit-pkg-month-days-val').value = monthDays;
  document.getElementById('edit-pkg-title').textContent = `Edit Staff Profile: ${emp.name}`;
  document.getElementById('edit-pkg-subtitle').textContent = `Emp Code: ${emp.emp_code} | Department: ${emp.department || 'General'} | Category: ${emp.category || 'Staff'}`;
  
  const chip = document.getElementById('edit-pkg-month-chip');
  if (chip) chip.textContent = currentMonth;
  const infoBadge = document.getElementById('edit-pkg-month-info');
  if (infoBadge) infoBadge.textContent = `${currentMonth} (${monthDays} Days)`;

  // Section 1: Staff Profile & Policy
  document.getElementById('edit-pkg-name').value = emp.name || '';
  document.getElementById('edit-pkg-category').value = emp.category || 'Teaching';
  document.getElementById('edit-pkg-desig').value = emp.designation || '';
  document.getElementById('edit-pkg-dept').value = emp.department || '';
  document.getElementById('edit-pkg-policy').value = emp.attendance_policy || (emp.is_vip ? 'exempt_full' : 'standard');

  // Section 2: Attendance Days
  document.getElementById('edit-pkg-bio-days').value = emp.present_days !== undefined ? emp.present_days : (emp.biometric_days || 0);
  document.getElementById('edit-pkg-holidays').value = emp.holiday !== undefined ? emp.holiday : 4;
  document.getElementById('edit-pkg-cl').value = emp.cl_days !== undefined ? emp.cl_days : (emp.availed_leaves || 0);
  document.getElementById('edit-pkg-od').value = emp.od_days !== undefined ? emp.od_days : (emp.sv_od || 0);
  document.getElementById('edit-pkg-pay-days').value = emp.total_pay_days !== undefined ? emp.total_pay_days : monthDays;

  // Section 3: Salary & Earnings
  document.getElementById('edit-pkg-base-sal').value = emp.base_salary || 0;
  document.getElementById('edit-pkg-arrears').value = emp.arrears || 0;

  // Section 4: Deductions Breakdown
  document.getElementById('edit-pkg-pt').value = emp.pt_deduction !== undefined ? emp.pt_deduction : 200;
  document.getElementById('edit-pkg-wf').value = emp.wf_deduction !== undefined ? emp.wf_deduction : (emp.category === 'Teaching' ? 75 : 30);
  document.getElementById('edit-pkg-epf').value = emp.epf_deduction || 0;
  document.getElementById('edit-pkg-it').value = emp.it_deduction || 0;
  document.getElementById('edit-pkg-bus').value = emp.bus_deduction || 0;
  document.getElementById('edit-pkg-hostel-eb').value = emp.hostel_eb_deduction || 0;
  document.getElementById('edit-pkg-mess').value = emp.mess_deduction || 0;
  document.getElementById('edit-pkg-other-ded').value = emp.other_deductions || 0;

  // Section 6: Banking & Credentials
  document.getElementById('edit-pkg-bank-name').value = emp.bank_name || 'PNB';
  document.getElementById('edit-pkg-acc-no').value = (emp.account_no && emp.account_no !== 'Pending') ? emp.account_no : '';
  document.getElementById('edit-pkg-ifsc').value = emp.ifsc_code || 'PUNB0401700';

  // Wire Revert button in modal
  const btnRevertModal = document.getElementById('btn-revert-from-modal');
  if (btnRevertModal) {
    btnRevertModal.onclick = () => {
      document.getElementById('modal-employee-package').classList.remove('active');
      revertToOriginal(emp.emp_code);
    };
  }

  // Recalculate preview immediately
  updateModalLivePreview();

  // Show Modal
  document.getElementById('modal-employee-package').classList.add('active');
}

// Live calculation preview inside modal as user changes days, base, arrears, or deductions
function updateModalLivePreview() {
  const monthDays = parseFloat(document.getElementById('edit-pkg-month-days-val')?.value || 31);
  const payDays = parseFloat(document.getElementById('edit-pkg-pay-days')?.value || 0);
  const baseSalary = parseFloat(document.getElementById('edit-pkg-base-sal')?.value || 0);
  const arrears = parseFloat(document.getElementById('edit-pkg-arrears')?.value || 0);
  const category = document.getElementById('edit-pkg-category')?.value || 'Teaching';

  // 1. Compute LOP Days
  const lopDays = Math.max(0, Math.round((monthDays - payDays) * 10) / 10);
  const lopEl = document.getElementById('edit-pkg-lop-display');
  if (lopEl) {
    lopEl.textContent = `${lopDays}d LOP`;
    lopEl.style.color = lopDays > 0 ? '#e11d48' : '#10b981';
  }

  // 2. Compute Gross
  let gross = 0;
  if (baseSalary > 0 && payDays > 0 && monthDays > 0) {
    if (category.toLowerCase().includes('teaching') && !category.toLowerCase().includes('non')) {
      const basic = Math.round(baseSalary / 1.5331);
      const earnedBasic = (basic / monthDays) * payDays;
      const da = Math.round(earnedBasic * 0.3731);
      const hra = Math.round(earnedBasic * 0.16);
      gross = Math.round(earnedBasic + da + hra + arrears);
    } else {
      gross = Math.ceil((baseSalary / monthDays) * payDays + arrears);
    }
  } else if (arrears > 0) {
    gross = arrears;
  }
  const grossEl = document.getElementById('edit-pkg-gross-preview');
  if (grossEl) grossEl.textContent = '₹' + gross.toLocaleString('en-IN');

  // 3. Deductions
  let pt = parseFloat(document.getElementById('edit-pkg-pt')?.value);
  if (isNaN(pt)) {
    pt = gross > 20000 ? 200 : (gross > 15000 ? 150 : 0);
  }
  let wf = parseFloat(document.getElementById('edit-pkg-wf')?.value);
  if (isNaN(wf)) {
    wf = (category.toLowerCase().includes('teaching') && !category.toLowerCase().includes('non')) ? (gross > 0 ? 75 : 0) : (gross > 0 ? 30 : 0);
  }
  const epf = parseFloat(document.getElementById('edit-pkg-epf')?.value || 0);
  const it = parseFloat(document.getElementById('edit-pkg-it')?.value || 0);
  const bus = parseFloat(document.getElementById('edit-pkg-bus')?.value || 0);
  const hostel = parseFloat(document.getElementById('edit-pkg-hostel-eb')?.value || 0);
  const mess = parseFloat(document.getElementById('edit-pkg-mess')?.value || 0);
  const other = parseFloat(document.getElementById('edit-pkg-other-ded')?.value || 0);

  const totalDed = pt + wf + epf + it + bus + hostel + mess + other;
  const dedEl = document.getElementById('edit-pkg-total-ded-preview');
  if (dedEl) dedEl.textContent = '₹' + Math.round(totalDed).toLocaleString('en-IN');

  // 4. Net Payout
  const net = Math.max(0, gross - totalDed);
  const netEl = document.getElementById('edit-pkg-net-preview');
  if (netEl) netEl.textContent = '₹' + Math.round(net).toLocaleString('en-IN');

  const bdText = document.getElementById('edit-pkg-breakdown-text');
  if (bdText) bdText.textContent = `Gross ₹${Math.round(gross).toLocaleString('en-IN')} - Deductions ₹${Math.round(totalDed).toLocaleString('en-IN')}`;
}

// Auto-sum payable days when editing biometric, holiday, CL, or OD
function handleAttendanceDaysChange() {
  const bio = parseFloat(document.getElementById('edit-pkg-bio-days')?.value || 0);
  const hol = parseFloat(document.getElementById('edit-pkg-holidays')?.value || 0);
  const cl = parseFloat(document.getElementById('edit-pkg-cl')?.value || 0);
  const od = parseFloat(document.getElementById('edit-pkg-od')?.value || 0);
  const monthDays = parseFloat(document.getElementById('edit-pkg-month-days-val')?.value || 31);

  const sum = Math.min(monthDays, Math.round((bio + hol + cl + od) * 10) / 10);
  const payDaysInput = document.getElementById('edit-pkg-pay-days');
  if (payDaysInput) payDaysInput.value = sum;
  updateModalLivePreview();
}

async function saveEmployeePackage(e) {
  if (e) e.preventDefault();
  const empCode = document.getElementById('edit-pkg-emp-code').value;
  const payload = {
    emp_code: empCode,
    month_year: currentMonth,
    name: document.getElementById('edit-pkg-name').value.trim(),
    category: document.getElementById('edit-pkg-category').value,
    designation: document.getElementById('edit-pkg-desig').value.trim(),
    department: document.getElementById('edit-pkg-dept').value.trim(),
    attendance_policy: document.getElementById('edit-pkg-policy').value,

    biometric_days: parseFloat(document.getElementById('edit-pkg-bio-days').value || 0),
    holiday: parseFloat(document.getElementById('edit-pkg-holidays').value || 0),
    availed_leaves: parseFloat(document.getElementById('edit-pkg-cl').value || 0),
    sv_od: parseFloat(document.getElementById('edit-pkg-od').value || 0),
    total_pay_days: parseFloat(document.getElementById('edit-pkg-pay-days').value || 0),

    base_salary: parseFloat(document.getElementById('edit-pkg-base-sal').value || 0),
    arrears: parseFloat(document.getElementById('edit-pkg-arrears').value || 0),

    pt_deduction: parseFloat(document.getElementById('edit-pkg-pt').value || 0),
    wf_deduction: parseFloat(document.getElementById('edit-pkg-wf').value || 0),
    epf_deduction: parseFloat(document.getElementById('edit-pkg-epf').value || 0),
    it_deduction: parseFloat(document.getElementById('edit-pkg-it').value || 0),
    bus_deduction: parseFloat(document.getElementById('edit-pkg-bus').value || 0),
    hostel_eb_deduction: parseFloat(document.getElementById('edit-pkg-hostel-eb').value || 0),
    mess_deduction: parseFloat(document.getElementById('edit-pkg-mess').value || 0),
    other_deductions: parseFloat(document.getElementById('edit-pkg-other-ded').value || 0),

    bank_name: document.getElementById('edit-pkg-bank-name').value.trim(),
    account_no: document.getElementById('edit-pkg-acc-no').value.trim(),
    ifsc_code: document.getElementById('edit-pkg-ifsc').value.trim()
  };

  try {
    const res = await fetch('/api/employee/update-all-unified', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === 'success') {
      document.getElementById('modal-employee-package').classList.remove('active');
      showToast(`✔ Saved 360° Profile, Attendance & Salary for ${payload.name}`);
      await loadData();
    } else {
      alert('Error updating profile: ' + (data.message || 'Unknown error'));
    }
  } catch (err) {
    alert('Network error saving employee package');
  }
}


// -----------------------------------------------------------------------------
// 2. BULK / MASS SALARY ADJUSTMENTS
// -----------------------------------------------------------------------------
function openBulkAdjustModal() {
  const deptSelect = document.getElementById('bulk-adj-dept');
  if (deptSelect) {
    const depts = Array.from(new Set(allSalaryRecords.map(e => e.department))).sort((a, b) => {
      const idxA = getDeptOrderIndex(a);
      const idxB = getDeptOrderIndex(b);
      if (idxA !== idxB) return idxA - idxB;
      return String(a || '').localeCompare(String(b || ''));
    });
    deptSelect.innerHTML = '<option value="all">All Departments</option>';
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      deptSelect.appendChild(opt);
    });
  }
  document.getElementById('modal-bulk-adjust').classList.add('active');
}

async function executeBulkAdjust(e) {
  if (e) e.preventDefault();
  const category = document.getElementById('bulk-adj-category').value;
  const department = document.getElementById('bulk-adj-dept').value;
  const field = document.getElementById('bulk-adj-field').value;
  const operation = document.getElementById('bulk-adj-op').value;
  const amount = parseFloat(document.getElementById('bulk-adj-amount').value || 0);

  const confirmMsg = `Execute bulk adjustment for [Category: ${category}, Dept: ${department}]?\nField: ${field}\nOperation: ${operation} ${amount}`;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/salary/bulk-adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        month_year: currentMonth,
        category: category,
        department: department,
        field: field,
        operation: operation,
        value: amount
      })
    });
    const data = await res.json();
    if (data.status === 'success') {
      document.getElementById('modal-bulk-adjust').classList.remove('active');
      showToast(`⚡ Bulk adjustment applied to ${data.affected_count} staff!`);
      await loadData();
    } else {
      alert('Error in bulk adjustment: ' + data.message);
    }
  } catch (err) {
    alert('Network error executing bulk adjustments');
  }
}

// -----------------------------------------------------------------------------
// 3. MONTH-OVER-MONTH VARIANCE AUDIT
// -----------------------------------------------------------------------------
async function openSalaryVarianceModal() {
  const monthSelect = document.getElementById('month-select');
  const allMonths = Array.from(monthSelect.options).map(o => o.value);
  const currIdx = allMonths.indexOf(currentMonth);
  let prevMonth = currIdx < allMonths.length - 1 ? allMonths[currIdx + 1] : (allMonths[1] || 'july -2026');

  document.getElementById('variance-meta').textContent = `Comparing ${currentMonth} against ${prevMonth}`;
  document.getElementById('modal-salary-variance').classList.add('active');

  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  try {
    const res = await fetch(`/api/salary/variance?curr_month=${encodeURIComponent(currentMonth)}&prev_month=${encodeURIComponent(prevMonth)}&active_only=${activeOnly}`);
    const data = await res.json();
    if (data.status === 'success') {
      const s = data.summary;
      document.getElementById('var-prev-net').textContent = f(s.tot_prev_net);
      document.getElementById('var-curr-net').textContent = f(s.tot_curr_net);
      
      const diffEl = document.getElementById('var-net-diff');
      diffEl.textContent = (s.total_net_diff >= 0 ? '+' : '') + f(s.total_net_diff);
      diffEl.style.color = s.total_net_diff >= 0 ? '#15803d' : '#dc2626';

      document.getElementById('var-inc-count').textContent = s.increment_count;
      document.getElementById('var-lop-count').textContent = s.decrement_count;

      const tbody = document.getElementById('variance-table-body');
      tbody.innerHTML = '';

      data.comparisons.forEach(item => {
        const tr = document.createElement('tr');
        let statusBadge = `<span class="badge-same">Same</span>`;
        if (item.status === 'increment') statusBadge = `<span class="badge-inc">+₹${Math.round(item.net_diff).toLocaleString('en-IN')}</span>`;
        else if (item.status === 'decrement') statusBadge = `<span class="badge-dec">-₹${Math.round(Math.abs(item.net_diff)).toLocaleString('en-IN')}</span>`;
        else if (item.status === 'new') statusBadge = `<span class="badge-new">New Staff</span>`;

        tr.innerHTML = `
          <td style="font-weight:700; color:#0f172a;">${item.emp_code}</td>
          <td><strong>${item.name}</strong><div style="font-size:0.7rem; color:#94a3b8;">${item.designation || 'Staff'}</div></td>
          <td style="font-size:0.78rem; color:#475569;">${item.department}</td>
          <td style="font-size:0.78rem;">${item.category}</td>
          <td style="text-align:right; color:#64748b;">${item.prev_days}</td>
          <td style="text-align:right; font-weight:700; color:#0f172a;">${item.curr_days}</td>
          <td style="text-align:right; color:#64748b;">${f(item.prev_net)}</td>
          <td style="text-align:right; font-weight:700; color:#15803d;">${f(item.curr_net)}</td>
          <td style="text-align:right; font-weight:800; color:${item.net_diff >= 0 ? '#15803d' : '#dc2626'};">
            ${item.net_diff >= 0 ? '+' : ''}${f(item.net_diff)}
          </td>
          <td>${statusBadge}</td>
        `;
        tbody.appendChild(tr);
      });
    }
  } catch (err) {
    alert('Error loading salary variance report');
  }
}

// -----------------------------------------------------------------------------
// 4. FORMAL INSTITUTIONAL PRINTABLE PAY SLIP
// -----------------------------------------------------------------------------
async function openFormalPaySlip(empCode) {
  if (!empCode) return;
  // Gate: salary must be revealed (PIN required)
  if (!showSalaryColumns) {
    showToast('🔒 Enter PIN to view pay slips');
    openPinModal();
    return;
  }
  try {
    const res = await fetch(`/api/salary/slip-data?month=${encodeURIComponent(currentMonth)}&emp_code=${encodeURIComponent(empCode)}`);
    const data = await res.json();
    if (data.status !== 'success') {
      alert(data.message || 'Error generating pay slip');
      return;
    }

    const r = data.record;
    const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
    const isTeaching = (r.category || '').toLowerCase().includes('teaching') && !(r.category || '').toLowerCase().includes('non');

    let earningsRows = '';
    if (isTeaching) {
      earningsRows = `
        <tr><td>Basic Pay (Earned)</td><td style="text-align:right; font-weight:600;">${f(r.earned_basic)}</td></tr>
        <tr><td>Dearness Allowance (DA 37.31%)</td><td style="text-align:right; font-weight:600;">${f(r.earned_da)}</td></tr>
        <tr><td>House Rent Allowance (HRA 16%)</td><td style="text-align:right; font-weight:600;">${f(r.earned_hra)}</td></tr>
        <tr><td>Arrears / Allowance</td><td style="text-align:right; font-weight:600;">${f(r.arrears)}</td></tr>
      `;
    } else {
      earningsRows = `
        <tr><td>Consolidated Monthly Pay</td><td style="text-align:right; font-weight:600;">${f(r.base_salary)}</td></tr>
        <tr><td>Earned Gross Pay</td><td style="text-align:right; font-weight:600;">${f(r.gross_salary - (r.arrears || 0))}</td></tr>
        <tr><td>Arrears / Bonus</td><td style="text-align:right; font-weight:600;">${f(r.arrears)}</td></tr>
      `;
    }

    const html = `
      <div class="official-payslip-doc">
        <!-- University & College Crest Header -->
        <div class="slip-header-block">
          <div class="slip-univ-name">SRI VENKATESWARA COLLEGE OF ENGINEERING & TECHNOLOGY</div>
          <div class="slip-univ-sub">(AUTONOMOUS) • RVS GROUP OF INSTITUTIONS • CHITTOOR, ANDHRA PRADESH</div>
          <div class="slip-doc-title">PAYSLIP FOR THE MONTH OF ${currentMonth.toUpperCase()}</div>
        </div>

        <!-- Employee Credentials Grid -->
        <div class="slip-meta-grid">
          <div>
            <div class="slip-meta-row"><span class="slip-meta-label">Employee Code:</span><span class="slip-meta-val">${r.emp_code}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Employee Name:</span><span class="slip-meta-val">${r.name}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Designation:</span><span class="slip-meta-val">${r.designation || 'Faculty / Staff'}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Department:</span><span class="slip-meta-val">${r.department}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Staff Category:</span><span class="slip-meta-val">${r.category}</span></div>
          </div>
          <div>
            <div class="slip-meta-row"><span class="slip-meta-label">Bank Name:</span><span class="slip-meta-val">${r.bank_name || 'PNB'}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Account No:</span><span class="slip-meta-val">${r.account_no || 'Pending Submission'}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">IFSC Code:</span><span class="slip-meta-val">${r.ifsc_code || 'PUNB0401700'}</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Month Total Days:</span><span class="slip-meta-val">${data.month_days} Days</span></div>
            <div class="slip-meta-row"><span class="slip-meta-label">Eligible Pay Days:</span><span class="slip-meta-val" style="color:#15803d; font-weight:800;">${r.total_pay_days} Days</span></div>
          </div>
        </div>

        <!-- Side-by-Side Earnings & Deductions Tables -->
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div>
            <table class="slip-salary-table">
              <thead>
                <tr><th>Earnings Head</th><th style="text-align:right;">Amount (₹)</th></tr>
              </thead>
              <tbody>
                ${earningsRows}
                <tr class="slip-total-line">
                  <td><strong>GROSS EARNINGS (A)</strong></td>
                  <td style="text-align:right; font-weight:800; color:#7e22ce;">${f(r.gross_salary)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <table class="slip-salary-table">
              <thead>
                <tr><th>Deductions Head</th><th style="text-align:right;">Amount (₹)</th></tr>
              </thead>
              <tbody>
                <tr><td>Professional Tax (PT - AP)</td><td style="text-align:right; font-weight:600;">${f(r.pt_deduction)}</td></tr>
                <tr><td>Staff Welfare Fund (WF)</td><td style="text-align:right; font-weight:600;">${f(r.wf_deduction)}</td></tr>
                <tr><td>Provident Fund (EPF)</td><td style="text-align:right; font-weight:600;">${f(r.epf_deduction)}</td></tr>
                <tr><td>Income Tax / TDS</td><td style="text-align:right; font-weight:600;">${f(r.it_deduction)}</td></tr>
                <tr><td>Other Deductions / Advance</td><td style="text-align:right; font-weight:600;">${f(r.other_deductions)}</td></tr>
                <tr class="slip-total-line">
                  <td><strong>TOTAL DEDUCTIONS (B)</strong></td>
                  <td style="text-align:right; font-weight:800; color:#b45309;">${f(r.total_deductions)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Net Payable Amount & In Words Banner -->
        <div class="slip-net-banner">
          <div class="slip-words-block">
            <span style="font-size:0.75rem; font-weight:800; color:#047857; text-transform:uppercase; letter-spacing:0.04em;">Net Disbursed in Words:</span>
            <div class="slip-words-val">${data.net_in_words}</div>
          </div>
          <div class="slip-net-num-box">
            <span style="font-size:0.75rem; font-weight:800; color:#047857;">NET PAYABLE AMOUNT:</span>
            <div class="slip-net-amount">${f(r.net_salary)}</div>
          </div>
        </div>

        <!-- Signatures Footer -->
        <div class="slip-signatures-grid">
          <div class="signature-box">Employee Signature</div>
          <div class="signature-box">Checked by Accounts Section</div>
          <div class="signature-box">Principal / Director Approval</div>
        </div>
      </div>
    `;

    document.getElementById('printable-pay-slip-content').innerHTML = html;
    document.getElementById('modal-pay-slip').classList.add('active');
  } catch (err) {
    alert('Network error generating pay slip');
  }
}

// -----------------------------------------------------------------------------
// 5. EXECUTIVE DEPARTMENT-WISE SUMMARY SHEET
// -----------------------------------------------------------------------------
async function openExecutiveSummaryModal() {
  document.getElementById('exec-summary-meta').textContent = `Executive Management Note • ${currentMonth}`;
  document.getElementById('modal-executive-summary').classList.add('active');

  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  try {
    const res = await fetch(`/api/salary/executive-summary?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`);
    const data = await res.json();
    if (data.status !== 'success') {
      alert('Error fetching executive summary');
      return;
    }

    const g = data.grand_totals;

    let statRows = '';
    data.statutory_remittances.forEach(st => {
      statRows += `
        <tr>
          <td><strong>${st.remittance_head}</strong></td>
          <td style="color:#475569;">${st.beneficiary}</td>
          <td style="text-align:right; font-weight:800; color:#1e3a8a;">${f(st.amount)}</td>
        </tr>
      `;
    });

    let catRows = '';
    let cSno = 1;
    (data.category_summary || []).forEach(c => {
      const totDed = (c.gross_salary || 0) - (c.net_salary || 0);
      catRows += `
        <tr>
          <td style="text-align:center; color:#94a3b8;">${cSno++}</td>
          <td><strong>${c.category}</strong></td>
          <td style="text-align:center; font-weight:700;">${c.staff_count}</td>
          <td style="text-align:right;">${f(c.base_salary)}</td>
          <td style="text-align:right; font-weight:700; color:#475569;">${f(c.gross_salary)}</td>
          <td style="text-align:right; color:#b45309;">${f(totDed)}</td>
          <td style="text-align:right; font-weight:800; color:#15803d; background:#f0fdf4;">${f(c.net_salary)}</td>
        </tr>
      `;
    });

    let deptRows = '';
    let dSno = 1;
    data.department_summary.forEach(d => {
      const totDed = d.pt + d.wf + d.epf + d.it + d.other;
      deptRows += `
        <tr>
          <td style="text-align:center; color:#94a3b8;">${dSno++}</td>
          <td><strong>${d.department}</strong></td>
          <td style="text-align:center; font-weight:700;">${d.staff_count}</td>
          <td style="text-align:right;">${f(d.base_salary)}</td>
          <td style="text-align:right; font-weight:700; color:#475569;">${f(d.gross_salary)}</td>
          <td style="text-align:right; color:#b45309;">${f(totDed)}</td>
          <td style="text-align:right; font-weight:800; color:#15803d; background:#f0fdf4;">${f(d.net_salary)}</td>
        </tr>
      `;
    });

    const html = `
      <div class="official-payslip-doc" style="max-width:100%;">
        <div class="slip-header-block">
          <div class="slip-univ-name">SRI VENKATESWARA COLLEGE OF ENGINEERING & TECHNOLOGY</div>
          <div class="slip-univ-sub">(AUTONOMOUS) • RVS GROUP OF INSTITUTIONS • CHITTOOR</div>
          <div class="slip-doc-title">EXECUTIVE PAYROLL & STATUTORY ALLOCATION NOTE - ${currentMonth.toUpperCase()}</div>
        </div>

        <!-- 4 Top Executive KPI Metrics -->
        <div class="exec-kpi-grid">
          <div class="exec-kpi-card">
            <span class="exec-kpi-label">Active Staff Count</span>
            <span class="exec-kpi-val">${g.total_staff}</span>
          </div>
          <div class="exec-kpi-card">
            <span class="exec-kpi-label">Total Monthly Budget</span>
            <span class="exec-kpi-val" style="color:#1d4ed8;">${f(g.total_budget)}</span>
          </div>
          <div class="exec-kpi-card">
            <span class="exec-kpi-label">Earned Gross Total</span>
            <span class="exec-kpi-val" style="color:#7e22ce;">${f(g.total_gross)}</span>
          </div>
          <div class="exec-kpi-card" style="background:#f0fdf4; border-color:#86efac;">
            <span class="exec-kpi-label" style="color:#065f46;">Net Bank Disbursement</span>
            <span class="exec-kpi-val" style="color:#047857;">${f(g.total_net_disbursed)}</span>
          </div>
        </div>

        <!-- Statutory Remittance Table -->
        <h4 style="font-size:0.85rem; font-weight:800; color:#1e3a8a; text-transform:uppercase; margin-bottom:0.5rem;">
          1. Statutory & Regulatory Remittance Schedule (Taxes, Provident Fund & Society)
        </h4>
        <table class="payroll-table" style="margin-bottom:1.5rem;">
          <thead>
            <tr>
              <th>Remittance Head</th>
              <th>Designated Beneficiary Account</th>
              <th style="text-align:right;">Remittance Amount (₹)</th>
            </tr>
          </thead>
          <tbody>
            ${statRows}
          </tbody>
        </table>

        <!-- Category Breakdown Table -->
        <h4 style="font-size:0.85rem; font-weight:800; color:#1e3a8a; text-transform:uppercase; margin-bottom:0.5rem;">
          2. Category-Wise Payroll Allocation Summary (Teaching & Non-Teaching)
        </h4>
        <table class="payroll-table" style="margin-bottom:1.5rem;">
          <thead>
            <tr>
              <th style="width:40px; text-align:center;">#</th>
              <th>Category</th>
              <th style="text-align:center;">Staff</th>
              <th style="text-align:right;">Budget (₹)</th>
              <th style="text-align:right;">Gross (₹)</th>
              <th style="text-align:right;">Deductions (₹)</th>
              <th style="text-align:right;">Net Disbursement (₹)</th>
            </tr>
          </thead>
          <tbody>
            ${catRows}
          </tbody>
        </table>

        <!-- Department Breakdown Table -->
        <h4 style="font-size:0.85rem; font-weight:800; color:#1e3a8a; text-transform:uppercase; margin-bottom:0.5rem;">
          3. Department-Wise Payroll Allocation Summary
        </h4>
        <div style="max-height: 380px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:8px;">
          <table class="payroll-table">
            <thead>
              <tr>
                <th style="width:40px;">#</th>
                <th>Department</th>
                <th style="text-align:center;">Staff</th>
                <th style="text-align:right;">Budget (₹)</th>
                <th style="text-align:right;">Gross (₹)</th>
                <th style="text-align:right;">Deductions (₹)</th>
                <th style="text-align:right;">Net Disbursement (₹)</th>
              </tr>
            </thead>
            <tbody>
              ${deptRows}
            </tbody>
          </table>
        </div>

        <div class="slip-signatures-grid" style="margin-top:2rem;">
          <div class="signature-box">Prepared by Accounts Section</div>
          <div class="signature-box">Internal Financial Auditor</div>
          <div class="signature-box">Principal / Vice-Chairman Approval</div>
        </div>
      </div>
    `;

    document.getElementById('printable-exec-content').innerHTML = html;
  } catch (err) {
    alert('Network error loading executive summary');
  }
}

// -----------------------------------------------------------------------------
// 6. CASH DENOMINATIONS REQUISITION SLIP
// -----------------------------------------------------------------------------
async function openCashDenominationsModal() {
  document.getElementById('cash-denom-meta').textContent = `Cash Requisition Slip • ${currentMonth}`;
  document.getElementById('modal-cash-denominations').classList.add('active');

  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  try {
    const res = await fetch(`/api/salary/cash-denominations?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`);
    const data = await res.json();
    if (data.status !== 'success') {
      alert('Error fetching cash denominations');
      return;
    }

    let denomCards = '';
    data.denomination_summary.forEach(d => {
      const isCoins = String(d.denom) === 'Coins';
      denomCards += `
        <div class="denom-card">
          <div class="denom-badge-val">${isCoins ? 'Coins' : '₹' + d.denom}</div>
          <div class="denom-notes-count">${d.count} notes</div>
          <div class="denom-tot-amt">${f(d.total)}</div>
        </div>
      `;
    });

    let staffRows = '';
    let sIdx = 1;
    data.staff_records.forEach(s => {
      staffRows += `
        <tr>
          <td style="text-align:center; color:#94a3b8;">${sIdx++}</td>
          <td style="font-weight:700;">${s.emp_code}</td>
          <td><strong>${s.name}</strong></td>
          <td style="font-size:0.75rem;">${s.category}</td>
          <td style="font-size:0.75rem; color:#64748b;">${s.department}</td>
          <td style="text-align:right; font-weight:800; color:#15803d; background:#f0fdf4;">${f(s.net_salary)}</td>
          <td style="text-align:center; font-weight:700;">${s.n500 || '-'}</td>
          <td style="text-align:center; font-weight:700;">${s.n200 || '-'}</td>
          <td style="text-align:center; font-weight:700;">${s.n100 || '-'}</td>
          <td style="text-align:center; font-weight:700;">${s.n50 || '-'}</td>
          <td style="text-align:center; font-weight:700;">${s.n20 || '-'}</td>
          <td style="text-align:center; font-weight:700;">${s.n10 || '-'}</td>
          <td style="text-align:center; color:#64748b;">${s.coins || '-'}</td>
        </tr>
      `;
    });

    const html = `
      <div class="official-payslip-doc" style="max-width:100%;">
        <div class="slip-header-block">
          <div class="slip-univ-name">SRI VENKATESWARA COLLEGE OF ENGINEERING & TECHNOLOGY</div>
          <div class="slip-univ-sub">(AUTONOMOUS) • RVS GROUP OF INSTITUTIONS • CHITTOOR</div>
          <div class="slip-doc-title">BANK TELLER CASH WITHDRAWAL REQUISITION - ${currentMonth.toUpperCase()}</div>
        </div>

        <!-- Bank Teller Requisition Banner -->
        <div class="teller-requisition-banner">
          <div>
            <div class="teller-heading">Official Bank Cash Withdrawal Requisition</div>
            <div class="teller-sub">For disbursement to ${data.staff_count} Support, Attender & Unbanked Staff</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:0.72rem; font-weight:800; color:#92400e; text-transform:uppercase;">Grand Cash Required:</div>
            <div class="teller-total-cash">${f(data.total_cash_amount)}</div>
          </div>
        </div>

        <!-- Currency Note Denomination Grid -->
        <h4 style="font-size:0.85rem; font-weight:800; color:#1e3a8a; text-transform:uppercase; margin-bottom:0.5rem;">
          Currency Notes Needed (By Denomination):
        </h4>
        <div class="denom-grid">
          ${denomCards}
        </div>

        <!-- Detailed Individual Staff Breakdown Table -->
        <h4 style="font-size:0.85rem; font-weight:800; color:#1e3a8a; text-transform:uppercase; margin-bottom:0.5rem;">
          Staff Cash Payout & Denomination Breakdown:
        </h4>
        <div style="max-height:360px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:8px;">
          <table class="payroll-table">
            <thead>
              <tr>
                <th style="width:35px;">#</th>
                <th>Emp Code</th>
                <th>Staff Name</th>
                <th>Category</th>
                <th>Department</th>
                <th style="text-align:right;">Net Cash (₹)</th>
                <th style="text-align:center;">₹500</th>
                <th style="text-align:center;">₹200</th>
                <th style="text-align:center;">₹100</th>
                <th style="text-align:center;">₹50</th>
                <th style="text-align:center;">₹20</th>
                <th style="text-align:center;">₹10</th>
                <th style="text-align:center;">Coins</th>
              </tr>
            </thead>
            <tbody>
              ${staffRows}
            </tbody>
          </table>
        </div>

        <div class="slip-signatures-grid" style="margin-top:2rem;">
          <div class="signature-box">Disbursement Cashier Signature</div>
          <div class="signature-box">Accounts Officer Verification</div>
          <div class="signature-box">Bank Branch Teller Stamp & Seal</div>
        </div>
      </div>
    `;

    document.getElementById('printable-cash-content').innerHTML = html;
  } catch (err) {
    alert('Network error loading cash denominations');
  }
}

// =============================================================================
// DELETE OLD DATA / MONTH DATASET HANDLERS
// =============================================================================
async function openDeleteMonthModal() {
  const modal = document.getElementById('modal-delete-data');
  if (!modal) return;

  const select = document.getElementById('delete-month-select');
  const confirmInput = document.getElementById('delete-confirm-input');
  const executeBtn = document.getElementById('btn-execute-delete-data');

  if (confirmInput) confirmInput.value = '';
  if (executeBtn) {
    executeBtn.disabled = true;
    executeBtn.style.opacity = '0.45';
    executeBtn.style.cursor = 'not-allowed';
  }

  try {
    const res = await fetch('/api/months');
    const data = await res.json();
    const months = data.months || [];

    if (select) {
      select.innerHTML = '';
      months.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        if (m === currentMonth) opt.selected = true;
        select.appendChild(opt);
      });
      if (months.length > 0) {
        updateDeleteMonthBadge(select.value || months[0]);
      }
    }
    modal.classList.add('active');
  } catch (err) {
    console.error('Error opening delete modal:', err);
    alert('Failed to load month list: ' + err.message);
  }
}

async function updateDeleteMonthBadge(monthName) {
  const badgeName = document.getElementById('del-badge-name');
  const badgeRecords = document.getElementById('del-badge-records');
  if (badgeName) badgeName.textContent = monthName;

  try {
    const res = await fetch(`/api/month/info?month=${encodeURIComponent(monthName)}`);
    const data = await res.json();
    if (data.status === 'success' && data.info) {
      if (badgeRecords) badgeRecords.textContent = `${data.info.records_count} employees · ${data.info.logs_count} punch logs`;
    }
  } catch (e) {
    if (badgeRecords) badgeRecords.textContent = 'Active dataset';
  }
}

async function executeDeleteMonth() {
  const select = document.getElementById('delete-month-select');
  const targetMonth = select ? select.value : '';
  if (!targetMonth) {
    alert('Please select a month to delete.');
    return;
  }

  const confirmMsg = `Are you ABSOLUTELY sure you want to permanently delete all attendance logs and salary records for "${targetMonth}"?\n\nThis cannot be undone!`;
  if (!confirm(confirmMsg)) return;

  showToast(`⏳ Deleting records for ${targetMonth}...`);
  try {
    const res = await fetch('/api/month/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ month_name: targetMonth })
    });
    const data = await res.json();

    if (res.ok && data.status === 'success') {
      showToast(`✅ Successfully deleted ${targetMonth}!`);
      document.getElementById('modal-delete-data').classList.remove('active');

      // Reload months
      await loadMonths();
      // If current month was deleted, switch to first available
      const selectMonth = document.getElementById('month-select');
      if (selectMonth && selectMonth.options.length > 0) {
        currentMonth = selectMonth.options[0].value;
        selectMonth.value = currentMonth;
      }
      await loadData();
    } else {
      alert('Deletion failed: ' + (data.message || 'Unknown error'));
    }
  } catch (err) {
    console.error('Delete error:', err);
    alert('Error deleting month: ' + err.message);
  }
}
