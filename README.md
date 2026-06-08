# 🌿 JobHarvest

## Project Overview

JobHarvest automatically goes to Python.org's job board and pulls all the job listings for you — no manual browsing needed. It saves everything to a local database so you can search through jobs, filter by keyword or location, and even export the results to a spreadsheet. Basically, it's a little tool that does the tedious job-hunting legwork so you don't have to.

---

## Features

- **Scrape jobs with one click** — hit the button and it pulls the latest listings from Python.org automatically
- **Search and filter** — find jobs by keyword, location, or filter for remote-only positions
- **Persistent storage** — jobs are saved to a local database, so they stick around even after you close the app
- **Export to CSV** — download your search results as a spreadsheet to sort through offline or share
- **Track scrape history** — see stats like how many jobs were found, how many were new, and how long each scrape took
- **Duplicate prevention** — re-scraping won't flood your database with the same listings twice

---

## Project Structure

```
days17-18-job-listings-aggregator JobHarvest/
├── api.py          # Flask app — all the routes and endpoints live here
├── scraper.py      # Handles fetching and parsing jobs from Python.org
├── database.py     # All database logic — saving, searching, and stats queries
├── config.py       # Central settings — change scrape depth, source URL, limits here
├── jobs.db         # SQLite database (auto-created on first run)
├── templates/
│   └── index.html  # The frontend UI
└── static/
    └── style.css   # Styling for the UI
```

The project follows a clean separation of concerns — scraping, storage, and the API are all in their own files. So if Python.org changes their HTML structure and the scraper breaks, you know exactly where to go fix it. Same idea if you want to swap out the database or add a new endpoint.

---

## Installation

### Prerequisites
- Python 3.6+
- pip

### Install dependencies

```bash
pip install flask requests beautifulsoup4 lxml
```

### Run the app

```bash
python api.py
```

The database gets created automatically on first run — no setup scripts, no migrations. Just open your browser to `http://127.0.0.1:5000` and you're in.

> **Note:** The scraper disables SSL verification (`verify=False`) when making requests, so don't be alarmed if you see a warning about that in the terminal. It's a known shortcut — something to clean up if you're taking this beyond local use.

---

## Usage

### Scrape jobs
Click the **Scrape Jobs** button in the UI, or send a POST request to `/api/scrape`. This pulls fresh listings from Python.org and saves them to the database.

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

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serves the frontend UI |
| POST | `/api/scrape` | Triggers a scrape job and pulls fresh listings from Python.org |
| GET | `/api/jobs` | Returns jobs from the database — supports `keyword`, `location`, `remote`, and `limit` query params |
| GET | `/api/jobs/export` | Downloads filtered job results as a CSV file — accepts the same query params as `/api/jobs` |
| GET | `/api/stats` | Returns scrape history and database stats like total jobs and source breakdown |

---

## Configuration

All settings live in `config.py`:

```python
DB_FILENAME = "jobs.db"       # Name of the SQLite database file
PAGES_TO_SCRAPE = 2           # How many pages to pull from Python.org per scrape
JOB_SOURCE = "https://www.python.org/jobs"  # Target site
LIMIT = 10                    # Default result limit for stats queries
```

---

## Known Limitations

Being upfront about these isn't a bad look — it just shows you know your own codebase.

- **Salary data is always null** — Python.org's job listings don't have a structured salary field, so that column is empty across the board
- **Single source only** — right now it only scrapes Python.org, so the job pool is pretty limited
- **No description scraping** — The description field is null because the scraper only pulls the listing summary from the index page. It does not capture full details from individual listing pages, so I used a nullish coalescing operator to display an alternative message
- **SSL verification is disabled** — `verify=False` is a shortcut that shouldn't stay in production code
- **No scheduling** — scraping is manual only; you have to click the button yourself every time you want fresh data
- **Basic search** — keyword search only matches job titles, not company names or descriptions, so you might miss relevant listings
- **No pagination on the frontend** — if you have hundreds of jobs in the database, they all load at once

---

## Future Improvements

- **Multiple job sources** — add scrapers for LinkedIn, Indeed, or other job boards so the pool isn't limited to Python.org
- **Full job description scraping** — follow each listing's URL and pull the complete job details, not just the summary
- **Salary parsing** — even where salary isn't structured, a lot of listings mention it somewhere in the description; a simple regex or AI extraction could surface that
- **Scheduled scraping** — run scrapes automatically on a schedule (daily, weekly) so the database stays fresh without manual triggering
- **Email alerts** — notify you when a new job matching your saved keywords shows up
- **Better search** — expand keyword matching to cover descriptions, company names, and tags, not just job titles
- **Frontend pagination** — load jobs in pages instead of dumping everything at once
- **Fix the SSL issue** — properly handle certificate verification instead of skipping it
- **Docker support** — containerize the whole thing so setup is literally one command
- **Analytics dashboard** — visualize trends like which companies post most often, average time listings stay up, remote vs on-site ratio over time

The core is solid — these would just take it from a useful local tool to something you could actually ship.