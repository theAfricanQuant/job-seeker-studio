#!/usr/bin/env python3
"""Field Notes: a local-only CV-to-Typst job-application workspace."""

from __future__ import annotations

import base64
import hashlib
from html import escape as xml_escape
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlencode, unquote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

APP_ROOT = Path(__file__).resolve().parent
DATA_ROOT = APP_ROOT / "local_data"
WORKSPACES_ROOT = DATA_ROOT / "workspaces"
UPLOADS = DATA_ROOT / "uploads"  # Legacy local-pilot path; never used by authenticated workspaces.
DOCUMENTS = DATA_ROOT / "documents"  # Retained for isolated document-generation tests.
CV_STUDIO_RUNTIME = APP_ROOT / "cv_studio_runtime"
PROFILE_FILE = DATA_ROOT / "profile.json"
JOB_CACHE_FILE = DATA_ROOT / "job_matches.json"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
JOBICY_ENDPOINT = "https://jobicy.com/api/v2/remote-jobs"
FREEHIRE_ENDPOINT = "https://freehire.me/api/v1/jobs/search"
WORKSPACE_TTL_SECONDS = 30 * 24 * 60 * 60
WORKSPACE_COOKIE = "field_notes_workspace"
CV_TEMPLATES = {"ats-plain", "crest", "emblem", "grid", "horizon", "index", "letterhead", "meridian", "quietude", "ridgeline", "soft-and-hard", "spine", "vertex"}
PUBLIC_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}

JOBS = [
    {
        "id": "nordbeam-quant",
        "title": "Senior Quantitative Analyst",
        "company": "Nordbeam Capital",
        "location": "Frankfurt · Hybrid",
        "posted": "3 days ago",
        "keywords": ["python", "financial engineering", "risk models", "time series", "quant", "research"],
        "summary": "Build and explain quantitative risk models used by portfolio and trading teams.",
    },
    {
        "id": "mosaic-ml",
        "title": "Applied ML Scientist",
        "company": "Mosaic Risk",
        "location": "Remote · EU",
        "posted": "5 days ago",
        "keywords": ["python", "machine learning", "nlp", "time series", "research", "data science"],
        "summary": "Develop applied machine-learning models for financial decision support.",
    },
    {
        "id": "helio-risk",
        "title": "Market Risk Data Scientist",
        "company": "Helio Bank",
        "location": "Berlin · On-site",
        "posted": "1 week ago",
        "keywords": ["python", "risk models", "data science", "statistics", "german", "financial engineering"],
        "summary": "Turn market-risk data into practical analysis and reporting for senior stakeholders.",
    },
]

KNOWN_SKILLS = {
    "python": "Python",
    "machine learning": "Machine learning",
    "ml": "Machine learning",
    "nlp": "NLP",
    "time series": "Time series",
    "quant": "Quantitative research",
    "financial engineering": "Financial engineering",
    "risk model": "Risk modelling",
    "data science": "Data science",
    "statistics": "Statistics",
    "sql": "SQL",
    "pandas": "Pandas",
    "german": "German",
}


def ensure_data_directories() -> None:
    for folder in (DATA_ROOT, WORKSPACES_ROOT, UPLOADS, DOCUMENTS):
        folder.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or "cv.txt"


def workspace_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def workspace_root(token: str) -> Path:
    return WORKSPACES_ROOT / workspace_key(token)


def workspace_profile_file(token: str) -> Path:
    return workspace_root(token) / "profile.json"


def workspace_uploads(token: str) -> Path:
    return workspace_root(token) / "uploads"


def workspace_documents(token: str) -> Path:
    return workspace_root(token) / "documents"


def workspace_job_cache_file(token: str) -> Path:
    return workspace_root(token) / "job_matches.json"


def ensure_workspace(token: str) -> Path:
    root = workspace_root(token)
    for folder in (root, workspace_uploads(token), workspace_documents(token)):
        folder.mkdir(parents=True, exist_ok=True)
    return root


def read_profile(token: str) -> dict:
    profile_file = workspace_profile_file(token)
    if profile_file.exists():
        return json.loads(profile_file.read_text(encoding="utf-8"))
    return empty_profile()


def empty_profile() -> dict:
    return {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "headline": "",
        "skills": [],
        "experiences": [],
        "education": [],
        "projects": [],
        "languages": [],
        "source_excerpt": "",
        "cv_template": "ats-plain",
        "uploaded_file": "",
        "updated_at": "",
    }


