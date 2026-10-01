# Implementation reference

## Architecture

The app has no third-party Python packages and no build system.

    Browser UI: index.html + app.js
                 ↕ JSON over localhost
    app.py: ThreadingHTTPServer on 127.0.0.1:8765
      - PDF extraction through pdftotext
      - DOCX extraction through standard-library ZIP/XML
      - profile and uploads stored in local_data/
      - attributable Jobicy + FreeHire retrieval with demo-role fallback
      - reviewed structured candidate records and local evidence scoring
      - Typst CV Studio rendering: selected design + ATS Plain companion PDF

app.py intentionally binds to loopback only. It serves the browser UI, the JSON API, and generated files below local_data/.

## API contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/status | Reports whether Typst is available locally. |
| GET | /api/profile | Returns the saved candidate profile. |
| POST | /api/upload | Accepts a filename and base64 file bytes; extracts a starter profile. |
| POST | /api/profile | Saves reviewed candidate facts. |
| GET | /api/jobs | Retrieves attributable live roles when providers respond, then scores them against saved profile content. |
| POST | /api/generate | Creates Typst sources and PDFs for the selected job. |
| GET | /files/... | Downloads a generated or source file strictly under local_data/. |

## Data and generated files

    local_data/
      uploads/      source CV copies
      profile.json  approved candidate facts
      documents/
        YYYYMMDD-HHMMSS/
          cv-content.typ
          tailored_cv_<chosen-template>.typ
          tailored_cv_<chosen-template>.pdf
          tailored_cv_ats_plain.typ
          tailored_cv_ats_plain.pdf
          cover_letter.typ
          cover_letter.pdf

The application creates source files even if PDF compilation fails, then returns compiler errors to the UI. Preserve this recovery path.

## Typst rules

- Candidate evidence must be structured and reviewable before generation. Raw extracted text is reference material, never document content.
- Each generation copies the CV Studio runtime into its own local document folder, so a candidate's data never becomes shared template data.
- The selected adapter must compile by name; never substitute a different template silently. The ATS Plain adapter is generated as a separate portal-safe companion.
- Verify a document change with `uv run python tests/smoke_test.py`; it proves an actual named Studio adapter, ATS Plain, and the cover letter compile and expose readable text.
