import json
import os
import re
import time
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
    "senior", "sr.", "sr ", "principal", "staff", "lead", "manager",
    "director", "architect", "head of", "vp", "chief", "team leader",
    "experienced", "expert", "specialist", " iii", " iv"
]

JUNIOR_TITLE_KEYWORDS = [
    "student", "intern", "internship", "junior", "jr.", "jr ",
    "graduate", "new grad", "entry", "סטודנט", "מתמחה", "בוגר", "ג'וניור"
]

ROLE_KEYWORDS = [
    "vlsi", "chip", "rtl", "verification", "hardware", "silicon",
    "asic", "fpga", "soc", "design", "firmware", "embedded",
    "rf", "dsp", "electrical", "analog", "digital", "board", "dft", "physical"
]

EXPERIENCE_PATTERNS = [
    r"(\d+)\s*(?:\+|plus)?\s*(?:-\s*\d+\s*)?(?:years?|yrs?)\b.{0,35}?\bexperience",
    r"(?:at least|minimum(?:\s+of)?|min\.?|over|more than)\s+(\d+)\s*(?:\+)?\s*(?:years?|yrs?)\b",
    r"experience\s*[:\-]?\s*(?:at least\s+|minimum\s+)?(\d+)\s*(?:\+)?\s*(?:-\s*\d+\s*)?(?:years?|yrs?)\b",
    r"(\d+)\s*\+\s*(?:years?|yrs?)\b",
    r"(\d+)\s*(?:\+)?\s*(?:-\s*\d+\s*)?שנות\s+ניסיון",
    r"(?:ניסיון\s+של|מעל|לפחות)\s+(?:לפחות\s+)?(\d+)\s*(?:\+)?\s*(?:שנים|שנות)",
]

WORKDAY_COMPANIES = [
    {
        "name": "NVIDIA",
        "api_url": "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
        "base_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
    },
    {
        "name": "Intel",
        "api_url": "https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs",
        "base_url": "https://intel.wd1.myworkdayjobs.com/en-US/External",
    },
    {
        "name": "Marvell",
        "api_url": "https://marvell.wd1.myworkdayjobs.com/wday/cxs/marvell/MarvellCareers/jobs",
        "base_url": "https://marvell.wd1.myworkdayjobs.com/en-US/MarvellCareers",
    },
    {
        "name": "Western Digital / SanDisk",
        "api_url": "https://wdc.wd1.myworkdayjobs.com/wday/cxs/wdc/External/jobs",
        "base_url": "https://wdc.wd1.myworkdayjobs.com/en-US/External",
    },
    {
        "name": "Cadence",
        "api_url": "https://cadence.wd1.myworkdayjobs.com/wday/cxs/cadence/External_Careers/jobs",
        "base_url": "https://cadence.wd1.myworkdayjobs.com/en-US/External_Careers",
    },
    {
        "name": "Arm",
        "api_url": "https://arm.wd3.myworkdayjobs.com/wday/cxs/arm/ArmCareers/jobs",
        "base_url": "https://arm.wd3.myworkdayjobs.com/en-US/ArmCareers",
    },
    {
        "name": "Synopsys",
        "api_url": "https://synopsys.wd1.myworkdayjobs.com/wday/cxs/synopsys/External_Careers/jobs",
        "base_url": "https://synopsys.wd1.myworkdayjobs.com/en-US/External_Careers",
    },
]

CUSTOM_SITE_COMPANIES = [
    "Qualcomm",
    "Cisco",
    "RAD",
    "Mobileye",
    "Hailo",
    "NextSilicon",
    "Valens",
    "Sony Semiconductor",
    "Texas Instruments",
    "SolarEdge",
    "Elbit Systems",
    "Rafael",
    "Israel Aerospace Industries",
    "Veriest",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def load_seen_jobs():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_jobs(seen_jobs):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_jobs), f, ensure_ascii=False, indent=2)


def normalize_url(url):
    return str(url).split("?")[0].strip()


def make_job_key(company, title):
    return f"{str(company).strip().lower()}|{str(title).strip().lower()}"


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                time.sleep(0.5)
                return True
            time.sleep(2)
        except Exception as e:
            print(f"Telegram send error (attempt {attempt + 1}): {e}")
            time.sleep(2)
    return False