def write_profile(profile: dict, workspace_token: str) -> dict:
    ensure_workspace(workspace_token)
    clean = {
        "name": str(profile.get("name", "")).strip()[:100],
        "email": str(profile.get("email", "")).strip()[:160],
        "phone": str(profile.get("phone", "")).strip()[:80],
        "location": str(profile.get("location", "")).strip()[:100],
        "headline": str(profile.get("headline", "")).strip()[:220],
        "skills": normalize_skills(profile.get("skills", [])),
        "experiences": normalize_records(profile.get("experiences", profile.get("experience_text", "")), 8),
        "education": normalize_records(profile.get("education", profile.get("education_text", "")), 6),
        "projects": normalize_records(profile.get("projects", profile.get("project_text", "")), 6),
        "languages": normalize_skills(profile.get("languages", [])),
        "source_excerpt": str(profile.get("source_excerpt", "")).strip()[:12000],
        "cv_template": str(profile.get("cv_template", "ats-plain")).strip().lower() if str(profile.get("cv_template", "ats-plain")).strip().lower() in CV_TEMPLATES else "ats-plain",
        "uploaded_file": str(profile.get("uploaded_file", "")).strip()[:180],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    workspace_profile_file(workspace_token).write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean


def normalize_skills(value: object) -> list[str]:
    raw = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
    found: list[str] = []
    for item in raw:
        skill = str(item).strip()
        if skill and skill.lower() not in {s.lower() for s in found}:
            found.append(skill[:70])
    return found[:24]


def normalize_records(value: object, limit: int) -> list[dict]:
    """Keep only candidate-reviewed CV records; never infer jobs, dates, or achievements."""
    if isinstance(value, str):
        blocks = [block.strip() for block in re.split(r"\n\s*\n", value.strip()) if block.strip()]
        records: list[object] = []
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            fields = [field.strip() for field in lines[0].split("|")]
            records.append({
                "title": fields[0] if fields else "",
                "subtitle": fields[1] if len(fields) > 1 else "",
                "dates": fields[2] if len(fields) > 2 else "",
                "location": fields[3] if len(fields) > 3 else "",
                "bullets": [line.removeprefix("-").strip() for line in lines[1:] if line.removeprefix("-").strip()],
            })
    else:
        records = value if isinstance(value, list) else []
    clean: list[dict] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:160]
        subtitle = str(item.get("subtitle", item.get("company", ""))).strip()[:160]
        dates = str(item.get("dates", "")).strip()[:80]
        location = str(item.get("location", "")).strip()[:100]
        raw_bullets = item.get("bullets", item.get("lines", []))
        bullets = [str(bullet).strip()[:500] for bullet in (raw_bullets if isinstance(raw_bullets, list) else []) if str(bullet).strip()][:8]
        if title or subtitle or bullets:
            clean.append({"title": title, "subtitle": subtitle, "dates": dates, "location": location, "bullets": bullets})
    return clean[:limit]


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()
    if extension == ".pdf":
        command = ["pdftotext", "-layout", str(path), "-"]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
            return result.stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("This PDF could not be read. Try a text-based PDF or a .docx/.txt CV.") from error
    if extension == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            paragraphs = []
            for paragraph in root.iter():
                if paragraph.tag.endswith("}p"):
                    text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
                    if text.strip():
                        paragraphs.append(text.strip())
            return "\n".join(paragraphs)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError("This .docx file could not be read.") from error
    if extension in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Use a PDF, DOCX, TXT, or Markdown CV.")


def cv_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip() and not re.match(r"^(Page \| \d+|.+@.+)$", line.strip())]


def parsed_name(lines: list[str]) -> str:
    for line in lines[:30]:
        candidate = re.sub(r"^.*?\bName\s+", "", line, flags=re.I).strip()
        if candidate != line and re.fullmatch(r"[A-Za-zÀ-ÿ .'-]{4,70}", candidate):
            return candidate
    for index, line in enumerate(lines[:15]):
        if line.lower() in {"curriculum", "vitae", "curriculum vitae"} and index + 1 < len(lines):
            candidate = lines[index + 1]
            if re.fullmatch(r"[A-Za-zÀ-ÿ .'-]{4,70}", candidate):
                return candidate
    return ""


def parsed_location(lines: list[str]) -> str:
    for line in lines[:35]:
        labelled = re.match(r"^(?:address|location|based in|residence)\s*[:|-]\s*(.+)$", line, re.I)
        if labelled and len(labelled.group(1).strip()) <= 120:
            return labelled.group(1).strip()
    country_words = ("nigeria", "germany", "france", "kenya", "ghana", "south africa", "canada", "united kingdom", "usa", "united states", "europe")
    return next((line for line in lines[:25] if any(country in line.lower() for country in country_words) and "@" not in line and len(line) <= 120), "")


def clean_cv_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("│", "|").replace("", "").replace("•", "").strip(" -|•")).strip()


def parse_work_experience(lines: list[str]) -> list[dict]:
    start = next((index for index, line in enumerate(lines) if "work experience" in line.lower()), None)
    if start is None:
        return []
    end = next((index for index, line in enumerate(lines[start + 1:], start + 1) if any(marker in line.lower() for marker in ("acad. background", "academic background", "education", "regional/international experience"))), len(lines))
    chunk = lines[start + 1:end]
    date_pattern = re.compile(r"(?:(?:0?[1-9]|1[0-2])[/.-]\d{4}|\d{4})\s*[–-]\s*(?:(?:0?[1-9]|1[0-2])[/.-]\d{4}|\d{4}|till date|present)", re.I)
    boundaries = [index for index, line in enumerate(chunk) if date_pattern.search(line)]
    records: list[dict] = []

    def collect_bullets(segment: list[str]) -> list[str]:
        bullets: list[str] = []
        current = ""
        for line in segment:
            clean = clean_cv_line(line)
            if not clean or re.match(r"^Ene Sandra Macharm", clean, re.I):
                continue
            marker = re.match(r"^(?:•|o)\s*(.+)$", line.strip(), re.I)
            if marker:
                if current:
                    bullets.append(current)
                current = clean_cv_line(marker.group(1))
            elif current:
                current = clean_cv_line(current + " " + clean)
        if current:
            bullets.append(current)
        return bullets[:7]

    # Some two-column PDFs put the first role on the same line as the section heading.
    lead = re.sub(r"^.*?work experience\s+", "", lines[start], flags=re.I).replace("│", "|")
    if "|" in lead and boundaries:
        lead_title, _, lead_org = (clean_cv_line(part) for part in lead.partition("|"))
        if start + 1 < len(lines) and not date_pattern.search(lines[start + 1]):
            lead_org = clean_cv_line(" ".join(filter(None, [lead_org, lines[start + 1]])))
        first_date = date_pattern.search(chunk[boundaries[0]])
        first_end = boundaries[1] if len(boundaries) > 1 else len(chunk)
        if first_date and lead_title:
            records.append({"title": lead_title[:160], "subtitle": lead_org[:160], "dates": first_date.group(0)[:80], "location": "", "bullets": collect_bullets(chunk[boundaries[0] + 1:first_end])})
    for position, begin in enumerate(boundaries):
        finish = boundaries[position + 1] if position + 1 < len(boundaries) else len(chunk)
        segment = chunk[begin:finish]
        date_match = date_pattern.search(segment[0])
        if not date_match:
            continue
        header_positions = [index for index, line in enumerate(segment) if "|" in line or "│" in line]
        if not header_positions:
            continue
        header_index = header_positions[-1]
        header = segment[header_index].replace("│", "|")
        title, _, organisation = (clean_cv_line(part) for part in header.partition("|"))
        title = clean_cv_line(date_pattern.sub("", title))
        if header_index and (not title or title[:1].islower()):
            previous = clean_cv_line(date_pattern.sub("", segment[header_index - 1]))
            if previous and not re.match(r"^(?:•|o)", previous, re.I):
                title = clean_cv_line(previous + " " + title)
        following = segment[header_index + 1:]
        if following and not re.match(r"^(?:•|o\s)", following[0].strip(), re.I) and not date_pattern.search(following[0]):
            organisation = clean_cv_line(" ".join(filter(None, [organisation, following.pop(0)])))
        bullets = collect_bullets(following)
        if title and (organisation or bullets):
            records.append({"title": title[:160], "subtitle": organisation[:160], "dates": date_match.group(0)[:80], "location": "", "bullets": bullets[:7]})
    return records[:8]


