"""End-to-end local verification for Field Notes document generation."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import zipfile
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
        assert not any(item["name"].endswith(".typ") for item in result["files"])
        pdfs = [item for item in result["files"] if item["name"].endswith(".pdf")]
        assert {item["name"] for item in pdfs} == {"tailored_cv_meridian.pdf", "tailored_cv_ats_plain.pdf", "cover_letter.pdf"}
        docxs = [item for item in result["files"] if item["name"].endswith(".docx")]
        assert {item["name"] for item in docxs} == {"tailored_cv_editable.docx", "cover_letter_editable.docx"}
        for item in docxs:
            docx = app.DATA_ROOT / item["url"].removeprefix("/files/")
            with zipfile.ZipFile(docx) as archive:
                content = archive.read("word/document.xml").decode("utf-8")
            assert "Taylor" in content and "Example" in content, (item["name"], content[:500])
        for item in pdfs:
            pdf = app.DATA_ROOT / item["url"].removeprefix("/files/")
            text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
            assert "Taylor" in text and "Example" in text, (item["name"], text[:500])
        assert "Built Python research tools" in subprocess.run(["pdftotext", str(app.DATA_ROOT / next(item["url"].removeprefix("/files/") for item in result["files"] if item["name"] == "tailored_cv_meridian.pdf")), "-"], check=True, capture_output=True, text=True).stdout
        base_result = app.generate_cv(
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
                    "bullets": ["Built Python research tools for financial time-series analysis."],
                }],
            }
        )
        assert base_result["compiled"], base_result["errors"]
        assert base_result["primary_cv"] == "cv_meridian.pdf"
        assert {item["name"] for item in base_result["files"]} == {"cv_meridian.pdf", "cv_editable.docx"}
        base_pdf = app.DATA_ROOT / next(item["url"].removeprefix("/files/") for item in base_result["files"] if item["name"] == "cv_meridian.pdf")
        base_text = subprocess.run(["pdftotext", str(base_pdf), "-"], check=True, capture_output=True, text=True).stdout
        assert "Taylor" in base_text and "Built Python research tools" in base_text
        print("Field Notes smoke test passed: PDFs compiled and editable DOCX CV and cover letter were created.")


if __name__ == "__main__":
    main()
