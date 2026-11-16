import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.sessions import SessionMiddleware

from agent import answer
from profile_source import (
    InactiveCustomerRecord,
    MultipleCustomerMatches,
    ProfileSourceUnavailable,
    customer_id_exists,
    customer_id_failure_reason,
    get_bookings,
    get_profile,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == "replace-with-a-random-secret-key":
    raise RuntimeError("Set SECRET_KEY in .env to a random secret before starting the app")
if os.getenv("PROFILE_SOURCE", "excel").strip().lower() == "informatica" and len(os.getenv("DEMO_PASSWORD", "")) < 8:
    raise RuntimeError("DEMO_PASSWORD must contain at least 8 characters when PROFILE_SOURCE=informatica")

PASSWORD_ITERATIONS = 260_000
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_LOCK_SECONDS = 10 * 60
MAX_LOGIN_FAILURES = 5
DUMMY_SALT = b"\x00" * 16
GENERIC_LOGIN_ERROR = {"detail": "Invalid ID or password."}
GUEST_FACING_FIELDS = (
    "first_name", "loyalty_tier", "voyage_count", "last_voyage_region",
    "last_voyage_year", "preferred_regions", "preferred_suite",
)
logger = logging.getLogger(__name__)
login_failures: dict[str, deque[float]] = defaultdict(deque)
login_blocked_until: dict[str, float] = {}
ip_login_failures: dict[str, deque[float]] = defaultdict(deque)
ip_login_blocked_until: dict[str, float] = {}


def _print_startup_mode() -> None:
    profile_source = os.getenv("PROFILE_SOURCE", "excel").strip().lower()
    login_mode = "informatica_shared_password" if profile_source == "informatica" else "users_json_hashes"
    password_set = bool(os.getenv("DEMO_PASSWORD", ""))
    print(
        f"RCYC startup: PROFILE_SOURCE={profile_source} "
        f"login_mode={login_mode} DEMO_PASSWORD_set={'true' if password_set else 'false'}"
    )


def _log_login_failure(reason_code: str) -> None:
    logger.warning("login_failure reason_code=%s", reason_code)


_print_startup_mode()

app = FastAPI(title="RCYC Guest Concierge Agent")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="rcyc_session",
    same_site="lax",
    https_only=False,
)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    guest_id: str | None = None
    customer_id: str | None = None
    password: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1, max_length=2000)


@lru_cache(maxsize=1)
def _users_by_id() -> dict[str, dict]:
    path = DATA_DIR / "users.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as users_file:
        records = json.load(users_file)
    return {str(record["RCYC_ID"]).strip().upper(): record for record in records}


def _login_is_blocked(guest_id: str, now: float) -> bool:
    blocked_until = login_blocked_until.get(guest_id, 0)
    if blocked_until > now:
        return True
    if blocked_until:
        login_blocked_until.pop(guest_id, None)
        login_failures.pop(guest_id, None)
    return False


def _record_login_failure(guest_id: str, now: float) -> None:
    failures = login_failures[guest_id]
    while failures and now - failures[0] >= LOGIN_WINDOW_SECONDS:
        failures.popleft()
    failures.append(now)
    if len(failures) >= MAX_LOGIN_FAILURES:
        login_blocked_until[guest_id] = now + LOGIN_LOCK_SECONDS
        failures.clear()


def _ip_login_is_blocked(client_ip: str, now: float) -> bool:
    blocked_until = ip_login_blocked_until.get(client_ip, 0)
    if blocked_until > now:
        return True
    if blocked_until:
        ip_login_blocked_until.pop(client_ip, None)
        ip_login_failures.pop(client_ip, None)
    return False


def _record_ip_login_failure(client_ip: str, now: float) -> None:
    failures = ip_login_failures[client_ip]
    while failures and now - failures[0] >= LOGIN_WINDOW_SECONDS:
        failures.popleft()
    failures.append(now)
    if len(failures) >= MAX_LOGIN_FAILURES:
        ip_login_blocked_until[client_ip] = now + LOGIN_LOCK_SECONDS
        failures.clear()


def _informatica_mode() -> bool:
    return os.getenv("PROFILE_SOURCE", "excel").strip().lower() == "informatica"


def _session_customer_id(session: dict) -> str | None:
    key = "customer_id" if _informatica_mode() else "guest_id"
    return session.get(key)


@app.get("/")
def index(request: Request):
    if not _session_customer_id(request.session):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/login")
