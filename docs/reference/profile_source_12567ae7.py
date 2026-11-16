import copy
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
import time
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests


DATA_DIR = Path(__file__).resolve().parent / "data"
logger = logging.getLogger(__name__)

# Guest360 field and group keys verified against a live master record.
# Flat keys only; no entity prefix. Internal contact/identifier details are mapped
# for application use only and must never be sent to the browser, logs, or an LLM.
FIELD_MAP = {
    "rcyc_id": {"group": None, "field": "rcyc_id"},
    "guest_id": {"group": None, "field": None},  # TO VERIFY; env-driven in effective_field_map
    "first_name": {"group": None, "field": "first_name"},
    "middle_name": {"group": None, "field": None},  # TO VERIFY
    "last_name": {"group": None, "field": "last_name"},
    "full_name": {"group": None, "field": "full_name"},
    "email": {"group": "email", "field": None},  # list: email_address, email_validation_status
    "phone": {"group": "phone", "field": None},  # list: phone_number, country_code, phone_validation_status
    "consent_to_personalize": None,  # no consent field in live record; defaults to N
    "identifier_full": {"group": "IdentifierFull", "field": None},  # TO VERIFY
    "identifier": {"group": "identifier", "field": None},  # list: _id, resco_guest_id
    "identifier_short": {"group": "identifier_short", "field": None},  # list: identifier_type, identifier_value
    "source_system": {"group": None, "field": "source_system"},
    "resco_guest_id": {"group": "identifier", "field": "resco_guest_id"},  # first entry; fallback below
    "loyalty_tier": None,
    "voyage_count": None,
    "last_voyage_region": None,
    "last_voyage_year": None,
    "preferred_suite": None,
    "top_ancillary": None,
    "preferred_regions": None,
    "dietary_needs": None,
    "accessibility_needs": None,
    "vip_flag": None,
    "ltv_tier": None,
    "open_complaint": None,
    "active_booking": None,
}

PROFILE_ATTRIBUTE_FIELDS = (
    "first_name", "last_name", "full_name", "consent_to_personalize", "loyalty_tier", "voyage_count",
    "last_voyage_region", "last_voyage_year", "preferred_suite", "top_ancillary",
    "preferred_regions", "dietary_needs", "accessibility_needs", "vip_flag",
    "ltv_tier", "open_complaint", "active_booking",
    "source_system", "resco_guest_id", "email", "phone", "identifier", "identifier_short",
)


BOOKING_FIELD_MAP = {
    "booking_id": "booking_id",
    "voyage_ref": "voyage_id_itinerary",
    "voyage_count": "voyage_count_lifetime_rolling_",
    "status_code": "booking_status",
    "fare": "voyage_fare_suite_revenue",
    "booking_date": "booking_recency_",
}


def normalize_booking_status(value) -> tuple[str | None, str | None]:
    """Normalize a booking status lookup into (status_code, status_label).

    Informatica returns ``booking_status`` as a lookup object shaped like
    ``{"Code": ..., "Name": ...}``.  ``status_code`` is always the string
    ``Code`` (or the plain string itself).  ``status_label`` is ``Name`` only
    when it is non-empty and different from ``Code``; otherwise ``None`` so a
    code is never presented as a human-readable description.  A raw dict is
    never returned.
    """
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


class ProfileSourceUnavailable(RuntimeError):
    """A configured external profile source cannot safely answer the request."""


class MultipleCustomerMatches(ProfileSourceUnavailable):
    """An exact Customer ID query returned more than one master record."""


class InactiveCustomerRecord(ProfileSourceUnavailable):
    """The exact Customer ID query returned a record marked as non-active."""


def effective_field_map() -> dict:
    field_map = {
        name: dict(spec) if isinstance(spec, dict) else None
        for name, spec in FIELD_MAP.items()
    }
    guest_id_field = os.getenv("INFA_GUEST_ID_FIELD", "guest_id").strip() or "guest_id"
    field_map["guest_id"] = {"group": None, "field": guest_id_field}
    return field_map


