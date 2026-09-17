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
                "headline": "Quantitative analyst",
                "skills": ["Python", "Time series", "Risk modelling"],
                "source_excerpt": "Built Python research tools for financial time-series analysis and communicated results to stakeholders.",
            },
            "nordbeam-quant",
        )
        assert result["compiled"], result["errors"]
        pdfs = [item for item in result["files"] if item["name"].endswith(".pdf")]
        assert len(pdfs) == 2
        for item in pdfs:
            pdf = app.DATA_ROOT / item["url"].removeprefix("/files/")
            text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
            assert "Taylor Example" in text
        print("Field Notes smoke test passed: Typst CV and cover letter compiled with readable text.")


if __name__ == "__main__":
    main()
