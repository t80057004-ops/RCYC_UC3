"""FastAPI application entrypoint for MARIS RCYC Guest Concierge."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from backend.app.chat_store import ChatStore
from backend.app.concierge_agent import ConciergeAgent
from backend.app.config import BASE_DIR, Settings, logger, settings
from backend.app.data_provider import (
    GuestDataProvider,
    InactiveCustomerRecord,
    InformaticaProvider,
    MultipleCustomerMatches,
    ProfileSourceUnavailable,
    build_anonymous_profile,
    create_data_provider,
    mask_email,
    mask_phone,
)
from backend.app.escalation_engine import evaluate_escalation
from backend.app.llm_engine import PluggableLLMEngine
from backend.app.models import (
    ChatRequest,
    ChatResponse,
    ChatTurn,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    ConversationTitleRequest,
    ConversationTitleResponse,
    CreateConversationRequest,
    EscalationInfo,
    FeedbackRequest,
    FeedbackResponse,
    GuestContextResponse,
    GuestSummary,
    RenameConversationRequest,
    Voyage,
    to_public_profile,
)

FRONTEND_DIR = BASE_DIR / "frontend"

SESSION_COOKIE_NAME = "rcyc_session"
SESSION_TTL_SECONDS = 24 * 60 * 60
VISITOR_SESSION_TTL_SECONDS = 4 * 60 * 60
VISITOR_CHAT_WINDOW_SECONDS = 10 * 60
VISITOR_CHAT_MAX_MESSAGES = 20
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_LOCK_SECONDS = 10 * 60
MAX_LOGIN_FAILURES = 5
GENERIC_LOGIN_ERROR = {"detail": "Invalid ID or password."}

login_failures: dict[str, deque[float]] = defaultdict(deque)
login_blocked_until: dict[str, float] = {}
ip_login_failures: dict[str, deque[float]] = defaultdict(deque)
ip_login_blocked_until: dict[str, float] = {}
visitor_chat_timestamps: dict[str, deque[float]] = defaultdict(deque)
revoked_session_tokens: dict[str, int] = {}

data_provider = create_data_provider(settings)
llm_engine = PluggableLLMEngine(settings)
concierge_agent = ConciergeAgent(data_provider=data_provider, llm_engine=llm_engine)
chat_store = ChatStore(settings.chat_db_path, settings.chat_retention_days)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    guest_id: str | None = None
    customer_id: str | None = None
    password: str


async def _daily_retention_loop() -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            active_cfg = _active_settings()
            _active_chat_store().cleanup_expired(active_cfg.chat_retention_days)
        except Exception as exc:
            logger.warning("Daily chat retention cleanup failed (%s).", exc)


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        _active_chat_store().cleanup_expired(_active_settings().chat_retention_days)
    except Exception as exc:
        logger.warning("Startup chat retention cleanup failed (%s).", exc)

    cleanup_task = asyncio.create_task(_daily_retention_loop())

    if settings.gemini_api_key:
        try:
            llm_engine.refresh_gemini_models()
        except Exception as exc:
            logger.warning("Gemini ListModels failed on startup (%s).", exc)
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title="MARIS · RCYC Guest Concierge",
    description="Ritz-Carlton Yacht Collection Guest Concierge prototype powered by GuestDataProvider.",
    version="1.1.0",
    lifespan=lifespan,
)
app.state.settings = settings
app.state.data_provider = data_provider
app.state.concierge_agent = concierge_agent
app.state.chat_store = chat_store

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _active_settings() -> Settings:
    return getattr(app.state, "settings", settings)


def _active_provider() -> GuestDataProvider:
    return getattr(app.state, "data_provider", data_provider)


def _active_agent() -> ConciergeAgent:
    return getattr(app.state, "concierge_agent", concierge_agent)


def _active_chat_store() -> ChatStore:
    return getattr(app.state, "chat_store", chat_store)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(token: str) -> bytes:
    padding = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + padding)


# UNCONFIRMED: Custom stdlib HMAC-SHA256 JSON session cookie format ({customer_id, iat, exp} + hex digest)
# used because `itsdangerous` is not installed; app.py lines 74-80 used Starlette SessionMiddleware (itsdangerous).
def _sign_session(customer_id: str, secret_key: str) -> str:
    if not secret_key or secret_key == "replace-with-a-random-secret-key":
        raise RuntimeError("SECRET_KEY is required for session signing")
    now = int(time.time())
    payload = json.dumps(
        {"customer_id": customer_id, "role": "guest", "iat": now, "exp": now + SESSION_TTL_SECONDS},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    body = _b64url_encode(payload)
    sig = hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _sign_visitor_session(secret_key: str) -> str:
    if not secret_key or secret_key == "replace-with-a-random-secret-key":
        raise RuntimeError("SECRET_KEY is required for session signing")
    now = int(time.time())
    payload = json.dumps(
        {"role": "visitor", "iat": now, "exp": now + VISITOR_SESSION_TTL_SECONDS},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    body = _b64url_encode(payload)
    sig = hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _unsign_session_payload(token: str | None, secret_key: str) -> dict[str, Any] | None:
    if not token or "." not in token or not secret_key:
        return None
    body, _, sig = token.partition(".")
    expected = hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_b64url_decode(body).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def _unsign_session(token: str | None, secret_key: str) -> str | None:
    data = _unsign_session_payload(token, secret_key)
    if not data or data.get("role") == "visitor":
        return None
    cid = str(data.get("customer_id") or "").strip()
    return cid or None


def _set_session_cookie_token(
    response: JSONResponse,
    token: str,
    max_age: int = SESSION_TTL_SECONDS,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )


def _set_session_cookie(response: JSONResponse, customer_id: str, secret_key: str) -> str:
    token = _sign_session(customer_id, secret_key)
    _set_session_cookie_token(response, token)
    return token


def _clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )


def _revoke_token(token: str | None) -> None:
    if not token:
        return
    now = int(time.time())
    expired = [digest for digest, exp in revoked_session_tokens.items() if exp < now]
    for digest in expired:
        revoked_session_tokens.pop(digest, None)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    revoked_session_tokens[digest] = now + SESSION_TTL_SECONDS


def _is_token_revoked(token: str | None) -> bool:
    if not token:
        return False
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    exp = revoked_session_tokens.get(digest)
    if exp is None:
        return False
    if exp < int(time.time()):
        revoked_session_tokens.pop(digest, None)
        return False
    return True


def _extract_raw_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header:
        scheme, _, token = auth_header.partition(" ")
        clean_tok = token.strip()
        if scheme.lower() == "bearer" and clean_tok:
            return clean_tok
        return None
    return request.cookies.get(SESSION_COOKIE_NAME)


def _session_info(request: Request, active_cfg: Settings) -> tuple[str | None, str | None]:
    raw_tok = _extract_raw_token(request)
    if not raw_tok or _is_token_revoked(raw_tok):
        return None, None
    data = _unsign_session_payload(raw_tok, active_cfg.secret_key)
    if not data:
        return None, None
    if data.get("role") == "visitor":
        return "visitor", None
    cid = str(data.get("customer_id") or "").strip()
    if cid:
        return "guest", cid
    return None, None


def _session_customer_id(request: Request, active_cfg: Settings) -> str | None:
    role, cid = _session_info(request, active_cfg)
    if role == "guest" and cid:
        return cid
    return None


def _require_guest_session(request: Request, active_cfg: Settings) -> str:
    role, customer_id = _session_info(request, active_cfg)
    if role == "visitor":
        raise HTTPException(status_code=403, detail="Sign in required to access profile or bookings.")
    if role != "guest" or not customer_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return customer_id


def _check_and_record_visitor_chat(client_ip: str, now: float) -> bool:
    """Allow up to VISITOR_CHAT_MAX_MESSAGES per VISITOR_CHAT_WINDOW_SECONDS per IP."""
    dq = visitor_chat_timestamps[client_ip]
    while dq and now - dq[0] >= VISITOR_CHAT_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= VISITOR_CHAT_MAX_MESSAGES:
        return False
    dq.append(now)
    return True


def verify_guest_credentials(
    customer_id: str,
    password: str,
    active_cfg: Settings | None = None,
) -> bool:
    """Verify guest credentials in one place so per-guest passwords can replace DEMO_PASSWORD later."""
    cfg = active_cfg or _active_settings()
    if len(cfg.demo_password) < 8:
        return False
    return hmac.compare_digest(
        password.encode("utf-8"),
        cfg.demo_password.encode("utf-8"),
    )


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


def _client_ip(request: Request) -> str:
    peer_ip = request.client.host if request.client else ""
    if peer_ip == "127.0.0.1":
        forwarded_for = request.headers.get("x-forwarded-for", "").strip()
        if forwarded_for:
            first_hop = forwarded_for.split(",")[0].strip()
            if first_hop:
                return first_hop
        return "127.0.0.1"
    return peer_ip or "unknown"


def _log_login_failure(reason_code: str) -> None:
    logger.warning("login_failure reason_code=%s", reason_code)


def _usable_name(value: Any) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    if not name or name.casefold() in {"none", "null", "undefined"}:
        return None
    return name


def _usable_first_name(attributes: dict[str, Any]) -> str | None:
    return _usable_name(attributes.get("first_name"))


def _usable_full_name(attributes: dict[str, Any]) -> str | None:
    full_name = _usable_name(attributes.get("full_name"))
    if full_name:
        return full_name
    first = _usable_name(attributes.get("first_name")) or ""
    last = _usable_name(attributes.get("last_name")) or ""
    if first or last:
        return " ".join(p for p in (first, last) if p)
    return None


def _mask_email(value: Any) -> str | None:
    return mask_email(value)


def _mask_phone(entry: Any) -> str | None:
    return mask_phone(entry)


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/api/health", methods=["GET", "HEAD"])
def health_check() -> dict[str, Any]:
    """Service readiness overview (never exposes API keys, secrets, or model lists)."""
    active_cfg = _active_settings()
    provider = _active_provider()
    payload: dict[str, Any] = {
        "status": "ok",
        "service": "rcyc-guest-concierge-uc3",
        "llm_provider": active_cfg.llm_provider,
        "gemini_model": llm_engine.selected_gemini_model if active_cfg.llm_provider == "gemini" else None,
        "gemini_generate_content_models_count": sum(
            1 for m in llm_engine.available_models if "generateContent" in m.get("supportedGenerationMethods", [])
        ),
        "last_gemini_check": llm_engine.last_gemini_check,
        "data_provider": active_cfg.data_provider_mode,
        "demo_mode": active_cfg.demo_mode,
        "infa_configured": bool(
            active_cfg.infa_login_url
            and active_cfg.infa_username
            and active_cfg.infa_password
            and active_cfg.infa_model_version
            and active_cfg.secret_key
            and len(active_cfg.demo_password) >= 8
        ),
        "guests_loaded": len(provider.listSampleGuests()),
        "voyages_loaded": len(provider.listVoyages()),
    }
    return payload


@app.get("/api/health/informatica")
def health_informatica() -> dict[str, Any]:
    """Return boolean Informatica connectivity diagnostics without exposing secrets or records."""
    active_cfg = _active_settings()
    configured = bool(
        active_cfg.infa_login_url
        and active_cfg.infa_username
        and active_cfg.infa_password
        and active_cfg.infa_model_version
    )
    entity = active_cfg.infa_entity or "guest360"
    if not configured:
        return {
            "configured": False,
            "login_ok": False,
            "search_ok": False,
            "entity": entity,
        }

    probe = _active_provider()
    if not isinstance(probe, InformaticaProvider):
        probe = InformaticaProvider(active_cfg)

    login_ok = False
    search_ok = False
    try:
        probe.login()
        login_ok = True
        probe._search_guest_result("0", field_name=probe.customer_id_field)
        search_ok = True
    except ProfileSourceUnavailable:
        pass
    except Exception:
        pass

    return {
        "configured": configured,
        "login_ok": login_ok,
        "search_ok": search_ok,
        "entity": entity,
    }


@app.post("/api/login")
def login(request: Request, credentials: LoginRequest):
    """Authenticate an Informatica Business 360 customer using Customer/Guest ID + shared DEMO_PASSWORD."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode != "informatica":
        raise HTTPException(status_code=404, detail="Not found")

    now = time.monotonic()
    client_ip = _client_ip(request)
    # UNCONFIRMED: Accepts guest_id fallback in addition to customer_id (app.py line 178 reads strictly customer_id in informatica mode).
    submitted_id = (credentials.customer_id if credentials.customer_id is not None else credentials.guest_id) or ""
    customer_id = submitted_id.strip()
    valid_id = bool(re.fullmatch(r"\d{1,30}", customer_id))

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

    demo_password = active_cfg.demo_password
    if len(demo_password) < 8 or not active_cfg.secret_key:
        _log_login_failure("AUTH_MISCONFIGURED")
        return JSONResponse(
            status_code=503,
            content={"detail": "Customer sign-in service temporarily unavailable."},
        )

    if not verify_guest_credentials(customer_id, credentials.password, active_cfg):
        _record_login_failure(customer_id, now)
        _record_ip_login_failure(client_ip, now)
        _log_login_failure("PASSWORD_MISMATCH")
        return JSONResponse(status_code=401, content=GENERIC_LOGIN_ERROR)

    provider = _active_provider()
    if not isinstance(provider, InformaticaProvider):
        _log_login_failure("SOURCE_UNAVAILABLE")
        return JSONResponse(
            status_code=503,
            content={"detail": "Customer sign-in service temporarily unavailable."},
        )

    try:
        exists = provider.customer_id_exists(customer_id)
        lookup_failure_reason = provider.customer_id_failure_reason(customer_id) if not exists else None
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

    token = _sign_session(customer_id, active_cfg.secret_key)
    resp = JSONResponse(status_code=200, content={"authenticated": True, "token": token})
    _set_session_cookie_token(resp, token)
    return resp


