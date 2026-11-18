# MARIS · RCYC Guest Concierge Agent (UC 3)

Prototype of **MARIS**, The Ritz-Carlton Yacht Collection Guest Concierge Agent.

## Architecture

- **Frontend (`frontend/`)**: HTML, CSS, and Vanilla JavaScript (`index.html`, `styles.css`, `app.js`) matching the MARIS luxury layout with a collapsible `Demo insights` drawer, sanitized chat rendering, and mobile-collapsible `Your details` panel.
- **Backend (`backend/app/`)**: Python + FastAPI:
  - `data_provider.py`: Unified `GuestDataProvider` interface (`getProfile`, `getBookings`, `listVoyages`) implemented by `MockProvider` (reads `data/sample_data.json`) alongside an empty `AmperityProvider` stub with field mapping comments.
  - `recommendation_engine.py`: Explainable 4-weight voyage scoring (`preferred_region`, `interest_focus`, `preferred_suite_availability`, `new_region_vs_last_voyage`) with strict consent gating.
  - `escalation_engine.py`: Experience Ambassador escalation rules (open complaints, refund/dissatisfaction, medical/allergy/wheelchair coordination, VIP custom arrangements, explicit human requests).
  - `llm_engine.py`: Server-side Gemini phrasing (via `GEMINI_API_KEY` and `ListModels`-verified `GEMINI_MODEL`) and optional Ollama/Anthropic support with silent fallback to rule-based phrasing.
  - `concierge_agent.py` & `main.py`: Intent routing, privacy enforcement, and REST endpoints.

## Amperity mapping

| MARIS Model | MARIS Field | Amperity Column |
|---|---|---|
| `GuestProfile` | `rcyc_id` | TO CONFIRM |
| `GuestProfile` | `first_name` | TO CONFIRM |
| `GuestProfile` | `last_name` | TO CONFIRM |
| `GuestProfile` | `loyalty_tier` | TO CONFIRM |
| `GuestProfile` | `past_voyages` | TO CONFIRM |
| `GuestProfile` | `previous_voyage_region` | TO CONFIRM |
| `GuestProfile` | `sailed_regions` | TO CONFIRM |
| `GuestProfile` | `preferred_suite` | TO CONFIRM |
| `GuestProfile` | `interest_focus` | TO CONFIRM |
| `GuestProfile` | `ancillary_purchase_preferences` | TO CONFIRM |
| `GuestProfile` | `preferred_destinations` | TO CONFIRM |
| `GuestProfile` | `dietary_requirements` | TO CONFIRM |
| `GuestProfile` | `accessibility_requirements` | TO CONFIRM |
| `GuestProfile` | `vip_status` | TO CONFIRM |
| `GuestProfile` | `open_complaint_status` | TO CONFIRM |
| `GuestProfile` | `complaint_summary` | TO CONFIRM |
| `GuestProfile` | `personalization_consent` | TO CONFIRM |
| `GuestProfile` | `profile_label` | TO CONFIRM |
| `GuestProfile` | `guest_status` | TO CONFIRM |
| `Booking` | `booking_id` | TO CONFIRM |
| `Booking` | `rcyc_id` | TO CONFIRM |
| `Booking` | `voyage_id` | TO CONFIRM |
| `Booking` | `voyage_name` | TO CONFIRM |
| `Booking` | `destination` | TO CONFIRM |
| `Booking` | `ship` | TO CONFIRM |
| `Booking` | `suite_category` | TO CONFIRM |
| `Booking` | `booked_on` | TO CONFIRM |
| `Booking` | `sailing_dates` | TO CONFIRM |
| `Booking` | `status_code` | TO CONFIRM |

## Running Locally on Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn backend.app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000` in your browser, or run the automated test suite:

```powershell
python tests/test_scenarios.py http://127.0.0.1:8000
```

## Informatica Business 360 Basis, Setup & UNCONFIRMED Items

When `DATA_PROVIDER_MODE=informatica`, MARIS authenticates guests using Customer ID (`INFA_CUSTOMER_ID_FIELD`, default `rcyc_id`) + shared `DEMO_PASSWORD` via `verify_guest_credentials()`, reads live `Guest360` + `rel_g360_to_booking` records, joins bookings locally against the 12 catalog voyages (`data/sample_data.json`), and keeps reference snapshots in `docs/reference/` (never served statically).

