import psycopg2
from config import LIMIT
import os
from psycopg2 import extras

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/jobharvest')

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

jobs_table = """CREATE TABLE IF NOT EXISTS jobs_table(
    id SERIAL PRIMARY KEY,
    job_title TEXT NOT NULL,
    company_name TEXT NOT NULL,
    location TEXT NOT NULL,
    salary REAL,
    description TEXT,
    job_url TEXT UNIQUE,
    source TEXT NOT NULL,
    time_stamp TEXT NOT NULL,
    remote_flag BOOLEAN
)"""

scrape_runs = """CREATE TABLE IF NOT EXISTS scrape_runs(
    id SERIAL PRIMARY KEY,
    source_site TEXT NOT NULL,
    jobs_found INTEGER NOT NULL,
    jobs_added INTEGER NOT NULL,
    start_time REAL NOT NULL,
    completion_time REAL NOT NULL,
    status TEXT NOT NULL
)"""

def initialize_db():
    connection = psycopg2.connect(DATABASE_URL)
    cursor = connection.cursor()
    cursor.execute(jobs_table)
    cursor.execute(scrape_runs)
    connection.commit()
    return connection


def add_job(connection, job_title, company_name, location, salary, description, job_url, source, time_stamp, remote_flag):
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        """INSERT INTO jobs_table(
            job_title, company_name, location, salary, description,
            job_url, source, time_stamp, remote_flag
        ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (job_url) DO NOTHING""",
        (job_title, company_name, location, salary, description, job_url, source, time_stamp, remote_flag)
    )
    connection.commit()
    row_count = cursor.rowcount
    return row_count


def add_scrape_job(connection, source_site, jobs_found, jobs_added, start_time, completion_time, status):
    """Append a scrape session record. All runs are retained — no upsert logic."""
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
    """Dynamically build a WHERE clause from whichever filters are non-None/non-False.
    Conditions accumulate into a list and are joined with AND — no filter means no WHERE clause.
    LIKE wildcards on both sides give substring matching, not prefix-only."""
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = "SELECT * FROM jobs_table"
    conditions = []
    params = []

    if key_word is not None:
        conditions.append("job_title LIKE %s")
        params.append(f"%{key_word}%")

    if location is not None:
        conditions.append("location LIKE %s")
        params.append(f"%{location}%")

    if remote:
        conditions.append("remote_flag = %s")
        params.append(remote)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    cursor.execute(query, params)
    job_results = cursor.fetchall()

    # Explicitly map Row objects to dicts so callers get serialisable data
    # rather than sqlite3.Row instances, which aren't JSON-serialisable by default.
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
    } for job in job_results]

    return jobs_list


def get_stats(connection):
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT COUNT(*) FROM jobs_table")
    total_jobs = cursor.fetchone()

    cursor.execute(
        "SELECT job_title, company_name, time_stamp FROM jobs_table ORDER BY time_stamp DESC LIMIT %s",
        (LIMIT,)
    )
    recent_add = cursor.fetchall()
    recent_results = [{
        'job_title': added['job_title'],
        'company_name': added['company_name'],
        'time_stamp': added['time_stamp']
    } for added in recent_add]

    cursor.execute(
        "SELECT source, COUNT(*) AS jobs_added FROM jobs_table GROUP BY source ORDER BY jobs_added DESC"
    )
    src_breakdown = cursor.fetchall()
    src_results = [{
        'source': src['source'],
        'jobs_added': src['jobs_added']
    } for src in src_breakdown]

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

    results = {
        "total_jobs": int(total_jobs['count']),
        "recent_add": recent_results,
        "src_breakdown": src_results,
        "scrape_breakdown": scrape_results
    }
    return results