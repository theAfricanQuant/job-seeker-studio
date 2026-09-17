# Product brief

## The job

Help an individual job seeker prepare a more relevant application without sacrificing accuracy, privacy, or human judgement.

## Current user flow

1. The user chooses a CV file.
2. The app reads its text locally and creates a starter profile.
3. The user reviews and edits their name, contact details, headline, skills, and career evidence.
4. The app scores locally stored sample roles against that approved profile.
5. The user chooses one role.
6. The app creates editable Typst CV and cover-letter sources, then local PDFs.
7. The user reviews the documents and handles any application outside the app.

## Product truths

- A score is a decision aid, not an assessment of employability or hiring likelihood.
- Tailored material must remain traceable to candidate-approved evidence. Missing evidence is a prompt to edit, not a gap to fill with plausible prose.
- A CV can contain sensitive personal information. The user controls it: no external upload, model call, or submission is implied by the current product.
- Real job discovery is not implemented. The visible roles are clear sample data, so the interface never implies they are live vacancies.
- Downloading an application package is safe; submitting an application is a separate, human-controlled action.

## Acceptance criteria for user-facing changes

- The next action is clear to a non-technical job seeker.
- Any use of candidate information is visible and understandable.
- A candidate can edit the exact facts that influence scoring and document output.
- Generated documents remain available as both .typ source and PDF.