@app.post("/api/visitor")
def start_visitor_session():
    """Issue a signed 4-hour visitor session token with role 'visitor' and no customer_id."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode != "informatica":
        raise HTTPException(status_code=404, detail="Not found")
    if not active_cfg.secret_key or active_cfg.secret_key == "replace-with-a-random-secret-key":
        return JSONResponse(
            status_code=503,
            content={"detail": "Visitor browsing service temporarily unavailable."},
        )
    token = _sign_visitor_session(active_cfg.secret_key)
    resp = JSONResponse(
        status_code=200,
        content={"authenticated": False, "role": "visitor", "token": token},
    )
    _set_session_cookie_token(resp, token, max_age=VISITOR_SESSION_TTL_SECONDS)
    return resp


@app.get("/api/session")
def session_status(request: Request) -> dict[str, Any]:
    """Return local session role without calling Informatica."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode != "informatica":
        return {"authenticated": False, "role": None, "data_provider": active_cfg.data_provider_mode}
    role, _ = _session_info(request, active_cfg)
    return {
        "authenticated": role == "guest",
        "role": role,
        "data_provider": "informatica",
    }


@app.post("/api/logout")
def logout(request: Request):
    """Clear the signed session cookie and revoke the current token."""
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header:
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            _revoke_token(token.strip())
    _revoke_token(request.cookies.get(SESSION_COOKIE_NAME))
    resp = JSONResponse(status_code=200, content={"authenticated": False})
    _clear_session_cookie(resp)
    return resp


