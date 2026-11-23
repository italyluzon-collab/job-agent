import json
import os
import requests
from jobspy import scrape_jobs

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SEEN_FILE = "seen_jobs.json"

SEARCH_TERMS = ["VLSI", "Chip Design", "RTL", "Design Verification , "design"]
LOCATION = "Israel"
EXCLUDE_KEYWORDS = ["senior", "principal", "staff", "lead", "manager", "director"]
HOURS_OLD = 24


def load_seen_jobs():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_jobs(seen_jobs):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_jobs), f, ensure_ascii=False, indent=2)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload, timeout=10)


def is_relevant(title):
    title_lower = str(title).lower()
    return not any(word in title_lower for word in EXCLUDE_KEYWORDS)


def run_agent():
    seen_jobs = load_seen_jobs()
    new_jobs_count = 0

    for term in SEARCH_TERMS:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=LOCATION,
                results_wanted=20,
                hours_old=HOURS_OLD,
            )
        except Exception as e:
            print(f"Error scraping {term}: {e}")
            continue

        if jobs.empty:
            continue

        for _, row in jobs.iterrows():
            job_url = str(row.get("job_url", ""))
            title = str(row.get("title", "Unknown Role"))
            company = str(row.get("company", "Unknown Company"))
            location = str(row.get("location", ""))

            if not job_url or job_url in seen_jobs:
                continue

            if not is_relevant(title):
                continue

            message = (
                f"<b>{title}</b>\n"
                f"Company: {company}\n"
                f"Location: {location}\n"
                f"<a href='{job_url}'>Apply / View Job</a>"
            )
            send_telegram_message(message)
            seen_jobs.add(job_url)
            new_jobs_count += 1

    save_seen_jobs(seen_jobs)
    print(f"Done. Sent {new_jobs_count} new jobs.")


if __name__ == "__main__":
    run_agent()
