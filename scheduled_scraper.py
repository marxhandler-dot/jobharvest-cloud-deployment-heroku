# =============================================================================
# scheduled_scraper.py
# -----------------------------------------------------------------------------
# Standalone entry point designed to be triggered by an external scheduler
# (e.g. cron, APScheduler, Heroku Scheduler) rather than an HTTP request.
# It reuses the same scrape_jobs() logic as the API, just without Flask.
# =============================================================================

from database import initialize_db   # Opens a DB connection and ensures tables exist
from scraper import scrape_jobs      # Core scraping logic shared with the API
from config import PAGES_TO_SCRAPE   # Number of pages to visit per run


def sched_scraper():
    """Run one full scrape cycle and print the results to stdout.

    Intended to be called by a scheduler on a timer (e.g. every hour or daily).
    Opens its own DB connection rather than reusing one, so it can run
    completely independently of the Flask app — no web server needed.

    Side effects:
        - New job listings are inserted into the database.
        - A scrape run record is logged to scrape_runs.
        - A summary is printed to stdout for the scheduler's log output.
    """
    # Initialize a fresh connection — the scheduler runs this as its own process,
    # so there's no existing connection to reuse from the web app.
    connection = initialize_db()

    results = scrape_jobs(connection, PAGES_TO_SCRAPE)

    # Always close the connection when done to release the DB resource.
    # Leaving connections open can exhaust the DB's connection pool over time.
    connection.close()

    # Print to stdout so the scheduler (cron, Heroku, etc.) can capture the
    # output in its logs — useful for confirming runs completed successfully.
    print("Your scheduled scraper has run successfully!")
    print(results)


# Only run sched_scraper() when this file is executed directly.
# This guard prevents the function from running if another module imports this file.
# Usage: `python scheduled_scraper.py`
if __name__ == "__main__":
    sched_scraper()