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
        if len(skill) > 70:   # cut on a word, not mid-word
            skill = skill[:70].rsplit(" ", 1)[0] or skill[:70]
            skill = re.sub(r"\s+(?:and|or|the|of|with|in|for|to|a|an|on|by|as|at|incl\.?)$", "", skill, flags=re.I)
        if skill and skill.lower() not in {s.lower() for s in found}:
            found.append(skill)
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


INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def normalize_text(text: str) -> str:
    """Strip the invisible characters PDF and Word extractors sprinkle through a CV.

    Word exports and `pdftotext` emit zero-width spaces inside field labels
    ("Name:\u200b Ricky"), which silently breaks every pattern that follows.
    """
    text = text.translate(INVISIBLE_CHARS)
    for space in ("\u00a0", "\u202f", "\u2007", "\u2009", "\u2002"):
        text = text.replace(space, " ")
    return text


def extract_text(path: Path) -> str:
    return normalize_text(raw_extract_text(path))


def raw_extract_text(path: Path) -> str:
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
    # Whatever the extractor left behind, no line reaching a parser holds a zero-width space.
    text = normalize_text(text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip() and not re.match(r"^(Page \| \d+|.+@.+)$", line.strip())]


NAME_WORD = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'’\-]*")

# Lowercase name particles ("Maria de la Cruz", "van der Berg") are still a person.
NAME_PARTICLES = {"de", "del", "della", "der", "den", "van", "von", "bin", "ibn", "al", "el", "da", "di", "du", "dos", "das", "le", "la", "los", "mac", "mc", "ap", "af", "o"}

# Professional titles that trail a name ("Ricky Sambo Macharm, PEM™") are not the name.
CREDENTIAL_WORDS = {"pem", "pmp", "mba", "msc", "m.sc", "bsc", "b.sc", "phd", "ph.d", "acca", "cfa", "cpa",
                    "ceng", "c.eng", "rn", "md", "pgd", "hnd", "ond", "cipm", "mnim", "fca", "ccna", "pmi",
                    "shrm", "meng", "beng", "ba", "ma", "llb", "llm", "dr", "prof", "eng", "csm", "itil",
                    "ceh", "cissp", "cfp", "cisa", "cism", "prince2", "six", "sigma"}

# Field labels on a personal-data block must never be read as a name.
CV_LABEL_WORDS = {"name", "names", "surname", "given", "first", "last", "middle", "address", "email",
                  "e-mail", "phone", "mobile", "nationality", "date", "place", "birth", "dob", "sex",
                  "gender", "marital", "status", "contact", "tel", "fax", "website", "linkedin"}

# Section headings and job titles must never be mistaken for a person's name.
CV_SECTION_WORDS = {
    "curriculum", "vitae", "resume", "cv", "profile", "summary", "objective", "experience",
    "employment", "history", "education", "academic", "background", "skills", "skill",
    "qualifications", "languages", "language", "certifications", "certificates", "projects",
    "interests", "references", "contact", "details", "personal", "professional", "key",
    "other", "relevant", "about", "achievements", "awards", "publications", "training",
    "courses", "volunteering",
}

CV_ROLE_WORDS = {
    "senior", "junior", "lead", "head", "chief", "principal", "staff", "associate", "assistant",
    "deputy", "executive", "officer", "manager", "management", "director", "engineer",
    "engineering", "developer", "programmer", "architect", "scientist", "analyst", "analytics",
    "consultant", "consulting", "advisor", "adviser", "specialist", "coordinator",
    "administrator", "researcher", "research", "intern", "trainee", "graduate", "student",
    "teacher", "lecturer", "professor", "tutor", "designer", "technician", "accountant",
    "auditor", "lawyer", "attorney", "nurse", "doctor", "pharmacist", "driver", "marketer",
    "sales", "marketing", "product", "project", "program", "programme", "business", "finance",
    "financial", "software", "data", "machine", "learning", "science", "quantitative", "quant",
    "risk", "portfolio", "investment", "banking", "energy", "climate", "policy", "strategy",
    "operations", "logistics", "human", "resources", "recruiter", "communications", "writer",
    "editor", "photographer", "artist", "chef", "welder", "electrician", "plumber", "mechanic",
    "supervisor", "foreman", "fitter", "operator", "midwife", "physician", "surgeon", "dentist",
    "psychologist", "counselor", "counsellor", "social", "worker", "trainer", "instructor",
    "coach", "freelance", "remote", "available", "open",
}

