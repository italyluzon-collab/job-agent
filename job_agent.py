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
    "senior", "sr.", "principal", "staff", "lead", "manager",
    "director", "architect", "head of", "vp", "chief", "team leader"
]

ROLE_KEYWORDS = [
    "vlsi", "chip", "rtl", "verification", "hardware", "silicon",
    "asic", "fpga", "soc", "design", "firmware", "embedded",
    "rf", "dsp", "electrical", "analog", "digital", "board", "system"
]

EXPERIENCE_PATTERNS = [
    r"(\d+)\s*(?:\+|plus)?\s*(?:-\s*\d+\s*)?years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience",
    r"(?:at least|minimum(?:\s+of)?|min\.?)\s+(\d+)\s*(?:\+)?\s*years?",
    r"(\d+)\s*(?:\+)?\s*(?:-\s*\d+\s*)?שנות\s+ניסיון",
    r"ניסיון\s+של\s+(?:לפחות\s+)?(\d+)\s*(?:\+)?\s*שנים",
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

COMEET_COMPANIES = [
    # דוגמה להוספת חברה מ-Comeet (Hailo, NextSilicon, Valens, Veriest):
    # {"name": "Hailo", "uid": "COMPANY_UID", "token": "PUBLIC_TOKEN"},
]

CUSTOM_SITE_COMPANIES = [
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
}


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


def is_relevant(title, description="", check_role=False):
    title_lower = str(title).lower()
    desc_lower = str(description).lower() if description and str(description) != "nan" else ""

    if any(word in title_lower for word in EXCLUDE_TITLE_KEYWORDS):
        return False

    if check_role and not any(word in title_lower for word in ROLE_KEYWORDS):
        return False

    if any(word in title_lower for word in ["student", "intern", "graduate", "סטודנט", "בוגר"]):
        return True

    if desc_lower:
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
                results_wanted=15,
                hours_old=HOURS_OLD,
                linkedin_fetch_description=True,
            )
            time.sleep(1)
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
                "check_role": False,
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
                    "check_role": True,
                })
        except Exception as e:
            print(f"Workday error ({company['name']}): {e}")
    return results


def fetch_comeet_jobs():
    results = []
    for company in COMEET_COMPANIES:
        try:
            url = f"https://www.comeet.co/careers-api/2.0/company/{company['uid']}/positions"
            params = {"token": company["token"], "details": "false"}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            for job in resp.json():
                loc = (job.get("location") or {}).get("name", "Israel")
                results.append({
                    "title": job.get("name", ""),
                    "company": company["name"],
                    "location": loc,
                    "url": job.get("position_url", ""),
                    "description": "",
                    "check_role": True,
                })
        except Exception as e:
            print(f"Comeet error ({company['name']}): {e}")
    return results


def fetch_qualcomm_jobs():
    results = []
    try:
        url = "https://careers.qualcomm.com/api/apply/v2/jobs"
        params = {"domain": "qualcomm.com", "location": "Israel", "start": 0, "num": 20}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        positions = resp.json().get("positions", [])
        for job in positions:
            results.append({
                "title": job.get("name", ""),
                "company": "Qualcomm",
                "location": job.get("location", "Israel"),
                "url": job.get("canonicalPositionUrl", ""),
                "description": "",
                "check_role": True,
            })
    except Exception as e:
        print(f"Qualcomm error: {e}")
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
                linkedin_fetch_description=True,
            )
            time.sleep(1.5)
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
                    "description": str(row.get("description", "")),
                    "check_role": True,
                })
        except Exception as e:
            print(f"{company} error: {e}")
    return results


def run_agent():
    seen_jobs = load_seen_jobs()
    new_jobs_count = 0

    all_jobs = (
        fetch_linkedin_jobs()
        + fetch_workday_jobs()
        + fetch_comeet_jobs()
        + fetch_qualcomm_jobs()
        + fetch_custom_company_jobs()
    )

    for job in all_jobs:
        job_url = job["url"]
        if not job_url or job_url in seen_jobs:
            continue

        if not is_relevant(job["title"], job["description"], check_role=job["check_role"]):
            continue

        message = (
            f"<b>{job['title']}</b>\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"<a href='{job_url}'>Apply / View Job</a>"
        )
        send_telegram_message(message)
        seen_jobs.add(job_url)
        new_jobs_count += 1

    save_seen_jobs(seen_jobs)
    print(f"Done. Sent {new_jobs_count} new jobs.")


if __name__ == "__main__":
    run_agent()