def login_page():
    template = (BASE_DIR / "static" / "login.html").read_text(encoding="utf-8")
    if _informatica_mode():
        template = template.replace("__LOGIN_ID_LABEL__", "Customer ID").replace("__LOGIN_ID_FIELD__", "customer_id")
    else:
        template = template.replace("__LOGIN_ID_LABEL__", "Guest ID").replace("__LOGIN_ID_FIELD__", "guest_id")
    return HTMLResponse(template)


@app.post("/login")
def login(request: Request, credentials: LoginRequest):
    now = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    infa_mode = _informatica_mode()
    submitted_id = credentials.customer_id if infa_mode else credentials.guest_id
    submitted_id = submitted_id or ""
    customer_id = submitted_id if infa_mode else submitted_id.strip().upper()
    valid_id = bool(re.fullmatch(r"\d{1,30}", customer_id)) if infa_mode else bool(customer_id)

    if _ip_login_is_blocked(client_ip, now):
        _log_login_failure("RATE_LIMITED")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    if valid_id and _login_is_blocked(customer_id, now):
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("RATE_LIMITED")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    if not valid_id:
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("INVALID_INPUT")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    if infa_mode:
        demo_password = os.getenv("DEMO_PASSWORD", "")
        password_matches = hmac.compare_digest(
            credentials.password.encode("utf-8"), demo_password.encode("utf-8")
        )
        if not (valid_id and password_matches):
            if valid_id:
                _record_login_failure(customer_id, now)
            _record_ip_login_failure(client_ip, now)
            _log_login_failure("PASSWORD_MISMATCH")
            return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
        try:
            exists = customer_id_exists(customer_id)
            lookup_failure_reason = customer_id_failure_reason(customer_id) if not exists else None
        except MultipleCustomerMatches:
            _record_login_failure(customer_id, now)
            _record_ip_login_failure(client_ip, now)
            _log_login_failure("MULTIPLE_MATCHES")
            return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
        except InactiveCustomerRecord:
            _record_login_failure(customer_id, now)
            _record_ip_login_failure(client_ip, now)
            _log_login_failure("INACTIVE_RECORD")
            return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
        except ProfileSourceUnavailable:
            _log_login_failure("SOURCE_UNAVAILABLE")
            return JSONResponse(
                status_code=503,
                content={"detail": "Customer sign-in service temporarily unavailable."},
            )
        if not exists:
            _record_login_failure(customer_id, now)
            _record_ip_login_failure(client_ip, now)
            _log_login_failure(lookup_failure_reason or "ID_NOT_FOUND")
            return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

        login_failures.pop(customer_id, None)
        login_blocked_until.pop(customer_id, None)
        ip_login_failures.pop(client_ip, None)
        ip_login_blocked_until.pop(client_ip, None)
        request.session.clear()
        request.session["customer_id"] = customer_id
        return {"authenticated": True}

    guest_id = customer_id

    record = _users_by_id().get(guest_id)
    salt = bytes.fromhex(record["salt"]) if record else DUMMY_SALT
    iterations = int(record.get("iterations", PASSWORD_ITERATIONS)) if record else PASSWORD_ITERATIONS
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", credentials.password.encode("utf-8"), salt, iterations
    ).hex()
    stored_hash = record["password_hash"] if record else "0" * 64
    password_matches = hmac.compare_digest(candidate_hash, stored_hash)

    if not record:
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("ID_NOT_FOUND")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
    if not password_matches:
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("PASSWORD_MISMATCH")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    profile = None
    try:
        profile = get_profile(guest_id)
    except ProfileSourceUnavailable:
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("SOURCE_UNAVAILABLE")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
    except Exception:
        logger.warning("Profile lookup failed during login")
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("SOURCE_UNAVAILABLE")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
    require_booking = os.getenv("REQUIRE_BOOKING_FOR_LOGIN", "false").strip().lower() == "true"
    is_booked = (not require_booking) or bool(
        profile
        and str(profile.get("attributes", {}).get("active_booking", "")).upper() == "Y"
    )
    if not profile:
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("ID_NOT_FOUND")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)
    if not is_booked:
        _record_login_failure(guest_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("INACTIVE_RECORD")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    login_failures.pop(guest_id, None)
    login_blocked_until.pop(guest_id, None)
    ip_login_failures.pop(client_ip, None)
    ip_login_blocked_until.pop(client_ip, None)
    request.session.clear()
    request.session["guest_id"] = guest_id
    return {"authenticated": True}


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}