def parse_education(lines: list[str]) -> list[dict]:
    start = next((index for index, line in enumerate(lines) if any(marker in line.lower() for marker in ("acad. background", "academic background", "education"))), None)
    if start is None:
        return []
    end = next((index for index, line in enumerate(lines[start + 1:], start + 1) if "languages" in line.lower()), len(lines))
    section = lines[start + 1:end]
    records: list[dict] = []
    year_pattern = re.compile(r"\b(?:19|20)\d{2}\b")
    degree_pattern = re.compile(r"\b(?:MBA|M\.Sc|MSc|B\.Sc|BSc|Bachelor|Master|Certificate|Diploma)\b", re.I)
    for index, line in enumerate(section):
        if not degree_pattern.search(line):
            continue
        detail = line.replace("│", "|")
        year = year_pattern.search(detail) or (year_pattern.search(section[index + 1]) if index + 1 < len(section) else None)
        detail = clean_cv_line(year_pattern.sub("", detail))
        title, _, school = (clean_cv_line(part) for part in detail.partition("|"))
        if title:
            records.append({"title": title[:160], "subtitle": school[:160], "dates": year.group(0) if year else "", "location": "", "bullets": []})
    return records[:5]


def parse_languages(lines: list[str]) -> list[str]:
    start = next((index for index, line in enumerate(lines) if line.lower() == "languages" or line.lower().startswith("languages ")), None)
    if start is None:
        return []
    end = next((index for index, line in enumerate(lines[start + 1:], start + 1) if "other rele" in line.lower() or "key qualifications" in line.lower()), len(lines))
    first = re.sub(r"^languages\s+", "", lines[start], flags=re.I)
    return normalize_skills([clean_cv_line(line) for line in [first, *lines[start + 1:end]] if ":" in line])


def profile_from_text(text: str, uploaded_file: str, workspace_token: str) -> dict:
    lines = cv_lines(text)
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", text)
    candidate_name = parsed_name(lines)
    lower = text.lower()
    skills = []
    for key, label in KNOWN_SKILLS.items():
        if re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", lower) and label not in skills:
            skills.append(label)
    experiences = parse_work_experience(lines)
    headline = experiences[0]["title"] if experiences else next((line for line in lines if len(line) < 150 and any(word in line.lower() for word in ["analyst", "scientist", "engineer", "research", "manager", "coordinator", "advisor"])), "")
    key_start = next((index for index, line in enumerate(lines) if "key qualifications" in line.lower()), None)
    if key_start is not None:
        skills.extend(clean_cv_line(line) for line in lines[key_start + 1:key_start + 10] if clean_cv_line(line))
    location = parsed_location(lines)
    return write_profile({
        "name": candidate_name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "headline": headline,
        "location": location,
        "skills": skills,
        "experiences": experiences,
        "education": parse_education(lines),
        "languages": parse_languages(lines),
        "source_excerpt": "\n".join(lines[:180]),
        "uploaded_file": uploaded_file,
    }, workspace_token)


def job_matches(profile: dict) -> list[dict]:
    searchable = " ".join(profile.get("skills", []) + [profile.get("headline", ""), profile.get("source_excerpt", "")]).lower()
    results = []
    for job in JOBS:
        hits = [keyword for keyword in job["keywords"] if keyword in searchable]
        score = min(97, 48 + len(hits) * 8)
        results.append({**job, "score": score, "matches": hits})
    return sorted(results, key=lambda item: item["score"], reverse=True)


def candidate_search_term(profile: dict) -> str:
    """Derive a narrow, user-approved search term; never send the raw CV."""
    headline_words = re.findall(r"[A-Za-z]{3,}", profile.get("headline", ""))
    if headline_words:
        return " ".join(headline_words[:4])
    skills = profile.get("skills", [])
    return str(skills[0]) if skills else "remote"


