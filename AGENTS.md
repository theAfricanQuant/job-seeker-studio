# Field Notes — agent guide

Field Notes is a local-first application assistant for an individual job seeker. It turns a reviewed CV profile and a chosen job into editable Typst source plus a CV and cover-letter PDF.

## Read the right brief first

- For product, privacy, or candidate-safety changes, read PRODUCT.md.
- For runtime, API, file, or Typst-generator changes, read IMPLEMENTATION.md.
- For job-provider, LLM, authentication, or production-scaling work, read ROADMAP.md.

## Non-negotiable product boundaries

1. Typst is the document engine. Preserve editable .typ output; do not introduce LaTeX.
2. Candidate evidence is reviewed before it is used. Tailoring reprioritizes facts; it never invents experience or qualifications.
3. Keep the app local-first. CVs and generated documents remain in local_data/, which is ignored by Git.
4. The current roles are local samples. Treat a real job-data source as a deliberate integration with explicit permission and terms review.
5. The app stops at human-approved documents. Any future application submission requires an explicit, per-application human confirmation.

## Working loop

1. Inspect the relevant brief above and the files touched by the request.
2. Make the smallest coherent change across UI, API, and verification.
3. Preserve the plain-Python, no-runtime-dependency setup unless a new dependency clearly earns its operational cost.
4. Run the checks below. For generator changes, run the smoke test and inspect failures rather than bypassing compilation.
5. Update the relevant brief only when a product decision, architecture boundary, or roadmap priority changed.

## Run and verify

    python3 app.py
    python3 -m py_compile app.py
    node --check app.js
    python3 tests/smoke_test.py

The server listens only on 127.0.0.1:8765. Open that address in a browser after starting it.

## Source map

- app.py — local HTTP server, CV text extraction, profile storage, job scoring, Typst generation, and PDF compilation.
- index.html, styles.css, app.js — browser interface; no framework or build step.
- local_data/ — private runtime data, created automatically; never commit it.
- tests/smoke_test.py — validates both Typst documents compile and have readable PDF text.