- **Session & iframe auth**: `POST /api/login` returns `{"authenticated": true, "token": "<signed_token>"}` (24-hour TTL) and sets an `HttpOnly`, `Secure`, `SameSite=None` cookie (`rcyc_session`). Authenticated endpoints (`/api/me`, `/api/chat`, `/api/logout`) accept either the cookie or `Authorization: Bearer <token>`, and signing out revokes the token server-side (`401` on reuse).
- **Strict consent & optional 2c fields**: Consent defaults to `N` (`Personalization is off`). Configure `INFA_FIELD_CONSENT` (`group.field` or flat field) for live `Y`/`N` consent, or enable `DEMO_ASSUME_PERSONALIZATION_CONSENT=true` for demos when no consent field is configured. Optional fields (`INFA_FIELD_LOYALTY_TIER`, `INFA_FIELD_PREFERRED_REGIONS`, `INFA_FIELD_PREFERRED_SUITE`, `INFA_FIELD_INTEREST_FOCUS`, `INFA_FIELD_CONSENT`, `INFA_FIELD_VIP`, `INFA_FIELD_OPEN_COMPLAINT`) are skipped when empty.
- **Diagnostics**: `GET /api/health/informatica` returns only `{configured, login_ok, search_ok, entity}`.

The following items are **UNCONFIRMED** (not verbatim from `profile_source.py` / `app.py` or flagged `# TO VERIFY` / `None` in `profile_source.py`):
- **UNCONFIRMED** (`FIELD_MAP`): `guest_id`, `middle_name`, `identifier_full`, and `None`-mapped fields (`consent_to_personalize`, `loyalty_tier`, `voyage_count`, `last_voyage_region`, `last_voyage_year`, `preferred_suite`, `top_ancillary`, `preferred_regions`, `dietary_needs`, `accessibility_needs`, `vip_flag`, `ltv_tier`, `open_complaint`, `active_booking`) are unverified against a live Business 360 record (`profile_source.py` lines 22, 24, 29–30, 35–48, 282).
- **UNCONFIRMED** (Session cookie format): `backend/app/main.py` uses a custom stdlib HMAC-SHA256 JSON cookie (`base64url({"customer_id", "iat", "exp"}).hexdigest`, `Secure=True`) because `itsdangerous` is not installed (`app.py` lines 74–80 used Starlette `SessionMiddleware` with `https_only=False`).
- **UNCONFIRMED** (HTTP client): `InformaticaProvider` uses `httpx.request` instead of `requests.request` (`profile_source.py` line 310).
- **UNCONFIRMED** (Login payload field alias): `POST /api/login` accepts either `guest_id` or `customer_id` (`app.py` line 178 reads strictly `customer_id` in Informatica mode).
- **UNCONFIRMED** (Catalog & domain adapter): `InformaticaProvider.getProfile()`, `getBookings()`, and `listVoyages()` (local `sample_data.json` catalog) adapt `profile_source.py` raw dicts into MARIS `GuestProfile` and `Booking` models.
- **Live Informatica check**: Only runnable when `INFA_*`, `SECRET_KEY`, and `DEMO_PASSWORD` Secrets are configured.
- **Sample spreadsheet notice**: `data/guest_profiles.xlsx` is sample data only and must be removed or replaced before any real guest data is used.

## Conversation History & Feedback Persistence

Signed-in Informatica guests have their conversations persisted in SQLite (`backend/app/chat_store.py`) and strictly scoped by the server-verified session Customer ID:

- **Configuration**:
  - `CHAT_DB_PATH` (default `data/chat.db`): SQLite database path.
  - `CHAT_RETENTION_DAYS` (default `30`): Days to retain conversations before automatic deletion on startup and every 24 hours.
  - **Container storage caveat**: Container filesystems are ephemeral—mount a persistent volume at `CHAT_DB_PATH` in production if chat history should survive container restarts or redeployments.
- **Stored fields only** (never stores email, phone, loyalty tier, or raw Informatica payloads):
  - `conversations`: `id`, `customer_id`, `title`, `created_at`, `updated_at`
  - `messages`: `id`, `conversation_id`, `role`, `text`, `created_at`
  - `message_feedback`: `conversation_id`, `message_id`, `customer_id`, `vote` (`up` or `down`), `created_at`, `updated_at`
- **API endpoints** (require a signed-in guest session; unauthenticated callers receive `401`, visitors receive `403`, cross-guest access returns `404`):
  - `GET /api/conversations` (`?q=` optional literal search across title and message text, sorted newest first)
  - `POST /api/conversations`
  - `GET /api/conversations/{id}`
  - `PATCH /api/conversations/{id}` (title 1–80 chars, trimmed)
  - `DELETE /api/conversations/{id}`
  - `POST /api/feedback` (`{conversation_id, message_id, vote}`)
  - `POST /api/chat` accepts optional `conversation_id`, auto-titles new threads from the first 6 words of the guest's first message, and persists exchanges.

