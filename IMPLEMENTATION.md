# Implementation reference

## Architecture

The app has no third-party Python packages and no build system.

    Browser UI: index.html + app.js
                 ↕ JSON over localhost
    app.py: ThreadingHTTPServer on 127.0.0.1:8765
      - PDF extraction through pdftotext
      - DOCX extraction through standard-library ZIP/XML
      - profile and uploads stored in local_data/
      - keyword-only sample-job scoring
      - Typst source generation and local PDF compilation

app.py intentionally binds to loopback only. It serves the browser UI, the JSON API, and generated files below local_data/.

## API contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/status | Reports whether Typst is available locally. |
| GET | /api/profile | Returns the saved candidate profile. |
| POST | /api/upload | Accepts a filename and base64 file bytes; extracts a starter profile. |
| POST | /api/profile | Saves reviewed candidate facts. |
| GET | /api/jobs | Scores the sample jobs against saved profile content. |
| POST | /api/generate | Creates Typst sources and PDFs for the selected job. |
| GET | /files/... | Downloads a generated or source file strictly under local_data/. |

## Data and generated files

    local_data/
      uploads/      source CV copies
      profile.json  approved candidate facts
      documents/
        YYYYMMDD-HHMMSS/
          tailored_cv.typ
          tailored_cv.pdf
          cover_letter.typ
          cover_letter.pdf

The application creates source files even if PDF compilation fails, then returns compiler errors to the UI. Preserve this recovery path.

## Typst rules

- typst_escape() must cover user-controlled content before interpolation. Keep it updated for any new fields.
- Use installed local fonts and no remote Typst package import, so generation works offline.
- Verify a document change with python3 tests/smoke_test.py; it compiles both sources and checks PDF text extraction.
- Improve visual design through Typst source while retaining selectable, sane PDF text for applicant-tracking systems.
