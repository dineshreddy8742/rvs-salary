# RVS Salary & Biometric Attendance Platform

A full-featured Python Flask & SQLite platform for processing biometric machine attendance logs, managing monthly salary computations, leave regularization, holiday policies, and generating audit-ready salary output spreadsheets.

---

## 🚀 Key Features

- **Biometric Attendance Parsing**: Automatically processes raw multi-sheet biometric punch Excel reports (`.xls`).
- **Dynamic Policy & Quotas**:
  - Handles Casual Leaves (CL), On-Duty (OD/SV-OD), and Holidays.
  - Supports VIP/Exempt policy rules (e.g. Principal & Management).
- **Interactive Web Interface**:
  - Month-by-month switching and analytics dashboard.
  - 360° Employee Dossier & Punch Calendar visualization.
  - Day-level regularization & bulk slip adjustment.
  - Active staff filtering and department breakdowns.
- **Excel Export**: Export finalized monthly salary sheets in institution-standard `.xls` formats.
- **Persistent Storage**: Backed by SQLite database for fast queries and multi-month records.

---

## 📁 Project Structure

```text
├── app.py                     # Flask web server & REST API endpoints
├── attendance_engine.py       # Core biometric parsing and attendance calculation engine
├── database.py                # SQLite schema, queries, employee records & mutations
├── export_excel.py            # Formatted Excel sheet generator
├── process_attendance.py       # Standalone CLI utility for batch attendance processing
├── requirements.txt           # Python dependencies
├── .gitignore                 # Git ignore rules
├── static/                    # Frontend UI assets
│   ├── index.html             # Single-page application HTML
│   ├── styles.css             # UI styling & responsive layout
│   ├── app.js                 # Frontend interactions & API client
│   └── rvs-logo.png           # Institution logo
└── rvs_attendance.db          # SQLite database
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.9+
- Git

### 2. Clone the Repository
```bash
git clone https://github.com/dineshreddy8742/rvs-salary.git
cd rvs-salary
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
python app.py
```

Open your browser and navigate to:
```
http://localhost:5000
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/months` | List all available attendance months in database |
| `GET` | `/api/data?month=<name>` | Get attendance records and summary metrics for a month |
| `GET` | `/api/portfolio/<emp_code>` | 360° employee dossier and leave balance |
| `GET` | `/api/employee/<emp_code>/daily` | Daily punch logs and calendar details |
| `POST` | `/api/update` | Update leave, OD, holiday, or biometric days |
| `POST` | `/api/policy` | Update employee attendance policy (standard / exempt) |
| `POST` | `/api/upload` | Upload and seed new raw biometric Excel file |
| `GET` | `/api/export?month=<name>` | Download finalized salary Excel spreadsheet |

---

## 📄 License
Internal use - RVS Group of Institutions.
