"""End-to-end local verification for Field Notes document generation."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_app():
    spec = importlib.util.spec_from_file_location("field_notes", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(app)
    return app


def main() -> None:
    if not shutil.which("typst"):
        raise SystemExit("Typst is required for this smoke test.")
    app = load_app()
    with tempfile.TemporaryDirectory(prefix="field-notes-smoke-") as temporary:
        app.DATA_ROOT = Path(temporary) / "local_data"
        app.DOCUMENTS = app.DATA_ROOT / "documents"
        app.DOCUMENTS.mkdir(parents=True)
        result = app.generate_documents(
            {
                "name": "Taylor Example",
                "email": "taylor@example.com",
                "phone": "+49 123 456 789",
                "location": "Berlin, Germany",
                "headline": "Quantitative analyst",
                "skills": ["Python", "Time series", "Risk modelling"],
                "cv_template": "meridian",
                "experiences": [{
                    "title": "Quantitative Analyst", "subtitle": "Example Capital", "dates": "2021 – Present", "location": "Berlin",
                    "bullets": [
                        "Built Python research tools for financial time-series analysis.",
                        "Communicated risk-model findings to investment stakeholders.",
                    ],
                }],
                "education": [{"title": "MSc Financial Engineering", "subtitle": "Example University", "dates": "2018 – 2020", "location": "Berlin", "bullets": []}],
            },
            "nordbeam-quant",
        )
        assert result["compiled"], result["errors"]
        assert result["template"] == "meridian"
        assert result["primary_cv"] == "tailored_cv_meridian.pdf"
        assert "Meridian" not in result["tailoring"]["foregrounded_evidence"]  # evidence labels, never template names
        pdfs = [item for item in result["files"] if item["name"].endswith(".pdf")]
        assert {item["name"] for item in pdfs} == {"tailored_cv_meridian.pdf", "tailored_cv_ats_plain.pdf", "cover_letter.pdf"}
        selected_adapter = app.DATA_ROOT / next(item["url"].removeprefix("/files/") for item in result["files"] if item["name"] == "tailored_cv_meridian.typ")
        assert 'meridian-cv' in selected_adapter.read_text(encoding="utf-8")
        for item in pdfs:
            pdf = app.DATA_ROOT / item["url"].removeprefix("/files/")
            text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
            assert "Taylor" in text and "Example" in text, (item["name"], text[:500])
        assert "Built Python research tools" in subprocess.run(["pdftotext", str(app.DATA_ROOT / next(item["url"].removeprefix("/files/") for item in result["files"] if item["name"] == "tailored_cv_meridian.pdf")), "-"], check=True, capture_output=True, text=True).stdout
        print("Field Notes smoke test passed: Typst CV and cover letter compiled with readable text.")


if __name__ == "__main__":
    main()
