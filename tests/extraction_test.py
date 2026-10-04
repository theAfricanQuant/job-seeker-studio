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
]

NO_NAME_CASES = [
    ("headings only", "Curriculum Vitae\nProfessional Summary\nExperience\nAnalyst | Acme | 2020 - 2023"),
    ("job title only", "Senior Data Scientist\nFrankfurt, Germany\n\nExperience\nAnalyst | Acme | 2020 - 2023"),
]


def load_app():
    spec = importlib.util.spec_from_file_location("field_notes_extraction", ROOT / "app.py")
    assert spec is not None
    app = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(app)
    return app


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

    samples = sorted((ROOT / "template_samples" / "pdfs").glob("*.pdf"))
    for sample in samples:
        name = app.parsed_name(app.cv_lines(app.extract_text(sample)))
        if not name:
            failures.append(f"{sample.name}: no name found in the rendered sample CV")

    if failures:
        print("Field Notes extraction test FAILED")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print(f"Field Notes extraction test passed: {len(TEXT_CASES)} text shapes, {len(NO_NAME_CASES)} refusals, {len(samples)} rendered sample PDFs.")


if __name__ == "__main__":
    main()