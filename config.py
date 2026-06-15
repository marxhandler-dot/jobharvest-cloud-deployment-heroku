# =============================================================================
# config.py
# -----------------------------------------------------------------------------
# Central place for app-wide settings. Pulling values from environment
# variables (os.environ) means you can change behaviour without touching code —
# just set a different env var on the server or in your .env file.
# The int() cast is required because os.environ always returns strings.
# =============================================================================

import os

# How many pages of python.org/jobs to visit per scrape run.
# Defaults to 2 if the env var isn't set — a safe, low-impact starting point.
PAGES_TO_SCRAPE = int(os.environ.get('PAGES_TO_SCRAPE', 2))

# The root URL being scraped. Defined once here so every other module
# imports it rather than hardcoding the same string in multiple places.
JOB_SOURCE = "https://www.python.org/jobs"

# Default cap on how many rows database queries return.
# Keeps responses fast and prevents accidentally dumping thousands of rows.
LIMIT = int(os.environ.get('LIMIT', 10))