COUNTRY_WORDS = (
    "nigeria", "germany", "ghana", "kenya", "south africa", "tanzania", "uganda", "rwanda",
    "ethiopia", "senegal", "cameroon", "ivory coast", "côte d'ivoire", "benin", "togo", "mali",
    "zambia", "zimbabwe", "botswana", "namibia", "malawi", "mozambique", "egypt", "morocco",
    "tunisia", "algeria", "libya", "sudan", "somalia", "eritrea", "liberia", "sierra leone",
    "gambia", "guinea", "burkina faso", "niger", "chad", "gabon", "congo", "angola", "lesotho",
    "eswatini", "swaziland", "mauritius", "madagascar", "cape verde", "united kingdom", "uk",
    "england", "scotland", "wales", "ireland", "france", "spain", "portugal", "italy", "greece",
    "netherlands", "holland", "belgium", "luxembourg", "switzerland", "austria", "denmark",
    "sweden", "norway", "finland", "iceland", "poland", "czech", "slovakia", "hungary",
    "romania", "bulgaria", "croatia", "serbia", "slovenia", "bosnia", "albania", "estonia",
    "latvia", "lithuania", "ukraine", "russia", "turkey", "cyprus", "malta", "usa",
    "united states", "canada", "mexico", "brazil", "argentina", "chile", "colombia", "peru",
    "venezuela", "ecuador", "bolivia", "uruguay", "paraguay", "costa rica", "panama", "cuba",
    "jamaica", "india", "pakistan", "bangladesh", "sri lanka", "nepal", "china", "japan",
    "korea", "singapore", "malaysia", "indonesia", "philippines", "vietnam", "thailand",
    "cambodia", "myanmar", "australia", "new zealand", "united arab emirates", "uae", "qatar",
    "saudi arabia", "kuwait", "bahrain", "oman", "jordan", "lebanon", "israel", "iran", "iraq",
    "kazakhstan", "europe", "africa", "asia", "north america", "latin america",
)


def name_candidate(line: str) -> str:
    """Return the line when it reads like a person's name, otherwise an empty string."""
    for piece in (line, re.split(r"[,;(]", line)[0]):
        candidate = re.sub(r"[™®©]", "", piece)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,;:|•·-")
        if not candidate or not 4 <= len(candidate) <= 70:
            continue
        if any(char.isdigit() for char in candidate) or "http" in candidate.lower():
            continue
        if any(char in candidate for char in ":|/\\()[]{}<>*&+=%$#"):
            continue
        words = candidate.split()
        # A trailing credential is a title, not part of the name ("Ricky Sambo Macharm PEM").
        while len(words) > 2 and (words[-1].lower().strip(".'-") in CREDENTIAL_WORDS or (words[-1].isupper() and 2 <= len(words[-1]) <= 5)):
            words = words[:-1]
        candidate = " ".join(words)
        if not 2 <= len(words) <= 5:
            continue
        if not all(NAME_WORD.fullmatch(word) for word in words):
            continue
        if any(not word[:1].isupper() and word.lower() not in NAME_PARTICLES for word in words):
            continue
        if sum(1 for word in words if word[:1].isupper()) < 2:
            continue
        lowered = {word.lower().strip(".'-") for word in words}
        if lowered & CV_SECTION_WORDS or lowered & CV_ROLE_WORDS or lowered & CV_LABEL_WORDS:
            continue
        return candidate
    return ""


def parsed_name(lines: list[str]) -> str:
    # 1. An explicit label: "Name: Jane Doe". Anything after a comma is a title, not the name.
    for line in lines[:30]:
        candidate = re.sub(r"^.*?\bName\b\s*[:\-–]?\s*", "", line, flags=re.I).strip()
        if candidate == line:
            continue
        candidate = re.split(r"[,;(]", candidate)[0].strip(" .'-")
        words = candidate.split()
        while len(words) > 2 and (words[-1].lower().strip(".'-") in CREDENTIAL_WORDS or (words[-1].isupper() and 2 <= len(words[-1]) <= 5)):
            words = words[:-1]
        candidate = " ".join(words)
        if re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{2,69}", candidate):
            return candidate
    # 2. A "Curriculum Vitae" heading with the name underneath it.
    for index, line in enumerate(lines[:15]):
        if line.lower().strip(" :") in {"curriculum", "vitae", "curriculum vitae"} and index + 1 < len(lines):
            candidate = name_candidate(lines[index + 1])
            if candidate:
                return candidate
    # 3. The common case: the name is simply the first line. Score candidates instead of
    #    trusting the first match, so a job title on line one is not read as a person.
    best, best_score = "", 0
    for index, line in enumerate(lines[:10]):
        candidate = name_candidate(line)
        if not candidate:
            continue
        score = 3 if index == 0 else (2 if index <= 2 else 1)
        score += 1 if candidate.isupper() else 0
        score += 1 if len(candidate.split()) == 2 else 0
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= 3 else ""


