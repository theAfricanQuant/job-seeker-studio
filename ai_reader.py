"""Jev (TypeSafe System One) labels a CV line by line; ordinary code assembles the profile.

Contract — the safety story this module must keep:

* The model only ever chooses a label from :data:`LABELS` for one line of the
  candidate's *own* text. It cannot write an achievement, a date, an employer, a
  qualification or a language level. Every value in the profile is copied out of the
  CV, and the candidate reviews every field before anything is generated.
* A CV is untrusted input. Its text is only ever sent as ``state`` to be labelled —
  never as instructions — and nothing in it is executed or followed.
* ``classify`` returns a confidence per line. Low confidence is a signal for the
  assembler to re-read a line itself (see :func:`split_heading_line`), not a licence
  to guess.

The module is stdlib-only, like the rest of the studio, and does nothing unless
``FIELD_NOTES_AI`` is switched on and an API key is available.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
DEFAULT_ENV_FILE = "/root/.hermes/.env"
MAX_LINES = 160          # a bound on cost per CV; longer CVs are cut, not paid for
WORKERS = 8
TIMEOUT = 40

LABELS = {
    "person_name": "the CV owner's own name",
    "contact_details": "email, phone, street address, date of birth, nationality",
    "section_heading": "a heading naming a whole CV section (Work Experience, Education, Languages, Skills)",
    "job_title": "the title of a role the person held (Senior Data Scientist, Head of Component)",
    "employer": "the organisation the person worked for",
    "date_range": "a start/end date or range, alone or with little else",
    "bullet_point": "a sentence saying what the person did, usually after a bullet glyph",
    "education_qualification": "a degree or certificate the person earned (MBA, BEng, BSc)",
    "school": "a university, school or college name",
    "language": "a spoken language, with or without a proficiency level",
    "skill": "a technical or professional skill (Python, stakeholder management)",
    "other": "none of the above",
}

HEADING_KEYS = (
    "workexperience", "professionalexperience", "experience", "career", "employmenthistory",
    "education", "languages", "languageskills", "skills", "keyskills", "technicalskills",
    "corecompetencies", "profile", "summary", "professionalprofile", "personaldata",
)

_QUESTION = {
    "line_type": {
        "type": "choice",
        "instructions": "In a CV, what is the line labelled `line`?",
        "criteria": LABELS,
    }
}

_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()
_usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}


def usage() -> dict:
    """Token counters for the current process, so cost can be reported honestly."""
    return dict(_usage)


class Unavailable(RuntimeError):
    """Jev could not be reached or refused the request; callers fall back to the rules."""


def api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    path = os.environ.get("FIELD_NOTES_AI_ENV", DEFAULT_ENV_FILE)
    try:
        for line in open(path, encoding="utf-8", errors="ignore"):
            if line.strip().startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def enabled() -> bool:
    flag = os.environ.get("FIELD_NOTES_AI", "").strip().lower()
    return flag in {"1", "true", "on", "yes"} and bool(api_key())


def _letters(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def split_heading_line(line: str) -> tuple[str, str] | None:
    """A heading that shares its line with content: ('Work Experience', 'Africa Partnerships…').

    Used when the model is unsure, so the split is made by ordinary code rather than guessed.
    """
    words = line.split()
    for count in range(min(4, len(words) - 1), 0, -1):
        if _letters(" ".join(words[:count])) in HEADING_KEYS:
            return " ".join(words[:count]), " ".join(words[count:]).strip(" |│·-")
    return None


def _post(state: dict, key: str, questions: dict | None = None) -> dict:
    body = json.dumps({"state": state, "model": MODEL, "questions": questions or _QUESTION}).encode()
    request = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read())
            _usage["requests"] += 1
            _usage["input_tokens"] += int(payload.get("usage", {}).get("input_tokens", 0) or 0)
            _usage["output_tokens"] += int(payload.get("usage", {}).get("output_tokens", 0) or 0)
            return payload
        except urllib.error.HTTPError as error:
            last = error
            if error.code in (429, 529, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise Unavailable(f"TypeSafe returned {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last = error
            time.sleep(1.0 * (attempt + 1))
    raise Unavailable(f"TypeSafe unreachable: {last}")


def classify_line(text: str, above: str, below: str, key: str) -> tuple[str, float]:
    with _cache_lock:
        hit = _cache.get(text)
    if hit:
        return hit
    answer = _post({"line": text, "line_above": above, "line_below": below}, key)["answers"]["line_type"]
    result = (str(answer["choice"]), float(answer.get("confidence", 0.0)))
    with _cache_lock:
        _cache[text] = result
    return result


def merge_units(lines: list[str]) -> list[str]:
    """Rejoin PDF fragments before anything is labelled.

    A two-column or tightly-set PDF breaks words and sentences across lines
    ("Personal Infor-" / "mation", "Eswa-" / "tini"). Labelling those fragments asks the
    model the wrong question, so a hyphenated word and a lowercase continuation are joined
    back onto the unit above them first. This is ordinary code doing what code is good at;
    the model then labels whole units.
    """
    units: list[str] = []
    for raw in lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if not units:
            units.append(line)
            continue
        previous = units[-1]
        if previous.endswith("-") and not previous.endswith((" -", "–", "—")):
            units[-1] = previous[:-1] + line
        elif line[:1].islower() and not previous.endswith((".", "!", "?", ";", ":")):
            units[-1] = previous + " " + line
        else:
            units.append(line)
    return units


def classify(lines: list[str], key: str | None = None) -> list[dict]:
    """Label every unit. Raises :class:`Unavailable` if too much of it failed."""
    lines = merge_units(lines)
    key = key or api_key()
    if not key:
        raise Unavailable("no TypeSafe API key")
    todo = [index for index, line in enumerate(lines[:MAX_LINES]) if line.strip()]
    if not todo:
        raise Unavailable("nothing to read")
    labelled: dict[int, tuple[str, float]] = {}
    failures: list[str] = []

    def one(index: int) -> None:
        above = lines[index - 1] if index else ""
        below = lines[index + 1] if index + 1 < len(lines) else ""
        try:
            labelled[index] = classify_line(lines[index], above, below, key)
        except Unavailable as error:
            failures.append(str(error))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))
    if not labelled or len(failures) > max(2, len(todo) // 5):
        raise Unavailable(f"{len(failures)} of {len(todo)} lines failed: {failures[:2]}")
    return [{"text": lines[index], "label": labelled[index][0], "confidence": labelled[index][1]}
            for index in sorted(labelled)]


def _ask(instructions: str, criteria: dict, state, key: str | None = None) -> tuple[str, float]:
    """One bounded Choice question. Returns (chosen option key, confidence)."""
    payload = _post(state, key or api_key(), {"line_type": {"type": "choice", "instructions": instructions, "criteria": criteria}})
    answer = payload["answers"]["line_type"]
    return str(answer["choice"]), float(answer.get("confidence", 0.0))


def name_choice(units: list[str], key: str | None = None) -> tuple[str, float]:
    """Which of these candidate lines holds the CV owner's own name?

    Candidates come from code; the model only picks one (or none).
    """
    candidates = [line for line in units[:12] if 3 < len(line) < 70]
    if not candidates:
        return "", 0.0
    criteria = {line: "a line from the top of the CV" for line in candidates}
    criteria["none"] = "none of these is the person's own name"
    return _ask(
        "Which of these lines, taken from the top of a CV, contains the CV owner's own personal name? "
        "Ignore job titles, section headings, addresses, phone numbers, email addresses and employer names.",
        criteria, {"lines": candidates}, key,
    )


def header_order(title: str, employer: str, key: str | None = None) -> tuple[bool, float]:
    """Has the rules reader got a role header the right way round? True means it should swap."""
    answer, confidence = _ask(
        "In a CV, a role is described by two parts. Which part is the job title the person held, "
        "and which is the organisation they worked for?",
        {
            "keep": f"job title: {title!r}; employer: {employer!r}",
            "swap": f"job title: {employer!r}; employer: {title!r}",
        },
        {"part_one": title, "part_two": employer}, key,
    )
    return answer == "swap", confidence


def section_choice(candidates: list[str], key: str | None = None) -> tuple[str, float]:
    """Which candidate line opens the work experience part of this CV?"""
    if not candidates:
        return "", 0.0
    criteria = {line: "a line from this CV" for line in candidates}
    criteria["none"] = "no line here opens the work experience part"
    return _ask(
        "Which of these lines opens the part of the CV that lists the jobs the person has held "
        "(their work experience, employment history or career)? A heading, or a line that begins with a job title.",
        criteria, {"lines": candidates}, key,
    )


def clean_name_line(line: str) -> str:
    """Strip a label the model's line may still carry: 'Name Ene Sandra Macharm' → 'Ene Sandra…'."""
    value = re.sub(r"^\s*(?:full\s+name|name)\b\s*[:\-–]?\s*", "", line, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" ,;:|•·-")


