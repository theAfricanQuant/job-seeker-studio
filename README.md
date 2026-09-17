# Field Notes

Field Notes is a local-first job-application workspace. It reads a candidate-approved CV profile, scores sample roles, and generates editable Typst source plus local PDF CV and cover-letter drafts.

## Run locally

    python3 app.py

Open http://127.0.0.1:8765.

The app needs typst to compile PDFs and pdftotext to read PDF CVs. It has no Python package installation step.

## Verification

    python3 -m py_compile app.py
    node --check app.js
    python3 tests/smoke_test.py

## Handoff

Start with AGENTS.md. It directs future agents to the product, implementation, and roadmap documents relevant to their task.