def clean_location(line: str) -> str:
    """Trim a header line down to the place itself, dropping phones and separators."""
    value = re.split(r"[·|•]", line)[0]
    value = re.sub(r"\s*[-–—]?\s*\(?\+?\d[\d ()/-]{6,}\d\)?.*$", "", value)
    return value.strip(" ,;·|-")


def parsed_location(lines: list[str]) -> str:
    for index, line in enumerate(lines[:35]):
        labelled = re.match(r"^(?:address|location|based in|residence|city|town)\s*[:|\-]\s*(.+)$", line, re.I)
        if not labelled or len(labelled.group(1).strip()) > 120:
            continue
        value = clean_location(labelled.group(1).strip()).strip(" .,;·|-")
        for extra in lines[index + 1:index + 3]:
            # A postal address that wraps keeps going on the next line.
            continuation = clean_cv_line(extra)
            if not continuation or ":" in continuation or len(continuation) > 60 or any(char.isdigit() for char in continuation):
                break
            if re.search(r"[.!?]\s*$", value):
                break
            value = clean_cv_line(f"{value}, {continuation}").strip(" .,;·|-")
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
        # A full postal address is not a useful location: keep the town and region.
        if len(pieces) >= 3 and not any(char.isdigit() for char in pieces[-1]):
            value = ", ".join(pieces[-2:])
        return value
    for line in lines[:25]:
        if len(line) > 160:
            continue
        for piece in re.split(r"[|·•]", line):
            value = re.sub(r"^[A-Za-z][A-Za-z #/()'-]{1,26}:\s*", "", clean_location(piece))
            if not 3 <= len(value) <= 60 or "@" in value or any(char.isdigit() for char in value):
                continue
            lowered = value.lower()
            if any(re.search(r"(?<![a-z])" + re.escape(country) + r"(?![a-z])", lowered) for country in COUNTRY_WORDS):
                return value
    for line in lines[:15]:
        head, separator, tail = line.partition(",")
        if separator and tail.strip().lower().strip(" .") in COUNTRY_WORDS:
            return clean_location(line)
    return ""


def clean_cv_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("│", "|").replace("", "").replace("•", "").strip(" -|•")).strip()


def heading_key(line: str) -> str:
    """Normalise a heading for comparison; also collapses letter-spaced headings."""
    return re.sub(r"[^a-z&/]", "", line.lower())


EXPERIENCE_HEADINGS = (
    "work experience", "professional experience", "employment experience", "experience",
    "employment history", "career history", "work history", "professional background",
    "relevant experience", "regional/international experience",
)
EDUCATION_HEADINGS = (
    "academic background", "acad. background", "education", "education and training",
    "academic qualifications", "academic record", "qualifications",
)
LANGUAGE_HEADINGS = ("languages", "language skills", "language proficiency", "spoken languages")
SECTION_BREAKS = (
    "academic background", "acad. background", "education", "education and training", "languages",
    "language skills", "language proficiency", "certifications", "certificates", "publications",
    "projects", "interests", "hobbies", "references", "core competencies", "core competence", "skills",
    "key skills", "key qualifications", "profile", "summary", "awards", "training", "courses",
    "volunteering", "additional information", "additional training", "affiliations",
    "additional training, experience and affiliations", "computer/internet proficiency",
    "computer skills", "computer proficiency", "personal data", "personal details", "contact",
    "other relevant", "other relevant information", "referees", "regional/international experience",
    "regional experience", "international experience",
)

# Headings that are distinctive enough to recognise as a single word at the start of a line.
DISTINCTIVE_HEADINGS = {
    "languages", "language", "education", "skills", "profile", "summary", "interests", "references",
    "referees", "certifications", "certificates", "publications", "awards", "hobbies", "training",
    "courses", "qualifications", "affiliations",
}

