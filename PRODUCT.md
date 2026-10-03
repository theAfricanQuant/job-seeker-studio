# Product brief

## The job

Help an individual job seeker prepare a more relevant application without sacrificing accuracy, privacy, or human judgement.

## Current user flow

1. The app creates a private workspace for the visitor's browser—no email sign-in is required.
2. The user chooses a CV file; the app reads its text and creates a starter profile, including any email, phone number, and labelled address it finds.
3. The user reviews and edits their name, contact details, headline, skills, and career evidence.
4. The app derives a narrow search term from the approved profile and scores attributable Jobicy and FreeHire listings. It falls back to clearly labelled demo roles only when live providers are unavailable.
5. The user chooses one role.
6. The app renders the chosen CV Studio design, an ATS Plain companion CV, and a cover-letter draft as PDFs, plus editable Word versions of the tailored CV and cover letter.
7. The user reviews the documents and handles any application outside the app.

## Product truths

- A score is a decision aid, not an assessment of employability or hiring likelihood.
- Tailored material must remain traceable to candidate-approved evidence. Missing evidence is a prompt to edit, not a gap to fill with plausible prose.
- A CV can contain sensitive personal information. Files, profiles, job caches, and generated documents are restricted to an unguessable browser workspace cookie. Clearing browser data creates a new workspace and prevents recovery in this pilot. A job provider receives only a narrow search term; no model call or submission is implied.
- Current Jobicy and FreeHire listings are shown with their provider and original vacancy link. Their availability and coverage are not a claim of complete worldwide or African market coverage.
- Downloading an application package is safe; submitting an application is a separate, human-controlled action.

## Acceptance criteria for user-facing changes

- The next action is clear to a non-technical job seeker.
- Any use of candidate information is visible and understandable.
- A candidate can edit the exact facts that influence scoring and document output.
- Generated documents remain available as PDF and editable DOCX. Typst is an internal engine, not a candidate-facing format.
