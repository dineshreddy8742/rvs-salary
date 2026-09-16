// RVS Salary & Biometric Attendance Web Platform JavaScript
// Multi-Month & Yearly Ledger with 360° Employee Portfolio & VIP Policies

let allEmployees = [];
let currentFilter = 'all';
let currentDept = 'all';
let activeOnly = true;
let currentMonth = 'August -2026';
let activePortfolioEmpCode = null;

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

  // Active Only toggle
  document.getElementById('toggle-active-only').addEventListener('change', (e) => {
    activeOnly = e.target.checked;
    loadData();
  });

  // Export button
  document.getElementById('btn-export').addEventListener('click', () => {
    showToast(`⚡ Exporting ${currentMonth} to output.xls...`);
    window.location.href = `/api/export?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`;
  });

  // Upload file trigger
  const fileInput = document.getElementById('file-input');
  document.getElementById('btn-upload-trigger').addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Ask user for month name or default to current
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

  // Bulk Slips Modal (Option 3)
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

  // Timeline Modal (Option 2)
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

// Load data from backend for active month
async function loadData() {
  try {
    const res = await fetch(`/api/data?month=${encodeURIComponent(currentMonth)}&active_only=${activeOnly}`);
    const data = await res.json();

    if (data.status === 'success') {
      allEmployees = data.employees;
      renderKPIs(data.stats);
      populateDepartmentSelect(data.departments);
      renderTable();
    }
  } catch (err) {
    console.error('Error fetching data:', err);
    showToast('Error loading attendance data');
  }
}

function renderKPIs(stats) {
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

// Render the master spreadsheet table
function renderTable() {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';

  const query = document.getElementById('search-input').value.toLowerCase().trim();

  // Filter records
  const filtered = allEmployees.filter(emp => {
    // Dept filter
    if (currentDept !== 'all' && emp.department !== currentDept) return false;

    // Status pill filter
    if (currentFilter === 'review' && !emp.needs_review) return false;
    if (currentFilter === 'vip' && emp.attendance_policy === 'standard') return false;
    if (currentFilter === 'absent' && (!emp.absent_days || emp.absent_days.length === 0)) return false;
    if (currentFilter === 'leaves' && (!emp.availed_leaves && !emp.sv_od)) return false;

    // Search query
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

  // Group by department
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

    // Policy & Needs review badges
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
        <span class="emp-name-link" onclick="openPortfolio('${emp.emp_code}')" title="Click to view 360° Annual Dossier & Leave Passbook">
          ${emp.name}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
        </span>
      </td>
      <td style="color: #64748b; font-size: 0.8rem;">${emp.designation || '-'}</td>
      <td style="color: #64748b; font-weight: 600; font-size: 0.8rem;">${emp.department}</td>
      <td style="text-align: right; font-weight: 600;" id="bio-${emp.emp_code}">${emp.biometric_days}</td>
      <td style="text-align: right; color: #64748b;">${emp.holiday}</td>
      
      <!-- Option 1: Inline Editable Availed Leaves (CL) -->
      <td style="text-align: right;" class="col-leave">
        <input type="number" step="0.5" min="0" max="31" 
               class="cell-input" 
               value="${leavesVal}" 
               placeholder="-"
               onchange="handleInlineEdit('${emp.emp_code}', 'availed_leaves', this.value, this)">
      </td>

      <!-- Option 1: Inline Editable SV/OD -->
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

// =========================================================================
// EMPLOYEE 360° PORTFOLIO & LEAVE PASSBOOK MODAL
// =========================================================================
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

// =========================================================================
// OPTION 1: INLINE SPREADSHEET QUICK-EDIT HANDLER
// =========================================================================
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
      showToast(`✔ Updated pay days for ${data.portfolio.name}`);
    }
  } catch (err) {
    alert('Error saving inline edit');
  }
}

// =========================================================================
// OPTION 2: 31-DAY PUNCH TIMELINE & REGULARIZATION MODAL
// =========================================================================
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

    // Summary bar
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
