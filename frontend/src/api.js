// API Client for RVS University Payroll Backend

async function handleResponse(res) {
  if (res.status === 401) {
    // Session expired or unauthenticated
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  return res;
}

export async function fetchMonths() {
  const res = await fetch('/api/months').then(handleResponse);
  if (!res.ok) throw new Error('Failed to fetch months');
  return res.json();
}

export async function fetchData(month, activeOnly = true) {
  const url = `/api/data?month=${encodeURIComponent(month)}&active_only=${activeOnly}`;
  const res = await fetch(url).then(handleResponse);
  if (!res.ok) throw new Error('Failed to fetch data');
  return res.json();
}

export async function fetchSalaryAll(month) {
  const url = `/api/salary/all?month=${encodeURIComponent(month)}`;
  const res = await fetch(url).then(handleResponse);
  if (!res.ok) throw new Error('Failed to fetch salary data');
  return res.json();
}

export async function updateEmployeeField(empCode, field, value, month) {
  const res = await fetch('/api/update-employee', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      emp_code: empCode,
      field,
      value,
      month_year: month,
    }),
  }).then(handleResponse);
  if (!res.ok) throw new Error('Failed to update attendance field');
  return res.json();
}

export async function updateSalaryMonthlyField(empCode, field, value, month) {
  const res = await fetch('/api/salary/update-monthly', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      emp_code: empCode,
      month_year: month,
      field,
      value,
    }),
  }).then(handleResponse);
  if (!res.ok) throw new Error('Failed to update salary field');
  return res.json();
}

export async function updateEmployeePackage(payload) {
  const res = await fetch('/api/employee/update-package', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to update employee package');
  }
  return data;
}

export async function addEmployee(payload) {
  const res = await fetch('/api/employee/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to add employee');
  }
  return data;
}

export async function deleteEmployee(empCode) {
  const res = await fetch('/api/employee/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ emp_code: empCode }),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to delete employee');
  }
  return data;
}

export async function deleteManualStaff(deleteCodes = null) {
  const res = await fetch('/api/employee/delete-manual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      delete_all: !deleteCodes || deleteCodes.length === 0,
      codes: deleteCodes || [],
    }),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to delete staff');
  }
  return data;
}

export async function bulkStaffImport(staffList) {
  const res = await fetch('/api/bulk-staff-import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ staff: staffList }),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to import staff');
  }
  return data;
}

export async function revertToBiometric(empCode, month) {
  const res = await fetch('/api/revert-employee', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      emp_code: empCode,
      month_year: month,
    }),
  }).then(handleResponse);
  const data = await res.json();
  if (!res.ok || data.status !== 'success') {
    throw new Error(data.message || 'Failed to revert employee');
  }
  return data;
}

export async function checkUploadStatus(jobId) {
  const res = await fetch(`/api/upload/status/${jobId}`).then(handleResponse);
  if (!res.ok) throw new Error('Status check failed');
  return res.json();
}
