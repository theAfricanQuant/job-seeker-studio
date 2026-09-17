#!/usr/bin/env python3
"""Field Notes: a local-only CV-to-Typst job-application workspace."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

APP_ROOT = Path(__file__).resolve().parent
DATA_ROOT = APP_ROOT / "local_data"
UPLOADS = DATA_ROOT / "uploads"
DOCUMENTS = DATA_ROOT / "documents"
PROFILE_FILE = DATA_ROOT / "profile.json"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

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
    for folder in (DATA_ROOT, UPLOADS, DOCUMENTS):
        folder.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or "cv.txt"


def read_profile() -> dict:
    if PROFILE_FILE.exists():
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    return empty_profile()


def empty_profile() -> dict:
    return {
        "name": "",
        "email": "",
        "phone": "",
        "headline": "",
        "skills": [],
        "source_excerpt": "",
        "uploaded_file": "",
        "updated_at": "",
    }


def write_profile(profile: dict) -> dict:
    clean = {
        "name": str(profile.get("name", "")).strip()[:100],
        "email": str(profile.get("email", "")).strip()[:160],
        "phone": str(profile.get("phone", "")).strip()[:80],
        "headline": str(profile.get("headline", "")).strip()[:220],
        "skills": normalize_skills(profile.get("skills", [])),
        "source_excerpt": str(profile.get("source_excerpt", "")).strip()[:4000],
        "uploaded_file": str(profile.get("uploaded_file", "")).strip()[:180],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    PROFILE_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean


def normalize_skills(value: object) -> list[str]:
    raw = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
    found: list[str] = []
    for item in raw:
        skill = str(item).strip()
        if skill and skill.lower() not in {s.lower() for s in found}:
            found.append(skill[:70])
    return found[:24]


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()
    if extension == ".pdf":
        command = ["pdftotext", str(path), "-"]
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


def profile_from_text(text: str, uploaded_file: str) -> dict:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", text)
    candidate_name = ""
    for line in lines[:8]:
        if "@" not in line and len(line) <= 70 and re.fullmatch(r"[A-Za-zÀ-ÿ .'-]+", line):
            candidate_name = line
            break
    lower = text.lower()
    skills = []
    for key, label in KNOWN_SKILLS.items():
        if re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", lower) and label not in skills:
            skills.append(label)
    headline = next((line for line in lines if len(line) < 150 and any(word in line.lower() for word in ["analyst", "scientist", "engineer", "research", "manager"])), "")
    return write_profile({
        "name": candidate_name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "headline": headline,
        "skills": skills,
        "source_excerpt": "\n".join(lines[:35]),
        "uploaded_file": uploaded_file,
    })


def job_matches(profile: dict) -> list[dict]:
    searchable = " ".join(profile.get("skills", []) + [profile.get("headline", ""), profile.get("source_excerpt", "")]).lower()
    results = []
    for job in JOBS:
        hits = [keyword for keyword in job["keywords"] if keyword in searchable]
        score = min(97, 48 + len(hits) * 8)
        results.append({**job, "score": score, "matches": hits})
    return sorted(results, key=lambda item: item["score"], reverse=True)


def typst_escape(value: str) -> str:
    replacements = {"\\": "\\\\", "#": "\\#", "@": "\\@", "[": "\\[", "]": "\\]", "{": "\\{", "}": "\\}", "*": "\\*", "_": "\\_"}
    return "".join(replacements.get(character, character) for character in value)


def bullet_lines(skills: list[str]) -> str:
    return "\n".join(f"- {typst_escape(skill)}" for skill in skills[:8]) or "- Add verified skills before generating this document."


def candidate_summary(profile: dict, job: dict) -> str:
    skill_list = ", ".join(profile.get("skills", [])[:5])
    base = profile.get("headline") or "Candidate with experience described in the approved profile"
    if skill_list:
        base += f". Relevant verified skills include {skill_list}"
    return f"{base}. This version foregrounds evidence relevant to {job['title']} at {job['company']}."


def cv_typst(profile: dict, job: dict) -> str:
    name = typst_escape(profile.get("name") or "Candidate")
    headline = typst_escape(profile.get("headline") or "Professional profile")
    contact = " · ".join(filter(None, [profile.get("email"), profile.get("phone")])) or "Contact details to be confirmed"
    excerpt = typst_escape(profile.get("source_excerpt") or "Add approved experience evidence before finalizing.")
    summary = typst_escape(candidate_summary(profile, job))
    return f'''#set page(paper: "a4", margin: (x: 18mm, y: 16mm))
#set text(font: "DejaVu Sans", size: 10pt)
#set par(leading: 0.7em)

#align(center)[
  #text(size: 22pt, weight: "bold")[{name}]
  #text(fill: rgb("355f50"))[{headline}]
  {typst_escape(contact)}
]

#line(length: 100%, stroke: 0.8pt + rgb("355f50"))

= Profile for {typst_escape(job['title'])}
{summary}

= Verified skills
{bullet_lines(profile.get('skills', []))}

= Approved career evidence
{excerpt}

= Role being considered
*{typst_escape(job['title'])}* · {typst_escape(job['company'])} · {typst_escape(job['location'])}

{typst_escape(job['summary'])}
'''


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


def generate_documents(profile: dict, job_id: str) -> dict:
    job = next((item for item in JOBS if item["id"] == job_id), None)
    if not job:
        raise ValueError("Choose a job before generating documents.")
    if not profile.get("name"):
        raise ValueError("Review and save the candidate name before generating documents.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = DOCUMENTS / stamp
    folder.mkdir(parents=True, exist_ok=True)
    cv_source = folder / "tailored_cv.typ"
    letter_source = folder / "cover_letter.typ"
    cv_pdf = folder / "tailored_cv.pdf"
    letter_pdf = folder / "cover_letter.pdf"
    cv_source.write_text(cv_typst(profile, job), encoding="utf-8")
    letter_source.write_text(cover_typst(profile, job), encoding="utf-8")
    cv_ok, cv_error = compile_typst(cv_source, cv_pdf)
    letter_ok, letter_error = compile_typst(letter_source, letter_pdf)
    files = [cv_source, letter_source] + ([cv_pdf] if cv_ok else []) + ([letter_pdf] if letter_ok else [])
    return {
        "job": job,
        "compiled": cv_ok and letter_ok,
        "message": "Documents generated locally." if cv_ok and letter_ok else "Typst source generated; PDF compilation needs attention.",
        "errors": [error for error in (cv_error, letter_error) if error],
        "files": [{"name": file.name, "url": "/files/" + file.relative_to(DATA_ROOT).as_posix()} for file in files],
    }


class FieldNotesHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print("[Field Notes] " + format % args)

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES * 2:
            raise ValueError("Request is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            return self.send_json({"typst_available": bool(shutil.which("typst")), "local_only": True})
        if path == "/api/profile":
            return self.send_json(read_profile())
        if path == "/api/jobs":
            return self.send_json({"jobs": job_matches(read_profile()), "source": "Sample roles stored locally"})
        if path.startswith("/files/"):
            requested = (DATA_ROOT / unquote(path.removeprefix("/files/"))).resolve()
            if not requested.is_file() or DATA_ROOT.resolve() not in requested.parents:
                return self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            mime, _ = mimetypes.guess_type(requested.name)
            content = requested.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{requested.name}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            return self.wfile.write(content)
        if path in {"/", "/index.html"}:
            path = "/index.html"
        if path in {"/index.html", "/styles.css", "/app.js"}:
            self.path = path
            return super().do_GET()
        return self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            body = self.json_body()
            if path == "/api/upload":
                name = safe_filename(str(body.get("name", "cv.txt")))
                encoded = str(body.get("content", ""))
                try:
                    content = base64.b64decode(encoded, validate=True)
                except ValueError as error:
                    raise ValueError("The selected file could not be decoded.") from error
                if not content or len(content) > MAX_UPLOAD_BYTES:
                    raise ValueError("Use a non-empty CV smaller than 8 MB.")
                destination = UPLOADS / (datetime.now().strftime("%Y%m%d-%H%M%S-") + name)
                destination.write_bytes(content)
                profile = profile_from_text(extract_text(destination), name)
                return self.send_json({"profile": profile, "message": "CV read locally. Review the extracted profile before generating documents."})
            if path == "/api/profile":
                return self.send_json({"profile": write_profile(body), "message": "Profile saved locally."})
            if path == "/api/generate":
                return self.send_json(generate_documents(read_profile(), str(body.get("job_id", ""))))
            return self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except (ValueError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # pragma: no cover - defensive local-app boundary
            return self.send_json({"error": "Unexpected local error: " + str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)


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