def _plain_language(line: str) -> str:
    text = re.sub(r"^[^:]{0,20}?\b(?:languages?|language skills|language proficiency)\b\s*[:\-–]?\s*", "", line, flags=re.I)
    text = text.strip(" •·|,;-–—")
    if not text:
        return ""
    text = re.sub(r"\s*\(([^)]*)\)\s*", lambda m: " — " + m.group(1).strip(), text, count=1)
    text = re.sub(r"^\s*([A-Za-zÀ-ÿ ]{2,25}?)\s*[:—–]\s*(.+)$", r"\1 — \2", text)
    return re.sub(r"\s+", " ", text).strip()[:60]


def _split_skills(line: str) -> list[str]:
    return [piece.strip(" •·|,;") for piece in re.split(r"[,;·|]", line) if 2 < len(piece.strip()) <= 70]


def read_profile(lines: list[str], language_formatter=None, key: str | None = None) -> dict:
    """Label the CV and assemble the profile fields. Raises :class:`Unavailable` on failure."""
    items = classify(lines, key=key)
    fmt = language_formatter or _plain_language

    name_line = ""
    headline = ""
    header_zone = True
    current: dict | None = None
    experiences: list[dict] = []
    education: list[dict] = []
    languages: list[str] = []
    skills: list[str] = []

    def close() -> None:
        nonlocal current
        if current and (current["title"] or current["subtitle"] or current["dates"] or current["bullets"]):
            experiences.append(current)
        current = None

    def start(**fields) -> dict:
        return {"title": "", "subtitle": "", "dates": "", "location": "", "bullets": [], **fields}

    for item in items:
        line, label, confidence = item["text"].strip(), item["label"], item["confidence"]
        if not line:
            continue
        if label in {"employer", "date_range"}:
            header_zone = False
        if label == "person_name":
            name_line = name_line or line
        elif label == "job_title":
            title = line
            if confidence < 0.6:
                # Unsure: this may be a section heading glued to a title. Split it in code.
                split = split_heading_line(line)
                if split and split[1]:
                    title = split[1]
            if header_zone:
                headline = headline or title         # the title under the name, not a role
                continue
            if current is None:
                current = start(title=title)
            elif not current["title"]:
                current["title"] = title
            elif current["dates"] or current["bullets"]:
                close()
                current = start(title=title)
            else:
                current["title"] = (current["title"] + " " + title).strip()   # a wrapped title
        elif label == "employer":
            if current is None:
                current = start(subtitle=line)
            elif not current["subtitle"]:
                current["subtitle"] = line
            elif current["dates"] or current["bullets"]:
                close()
                current = start(subtitle=line)
            else:
                current["subtitle"] = (current["subtitle"] + " " + line).strip()
        elif label == "date_range":
            if current is None:
                current = start(dates=line)
            elif not current["dates"]:
                current["dates"] = line
            else:
                close()
                current = start(dates=line)
        elif label == "bullet_point":
            if current is None:
                current = start()
            current["bullets"].append(line)
        elif label == "education_qualification":
            education.append({"title": line, "subtitle": "", "dates": "", "location": "", "bullets": []})
        elif label == "school":
            if education and not education[-1]["subtitle"]:
                education[-1]["subtitle"] = line
            else:
                education.append({"title": "", "subtitle": line, "dates": "", "location": "", "bullets": []})
        elif label == "language":
            value = fmt(line)
            if value and value.lower() not in {item.lower() for item in languages}:
                languages.append(value)
        elif label == "skill":
            for value in _split_skills(line):
                if value.lower() not in {item.lower() for item in skills}:
                    skills.append(value)
    close()

    if not headline:
        headline = experiences[0]["title"] if experiences else ""
    if not any((name_line, headline, experiences, education, languages, skills)):
        raise Unavailable("the model returned nothing usable")
    return {
        "name_line": name_line,
        "headline": headline,
        "experiences": experiences[:8],
        "education": education[:6],
        "languages": languages[:8],
        "skills": skills[:24],
    }