// RVS Salary & Biometric Attendance Web Platform JavaScript
// Multi-Month & Yearly Ledger with 360° Employee Portfolio & Full Payroll Generation

let allEmployees = [];
let allSalaryRecords = [];
let currentFilter = 'all';
let currentDept = 'all';
let currentCategory = 'all';
let currentSort = 'code_asc';
let activeOnly = true;
let currentMonth = 'August -2026';
let activePortfolioEmpCode = null;
let currentViewMode = 'attendance'; // 'attendance' or 'salary'
let currentDashboardMode = 'unified'; // 'unified', 'attendance', or 'salary'
let showSalaryColumns = false; // Principal Instruction: Salary columns hidden by default
let unifiedRecords = [];

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

  // Filter tabs
  document.querySelectorAll('.filter-tabs .tab-pill').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const pill = e.currentTarget;
      document.querySelectorAll('.filter-tabs .tab-pill').forEach(b => b.classList.remove('active'));
      pill.classList.add('active');
      currentFilter = pill.dataset.filter;
      renderTable();
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
    if (!monthPrompt) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('month_name', monthPrompt);

    showToast(`Uploading & Analyzing ${file.name} for ${monthPrompt}...`);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.status === 'success') {
        showToast('File analyzed and saved to database successfully!');
        currentMonth = monthPrompt;
        await loadMonths();
      } else {
        alert('Upload error: ' + data.message);
      }
    } catch (err) {
      alert('Network error uploading file');
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
      menuDisburse.classList.toggle('show');
    });
    document.addEventListener('click', () => menuDisburse.classList.remove('show'));
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

  // Update guidance bar text dynamically for instant user clarity
  const guideTag = document.querySelector('.guidance-bar .guide-tag');
  const guideContent = document.getElementById('guidance-content');

  if (currentDashboardMode === 'unified') {
    if (guideTag) guideTag.textContent = '🌟 Unified Master';
    if (guideContent) {
      guideContent.innerHTML = `
        <span>💡 <strong>Unified Master Mode:</strong> Attendance & Salary consolidated side-by-side with full inline editing.</span>
        <span>•</span>
        <span>Edit <strong>CL ✎</strong>, <strong>OD ✎</strong>, <strong>Pay Days ✎</strong>, <strong>Base Rate ✎</strong>, or <strong>Other Ded ✎</strong> directly.</span>
        <span>•</span>
        <span>Notice <strong>₹275</strong> is split transparently: <strong>PT: ₹200</strong> (AP State Tax) + <strong>WF: ₹75</strong> (Staff Welfare).</span>
      `;
    }
  } else if (currentDashboardMode === 'attendance') {
    if (guideTag) guideTag.textContent = '📋 Attendance Register';
    if (guideContent) {
      guideContent.innerHTML = `
        <span>📋 <strong>Attendance Grid Mode:</strong> Register of biometric punches, holiday credits, and leave slips.</span>
        <span>•</span>
        <span>Edit <strong>CL ✎</strong> or <strong>OD ✎</strong> inline to recalculate pay days automatically, or click <strong>✔ Full Pay</strong> for 1-click 31 days.</span>
        <span>•</span>
        <span>Click <strong>📅 Punches</strong> to view daily 1–31 biometric in/out times and apply regularization.</span>
      `;
    }
  } else if (currentDashboardMode === 'salary') {
    if (guideTag) guideTag.textContent = '💰 Salary & Bank Ledger';
    if (guideContent) {
      guideContent.innerHTML = `
        <span>💰 <strong>Salary & Bank Ledger Mode:</strong> Official institutional salary bill with Bank Account Numbers & IFSC codes.</span>
        <span>•</span>
        <span>Clear breakdown of statutory deductions: <strong>PT ₹200</strong>, <strong>WF ₹75</strong>, <strong>EPF</strong>, and <strong>Other Ded ✎</strong>.</span>
        <span>•</span>
        <span>Click <strong>🖨️ Slip</strong> for formal printable pay slip, or <strong>⚙️ Edit</strong> to adjust packages & bank details.</span>
      `;
    }
  }

  renderTable();
}

