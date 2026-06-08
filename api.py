# =============================================================================
# api.py
# -----------------------------------------------------------------------------
# Flask entry point. Defines all HTTP endpoints and wires them to database
# and scraper logic. Each route opens its own DB connection and closes it
# after use — intentional, to avoid shared-state issues across requests.
# =============================================================================

from flask import Flask, jsonify, request, make_response, render_template
# Flask      → the core web framework class
# jsonify    → converts a Python dict/list into a proper JSON HTTP response
# request    → lets us read incoming query parameters and request data
# make_response → lets us build a response object and manually set headers
# render_template → loads an HTML file from the templates/ folder and returns it

from database import initialize_db, search_jobs, get_stats
# initialize_db → creates DB tables if they don't exist, returns a connection
# search_jobs   → queries the jobs table with optional filters
# get_stats     → returns aggregate statistics about stored jobs and scrape runs

from scraper import scrape_jobs      # The function that fetches and stores job listings
from config import PAGES_TO_SCRAPE   # How many pages to scrape per run (set once in config)

import csv   # Built-in module for writing comma-separated values
import io    # Built-in module for working with in-memory streams (no disk writes needed)


# Flask(__name__) creates the application instance.
# __name__ tells Flask where to look for templates and static files
# (relative to this file's location).
app = Flask(__name__)

# Run DB initialization once when the server starts — this ensures the
# tables exist before any request tries to use them. The connection is
# closed right away because each route will open its own fresh connection.
connection = initialize_db()
connection.close()


@app.route("/")
def home():
    """Serve the frontend single-page application.

    render_template() looks for 'index.html' inside the templates/ directory.
    Flask handles the file lookup automatically based on the app's root path.
    """
    return render_template('index.html')


@app.route('/api/scrape', methods=['POST'])
def scraper():
    """Trigger a fresh scrape of python.org/jobs and return a summary.

    Why POST and not GET?
    GET requests should be read-only (safe and idempotent). This endpoint
    writes data to the database, so POST is the semantically correct method.

    Returns:
        JSON dict with keys 'total_jobs_found' and 'new_jobs_added'.
        Example: {"total_jobs_found": "Total jobs found: 30", "new_jobs_added": "Number of new jobs: 5"}
    """
    connection = initialize_db()
    results = scrape_jobs(connection, PAGES_TO_SCRAPE)
    connection.close()

    # jsonify() wraps the Python dict in an HTTP response with
    # Content-Type: application/json set automatically.
    return jsonify(results)


@app.route('/api/jobs')
def locate_jobs():
    """Search and return job listings with optional filters.

    All query parameters are optional. When combined, filters use AND logic
    — a job must match ALL provided filters to be returned.

    Query Params:
        keyword  (str):  Filter by keyword in job title or description.
        location (str):  Filter by location string.
        remote   (bool): Pass 'true' to return only remote jobs. Defaults to false.
        limit    (int):  Cap the number of results returned.

    Returns:
        JSON array of job objects matching the given filters.
    """
    connection = initialize_db()

    # request.args is a dict-like object holding all URL query parameters.
    # .get('keyword') returns None if the parameter wasn't included — which
    # tells search_jobs() to skip that filter entirely.
    key_word = request.args.get('keyword')
    location = request.args.get('location')

    # Query params are always strings, so we manually convert to bool.
    # .get('remote', 'false') returns 'false' as the default if omitted,
    # then .lower() == "true" evaluates to False — a safe, non-None default.
    remote = request.args.get('remote', 'false').lower() == "true"

    # type=int tells Flask to cast the string to an integer for us.
    # Returns None (not an error) if the param is absent.
    limit = request.args.get('limit', type=int)

    results = search_jobs(connection, key_word, location, remote, limit)
    connection.close()
    return jsonify(results)


@app.route('/api/stats')
def statistics():
    """Return aggregate statistics about stored jobs and past scrape runs.

    Returns:
        JSON object with stats like total job count, newest scrape date, etc.
        (Exact shape defined by get_stats() in database.py.)
    """
    connection = initialize_db()
    results = get_stats(connection)
    connection.close()
    return jsonify(results)


@app.route('/api/jobs/export')
def export_job():
    """Export filtered job listings as a downloadable CSV file.

    Accepts the same query parameters as /api/jobs (keyword, location,
    remote, limit). The response is streamed as a file download rather
    than displayed in the browser.

    Why io.StringIO instead of writing to disk?
    StringIO creates an in-memory file-like object. This is faster, avoids
    disk I/O, and means we never have to clean up a temp file afterward.

    Returns:
        A CSV file download named 'job_report.csv'.
    """
    connection = initialize_db()

    # Identical filter logic to /api/jobs — both endpoints share the same
    # query surface so users get a consistent filtering experience.
    key_word = request.args.get('keyword')
    location = request.args.get('location')
    remote = request.args.get('remote', 'false').lower() == "true"
    limit = request.args.get('limit', type=int)

    results = search_jobs(connection, key_word, location, remote, limit)

    # These are the column headers for the CSV — order matters here since
    # DictWriter uses this list to determine column order.
    field_names = ['job_title', 'company_name', 'location', 'salary', 'description',
                   'job_url', 'source', 'time_stamp', 'remote_flag']

    # io.StringIO() creates a buffer that behaves like a file but lives in RAM.
    # csv.DictWriter writes each result dict as a CSV row, matching keys to columns.
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=field_names)

    # writeheader() writes the field_names list as the first row (column labels).
    writer.writeheader()

    # writerows() iterates over the results list and writes each dict as one CSV row.
    writer.writerows(results)
    connection.close()

    # .getvalue() retrieves everything written to the in-memory buffer as one string.
    content = output.getvalue()

    # make_response() lets us build the response manually so we can customize headers.
    response = make_response(content)

    # Tell the browser this is a CSV file, not HTML — affects how it handles the data.
    response.headers['Content-Type'] = 'text/csv'

    # 'attachment' tells the browser to download the file instead of showing it inline.
    # filename= sets the default name shown in the Save dialog.
    response.headers['Content-Disposition'] = 'attachment; filename=job_report.csv'
    return response


# This block only runs when the script is executed directly (e.g. `python api.py`).
# It does NOT run when Flask is started via a WSGI server (gunicorn, etc.) in production.
# debug=True enables auto-reload on code changes and shows detailed error pages.
if __name__ == "__main__":
    app.run(debug=True)