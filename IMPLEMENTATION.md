# Implementation reference

## Architecture

The app has no third-party Python packages and no build system.

    Browser UI: index.html + app.js
                 ↕ JSON + opaque browser-workspace cookie over localhost
    app.py: ThreadingHTTPServer on 127.0.0.1:8765
      - PDF extraction through pdftotext
      - DOCX extraction through standard-library ZIP/XML
      - hashed anonymous browser workspaces under local_data/workspaces/
      - attributable Jobicy + FreeHire retrieval with demo-role fallback
      - reviewed structured candidate records and local evidence scoring
      - internal Typst CV Studio rendering: selected design + ATS Plain companion PDF
      - dependency-free OOXML writing: editable CV and cover-letter DOCX files

app.py intentionally binds to loopback only. It serves the browser UI, the JSON API, and files only below the current browser's unguessable workspace. No email verification is required; deleting browser data makes the pilot workspace unrecoverable.

## API contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/status | Reports whether Typst is available locally. |
| GET | /api/profile | Creates or returns this browser's candidate profile and workspace cookie. |
| POST | /api/upload | Accepts a filename and base64 file bytes; extracts a starter profile. |
| POST | /api/profile | Saves reviewed candidate facts. |
| GET | /api/jobs | Retrieves attributable live roles when providers respond, then scores them against saved profile content. |
| POST | /api/generate | Creates selected and ATS PDF CVs, a PDF cover letter, and editable DOCX CV/cover-letter files. |
| GET | /files/... | Downloads only generated PDF or DOCX files strictly under the signed-in workspace. |

## Data and generated files

    local_data/
      workspaces/
        <token-sha256>/  stable opaque directory name
          uploads/       source CV copies
          profile.json   approved candidate facts; email is session-owned
          documents/
            YYYYMMDD-HHMMSS/
              tailored_cv_<chosen-template>.pdf
              tailored_cv_ats_plain.pdf
              cover_letter.pdf
              tailored_cv_editable.docx
              cover_letter_editable.docx

The application creates editable Word documents even if PDF compilation fails, then returns compiler errors to the UI. Typst sources stay inside the private render folder and are not offered through the file route.

## Document rules

- Candidate evidence must be structured and reviewable before generation. Raw extracted text is reference material, never document content.
- All profile, job-cache, upload, generation, and file-download operations use the current browser's opaque workspace cookie. A submitted profile email is candidate data, never an access credential.
- Each generation copies the CV Studio runtime into its own local document folder, so a candidate's data never becomes shared template data.
- The selected adapter must compile by name; never substitute a different template silently. The ATS Plain adapter is generated as a separate portal-safe companion.
- The selected PDF reflects the chosen CV Studio design. DOCX is a clean, content-first editable version, so a candidate can make final changes in Word or LibreOffice without dealing with a source language.
- Verify a document change with `uv run python tests/smoke_test.py`; it proves an actual named Studio adapter, ATS Plain, and the cover letter compile and that editable DOCX outputs are created.
