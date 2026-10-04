"""Regression checks for reading a candidate's name and location out of a CV.

A CV that simply puts the name on the first line is the common case and must work;
a CV that never states a name must not have one invented for it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_CASES = [
    ("name on the first line", "Priya Raman\npriya@example.com\nFrankfurt, Germany\n\nWork Experience\nAnalyst | Acme | 2020 - 2023", "Priya Raman", "Frankfurt, Germany"),
    ("name in capitals", "PRIYA RAMAN\nFrankfurt, Germany\n\nWork Experience\nAnalyst | Acme | 2020 - 2023", "PRIYA RAMAN", "Frankfurt, Germany"),
    ("name after a CV heading", "Curriculum Vitae\nPriya Raman\nOberursel, Germany\n", "Priya Raman", "Oberursel, Germany"),
    ("name labelled", "Name: Priya Raman\nLocation: Frankfurt, Germany\n", "Priya Raman", "Frankfurt, Germany"),
    ("job title before the name", "Senior Data Scientist\nPriya Raman\nFrankfurt, Germany\n", "Priya Raman", "Frankfurt, Germany"),
    ("name with credentials", "Priya Raman, MSc\nFrankfurt, Germany\n", "Priya Raman", "Frankfurt, Germany"),
    ("name with particles", "Maria de la Cruz Fernandez\nMadrid, Spain\n", "Maria de la Cruz Fernandez", "Madrid, Spain"),
    ("three-part name", "Ene Sandra Macharm\nOberursel, Germany\n", "Ene Sandra Macharm", "Oberursel, Germany"),
    ("city and country", "Tiku Allu\ntiku@example.com | +234 803 555 0199\nAbuja, Nigeria\n", "Tiku Allu", "Abuja, Nigeria"),
    (
        "personal data block with a title after the comma",
        "Personal Data:\nName: Ricky Sambo Macharm, PEM™\nDate of Birth: 27/10/1974\nPlace of Birth: Jos, Nigeria\nNationality: Nigerian\nAddress: Works and maintenance, National Veterinary Research Institute, Vom, Plateau State.\nE-Mail: ricky.macharm@gmail.com\nMobile #: +2347055743990; +2348033866978\n",
        "Ricky Sambo Macharm",
        "Vom, Plateau State",
    ),
    (
        "personal data block, title without a comma",
        "Name: Ricky Sambo Macharm PEM\nNationality: Nigerian\nAddress: Vom, Plateau State\nMobile #: +2347055743990\n",
        "Ricky Sambo Macharm",
        "Vom, Plateau State",
    ),
    (
        # Word exports put a zero-width space inside the label; it must not reach the name.
        "labelled name carrying a zero-width space",
        "Personal Data:\nName:\u200b Priya Raman, PhD\nDate of Birth: 01/01/1985\nAddress: 12 Main Street, Oberursel,\n        Germany\n",
        "Priya Raman",
        "Oberursel, Germany",
    ),
    (
        # A postal address that wraps must keep its last two parts, not its first two.
        "wrapped postal address",
        "Priya Raman\nAddress: Works and maintenance, Federal Research Institute,\n        Zaria, Kaduna State.\n",
        "Priya Raman",
        "Zaria, Kaduna State",
    ),
]

NO_NAME_CASES = [
    ("headings only", "Curriculum Vitae\nProfessional Summary\nExperience\nAnalyst | Acme | 2020 - 2023"),
    ("job title only", "Senior Data Scientist\nFrankfurt, Germany\n\nExperience\nAnalyst | Acme | 2020 - 2023"),
]

EXPERIENCE_CASES = [
    (
        'a role dated "2007-Date", bullet glyphs, and the country on its own line',
        "Priya Raman\n\nWork Experience\n2007-Date   SENIOR Engineer: Acme Works, Frankfurt,\n            Germany\n            \u25cf Maintenance of laboratory equipment;\n            \u25cf Calibration of new and old equipment;\n2001-2005   Other Company, Berlin\n            \u25cf Publishing quarterly newsletters;\n",
        "SENIOR Engineer",
        "2007-Date",
        "Acme Works",
        2,
    ),
]

LANGUAGE_CASES = [
    (
        "a language table",
        "Priya Raman\n\nLANGUAGE PROFICIENCY\nLANGUAGE   WRITTEN   SPOKEN   READING   LISTENING\nENGLISH    excellent excellent excellent excellent\nHAUSA      average   average   average   above average\n\nHOBBIES\n\u25cf Reading\n",
        ["ENGLISH — excellent", "HAUSA — average"],
    ),
    (
        "languages as a list",
        "Priya Raman\n\nLanguages: English (fluent), German (basic)\n",
        ["English — fluent", "German — basic"],
    ),
]


def load_app():
    spec = importlib.util.spec_from_file_location("field_notes_extraction", ROOT / "app.py")
    assert spec is not None
    app = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(app)
    return app


def fixture_pdfs(app) -> list[Path]:
    """Rendered fixtures; recompile any whose .typ source is newer than its .pdf."""
    rendered: list[Path] = []
    for source in sorted((ROOT / "tests" / "fixtures").glob("*.typ")):
        output = source.with_suffix(".pdf")
        if not output.exists() or output.stat().st_mtime < source.stat().st_mtime:
            ok, error = app.compile_typst(source, output)
            if not ok:
                raise SystemExit(f"could not render {source.name}: {error}")
        rendered.append(output)
    return rendered


def main() -> None:
    app = load_app()
    failures: list[str] = []

    for label, body, expected_name, expected_location in TEXT_CASES:
        lines = app.cv_lines(body)
        name, location = app.parsed_name(lines), app.parsed_location(lines)
        if name != expected_name or location != expected_location:
            failures.append(f"{label}: got name={name!r} location={location!r}, expected {expected_name!r} / {expected_location!r}")

    for label, body in NO_NAME_CASES:
        name = app.parsed_name(app.cv_lines(body))
        if name:
            failures.append(f"{label}: invented the name {name!r}")

    for label, body, expected_title, expected_dates, expected_org, expected_bullets in EXPERIENCE_CASES:
        records = app.parse_work_experience(app.cv_lines(body))
        if not records:
            failures.append(f"{label}: no role was read")
            continue
        first = records[0]
        if first["title"] != expected_title or first["dates"] != expected_dates or first["subtitle"] != expected_org or len(first["bullets"]) != expected_bullets:
            failures.append(
                f"{label}: got {first['title']!r} / {first['dates']!r} / {first['subtitle']!r} / "
                f"{len(first['bullets'])} bullets, expected {expected_title!r} / {expected_dates!r} / {expected_org!r} / {expected_bullets}"
            )

    for label, body, expected in LANGUAGE_CASES:
        got = app.parse_languages(app.cv_lines(body))
        if got != expected:
            failures.append(f"{label}: got {got!r}, expected {expected!r}")

    samples = sorted((ROOT / "template_samples" / "pdfs").glob("*.pdf"))
    for sample in samples:
        name = app.parsed_name(app.cv_lines(app.extract_text(sample)))
        if not name:
            failures.append(f"{sample.name}: no name found in the rendered sample CV")

    fixtures = fixture_pdfs(app)
    for fixture in fixtures:
        text = app.extract_text(fixture)
        if "\u200b" in text:
            failures.append(f"{fixture.name}: the reader kept a zero-width space")
        profile = app.profile_from_text(text, fixture.name, "fixture-token")
        for field in ("name", "location", "headline"):
            if not profile[field]:
                failures.append(f"{fixture.name}: no {field} read from the fixture CV")
        if not profile["experiences"] or not profile["education"] or not profile["languages"]:
            failures.append(f"{fixture.name}: roles, education or languages came back empty")

    if failures:
        print("Field Notes extraction test FAILED")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print(
        f"Field Notes extraction test passed: {len(TEXT_CASES)} text shapes, {len(NO_NAME_CASES)} refusals, "
        f"{len(EXPERIENCE_CASES)} role shapes, {len(LANGUAGE_CASES)} language shapes, "
        f"{len(samples)} rendered sample PDFs, {len(fixtures)} fixtures."
    )


if __name__ == "__main__":
    main()