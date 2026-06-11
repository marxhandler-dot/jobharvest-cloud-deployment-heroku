import os

PAGES_TO_SCRAPE = int(os.environ.get('PAGES_TO_SCRAPE', 2))
JOB_SOURCE = "https://www.python.org/jobs"
LIMIT = int(os.environ.get('LIMIT', 10))