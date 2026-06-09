# =============================================================================
# scraper.py
# -----------------------------------------------------------------------------
# Scrapes python.org/jobs across N pages, persists new listings, and logs
# each run to scrape_runs. Designed to be resilient — per-page exceptions
# are caught and skipped rather than aborting the entire session.
# =============================================================================

import requests
from bs4 import BeautifulSoup
from config import JOB_SOURCE
from datetime import datetime
from database import add_job, add_scrape_job


def scrape_jobs(connection, pages):
    """Scrape up to `pages` pages of python.org/jobs and persist results.

    Deduplication is handled downstream by add_job() via the UNIQUE constraint
    on job_url — this function just tracks new vs. existing counts.

    Returns a summary dict: total found and net-new additions.
    """
    # Minimal UA header to avoid bot-detection rejections from python.org.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = "https://www.python.org/jobs/?page={}"

    new_jobs = 0
    existing_job = 0
    start_time = datetime.now()

    for page_num in range(1, pages + 1):
        try:
            # verify=False skips SSL validation — acceptable here for a known
            # public endpoint, but worth revisiting if cert issues are resolved.
            response = requests.get(url.format(page_num), headers=headers, verify=False)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, "lxml")

            jobs = soup.select_one("ol.list-recent-jobs")
            jobs_list = jobs.select("li")

            for lists in jobs_list:
                # .listing-company-name contains interleaved text nodes for both
                # job title and company. stripped_strings[-2] is the title,
                # [-1] is the company — fragile if the HTML structure changes.
                job_title = list(lists.select_one(".listing-company-name").stripped_strings)[-2]
                company_name = list(lists.select_one(".listing-company-name").stripped_strings)[-1]

                location = lists.select_one(".listing-location").text

                # Construct absolute URL from the relative href in the listing anchor.
                job_url = f"https://www.python.org{lists.select_one('.listing-company-name a')['href']}"

                source = JOB_SOURCE
                time_stamp = datetime.now()

                # Heuristic remote detection — checks both location and title
                # since listings are inconsistent about where they indicate remote.
                remote_flag = "remote" in location.lower() or "remote" in job_title.lower()

                # Salary and description aren't available on listing pages;
                # a detail-page fetch would be needed to populate these.
                salary = None
                description = None

                save_jobs = add_job(
                    connection, job_title, company_name, location,
                    salary, description, job_url, source, time_stamp, remote_flag
                )

                if save_jobs == 1:
                    new_jobs += 1
                else:
                    existing_job += 1

        except Exception as e:
            # Log and continue — a broken page shouldn't abort the whole run.
            print(f"Failed to scrape page {page_num}: {e}")
            continue

    completion_time = datetime.now()

    total_jobs_found = new_jobs + existing_job

    # Status reflects whether the scrape yielded any data at all, not whether
    # every page succeeded — a partial scrape still counts as "success".
    if total_jobs_found > 0:
        status = "success"
    else:
        status = "failed"

    add_scrape_job(connection, source, total_jobs_found, new_jobs, start_time, completion_time, status)

    final_results = {
        "total_jobs_found": f"Total jobs found: {total_jobs_found}",
        "new_jobs_added": f"Number of new jobs: {new_jobs}"
    }
    return final_results