def score_listings(profile: dict, listings: list[dict]) -> list[dict]:
    searchable = " ".join(profile.get("skills", []) + [profile.get("headline", ""), profile.get("source_excerpt", "")]).lower()
    scored = []
    for listing in listings:
        haystack = " ".join([listing.get("title", ""), listing.get("summary", "")] + listing.get("keywords", [])).lower()
        skill_hits = [skill for skill in profile.get("skills", []) if skill.lower() in haystack]
        title_hits = [word for word in re.findall(r"[a-z]{4,}", listing.get("title", "").lower()) if word in searchable]
        scored.append({**listing, "score": min(97, 35 + len(skill_hits) * 13 + len(title_hits) * 5), "matches": skill_hits + title_hits})
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def normalize_jobicy_listing(raw: dict) -> dict:
    job_id = str(raw.get("id") or raw.get("jobSlug") or "")
    if not job_id:
        raise ValueError("A remote listing did not include an identifier.")
    description = re.sub(r"<[^>]+>", " ", str(raw.get("jobDescription") or ""))
    return {
        "id": "jobicy-" + job_id,
        "title": str(raw.get("jobTitle") or "Untitled role").strip(),
        "company": str(raw.get("companyName") or "Company not supplied").strip(),
        "location": str(raw.get("jobGeo") or "Remote").strip(),
        "posted": str(raw.get("pubDate") or "Recently listed").strip(),
        "keywords": [str(value) for value in raw.get("jobIndustry", []) + raw.get("jobType", [])],
        "summary": re.sub(r"\s+", " ", description).strip()[:900] or "Open the original listing for the full description.",
        "apply_url": str(raw.get("url") or "").strip(),
        "source": "Jobicy",
    }


def fetch_jobicy_jobs(profile: dict) -> list[dict]:
    def request_listings(parameters: dict[str, object]) -> list[dict]:
        request = Request(JOBICY_ENDPOINT + "?" + urlencode(parameters), headers={"Accept": "application/json", "User-Agent": "FieldNotesCareerStudioLocalPilot/0.1"})
        with urlopen(request, timeout=12) as response:  # nosec B310 - fixed HTTPS endpoint
            payload = json.loads(response.read().decode("utf-8"))
        return [normalize_jobicy_listing(item) for item in payload.get("jobs", [])]

    listings = request_listings({"count": 30, "geo": "anywhere", "tag": candidate_search_term(profile)[:50]})
    if not listings:
        listings = request_listings({"count": 30, "geo": "anywhere"})
    return listings


def normalize_freehire_listing(raw: dict) -> dict:
    job_id = str(raw.get("public_slug") or "")
    if not job_id:
        raise ValueError("A FreeHire listing did not include a public identifier.")
    description = re.sub(r"<[^>]+>", " ", str(raw.get("description") or ""))
    enrichment = raw.get("enrichment") if isinstance(raw.get("enrichment"), dict) else {}
    keywords = [str(value) for value in raw.get("skills", [])]
    if enrichment.get("category"):
        keywords.append(str(enrichment["category"]))
    if raw.get("work_mode"):
        keywords.append(str(raw["work_mode"]))
    return {
        "id": "freehire-" + job_id,
        "title": str(raw.get("title") or "Untitled role").strip(),
        "company": str(raw.get("company") or "Company not supplied").strip(),
        "location": str(raw.get("location") or raw.get("work_mode") or "Location not supplied").strip(),
        "posted": str(raw.get("posted_at") or "Recently listed").strip(),
        "keywords": keywords,
        "summary": re.sub(r"\s+", " ", description).strip()[:900] or "Open the original listing for the full description.",
        "apply_url": str(raw.get("url") or "").strip(),
        "source": "FreeHire",
    }


def fetch_freehire_jobs(profile: dict) -> list[dict]:
    parameters = {"q": candidate_search_term(profile)[:50], "limit": 30}
    request = Request(FREEHIRE_ENDPOINT + "?" + urlencode(parameters), headers={"Accept": "application/json", "User-Agent": "FieldNotesCareerStudioLocalPilot/0.1"})
    with urlopen(request, timeout=12) as response:  # nosec B310 - fixed HTTPS endpoint
        payload = json.loads(response.read().decode("utf-8"))
    return [normalize_freehire_listing(item) for item in payload.get("data", [])]


def fetch_remote_jobs(profile: dict) -> tuple[list[dict], list[str]]:
    listings: list[dict] = []
    sources: list[str] = []
    for source, fetcher in (("Jobicy", fetch_jobicy_jobs), ("FreeHire", fetch_freehire_jobs)):
        try:
            provider_listings = fetcher(profile)
        except Exception:
            continue
        if provider_listings:
            listings.extend(provider_listings)
            sources.append(source)
    if not listings:
        raise ValueError("No configured job provider was available.")
    unique: dict[str, dict] = {}
    for listing in listings:
        identity = listing.get("apply_url") or "|".join((listing["title"], listing["company"], listing["location"])).lower()
        unique.setdefault(identity, listing)
    return score_listings(profile, list(unique.values()))[:40], sources


def production_mode() -> bool:
    return os.getenv("FIELD_NOTES_ENV", "development").strip().lower() == "production"


def browser_workspace_token(cookie_header: str) -> str | None:
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except (CookieError, ValueError):
        return None
    morsel = cookie.get(WORKSPACE_COOKIE)
    if not morsel or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", morsel.value):
        return None
    return morsel.value


def new_workspace_token() -> str:
    return secrets.token_urlsafe(32)


def workspace_cookie(token: str) -> str:
    secure = "; Secure" if production_mode() else ""
    return f"{WORKSPACE_COOKIE}={token}; Max-Age={WORKSPACE_TTL_SECONDS}; Path=/; HttpOnly; SameSite=Lax{secure}"


def current_jobs(profile: dict, owner_email: str) -> tuple[list[dict], str]:
    if not (profile.get("headline") or profile.get("skills") or profile.get("source_excerpt")):
        return [], "Save a candidate profile to search remote jobs."
    try:
        jobs, providers = fetch_remote_jobs(profile)
    except Exception:
        jobs = job_matches(profile)
        source = "Local demo roles — live remote search was unavailable"
    else:
        source = "Live roles from " + " + ".join(providers)
    ensure_workspace(owner_email)
    workspace_job_cache_file(owner_email).write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    return jobs, source