def _values_for_key(value, key: str):
    if isinstance(value, dict):
        for candidate, child in value.items():
            if candidate == key:
                yield child
            yield from _values_for_key(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _values_for_key(child, key)


def _scalar_values(value) -> list:
    if isinstance(value, dict):
        values = []
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


def mapped_values(record: dict, spec: dict | None) -> list:
    if not spec or not spec.get("field"):
        return []
    group = spec.get("group")
    containers = list(_values_for_key(record, group)) if group else [record]
    values = []
    for container in containers:
        for value in _values_for_key(container, spec["field"]):
            values.extend(_scalar_values(value))
    return values


def _consent_value(values: list) -> str:
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


def map_informatica_attributes(record: dict, field_map: dict | None = None) -> dict:
    field_map = field_map or effective_field_map()
    attributes = {name: None for name in PROFILE_ATTRIBUTE_FIELDS}
    for name in PROFILE_ATTRIBUTE_FIELDS:
        if name == "consent_to_personalize":
            attributes[name] = _consent_value(mapped_values(record, field_map.get(name)))
            continue
        spec = field_map.get(name)
        group = spec.get("group") if isinstance(spec, dict) else None
        field = spec.get("field") if isinstance(spec, dict) else None
        # Group-valued internal attributes (email, phone, identifier, identifier_short)
        # are stored as the raw list of entry dicts so internal code can inspect them.
        if group and not field:
            containers = list(_values_for_key(record, group))
            flattened = []
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
                # Fallback to identifier_short entry typed "Resco Guest ID".
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
        if values:
            attributes[name] = values[0]
    return attributes


@lru_cache(maxsize=1)
def _guest_profiles() -> dict[str, dict]:
    path = DATA_DIR / "guests.xlsx"
    frame = pd.read_excel(path, dtype={"RCYC_ID": str}).fillna("")
    profiles = {}
    for row in frame.to_dict(orient="records"):
        profile_id = str(row.pop("RCYC_ID")).strip()
        row["voyage_count"] = int(row["voyage_count"] or 0)
        row["last_voyage_year"] = int(row["last_voyage_year"] or 0)
        profiles[profile_id] = row
    return profiles


class ExcelProfileSource:
    def get_profile(self, guest_id: str) -> dict | None:
        attributes = _guest_profiles().get(guest_id)
        if attributes is None:
            return None
        return {"profile_id": guest_id, "attributes": attributes.copy()}

    def list_guests(self) -> list[dict]:
        return [
            {"guest_id": guest_id, "first_name": profile["first_name"], "last_name": profile["last_name"]}
            for guest_id, profile in _guest_profiles().items()
        ]


class AmperityProfileSource:
    """NOT TESTED, no credentials. Adapter boundary for the Amperity Profile API."""

    def get_profile(self, guest_id: str) -> dict | None:
        tenant = os.getenv("AMPERITY_TENANT", "").strip()
        token = os.getenv("AMPERITY_TOKEN", "").strip()
        index_id = os.getenv("AMPERITY_INDEX_ID", "").strip()
        if not all((tenant, token, index_id)):
            raise RuntimeError("Amperity requires AMPERITY_TENANT, AMPERITY_TOKEN, and AMPERITY_INDEX_ID")

        url = f"https://{tenant}.amperity.com/api/indexes/{index_id}/profiles/{guest_id}"
        response = requests.get(
            url,
            headers={"amperity-tenant": tenant, "Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if "attributes" in payload else {
            "profile_id": guest_id,
            "attributes": payload,
        }


class InformaticaProfileSource:
    """Business 360 source. Field IDs other than rcyc_id remain unverified."""

    def __init__(self):
        self.login_url = os.getenv("INFA_LOGIN_URL", "").strip()
        self.username = os.getenv("INFA_USERNAME", "").strip()
        self.password = os.getenv("INFA_PASSWORD", "")
        self.entity = os.getenv("INFA_ENTITY", "guest360").strip() or "guest360"
        self.guest_id_field = os.getenv("INFA_GUEST_ID_FIELD", "guest_id").strip() or "guest_id"
        self.customer_id_field = os.getenv("INFA_CUSTOMER_ID_FIELD", "rcyc_id").strip() or "rcyc_id"
        self.model_version = os.getenv("INFA_MODEL_VERSION", "").strip()
        self.timeout_seconds = self._float_setting("INFA_TIMEOUT_SECONDS", 10.0)
        self.cache_seconds = self._float_setting("INFA_CACHE_SECONDS", 60.0)
        self._session_id: str | None = None
        self._base_api_url: str | None = None
        self._profile_cache: dict[str, tuple[float, dict | None]] = {}
        self._customer_lookup_cache: dict[str, tuple[float, str | None, str | None]] = {}
        self.request_log: list[dict[str, str]] = []

    @staticmethod
    def _float_setting(name: str, default: float) -> float:
        try:
            return max(float(os.getenv(name, str(default))), 0.0)
        except ValueError:
            return default

    def _send_with_rate_retry(self, method: str, url: str, headers: dict, body: dict | None = None):
        for attempt in range(2):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=body,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout as exc:
                self._record_request(method, url, "NO_RESPONSE")
                raise ProfileSourceUnavailable from exc
            except requests.RequestException as exc:
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
        log_method = logger.warning if status == "NO_RESPONSE" or status.isdigit() and int(status) >= 400 else logger.info
        log_method(
            "Informatica request method=%s host=%s path=%s status=%s",
            request_summary["method"],
            request_summary["host"],
            request_summary["path"],
            request_summary["status"],
        )

    @staticmethod
    def _require_success(response) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code >= 500:
            logger.warning("Informatica service returned a server error")
        else:
            logger.warning("Informatica request was rejected")
        raise ProfileSourceUnavailable

    @staticmethod
    def _json_object(response) -> dict:
        try:
            payload = response.json()
        except (ValueError, requests.RequestException) as exc:
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
            path = path[:-len("/saas")]
        # Business 360 REST API Reference, Authentication method:
        # https://docs.informatica.com/master-data-management-cloud/business-360-console/current-version/business-360-rest-api-reference/business-360-rest-api/authentication-method.html
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

    def _api_request(self, method: str, path: str, body: dict | None = None):
        if not self.model_version:
            logger.warning("Informatica model version is not configured")
            raise ProfileSourceUnavailable
        if not self._session_id or not self._base_api_url:
            self.login()

        url = f"{self._base_api_url}/{path.lstrip('/')}"
        # Header names are verbatim from Informatica's Business 360 REST API Reference:
        # https://docs.informatica.com/master-data-management-cloud/business-360-console/current-version/business-360-rest-api-reference/business-360-rest-api/request-header.html
        # Session header behavior: https://docs.informatica.com/master-data-management-cloud/business-360-console/current-version/business-360-rest-api-reference/business-360-rest-api/session-ids-and-json-web-tokens.html
        for auth_attempt in range(2):
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "IDS-SESSION-ID": self._session_id,
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

    def _search_guest_result(self, guest_id: str, field_name: str | None = None) -> tuple[str | None, str | None]:
        if not self.model_version:
            logger.warning("Informatica model version is not configured")
            raise ProfileSourceUnavailable
        field_name = field_name or self.guest_id_field
        customer_field = f"{self.entity}.{field_name}"
        # Business 360 Search API request body and response reference:
        # https://docs.informatica.com/master-data-management-cloud/business-360-console/current-version/business-360-rest-api-reference/business-360-rest-api/search-api.html
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

    def search_guest(self, guest_id: str, field_name: str | None = None) -> str | None:
        business_id, _reason = self._search_guest_result(guest_id, field_name)
        return business_id

    @staticmethod
    def _search_record_field_value(record: dict, qualified_field_name: str):
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

    def get_bookings(self, guest_business_id: str) -> list[dict]:
        max_bookings = int(os.getenv("INFA_MAX_BOOKINGS", "10") or 10)
        now = time.monotonic()
        cache_key = f"bookings:{guest_business_id}"
        cached = self._profile_cache.get(cache_key)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1] or [])
        try:
            payload = self._json_object(
                self._api_request(
                    "POST",
                    "/business-entity/public/api/v1/relationship/rel_g360_to_booking/filter",
                    {
                        "pageOffset": 0,
                        "pageSize": max_bookings,
                        "filter": {"_from": {"businessEntity": "guest360", "businessId": guest_business_id}},
                    },
                )
            )
        except ProfileSourceUnavailable:
            raise
        content = payload.get("content", [])
        if not isinstance(content, list):
            content = []
        bookings = []
        for item in content[:max_bookings]:
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
            booking = {}
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
        import datetime as _dt

        def _parse_date(value):
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
        bookings = [b for _, _, b in dated]
        self._profile_cache[cache_key] = (now + self.cache_seconds, bookings)
        return copy.deepcopy(bookings)

    def read_master_record_for_entity(self, entity: str, business_id: str) -> dict:
        response = self._api_request("GET", f"/business-entity/public/api/v1/entity/{entity}/{business_id}")
        return self._json_object(response)

    def read_master_record(self, business_id: str) -> dict:
        response = self._api_request(
            "GET",
            f"/business-entity/public/api/v1/entity/{self.entity}/{business_id}",
        )
        return self._json_object(response)

    def get_profile(self, guest_id: str) -> dict | None:
        now = time.monotonic()
        cached = self._profile_cache.get(guest_id)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1])

        business_id = self._customer_business_id(guest_id)
        if business_id is None:
            self._profile_cache[guest_id] = (now + self.cache_seconds, None)
            return None
        master_record = self.read_master_record(business_id)
        profile = {
            "profile_id": business_id,
            "attributes": map_informatica_attributes(master_record),
        }
        self._profile_cache[guest_id] = (now + self.cache_seconds, profile)
        return copy.deepcopy(profile)