# Bullets come in many glyphs: Word and PDF exports use ●, ▪, ‣ as often as •.
BULLET_RE = re.compile(r"^(?:[•●○◦▪▫‣·*·–—]|o\s|-)\s*(.+)$")

# "2007 – Present", "2007-Date", "2007 to date", "01/2019 – 06/2021".
DATE_RANGE = (
    r"(?:(?:0?[1-9]|1[0-2])[/.-]\d{4}|\d{4})\s*(?:[–—-]|\bto\b)\s*"
    r"(?:(?:0?[1-9]|1[0-2])[/.-]\d{4}|\d{4}|date|till date|to date|present|now|current)"
)
DATE_PATTERN = re.compile(DATE_RANGE, re.I)


def heading_remainder(line: str, wanted: set[str]) -> str | None:
    """When a heading shares its line with the content after it, return that content.

    Two-column PDFs print `Work Experience   Africa Partnerships Energy Coordinator`
    on one line; the heading has to be recognised without swallowing the job title.
    """
    words = line.split()
    for count in range(min(4, len(words) - 1), 0, -1):
        prefix = " ".join(words[:count])
        key = heading_key(prefix.rstrip(":|·-"))
        if key not in wanted:
            continue
        if count == 1:
            # A single generic word ("Experience Manager | Acme") is a job title, not a heading.
            follows = line[len(prefix):]
            if follows[:1] not in {":", "|", "·"} and key not in DISTINCTIVE_HEADINGS:
                continue
        return " ".join(words[count:])
    return None


def section_start(lines: list[str], names: tuple[str, ...], after: int = 0) -> tuple[int, str] | None:
    """The first heading line, plus anything sharing that line with it."""
    wanted = {heading_key(name) for name in names}
    for index in range(after, len(lines)):
        line = lines[index]
        if len(line) > 120 or BULLET_RE.match(line.strip()):
            continue
        if heading_key(line) in wanted:
            return index, ""
        remainder = heading_remainder(line, wanted)
        if remainder:
            return index, remainder
    return None


def section_index(lines: list[str], names: tuple[str, ...], after: int = 0) -> int | None:
    """Index of the first heading line naming one of `names`, searched from `after`."""
    found = section_start(lines, names, after)
    return found[0] if found else None


def split_trailing_place(value: str) -> tuple[str, str]:
    """Peel a trailing "City, Country" off an organisation or school name."""
    cleaned = re.sub(r"\b([A-Z][\w'’-]*(?:, [A-Z][\w'’-]*)?)\s+\1\b", r"\1", clean_cv_line(value))
    pieces = [piece.strip() for piece in cleaned.split(",") if piece.strip()]
    if len(pieces) < 2:
        return cleaned, ""
    take = 2 if len(pieces) >= 3 and pieces[-1].lower().strip(".") in COUNTRY_WORDS else 1
    return clean_cv_line(", ".join(pieces[:-take])), clean_cv_line(", ".join(pieces[-take:]))


WORK_MODES = ("hybrid", "remote", "on-site", "onsite", "part-time", "parttime", "full-time", "fulltime",
              "contract", "permanent", "temporary", "freelance", "internship", "working remotely")


def strip_work_mode(value: str) -> str:
    """Drop a trailing work-mode word ("· Hybrid", "Remote") from a header line."""
    cleaned = clean_cv_line(value)
    while cleaned:
        trimmed = re.sub(r"(?:^|[\s·|,\-]+)(?:" + "|".join(re.escape(mode) for mode in WORK_MODES) + r")\s*$", "", cleaned, flags=re.I).strip(" ,;·|-")
        if trimmed == cleaned:
            return cleaned
        cleaned = trimmed
    return cleaned


