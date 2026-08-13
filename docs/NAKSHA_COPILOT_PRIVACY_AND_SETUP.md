# Naksha Copilot — Privacy and Setup

Naksha Copilot is a read-only Gemini integration for IT Department, Software Team, and Management users.

## Data boundary

Only aggregate totals, device-category counts, department counts, status counts, monthly/yearly statistics, data-quality counts, and anonymized request references are sent to Gemini.

The backend blocks employee identities, emails, phone numbers, serial numbers, asset tags/IDs, ticket content, credentials, client names, remarks, and raw database rows. Gemini never receives database credentials and cannot execute SQL or modify records.

Audit events store a request reference, period, model, result, and SHA-256 hash of the question. They do not store the question or AI response.

## Local setup

Add these values to the root `.env` file. Never expose the key through a `VITE_*` variable.

```env
NAKSHA_COPILOT_ENABLED=true
GEMINI_API_KEY=replace-with-your-real-key
GEMINI_MODEL=gemini-3.5-flash-lite
NAKSHA_COPILOT_TIMEOUT_SECONDS=25
NAKSHA_COPILOT_REQUESTS_PER_HOUR=20
NAKSHA_COPILOT_MAX_OUTPUT_TOKENS=900
```

Rebuild the backend and frontend after changing the environment.

The normal asset-management system remains available when Gemini is disabled, unavailable, timed out, or out of free-tier quota.
