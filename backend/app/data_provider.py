"""Unified Guest & Catalog Data Interface (MockProvider + AmperityProvider stub)."""

from __future__ import annotations

import copy
import datetime as _dt
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.app.config import Settings, logger, settings
from backend.app.models import (
    Booking,
    GuestProfile,
    GuestRecognitionStatus,
    GuestSummary,
    Voyage,
)

# Guest360 field and group keys verified against a live master record (from profile_source.py).
# Flat keys only; no entity prefix. Internal contact/identifier details are mapped
# for application use only and must never be sent to the browser, logs, or an LLM.
FIELD_MAP: dict[str, dict[str, str | None] | None] = {
    "rcyc_id": {"group": None, "field": "rcyc_id"},
    "guest_id": None,  # Skipped unless INFA_GUEST_ID_FIELD is configured
    "first_name": {"group": None, "field": "first_name"},
    "middle_name": None,
    "last_name": {"group": None, "field": "last_name"},
    "full_name": {"group": None, "field": "full_name"},
    "email": {"group": "email", "field": None},  # list: email_address, email_validation_status
    "phone": {"group": "phone", "field": None},  # list: phone_number, country_code, phone_validation_status
    "consent_to_personalize": None,  # Configured via INFA_FIELD_CONSENT; defaults to N
    "identifier_full": None,
    "identifier": {"group": "identifier", "field": None},  # list: _id, resco_guest_id
    "identifier_short": {"group": "identifier_short", "field": None},  # list: identifier_type, identifier_value
    "source_system": {"group": None, "field": "source_system"},
    "resco_guest_id": {"group": "identifier", "field": "resco_guest_id"},
    "loyalty_tier": None,
    "voyage_count": None,
    "last_voyage_region": None,
    "last_voyage_year": None,
    "preferred_suite": None,
    "top_ancillary": None,
    "preferred_regions": None,
    "interest_focus": None,
    "dietary_needs": None,
    "accessibility_needs": None,
    "vip_flag": None,
    "ltv_tier": None,
    "open_complaint": None,
    "active_booking": None,
}

PROFILE_ATTRIBUTE_FIELDS = (
    "first_name",
    "last_name",
    "full_name",
    "consent_to_personalize",
    "loyalty_tier",
    "voyage_count",
    "last_voyage_region",
    "last_voyage_year",
    "preferred_suite",
    "top_ancillary",
    "preferred_regions",
    "interest_focus",
    "dietary_needs",
    "accessibility_needs",
    "vip_flag",
    "ltv_tier",
    "open_complaint",
    "active_booking",
    "source_system",
    "resco_guest_id",
    "email",
    "phone",
    "identifier",
    "identifier_short",
)

BOOKING_FIELD_MAP = {
    "booking_id": "booking_id",
    "voyage_ref": "voyage_id_itinerary",
    "voyage_count": "voyage_count_lifetime_rolling_",
    "status_code": "booking_status",
    "fare": "voyage_fare_suite_revenue",
    "booking_date": "booking_recency_",
}


class ProfileSourceUnavailable(RuntimeError):
    """A configured external profile source cannot safely answer the request."""


class MultipleCustomerMatches(ProfileSourceUnavailable):
    """An exact Customer ID query returned more than one master record."""


class InactiveCustomerRecord(ProfileSourceUnavailable):
    """The exact Customer ID query returned a record marked as non-active."""


def normalize_booking_status(value: Any) -> tuple[str | None, str | None]:
    """Normalize a booking status lookup into (status_code, status_label)."""
    if isinstance(value, dict):
        code = value.get("Code")
        if code in (None, ""):
            code = value.get("Name")
        name = value.get("Name")
    elif value in (None, ""):
        code = None
        name = None
    else:
        code = value
        name = None

    code_str = None if code in (None, "") else str(code).strip()
    if code_str == "":
        code_str = None
    label_str = None if name in (None, "") else str(name).strip()
    if label_str == "":
        label_str = None
    if label_str is not None and code_str is not None and label_str == code_str:
        label_str = None
    return code_str, label_str


def parse_infa_field_path(raw: str | None) -> dict[str, str | None] | None:
    """Parse an env-configured Informatica field path in `group.field` or `field` style."""
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    if "." in cleaned:
        group, field = cleaned.split(".", 1)
        group = group.strip()
        field = field.strip()
        if not field:
            return None
        return {"group": group or None, "field": field}
    return {"group": None, "field": cleaned}


