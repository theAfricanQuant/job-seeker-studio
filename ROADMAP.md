# Roadmap

## Next: strengthen the local workflow

1. Add individual accomplishments, links, certifications, and an explicit per-signal include/exclude control to the reviewed candidate record.
2. Add an explicit page-length check and rendered-page review to every generated template.
3. Add document history, comparison, and visible deletion of uploaded CVs/documents.
4. Add document history, compare revisions, and make deletion of uploaded CVs/documents visible in the interface.

## Add real job discovery only with an approved source

The local pilot currently uses Jobicy and FreeHire with source attribution and original application links. Before each new source, capture its allowed use, rate limits, data retention, attribution, and costs in a provider-specific document. Avoid treating public web pages as permission to build a commercial scraper.

The connector contract should return normalized fields:

    id, title, company, location, posted_at, description, apply_url, source

Keep connectors separate from the local scoring and document pipeline. The app must still make it clear when an item is a real vacancy, an expired listing, or a sample.

## Add AI drafting only with an explicit product decision

The intended hosted model provider is Nous Research. Before its API sees candidate data:

1. Obtain clear user consent and identify the provider.
2. Limit the payload to reviewed profile facts and the chosen job description.
3. Make the model output an editable draft with source evidence, never a final truth.
4. Add retention/deletion policy, cost limits, and prompt-injection handling for job descriptions.

## Production readiness

Authentication, encrypted storage, audit events, rate limits, backups, and multi-user access controls are a separate milestone. Preserve the current human-review-before-submit boundary.
