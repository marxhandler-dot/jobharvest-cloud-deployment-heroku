# =============================================================================
# api.py
# -----------------------------------------------------------------------------
# Flask entry point. Defines all HTTP endpoints and wires them to database
# and scraper logic. Each route opens its own DB connection and closes it
# after use — intentional, to avoid shared-state issues across requests.
# =============================================================================

from flask import Flask, jsonify, request, make_response, render_template
# Flask         → the core web framework class that powers this whole app
# jsonify       → converts a Python dict/list into a proper JSON HTTP response
#                 and automatically sets Content-Type: application/json
# request       → a global object Flask populates with incoming request data
#                 (query params, form data, headers, etc.) for the current request
# make_response → lets us build a response manually so we can customise headers
#                 (needed for the CSV download endpoint)
# render_template → loads an HTML file from the templates/ folder, renders it,
#                   and returns it as the HTTP response body

from database import initialize_db, search_jobs, get_stats
# initialize_db → opens a DB connection and creates tables if they don't exist yet
# search_jobs   → queries the jobs table with optional keyword/location/remote filters
# get_stats     → returns aggregate statistics (totals, recent jobs, run history)

from scraper import scrape_jobs      # The function that fetches and stores job listings
from config import PAGES_TO_SCRAPE   # How many pages to scrape per run (set once in config)

import csv   # Built-in module for writing comma-separated values
import io    # Built-in module for in-memory file-like objects (avoids writing to disk)
from datetime import datetime


# Flask(__name__) creates the application instance.
# __name__ tells Flask where to look for templates and static files
# relative to this file — important when the app is imported as a module.
app = Flask(__name__)


@app.route("/")
def home():
    """Serve the frontend single-page application.

    render_template() looks inside the templates/ directory for 'index.html'.
    Flask handles the file path automatically — no need to specify the full path.
    """
    return render_template('index.html')


@app.route('/api/scrape', methods=['POST'])
def scraper():
    """Trigger a fresh scrape of python.org/jobs and return a summary.

    Why POST and not GET?
    HTTP GET should only *read* data (safe and idempotent). This endpoint
    *writes* to the database, so POST is the semantically correct verb.

    Flow: open DB → run scraper → close DB → return summary as JSON.

    Returns:
        JSON dict with keys 'total_jobs_found' and 'new_jobs_added'.
        Example: {"total_jobs_found": "Total jobs found: 30", "new_jobs_added": "Number of new jobs: 5"}
    """
    # Open a fresh connection for this request — not shared with other requests.
    connection = initialize_db()
    results = scrape_jobs(connection, PAGES_TO_SCRAPE)
    connection.close()  # Always close after the work is done to free the DB resource

    # jsonify() wraps the Python dict in an HTTP 200 response with the
    # correct Content-Type header set automatically.
    return jsonify(results)


@app.route('/api/jobs')
def locate_jobs():
    """Search and return job listings with optional filters.

    All query parameters are optional. When combined, filters use AND logic —
    a job must satisfy every provided filter to appear in the results.

    Query Params:
        keyword  (str):  Substring to match against job title.
        location (str):  Substring to match against location field.
        remote   (bool): Pass 'true' to return only remote-flagged jobs.
        limit    (int):  Cap the number of results returned.

    Returns:
        JSON array of job objects. Empty array if nothing matches.
    """
    connection = initialize_db()

    # request.args is a dict-like object holding all URL query parameters.
    # .get('keyword') returns None when the parameter isn't present in the URL,
    # which tells search_jobs() to skip that filter entirely — no error thrown.
    key_word = request.args.get('keyword')
    location = request.args.get('location')

    # Query params are always plain strings, so we manually convert to boolean.
    # Default is 'false' so omitting the param means "don't filter by remote".
    # .lower() == "true" evaluates to True only when the string is exactly "true".
    remote = request.args.get('remote', 'false').lower() == "true"

    # type=int tells Flask to cast the string to an integer automatically.
    # Returns None (not an error) when the parameter is absent.
    limit = request.args.get('limit', type=int)

    results = search_jobs(connection, key_word, location, remote, limit)
    connection.close()
    return jsonify(results)


