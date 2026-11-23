import json
import os
import re
import requests
from jobspy import scrape_jobs

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SEEN_FILE = "seen_jobs.json"

SEARCH_TERMS = ["VLSI", "Chip Design", "RTL", "Design Verification", "Hardware Student"]
LOCATION = "Israel"
HOURS_OLD = 24
MAX_YEARS_EXPERIENCE = 2

EXCLUDE_TITLE_KEYWORDS = [
    "senior", "sr.", "principal", "staff", "lead", "manager",
    "director", "architect", "head of", "vp", "chief", "team leader"
]

ENTRY_LEVEL_KEYWORDS = [
    "student", "intern", "internship", "junior", "graduate", "new grad",
    "entry level", "entry-level", "fresh grad", "no experience",
    "0-1", "0-2", "1-2", "סטודנט", "מתמחה", "בוגר", "ללא ניסיון", "ג'וניור"
]

EXPERIENCE_PATTERNS = [
    r"(\d+)\s*(?:\+|plus)?\s*(?:-\s*\d+\s*)?years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience",
    r"(?:at least|minimum(?:\s+of)?|min\.?)\s+(\d+)\s*(?:\+)?\s*years?",
    r"(\d+)\s*(?:\+)?\s*(?:-\s*\d+\s*)?שנות\s+ניסיון",
    r"ניסיון\s+של\s+(?:לפחות\s+)?(\d+)\s*(?:\+)?\s*שנים",
]


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


def extract_min_years(description):
    found_years = []
    for pattern in EXPERIENCE_PATTERNS:
        for match in re.findall(pattern, description):
            years = int(match)
            if 1 <= years <= 15:
                found_years.append(years)
    return min(found_years) if found_years else 0


def is_relevant(title, description):
    title_lower = str(title).lower()
    desc_lower = str(description).lower() if description and str(description) != "nan" else ""

    if any(word in title_lower for word in EXCLUDE_TITLE_KEYWORDS):
        return False

    if any(word in title_lower for word in ["student", "intern", "graduate", "סטודנט", "בוגר"]):
        return True

    if desc_lower:
        min_years = extract_min_years(desc_lower)
        if min_years > MAX_YEARS_EXPERIENCE:
            return False

    combined = f"{title_lower} {desc_lower}"
    return any(word in combined for word in ENTRY_LEVEL_KEYWORDS)


def run_agent():
    seen_jobs = load_seen_jobs()
    new_jobs_count = 0

    for term in SEARCH_TERMS:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=LOCATION,
                results_wanted=15,
                hours_old=HOURS_OLD,
                linkedin_fetch_description=True,
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
            description = row.get("description", "")

            if not job_url or job_url in seen_jobs:
                continue

            if not is_relevant(title, description):
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
