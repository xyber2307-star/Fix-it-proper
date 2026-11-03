# Fix It Proper

Paste a public website URL and get a ranked list of specific fixes with evidence, plus 2 to 3 AI rewrite variants for the page title, meta description, heading, and call to action.

V1 analyzes public websites and landing pages only. Social media pages are rejected with a clear error.

## Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer
- Java 17 or newer, for the Firebase emulators
- Optional: a Groq API key for AI explanations and rewrites, and a Google PageSpeed Insights API key for performance metrics. Without keys the tool still runs; missing sections are listed under `limitations`.
- Optional: a Firebase project for accounts, saved reports, and contact storage. Without it the analysis endpoint still works; the contact and saved report routes return `503`.

## Run the backend

From the repo root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows use `.venv\Scripts\activate` and `copy .env.example .env`.

Edit `.env` to set `GROQ_API_KEY` and `PAGESPEED_API_KEY`. `FRONTEND_ORIGIN` must match the frontend address below.

## Run the frontend

From the repo root, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The app serves at http://localhost:5173 by default.

## Firebase setup (accounts, saved reports, contact storage)

Local development uses the Firebase emulators. From the repo root:

```bash
npx firebase-tools emulators:start --only firestore,auth
```

Backend (`backend/.env`, see `.env.example`):

```bash
FIREBASE_PROJECT_ID=fix-it-proper-dev
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
```

Frontend (`frontend/.env`, see `.env.example`):

```bash
VITE_FIREBASE_API_KEY=demo-key
VITE_FIREBASE_AUTH_DOMAIN=demo.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=fix-it-proper-dev
VITE_FIREBASE_USE_EMULATORS=true
```

Any values work against the emulators; sign in, saved reports, and the contact
form all run locally end to end.

Production deploy, in order:

1. Create a Firebase project and enable Authentication providers (Email/Password
   and Google) plus a Firestore database.
2. Deploy the deny-all rules: `firebase deploy --only firestore:rules --project YOUR_PROJECT_ID`.
3. Enable report expiry (see `docs/DATA.md` for the TTL command).
4. Create a service account with the Firebase Admin and Datastore User roles,
   download its JSON key, and point the backend at it with
   `FIREBASE_CREDENTIALS_PATH` (file) or `FIREBASE_CREDENTIALS_BASE64`.
   Never commit the key file; `.gitignore` already excludes key patterns.
5. Set the real `VITE_FIREBASE_*` web keys in the frontend build environment
   and leave `VITE_FIREBASE_USE_EMULATORS` empty.

Retention: saved reports expire automatically after `REPORT_RETENTION_DAYS`
(default 30). Accounts, contact messages, and everything tied to a user are
removed by `DELETE /api/account` or on request to the contact email.

## Try it with curl

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/"}'
```

Optional brand voice context (plain text, up to 2000 characters):

```bash
curl -X POST "http://127.0.0.1:8000/api/analyze?brand_voice=Friendly%20neighborhood%20plumber" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/"}'
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

Each response carries `data_quality`: `full`, `partial`, or `og_only`. When it is not `full`, the UI warns the user and `score` is null. The total request budget is 40 seconds; slow PageSpeed or AI stages degrade to `limitations` entries instead of failing the request.

## YouTube video pages

Paste a watch, shorts, embed, or youtu.be URL to get a checklist
report built only on public page data: title, description,
thumbnail, and the transcript when captions exist. Rule checks cover
title length, the description hook, CTA and link presence, and
chapters for videos of 3 minutes or more. Every report states that
results are checklist based and not a performance forecast.

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=abc123"}'
```

## Checks

Backend (from `backend` with the venv active):

```bash
ruff check app tests
ruff format --check app tests
mypy app
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 pytest -q
```

Start the emulators first (see above) or the database tests skip. Rules tests
(from `backend/tests/rules`, after one `npm install` there):

```bash
node --test rules.test.mjs
```

Frontend (from `frontend`):

```bash
npm run lint
npm run typecheck
npm run build
```
