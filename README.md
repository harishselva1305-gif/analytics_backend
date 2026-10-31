# MediSafe AI

MediSafe AI is an educational medicine side-effect reporting and safety analytics project. It provides session-authenticated report submission, ownership-restricted records, admin review, aggregate analytics, CSV export, and a small synthetic text-classification demonstration.

> **Educational use only.** This project is not a medical device, does not diagnose, recommend treatment, verify medicine safety, or establish that a medicine caused a reported experience. Reports are user-submitted and have not been independently validated.

## Requirements

- Python 3.10 or newer (use a Python release supported by the selected package wheels).
- Windows PowerShell for the commands below.
- Internet access to load Chart.js from its CDN in the browser.

## Install and run (Windows PowerShell)

Open PowerShell in the `MediSafe-AI` project folder and run:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. If PowerShell blocks activation, allow it for the current terminal with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. `manage.py migrate` enables Django's sync step for this intentionally single-file app, creating its tables without a separate migrations package. SQLite data is stored in `db.sqlite3`.

Local development uses `DEBUG=1` and a development-only fallback key. Production deployments use `DEBUG=0`; Vercel production forces it off even if `DJANGO_DEBUG` is accidentally set to `1`. A real `DJANGO_SECRET_KEY` is required whenever debug is off.

## Deploy to Vercel

1. Import the `analytics_backend` repository into Vercel and set **Root Directory** to the repository root (`./`), where `manage.py`, `requirements.txt`, and `vercel.json` are located.
2. Keep the Django framework preset. The root `vercel.json` selects Django, and `backend/backend.py` exposes `wsgi.application` for Vercel's Django runtime.
3. In **Project Settings → Environment Variables**, add `DJANGO_SECRET_KEY` with a newly generated secret for Production and Preview. Generate one locally with:

   ```powershell
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

4. Set `DJANGO_DEBUG` to `0` for Production. Vercel's `VERCEL_URL` and `VERCEL_PROJECT_PRODUCTION_URL` are read automatically. All `*.vercel.app` deployment hosts and both local development hosts are already allowed. If you attach a custom domain, add it to `DJANGO_ALLOWED_HOSTS` as a comma-separated hostname list, for example `medisafe.example.com`.
5. Redeploy after changing environment variables or project settings.

The separate `analytics_frontend` Vercel project can proxy `/api/`, `/login/`, `/customer/`, `/admin/`, and `/django-admin/` to this Django deployment using external rewrites in its root `vercel.json`. Django trusts `https://analyticsfrontend.vercel.app` for CSRF by default. Add any frontend preview or custom origins to `DJANGO_CSRF_TRUSTED_ORIGINS` as a comma-separated list before using unsafe API requests from those origins.

Vercel's local SQLite file is not persistent storage. Use a managed database and shared cache for data that must survive deployments or serve multiple instances. Do not use real patient information.

## API

All endpoints are same-origin. Except for registration, login, and CSRF bootstrap, requests require a logged-in session. Unsafe session-authenticated requests require the CSRF token obtained from `GET /api/csrf/`; send it in `X-CSRFToken`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/csrf/` | Set and return a CSRF token |
| POST | `/api/register/` | Register with `username`, optional `email`, and `password` |
| POST | `/api/login/` | Start a session with `username` and `password` |
| POST | `/api/logout/` | End the authenticated session |
| GET | `/api/me/` | Current user and admin flag |
| GET | `/api/medicines/?q=...` | Search the medicine catalogue |
| POST | `/api/medicines/` | Add a verified catalogue entry (administrator only) |
| GET | `/api/reports/?q=...&status=...&page=...` | List the caller's reports (admins can see all) |
| POST | `/api/reports/` | Submit a report |
| GET | `/api/reports/<uuid>/` | Retrieve an authorized report |
| PATCH | `/api/reports/<uuid>/review/` | Change status/category (administrator only) |
| GET | `/api/analytics/overview/` | Report totals and review distribution |
| GET | `/api/analytics/medicines/` | Counts by medicine |
| GET | `/api/analytics/symptoms/` | Counts by predicted/reviewed category |
| GET | `/api/analytics/monthly/` | Counts by report creation month |
| POST | `/api/ai/classify/` | Classify submitted symptom/description text |
| GET | `/api/reports/export.csv` | Export only authorized reports |

Report submission JSON fields: `medicine_name`, `report_date` (`YYYY-MM-DD`), `symptoms` (text or list), `description`, `consent` (must be `true`), and optional `duration` and `age_range` (`under-18`, `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, or `65+`). Unknown user-entered medicine names are recorded as unverified. Administrator-created catalogue entries are marked verified. Administrators are Django staff/superuser accounts.

## Text categorization

The backend uses Pandas and a scikit-learn TF-IDF/logistic-regression pipeline trained from the clearly synthetic, in-source `SYNTHETIC_TRAINING_DATA`. Predictions are only rough educational text categories, with model confidence, and are not clinical judgments. Empty input or unavailable dependencies return `Unclassified`. A human administrator can replace the category during review; review status and category changes are recorded in review history. Synthetic examples are not representative of actual patients or medicines.

## Tests

Run the backend's focused Django API test suite:

```powershell
python manage.py test
```

Tests cover registration and login errors, input validation, report creation, ownership enforcement, admin review permissions, analytics with an empty database, classification fallback, CSV formula safety, and CSRF enforcement.

## Project layout

```text
analytics_backend/
├── frontend/
│   └── templates/
│       ├── index.html
│       └── login.html
├── backend/
│   ├── backend.py       # Django settings, models, API, and tests
│   ├── backend_admin.py
│   └── backend_urls.py
├── manage.py
├── wsgi.py
├── vercel.json
├── requirements.txt
├── README.md
└── .gitignore
```

## Limitations

- The categorizer is trained only on synthetic examples and has no clinical validation.
- SQLite and Django's local-memory cache are for coursework/development, not multi-instance production.
- Rate limiting uses Django REST Framework's default cache and is not a substitute for infrastructure controls.
- The browser loads Chart.js from a CDN; offline use requires a locally served library.
- User consent is stored with each submission; the platform is not designed for identifiable health data or regulatory compliance.
