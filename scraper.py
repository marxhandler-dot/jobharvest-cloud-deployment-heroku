# =============================================================================
# scraper.py
# -----------------------------------------------------------------------------
# Scrapes python.org/jobs across N pages, persists new listings, and logs
# each run to scrape_runs. Designed to be resilient — per-page exceptions
# are caught and skipped rather than aborting the entire session.
# =============================================================================

import requests                          # HTTP library for fetching web pages
from bs4 import BeautifulSoup            # HTML parser — lets us navigate the page like a tree
from config import JOB_SOURCE            # Root URL, defined once in config to avoid hardcoding
from datetime import datetime            # Used to timestamp each scraped listing and log run times
from database import add_job, add_scrape_job  # DB helpers — scraper doesn't touch SQL directly


def scrape_jobs(connection, pages):
    """Scrape up to `pages` pages of python.org/jobs and persist results.

    Iterates through paginated job listing pages, parses each job's details
    from the HTML, and inserts new listings into the database. Duplicate
    URLs are silently skipped by add_job()'s ON CONFLICT logic — this
    function just counts how many were new vs. already stored.

    Args:
        connection: Active psycopg2 DB connection (caller opens and closes it).
        pages:      Number of listing pages to visit (controlled by config).

    Returns:
        Dict with keys 'total_jobs_found' and 'new_jobs_added' as human-readable strings.
        Example: {"total_jobs_found": "Total jobs found: 30", "new_jobs_added": "Number of new jobs: 5"}
    """
    # Sending a User-Agent header makes the request look like a real browser.
    # Without it, some servers reject requests that come from Python scripts.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # The {} placeholder will be filled in with the page number on each loop iteration.
    url = "https://www.python.org/jobs/?page={}"

    new_jobs = 0       # Counts listings successfully inserted for the first time
    existing_job = 0   # Counts listings skipped because the URL was already in the DB
    start_time = datetime.now()  # Captured before the loop so total run time is accurate

    # range(1, pages + 1) gives us [1, 2, ..., pages] — page numbering starts at 1, not 0.
    for page_num in range(1, pages + 1):
        try:
            # .format(page_num) replaces the {} in the URL string with the current page number.
            response = requests.get(url.format(page_num), headers=headers)

            # Force UTF-8 decoding so special characters (accents, etc.) in job titles
            # aren't corrupted when BeautifulSoup reads the response text.
            response.encoding = 'utf-8'

            # Parse the raw HTML into a navigable tree structure.
            # "lxml" is the parser engine — faster and more lenient than Python's built-in html.parser.
            soup = BeautifulSoup(response.text, "lxml")

            # select_one() finds the FIRST element matching the CSS selector.
            # "ol.list-recent-jobs" means: an <ol> tag that has the class "list-recent-jobs".
            jobs = soup.select_one("ol.list-recent-jobs")

            # .select() (without _one) returns ALL matching elements as a list.
            # Each <li> inside the <ol> represents one job listing.
            jobs_list = jobs.select("li")

            for lists in jobs_list:
                # .stripped_strings is a generator that yields all visible text nodes
                # inside the element with leading/trailing whitespace removed.
                # list(...) converts that generator into an indexable list.
                # [-2] is the second-to-last item (job title), [-1] is the last (company name).
                # This relies on the HTML structure staying consistent — fragile but functional.
                job_title = list(lists.select_one(".listing-company-name").stripped_strings)[-2]
                company_name = list(lists.select_one(".listing-company-name").stripped_strings)[-1]

                # .text grabs all text content inside the element as a single string.
                location = lists.select_one(".listing-location").text

                # Build the full URL by prepending the domain to the relative href.
                # e.g. "/jobs/3456/" becomes "https://www.python.org/jobs/3456/"
                job_url = f"https://www.python.org{lists.select_one('.listing-company-name a')['href']}"

                source = JOB_SOURCE
                time_stamp = datetime.now()  # Record when THIS specific listing was scraped

                # "in ... .lower()" checks if the substring appears anywhere in the string,
                # case-insensitively. Using OR because some listings say "Remote" in the
                # title, some in the location — we catch both patterns.
                remote_flag = "remote" in location.lower() or "remote" in job_title.lower()

                # Salary and description require visiting each job's detail page.
                # We skip that to keep scraping fast; these fields stay None for now.
                salary = None
                description = None

                # Attempt to persist this listing. Returns 1 if inserted, 0 if duplicate.
                save_jobs = add_job(
                    connection, job_title, company_name, location,
                    salary, description, job_url, source, time_stamp, remote_flag
                )

                # Use the return value to keep a running tally for the summary report.
                if save_jobs == 1:
                    new_jobs += 1
                else:
                    existing_job += 1

        except Exception as e:
            # Catching broadly here is intentional — a malformed page, network hiccup,
            # or unexpected HTML structure on one page shouldn't kill the whole run.
            # We log the error and move on to the next page.
            print(f"Failed to scrape page {page_num}: {e}")
            continue  # Skip to the next iteration of the for loop

    completion_time = datetime.now()

    # total_jobs_found includes both new and duplicate listings encountered this run.
    total_jobs_found = new_jobs + existing_job

    # A run is considered successful as long as we found at least one listing,
    # even if none were new. "failed" means we got zero results — likely a
    # network issue or a site structure change broke parsing entirely.
    if total_jobs_found > 0:
        status = "success"
    else:
        status = "failed"

    # Log this entire run as a single audit record in scrape_runs.
    # Note: `source` here refers to the variable set inside the loop on the last
    # successful iteration — acceptable since the source URL never changes per run.
    add_scrape_job(connection, source, total_jobs_found, new_jobs, start_time, completion_time, status)

    # Return human-readable strings so the API can pass them directly to the frontend.
    final_results = {
        "total_jobs_found": f"Total jobs found: {total_jobs_found}",
        "new_jobs_added": f"Number of new jobs: {new_jobs}"
    }
    return final_results