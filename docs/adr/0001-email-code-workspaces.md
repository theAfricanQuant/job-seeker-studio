# ADR 0001: Anonymous browser cookie owns a candidate workspace

## Context

The local prototype kept a single profile and document directory. That model
would expose one visitor's career data to another once the app is hosted. An
email-code gate also stopped a visitor before their CV could be extracted.

## Decision

The app creates an opaque random workspace cookie automatically for each
browser. The server hashes that token to name a private workspace directory.
The CV's email address is extracted as candidate profile data only; it is never
an access credential and no email is sent during the basic workflow.

## Consequences

- A visitor can start immediately, but clearing browser data makes the
  workspace unrecoverable. Optional email recovery is a later product choice.
- A browser cannot read another browser's profile or generated files through
  guessed paths because workspace tokens have 256 bits of entropy.
- The current global local-pilot data is not silently migrated into a browser
  workspace; candidates upload or save their reviewed records after opening it.