def split_role_header(header: str, date_pattern: re.Pattern) -> tuple[str, str, str]:
    """Split "Title — Organisation, City (2022 – Present)" into title, organisation and location."""
    text = strip_work_mode(re.sub(r"\(\s*\)|\[\s*\]", " ", date_pattern.sub(" ", header)))
    organisation = location = ""
    # A bracket that is not a date carries the organisation: "Title (Organisation, City)" —
    # but only when no separator ("|", "—", ":") already split title from organisation.
    inside = re.search(r"\(([^()]*)\)", text)
    separator = re.search(r"[|—–]|\s-\s|:\s", text)
    if inside and inside.group(1).strip() and (separator is None or separator.start() > inside.start()):
        title = clean_cv_line(text[:inside.start()])
        organisation = clean_cv_line(inside.group(1))
        trailing = clean_cv_line(text[inside.end():])
        if trailing:
            organisation = clean_cv_line(f"{organisation} {trailing}")
    else:
        text = re.sub(r"\(\s*\)|\[\s*\]", " ", text)   # the brackets a removed date left behind
        text = re.sub(r"\)\s*\S+$", "", text)          # text glued after the closing bracket
        text = re.sub(r"[()\[\]]", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" -–—·|,.;")
        parts = re.split(r"\s*[|—–]\s*|\s+-\s+|:\s+", text, maxsplit=1)
        title = clean_cv_line(parts[0])
        organisation = clean_cv_line(parts[1]) if len(parts) > 1 else ""
    organisation, location = split_trailing_place(organisation)
    return strip_work_mode(title), organisation, strip_work_mode(location)


def looks_like_place(line: str) -> bool:
    value = clean_cv_line(line)
    if not 3 <= len(value) <= 40 or any(char.isdigit() for char in value):
        return False
    lowered = value.lower()
    return any(re.search(r"(?<![a-z])" + re.escape(country) + r"(?![a-z])", lowered) for country in COUNTRY_WORDS)


INSTITUTION_RE = re.compile(r"\b(?:Universit\w*|Institute|College|Polytechnic|School|Academy|Seminary|Faculty|Campus)\b", re.I)


def institution_below(section: list[str], start: int) -> tuple[str, str]:
    """The school named on one of the lines after a qualification line."""
    for line in section[start:start + 4]:
        clean = clean_cv_line(line)
        if not clean or len(clean) > 120 or DATE_PATTERN.search(clean):
            continue
        if INSTITUTION_RE.search(clean):
            clean = re.sub(r"\b(?:P\.?\s?M\.?\s?B\.?|PMB)\b.*$", "", clean, flags=re.I)
            return split_trailing_place(clean)
    return "", ""


def absorb_bleed(rows: list[str]) -> list[str]:
    """A line that opens with a date and continues in prose is the tail of the entry above.

    A two-column PDF keeps printing the right column while the left column has already
    moved on to the next date ("10/2020 – 10/2022   and other GET.transform donors).").
    """
    merged: list[str] = []
    for line in rows:
        clean = clean_cv_line(line)
        lead = re.match(r"^(" + DATE_RANGE + r")\s+(\S.*)$", clean, re.I)
        if lead and merged:
            tail = lead.group(2)
            previous = clean_cv_line(merged[-1])
            if tail[:1].islower() or previous[-1:] in {",", "(", "-", "–", "—", ";", ":"}:
                merged[-1] = clean_cv_line(f"{merged[-1]} {tail}")
                merged.append(lead.group(1))
                continue
        merged.append(line)
    return merged