def effective_field_map(
    cfg: Settings | None = None,
    guest_id_field: str | None = None,
) -> dict[str, dict[str, str | None] | None]:
    active_cfg = cfg or settings
    field_map = {
        name: dict(spec) if isinstance(spec, dict) else None
        for name, spec in FIELD_MAP.items()
    }
    raw_guest_field = guest_id_field if guest_id_field is not None else active_cfg.infa_guest_id_field
    field_map["guest_id"] = parse_infa_field_path(raw_guest_field)

    optional_env_paths = {
        "loyalty_tier": active_cfg.infa_field_loyalty_tier,
        "preferred_regions": active_cfg.infa_field_preferred_regions,
        "preferred_suite": active_cfg.infa_field_preferred_suite,
        "interest_focus": active_cfg.infa_field_interest_focus,
        "consent_to_personalize": active_cfg.infa_field_consent,
        "vip_flag": active_cfg.infa_field_vip,
        "open_complaint": active_cfg.infa_field_open_complaint,
    }
    for attr_name, raw_path in optional_env_paths.items():
        parsed = parse_infa_field_path(raw_path)
        if parsed is not None:
            field_map[attr_name] = parsed
    return field_map


def _values_for_key(value: Any, key: str):
    if isinstance(value, dict):
        for candidate, child in value.items():
            if candidate == key:
                yield child
            yield from _values_for_key(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _values_for_key(child, key)


def _scalar_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        values: list[Any] = []
        for child in value.values():
            values.extend(_scalar_values(child))
        return values
    if isinstance(value, list):
        values = []
        for child in value:
            values.extend(_scalar_values(child))
        return values
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    return [value]


def mapped_values(record: dict[str, Any], spec: dict[str, Any] | None) -> list[Any]:
    if not spec or not spec.get("field"):
        return []
    group = spec.get("group")
    containers = list(_values_for_key(record, group)) if group else [record]
    values: list[Any] = []
    for container in containers:
        for value in _values_for_key(container, str(spec["field"])):
            values.extend(_scalar_values(value))
    return values


def _consent_value(values: list[Any]) -> str:
    if not values:
        return "N"
    normalized = {str(value).strip().upper() for value in values}
    if len(normalized) != 1:
        return "N"
    value = normalized.pop()
    if value in {"Y", "YES", "TRUE", "1"}:
        return "Y"
    if value in {"N", "NO", "FALSE", "0"}:
        return "N"
    return "N"


def map_informatica_attributes(
    record: dict[str, Any],
    field_map: dict[str, dict[str, str | None] | None] | None = None,
) -> dict[str, Any]:
    resolved_map = field_map or effective_field_map()
    attributes: dict[str, Any] = {name: None for name in PROFILE_ATTRIBUTE_FIELDS}
    for name in PROFILE_ATTRIBUTE_FIELDS:
        if name == "consent_to_personalize":
            attributes[name] = _consent_value(mapped_values(record, resolved_map.get(name)))
            continue
        spec = resolved_map.get(name)
        group = spec.get("group") if isinstance(spec, dict) else None
        field = spec.get("field") if isinstance(spec, dict) else None
        if group and not field:
            containers = list(_values_for_key(record, group))
            flattened: list[Any] = []
            for container in containers:
                if isinstance(container, list):
                    flattened.extend(container)
                else:
                    flattened.append(container)
            attributes[name] = flattened if flattened else None
            continue
        if name == "resco_guest_id":
            values = mapped_values(record, spec)
            if not values:
                for container in _values_for_key(record, "identifier_short"):
                    entries = container if isinstance(container, list) else [container]
                    for entry in entries:
                        if isinstance(entry, dict):
                            type_value = entry.get("identifier_type")
                            if isinstance(type_value, dict):
                                type_name = type_value.get("Name") or type_value.get("Code")
                            else:
                                type_name = type_value
                            if str(type_name).strip() == "Resco Guest ID":
                                value = entry.get("identifier_value")
                                if value not in (None, ""):
                                    values = [value]
                                    break
                    if values:
                        break
            if values:
                attributes[name] = values[0]
            continue
        values = mapped_values(record, spec)
        if name in {"preferred_regions", "interest_focus"}:
            if values:
                expanded: list[str] = []
                for item in values:
                    for part in str(item).split(","):
                        cleaned_part = part.strip()
                        if cleaned_part and cleaned_part not in expanded:
                            expanded.append(cleaned_part)
                attributes[name] = expanded if expanded else None
            continue
        if values:
            attributes[name] = values[0]
    return attributes


def _usable_name(value: Any) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    if not name or name.casefold() in {"none", "null", "undefined"}:
        return None
    return name


def mask_email(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text or "@" not in text:
        return None
    local, _, domain = text.partition("@")
    if not local or not domain:
        return None
    return f"{local[0]}***@{domain}"


def mask_phone(entry: Any) -> str | None:
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


def build_anonymous_profile() -> GuestProfile:
    """Return a clean prospect profile for anonymous visitors."""
    return GuestProfile(
        rcyc_id="ANONYMOUS",
        first_name="Visitor",
        last_name="",
        loyalty_tier="Visitor",
        past_voyages=0,
        previous_voyage_region="None",
        sailed_regions=[],
        preferred_suite="Not Specified",
        interest_focus=[],
        ancillary_purchase_preferences=[],
        preferred_destinations=[],
        dietary_requirements="None",
        accessibility_requirements="None",
        vip_status=False,
        open_complaint_status=False,
        complaint_summary="",
        personalization_consent=False,
        profile_label="Anonymous Visitor",
        guest_status="anonymous",
    )


class GuestDataProvider(ABC):
    """Single data access interface used by all concierge logic and API routes."""

    @abstractmethod
    def getProfile(self, guestId: str) -> GuestProfile | None:
        """Retrieve a guest profile by RCYC_ID, or None if not found."""

    @abstractmethod
    def getBookings(self, guestId: str) -> list[Booking]:
        """Retrieve bookings for the given RCYC_ID."""

    @abstractmethod
    def listVoyages(self) -> list[Voyage]:
        """Retrieve all voyages from the catalog."""

    @abstractmethod
    def listSampleGuests(self) -> list[GuestSummary]:
        """Retrieve sample guest summaries for the demo selector."""

    def getMaskedContactInfo(self, guestId: str) -> dict[str, str | None]:
        """Retrieve only masked email and phone for the verified guest (never unmasked)."""
        return {"email": None, "phone": None}


class MockProvider(GuestDataProvider):
    """Local JSON provider reading sample guests, bookings, and voyages."""

    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path
        self._profiles: dict[str, GuestProfile] = {}
        self._bookings: dict[str, list[Booking]] = {}
        self._voyages: list[Voyage] = []
        self.reload()

    def reload(self) -> None:
        if not self.json_path.exists():
            raise FileNotFoundError(f"Sample JSON file not found: {self.json_path}")

        raw = json.loads(self.json_path.read_text(encoding="utf-8"))

        profiles: dict[str, GuestProfile] = {}
        for item in raw.get("guests", []):
            rcyc_id = str(item["rcyc_id"]).strip().upper()
            past_voyages = int(item.get("past_voyages", 0))
            status: GuestRecognitionStatus = "returning" if past_voyages > 0 else "new"
            profiles[rcyc_id] = GuestProfile(
                rcyc_id=rcyc_id,
                first_name=item["first_name"],
                last_name=item["last_name"],
                loyalty_tier=item.get("loyalty_tier", "Member"),
                past_voyages=past_voyages,
                previous_voyage_region=item.get("previous_voyage_region", "None"),
                sailed_regions=list(item.get("sailed_regions", [])),
                preferred_suite=item.get("preferred_suite", "Terrace Suite"),
                interest_focus=list(item.get("interest_focus", [])),
                ancillary_purchase_preferences=list(item.get("ancillary_purchase_preferences", [])),
                preferred_destinations=list(item.get("preferred_destinations", [])),
                dietary_requirements=item.get("dietary_requirements", "None"),
                accessibility_requirements=item.get("accessibility_requirements", "None"),
                vip_status=bool(item.get("vip_status", False)),
                open_complaint_status=bool(item.get("open_complaint_status", False)),
                complaint_summary=item.get("complaint_summary", ""),
                personalization_consent=bool(item.get("personalization_consent", True)),
                profile_label=item.get("profile_label", ""),
                guest_status=status,
            )

        bookings_map: dict[str, list[Booking]] = {}
        for b in raw.get("bookings", []):
            gid = str(b["rcyc_id"]).strip().upper()
            bookings_map.setdefault(gid, []).append(Booking(**b))

        voyages = [Voyage(**v) for v in raw.get("voyages", [])]

        self._profiles = profiles
        self._bookings = bookings_map
        self._voyages = voyages
        logger.info(
            "MockProvider loaded %d sample guests, %d bookings, %d voyages from %s",
            len(self._profiles),
            sum(len(v) for v in self._bookings.values()),
            len(self._voyages),
            self.json_path,
        )

    def getProfile(self, guestId: str) -> GuestProfile | None:
        normalized = (guestId or "").strip().upper()
        if not normalized or normalized == "ANONYMOUS":
            return build_anonymous_profile()
        return self._profiles.get(normalized)

    def getBookings(self, guestId: str) -> list[Booking]:
        normalized = (guestId or "").strip().upper()
        if not normalized or normalized == "ANONYMOUS":
            return []
        return list(self._bookings.get(normalized, []))

    def listVoyages(self) -> list[Voyage]:
        return list(self._voyages)

    def listSampleGuests(self) -> list[GuestSummary]:
        return [
            GuestSummary(
                rcyc_id=p.rcyc_id,
                full_name=p.full_name,
                loyalty_tier=p.loyalty_tier,
                past_voyages=p.past_voyages,
                open_complaint_status=p.open_complaint_status,
                personalization_consent=p.personalization_consent,
                profile_label=p.profile_label,
                guest_status=p.guest_status,
            )
            for p in self._profiles.values()
        ]


class InformaticaProvider(GuestDataProvider):
    """Informatica Business 360 GuestDataProvider ported from profile_source.py."""

    def __init__(self, cfg: Settings | None = None) -> None:
        active_cfg = cfg or settings
        self._cfg = active_cfg
        self.sample_data_json = active_cfg.sample_data_json
        self.login_url = active_cfg.infa_login_url
        self.username = active_cfg.infa_username
        self.password = active_cfg.infa_password
        self.entity = active_cfg.infa_entity or "guest360"
        self.guest_id_field = active_cfg.infa_guest_id_field
        self.customer_id_field = active_cfg.infa_customer_id_field or "rcyc_id"
        self.model_version = active_cfg.infa_model_version
        self.timeout_seconds = max(float(active_cfg.infa_timeout_seconds), 0.0)
        self.cache_seconds = max(float(active_cfg.infa_cache_seconds), 0.0)
        self.max_bookings = max(int(active_cfg.infa_max_bookings), 1)
        self._session_id: str | None = None
        self._base_api_url: str | None = None
        self._profile_cache: dict[str, tuple[float, Any]] = {}
        self._customer_lookup_cache: dict[str, tuple[float, str | None, str | None]] = {}
        self.request_log: list[dict[str, str]] = []
        self._voyages_cache: list[Voyage] | None = None

    def _send_with_rate_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                # UNCONFIRMED: Uses httpx.request (requests is not installed); profile_source.py line 310 used requests.request.
                response = httpx.request(
                    method,
                    url,
                    headers=headers,
                    json=body,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                self._record_request(method, url, "NO_RESPONSE")
                raise ProfileSourceUnavailable from exc
            except httpx.HTTPError as exc:
                self._record_request(method, url, "NO_RESPONSE")
                raise ProfileSourceUnavailable from exc
            self._record_request(method, url, str(response.status_code))
            if response.status_code == 429 and attempt == 0:
                time.sleep(0.25)
                continue
            if response.status_code == 429:
                logger.warning("Informatica rate limit persisted after retry")
                raise ProfileSourceUnavailable
            return response
        raise ProfileSourceUnavailable

    def _record_request(self, method: str, url: str, status: str) -> None:
        parsed = urlsplit(url)
        path_parts = parsed.path.split("/")
        for index, part in enumerate(path_parts):
            if part == "entity" and index + 2 < len(path_parts):
                path_parts[index + 2] = "<record>"
            elif re.fullmatch(r"\d{6,}|[0-9a-fA-F-]{24,}", part):
                path_parts[index] = "<id>"
        request_summary = {
            "method": method,
            "host": parsed.hostname or "unknown",
            "path": "/".join(path_parts) or "/",
            "status": status,
        }
        self.request_log.append(request_summary)
        log_method = logger.warning if status == "NO_RESPONSE" or (status.isdigit() and int(status) >= 400) else logger.info
        log_method(
            "Informatica request method=%s host=%s path=%s status=%s",
            request_summary["method"],
            request_summary["host"],
            request_summary["path"],
            request_summary["status"],
        )

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code >= 500:
            logger.warning("Informatica service returned a server error")
        else:
            logger.warning("Informatica request was rejected")
        raise ProfileSourceUnavailable

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            logger.warning("Informatica returned an unreadable response")
            raise ProfileSourceUnavailable from exc
        if not isinstance(payload, dict):
            logger.warning("Informatica returned an unexpected response shape")
            raise ProfileSourceUnavailable
        return payload

    @staticmethod
    def _business_360_base_api_url(base_api_url: str) -> str:
        parsed = urlsplit(base_api_url)
        if not parsed.scheme or not parsed.hostname:
            logger.warning("Informatica login returned an invalid base API URL")
            raise ProfileSourceUnavailable
        host_parts = parsed.hostname.split(".")
        if not host_parts[0].endswith("-mdm"):
            host_parts[0] += "-mdm"
        hostname = ".".join(host_parts)
        netloc = f"{hostname}:{parsed.port}" if parsed.port else hostname
        path = parsed.path.rstrip("/")
        if path.endswith("/saas"):
            path = path[: -len("/saas")]
        return urlunsplit((parsed.scheme, netloc, path, "", "")).rstrip("/")

    def login(self) -> None:
        if not self.login_url or not self.username or not self.password:
            logger.warning("Informatica login configuration is incomplete")
            raise ProfileSourceUnavailable
        response = self._send_with_rate_retry(
            "POST",
            self.login_url,
            {"Accept": "application/json", "Content-Type": "application/json"},
            {"username": self.username, "password": self.password},
        )
        self._require_success(response)
        payload = self._json_object(response)
        user_info = payload.get("userInfo") or {}
        products = payload.get("products") or []
        base_api_url = payload.get("baseApiUrl")
        if not base_api_url and isinstance(products, list):
            base_api_url = next(
                (product.get("baseApiUrl") for product in products if isinstance(product, dict) and product.get("baseApiUrl")),
                None,
            )
        session_id = user_info.get("sessionId") if isinstance(user_info, dict) else None
        session_id = session_id or payload.get("sessionId")
        if not session_id or not base_api_url:
            logger.warning("Informatica login response is missing session metadata")
            raise ProfileSourceUnavailable
        self._session_id = str(session_id)
        self._base_api_url = self._business_360_base_api_url(str(base_api_url))

    def _api_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
        if not self.model_version:
            logger.warning("Informatica model version is not configured")
            raise ProfileSourceUnavailable
        if not self._session_id or not self._base_api_url:
            self.login()

        url = f"{self._base_api_url}/{path.lstrip('/')}"
        for auth_attempt in range(2):
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "IDS-SESSION-ID": self._session_id or "",
                "MODEL_VERSION": self.model_version,
            }
            response = self._send_with_rate_retry(method, url, headers, body)
            if response.status_code == 401 and auth_attempt == 0:
                self._session_id = None
                self._base_api_url = None
                self.login()
                continue
            if response.status_code == 401:
                logger.warning("Informatica authorization failed after re-login")
                raise ProfileSourceUnavailable
            self._require_success(response)
            return response
        raise ProfileSourceUnavailable

    @staticmethod
    def _search_record_field_value(record: dict[str, Any], qualified_field_name: str) -> Any:
        if qualified_field_name in record:
            return record[qualified_field_name]
        fields = record.get("fields")
        if isinstance(fields, dict) and qualified_field_name in fields:
            return fields[qualified_field_name]
        entity_name, separator, field_name = qualified_field_name.partition(".")
        entity_fields = record.get(entity_name) if separator else None
        if isinstance(entity_fields, dict):
            return entity_fields.get(field_name)
        return None

    def _search_guest_result(self, guest_id: str, field_name: str | None = None) -> tuple[str | None, str | None]:
        if not self.model_version:
            logger.warning("Informatica model version is not configured")
            raise ProfileSourceUnavailable
        resolved_field = field_name or self.guest_id_field
        customer_field = f"{self.entity}.{resolved_field}"
        search_body = {
            "entityType": self.entity,
            "fields": {customer_field: f'"{guest_id}"'},
            "filters": {
                "operator": "AND",
                "filter": [
                    {
                        "comparator": "EQUALS",
                        "fieldName": customer_field,
                        "fieldValue": guest_id,
                    },
                ],
            },
            "pageSize": 25,
            "pageOffset": 0,
            "recordsToReturn": 25,
            "recordOffset": 0,
        }
        payload = self._json_object(
            self._api_request("POST", "/search/public/api/v1/search", search_body)
        )
        search_result = payload.get("searchResult", {})
        if not isinstance(search_result, dict):
            return None, "ID_NOT_FOUND"
        hits = search_result.get("hits", 0)
        records = search_result.get("records", [])
        if not isinstance(hits, int) or hits <= 0:
            return None, "ID_NOT_FOUND"
        if hits > 1:
            logger.warning("Multiple Informatica records matched the exact customer ID; refusing ambiguous lookup")
            return None, "MULTIPLE_MATCHES"
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            return None, "ID_NOT_FOUND"

        record = records[0]
        record_field_value = self._search_record_field_value(record, customer_field)
        if record_field_value is None or str(record_field_value) != str(guest_id):
            return None, "ID_MISMATCH"
        metadata = record.get("_meta")
        metadata = metadata if isinstance(metadata, dict) else {}
        states = metadata.get("states")
        states = states if isinstance(states, dict) else {}
        record_state = states.get("recordStateIndicator")
        if record_state is not None and str(record_state).strip().upper() != "ACTIVE":
            return None, "INACTIVE_RECORD"

        business_id = metadata.get("businessId")
        if not business_id:
            logger.warning("Informatica search result did not contain a business ID")
            raise ProfileSourceUnavailable
        return str(business_id), None

    def _customer_business_lookup(self, customer_id: str) -> tuple[str | None, str | None]:
        now = time.monotonic()
        cached = self._customer_lookup_cache.get(customer_id)
        if cached and cached[0] > now:
            return cached[1], cached[2]
        business_id, reason = self._search_guest_result(customer_id, field_name=self.customer_id_field)
        self._customer_lookup_cache[customer_id] = (now + self.cache_seconds, business_id, reason)
        return business_id, reason

    def _customer_business_id(self, customer_id: str) -> str | None:
        business_id, _reason = self._customer_business_lookup(customer_id)
        return business_id

    def customer_id_exists(self, customer_id: str) -> bool:
        return self._customer_business_id(customer_id) is not None

    def customer_id_failure_reason(self, customer_id: str) -> str | None:
        try:
            business_id, reason = self._customer_business_lookup(customer_id)
        except ProfileSourceUnavailable:
            return None
        return None if business_id else reason

    def read_master_record_for_entity(self, entity: str, business_id: str) -> dict[str, Any]:
        response = self._api_request("GET", f"/business-entity/public/api/v1/entity/{entity}/{business_id}")
        return self._json_object(response)

    def read_master_record(self, business_id: str) -> dict[str, Any]:
        response = self._api_request(
            "GET",
            f"/business-entity/public/api/v1/entity/{self.entity}/{business_id}",
        )
        return self._json_object(response)

    def get_raw_profile(self, customer_id: str) -> dict[str, Any] | None:
        now = time.monotonic()
        cached = self._profile_cache.get(customer_id)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1])

        business_id = self._customer_business_id(customer_id)
        if business_id is None:
            self._profile_cache[customer_id] = (now + self.cache_seconds, None)
            return None
        master_record = self.read_master_record(business_id)
        field_map = effective_field_map(self._cfg, self.guest_id_field)
        profile = {
            "profile_id": business_id,
            "attributes": map_informatica_attributes(master_record, field_map=field_map),
        }
        self._profile_cache[customer_id] = (now + self.cache_seconds, profile)
        return copy.deepcopy(profile)

    def get_raw_bookings(self, customer_id: str) -> list[dict[str, Any]]:
        guest_business_id = self._customer_business_id(customer_id)
        if not guest_business_id:
            return []
        now = time.monotonic()
        cache_key = f"bookings:{guest_business_id}"
        cached = self._profile_cache.get(cache_key)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1] or [])

        payload = self._json_object(
            self._api_request(
                "POST",
                "/business-entity/public/api/v1/relationship/rel_g360_to_booking/filter",
                {
                    "pageOffset": 0,
                    "pageSize": self.max_bookings,
                    "filter": {"_from": {"businessEntity": "guest360", "businessId": guest_business_id}},
                },
            )
        )
        content = payload.get("content", [])
        if not isinstance(content, list):
            content = []
        bookings: list[dict[str, Any]] = []
        for item in content[: self.max_bookings]:
            if not isinstance(item, dict):
                continue
            from_info = item.get("_from")
            to_info = item.get("_to")
            if not isinstance(from_info, dict) or not isinstance(to_info, dict):
                logger.warning("Informatica booking relationship item missing endpoints")
                continue
            if from_info.get("businessId") != guest_business_id:
                logger.warning("Informatica booking relationship from-id mismatch")
                continue
            if to_info.get("businessEntity") != "booking":
                logger.warning("Informatica booking relationship target is not booking")
                continue
            booking_bid = to_info.get("businessId")
            if not booking_bid:
                continue
            try:
                record = self.read_master_record_for_entity("booking", str(booking_bid))
            except Exception:
                logger.warning("Informatica booking read failed")
                continue
            booking: dict[str, Any] = {}
            for key, field in BOOKING_FIELD_MAP.items():
                if key == "status_code":
                    continue
                if field in record and record.get(field) not in (None, ""):
                    booking[key] = record.get(field)
            status_code, status_label = normalize_booking_status(record.get("booking_status"))
            if status_code not in (None, ""):
                booking["status_code"] = status_code
            if status_label not in (None, ""):
                booking["status_label"] = status_label
            bookings.append(booking)

        def _parse_date(value: Any) -> _dt.datetime | None:
            if value is None:
                return None
            text = str(value).strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return _dt.datetime.strptime(text, fmt)
                except ValueError:
                    continue
            return None

        dated = [(_parse_date(b.get("booking_date")), i, b) for i, b in enumerate(bookings)]
        dated.sort(key=lambda x: (x[0] is None, -(x[0].timestamp() if x[0] else 0), x[1]))
        sorted_bookings = [b for _, _, b in dated]
        self._profile_cache[cache_key] = (now + self.cache_seconds, sorted_bookings)
        return copy.deepcopy(sorted_bookings)

    def _catalog_by_voyage_id(self) -> dict[str, Voyage]:
        return {v.voyage_id.strip().upper(): v for v in self.listVoyages()}

    def get_joined_bookings(self, customer_id: str) -> list[dict[str, Any]]:
        """Return raw Informatica bookings enriched with local catalog fields when matched."""
        raw_bookings = self.get_raw_bookings(customer_id)
        catalog_by_id = self._catalog_by_voyage_id()
        joined: list[dict[str, Any]] = []
        for raw_b in raw_bookings:
            item = dict(raw_b)
            voyage_ref = str(item.get("voyage_ref") or "").strip()
            matched = catalog_by_id.get(voyage_ref.upper()) if voyage_ref else None
            if matched is not None:
                item["voyage_name"] = matched.voyage_name
                item["destination"] = matched.destination
                item["ship"] = matched.yacht_name
            joined.append(item)
        return joined

    def getProfile(self, guestId: str) -> GuestProfile | None:
        cleaned = (guestId or "").strip()
        if not cleaned or cleaned.upper() == "ANONYMOUS":
            return build_anonymous_profile()
        raw = self.get_raw_profile(cleaned)
        if not raw:
            return None
        attrs = raw.get("attributes", {}) or {}
        first_name = _usable_name(attrs.get("first_name")) or ""
        last_name = _usable_name(attrs.get("last_name")) or ""

        raw_bookings = self.get_raw_bookings(cleaned)
        joined_bookings = self.getBookings(cleaned)
        matched_bookings = [b for b in joined_bookings if b.destination]
        sailed_regions = list(dict.fromkeys(b.destination for b in matched_bookings))
        previous_voyage_region = next((b.destination for b in matched_bookings), "None")

        rolling_counts: list[int] = []
        for rb in raw_bookings:
            val = rb.get("voyage_count")
            if val in (None, ""):
                continue
            try:
                rolling_counts.append(int(float(str(val).strip())))
            except (TypeError, ValueError):
                continue
        past_voyages = max(rolling_counts) if rolling_counts else len(raw_bookings)
        guest_status: GuestRecognitionStatus = "returning" if len(raw_bookings) >= 1 else "new"

        loyalty_tier = _usable_name(attrs.get("loyalty_tier")) or ""
        preferred_suite = _usable_name(attrs.get("preferred_suite")) or ""
        raw_pref_regions = attrs.get("preferred_regions")
        if isinstance(raw_pref_regions, list):
            preferred_destinations = [str(r).strip() for r in raw_pref_regions if str(r).strip()]
        elif isinstance(raw_pref_regions, str) and raw_pref_regions.strip():
            preferred_destinations = [r.strip() for r in raw_pref_regions.split(",") if r.strip()]
        else:
            preferred_destinations = []

        raw_interest = attrs.get("interest_focus")
        if isinstance(raw_interest, list):
            interest_focus = [str(f).strip().lower() for f in raw_interest if str(f).strip()]
        elif isinstance(raw_interest, str) and raw_interest.strip():
            interest_focus = [f.strip().lower() for f in raw_interest.split(",") if f.strip()]
        else:
            interest_focus = []

        consent_field_configured = bool((self._cfg.infa_field_consent or "").strip())
        if consent_field_configured:
            consent = str(attrs.get("consent_to_personalize") or "N").strip().upper() in {"Y", "YES", "TRUE", "1"}
            consent_assumed = False
        elif self._cfg.demo_assume_personalization_consent:
            consent = True
            consent_assumed = True
        else:
            consent = False
            consent_assumed = False

        vip_flag = str(attrs.get("vip_flag") or "").strip().upper() in {"Y", "YES", "TRUE", "1"}
        open_complaint = str(attrs.get("open_complaint") or "").strip().upper() in {"Y", "YES", "TRUE", "1"}

        return GuestProfile(
            rcyc_id=cleaned,
            first_name=first_name,
            last_name=last_name,
            loyalty_tier=loyalty_tier,
            past_voyages=past_voyages,
            previous_voyage_region=previous_voyage_region,
            sailed_regions=sailed_regions,
            preferred_suite=preferred_suite,
            interest_focus=interest_focus,
            ancillary_purchase_preferences=[],
            preferred_destinations=preferred_destinations,
            dietary_requirements="None",
            accessibility_requirements="None",
            vip_status=vip_flag,
            open_complaint_status=open_complaint,
            complaint_summary="",
            personalization_consent=consent,
            consent_assumed=consent_assumed,
            profile_label="",
            guest_status=guest_status,
        )

    def getBookings(self, guestId: str) -> list[Booking]:
        cleaned = (guestId or "").strip()
        if not cleaned or cleaned.upper() == "ANONYMOUS":
            return []
        joined_bookings = self.get_joined_bookings(cleaned)
        results: list[Booking] = []
        for b in joined_bookings:
            results.append(
                Booking(
                    booking_id=str(b.get("booking_id") or ""),
                    rcyc_id=cleaned,
                    voyage_id=str(b.get("voyage_ref") or ""),
                    voyage_name=str(b.get("voyage_name") or ""),
                    destination=str(b.get("destination") or ""),
                    ship=str(b.get("ship") or ""),
                    suite_category="",
                    booked_on=str(b.get("booking_date") or ""),
                    sailing_dates=None,
                    status_code=str(b.get("status_code") or ""),
                    status_label=str(b.get("status_label") or ""),
                )
            )
        return results

    def listVoyages(self) -> list[Voyage]:
        if self._voyages_cache is not None:
            return list(self._voyages_cache)
        if not self.sample_data_json.exists():
            return []
        raw = json.loads(self.sample_data_json.read_text(encoding="utf-8"))
        self._voyages_cache = [Voyage(**v) for v in raw.get("voyages", [])]
        return list(self._voyages_cache)

    def listSampleGuests(self) -> list[GuestSummary]:
        return []

    def getMaskedContactInfo(self, guestId: str) -> dict[str, str | None]:
        cleaned = (guestId or "").strip()
        if not cleaned or cleaned.upper() == "ANONYMOUS":
            return {"email": None, "phone": None}
        profile = self.get_raw_profile(cleaned)
        if not profile:
            return {"email": None, "phone": None}
        attrs = profile.get("attributes", {}) or {}
        masked_email: str | None = None
        email_entries = attrs.get("email")
        if isinstance(email_entries, list):
            for entry in email_entries:
                if isinstance(entry, dict):
                    masked_email = mask_email(entry.get("email_address"))
                    if masked_email:
                        break
        masked_phone: str | None = None
        phone_entries = attrs.get("phone")
        if isinstance(phone_entries, list):
            for entry in phone_entries:
                if isinstance(entry, dict):
                    masked_phone = mask_phone(entry)
                    if masked_phone:
                        break
        return {"email": masked_email, "phone": masked_phone}


class AmperityProvider(GuestDataProvider):
    """
    Placeholder stub for future Amperity integration.

    TODO: Implement authenticated Amperity Profile API client when tenant,
    index schema, and credentials are provisioned in server environment variables.
    """

    def getProfile(self, guestId: str) -> GuestProfile | None:
        raise NotImplementedError("AmperityProvider.getProfile is not implemented yet.")

    def getBookings(self, guestId: str) -> list[Booking]:
        raise NotImplementedError("AmperityProvider.getBookings is not implemented yet.")

    def listVoyages(self) -> list[Voyage]:
        raise NotImplementedError("AmperityProvider.listVoyages is not implemented yet.")

    def listSampleGuests(self) -> list[GuestSummary]:
        raise NotImplementedError("AmperityProvider.listSampleGuests is not supported in live mode.")


def create_data_provider(cfg: Settings | None = None) -> GuestDataProvider:
    """Factory returning the configured GuestDataProvider."""
    active_cfg = cfg or settings
    if active_cfg.data_provider_mode == "informatica":
        return InformaticaProvider(active_cfg)
    if active_cfg.data_provider_mode == "amperity":
        return AmperityProvider()
    return MockProvider(active_cfg.sample_data_json)