function setFilterPill(filterName) {
  document.querySelectorAll('.filter-tabs .tab-pill').forEach(b => b.classList.remove('active'));
  const target = document.querySelector(`.filter-tabs [data-filter="${filterName}"]`);
  if (target) target.classList.add('active');
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
      if (!data.months.includes(currentMonth)) {
        currentMonth = data.months[0];
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
    const dataSal = await resSal.json();

    if (dataAtt.status === 'success' && dataSal.status === 'success') {
      allEmployees = dataAtt.employees || [];
      allSalaryRecords = dataSal.records || [];
      buildUnifiedRecords(dataAtt.stats, dataSal.stats);
      populateDepartmentSelect(dataAtt.departments);
      if (dataSal.categories) populateCategorySelect(dataSal.categories);
      renderTable();
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

    const cl = Number(att.availed_leaves !== undefined ? att.availed_leaves : (att.cl_days || 0));
    const od = Number(att.sv_od !== undefined ? att.sv_od : (att.od_days || 0));
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

  const totalStaff = attStats.total_staff || unifiedRecords.length;
  const elStaff = document.getElementById('stat-total-staff');
  if (elStaff) elStaff.textContent = totalStaff;

  // Store raw salary values globally so we can mask/unmask without re-fetching
  window._kpiSalaryData = {
    budget:  salStats.total_payroll_budget,
    gross:   salStats.total_gross_disbursed,
    ded:     salStats.total_all_deductions,
    net:     salStats.total_net_disbursed
  };

  // Apply mask based on current lock state
  updateSalaryKPIMask();

  const elDays = document.getElementById('stat-total-pay-days');
  if (elDays) {
    const payDays = attStats.total_pay_days || unifiedRecords.reduce((acc, r) => acc + (r.total_pay_days || 0), 0);
    elDays.textContent = `${Math.round(payDays)} Days`;
  }

  const navReview = document.getElementById('nav-review-count');
  if (navReview) navReview.textContent = attStats.needs_review_count || 0;

  const navVip = document.getElementById('nav-vip-count');
  if (navVip) navVip.textContent = attStats.vip_count || 0;

  // Filter Pill Counter Badges
  const busCount = unifiedRecords.filter(r => (Number(r.bus_deduction) || 0) > 0).length;
  const messCount = unifiedRecords.filter(r => (Number(r.mess_deduction) || 0) > 0).length;
  const hostelCount = unifiedRecords.filter(r => (Number(r.hostel_eb_deduction) || 0) > 0).length;
  const dedCount = unifiedRecords.filter(r => (Number(r.total_deductions) || 0) > 0).length;

  const elBus = document.getElementById('count-bus');
  if (elBus) elBus.textContent = busCount;

  const elMess = document.getElementById('count-mess');
  if (elMess) elMess.textContent = messCount;

  const elHostel = document.getElementById('count-hostel');
  if (elHostel) elHostel.textContent = hostelCount;

  const elDedPill = document.getElementById('count-ded');
  if (elDedPill) elDedPill.textContent = dedCount;
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
}

function populateDepartmentSelect(depts) {
  const select = document.getElementById('dept-select');
  const currentVal = select.value;
  select.innerHTML = '<option value="all">All Departments</option>';
  depts.forEach(d => {
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
    if (text) text.textContent = 'Salary: Visible — Click to Lock';
  } else {
    btn.classList.remove('salary-revealed');
    btn.title = 'Enter PIN to reveal salary columns (Principal instruction)';
    if (icon) icon.textContent = '🔒';
    if (text) text.textContent = 'Salary Columns: Locked';
  }

  // Sync KPI cards to lock/unlock state
  updateSalaryKPIMask();
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
          <th style="width: 38px; text-align: center;" class="sticky-col-code">#</th>
          <th style="width: 78px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
          <th style="min-width: 190px; cursor: pointer;" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
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
          
          <th style="width: 185px; text-align: center;">Actions</th>
        </tr>
      `;
    } else {
      thead.innerHTML = `
        <tr>
          <th style="width: 38px; text-align: center;" class="sticky-col-code">#</th>
          <th style="width: 78px; text-align: center; cursor: pointer;" class="sticky-col-code" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
          <th style="min-width: 190px; cursor: pointer;" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
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
          
          <th style="width: 185px; text-align: center;">Actions</th>
        </tr>
      `;
    }
  } else if (mode === 'attendance') {
    thead.innerHTML = `
      <tr>
        <th style="width: 40px; text-align: center;">#</th>
        <th style="width: 80px; text-align: center; cursor: pointer;" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
        <th style="min-width: 210px; cursor: pointer;" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Employee Name ↕</th>
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
        <th style="width: 40px; text-align: center;">#</th>
        <th style="width: 80px; text-align: center; cursor: pointer;" onclick="handleHeaderSort('code')" title="Sort by Emp Code">Emp Code ↕</th>
        <th style="min-width: 190px; cursor: pointer;" onclick="handleHeaderSort('name')" title="Sort by Name (A → Z)">Staff Member ↕</th>
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
        const numA = parseInt(String(a.emp_code).replace(/\D/g, '')) || 0;
        const numB = parseInt(String(b.emp_code).replace(/\D/g, '')) || 0;
        return numA !== numB ? numA - numB : String(a.emp_code).localeCompare(String(b.emp_code));
      }
    }
  });

  const totalCols = (mode === 'unified') ? (showSalaryColumns ? 20 : 12) : ((mode === 'attendance') ? 13 : 18);

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${totalCols}" style="text-align: center; padding: 3rem; color: #94a3b8; font-weight: 500;">No employees found matching the selected filter.</td></tr>`;
    return;
  }

  let lastDept = null;
  let sNo = 1;
  const showDeptHeader = (currentSort === 'code_asc' && currentDept === 'all');

  filtered.forEach(emp => {
    if (showDeptHeader && emp.department !== lastDept) {
      lastDept = emp.department;
      const deptRow = document.createElement('tr');
      deptRow.className = 'dept-section-row';
      deptRow.innerHTML = `<td colspan="${totalCols}" style="background:#f8fafc; font-weight:800; color:#1e3a8a; padding: 6px 12px; border-top: 1px solid #e2e8f0;">DEPARTMENT: ${lastDept}</td>`;
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
        <td style="text-align: center; color: #94a3b8; font-weight: 600;" class="sticky-col-code">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;" class="sticky-col-code">${emp.emp_code}</td>
        <td>
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
        
        <!-- Editable CL -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-cl" 
                 value="${emp.cl_days || 0}" 
                 title="Casual Leave (CL) Slips - Click to edit directly"
                 onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
        </td>
        
        <!-- Editable OD -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-od" 
                 value="${emp.od_days || 0}" 
                 title="On Duty (OD) Slips - Click to edit directly"
                 onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'sv_od', this.value, this)">
        </td>
        
        <!-- LOP Badge -->
        <td style="text-align: center;">
          ${emp.lop_days > 0 
            ? `<span class="lop-badge" title="${emp.lop_days} Unpaid Absent Days">${emp.lop_days}d LOP</span>` 
            : `<span style="color:#94a3b8; font-size:0.75rem;">0</span>`}
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
        <td style="text-align: center; color: #94a3b8; font-weight: 600;">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;">${emp.emp_code}</td>
        <td>
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
        
        <!-- Editable CL -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-cl" 
                 value="${emp.cl_days || 0}" 
                 title="Edit Casual Leave (CL)"
                 onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
        </td>
        
        <!-- Editable OD -->
        <td style="text-align: center;">
          <input type="number" step="0.5" min="0" max="31"
                 class="cell-sal-input input-od" 
                 value="${emp.od_days || 0}" 
                 title="Edit On-Duty (OD)"
                 onchange="handleAttendanceInlineEdit('${emp.emp_code}', 'sv_od', this.value, this)">
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
        <td style="text-align: center; color: #94a3b8; font-weight: 600;">${sNo++}</td>
        <td style="text-align: center; font-weight: 700; color: #0f172a;">${emp.emp_code}</td>
        <td>
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
    const depts = Array.from(new Set(unifiedRecords.map(e => e.department))).sort();
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
async function openPortfolio(empCode) {
  try {
    activePortfolioEmpCode = empCode;
    const res = await fetch(`/api/portfolio/${empCode}`);
    const data = await res.json();
    if (data.status !== 'success') return;

    renderPortfolioModal(data.portfolio);
    document.getElementById('modal-portfolio').classList.add('active');
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

// 31-Day Punch Timeline Modal
async function openTimelineModal(empCode) {
  try {
    const res = await fetch(`/api/employee/${empCode}/daily?month=${encodeURIComponent(currentMonth)}`);
    const data = await res.json();
    if (data.status !== 'success') return;

    const emp = data.employee;
    const days = data.days;

    document.getElementById('timeline-emp-name').textContent = emp.name;
    document.getElementById('timeline-emp-meta').textContent = 
      `Emp Code: ${emp.emp_code} | Department: ${emp.department} | Month: ${currentMonth}`;

    const bar = document.getElementById('timeline-summary-bar');
    const activeMonthData = emp.months.find(m => m.month_year === currentMonth) || {};
    bar.innerHTML = `
      <span class="badge-pill" style="background:#ecfdf5; color:#065f46; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Biometric Days: ${activeMonthData.biometric_days || 0}</span>
      <span class="badge-pill" style="background:#eff6ff; color:#1e40af; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Holidays: ${activeMonthData.holiday || 6}</span>
      <span class="badge-pill" style="background:#f5f3ff; color:#6b21a8; font-size: 0.78rem; padding: 0.35rem 0.85rem;">Availed Leaves: ${activeMonthData.availed_leaves || 0}</span>
      <span class="badge-pill" style="background:#f0fdfa; color:#0f766e; font-size: 0.78rem; padding: 0.35rem 0.85rem;">SV/OD: ${activeMonthData.sv_od || 0}</span>
      <span class="badge-pill" style="background:#dcfce7; color:#15803d; font-size: 0.82rem; font-weight:800; padding: 0.35rem 0.85rem; border:1px solid #86efac;">Total Pay Days: ${activeMonthData.total_pay_days || 0}</span>
    `;

    renderCalendarGrid(emp.emp_code, days);
    document.getElementById('modal-timeline').classList.add('active');
  } catch (err) {
    alert('Error loading employee punch details');
  }
}

function renderCalendarGrid(empCode, days) {
  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  if (!days || days.length === 0) {
    grid.innerHTML = '<div style="grid-column: 1/-1; padding:2rem; text-align:center; color:#94a3b8;">No biometric punch logs recorded for this month (Manual / Exempt Staff).</div>';
    return;
  }

  days.forEach(day => {
    const card = document.createElement('div');
    const st = (day.override_status || day.status || '').toUpperCase();

    let statusClass = 'status-present';
    let statusPill = 'Present';

    if (st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
      statusClass = 'status-missed';
      statusPill = 'No Out-Punch';
    } else if (st.includes('CL') || st.includes('LEAVE')) {
      statusClass = 'status-cl';
      statusPill = 'CL Leave';
    } else if (st.includes('OD') || st.includes('ON DUTY')) {
      statusClass = 'status-od';
      statusPill = 'On Duty';
    } else if (st.includes('HOLIDAY')) {
      statusClass = 'status-holiday';
      statusPill = 'Holiday';
    } else if (st.includes('ABSENT')) {
      statusClass = 'status-absent';
      statusPill = 'Absent';
    } else if (st.includes('1/2') || st.includes('HALF')) {
      statusClass = 'status-present';
      statusPill = '½ Present';
    }

    card.className = `day-card ${statusClass}`;

    const inTime = day.in_time ? `In: ${day.in_time}` : 'In: --';
    const outTime = day.out_time ? `Out: ${day.out_time}` : 'Out: --';
    const dur = day.duration && day.duration !== '00:00' ? `Dur: ${day.duration}` : '';

    let actionButtons = '';
    if (st.includes('NO OUTPUNCH') || st.includes('NO OUT PUNCH')) {
      actionButtons = `
        <div class="day-actions-menu">
          <button class="day-btn" style="background:#ecfdf5; color:#065f46; border-color:#86efac;" onclick="applyDayAction('${empCode}', ${day.day}, 'present')">✔ Approve Full</button>
          <button class="day-btn" onclick="applyDayAction('${empCode}', ${day.day}, 'cl')">+ Add CL Slip</button>
        </div>
      `;
    } else if (st.includes('ABSENT')) {
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
        <span>${inTime}</span>
        <span>${outTime}</span>
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
    const depts = Array.from(new Set(allSalaryRecords.map(e => e.department))).sort();
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