@app.get("/api/me")
def me(request: Request):
    """Return minimized, masked profile + raw-status bookings for the signed-in Informatica customer."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode != "informatica":
        raise HTTPException(status_code=404, detail="Not found")

    role, customer_id = _session_info(request, active_cfg)
    if role == "visitor":
        raise HTTPException(status_code=403, detail="Sign in required to access profile or bookings.")
    if role != "guest" or not customer_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    provider = _active_provider()
    if not isinstance(provider, InformaticaProvider):
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable")

    try:
        profile = provider.get_raw_profile(customer_id)
    except ProfileSourceUnavailable:
        logger.warning("Profile source temporarily unavailable for /api/me")
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None

    if not profile:
        resp = JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        _clear_session_cookie(resp)
        return resp

    attributes = profile.get("attributes", {}) or {}
    first_name = _usable_first_name(attributes)
    full_name = _usable_full_name(attributes)

    result: dict[str, Any] = {}
    if first_name:
        result["first_name"] = first_name
    if full_name:
        result["full_name"] = full_name
    result["customer_id"] = customer_id

    email_entries = attributes.get("email")
    if isinstance(email_entries, list):
        for entry in email_entries:
            if isinstance(entry, dict):
                masked_email = _mask_email(entry.get("email_address"))
                if masked_email:
                    result["email"] = masked_email
                    break

    phone_entries = attributes.get("phone")
    if isinstance(phone_entries, list):
        for entry in phone_entries:
            if isinstance(entry, dict):
                masked_phone = _mask_phone(entry)
                if masked_phone:
                    result["phone"] = masked_phone
                    break

    loyalty_tier = _usable_name(attributes.get("loyalty_tier"))
    if loyalty_tier:
        result["loyalty_tier"] = loyalty_tier

    pref_regions = attributes.get("preferred_regions")
    if isinstance(pref_regions, list) and pref_regions:
        result["preferred_destinations"] = [str(r).strip() for r in pref_regions if str(r).strip()]

    preferred_suite = _usable_name(attributes.get("preferred_suite"))
    if preferred_suite:
        result["preferred_suite"] = preferred_suite

    interest_focus = attributes.get("interest_focus")
    if isinstance(interest_focus, list) and interest_focus:
        result["interest_focus"] = [str(f).strip() for f in interest_focus if str(f).strip()]

    if active_cfg.infa_field_vip and attributes.get("vip_flag") is not None:
        result["vip_status"] = str(attributes.get("vip_flag") or "").strip().upper() in {"Y", "YES", "TRUE", "1"}

    if active_cfg.infa_field_open_complaint and attributes.get("open_complaint") is not None:
        result["open_complaint_status"] = str(attributes.get("open_complaint") or "").strip().upper() in {
            "Y",
            "YES",
            "TRUE",
            "1",
        }

    consent_configured = bool((active_cfg.infa_field_consent or "").strip())
    if consent_configured:
        result["personalization_consent"] = str(attributes.get("consent_to_personalize") or "N").strip().upper() in {
            "Y",
            "YES",
            "TRUE",
            "1",
        }
        result["consent_configured"] = True
        result["demo_consent_assumed"] = False
    elif active_cfg.demo_assume_personalization_consent:
        result["personalization_consent"] = True
        result["consent_configured"] = False
        result["demo_consent_assumed"] = True
    else:
        result["personalization_consent"] = False
        result["consent_configured"] = False
        result["demo_consent_assumed"] = False

    try:
        bookings = provider.get_joined_bookings(customer_id)
    except ProfileSourceUnavailable:
        raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None

    booking_list: list[dict[str, Any]] = []
    for b in (bookings or [])[: active_cfg.infa_max_bookings]:
        item: dict[str, Any] = {}
        if b.get("booking_id") is not None:
            item["booking_id"] = b.get("booking_id")
        if b.get("voyage_ref") is not None:
            item["voyage_ref"] = b.get("voyage_ref")
        if b.get("voyage_name"):
            item["voyage_name"] = b.get("voyage_name")
        if b.get("destination"):
            item["destination"] = b.get("destination")
        if b.get("ship"):
            item["ship"] = b.get("ship")
        voyage_count = b.get("voyage_count")
        if voyage_count is not None and voyage_count != "":
            item["voyage_count"] = voyage_count
        booking_date = b.get("booking_date")
        if booking_date is not None and booking_date != "":
            item["booking_date"] = booking_date
        status_code = b.get("status_code")
        if status_code is not None and status_code != "":
            item["status_code"] = status_code
        status_label = b.get("status_label")
        if status_label is not None and status_label != "":
            item["status_label"] = status_label
        if item:
            booking_list.append(item)

    result["bookings"] = booking_list
    return result


@app.get("/api/guests", response_model=list[GuestSummary])
def list_guests() -> list[GuestSummary]:
    """List sample guests only when DEMO_MODE=true and not in informatica mode."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode == "informatica" or not active_cfg.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")
    return _active_provider().listSampleGuests()