def parse_work_experience(lines: list[str]) -> list[dict]:
    found = section_start(lines, EXPERIENCE_HEADINGS)
    if not found:
        return []
    start, remainder = found
    if remainder:
        # The heading shared its line with the first role's title.
        lines = list(lines)
        lines[start] = remainder
    end = section_index(lines, SECTION_BREAKS, start + 1) or len(lines)
    chunk = absorb_bleed(lines[start + 1:end])
    date_pattern = DATE_PATTERN
    boundaries = [index for index, line in enumerate(chunk) if date_pattern.search(line)]
    records: list[dict] = []

    def collect_bullets(segment: list[str]) -> list[str]:
        bullets: list[str] = []
        current = ""
        for line in segment:
            clean = clean_cv_line(line)
            if not clean:
                continue
            marker = BULLET_RE.match(line.strip())
            if marker:
                if current:
                    bullets.append(current)
                current = clean_cv_line(marker.group(1))
            elif current and len(current) < 220:
                current = clean_cv_line(current + " " + clean)
            elif current:
                bullets.append(current)
                current = clean
        if current:
            bullets.append(current)
        return bullets[:7]

    # Some two-column PDFs put the first role on the same line as the section heading.
    lead_raw = lines[start]
    for name in EXPERIENCE_HEADINGS:
        lead_raw = re.sub(re.escape(name), " ", lead_raw, flags=re.I)
    lead_title, lead_org, lead_location = split_role_header(lead_raw.strip(" |·-"), date_pattern)
    consumed: set[int] = set()
    if lead_title:
        first_line = clean_cv_line(chunk[0]) if chunk else ""
        if not lead_org and first_line and not BULLET_RE.match(chunk[0].strip()) and not date_pattern.fullmatch(first_line):
            if date_pattern.search(first_line) or any(re.search(r"(?<![a-z])" + re.escape(mode) + r"(?![a-z])", first_line, re.I) for mode in WORK_MODES):
                _, lead_org, lead_location = split_role_header(chunk[0], date_pattern)
            else:
                lead_org, lead_location = split_trailing_place(first_line)
        if boundaries:
            first_date = date_pattern.search(chunk[boundaries[0]])
            first_end = boundaries[1] if len(boundaries) > 1 else len(chunk)
            lead_dates = first_date.group(0)[:80] if first_date else ""
            lead_bullets = collect_bullets(chunk[boundaries[0] + 1:first_end])
            consumed.add(boundaries[0])
        else:
            lead_dates, lead_bullets = "", collect_bullets(chunk)
        records.append({
            "title": lead_title[:160],
            "subtitle": lead_org[:160],
            "dates": lead_dates,
            "location": lead_location[:80],
            "bullets": lead_bullets,
        })

    for position, begin in enumerate(boundaries):
        if begin in consumed:
            continue
        finish = boundaries[position + 1] if position + 1 < len(boundaries) else len(chunk)
        segment = chunk[begin:finish]
        date_match = date_pattern.search(segment[0])
        if not date_match:
            continue
        # A date-only line means the title sits further down, as in a left-column layout.
        header_index = 0
        bordered_header = False
        if date_pattern.fullmatch(clean_cv_line(segment[0]).strip()):
            # Left-column layouts mark the title cell with a border glyph ("Title │ Org"),
            # and the lines above the title belong to the entry before this one.
            bordered = next(
                (offset for offset, line in enumerate(segment)
                 if offset > 0 and ("│" in line or "|" in line) and not BULLET_RE.match(line.strip())),
                None,
            )
            if bordered is not None:
                bordered_header = True
                header_index = bordered
                while header_index > 1 and clean_cv_line(segment[header_index])[:1].islower():
                    header_index -= 1   # the title cell wrapped onto the line above
            else:
                header_index = next(
                    (offset for offset, line in enumerate(segment)
                     if offset > 0 and not BULLET_RE.match(line.strip())
                     and not date_pattern.fullmatch(clean_cv_line(line).strip())),
                    0,
                )
        header_lines = [segment[header_index]]
        cursor = header_index + 1
        while cursor < len(segment) and not BULLET_RE.match(segment[cursor].strip()):
            following_line = clean_cv_line(segment[cursor])
            if not following_line:
                break
            previous_raw = segment[cursor - 1].strip()
            wraps = following_line[:1].islower() or bool(re.search(r"[|│&,–—/]\s*$|\b(?:and|of|the|in|for|with|to|by|at)\s*$", previous_raw, re.I))
            if not wraps and (
                not bordered_header                      # a title cell that spans lines
                or len(" ".join(header_lines)) >= 140
                or previous_raw[-1:] in ".!?;"
            ):
                break   # the line above finished cleanly, so this is a new block
            header_lines.append(segment[cursor])
            cursor += 1
        title, organisation, location = split_role_header(clean_cv_line(" ".join(header_lines)), date_pattern)
        if header_index == 0 and (not title or not organisation) and begin > 0:
            previous = chunk[begin - 1]
            if not date_pattern.search(previous) and not BULLET_RE.match(previous.strip()) and len(clean_cv_line(previous)) <= 120:
                previous_title, previous_org, previous_location = split_role_header(previous, date_pattern)
                title = title or previous_title
                organisation = organisation or previous_org
                location = location or previous_location
        following = segment[cursor:]
        if following and looks_like_place(following[0]):
            place = clean_cv_line(following[0])
            if not location:
                location = place
            elif place.lower() not in location.lower():
                location = f"{location}, {place}"   # "Vom" on one line, "Nigeria" on the next
        elif following and not BULLET_RE.match(following[0].strip()) and not date_pattern.search(following[0]) and strip_work_mode(following[0]) and not organisation:
            organisation, extra_location = split_trailing_place(clean_cv_line(" ".join(filter(None, [organisation, strip_work_mode(following[0])]))))
            location = location or extra_location
        bullets = collect_bullets(following)
        orphans = collect_bullets(segment[1:header_index])
        if orphans and records:
            # Lines printed above the title of this entry close the entry before it.
            records[-1]["bullets"] = (records[-1]["bullets"] + orphans)[:10]
        if title and (organisation or bullets):
            records.append({"title": title[:160], "subtitle": organisation[:160], "dates": date_match.group(0)[:80], "location": location[:80], "bullets": bullets[:7]})
    return records[:8]


