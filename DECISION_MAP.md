# Global Job Seeker Studio — Decision Map

This map guides the conversion of Field Notes into a public, free CV-to-job-
matching product. It combines the selected-CV workflow from Typst CV Studio
with the job discovery and application workflow of AI Job Search. It is a
planning record only; no public data, AI provider, or application submission
integration is approved by this map.

## #1: Audience and market strategy

Blocked by: none
Type: Grilling

### Question

Should the product launch for one country, Africa, or a global audience?

### Answer

The product is globally accessible and Africa-first: Nigerian and African job
seekers are the primary audience, with immigrants seeking opportunities in
Europe and the Americas also in scope. The launch interface is English; French
is the next supported interface language. The CV/profile engine is global. Job
discovery will be launched source by source and region by region, so the
interface must disclose its actual market coverage rather than imply worldwide
completeness.

## #2: Permitted job-data sources

Blocked by: #1
Type: Research

### Question

Which job sources can provide current, lawful, attributable listings for the
first Africa-first release and the first Europe/Americas expansion?

### Answer

For the local MVP, Jobicy may provide attributable worldwide remote roles and
FreeHire may provide attributable global tech roles through public APIs. Each is
shown with its source and original apply link. Their coverage is not a claim of
complete African local-job coverage.

The next source class is *company watchlists*, rather than an unapproved crawl
of job-board websites. Greenhouse has public, unauthenticated GET endpoints for
one named company's published job board. Lever and Ashby likewise publish
company career-board endpoints. Field Notes may let a visitor choose trusted
target employers and then collect only those employers' published listings,
preserving the original vacancy and apply URL. This is especially useful for a
curated Africa-first and diaspora employer list, but it is not a global job
search engine.

For deeper regional coverage, add providers only through their documented
contracts: USAJOBS' official search API for United States federal roles, and
Adzuna after registering for its required app ID/key and checking its country
coverage, rate limits, pricing, and republishing terms. Before adding a Nigerian
or pan-African commercial board, obtain its explicit API, feed, or distribution
permission. Do not treat an HTML search-results page as permission to scrape,
cache, or republish its jobs.

Remotive is deliberately excluded from the email-gated pilot even though it has
a public API: its free-use conditions need a separate product/terms decision.
The pilot must never use a source in a way that conflicts with its attribution,
rate-limit, data-collection, or display requirements.

The existing LinkedIn search skill uses public pages but is explicitly
personal-use-only and warns against commercial or bulk automated access. It
must not become a server-side source for the public product. The safe options
are an outbound visitor-controlled LinkedIn search, a visitor-pasted LinkedIn
job link, or a future licensed/official LinkedIn integration.

## #3: Free-use and abuse boundary

Blocked by: #1
Type: Grilling

### Question

How many CV analyses, job searches, and tailored-document generations may an
anonymous or signed-in visitor receive before costs and abuse controls apply?

### Answer

Visitors may upload a CV and see a small job-match preview without an account.
An email verification step unlocks the full shortlist and one tailored CV and
cover-letter package. The exact per-email quota, rate limits, and reset period
remain part of the hosted-pilot implementation decision.

## #4: Candidate-data privacy and retention

Blocked by: #1
Type: Grilling

### Question

Where are uploaded CVs, extracted profiles, generated documents, and search
history stored; for how long; and how can a visitor delete them?

### Answer

Unresolved. The existing local-first prototype cannot be presented as the
public product's storage model.

## #5: Tailoring contract and human approval

Blocked by: #3, #4
Type: Grilling

### Question

What exact output is allowed before human review, and how are unsupported
claims, missing qualifications, language requirements, and work authorization
handled?

### Answer

Partly resolved: tailored documents may reprioritize and clearly phrase
candidate-approved evidence, but never invent experience; the visitor reviews
and manually submits every application.

## #6: Public MVP architecture

Blocked by: #2, #3, #4, #5
Type: Prototype

### Question

What is the smallest hosted flow that securely accepts a CV, produces a
reviewable profile, returns traceable matches, and generates downloadable
documents within the free-use limit?

### Answer

Unresolved.
