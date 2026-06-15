# =============================================================================
# database.py
# -----------------------------------------------------------------------------
# Owns everything related to PostgreSQL: connecting, creating tables, inserting
# rows, and querying data. No raw SQL lives outside this file — keeping it here
# makes the rest of the codebase easier to read and test.
# =============================================================================

import psycopg2                  # Third-party PostgreSQL driver for Python
from config import LIMIT         # Default row cap imported from central config
import os
from psycopg2 import extras      # Gives us RealDictCursor (rows as dicts, not tuples)


# Read the connection string from the environment so credentials never live in code.
# Falls back to a local dev database when the env var isn't set.
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/jobharvest')

# Some hosting providers (e.g. Heroku) use the older "postgres://" scheme.
# psycopg2 only accepts "postgresql://", so we silently fix the prefix here.
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ---------------------------------------------------------------------------
# Table definitions as SQL strings
# ---------------------------------------------------------------------------
# CREATE TABLE IF NOT EXISTS means running this multiple times is safe —
# the table is only created on the very first run, never duplicated.

jobs_table = """CREATE TABLE IF NOT EXISTS jobs_table(
    id SERIAL PRIMARY KEY,      -- Auto-incrementing unique row ID
    job_title TEXT NOT NULL,
    company_name TEXT NOT NULL,
    location TEXT NOT NULL,
    salary REAL,                -- Nullable: most listings don't publish salary
    description TEXT,           -- Nullable: not available from the listing page
    job_url TEXT UNIQUE,        -- UNIQUE enforces deduplication at the DB level
    source TEXT NOT NULL,
    time_stamp TIMESTAMPTZ NOT NULL,  -- Timezone-aware timestamp
    remote_flag BOOLEAN               -- True when listing signals remote work
)"""

scrape_runs = """CREATE TABLE IF NOT EXISTS scrape_runs(
    id SERIAL PRIMARY KEY,
    source_site TEXT NOT NULL,
    jobs_found INTEGER NOT NULL,
    jobs_added INTEGER NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    completion_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL        -- "success" or "failed" — logged per run
)"""


def initialize_db():
    """Open a connection and ensure both tables exist before returning.

    Called at the start of every request so the schema is always ready,
    even on a brand-new database. The connection is returned to the caller
    so they control when it gets closed.

    Returns:
        psycopg2 connection object (caller is responsible for closing it).
    """
    connection = psycopg2.connect(DATABASE_URL)
    cursor = connection.cursor()

    # Execute both CREATE TABLE statements — harmless if tables already exist.
    cursor.execute(jobs_table)
    cursor.execute(scrape_runs)

    # Persist the table creation; without commit() the schema change is rolled back.
    connection.commit()
    return connection


def add_job(connection, job_title, company_name, location, salary, description,
            job_url, source, time_stamp, remote_flag):
    """Insert a single job listing, silently skipping it if the URL already exists.

    The ON CONFLICT (job_url) DO NOTHING clause is the key deduplication
    mechanism — because job_url has a UNIQUE constraint, any attempt to insert
    a duplicate URL is quietly ignored rather than raising an error.

    Args:
        connection:   Active psycopg2 connection.
        job_title:    Title of the role.
        company_name: Hiring company.
        location:     Location string as scraped.
        salary:       Float or None.
        description:  Full description or None.
        job_url:      Canonical URL — used as the unique key.
        source:       Root URL of the scraped site.
        time_stamp:   datetime of when this listing was scraped.
        remote_flag:  Boolean — True if listing appears to be remote.

    Returns:
        1 if the row was inserted (new job), 0 if it was skipped (duplicate).
    """
    # RealDictCursor makes rows behave like dicts (row['column']) instead of
    # positional tuples (row[0]), which is much easier to work with.
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """INSERT INTO jobs_table(
            job_title, company_name, location, salary, description,
            job_url, source, time_stamp, remote_flag
        ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (job_url) DO NOTHING""",
        # The %s placeholders are filled in order by this tuple.
        # Using parameterised queries (never f-strings with SQL) prevents SQL injection.
        (job_title, company_name, location, salary, description, job_url, source, time_stamp, remote_flag)
    )
    connection.commit()

    # cursor.rowcount is 1 when a row was actually inserted, 0 when DO NOTHING fired.
    # The scraper uses this to track new vs. duplicate listings.
    row_count = cursor.rowcount
    return row_count


def add_scrape_job(connection, source_site, jobs_found, jobs_added,
                   start_time, completion_time, status):
    """Log a completed scrape session so we have a permanent audit trail.

    Every run is appended as a new row — we deliberately never overwrite
    old records, so you can review the full history of what was scraped and when.

    Args:
        connection:      Active psycopg2 connection.
        source_site:     URL that was scraped.
        jobs_found:      Total listings encountered (new + duplicates).
        jobs_added:      Net-new listings stored this run.
        start_time:      datetime the scrape began.
        completion_time: datetime the scrape finished.
        status:          "success" or "failed".

    Returns:
        1 if the log row was written successfully.
    """
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """INSERT INTO scrape_runs(
            source_site, jobs_found, jobs_added, start_time, completion_time, status
        ) VALUES(%s, %s, %s, %s, %s, %s)""",
        (source_site, jobs_found, jobs_added, start_time, completion_time, status)
    )
    connection.commit()
    row_count = cursor.rowcount
    return row_count


