# Fix It Proper data storage

All persistent data lives in Firestore and is touched only by the backend.
`firestore.rules` denies every direct browser read and write; the rules tests
in `backend/tests/rules` prove it against the emulator.

## Collections

All documents are validated by Pydantic models in `backend/app/db/models.py`.
Repositories in `backend/app/db/repositories` own every query; route handlers
never call Firestore directly.

| Collection | Document ID | Fields | Written by |
|---|---|---|---|
| `users` | Firebase Auth uid | `uid`, `email`, `created_at`, `last_seen_at` | Any signed in request (upsert) |
| `reports` | `request_id` of the analysis | `user_id`, `request_id`, `url` (normalized), `data_quality`, `response` (AnalyzeResponse JSON), `created_at`, `expires_at` | `POST /api/analyze` with a valid ID token |
| `contact_messages` | Auto ID | `name`, `email`, `message`, `created_at`, `status` (`new`, `read`, `replied`) | `POST /api/contact` |

Anonymous analyses are never stored. Only signed in users get history.

## Retention and TTL

- `reports.expires_at` is set to `created_at` plus `REPORT_RETENTION_DAYS`
  (default 30). It is a Firestore Timestamp so the TTL policy can read it.
- Enable the TTL policy once per project (replace the project ID):

```bash
gcloud firestore fields ttls update expires_at \
  --collection-group=reports \
  --enable-ttl \
  --project=YOUR_PROJECT_ID
```

Firestore usually deletes expired documents within 72 hours of `expires_at`.
The emulator does not enforce TTL, so expired test documents stay until deleted.

- `users` and `contact_messages` have no expiry. They are removed when the
  owner deletes their account (`DELETE /api/account` removes the user record,
  every owned report, every contact message from the account email, and the
  Firebase Auth user), or on request to the contact email in the Privacy Policy.

## Never stored

- Raw page HTML, screenshots, or transcripts beyond what the report JSON holds.
- API keys or Firebase credentials.
- IP addresses. Rate limiting keeps counters in server memory only, keyed by
  client IP with a 1 hour window, and persists nothing. If limits ever need
  persistence, store a salted hash of the IP, never the address.

## Authentication

Sign in uses Firebase Authentication with email/password and Google providers.
The browser sends a Firebase ID token as `Authorization: Bearer <token>`; the
backend verifies it with the Admin SDK on every protected route and never
stores tokens. `POST /api/analyze` treats auth as optional: a missing or
invalid token still returns a full analysis, it just is not saved.

## Local development and tests

```bash
firebase emulators:start --only firestore,auth
```

- Firestore emulator: `127.0.0.1:8080`, Auth emulator: `127.0.0.1:9099`.
- Backend: set `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080` and
  `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099` (see `backend/.env.example`).
- Frontend: set the `VITE_FIREBASE_*` keys plus `VITE_FIREBASE_USE_EMULATORS=true`
  (see `frontend/.env.example`).
- Python tests read `FIRESTORE_EMULATOR_HOST` and skip the emulator cases when
  it is unset. They never touch production data.