def parse_education(lines: list[str]) -> list[dict]:
    found = section_start(lines, EDUCATION_HEADINGS)
    if not found:
        return []
    start, remainder = found
    end = section_index(lines, SECTION_BREAKS + EXPERIENCE_HEADINGS, start + 1) or len(lines)
    section = ([remainder] if remainder else []) + lines[start + 1:end]
    records: list[dict] = []
    degree_pattern = re.compile(r"\b(?:MBA|M\.Sc|MSc|MA|MEng|B\.Sc|BSc|BEng|B\.Eng|BA|Bachelor|Master|PhD|Ph\.D|Doctorate|Certificate|Diploma|HND|OND|PGD)\b", re.I)
    junk_pattern = re.compile(r"\b(?:Thesis|Dissertation|Graduated|Grade|Grades|Result|Results|Modules|Distance|Award|Awards|Ref|Ref\.|Project|Projects)\b.*$", re.I)
    for index, line in enumerate(section):
        if not degree_pattern.search(line):
            continue
        years = re.findall(r"\b(?:19|20)\d{2}\b", line)
        if (not years or re.search(r"[–-]\s*$|\(\s*$", clean_cv_line(line))) and index + 1 < len(section):
            years += re.findall(r"\b(?:19|20)\d{2}\b", section[index + 1])
        detail = re.sub(r"\(([^()]*)\)\s*", lambda match: " " if re.search(r"\d{4}", match.group(1)) else match.group(0), line)
        degree = degree_pattern.search(detail)
        # A wrapped line carries the tail of the entry above ("…portfolios.BEng …"); a degree
        # that simply starts this entry's name ("Senior Secondary Certificate …") does not.
        if degree and degree.start() > 0 and not detail[degree.start() - 1].isspace():
            detail = detail[degree.start():]
        detail = re.sub(r"\b(?:19|20)\d{2}\b", " ", detail)
        detail = re.sub(r"[()\[\]]", " ", detail)
        detail = re.sub(r"\s*[–-]\s*$", "", detail)
        detail = junk_pattern.sub("", detail)
        parts = re.split(r"\s*[|—–]\s*|\s+-\s+", clean_cv_line(detail), maxsplit=1)
        title = clean_cv_line(parts[0])
        if title.endswith(".") and "." not in title[:-1]:
            title = title[:-1]   # "MBA." -> "MBA", but leave "B.Sc." alone
        school, location = split_trailing_place(parts[1]) if len(parts) > 1 else ("", "")
        if not school:
            # The qualification and the school are usually on separate lines.
            school, location = institution_below(section, index + 1)
        if title:
            records.append({"title": title[:160], "subtitle": school[:160], "dates": f"{years[0]} – {years[-1]}" if len(years) > 1 else (years[0] if years else ""), "location": location[:80], "bullets": []})
    return records[:5]


LANGUAGE_COLUMNS = {"language", "languages", "written", "spoken", "reading", "listening", "speaking",
                    "level", "proficiency", "fluency", "score", "skill", "skills"}
LANGUAGE_LEVELS = ("mother tongue", "above average", "bilingual", "conversational", "native", "fluent",
                   "fluency", "proficiency", "excellent", "advanced", "intermediate", "proficient",
                   "average", "beginner", "basic", "good", "fair", "poor", "working", "limited")


SKILL_HEADINGS = ("skills", "key skills", "technical skills", "core competencies", "core competence",
                  "areas of expertise", "expertise", "competencies", "computer skills",
                  "computer/internet proficiency", "computer proficiency", "key qualifications",
                  "proficiencies", "technical proficiencies")
SKILL_LABELS = re.compile(
    r"^(?:core competenc(?:e|ies)|key skills|skills|technical skills|areas of expertise|"
    r"key qualifications|proficiencies|technical proficiencies|computer skills)\s*[:|]\s*(.+)$", re.I)