@app.get("/api/guests/{rcyc_id}", response_model=GuestContextResponse)
def get_guest_context(rcyc_id: str) -> GuestContextResponse:
    """Retrieve minimized profile and bookings through GuestDataProvider."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode == "informatica":
        raise HTTPException(status_code=404, detail="Guest lookup disabled in informatica mode")

    provider = _active_provider()
    normalized = (rcyc_id or "").strip().upper()
    profile = provider.getProfile(normalized)

    if profile is None:
        return GuestContextResponse(status="not_found", profile=None, bookings=[], escalation=False)

    if profile.guest_status == "anonymous":
        return GuestContextResponse(
            status="anonymous",
            profile=to_public_profile(profile),
            bookings=[],
            escalation=False,
        )

    bookings = provider.getBookings(profile.rcyc_id) if profile.personalization_consent else []
    escalation_flag = bool(profile.open_complaint_status and profile.personalization_consent)
    return GuestContextResponse(
        status="found",
        profile=to_public_profile(profile),
        bookings=bookings,
        escalation=escalation_flag,
    )


@app.get("/api/voyages", response_model=list[Voyage])
def list_voyages(destination: str | None = Query(default=None)) -> list[Voyage]:
    """List catalog voyages through GuestDataProvider.listVoyages()."""
    voyages = _active_provider().listVoyages()
    if destination:
        target = destination.strip().lower()
        return [v for v in voyages if target in v.destination.lower()]
    return voyages


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: Request, payload: ChatRequest):
    """Process a natural-language concierge inquiry."""
    active_cfg = _active_settings()
    agent = _active_agent()
    if active_cfg.data_provider_mode == "informatica":
        role, customer_id = _session_info(request, active_cfg)
        if role == "visitor":
            client_ip = _client_ip(request)
            if not _check_and_record_visitor_chat(client_ip, time.monotonic()):
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "You have reached the visitor chat limit of 20 messages per 10 minutes. "
                            "Please wait a few minutes, or sign in for continued assistance from MARIS."
                        )
                    },
                )
            return agent.handle_chat(payload, session_customer_id=None, visitor_mode=True)
        if role != "guest" or not customer_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        store = _active_chat_store()
        target_conv_id: str | None = None
        server_history: list[ChatTurn] = []
        server_last_voyages: list[str] = []
        if payload.conversation_id is not None:
            conv_id_clean = payload.conversation_id.strip()
            recent_ctx = store.get_recent_context(customer_id, conv_id_clean, limit=8) if conv_id_clean else None
            if recent_ctx is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            target_conv_id = conv_id_clean
            recent_rows, server_last_voyages = recent_ctx
            server_history = [
                ChatTurn(
                    role=r["role"],
                    content=r["text"],
                    voyage_ids=list(r.get("last_voyages") or []),
                )
                for r in recent_rows
                if r.get("role") in {"user", "assistant"}
            ]

        try:
            response = agent.handle_chat(
                payload,
                session_customer_id=customer_id,
                conversation_history=server_history,
                last_voyages=server_last_voyages,
            )
        except ProfileSourceUnavailable:
            logger.warning("Profile source temporarily unavailable for /api/chat")
            raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None
        if not response.guest_recognized:
            resp = JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            _clear_session_cookie(resp)
            return resp

        saved = store.append_exchange(
            customer_id,
            target_conv_id,
            payload.message,
            response.reply,
            assistant_voyage_ids=response.context_voyage_ids,
        )
        if saved is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        response.conversation_id = saved["conversation_id"]
        response.conversation_title = saved["conversation_title"]
        response.user_message_id = saved["user_message_id"]
        response.assistant_message_id = saved["assistant_message_id"]
        response.user_created_at = saved["user_created_at"]
        response.assistant_created_at = saved["assistant_created_at"]
        return response

    return agent.handle_chat(payload)


@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations_endpoint(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
) -> ConversationListResponse:
    """List saved conversations for the signed-in guest, newest first, with optional server-side search."""
    customer_id = _require_guest_session(request, _active_settings())
    rows = _active_chat_store().list_conversations(customer_id, query=q)
    return ConversationListResponse(conversations=[ConversationSummary(**r) for r in rows])


@app.post("/api/conversations", response_model=ConversationSummary, status_code=201)
def create_conversation_endpoint(
    request: Request,
    payload: CreateConversationRequest | None = Body(default=None),
) -> ConversationSummary:
    """Create a new conversation scoped to the signed-in guest."""
    customer_id = _require_guest_session(request, _active_settings())
    title = payload.title if (payload and payload.title) else "New chat"
    created = _active_chat_store().create_conversation(customer_id, title=title)
    return ConversationSummary(**created)


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_endpoint(request: Request, conversation_id: str) -> ConversationDetailResponse:
    """Return messages for a conversation owned by the signed-in guest."""
    customer_id = _require_guest_session(request, _active_settings())
    conv = _active_chat_store().get_conversation(customer_id, conversation_id.strip())
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetailResponse(**conv)


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation_endpoint(
    request: Request,
    conversation_id: str,
    payload: RenameConversationRequest,
) -> ConversationSummary:
    """Rename a conversation owned by the signed-in guest (1-80 chars, trimmed)."""
    customer_id = _require_guest_session(request, _active_settings())
    updated = _active_chat_store().rename_conversation(customer_id, conversation_id.strip(), payload.title)
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSummary(**updated)


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation_endpoint(request: Request, conversation_id: str) -> dict[str, Any]:
    """Delete a conversation owned by the signed-in guest."""
    customer_id = _require_guest_session(request, _active_settings())
    deleted = _active_chat_store().delete_conversation(customer_id, conversation_id.strip())
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "id": conversation_id.strip()}


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback_endpoint(request: Request, payload: FeedbackRequest) -> FeedbackResponse:
    """Upsert helpful/not-helpful feedback for an assistant reply owned by the signed-in guest."""
    customer_id = _require_guest_session(request, _active_settings())
    try:
        saved = _active_chat_store().upsert_feedback(
            customer_id=customer_id,
            conversation_id=payload.conversation_id,
            message_id=payload.message_id,
            vote=payload.vote,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return FeedbackResponse(**saved)


@app.post("/api/conversations/title", response_model=ConversationTitleResponse)
def conversation_title_endpoint(request: Request, payload: ConversationTitleRequest) -> ConversationTitleResponse:
    """Generate a short 2-5 word conversation title from only the first guest message."""
    active_cfg = _active_settings()
    if active_cfg.data_provider_mode == "informatica":
        role, customer_id = _session_info(request, active_cfg)
        if role not in {"guest", "visitor"} or (role == "guest" and not customer_id):
            raise HTTPException(status_code=401, detail="Not authenticated")

    agent = _active_agent()
    title = agent.llm_engine.generate_conversation_title(payload.message)
    return ConversationTitleResponse(title=title)


@app.post("/api/escalate", response_model=EscalationInfo)
def escalate_endpoint(request: Request, payload: ChatRequest) -> EscalationInfo:
    """Trigger a simulated Experience Ambassador handoff."""
    active_cfg = _active_settings()
    provider = _active_provider()
    if active_cfg.data_provider_mode == "informatica":
        role, customer_id = _session_info(request, active_cfg)
        if role == "visitor":
            profile = build_anonymous_profile()
        elif role == "guest" and customer_id:
            try:
                profile = provider.getProfile(customer_id)
            except ProfileSourceUnavailable:
                raise HTTPException(status_code=503, detail="Guest profile service temporarily unavailable") from None
            if profile is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
    else:
        profile = provider.getProfile(payload.rcyc_id or "ANONYMOUS")
        if profile is None:
            profile = provider.getProfile("ANONYMOUS")
    msg = payload.message.strip() or "I want to speak with an Experience Ambassador."
    if "experience ambassador" not in msg.lower():
        msg = f"{msg} (Requesting Experience Ambassador)"
    return evaluate_escalation(profile, msg, payload.history)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.api_route("/", methods=["GET", "HEAD"])
def serve_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.api_route("/styles.css", methods=["GET", "HEAD"])
def serve_css() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.api_route("/app.js", methods=["GET", "HEAD"])
def serve_js() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting MARIS RCYC Concierge on port %s", settings.port)
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=settings.port, reload=False)