def search_jobs(connection, key_word, location, remote, limit):
    """Query job listings with any combination of optional filters.

    Filters are only applied when the caller provides a non-None / non-False
    value. Conditions are collected into a list and joined with AND, so a job
    must satisfy every provided filter to appear in the results.

    Args:
        connection: Active psycopg2 connection.
        key_word:   Substring to match against job_title. None = skip filter.
        location:   Substring to match against location.  None = skip filter.
        remote:     True = only return remote listings.   False = skip filter.
        limit:      Max rows to return.                   None = no cap.

    Returns:
        List of dicts, one per matching job. Empty list if nothing matches.
    """
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Start with the base query and build up the WHERE clause dynamically.
    query = "SELECT * FROM jobs_table"
    conditions = []  # Each active filter adds one condition string here
    params = []      # Corresponding values — kept in sync with conditions

    if key_word is not None:
        # ILIKE with % wildcards on both sides = "contains" matching, not exact.
        conditions.append("job_title ILIKE %s")
        params.append(f"%{key_word}%")  # e.g. "%python%" matches "Senior Python Dev"

    if location is not None:
        conditions.append("location ILIKE %s")
        params.append(f"%{location}%")

    if remote:
        # Only filter on this when the caller explicitly requested remote jobs.
        # When remote=False we skip the filter entirely (don't exclude remote listings).
        conditions.append("remote_flag = %s")
        params.append(remote)

    # Only attach WHERE if at least one filter is active; otherwise return all rows.
    if conditions:
        query += " WHERE " + " AND ".join(conditions)  # e.g. "WHERE job_title LIKE %s AND remote_flag = %s"

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    # params is passed as a tuple so psycopg2 safely substitutes each %s placeholder.
    cursor.execute(query, params)
    job_results = cursor.fetchall()

    # Convert RealDictRow objects to plain Python dicts.
    # RealDictRows look like dicts but aren't JSON-serialisable by default,
    # which would cause Flask's jsonify() to crash without this step.
    jobs_list = [{
        'job_title': job['job_title'],
        'company_name': job['company_name'],
        'location': job['location'],
        'salary': job['salary'],
        'description': job['description'],
        'job_url': job['job_url'],
        'source': job['source'],
        'time_stamp': job['time_stamp'],
        'remote_flag': job['remote_flag']
    } for job in job_results]   # List comprehension: builds a new list by transforming each row

    return jobs_list


def get_stats(connection):
    """Aggregate statistics for the dashboard — totals, recent activity, and run history.

    Runs four separate SELECT queries and bundles their results into one dict
    so the frontend can populate multiple dashboard widgets from a single API call.

    Args:
        connection: Active psycopg2 connection.

    Returns:
        Dict with keys:
            total_jobs     (int)   – total rows in jobs_table
            recent_add     (list)  – last N jobs added, newest first
            src_breakdown  (list)  – job count grouped by source URL
            scrape_breakdown (list)– last N scrape run records
    """
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # COUNT(*) counts every row, including those with NULL values in other columns.
    cursor.execute("SELECT COUNT(*) FROM jobs_table")
    total_jobs = cursor.fetchone()  # Returns a single row: {'count': 42}

    # ORDER BY time_stamp DESC puts the newest jobs first; LIMIT caps the list.
    cursor.execute(
        "SELECT job_title, company_name, time_stamp FROM jobs_table ORDER BY time_stamp DESC LIMIT %s",
        (LIMIT,)
    )
    recent_add = cursor.fetchall()
    # Flatten each RealDictRow into a plain dict with only the fields the frontend needs.
    recent_results = [{
        'job_title': added['job_title'],
        'company_name': added['company_name'],
        'time_stamp': added['time_stamp']
    } for added in recent_add]

    # GROUP BY source lets us see how many jobs came from each scraped site.
    # ORDER BY jobs_added DESC puts the most prolific source at the top.
    cursor.execute(
        "SELECT source, COUNT(*) AS jobs_added FROM jobs_table GROUP BY source ORDER BY jobs_added DESC"
    )
    src_breakdown = cursor.fetchall()
    src_results = [{
        'source': src['source'],
        'jobs_added': src['jobs_added']
    } for src in src_breakdown]

    # Pull the most recent scrape run logs so the dashboard can show run history.
    cursor.execute(
        "SELECT start_time, completion_time, jobs_found, jobs_added, status FROM scrape_runs ORDER BY start_time DESC LIMIT %s",
        (LIMIT,)
    )
    scrape_breakdown = cursor.fetchall()
    scrape_results = [{
        'start_time': scrape['start_time'],
        'completion_time': scrape['completion_time'],
        'jobs_found': scrape['jobs_found'],
        'jobs_added': scrape['jobs_added'],
        'status': scrape['status']
    } for scrape in scrape_breakdown]

    # Bundle everything into one dict — the API endpoint returns this directly.
    results = {
        "total_jobs": int(total_jobs['count']),  # Cast from Decimal to int for JSON safety
        "recent_add": recent_results,
        "src_breakdown": src_results,
        "scrape_breakdown": scrape_results
    }
    return results