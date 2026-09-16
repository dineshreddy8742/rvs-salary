// RVS Salary & Biometric Attendance Web Platform JavaScript
// Multi-Month & Yearly Ledger with 360° Employee Portfolio & Full Payroll Generation

let allEmployees = [];
let allSalaryRecords = [];
let currentFilter = 'all';
let currentDept = 'all';
let currentCategory = 'all';
let activeOnly = true;
let currentMonth = 'August -2026';
let activePortfolioEmpCode = null;
let currentViewMode = 'attendance'; // 'attendance' or 'salary'

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
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

  // Filter tabs
  document.querySelectorAll('.filter-tabs .tab-pill').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tabs .tab-pill').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.dataset.filter;
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

  // View Switcher (Attendance Grid vs Salary & Payroll Ledger)
  const pillAtt = document.getElementById('pill-view-attendance');
  const pillSal = document.getElementById('pill-view-salary');

  if (pillAtt) {
    pillAtt.addEventListener('click', () => switchViewMode('attendance'));
  }
  if (pillSal) {
    pillSal.addEventListener('click', () => switchViewMode('salary'));
  }

  // Active Only toggle
  document.getElementById('toggle-active-only').addEventListener('change', (e) => {
    activeOnly = e.target.checked;
    loadData();
  });

  // Export Attendance button (.xls)
  document.getElementById('btn-export').addEventListener('click', () => {
    showToast(`⚡ Exporting ${currentMonth} Attendance to output.xls...`);
    window.location.href = `/api/export?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`;
  });

  // Export Salary Bill button (.xlsx)
  const btnExportSal = document.getElementById('btn-export-salary');
  if (btnExportSal) {
    btnExportSal.addEventListener('click', () => {
      showToast(`⚡ Exporting ${currentMonth} Institutional Salary Bill (.xlsx)...`);
      window.location.href = `/api/salary/export?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`;
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
  document.getElementById('card-needs-review').addEventListener('click', () => {
    setFilterPill('review');
  });
}

// Switch between Attendance and Salary View
function switchViewMode(mode) {
  currentViewMode = mode;
  const pillAtt = document.getElementById('pill-view-attendance');
  const pillSal = document.getElementById('pill-view-salary');
  const attGrid = document.getElementById('attendance-stats-grid');
  const salGrid = document.getElementById('salary-stats-grid');
  const catBox = document.getElementById('category-filter-box');

  if (mode === 'salary') {
    pillAtt.classList.remove('active');
    pillSal.classList.add('active');
    if (attGrid) attGrid.style.display = 'none';
    if (salGrid) salGrid.style.display = 'grid';
    if (catBox) catBox.style.display = 'flex';
  } else {
    pillSal.classList.remove('active');
    pillAtt.classList.add('active');
    if (salGrid) salGrid.style.display = 'none';
    if (attGrid) attGrid.style.display = 'grid';
    if (catBox) catBox.style.display = 'none';
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

// Load both attendance and salary data
async function loadData() {
  try {
    // 1. Fetch Attendance Records
    const resAtt = await fetch(`/api/data?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`);
    const dataAtt = await resAtt.json();

    if (dataAtt.status === 'success') {
      allEmployees = dataAtt.employees;
      renderAttendanceKPIs(dataAtt.stats);
      populateDepartmentSelect(dataAtt.departments);
    }

    // 2. Fetch Salary Records
    const resSal = await fetch(`/api/salary/data?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`);
    const dataSal = await resSal.json();

    if (dataSal.status === 'success') {
      allSalaryRecords = dataSal.records;
      renderSalaryKPIs(dataSal.stats);
      populateCategorySelect(dataSal.categories);
    }

    renderTable();
  } catch (err) {
    console.error('Error fetching data:', err);
    showToast('Error loading platform data');
  }
}

function renderAttendanceKPIs(stats) {
  document.getElementById('stat-total-staff').textContent = stats.total_staff;
  document.getElementById('stat-needs-review').textContent = stats.needs_review_count;
  document.getElementById('stat-total-leaves').textContent = stats.total_leaves;
  document.getElementById('stat-total-od').textContent = stats.total_od;
  document.getElementById('stat-total-pay-days').textContent = stats.total_pay_days;

  const navReview = document.getElementById('nav-review-count');
  if (navReview) navReview.textContent = stats.needs_review_count;

  const navVip = document.getElementById('nav-vip-count');
  if (navVip) navVip.textContent = stats.vip_count || 0;
}

function renderSalaryKPIs(stats) {
  const f = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  const elStaff = document.getElementById('stat-salary-staff');
  if (elStaff) elStaff.textContent = stats.total_staff;

  const elBud = document.getElementById('stat-salary-budget');
  if (elBud) elBud.textContent = f(stats.total_payroll_budget);

  const elGross = document.getElementById('stat-salary-gross');
  if (elGross) elGross.textContent = f(stats.total_gross_disbursed);

  const elDed = document.getElementById('stat-salary-deductions');
  if (elDed) elDed.textContent = f(stats.total_all_deductions);

  const elNet = document.getElementById('stat-salary-net');
  if (elNet) elNet.textContent = f(stats.total_net_disbursed);
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

// Render Table Header & Body dynamically based on currentViewMode
function renderTable() {
  const thead = document.getElementById('table-head');
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';

  if (currentViewMode === 'salary') {
    renderSalaryTable(thead, tbody);
  } else {
    renderAttendanceTable(thead, tbody);
  }
}

// -----------------------------------------------------------------------------
// RENDER ATTENDANCE TABLE
// -----------------------------------------------------------------------------
function renderAttendanceTable(thead, tbody) {
  thead.innerHTML = `
    <tr>
      <th style="width: 48px;">S.No</th>
      <th style="width: 85px;">Emp Code</th>
      <th style="width: 220px;">Employee Name (Click for Portfolio)</th>
      <th style="width: 120px;">Designation</th>
      <th style="width: 80px;">Dept</th>
      <th style="width: 100px;">Biometric Days</th>
      <th style="width: 70px;">Holiday</th>
      <th style="width: 115px;" class="col-leave" title="Option 1: Inline Editable Casual Leaves">Availed Leaves ✎</th>
      <th style="width: 100px;" class="col-od" title="Option 1: Inline Editable On Duty">SV/OD ✎</th>
      <th style="width: 110px;" class="col-total-pay" title="Total Pay Days for Salary">Total Pay Days</th>
      <th style="min-width: 200px;">Remarks / Policy</th>
      <th style="width: 180px; text-align: center;">Actions</th>
    </tr>
  `;

  const query = document.getElementById('search-input').value.toLowerCase().trim();

  const filtered = allEmployees.filter(emp => {
    if (currentDept !== 'all' && emp.department !== currentDept) return false;
    if (currentFilter === 'review' && !emp.needs_review) return false;
    if (currentFilter === 'vip' && emp.attendance_policy === 'standard') return false;
    if (currentFilter === 'absent' && (!emp.absent_days || emp.absent_days.length === 0)) return false;
    if (currentFilter === 'leaves' && (!emp.availed_leaves && !emp.sv_od)) return false;

    if (query) {
      const matchName = emp.name.toLowerCase().includes(query);
      const matchCode = emp.emp_code.toLowerCase().includes(query);
      const matchDesig = (emp.designation || '').toLowerCase().includes(query);
      if (!matchName && !matchCode && !matchDesig) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; padding: 3rem; color: #94a3b8; font-weight: 500;">No employees found matching the selected filter.</td></tr>`;
    return;
  }

  let lastDept = null;
  let sNo = 1;

  filtered.forEach(emp => {
    if (emp.department !== lastDept && currentDept === 'all') {
      lastDept = emp.department;
      const deptRow = document.createElement('tr');
      deptRow.className = 'dept-section-row';
      deptRow.innerHTML = `<td colspan="12">Department: ${lastDept}</td>`;
      tbody.appendChild(deptRow);
    }

    const tr = document.createElement('tr');
    tr.id = `row-${emp.emp_code}`;

    let statusBadge = '';
    if (emp.attendance_policy === 'exempt_full') {
      statusBadge += `<span class="badge-pill badge-policy-exempt">👑 Full Pay (VIP)</span> `;
    } else if (emp.attendance_policy === 'visiting_twice_weekly') {
      statusBadge += `<span class="badge-pill badge-policy-visiting">Visiting Schedule</span> `;
    }

    if (emp.missed_out_punches && emp.missed_out_punches.length > 0) {
      statusBadge += `<span class="badge-pill badge-missed" title="Missing Out-Punch on: ${emp.missed_out_punches.join(', ')}">No Out-Punch</span> `;
    } else if (emp.absent_days && emp.absent_days.length > 0 && emp.attendance_policy === 'standard') {
      statusBadge += `<span class="badge-pill badge-absent">Absent (${emp.absent_days.length}d)</span> `;
    }

    const leavesVal = emp.availed_leaves !== null && emp.availed_leaves !== undefined ? emp.availed_leaves : '';
    const odVal = emp.sv_od !== null && emp.sv_od !== undefined ? emp.sv_od : '';

    tr.innerHTML = `
      <td style="text-align: center; color: #94a3b8; font-weight: 600;">${sNo++}</td>
      <td style="text-align: center; font-weight: 700; color: #0f172a;">${emp.emp_code}</td>
      <td>
        <span class="emp-name-link" onclick="openPortfolio('${emp.emp_code}')" title="Click to view 360° Annual Dossier & Pay Slip">
          ${emp.name}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
        </span>
      </td>
      <td style="color: #64748b; font-size: 0.8rem;">${emp.designation || '-'}</td>
      <td style="color: #64748b; font-weight: 600; font-size: 0.8rem;">${emp.department}</td>
      <td style="text-align: right; font-weight: 600;" id="bio-${emp.emp_code}">${emp.biometric_days}</td>
      <td style="text-align: right; color: #64748b;">${emp.holiday}</td>
      
      <td style="text-align: right;" class="col-leave">
        <input type="number" step="0.5" min="0" max="31" 
               class="cell-input" 
               value="${leavesVal}" 
               placeholder="-"
               onchange="handleInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
      </td>

      <td style="text-align: right;" class="col-od">
        <input type="number" step="0.5" min="0" max="31" 
               class="cell-input" 
               value="${odVal}" 
               placeholder="-"
               onchange="handleInlineEdit('${emp.emp_code}', 'sv_od', this.value, this)">
      </td>

      <td style="text-align: right;" class="col-total-pay" id="total-${emp.emp_code}">
        ${emp.total_pay_days}
      </td>
      <td id="rem-${emp.emp_code}">
        ${statusBadge}
        <span style="font-size: 0.78rem; color: #475569;">${emp.remarks || '-'}</span>
      </td>
      <td style="text-align: center;">
        <div style="display: flex; gap: 0.35rem; justify-content: center;">
          <button class="action-timeline-btn" onclick="openTimelineModal('${emp.emp_code}')" title="Option 2: View and regularize 31-day punch logs">
            📅 Timeline
          </button>
          <button class="action-grant-full-btn" onclick="grantFullAttendance('${emp.emp_code}')" title="Grant 31 Full Pay Days instantly for this month">
            ✔ Full Pay
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// -----------------------------------------------------------------------------
// RENDER SALARY & PAYROLL TABLE
// -----------------------------------------------------------------------------
function renderSalaryTable(thead, tbody) {
  thead.innerHTML = `
    <tr>
      <th style="width: 45px;">S.No</th>
      <th style="width: 80px;">Emp Code</th>
      <th style="width: 220px;">Staff Name (Click for Payslip)</th>
      <th style="width: 100px;">Category</th>
      <th style="width: 70px;">Dept</th>
      <th style="width: 75px; text-align: right;">Pay Days</th>
      <th style="width: 110px; text-align: right;">Base Package ✎</th>
      <th style="width: 105px; text-align: right;">Earned Gross</th>
      <th style="width: 65px; text-align: right;">PT</th>
      <th style="width: 65px; text-align: right;">WF</th>
      <th style="width: 85px; text-align: right;">Other Ded ✎</th>
      <th style="width: 125px; text-align: right; background: #f0fdf4; color: #15803d;">Net Salary (₹)</th>
      <th style="min-width: 160px;">Bank Account & IFSC</th>
      <th style="width: 100px; text-align: center;">Action</th>
    </tr>
  `;

  const query = document.getElementById('search-input').value.toLowerCase().trim();

  const filtered = allSalaryRecords.filter(emp => {
    if (currentDept !== 'all' && emp.department !== currentDept) return false;
    if (currentCategory !== 'all' && emp.category !== currentCategory) return false;

    if (query) {
      const matchName = emp.name.toLowerCase().includes(query);
      const matchCode = emp.emp_code.toLowerCase().includes(query);
      const matchDesig = (emp.designation || '').toLowerCase().includes(query);
      if (!matchName && !matchCode && !matchDesig) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="14" style="text-align: center; padding: 3rem; color: #94a3b8; font-weight: 500;">No salary records found matching the filter.</td></tr>`;
    return;
  }

  let lastDept = null;
  let sNo = 1;

  filtered.forEach(emp => {
    if (emp.department !== lastDept && currentDept === 'all') {
      lastDept = emp.department;
      const deptRow = document.createElement('tr');
      deptRow.className = 'dept-section-row';
      deptRow.innerHTML = `<td colspan="14">Department: ${lastDept}</td>`;
      tbody.appendChild(deptRow);
    }

    const tr = document.createElement('tr');
    tr.id = `sal-row-${emp.emp_code}`;

    let catBadge = 'badge-cat-nt';
    if (emp.category === 'Teaching') {
      catBadge = 'badge-cat-teaching';
    } else if (emp.category === 'Management') {
      catBadge = 'badge-cat-mgt';
    } else if (['Transport', 'Attender', 'Garden Staff', 'Security'].includes(emp.category)) {
      catBadge = 'badge-cat-support';
    }

    tr.innerHTML = `
      <td style="text-align: center; color: #94a3b8; font-weight: 600;">${sNo++}</td>
      <td style="text-align: center; font-weight: 700; color: #0f172a;">${emp.emp_code}</td>
      <td>
        <span class="emp-name-link" onclick="openPortfolio('${emp.emp_code}')" title="Click to view detailed Pay Slip & breakdown">
          ${emp.name}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
        </span>
        <div style="font-size: 0.72rem; color: #94a3b8;">${emp.designation || 'Staff'}</div>
      </td>
      <td><span class="badge-pill ${catBadge}">${emp.category}</span></td>
      <td style="color: #64748b; font-weight: 600; font-size: 0.78rem;">${emp.department}</td>
      <td style="text-align: right; font-weight: 700; color: #0f172a;">${emp.total_pay_days}</td>
      
      <!-- Inline Editable Base Salary -->
      <td style="text-align: right;">
        <input type="number" step="500" min="0" 
               class="cell-sal-input" 
               value="${emp.base_salary}" 
               title="Edit monthly base package"
               onchange="handleSalaryInlineEdit('${emp.emp_code}', 'base_salary', this.value, this)">
      </td>

      <!-- Earned Gross Total -->
      <td style="text-align: right; font-weight: 700; color: #475569;" id="sal-gross-${emp.emp_code}">
        ₹${Math.round(emp.gross_salary).toLocaleString('en-IN')}
      </td>

      <!-- PT -->
      <td style="text-align: right; color: #64748b; font-size: 0.8rem;" id="sal-pt-${emp.emp_code}">
        ₹${emp.pt_deduction}
      </td>

      <!-- WF -->
      <td style="text-align: right; color: #64748b; font-size: 0.8rem;" id="sal-wf-${emp.emp_code}">
        ₹${emp.wf_deduction}
      </td>

      <!-- Inline Editable Other Deductions -->
      <td style="text-align: right;">
        <input type="number" step="50" min="0" 
               class="cell-sal-input" 
               style="width: 75px;"
               value="${emp.other_deductions || 0}" 
               title="Edit other deductions"
               onchange="handleSalaryInlineEdit('${emp.emp_code}', 'other_deductions', this.value, this)">
      </td>

      <!-- Net Salary Highlight -->
      <td style="text-align: right; font-weight: 800; font-size: 0.92rem; color: #15803d; background: #f0fdf4;" id="sal-net-${emp.emp_code}">
        ₹${Math.round(emp.net_salary).toLocaleString('en-IN')}
      </td>

      <!-- Bank Details -->
      <td>
        <div style="font-size: 0.75rem; font-weight: 700; color: #1e3a8a;">${emp.bank_name || 'PNB'} ${emp.account_no || 'Pending'}</div>
        <div style="font-size: 0.68rem; color: #64748b;">${emp.ifsc_code || 'PUNB0401700'}</div>
      </td>

      <!-- Action -->
      <td style="text-align: center;">
        <button class="action-timeline-btn" style="background: #f0fdf4; color: #15803d; border-color: #86efac;" onclick="openPortfolio('${emp.emp_code}')" title="View Month Pay Slip">
          💰 Pay Slip
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Inline Salary Edit Handler
async function handleSalaryInlineEdit(empCode, field, value, inputEl) {
  try {
    inputEl.classList.remove('saved');
    const res = await fetch('/api/salary/update-monthly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        emp_code: empCode,
        field: field,
        value: value === '' ? 0 : parseFloat(value),
        month_year: currentMonth
      })
    });
    const data = await res.json();
    if (data.status === 'success') {
      inputEl.classList.add('saved');
      setTimeout(() => inputEl.classList.remove('saved'), 1500);

      loadData();
      showToast(`✔ Updated salary for Emp ${empCode}`);
    }
  } catch (err) {
    alert('Error saving salary edit');
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
  if (psIt) psIt.textContent = f(curSal.other_deductions);

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