@lru_cache(maxsize=1)
def _source():
    source_name = os.getenv("PROFILE_SOURCE", "excel").strip().lower()
    if source_name == "excel":
        return ExcelProfileSource()
    if source_name == "amperity":
        return AmperityProfileSource()
    if source_name == "informatica":
        return InformaticaProfileSource()
    raise ValueError("PROFILE_SOURCE must be 'excel', 'amperity', or 'informatica'")


def get_bookings(guest_id: str) -> list[dict]:
    source = _source()
    if not isinstance(source, InformaticaProfileSource):
        return []
    business_id = source._customer_business_id(guest_id)
    if not business_id:
        return []
    try:
        return source.get_bookings(business_id)
    except ProfileSourceUnavailable:
        raise


def get_profile(guest_id: str) -> dict | None:
    """Resolve a profile by RCYC_ID/profile ID, never by email."""
    try:
        return _source().get_profile(guest_id)
    except ProfileSourceUnavailable:
        if os.getenv("PROFILE_FALLBACK_TO_EXCEL", "false").strip().lower() == "true":
            logger.warning("Informatica unavailable; explicit Excel fallback is enabled")
            return ExcelProfileSource().get_profile(guest_id)
        raise


def customer_id_exists(customer_id: str) -> bool:
    source = _source()
    if not isinstance(source, InformaticaProfileSource):
        return False
    return source.customer_id_exists(customer_id)


def customer_id_failure_reason(customer_id: str) -> str | None:
    source = _source()
    if not isinstance(source, InformaticaProfileSource):
        return None
    return source.customer_id_failure_reason(customer_id)


def list_guests() -> list[dict]:
    if os.getenv("PROFILE_SOURCE", "excel").strip().lower() != "excel":
        return []
    return ExcelProfileSource().list_guests()