def extract_min_years(description):
    found_years = []
    for pattern in EXPERIENCE_PATTERNS:
        for match in re.findall(pattern, description):
            years = int(match)
            if 1 <= years <= 15:
                found_years.append(years)
    return min(found_years) if found_years else 0


def is_relevant(title, description=""):
    title_lower = str(title).lower()
    desc_lower = str(description).lower() if description and str(description).lower() != "nan" else ""

    if any(word in title_lower for word in EXCLUDE_TITLE_KEYWORDS):
        return False

    if not any(word in title_lower for word in ROLE_KEYWORDS):
        return False

    if any(word in title_lower for word in JUNIOR_TITLE_KEYWORDS):
        return True

    # אם אין תיאור משרה, לא מאשרים אוטומטית תפקידים כלליים שלא ציינו סטודנט/ג'וניור בכותרת
    if not desc_lower.strip():
        return False

    min_years = extract_min_years(desc_lower)
    if min_years > MAX_YEARS_EXPERIENCE:
        return False

    return True


def fetch_linkedin_jobs():
    results = []
    for term in SEARCH_TERMS:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=LOCATION,
                results_wanted=10,
                hours_old=HOURS_OLD,
                fetch_description=True,
            )
            time.sleep(3)
        except Exception as e:
            print(f"LinkedIn error ({term}): {e}")
            continue

        if jobs.empty:
            continue

        for _, row in jobs.iterrows():
            results.append({
                "title": str(row.get("title", "Unknown Role")),
                "company": str(row.get("company", "Unknown Company")),
                "location": str(row.get("location", "")),
                "url": str(row.get("job_url", "")),
                "description": str(row.get("description", "")),
            })
    return results


def fetch_workday_jobs():
    results = []
    for company in WORKDAY_COMPANIES:
        try:
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": "Israel",
            }
            resp = requests.post(company["api_url"], json=payload, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            postings = resp.json().get("jobPostings", [])
            for job in postings:
                title = job.get("title", "")
                loc = job.get("locationsText", "")
                ext_path = job.get("externalPath", "")
                if not ext_path or "israel" not in loc.lower():
                    continue
                results.append({
                    "title": title,
                    "company": company["name"],
                    "location": loc,
                    "url": f"{company['base_url']}{ext_path}",
                    "description": "",
                })
            time.sleep(2)
        except Exception as e:
            print(f"Workday error ({company['name']}): {e}")
    return results


def fetch_custom_company_jobs():
    results = []
    for company in CUSTOM_SITE_COMPANIES:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin"],
                search_term=company,
                location=LOCATION,
                results_wanted=5,
                hours_old=HOURS_OLD,
                fetch_description=False,
            )
            time.sleep(2.5)
            if jobs.empty:
                continue
            for _, row in jobs.iterrows():
                comp_name = str(row.get("company", ""))
                if company.lower() not in comp_name.lower():
                    continue
                results.append({
                    "title": str(row.get("title", "Unknown Role")),
                    "company": comp_name,
                    "location": str(row.get("location", "")),
                    "url": str(row.get("job_url", "")),
                    "description": "",
                })
        except Exception as e:
            print(f"{company} error: {e}")
    return results


def run_agent():
    seen_jobs = load_seen_jobs()
    new_jobs_count = 0

    try:
        all_jobs = (
            fetch_linkedin_jobs()
            + fetch_workday_jobs()
            + fetch_custom_company_jobs()
        )

        for job in all_jobs:
            clean_url = normalize_url(job["url"])
            job_key = make_job_key(job["company"], job["title"])

            if not clean_url or clean_url in seen_jobs or job_key in seen_jobs:
                continue

            if not is_relevant(job["title"], job["description"]):
                continue

            message = (
                f"<b>{job['title']}</b>\n"
                f"Company: {job['company']}\n"
                f"Location: {job['location']}\n"
                f"<a href='{clean_url}'>Apply / View Job</a>"
            )
            if send_telegram_message(message):
                seen_jobs.add(clean_url)
                seen_jobs.add(job_key)
                new_jobs_count += 1
    finally:
        save_seen_jobs(seen_jobs)
        print(f"Done. Sent {new_jobs_count} new jobs.")


if __name__ == "__main__":
    run_agent()
