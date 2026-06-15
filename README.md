# 🌿 JobHarvest

## Project Overview

JobHarvest automatically goes to Python.org's job board and pulls all the job listings for you — no manual browsing needed. It saves everything to a PostgreSQL database so you can search through jobs, filter by keyword or location, and even export the results to a spreadsheet. The app runs on Heroku with a scheduled scraper that keeps the database fresh automatically — no manual triggering needed.

---

## Features

- **Scrape jobs with one click** — hit the button and it pulls the latest listings from Python.org automatically
- **Scheduled scraping** — Heroku Scheduler runs the scraper hourly so the database stays fresh without manual triggering
- **Search and filter** — find jobs by keyword, location, or filter for remote-only positions
- **Persistent storage** — jobs are saved to a Heroku Postgres database, so data survives restarts and redeploys
- **Export to CSV** — download your search results as a spreadsheet to sort through offline or share
- **Track scrape history** — see stats like how many jobs were found, how many were new, and when each scrape ran
- **Duplicate prevention** — re-scraping won't flood your database with the same listings twice
- **Health check endpoint** — `/health` returns live app status and database connection info

---

## Project Structure

```
days19-20-cloud-deployment-heroku/
├── api.py                # Flask app — all the routes and endpoints live here
├── scraper.py            # Handles fetching and parsing jobs from Python.org
├── database.py           # All database logic — saving, searching, and stats queries (PostgreSQL via psycopg2)
├── config.py             # Central settings — reads from environment variables with local fallbacks
├── scheduled_scraper.py  # Standalone script run by Heroku Scheduler for automated scraping
├── Procfile              # Tells Heroku how to start the app (gunicorn)
├── requirements.txt      # All dependencies for Heroku to install
├── runtime.txt           # Pins the Python version on Heroku (Python 3.13.3)
├── .gitignore            # Excludes venv/, __pycache__/, and jobs.db from version control
├── templates/
│   └── index.html        # The frontend UI
└── static/
    └── style.css         # Styling for the UI
```

The project follows a clean separation of concerns — scraping, storage, and the API are all in their own files. This paid off during the SQLite-to-PostgreSQL migration: because all database logic lives in `database.py`, it was the only file that needed to change. Same idea if you want to swap the database again or add a new endpoint.

---

## Tech Stack

- **Backend:** Python / Flask
- **Database:** PostgreSQL (Heroku Postgres Essential 0)
- **Production server:** Gunicorn
- **Deployment:** Heroku (GitHub-connected deployment)
- **Scheduling:** Heroku Scheduler (runs `scheduled_scraper.py` hourly)
- **DB driver:** psycopg2-binary

---

## Deployment

The app is deployed on Heroku with GitHub-connected deployment. Three files are required for Heroku to run the app:

- **`requirements.txt`** — lists all external packages Heroku needs to install
- **`Procfile`** — tells Heroku how to start the app: `web: gunicorn api:app`
- **`runtime.txt`** — pins the Python version: `python-3.13.3`

The database is a Heroku Postgres (Essential 0) addon, which automatically sets a `DATABASE_URL` environment variable. The app reads this at runtime in `database.py` and handles Heroku's `postgres://` prefix by converting it to `postgresql://` (required by modern drivers).

Sensitive values (`DATABASE_URL`) are never stored in code — they live as Heroku Config Vars. Configurable settings like `PAGES_TO_SCRAPE` and `LIMIT` are also set as Config Vars and read in `config.py` via `os.environ.get()` with local fallback defaults.

---

## Installation (Local Development)

### Prerequisites
- Python 3.6+
- pip
- A local PostgreSQL server

### Set up a virtual environment

```bash
python -m venv venv
venv\Scripts\Activate.ps1   # Windows
# or
source venv/bin/activate    # macOS/Linux
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure the database

Set a `DATABASE_URL` environment variable pointing to your local PostgreSQL instance, or the app will fall back to `postgresql://localhost/jobharvest`.

### Run the app

```bash
python api.py
```

The database tables are created automatically on first run. Open your browser to `http://127.0.0.1:5000`.

---

## Usage

### Scrape jobs
Click the **Scrape Jobs** button in the UI, or send a POST request to `/api/scrape`. This pulls fresh listings from Python.org and saves them to the database. The Heroku Scheduler also runs this automatically every hour via `scheduled_scraper.py`.

### Search jobs
Use the search bar in the UI to filter by keyword. You can also hit the API directly with query parameters:

```
GET /api/jobs?keyword=django&location=remote&remote=true&limit=20
```

### Export data
Download your current search results as a CSV:

```
GET /api/jobs/export?keyword=django
```

### View stats
Check scrape history and database totals:

```
GET /api/stats
```

### Health check
Verify the app and database connection are live:

```
GET /health
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serves the frontend UI |
| POST | `/api/scrape` | Triggers a scrape job and pulls fresh listings from Python.org |
| GET | `/api/jobs` | Returns jobs from the database — supports `keyword`, `location`, `remote`, and `limit` query params |
| GET | `/api/jobs/export` | Downloads filtered job results as a CSV file — accepts the same query params as `/api/jobs` |
| GET | `/api/stats` | Returns scrape history and database stats like total jobs and source breakdown |
| GET | `/health` | Returns app status, current timestamp, database connection status, and app version |

---

## Configuration

Settings live in `config.py` and are read from environment variables with fallback defaults for local development:

```python
import os

PAGES_TO_SCRAPE = int(os.environ.get('PAGES_TO_SCRAPE', 2))
JOB_SOURCE = "https://www.python.org/jobs"
LIMIT = int(os.environ.get('LIMIT', 10))
```

`DATABASE_URL` is read directly in `database.py` (not through `config.py`) because it contains a password and must never be committed to version control. On Heroku, `PAGES_TO_SCRAPE` and `LIMIT` can be tuned via the Config Vars dashboard without touching or redeploying the code.

---

## Known Limitations

- **Salary data is always null** — Python.org's job listings don't have a structured salary field, so that column is empty across the board
- **Single source only** — right now it only scrapes Python.org, so the job pool is pretty limited
- **No description scraping** — the description field is null because the scraper only pulls the listing summary from the index page; a nullish coalescing fallback message is shown instead
- **Basic search** — keyword search only matches job titles, not company names or descriptions, so you might miss relevant listings
- **No pagination on the frontend** — if you have hundreds of jobs in the database, they all load at once

---

## Future Improvements

- **Multiple job sources** — add scrapers for LinkedIn, Indeed, or other job boards so the pool isn't limited to Python.org
- **Full job description scraping** — follow each listing's URL and pull the complete job details, not just the summary
- **Salary parsing** — even where salary isn't structured, a lot of listings mention it somewhere in the description; a simple regex or AI extraction could surface that
- **Email alerts** — notify you when a new job matching your saved keywords shows up
- **Better search** — expand keyword matching to cover descriptions, company names, and tags, not just job titles
- **Frontend pagination** — load jobs in pages instead of dumping everything at once
- **Docker support** — containerize the whole thing so setup is literally one command
- **Analytics dashboard** — visualize trends like which companies post most often, average time listings stay up, remote vs on-site ratio over time

The core is solid and running in production — these would just take it further.