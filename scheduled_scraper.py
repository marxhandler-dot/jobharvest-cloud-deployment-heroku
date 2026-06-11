from database import initialize_db
from scraper import scrape_jobs
from config import PAGES_TO_SCRAPE

def sched_scraper():
    connection = initialize_db()
    results = scrape_jobs(connection, PAGES_TO_SCRAPE)
    connection.close()

    print("Your scheduled scraper has run successfully!")
    print(results)

if __name__ == "__main__":
    sched_scraper()