def job_by_id(job_id: str, owner_email: str | None = None) -> dict | None:
    job_cache = workspace_job_cache_file(owner_email) if owner_email else JOB_CACHE_FILE
    if job_cache.exists():
        cached = json.loads(job_cache.read_text(encoding="utf-8"))
        match = next((item for item in cached if item.get("id") == job_id), None)
        if match:
            return match
    return next((item for item in JOBS if item["id"] == job_id), None)


def typst_escape(value: str) -> str:
    replacements = {"\\": "\\\\", "#": "\\#", "@": "\\@", "[": "\\[", "]": "\\]", "{": "\\{", "}": "\\}", "*": "\\*", "_": "\\_"}
    return "".join(replacements.get(character, character) for character in value)


def typst_string(value: object) -> str:
    """A Typst string literal for candidate-entered plain text."""
    clean = str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{clean}"'


def typst_content(value: object) -> str:
    return "[" + typst_escape(str(value or "")) + "]"


def role_terms(job: dict) -> list[str]:
    text = " ".join([job.get("title", ""), job.get("summary", ""), *job.get("keywords", [])]).lower()
    ignored = {"with", "that", "this", "from", "into", "your", "role", "work", "team", "remote", "data", "the", "and", "for", "are", "job"}
    terms = [term for term in re.findall(r"[a-z][a-z+#.-]{2,}", text) if term not in ignored]
    return list(dict.fromkeys(terms))[:24]


def relevance_score(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lowered))


def fallback_experience(profile: dict) -> list[dict]:
    evidence = [line.strip(" -•\t") for line in profile.get("source_excerpt", "").splitlines() if len(line.strip()) >= 20]
    if not evidence:
        return []
    return [{"title": "Approved career evidence", "subtitle": "Review and structure before sending", "dates": "", "location": "", "bullets": evidence[:8]}]


def tailored_evidence(profile: dict, job: dict) -> tuple[dict, dict]:
    """Reorder reviewed facts by job vocabulary; do not rewrite or invent any facts."""
    terms = role_terms(job)
    experiences = profile.get("experiences", []) or fallback_experience(profile)
    ordered_experiences = []
    matched_evidence: list[str] = []
    for experience in experiences:
        copied = {**experience, "bullets": list(experience.get("bullets", []))}
        copied["bullets"].sort(key=lambda bullet: relevance_score(bullet, terms), reverse=True)
        score = relevance_score(" ".join([copied.get("title", ""), copied.get("subtitle", ""), *copied["bullets"]]), terms)
        copied["_relevance"] = score
        if score:
            matched_evidence.append(copied.get("title") or copied.get("subtitle") or "Approved evidence")
        ordered_experiences.append(copied)
    ordered_experiences.sort(key=lambda experience: experience.pop("_relevance"), reverse=True)
    skills = list(profile.get("skills", []))
    skills.sort(key=lambda skill: relevance_score(skill, terms), reverse=True)
    candidate_text = " ".join([*skills, *[" ".join(item.get("bullets", [])) for item in ordered_experiences]]).lower()
    gaps = [term for term in terms[:12] if term not in candidate_text][:5]
    return {
        **profile,
        "skills": skills,
        "experiences": ordered_experiences,
    }, {
        "matched_terms": [term for term in terms if term in candidate_text][:10],
        "foregrounded_evidence": list(dict.fromkeys(matched_evidence))[:5],
        "unverified_terms": gaps,
        "mode": "Local evidence ordering only — no achievements or qualifications were rewritten or invented.",
    }


def cv_content_typst(profile: dict, job: dict) -> tuple[str, dict]:
    tailored, tailoring = tailored_evidence(profile, job)
    contact_parts = [value for value in [tailored.get("email"), tailored.get("phone")] if value]
    contact = " | ".join(contact_parts) or "Contact details to be confirmed"
    skills = tailored.get("skills", [])
    sections: list[str] = []
    skill_bullets = ", ".join(skills) if skills else "Add verified skills before using this CV."
    sections.append("""    (
      title: "Core Competencies",
      entries: ((title: "Verified skills", subtitle: "", bullets: (%s,)),),
    )""" % typst_string(skill_bullets))

    def render_entries(records: list[dict]) -> str:
        entries = []
        for record in records:
            bullets = ",\n            ".join(typst_string(bullet) for bullet in record.get("bullets", []))
            bullet_value = f"({bullets},)" if bullets else "()"
            entries.append("""        (
          title: %s,
          subtitle: %s,
          dates: %s,
          location: %s,
          bullets: %s,
        )""" % (typst_string(record.get("title")), typst_string(record.get("subtitle")), typst_string(record.get("dates")), typst_string(record.get("location")), bullet_value))
        return ",\n".join(entries) + ","

    if tailored.get("experiences"):
        sections.append("    (\n      title: \"Professional Experience\",\n      entries: (\n%s\n      ),\n    )" % render_entries(tailored["experiences"]))
    if tailored.get("projects"):
        sections.append("    (\n      title: \"Projects\",\n      entries: (\n%s\n      ),\n    )" % render_entries(tailored["projects"]))
    if tailored.get("education"):
        sections.append("    (\n      title: \"Education\",\n      entries: (\n%s\n      ),\n    )" % render_entries(tailored["education"]))
    if tailored.get("languages"):
        sections.append("""    (
      title: "Languages",
      entries: ((title: "", subtitle: "", lines: (%s,)),),
    )""" % typst_string(" · ".join(tailored["languages"])))
    headline = tailored.get("headline") or "Professional profile"
    summary = f"{headline}. This application version orders only approved evidence against the selected {job.get('title', 'role')} listing."
    contact_items = [item for item in [*contact_parts, tailored.get("location")] if item] or ["Contact details to be confirmed"]
    return f'''// Generated locally by Field Notes Career Studio.
// Facts are candidate-approved. Tailoring only changes ordering; it does not invent claims.
#let cv = (
  author: {typst_string(tailored.get("name") or "Candidate")},
  profession: {typst_string(headline)},
  location: {typst_string(tailored.get("location") or "Location not supplied")},
  email: {typst_string(tailored.get("email"))},
  phone: {typst_string(tailored.get("phone"))},
  social: (),
  contact: {typst_content(contact)},
  contact-items: ({", ".join(typst_content(item) for item in contact_items)},),
  doc-title: "Curriculum Vitae",
  tagline: none,
  meta: none,
  sections: (
    (
      title: "Profile",
      prose: {typst_content(summary)},
    ),
{",\n".join(sections)}
  ),
)
''', tailoring