@app.route('/api/stats')
def statistics():
    """Return aggregate statistics about stored jobs and past scrape runs.

    Useful for powering a dashboard — total job count, recent additions,
    source breakdown, and scrape history all come back in one call.

    Returns:
        JSON object with keys: total_jobs, recent_add, src_breakdown, scrape_breakdown.
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
    remote, limit) so users get exactly what they were viewing, just as a file.

    Why io.StringIO instead of writing to disk?
    StringIO creates a file-like object that lives entirely in RAM. There's
    no temp file to clean up, and the response is faster since no disk I/O occurs.

    Returns:
        A CSV file download named 'job_report.csv'.
    """
    connection = initialize_db()

    # Identical filter logic to /api/jobs — consistent UX across both endpoints.
    key_word = request.args.get('keyword')
    location = request.args.get('location')
    remote = request.args.get('remote', 'false').lower() == "true"
    limit = request.args.get('limit', type=int)

    results = search_jobs(connection, key_word, location, remote, limit)

    # Column headers for the CSV — DictWriter uses this list to determine
    # both the header row and the order in which dict values are written.
    field_names = ['job_title', 'company_name', 'location', 'salary', 'description',
                   'job_url', 'source', 'time_stamp', 'remote_flag']

    # io.StringIO() creates a writable buffer in memory — behaves exactly like
    # a file but never touches the filesystem.
    output = io.StringIO()

    # DictWriter maps each dict's keys to the correct CSV column automatically.
    writer = csv.DictWriter(output, fieldnames=field_names)

    # writeheader() writes the field_names list as the first CSV row (column labels).
    writer.writeheader()

    # writerows() iterates over the results list and writes each dict as one CSV row.
    # Each key in the dict maps to the matching column name in field_names.
    writer.writerows(results)
    connection.close()

    # .getvalue() extracts everything written to the in-memory buffer as one string.
    content = output.getvalue()

    # make_response() lets us build the response manually so we can set custom headers.
    response = make_response(content)

    # Tell the browser this is CSV data, not HTML — affects how it handles it.
    response.headers['Content-Type'] = 'text/csv'

    # 'attachment' instructs the browser to download the file instead of rendering it.
    # filename= sets the default name that appears in the user's Save dialog.
    response.headers['Content-Disposition'] = 'attachment; filename=job_report.csv'
    return response


@app.route('/health')
def health_check():
    """Lightweight liveness probe for monitoring tools and load balancers.

    Attempts a real DB connection so the health check catches database
    outages, not just "is the Python process running".

    Returns:
        JSON with application_status, database_status, current_timestamp,
        and application_version. HTTP 200 in both the healthy and unhealthy
        cases — the consumer should inspect the JSON body, not just the status code.
    """
    try:
        connection = initialize_db()
        if connection:
            good_results = {
                'application_status': 'active',
                # strftime formats the datetime as a human-readable string.
                # "%B %d, %Y at %I:%M %p" → e.g. "June 15, 2026 at 02:30 PM"
                'current_timestamp': datetime.now().strftime("%B %d, %Y at %I:%M %p"),
                'database_status': 'connection was healthy',
                'application_version': 'version 1.0'
            }
            connection.close()
            return jsonify(good_results)

    except Exception as e:
        # If initialize_db() raises (e.g. wrong credentials, DB is down),
        # we catch it here and return a descriptive error in the JSON body
        # instead of letting Flask return a 500 error page.
        bad_results = {
                'application_status': 'inactive',
                'current_timestamp': datetime.now().strftime("%B %d, %Y at %I:%M %p"),
                'database_status': f'connection was unhealthy: {e}',
                'application_version': 'version 1.0'
            }
        return jsonify(bad_results)


# This block only runs when the file is executed directly: `python api.py`
# It does NOT run when a production WSGI server (gunicorn, uWSGI) imports this file.
# debug=True enables auto-reload on code changes and shows detailed error pages —
# never use debug=True in production as it exposes internals to anyone who hits an error.
if __name__ == "__main__":
    app.run(debug=True)