def _usable_name(value) -> str | None:
    """Return a usable guest name, normalising None/empty/'none'/'null' to None."""
    if value is None:
        return None
    name = str(value).strip()
    if not name or name.casefold() in {"none", "null", "undefined"}:
        return None
    return name


def _usable_first_name(attributes: dict) -> str | None:
    """Return the canonical first name for a profile, or None when empty."""
    return _usable_name(attributes.get("first_name"))


def _usable_full_name(attributes: dict) -> str | None:
    """Return full_name, else first + last, else None when all empty."""
    full_name = _usable_name(attributes.get("full_name"))
    if full_name:
        return full_name
    first = str(attributes.get("first_name") or "").strip()
    last = str(attributes.get("last_name") or "").strip()
    if first or last:
        return " ".join(p for p in (first, last) if p)
    return None


def _mask_email(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text or "@" not in text:
        return None
    local, _, domain = text.partition("@")
    if not local or not domain:
        return None
    return f"{local[0]}***@{domain}"


def _mask_phone(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    number = str(entry.get("phone_number", "")).strip()
    digits = "".join(ch for ch in number if ch.isdigit())
    if len(digits) < 4:
        return None
    last4 = digits[-4:]
    country = str(entry.get("country_code", "")).strip()
    if country:
        return f"+{country} ***{last4}" if not country.startswith("+") else f"{country} ***{last4}"
    return f"***{last4}"


@app.get("/me")
def me(request: Request):
    guest_id = _session_customer_id(request.session)
    if not guest_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        profile = _load_profile(guest_id)
    except ProfileSourceUnavailable:
        logger.warning("Profile source temporarily unavailable for /me")
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None
    if not profile:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")
    attributes = profile.get("attributes", {}) or {}
    first_name = _usable_first_name(attributes)
    full_name = _usable_full_name(attributes)

    result = {}
    if first_name:
        result["first_name"] = first_name
    if full_name:
        result["full_name"] = full_name
    if guest_id:
        result["customer_id"] = guest_id

    
    # email masked
    email_entries = attributes.get("email")
    if isinstance(email_entries, list) and email_entries and isinstance(email_entries[0], dict):
        masked_email = _mask_email(email_entries[0].get("email_address"))
        if masked_email:
            result["email"] = masked_email
    # phone masked
    phone_entries = attributes.get("phone")
    if isinstance(phone_entries, list) and phone_entries and isinstance(phone_entries[0], dict):
        masked_phone = _mask_phone(phone_entries[0])
        if masked_phone:
            result["phone"] = masked_phone

    # bookings
    try:
        bookings = get_bookings(guest_id)
    except ProfileSourceUnavailable:
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None

    booking_list = []
    for b in (bookings or [])[:10]:
        item = {}
        if b.get("booking_id") is not None:
            item["booking_id"] = b.get("booking_id")
        if b.get("voyage_ref") is not None:
            item["voyage_ref"] = b.get("voyage_ref")
        voyage_count = b.get("voyage_count")
        if voyage_count is not None and voyage_count != "":
            item["voyage_count"] = voyage_count
        booking_date = b.get("booking_date")
        if booking_date is not None and booking_date != "":
            item["booking_date"] = booking_date
        status_code = b.get("status_code")
        if status_code is not None and status_code != "":
            item["status_code"] = status_code
        if item:
            booking_list.append(item)

    if bookings:
        result["bookings"] = booking_list
    else:
        result["bookings"] = []
    return result


def _load_profile(guest_id: str) -> dict | None:
    """Shared profile loader for /me and /chat so both cannot disagree.

    Returns None when the source is unavailable (the caller maps this to 503)
    or when the profile is missing (the caller maps this to 401+session clear).
    """
    try:
        return get_profile(guest_id)
    except ProfileSourceUnavailable:
        raise
@app.post("/chat")
def chat(request: Request, chat_request: ChatRequest):
    guest_id = _session_customer_id(request.session)
    if not guest_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        profile = _load_profile(guest_id)
    except ProfileSourceUnavailable:
        logger.warning("Profile source temporarily unavailable for /chat")
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None
    if not profile:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = answer(guest_id, chat_request.message.strip(), request.session, profile=profile)
    ea_context = result.pop("ea_context", None)
    if ea_context:
        logger.info("EA escalation handled")



    return result
