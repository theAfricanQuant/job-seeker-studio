# Field Notes — agent guide

Field Notes is a browser-workspace application assistant for an individual job seeker. It turns a reviewed CV profile and a chosen job into PDFs plus editable Word CV and cover-letter files.

## Read the right brief first

- For product, privacy, or candidate-safety changes, read PRODUCT.md.
- For runtime, API, file, or Typst-generator changes, read IMPLEMENTATION.md.
- For job-provider, LLM, authentication, or production-scaling work, read ROADMAP.md.

## Non-negotiable product boundaries

1. Typst is the internal PDF engine. Preserve its selected-template rendering, but do not expose `.typ` files to candidates; their editable format is DOCX. Do not introduce LaTeX.
2. Candidate evidence is reviewed before it is used. Tailoring reprioritizes facts; it never invents experience or qualifications.
3. Keep candidate data private. CVs and generated documents remain in an opaque browser-workspace directory under local_data/, which is ignored by Git. Do not weaken the cookie-gated file routes.
4. Current roles come from Jobicy and FreeHire when available, otherwise clearly labelled demos. Treat every additional job source as a deliberate integration with explicit permission and terms review.
5. The app stops at human-approved documents. Any future application submission requires an explicit, per-application human confirmation.

## Working loop

1. Inspect the relevant brief above and the files touched by the request.
2. Make the smallest coherent change across UI, API, and verification.
3. Use uv for every Python command and dependency change. Preserve the plain-Python, no-runtime-dependency setup unless a new dependency clearly earns its operational cost.
4. Run the checks below. For generator changes, run the smoke test and inspect failures rather than bypassing compilation.
5. Update the relevant brief only when a product decision, architecture boundary, or roadmap priority changed.

## Run and verify

    uv run python app.py
    uv run python -m py_compile app.py
    uv run node --check app.js
    uv run python tests/workspace_test.py
    uv run python tests/smoke_test.py

The server listens only on 127.0.0.1:8765. Open that address in a browser after starting it.

## Source map

- app.py — local HTTP server, browser-workspace boundary, CV text extraction, profile storage, job scoring, internal Typst/PDF generation, and editable DOCX generation.
- index.html, styles.css, app.js — browser interface; no framework or build step.
- local_data/ — private runtime data, created automatically; never commit it.
- tests/workspace_test.py — verifies browser-cookie workspace creation and isolation.
- tests/smoke_test.py — validates PDF compilation and editable DOCX output.
