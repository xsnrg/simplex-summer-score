# K0IRO Summer of Simplex — Scoring Application

A Flask-based contest scoring web application for the K0IRO Summer of Simplex event.
Participants submit simplex contacts via a public web form; scores are calculated automatically
and displayed on a live leaderboard. Admins can manage submissions and apply bonus multipliers
through a protected dashboard.

---

## Tech Stack

- **Python 3.11+**
- **Flask 3.x** — web framework
- **Flask-SQLAlchemy** — ORM / database layer
- **SQLite** — database (file stored in `instance/`)
- **Werkzeug** — password hashing
- **python-dotenv** — environment variable management
- **pyenv** — recommended Python version manager

---

## Project Structure

```
simplex/
├── run.py                  # App entry point
├── create_admin.py         # One-time admin user creation script
├── requirements.txt
├── .env                    # Environment variables (not committed)
├── .gitignore
├── instance/
│   └── simplex.db          # SQLite database (auto-created, not committed)
├── tests/
│   ├── conftest.py         # Test fixtures and session-scoped app factory
│   ├── test_operator_page.py
│   └── test_adi_parser.py
└── app/
    ├── __init__.py         # App factory
    ├── models.py           # Database models
    ├── routing.py          # All route handlers
    ├── scoring.py          # Scoring logic
    ├── adi_parser.py       # ADIF file parser and validator
    ├── client_auth.py      # Auth decorators (login_required, admin_required)
    ├── static/
    │   ├── css/
    │   │   └── style.css
    │   └── img/
    │       └── logo.svg
    └── templates/
        ├── base.html
        ├── index.html
        ├── submit.html
        ├── leaderboard.html
        ├── operator.html
        ├── login.html
        ├── admin_home.html
        ├── admin_submissions.html
        ├── admin_deleted.html
        ├── scoring_overview.html
        ├── set_multiplier.html
        └── admin_reset.html
```

---

## Setup

### 1. Prerequisites

Ensure you have [pyenv](https://github.com/pyenv/pyenv) installed, along with
[pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv).

### 2. Create and activate a virtual environment

```bash
pyenv virtualenv 3.11.9 simplex
pyenv activate simplex
```

To auto-activate when entering the project directory:

```bash
cd simplex
pyenv local simplex
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-random-secret-key-here
```

Generate a strong secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **Note:** Never commit `.env` to version control. It is listed in `.gitignore`.

### 5. Create the first admin user

The database is created automatically on first run. After starting the app at least
once (or running the factory directly), create your admin account:

```bash
python create_admin.py
```

You will be prompted for a callsign and password. The script can be re-run at any
time to reset a password or add additional admin accounts.

### 6. Run the development server

```bash
flask --app run run --debug
```

The app will be available at `http://localhost:5000`.

---

## Admin Access

The admin login page is intentionally not linked in the navigation. To access it,
navigate directly to:

```
http://localhost:5000/login
```

After logging in, an **Admin** link will appear in the nav bar. Admin features include:

- View and soft-delete submissions (with restore and audit trail)
- Scoring overview with per-operator daily breakdown split by Voice and Digital
- Apply bonus score multipliers per operator per day
- Master reset (wipes all submissions and scores)

---

## Leaderboard & Operator Pages

The leaderboard (`/leaders`) displays operators sorted by total score. Each operator name is a clickable link to their individual submission detail page (`/operator/<callsign>`), showing all non-deleted contacts in a table with mode, frequency, POTA park, and notes columns.

---

## ADI File Upload

Participants can batch-submit contacts from an ADIF (`.adi`) file via the **Submit** page:

1. Click **"Upload ADI"** on the submit form
2. Select your `.adi` file
3. Declare whether any contacts are from POTA parks (**Yes / No**) — this is a per-file binary choice applied to all records with non-empty `POTA` fields
4. The server parses and validates the file, returning a JSON preview (up to 20 records) rendered as an HTML table
5. Review the preview, then click **"Submit All"** to batch-create submissions

**Mode mapping:** FM / LSB / USB / AM → voice; CW / RTTY / SSTV / FT4 / FT8 / PSK31 / JS8 / WINLINK → digital (auto-set `digital_mode`). Unknown digital modes require an explicit `DIGITAL_MODE` field.

---

## Testing

Tests use pytest with session-scoped Flask app factory and a temp SQLite database — no production data is ever touched. Each test gets full table cleanup (drop + recreate) before and after execution.

```bash
pip install pytest pytest-cov
pytest tests/ -v
```

All tables are fully cleared between tests; the temp DB file is removed after the session ends.

---

## Scoring Rules

| Activity | Points |
|---|:---:|
| Voice simplex contact (Ham or GMRS) | 1 |
| Digital simplex contact (SSTV, PSK, RTTY, FT4/8, JS8, Winlink) | 1 |
| Voice simplex contact from a POTA park | 2 |

Admin-applied daily bonus multipliers stack on top of base scores.

---

## Deployment Notes

For production deployment:

- Set `SECRET_KEY` to a strong random value in `.env`
- Run behind a WSGI server such as **gunicorn**:
  ```bash
  pip install gunicorn
  gunicorn -w 4 "run:app"
  ```
- Put a reverse proxy (nginx, Caddy) in front of gunicorn to handle HTTPS
- The `instance/` folder (containing the SQLite database) should be persisted
  and backed up — it is not committed to version control

---

## Environment Variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `SECRET_KEY` | Yes | `devkey-change-in-production` | Flask session signing key |

---

## License

Internal use — K0IRO Iowa Radio Operators.