def skills_from_lines(lines: list[str]) -> list[str]:
    """Read a labelled competence line, or a Skills / Computer proficiency section."""
    found: list[str] = []
    headings = {heading_key(name) for name in SKILL_HEADINGS}
    breaks = {heading_key(name) for name in SECTION_BREAKS}
    for index, line in enumerate(lines):
        clean = clean_cv_line(line)
        labelled = SKILL_LABELS.match(clean)
        if labelled:
            value = labelled.group(1)
            # A wrapped line continues the last item: "… Adapting technology to" / "meet objectives."
            if not value.rstrip().endswith((".", ";")) and index + 1 < len(lines):
                following = clean_cv_line(lines[index + 1])
                starts_lower = bool(following) and following[:1].islower()
                if starts_lower and len(following) <= 60 and ":" not in following and heading_key(following) not in breaks | headings | {heading_key(name) for name in EXPERIENCE_HEADINGS + EDUCATION_HEADINGS}:
                    value = f"{value.rstrip()} {following}"
            for piece in re.split(r"[,;]", value):
                piece = clean_cv_line(piece)
                if 2 < len(piece) <= 120:
                    found.append(piece)
            continue
        if len(clean) > 60 or heading_key(clean) not in headings:
            continue
        current = ""
        for extra in lines[index + 1:index + 16]:
            if heading_key(clean_cv_line(extra)) in breaks:
                break
            marker = BULLET_RE.match(extra.strip())
            value = clean_cv_line(marker.group(1) if marker else extra)
            if not value:
                continue
            if marker:
                if current:
                    found.append(current)
                current = value
            elif current:
                current = clean_cv_line(f"{current} {value}")   # a bullet that wrapped
            else:
                current = value
        if current:
            found.append(current)
    return normalize_skills(found)


def language_entry(clean: str) -> str:
    """One row of a language table, or one item of a list: "ENGLISH   excellent …"."""
    tokens = clean.split()
    if not tokens:
        return ""
    name = tokens[0].strip(".,;:()[]")
    if not name or name.lower() in LANGUAGE_COLUMNS or not re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,24}", name):
        return ""
    rest = clean[len(tokens[0]):].strip(" -–—:·|,.;()[]")
    level = ""
    words = rest.split()
    for position in range(len(words)):
        phrase = " ".join(words[position:position + 2]).lower().strip(".,;:()[]")
        single = words[position].lower().strip(".,;:()[]")
        if phrase in LANGUAGE_LEVELS:
            level = phrase
            break
        if single in LANGUAGE_LEVELS:
            level = single
            break
    if level:
        # "English: Oral and writing proficiency" — the level is prose, keep it whole.
        if words and words[0].lower().strip(".,;:()[]") != level:
            return f"{name} — {rest[:60]}"
        return f"{name} — {level}"
    return name if not rest else ""


def parse_languages(lines: list[str]) -> list[str]:
    # "Languages: English (fluent), German (basic)" on one line.
    inline: list[str] = []
    for line in lines:
        match = re.match(r"^\s*languages?\s*[:|]\s*(.+)$", line, re.I)
        if not match:
            continue
        for piece in re.split(r"[,;·|]", match.group(1)):
            entry = language_entry(clean_cv_line(piece))
            if entry:
                inline.append(entry)
    if inline:
        return normalize_skills(inline)
    found = section_start(lines, LANGUAGE_HEADINGS)
    if not found:
        return []
    start, remainder = found
    end = section_index(lines, SECTION_BREAKS, start + 1) or len(lines)
    entries: list[str] = []
    head = remainder or re.sub(r"^\s*languages?\s*[:|·-]?\s*", "", lines[start], flags=re.I)
    for line in [head, *lines[start + 1:end]]:
        entry = language_entry(clean_cv_line(line))
        if entry:
            entries.append(entry)
    return normalize_skills(entries)


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
    if experiences:
        headline = experiences[0]["title"]
    else:
        # Fall back to a line that reads like a job title — never a labelled field or an address.
        headline = next((line for line in lines if 4 < len(line) < 80 and ":" not in line and not any(char.isdigit() for char in line) and not {word.lower().strip(".,") for word in line.split()} & CV_LABEL_WORDS and any(word in line.lower() for word in ("analyst", "scientist", "engineer", "research", "manager", "coordinator", "advisor", "consultant", "specialist", "developer", "officer", "lead", "teacher", "lecturer", "nurse", "accountant"))), "")
    skills.extend(skills_from_lines(lines))
    location = parsed_location([re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()])
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
        "location": str(raw.get("location") or raw.get("work_mode") or "").strip(),
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
  location: {typst_string(tailored.get("location") or "")},
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
{typst_escape(job['location']) if job.get('location') else ""}

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