def cover_typst(profile: dict, job: dict) -> str:
    name = typst_escape(profile.get("name") or "Candidate")
    contact = " · ".join(filter(None, [profile.get("email"), profile.get("phone")])) or "Contact details to be confirmed"
    skills = ", ".join(profile.get("skills", [])[:5]) or "the verified skills in my profile"
    return f'''#set page(paper: "a4", margin: (x: 22mm, y: 20mm))
#set text(font: "DejaVu Sans", size: 10.5pt)
#set par(leading: 0.85em)

#text(size: 18pt, weight: "bold")[{name}]
{typst_escape(contact)}

#v(18pt)
{typst_escape(job['company'])}
{typst_escape(job['location'])}

#v(18pt)
Dear hiring team,

I am applying for the *{typst_escape(job['title'])}* role at *{typst_escape(job['company'])}*. My approved profile highlights experience and capabilities in {typst_escape(skills)}. I am particularly interested in the opportunity to contribute to work that involves {typst_escape(job['summary'].lower())}

This letter is intentionally a truthful starting draft. Before sending it, I will review the wording, add only specific evidence I can substantiate, and make sure it reflects my own voice.

Thank you for considering my application.

Sincerely,

{name}
'''


def compile_typst(source: Path, output: Path) -> tuple[bool, str]:
    if not shutil.which("typst"):
        return False, "Typst is not installed. Download the .typ source and compile it locally."
    try:
        result = subprocess.run(["typst", "compile", str(source), str(output)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    if result.returncode != 0:
        return False, result.stderr.strip() or "Typst could not compile this document."
    return True, ""


def compile_cv_studio(studio: Path, template: str) -> tuple[Path | None, str]:
    if template not in CV_TEMPLATES:
        return None, "Choose a supported CV Studio template."
    if not shutil.which("typst"):
        return None, "Typst is not installed."
    adapter = studio / "adapters" / f"{template}.typ"
    output = studio / "out" / f"{template}.pdf"
    output.parent.mkdir(exist_ok=True)
    try:
        result = subprocess.run(
            ["typst", "compile", "--root", str(studio), str(adapter), str(output)],
            capture_output=True, text=True, timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if result.returncode != 0:
        return None, result.stderr.strip() or f"Typst could not compile {template}."
    return output, ""


def word_run(text: object, *, bold: bool = False, italic: bool = False) -> str:
    """Small, dependency-free OOXML writer for editable, content-first Word files."""
    properties = "<w:rPr>" + ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "") + "</w:rPr>"
    pieces = str(text or "").split("\n")
    return properties + "".join(f'<w:t xml:space="preserve">{xml_escape(piece)}</w:t>' + ("<w:br/>" if index < len(pieces) - 1 else "") for index, piece in enumerate(pieces))


def word_paragraph(text: object = "", *, style: str = "", bold: bool = False, italic: bool = False, centered: bool = False) -> str:
    properties = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:jc w:val=\"center\"/>" if centered else "")
    return f"<w:p><w:pPr>{properties}</w:pPr><w:r>{word_run(text, bold=bold, italic=italic)}</w:r></w:p>"


def word_bullet(text: object) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r>{word_run("• " + str(text or ""))}</w:r></w:p>'


def write_docx(path: Path, paragraphs: list[str], title: str) -> None:
    """Write an editable DOCX without adding a runtime dependency to the local app."""
    created = datetime.now(timezone.utc).isoformat()
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s
<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/></w:sectPr></w:body></w:document>""" % "".join(paragraphs)
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
 <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:color w:val="000000"/><w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>
 <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="110" w:line="276" w:lineRule="auto"/></w:pPr></w:style>
 <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="80"/><w:jc w:val="center"/></w:pPr><w:rPr><w:color w:val="000000"/><w:b/><w:sz w:val="34"/></w:rPr></w:style>
 <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="190"/><w:jc w:val="center"/></w:pPr><w:rPr><w:color w:val="000000"/><w:sz w:val="23"/></w:rPr></w:style>
 <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="230" w:after="80"/><w:keepNext/></w:pPr><w:rPr><w:color w:val="000000"/><w:b/><w:sz w:val="25"/></w:rPr></w:style>
 <w:style w:type="paragraph" w:styleId="Role"><w:name w:val="Role"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="120" w:after="20"/><w:keepNext/></w:pPr><w:rPr><w:color w:val="000000"/><w:b/></w:rPr></w:style>
 <w:style w:type="paragraph" w:styleId="Meta"><w:name w:val="Meta"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="35"/></w:pPr><w:rPr><w:color w:val="404040"/><w:i/><w:sz w:val="19"/></w:rPr></w:style>
 <w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="35"/></w:pPr></w:style>
</w:styles>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>"""
    document_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>"""
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{xml_escape(title)}</dc:title><dc:creator>Field Notes Career Studio</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created></cp:coreProperties>'''
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Field Notes Career Studio</Application></Properties>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", document_relationships)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)


def cv_docx(profile: dict, job: dict, output: Path) -> dict:
    tailored, tailoring = tailored_evidence(profile, job)
    title = "Curriculum Vitae"
    contact = " | ".join(value for value in (tailored.get("email"), tailored.get("phone"), tailored.get("location")) if value)
    paragraphs = [word_paragraph(title, style="Title", centered=True), word_paragraph(tailored.get("name") or "Candidate", style="Subtitle", centered=True)]
    if tailored.get("headline"):
        paragraphs.append(word_paragraph(tailored["headline"], style="Meta", centered=True))
    if contact:
        paragraphs.append(word_paragraph(contact, style="Meta", centered=True))
    paragraphs.extend([word_paragraph("Profile", style="Heading1"), word_paragraph(f"{tailored.get('headline') or 'Professional profile'}. This application version orders only approved evidence against the selected {job.get('title', 'role')} listing.")])
    if tailored.get("skills"):
        paragraphs.extend([word_paragraph("Core Competencies", style="Heading1"), word_paragraph(" • ".join(tailored["skills"]))])

    def add_records(heading: str, records: list[dict]) -> None:
        if not records:
            return
        paragraphs.append(word_paragraph(heading, style="Heading1"))
        for record in records:
            heading_line = " | ".join(value for value in (record.get("title"), record.get("subtitle")) if value)
            meta = " | ".join(value for value in (record.get("dates"), record.get("location")) if value)
            paragraphs.append(word_paragraph(heading_line, style="Role"))
            if meta:
                paragraphs.append(word_paragraph(meta, style="Meta"))
            paragraphs.extend(word_bullet(bullet) for bullet in record.get("bullets", []))

    add_records("Experience", tailored.get("experiences", []))
    add_records("Projects", tailored.get("projects", []))
    add_records("Education", tailored.get("education", []))
    if tailored.get("languages"):
        paragraphs.extend([word_paragraph("Languages", style="Heading1"), word_paragraph(" • ".join(tailored["languages"]))])
    write_docx(output, paragraphs, title)
    return tailoring


def cover_docx(profile: dict, job: dict, output: Path) -> None:
    title = f"Cover Letter for {job['title']} at {job['company']}"
    contact = " | ".join(filter(None, [profile.get("email"), profile.get("phone"), profile.get("location")]))
    skills = ", ".join(profile.get("skills", [])[:5]) or "the verified skills in my profile"
    paragraphs = [word_paragraph(title, style="Title", centered=True), word_paragraph(profile.get("name") or "Candidate", style="Subtitle", centered=True)]
    if contact:
        paragraphs.append(word_paragraph(contact, style="Meta", centered=True))
    paragraphs.extend([
        word_paragraph(f"{job['company']}\n{job['location']}"),
        word_paragraph("Dear hiring team,"),
        word_paragraph(f"I am applying for the {job['title']} role at {job['company']}. My approved profile highlights experience and capabilities in {skills}. I am particularly interested in the opportunity to contribute to work that involves {job['summary'].lower()}"),
        word_paragraph("This letter is a truthful starting draft. Before sending it, I will review the wording, add only specific evidence I can substantiate, and make sure it reflects my own voice."),
        word_paragraph("Sincerely,"),
        word_paragraph(profile.get("name") or "Candidate"),
    ])
    write_docx(output, paragraphs, title)


def prepare_cv_studio(folder: Path, profile: dict, job: dict) -> tuple[Path, dict]:
    """Create an isolated, local render project so one candidate's data never becomes shared template data."""
    if not CV_STUDIO_RUNTIME.is_dir():
        raise ValueError("The local CV Studio runtime is missing. Reinstall the template runtime before generating.")
    studio = folder / "cv_studio"
    shutil.copytree(CV_STUDIO_RUNTIME, studio, ignore=shutil.ignore_patterns("out", "__pycache__"))
    content, tailoring = cv_content_typst(profile, job)
    (studio / "cv-content.typ").write_text(content, encoding="utf-8")
    return studio, tailoring


def generate_documents(profile: dict, job_id: str, owner_email: str | None = None) -> dict:
    job = job_by_id(job_id, owner_email)
    if not job:
        raise ValueError("Choose a job before generating documents.")
    if not profile.get("name"):
        raise ValueError("Review and save the candidate name before generating documents.")
    if not profile.get("experiences"):
        raise ValueError("Add and save at least one structured experience record before generating. The original CV text is reference material, not CV content.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    documents_root = workspace_documents(owner_email) if owner_email else DOCUMENTS
    documents_root.mkdir(parents=True, exist_ok=True)
    folder = documents_root / stamp
    folder.mkdir(parents=True, exist_ok=True)
    template = profile.get("cv_template", "ats-plain")
    if template not in CV_TEMPLATES:
        raise ValueError("Choose one of the CV Studio templates before generating.")
    studio, _ = prepare_cv_studio(folder, profile, job)
    render_source = folder / "render_source"
    render_source.mkdir(exist_ok=True)
    letter_source = render_source / "cover_letter.typ"
    selected_pdf = folder / f"tailored_cv_{template}.pdf"
    ats_pdf = folder / "tailored_cv_ats_plain.pdf"
    letter_pdf = folder / "cover_letter.pdf"
    editable_cv = folder / "tailored_cv_editable.docx"
    editable_letter = folder / "cover_letter_editable.docx"
    letter_source.write_text(cover_typst(profile, job), encoding="utf-8")
    docx_tailoring = cv_docx(profile, job, editable_cv)
    cover_docx(profile, job, editable_letter)
    selected_studio_pdf, selected_error = compile_cv_studio(studio, template)
    selected_ok = selected_studio_pdf is not None
    if selected_studio_pdf:
        shutil.copy2(selected_studio_pdf, selected_pdf)
    ats_ok, ats_error = True, ""
    if template != "ats-plain":
        ats_studio_pdf, ats_error = compile_cv_studio(studio, "ats-plain")
        ats_ok = ats_studio_pdf is not None
        if ats_studio_pdf:
            shutil.copy2(ats_studio_pdf, ats_pdf)
    letter_ok, letter_error = compile_typst(letter_source, letter_pdf)
    files = [editable_cv, editable_letter]
    if selected_ok:
        files.append(selected_pdf)
    if template != "ats-plain" and ats_ok:
        files.append(ats_pdf)
    if letter_ok:
        files.append(letter_pdf)
    file_root = workspace_root(owner_email) if owner_email else DATA_ROOT
    return {
        "job": job,
        "compiled": selected_ok and ats_ok and letter_ok,
        "template": template,
        "primary_cv": selected_pdf.name if selected_ok else "",
        "tailoring": docx_tailoring,
        "message": "PDF and editable Word CV and cover letter are ready." if selected_ok and ats_ok and letter_ok else "Editable Word documents are ready; PDF compilation needs attention.",
        "errors": [error for error in (selected_error, ats_error, letter_error) if error],
        "files": [{"name": file.name, "url": "/files/" + file.relative_to(file_root).as_posix()} for file in files],
    }


class FieldNotesHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print("[Field Notes] " + format % args)

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK, headers: dict[str, str] | None = None) -> None:
        payload = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def browser_workspace(self) -> tuple[str, dict[str, str]]:
        token = browser_workspace_token(self.headers.get("Cookie", ""))
        if token:
            return token, {}
        token = new_workspace_token()
        ensure_workspace(token)
        return token, {"Set-Cookie": workspace_cookie(token)}

    def json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES * 2:
            raise ValueError("Request is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/status":
            return self.send_json({"typst_available": bool(shutil.which("typst")), "local_only": not production_mode()})
        if path == "/api/profile":
            token, headers = self.browser_workspace()
            return self.send_json(read_profile(token), headers=headers)
        if path == "/api/jobs":
            token, headers = self.browser_workspace()
            jobs, source = current_jobs(read_profile(token), token)
            return self.send_json({"jobs": jobs, "source": source}, headers=headers)
        if path.startswith("/files/"):
            token = browser_workspace_token(self.headers.get("Cookie", ""))
            if not token:
                return self.send_json({"error": "This download belongs to a different browser workspace."}, HTTPStatus.UNAUTHORIZED)
            root = workspace_root(token).resolve()
            requested = (root / unquote(path.removeprefix("/files/"))).resolve()
            if not requested.is_file() or requested.suffix.lower() not in PUBLIC_DOCUMENT_EXTENSIONS or root not in requested.parents:
                return self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            mime, _ = mimetypes.guess_type(requested.name)
            content = requested.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime or "application/octet-stream")
            preview_requested = "preview" in parse_qs(parsed_url.query)
            disposition = "inline" if preview_requested and requested.suffix.lower() == ".pdf" else "attachment"
            self.send_header("Content-Disposition", f'{disposition}; filename="{requested.name}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            return self.wfile.write(content)
        if path in {"/", "/index.html"}:
            path = "/index.html"
        if path.startswith("/template-samples/"):
            samples_root = (APP_ROOT / "template_samples").resolve()
            requested = (samples_root / unquote(path.removeprefix("/template-samples/"))).resolve()
            if not requested.is_file() or samples_root not in requested.parents:
                return self.send_error(HTTPStatus.NOT_FOUND, "Template sample not found")
            mime, _ = mimetypes.guess_type(requested.name)
            content = requested.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            return self.wfile.write(content)
        if path in {"/index.html", "/styles.css", "/app.js"}:
            self.path = path
            return super().do_GET()
        return self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            body = self.json_body()
            token, headers = self.browser_workspace()
            if path == "/api/upload":
                name = safe_filename(str(body.get("name", "cv.txt")))
                encoded = str(body.get("content", ""))
                try:
                    content = base64.b64decode(encoded, validate=True)
                except ValueError as error:
                    raise ValueError("The selected file could not be decoded.") from error
                if not content or len(content) > MAX_UPLOAD_BYTES:
                    raise ValueError("Use a non-empty CV smaller than 8 MB.")
                destination = workspace_uploads(token) / (datetime.now().strftime("%Y%m%d-%H%M%S-") + name)
                destination.write_bytes(content)
                profile = profile_from_text(extract_text(destination), name, token)
                return self.send_json({"profile": profile, "message": "CV read. Review the extracted profile before generating documents."}, headers=headers)
            if path == "/api/profile":
                return self.send_json({"profile": write_profile(body, token), "message": "Profile saved in this browser workspace."}, headers=headers)
            if path == "/api/generate":
                profile = read_profile(token)
                return self.send_json(generate_documents(profile, str(body.get("job_id", "")), token), headers=headers)
            return self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except PermissionError as error:
            return self.send_json({"error": str(error)}, HTTPStatus.UNAUTHORIZED)
        except (ValueError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # pragma: no cover - defensive local-app boundary
            message = "Unexpected server error. Please try again." if production_mode() else "Unexpected local error: " + str(error)
            return self.send_json({"error": message}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    ensure_data_directories()
    host, port = "127.0.0.1", 8765
    print(f"Field Notes is running at http://{host}:{port}")
    print("Your CV and generated files stay in this folder's local_data directory.")
    ThreadingHTTPServer((host, port), FieldNotesHandler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
