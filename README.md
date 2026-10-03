# Field Notes

Field Notes is a local-first job-application workspace. It extracts a reviewable candidate record from a CV, shows attributable current roles, and generates evidence-based PDF and editable Word application files for a role the candidate chooses.

## What it does today

- Creates a private browser workspace automatically—no sign-in before upload. The browser holds the random workspace key; clearing browser data starts a new workspace.
- Reads PDF, DOCX, TXT, and Markdown CVs inside that workspace; the candidate reviews every extracted fact.
- Finds current remote roles through Jobicy and FreeHire when available, with source attribution and the original vacancy link. Only a narrow search term derived from the reviewed profile is sent to those providers; the CV itself stays inside the workspace.
- Lets the candidate inspect 13 real Typst CV Studio designs before choosing one.
- Generates the selected designed CV, a companion `ATS Plain` CV for portals, plus editable Word versions of the tailored CV and cover letter. Typst remains an internal document engine and is never offered to candidates.
- Tailors by reordering approved evidence against a selected listing. It does not invent achievements, qualifications, or language ability.

It is ready to test locally, not yet ready to expose publicly. Applications are always submitted manually by the candidate.

## Run locally

    uv run python app.py

Open http://127.0.0.1:8765.

The app needs uv, Typst to compile PDFs, and pdftotext to read PDF CVs. It has no Python package installation step. The bundled CV Studio runtime includes adapters and vendored template packages; see `THIRD_PARTY_NOTICES.md`.

## Verification

    uv run python -m py_compile app.py
    uv run node --check app.js
    uv run python tests/workspace_test.py
    uv run python tests/smoke_test.py

## Handoff

Start with AGENTS.md. It directs future agents to the product, implementation, and roadmap documents relevant to their task.
