"""Comprehensive live HTTP & functional test suite for MARIS RCYC Concierge."""

from __future__ import annotations

import json
import sys
import httpx

from backend.app.config import Settings
from backend.app.llm_engine import PluggableLLMEngine
from backend.app.models import EscalationInfo, GuestProfile


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"


def run_tests() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    results: list[dict[str, object]] = []

    # 1. Health & 7 sample guests / 12 voyages
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    health = r_health.json()
    assert health["guests_loaded"] == 7, f"Expected 7 sample guests, got {health['guests_loaded']}"
    assert health["voyages_loaded"] == 12, f"Expected 12 voyages, got {health['voyages_loaded']}"
    results.append({"test": "Health & Sample Data Counts", "status": "PASS", "detail": health})

    # 2. Greetings & Thanks return NO voyage recommendations
    for msg in ["hi", "good morning", "thank you!"]:
        rg = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": msg})
        assert rg.status_code == 200
        dg = rg.json()
        assert dg["recommendations"] == [], f"Greeting/thanks '{msg}' returned recommendations!"
        assert dg["referenced_voyages"] == []
        assert "Guest 360" not in dg["reply"]
        assert "rule_based" not in dg["reply"]
    results.append({"test": "Greetings & Thanks (no recommendations)", "status": "PASS"})

    # 3. Personalized recommendation ("Suggest the best voyage for me.") + explainable breakdown
    r_rec = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "Suggest the best voyage for me."})
    assert r_rec.status_code == 200
    d_rec = r_rec.json()
    assert len(d_rec["recommendations"]) == 3
    bd = d_rec["recommendations"][0]["score_breakdown"]
    assert set(bd.keys()) == {"preferred_region", "interest_focus", "preferred_suite_availability", "new_region_vs_last_voyage"}
    results.append({
        "test": "Best voyage for me + 4-weight breakdown",
        "status": "PASS",
        "top_voyage": d_rec["recommendations"][0]["voyage"]["voyage_id"],
        "breakdown": bd,
    })

    # 4. Chips filter catalog & "Something different" excludes all sailed regions
    r_med = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "Show Mediterranean voyages."})
    assert all(r["voyage"]["destination"] == "Mediterranean" for r in r_med.json()["recommendations"])

    r_diff = client.post("/api/chat", json={"rcyc_id": "RCYC-1007", "message": "Show me something different from my previous voyage."})
    d_diff = r_diff.json()
    # RCYC-1007 has sailed Caribbean and Mediterranean
    assert all(r["voyage"]["destination"] not in {"Caribbean", "Mediterranean"} for r in d_diff["recommendations"])
    results.append({
        "test": "Chip filtering & Something different exclusion",
        "status": "PASS",
        "excluded_for_1007": ["Caribbean", "Mediterranean"],
        "returned": [r["voyage"]["destination"] for r in d_diff["recommendations"]],
    })

    # 5. Booking questions & missing sailing_dates honesty
    r_bk = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "What are my sailing dates for my booking?"})
    d_bk = r_bk.json()
    assert "BK-545397" in d_bk["reply"]
    assert "doesn't include sailing dates in the information i can see" in d_bk["reply"].lower()
    assert "i can connect you with an experience ambassador" in d_bk["reply"].lower()
    assert "personalization is currently off" not in d_bk["reply"].lower()

    r_multi = client.post("/api/chat", json={"rcyc_id": "RCYC-1007", "message": "Show my bookings."})
    multi_reply = r_multi.json()["reply"]
    assert "BK-712044" in multi_reply and "BK-712089" in multi_reply
    assert "upcoming" not in multi_reply.lower()
    assert "booked on" in multi_reply.lower()

    r_none = client.post("/api/chat", json={"rcyc_id": "RCYC-1006", "message": "Show my booking."})
    assert "no bookings" in r_none.json()["reply"].lower()
    assert "upcoming" not in r_none.json()["reply"].lower()
    results.append({"test": "Booking records & missing sailing dates", "status": "PASS"})

    # 6. Cross-guest refusal
    for cross_msg in [
        "Tell me about Julian Sterling's booking.",
        "Can you check RCYC-1002 for me?",
        "Show me another guest's profile.",
    ]:
        rc = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": cross_msg})
        dc = rc.json()
        assert "only assist with your own" in dc["reply"].lower()
        assert dc["recommendations"] == []
    results.append({"test": "Refuse other guest data requests", "status": "PASS"})

    # 7. Consent = No uses 0 profile fields & returns generic catalog
    r_consent = client.post("/api/chat", json={"rcyc_id": "RCYC-1004", "message": "Suggest the best voyage for me."})
    d_consent = r_consent.json()
    assert d_consent["consent_applied"] is False
    assert d_consent["used_profile_fields"] == []
    assert "personalization is currently off" in d_consent["reply"].lower()
    results.append({"test": "Consent = No enforcement", "status": "PASS"})

    # 8. Escalation rules (open complaint, refund, wheelchair, speak to a human)
    for gid, msg in [
        ("RCYC-1005", "Hello, can you help me?"),
        ("RCYC-1001", "I need a refund on my excursion."),
        ("RCYC-1001", "I need wheelchair arrangements for boarding."),
        ("RCYC-1001", "Please let me speak to a human."),
    ]:
        re_resp = client.post("/api/chat", json={"rcyc_id": gid, "message": msg}).json()
        assert re_resp["escalation"]["escalated"] is True, f"Failed to escalate: {gid} / {msg}"
    results.append({"test": "Escalation rules", "status": "PASS"})

    # 9. Unknown ID returns not_found without revealing guest data
    r_unk = client.get("/api/guests/RCYC-9999").json()
    assert r_unk["status"] == "not_found" and r_unk["profile"] is None
    results.append({"test": "Unknown ID privacy handling", "status": "PASS"})

    # 10. Gemini silent fallback when key is missing or endpoint fails
    cfg_gemini = Settings(
        port=8000,
        log_level="INFO",
        sample_data_json=Settings.from_env().sample_data_json,
        data_provider_mode="mock",
        demo_mode=True,
        llm_provider="gemini",
        gemini_api_key="invalid-test-key",
        gemini_model="gemini-3.8-flash",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="llama3.1",
        anthropic_api_key="",
        anthropic_model="claude-3-5-sonnet-latest",
    )
    fb_engine = PluggableLLMEngine(cfg_gemini)
    p = GuestProfile(rcyc_id="RCYC-1001", first_name="Eleanor", last_name="Vance", loyalty_tier="Gold")
    fb_reply, fb_prov, fb_trig = fb_engine.generate_reply(
        profile=p,
        bookings=[],
        intent="recommendation",
        consent_applied=True,
        recommendations=[],
        referenced_voyages=[],
        escalation=EscalationInfo(escalated=False),
        user_message="Suggest the best voyage for me.",
    )
    assert fb_trig is True and fb_prov == "rule_based" and len(fb_reply) > 20
    results.append({"test": "Gemini silent fallback to rule_based", "status": "PASS"})

    # 11. Browser payload minimisation: forbidden keys absent from /api/guests/{id} and /api/chat
    forbidden_browser_keys = {
        "complaint_summary",
        "dietary_requirements",
        "accessibility_requirements",
        "vip_status",
    }

    def collect_keys(obj: object) -> set[str]:
        found: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.add(str(k))
                found.update(collect_keys(v))
        elif isinstance(obj, list):
            for item in obj:
                found.update(collect_keys(item))
        return found

    for gid in ["RCYC-1001", "RCYC-1002", "RCYC-1005"]:
        rg = client.get(f"/api/guests/{gid}")
        assert rg.status_code == 200
        dg = rg.json()
        assert "escalation" in dg and isinstance(dg["escalation"], bool)
        assert forbidden_browser_keys.isdisjoint(collect_keys(dg)), f"Forbidden key leaked in /api/guests/{gid}"

        rc_chat = client.post("/api/chat", json={"rcyc_id": gid, "message": "Suggest the best voyage for me."})
        assert rc_chat.status_code == 200
        dc_chat = rc_chat.json()
        assert forbidden_browser_keys.isdisjoint(collect_keys(dc_chat)), f"Forbidden key leaked in /api/chat ({gid})"
        assert "Delayed luggage" not in dc_chat["escalation"]["reason"]
    results.append({"test": "Browser payload minimisation (forbidden keys absent)", "status": "PASS"})

    # 12. Gemini payload test double: exact key-set equality, consent off, and rule-only intents
    from fastapi.testclient import TestClient
    from backend.app.concierge_agent import ConciergeAgent
    from backend.app.data_provider import MockProvider
    import backend.app.main as app_main

    captured_payloads: list[dict[str, object]] = []

    class GeminiCapturingEngine(PluggableLLMEngine):
        def _call_gemini(self, facts: dict[str, object]) -> str:
            captured_payloads.append(facts)
            return "Test double response."

    base_cfg = Settings.from_env()
    cap_cfg = Settings(
        port=base_cfg.port,
        log_level=base_cfg.log_level,
        sample_data_json=base_cfg.sample_data_json,
        data_provider_mode="mock",
        demo_mode=True,
        llm_provider="gemini",
        gemini_api_key="test-double-key",
        gemini_model=base_cfg.gemini_model,
        ollama_base_url=base_cfg.ollama_base_url,
        ollama_model=base_cfg.ollama_model,
        anthropic_api_key="",
        anthropic_model=base_cfg.anthropic_model,
    )
    cap_agent = ConciergeAgent(MockProvider(cap_cfg.sample_data_json), GeminiCapturingEngine(cap_cfg))

    # 12a. Consent ON -> exactly {user_message, intent, catalog_voyages, first_name}
    captured_payloads.clear()
    from backend.app.models import ChatRequest
    cap_agent.handle_chat(ChatRequest(rcyc_id="RCYC-1001", message="Suggest the best voyage for me."))
    assert len(captured_payloads) == 1
    assert set(captured_payloads[0].keys()) == {"user_message", "intent", "catalog_voyages", "first_name"}
    expected_catalog_item_keys = {
        "voyage_id",
        "voyage_name",
        "destination",
        "duration",
        "price",
        "season",
        "suites",
        "highlights",
    }
    for v_item in captured_payloads[0]["catalog_voyages"]:  # type: ignore[index]
        assert "ship" not in v_item
        assert set(v_item.keys()) == expected_catalog_item_keys
    cap_json_0 = json.dumps(captured_payloads[0]).lower()
    for leaked_phrase in ("match_reasons", "preferred region", "past sailings", "aligned with"):
        assert leaked_phrase not in cap_json_0, f"Preference/history leak in Gemini payload: {leaked_phrase}"

    # 12b. Consent OFF -> exactly {user_message, intent, catalog_voyages} (no first_name)
    captured_payloads.clear()
    cap_agent.handle_chat(ChatRequest(rcyc_id="RCYC-1004", message="Suggest the best voyage for me."))
    assert len(captured_payloads) == 1
    assert set(captured_payloads[0].keys()) == {"user_message", "intent", "catalog_voyages"}
    assert "first_name" not in captured_payloads[0]

    # 12c. Complaint, dietary, and accessibility questions -> Gemini is NOT called
    captured_payloads.clear()
    cap_agent.handle_chat(ChatRequest(rcyc_id="RCYC-1001", message="I want to file a complaint and ask for a refund."))
    cap_agent.handle_chat(ChatRequest(rcyc_id="RCYC-1001", message="Do you support gluten-free dietary options?"))
    cap_agent.handle_chat(ChatRequest(rcyc_id="RCYC-1001", message="I need wheelchair accessibility on board."))
    assert len(captured_payloads) == 0, f"Gemini was called unexpectedly: {captured_payloads}"
    results.append({"test": "Gemini payload exact key-set & rule-only bypass", "status": "PASS"})

    # 13. DEMO_MODE=false -> /api/guests returns 404; DATA_PROVIDER_MODE=informatica forces DEMO_MODE=false & disables /api/guests/{id}
    tc = TestClient(app_main.app)
    orig_settings = app_main.app.state.settings
    try:
        app_main.app.state.settings = Settings(
            port=orig_settings.port,
            log_level=orig_settings.log_level,
            sample_data_json=orig_settings.sample_data_json,
            data_provider_mode="mock",
            demo_mode=False,
            llm_provider=orig_settings.llm_provider,
            gemini_api_key=orig_settings.gemini_api_key,
            gemini_model=orig_settings.gemini_model,
            ollama_base_url=orig_settings.ollama_base_url,
            ollama_model=orig_settings.ollama_model,
            anthropic_api_key=orig_settings.anthropic_api_key,
            anthropic_model=orig_settings.anthropic_model,
        )
        assert tc.get("/api/guests").status_code == 404

        import os
        prev_mode = os.environ.get("DATA_PROVIDER_MODE")
        prev_demo = os.environ.get("DEMO_MODE")
        try:
            os.environ["DATA_PROVIDER_MODE"] = "informatica"
            os.environ["DEMO_MODE"] = "true"
            infa_cfg = Settings.from_env()
            assert infa_cfg.demo_mode is False
            app_main.app.state.settings = infa_cfg
            assert tc.get("/api/guests").status_code == 404
            assert tc.get("/api/guests/RCYC-1001").status_code == 404
        finally:
            if prev_mode is None:
                os.environ.pop("DATA_PROVIDER_MODE", None)
            else:
                os.environ["DATA_PROVIDER_MODE"] = prev_mode
            if prev_demo is None:
                os.environ.pop("DEMO_MODE", None)
            else:
                os.environ["DEMO_MODE"] = prev_demo
    finally:
        app_main.app.state.settings = orig_settings
    results.append({"test": "DEMO_MODE=false 404 & informatica overrides", "status": "PASS"})

    # 14. Informatica mode (mocked Business 360 HTTP): login, generic errors, 503 keeps session,
    # masking, zero PII to Gemini, and /api/guests + /api/guests/{id} disabled
    from unittest.mock import patch
    from backend.app.data_provider import InformaticaProvider

    infa_settings = Settings(
        port=base_cfg.port,
        log_level=base_cfg.log_level,
        sample_data_json=base_cfg.sample_data_json,
        data_provider_mode="informatica",
        demo_mode=False,
        llm_provider="gemini",
        gemini_api_key="test-double-key",
        gemini_model=base_cfg.gemini_model,
        ollama_base_url=base_cfg.ollama_base_url,
        ollama_model=base_cfg.ollama_model,
        anthropic_api_key="",
        anthropic_model=base_cfg.anthropic_model,
        infa_login_url="https://dm-us.informaticacloud.com/saas/public/core/v3/login",
        infa_username="mock-infa-user",
        infa_password="mock-infa-password",
        infa_entity="guest360",
        infa_guest_id_field="guest_id",
        infa_customer_id_field="rcyc_id",
        infa_model_version="1",
        infa_timeout_seconds=5.0,
        infa_cache_seconds=0.0,
        infa_max_bookings=10,
        secret_key="test-only-random-secret-key-for-task-2a",
        demo_password="TestDemoPassword123!",
    )
    infa_provider = InformaticaProvider(infa_settings)
    infa_captured_gemini: list[dict[str, object]] = []

    class InfaGeminiCapturingEngine(PluggableLLMEngine):
        def _call_gemini(self, facts: dict[str, object]) -> str:
            infa_captured_gemini.append(facts)
            return "Mediterranean catalog phrasing."

    infa_agent = ConciergeAgent(infa_provider, InfaGeminiCapturingEngine(infa_settings))

    orig_provider = app_main.app.state.data_provider
    orig_agent = app_main.app.state.concierge_agent
    orig_settings_14 = app_main.app.state.settings
    outage_active = {"flag": False}

    class FakeHttpResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_httpx_request(method: str, url: str, headers=None, json=None, timeout=None):
        if outage_active["flag"]:
            raise httpx.TimeoutException("Simulated Informatica outage")
        if url.endswith("/login"):
            return FakeHttpResponse(
                200,
                {
                    "userInfo": {"sessionId": "infa-sess-1"},
                    "baseApiUrl": "https://usw1.dm-us.informaticacloud.com/saas",
                },
            )
        if url.endswith("/search/public/api/v1/search"):
            filters = (json or {}).get("filters", {}).get("filter", [])
            val = str(filters[0].get("fieldValue", "")) if filters else ""
            if val == "1000000092615":
                return FakeHttpResponse(
                    200,
                    {
                        "searchResult": {
                            "hits": 1,
                            "records": [
                                {
                                    "guest360": {"rcyc_id": "1000000092615"},
                                    "_meta": {
                                        "businessId": "BIZ-1001",
                                        "states": {"recordStateIndicator": "ACTIVE"},
                                    },
                                }
                            ],
                        }
                    },
                )
            return FakeHttpResponse(200, {"searchResult": {"hits": 0, "records": []}})
        if url.endswith("/business-entity/public/api/v1/entity/guest360/BIZ-1001"):
            return FakeHttpResponse(
                200,
                {
                    "rcyc_id": "1000000092615",
                    "first_name": "Dennis",
                    "last_name": "Woods",
                    "full_name": "Dennis Woods",
                    "email": [{"email_address": "dennis.woods@email.com"}],
                    "phone": [{"country_code": "1", "phone_number": "3055550147"}],
                },
            )
        if url.endswith("/business-entity/public/api/v1/relationship/rel_g360_to_booking/filter"):
            return FakeHttpResponse(
                200,
                {
                    "content": [
                        {
                            "_from": {"businessEntity": "guest360", "businessId": "BIZ-1001"},
                            "_to": {"businessEntity": "booking", "businessId": "BK-BIZ-1"},
                        }
                    ]
                },
            )
        if url.endswith("/business-entity/public/api/v1/entity/booking/BK-BIZ-1"):
            return FakeHttpResponse(
                200,
                {
                    "booking_id": "545397",
                    "voyage_id_itinerary": "13260914",
                    "voyage_count_lifetime_rolling_": 2,
                    "booking_recency_": "2026-05-03",
                    "booking_status": {"Code": "C", "Name": "Confirmed"},
                },
            )
        return FakeHttpResponse(404, {})

    try:
        app_main.app.state.settings = infa_settings
        app_main.app.state.data_provider = infa_provider
        app_main.app.state.concierge_agent = infa_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()

        infa_client = TestClient(app_main.app, base_url="https://testserver")
        with patch("backend.app.data_provider.httpx.request", side_effect=fake_httpx_request):
            # Disabled demo endpoints in informatica mode
            assert infa_client.get("/api/guests").status_code == 404
            assert infa_client.get("/api/guests/RCYC-1001").status_code == 404

            # Wrong password -> generic 401
            r_bad_pw = infa_client.post(
                "/api/login",
                json={"guest_id": "1000000092615", "password": "WrongPassword999"},
            )
            assert r_bad_pw.status_code == 401
            assert r_bad_pw.json() == {"detail": "Invalid ID or password."}

            # Unknown ID -> identical generic 401
            r_unk_id = infa_client.post(
                "/api/login",
                json={"guest_id": "9999999999999", "password": "TestDemoPassword123!"},
            )
            assert r_unk_id.status_code == 401
            assert r_unk_id.json() == r_bad_pw.json()

            # Login success -> signed HttpOnly, SameSite=None, Secure cookie + Bearer token
            r_ok = infa_client.post(
                "/api/login",
                json={"guest_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_ok.status_code == 200
            login_json = r_ok.json()
            assert login_json["authenticated"] is True
            assert isinstance(login_json.get("token"), str) and "." in login_json["token"]
            set_cookie_hdr = r_ok.headers.get("set-cookie", "")
            assert "rcyc_session=" in set_cookie_hdr
            assert "httponly" in set_cookie_hdr.lower()
            assert "samesite=none" in set_cookie_hdr.lower()
            assert "secure" in set_cookie_hdr.lower()

            # /api/me masking + exact keys + status_code + status_label
            r_me = infa_client.get("/api/me")
            assert r_me.status_code == 200
            me_data = r_me.json()
            assert set(me_data.keys()) == {
                "first_name",
                "full_name",
                "customer_id",
                "email",
                "phone",
                "personalization_consent",
                "consent_configured",
                "demo_consent_assumed",
                "bookings",
            }
            assert me_data["first_name"] == "Dennis"
            assert me_data["full_name"] == "Dennis Woods"
            assert me_data["customer_id"] == "1000000092615"
            assert me_data["email"] == "d***@email.com"
            assert me_data["phone"] == "+1 ***0147"
            assert me_data["personalization_consent"] is False
            assert me_data["consent_configured"] is False
            assert me_data["demo_consent_assumed"] is False
            assert "dennis.woods@email.com" not in json.dumps(me_data)
            assert "3055550147" not in json.dumps(me_data)
            assert len(me_data["bookings"]) == 1
            bk = me_data["bookings"][0]
            assert set(bk.keys()) == {
                "booking_id",
                "voyage_ref",
                "voyage_count",
                "booking_date",
                "status_code",
                "status_label",
            }
            assert bk["status_code"] == "C"
            assert bk["status_label"] == "Confirmed"

            # /api/chat ignores body rcyc_id and sends zero PII to Gemini
            infa_captured_gemini.clear()
            r_chat_infa = infa_client.post(
                "/api/chat",
                json={"rcyc_id": "RCYC-1001", "message": "Suggest Mediterranean voyages."},
            )
            assert r_chat_infa.status_code == 200
            assert len(infa_captured_gemini) == 1
            assert set(infa_captured_gemini[0].keys()) == {"user_message", "intent", "catalog_voyages"}
            gemini_json = json.dumps(infa_captured_gemini[0])
            for pii in ("Dennis", "Woods", "1000000092615", "dennis.woods", "0147", "545397", "13260914"):
                assert pii not in gemini_json, f"PII leaked to Gemini payload: {pii}"

            # 503 outage keeps the signed session intact
            outage_active["flag"] = True
            r_me_503 = infa_client.get("/api/me")
            assert r_me_503.status_code == 503
            assert "rcyc_session" not in r_me_503.headers.get("set-cookie", "").lower()

            r_chat_503 = infa_client.post("/api/chat", json={"message": "Suggest Mediterranean voyages."})
            assert r_chat_503.status_code == 503
            assert "rcyc_session" not in r_chat_503.headers.get("set-cookie", "").lower()

            # Recovery works with the same session cookie
            outage_active["flag"] = False
            r_me_recovered = infa_client.get("/api/me")
            assert r_me_recovered.status_code == 200
            assert r_me_recovered.json()["customer_id"] == "1000000092615"
    finally:
        app_main.app.state.settings = orig_settings_14
        app_main.app.state.data_provider = orig_provider
        app_main.app.state.concierge_agent = orig_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
    results.append({"test": "Informatica Task 2A (mocked login, generic 401, 503 keeps session, masking, zero Gemini PII)", "status": "PASS"})

    # 15. context_packet stays server-side; browser escalation responses exclude context_packet,
    # rcyc_id, full_name, and loyalty_tier
    r_esc_chat = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "I need a refund on my excursion."})
    assert r_esc_chat.status_code == 200
    d_esc_chat = r_esc_chat.json()
    assert d_esc_chat["escalation"]["escalated"] is True
    assert "context_packet" not in d_esc_chat["escalation"]
    esc_chat_keys = collect_keys(d_esc_chat["escalation"])
    assert {"context_packet", "rcyc_id", "full_name", "guest_name", "loyalty_tier"}.isdisjoint(esc_chat_keys)

    r_esc_ep = client.post("/api/escalate", json={"rcyc_id": "RCYC-1001", "message": "Please connect me to an Experience Ambassador."})
    assert r_esc_ep.status_code == 200
    d_esc_ep = r_esc_ep.json()
    assert d_esc_ep["escalated"] is True
    assert "context_packet" not in d_esc_ep
    esc_ep_keys = collect_keys(d_esc_ep)
    assert {"context_packet", "rcyc_id", "full_name", "guest_name", "loyalty_tier"}.isdisjoint(esc_ep_keys)
    results.append({"test": "Server-side context_packet excluded from browser escalation payloads", "status": "PASS"})

    # 16. Client IP rate-limit isolation (127.0.0.1 trusts X-Forwarded-For; non-127.0.0.1 uses direct peer)
    try:
        app_main.app.state.settings = infa_settings
        app_main.app.state.data_provider = infa_provider
        app_main.app.state.concierge_agent = infa_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()

        proxy_client = TestClient(app_main.app, base_url="https://testserver", client=("127.0.0.1", 50000))
        with patch("backend.app.data_provider.httpx.request", side_effect=fake_httpx_request):
            # 5 failures from IP A across distinct unknown IDs block IP A only
            for idx in range(5):
                r_fail = proxy_client.post(
                    "/api/login",
                    headers={"X-Forwarded-For": "203.0.113.10"},
                    json={"guest_id": f"8888888880{idx}", "password": "TestDemoPassword123!"},
                )
                assert r_fail.status_code == 401
                assert r_fail.json() == {"detail": "Invalid ID or password."}

            # 6th attempt from IP A (even with valid credentials) is blocked by IP A rate limit
            r_blocked_a = proxy_client.post(
                "/api/login",
                headers={"X-Forwarded-For": "203.0.113.10"},
                json={"guest_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_blocked_a.status_code == 401
            assert r_blocked_a.json() == {"detail": "Invalid ID or password."}

            # IP B is NOT blocked by IP A's failures and succeeds with valid credentials
            r_ok_b = proxy_client.post(
                "/api/login",
                headers={"X-Forwarded-For": "203.0.113.20"},
                json={"guest_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_ok_b.status_code == 200
            assert r_ok_b.json()["authenticated"] is True

            # Direct non-127.0.0.1 peer cannot spoof X-Forwarded-For to bypass IP rate limit
            direct_client = TestClient(app_main.app, base_url="https://testserver", client=("198.51.100.55", 50000))
            for idx in range(5):
                r_spoof = direct_client.post(
                    "/api/login",
                    headers={"X-Forwarded-For": f"10.0.0.{idx + 1}"},
                    json={"guest_id": f"7777777770{idx}", "password": "TestDemoPassword123!"},
                )
                assert r_spoof.status_code == 401

            r_spoof_blocked = direct_client.post(
                "/api/login",
                headers={"X-Forwarded-For": "10.0.0.99"},
                json={"guest_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_spoof_blocked.status_code == 401
    finally:
        app_main.app.state.settings = orig_settings_14
        app_main.app.state.data_provider = orig_provider
        app_main.app.state.concierge_agent = orig_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
    results.append({"test": "Client IP rate-limit isolation & X-Forwarded-For trust", "status": "PASS"})

    # 17. CORS: foreign Origin receives no Access-Control-Allow-Origin when ALLOWED_ORIGINS is empty
    assert Settings.from_env().allowed_origins == () or isinstance(Settings.from_env().allowed_origins, tuple)
    r_cors = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert r_cors.status_code == 200
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in r_cors.headers.items()}
    r_preflight = client.options(
        "/api/chat",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in r_preflight.headers.items()}
    results.append({"test": "CORS foreign Origin rejected (no Access-Control-Allow-Origin)", "status": "PASS"})

    # 18. Informatica catalog join, derived history scoring, consent off vs on (env & demo switch),
    # Bearer auth + 401 after sign-out, and /api/health/informatica
    consent_state = {"consent": None}
    try:
        # Unconfigured /api/health/informatica
        app_main.app.state.settings = Settings(
            port=base_cfg.port,
            log_level=base_cfg.log_level,
            sample_data_json=base_cfg.sample_data_json,
            data_provider_mode="mock",
            demo_mode=True,
            llm_provider="rule_based",
            gemini_api_key="",
            gemini_model=base_cfg.gemini_model,
            ollama_base_url=base_cfg.ollama_base_url,
            ollama_model=base_cfg.ollama_model,
            anthropic_api_key="",
            anthropic_model=base_cfg.anthropic_model,
        )
        r_hi_unconf = tc.get("/api/health/informatica")
        assert r_hi_unconf.status_code == 200
        hi_unconf = r_hi_unconf.json()
        assert set(hi_unconf.keys()) == {"configured", "login_ok", "search_ok", "entity"}
        assert hi_unconf["configured"] is False
        assert hi_unconf["login_ok"] is False
        assert hi_unconf["search_ok"] is False

        def make_infa_cfg(
            *,
            demo_assume: bool = False,
            infa_field_consent: str = "",
            infa_field_loyalty_tier: str = "",
            infa_field_preferred_suite: str = "",
        ) -> Settings:
            return Settings(
                port=base_cfg.port,
                log_level=base_cfg.log_level,
                sample_data_json=base_cfg.sample_data_json,
                data_provider_mode="informatica",
                demo_mode=False,
                llm_provider="rule_based",
                gemini_api_key="",
                gemini_model=base_cfg.gemini_model,
                ollama_base_url=base_cfg.ollama_base_url,
                ollama_model=base_cfg.ollama_model,
                anthropic_api_key="",
                anthropic_model=base_cfg.anthropic_model,
                infa_login_url="https://dm-us.informaticacloud.com/saas/public/core/v3/login",
                infa_username="mock-infa-user",
                infa_password="mock-infa-password",
                infa_entity="guest360",
                infa_guest_id_field="",
                infa_customer_id_field="rcyc_id",
                infa_model_version="1",
                infa_timeout_seconds=5.0,
                infa_cache_seconds=0.0,
                infa_max_bookings=10,
                secret_key="test-only-random-secret-key-for-task-2a",
                demo_password="TestDemoPassword123!",
                demo_assume_personalization_consent=demo_assume,
                infa_field_consent=infa_field_consent,
                infa_field_loyalty_tier=infa_field_loyalty_tier,
                infa_field_preferred_suite=infa_field_preferred_suite,
            )

        def fake_infa_http_18(method: str, url: str, headers=None, json=None, timeout=None):
            if url.endswith("/login"):
                return FakeHttpResponse(
                    200,
                    {
                        "userInfo": {"sessionId": "infa-sess-18"},
                        "baseApiUrl": "https://usw1.dm-us.informaticacloud.com/saas",
                    },
                )
            if url.endswith("/search/public/api/v1/search"):
                filters = (json or {}).get("filters", {}).get("filter", [])
                val = str(filters[0].get("fieldValue", "")) if filters else ""
                if val == "1000000092615":
                    return FakeHttpResponse(
                        200,
                        {
                            "searchResult": {
                                "hits": 1,
                                "records": [
                                    {
                                        "guest360": {"rcyc_id": "1000000092615"},
                                        "_meta": {
                                            "businessId": "BIZ-1001",
                                            "states": {"recordStateIndicator": "ACTIVE"},
                                        },
                                    }
                                ],
                            }
                        },
                    )
                return FakeHttpResponse(200, {"searchResult": {"hits": 0, "records": []}})
            if url.endswith("/business-entity/public/api/v1/entity/guest360/BIZ-1001"):
                payload = {
                    "rcyc_id": "1000000092615",
                    "first_name": "Dennis",
                    "last_name": "Woods",
                    "full_name": "Dennis Woods",
                    "email": [{"email_address": "dennis.woods@email.com"}],
                    "phone": [{"country_code": "1", "phone_number": "3055550147"}],
                    "loyalty_tier": "Sapphire",
                    "pref_suite": "Owner's Suite",
                }
                if consent_state["consent"] is not None:
                    payload["consent_flag"] = consent_state["consent"]
                return FakeHttpResponse(200, payload)
            if url.endswith("/business-entity/public/api/v1/relationship/rel_g30_to_booking/filter") or url.endswith(
                "/business-entity/public/api/v1/relationship/rel_g360_to_booking/filter"
            ):
                return FakeHttpResponse(
                    200,
                    {
                        "content": [
                            {
                                "_from": {"businessEntity": "guest360", "businessId": "BIZ-1001"},
                                "_to": {"businessEntity": "booking", "businessId": "BK-BIZ-MATCHED"},
                            },
                            {
                                "_from": {"businessEntity": "guest360", "businessId": "BIZ-1001"},
                                "_to": {"businessEntity": "booking", "businessId": "BK-BIZ-RAW"},
                            },
                        ]
                    },
                )
            if url.endswith("/business-entity/public/api/v1/entity/booking/BK-BIZ-MATCHED"):
                return FakeHttpResponse(
                    200,
                    {
                        "booking_id": "545397",
                        "voyage_id_itinerary": "RCYC-MED-01",
                        "voyage_count_lifetime_rolling_": 2,
                        "booking_recency_": "2026-05-03",
                        "booking_status": {"Code": "C", "Name": "Confirmed"},
                    },
                )
            if url.endswith("/business-entity/public/api/v1/entity/booking/BK-BIZ-RAW"):
                return FakeHttpResponse(
                    200,
                    {
                        "booking_id": "545398",
                        "voyage_id_itinerary": "99999999",
                        "voyage_count_lifetime_rolling_": 1,
                        "booking_recency_": "2025-11-01",
                        "booking_status": {"Code": "P", "Name": "P"},
                    },
                )
            return FakeHttpResponse(404, {})

        def apply_cfg_18(cfg: Settings) -> None:
            prov = InformaticaProvider(cfg)
            eng = PluggableLLMEngine(cfg)
            app_main.app.state.settings = cfg
            app_main.app.state.data_provider = prov
            app_main.app.state.concierge_agent = ConciergeAgent(prov, eng)

        with patch("backend.app.data_provider.httpx.request", side_effect=fake_infa_http_18):
            # A. Consent OFF + /api/health/informatica configured + Bearer token + catalog join
            cfg_off = make_infa_cfg()
            apply_cfg_18(cfg_off)
            app_main.login_failures.clear()
            app_main.login_blocked_until.clear()
            app_main.ip_login_failures.clear()
            app_main.ip_login_blocked_until.clear()

            r_hi_conf = tc.get("/api/health/informatica")
            assert r_hi_conf.status_code == 200
            assert r_hi_conf.json() == {
                "configured": True,
                "login_ok": True,
                "search_ok": True,
                "entity": "guest360",
            }

            c_login = TestClient(app_main.app, base_url="https://testserver")
            r_login = c_login.post(
                "/api/login",
                json={"customer_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_login.status_code == 200
            bearer_tok = r_login.json()["token"]

            # Separate cookie-less client using Bearer token only (like iframe sessionStorage)
            c_bearer = TestClient(app_main.app, base_url="https://testserver")
            assert c_bearer.get("/api/me").status_code == 401
            assert c_bearer.get("/api/me", headers={"Authorization": "Bearer invalid.token"}).status_code == 401

            r_me_18 = c_bearer.get("/api/me", headers={"Authorization": f"Bearer {bearer_tok}"})
            assert r_me_18.status_code == 200
            me_18 = r_me_18.json()
            assert me_18["personalization_consent"] is False
            assert me_18["demo_consent_assumed"] is False
            assert len(me_18["bookings"]) == 2
            matched_bk = next(b for b in me_18["bookings"] if b["booking_id"] == "545397")
            raw_bk = next(b for b in me_18["bookings"] if b["booking_id"] == "545398")
            assert matched_bk["voyage_name"] == "Amalfi Coast & Cycladic Isles"
            assert matched_bk["destination"] == "Mediterranean"
            assert matched_bk["ship"] == "Ilma"
            assert matched_bk["status_label"] == "Confirmed"
            assert raw_bk["voyage_ref"] == "99999999"
            assert "voyage_name" not in raw_bk
            assert raw_bk["status_code"] == "P"
            assert "status_label" not in raw_bk

            # Bookings chat & numeric other-guest refusal
            r_bk_chat = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "What are my bookings?"},
            )
            assert r_bk_chat.status_code == 200
            assert "Amalfi Coast & Cycladic Isles" in r_bk_chat.json()["reply"]
            assert "99999999" in r_bk_chat.json()["reply"]
            assert "Status: P" in r_bk_chat.json()["reply"]

            r_other_num = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "Can you check booking for 1000000099999?"},
            )
            assert r_other_num.status_code == 200
            assert "only assist with your own" in r_other_num.json()["reply"].lower()

            # Consent OFF recommendation -> 0 scores, generic reply
            r_off_rec = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "Suggest the best voyage for me."},
            )
            assert r_off_rec.status_code == 200
            d_off = r_off_rec.json()
            assert d_off["consent_applied"] is False
            assert d_off["used_profile_fields"] == []
            assert all(rec["score"] == 0 for rec in d_off["recommendations"])
            assert "personalization is currently off" in d_off["reply"].lower()

            # B. DEMO_ASSUME_PERSONALIZATION_CONSENT=true (when INFA_FIELD_CONSENT unset)
            apply_cfg_18(make_infa_cfg(demo_assume=True))
            r_me_demo = c_bearer.get("/api/me", headers={"Authorization": f"Bearer {bearer_tok}"})
            assert r_me_demo.status_code == 200
            assert r_me_demo.json()["personalization_consent"] is True
            assert r_me_demo.json()["demo_consent_assumed"] is True
            assert r_me_demo.json()["consent_configured"] is False

            r_demo_rec = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "Suggest the best voyage for me."},
            )
            assert r_demo_rec.status_code == 200
            d_demo = r_demo_rec.json()
            assert d_demo["consent_applied"] is True
            assert d_demo["used_profile_fields"] == ["sailed_regions"]
            assert any(rec["score"] > 0 for rec in d_demo["recommendations"])
            assert "sailed regions" in d_demo["reply"].lower()
            assert "preferred suite" not in d_demo["reply"].lower()

            # C. INFA_FIELD_CONSENT set -> overrides demo switch when "N", enables with 2c fields when "Y"
            consent_state["consent"] = "N"
            apply_cfg_18(
                make_infa_cfg(
                    demo_assume=True,
                    infa_field_consent="consent_flag",
                    infa_field_loyalty_tier="loyalty_tier",
                    infa_field_preferred_suite="pref_suite",
                )
            )
            r_strict_n = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "Suggest the best voyage for me."},
            )
            assert r_strict_n.status_code == 200
            assert r_strict_n.json()["consent_applied"] is False

            consent_state["consent"] = "Y"
            r_me_2c = c_bearer.get("/api/me", headers={"Authorization": f"Bearer {bearer_tok}"})
            assert r_me_2c.status_code == 200
            assert r_me_2c.json()["loyalty_tier"] == "Sapphire"
            assert r_me_2c.json()["preferred_suite"] == "Owner's Suite"
            assert r_me_2c.json()["consent_configured"] is True
            assert r_me_2c.json()["demo_consent_assumed"] is False

            r_strict_y = c_bearer.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {bearer_tok}"},
                json={"message": "Suggest the best voyage for me."},
            )
            assert r_strict_y.status_code == 200
            d_strict_y = r_strict_y.json()
            assert d_strict_y["consent_applied"] is True
            assert "preferred_suite" in d_strict_y["used_profile_fields"]
            assert "sailed_regions" in d_strict_y["used_profile_fields"]

            # D. Sign out invalidates cookie & revokes Bearer token -> subsequent /api/me returns 401
            r_out = c_login.post("/api/logout")
            assert r_out.status_code == 200
            assert c_login.get("/api/me").status_code == 401

            r_out_b = c_bearer.post("/api/logout", headers={"Authorization": f"Bearer {bearer_tok}"})
            assert r_out_b.status_code == 200
            assert c_bearer.get("/api/me", headers={"Authorization": f"Bearer {bearer_tok}"}).status_code == 401
    finally:
        app_main.app.state.settings = orig_settings_14
        app_main.app.state.data_provider = orig_provider
        app_main.app.state.concierge_agent = orig_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
        app_main.revoked_session_tokens.clear()
    results.append({"test": "Informatica catalog join, scoring, consent switch, Bearer 401 & /api/health/informatica", "status": "PASS"})

    # 19. Concierge phrasing fixes:
    # - Missing ship / sailing dates / suite / cabin without personalization-off prefix
    # - Truthful simulated escalation wording
    # - No 'upcoming' in booking replies + 'Here is your booking on file' + 'Booked on'
    # - Masked email/phone replies (never unmasked, never sent to Gemini)
    # - Remove stray asterisks and repeated 'Welcome aboard' from catalog replies
    try:
        cfg_19 = make_infa_cfg()
        prov_19 = InformaticaProvider(cfg_19)

        class NoisyGeminiDouble(PluggableLLMEngine):
            def _call_gemini(self, facts: dict[str, object]) -> str:
                return (
                    "Welcome aboard, guest! Explore these options:\n"
                    "* **Amalfi Coast**: Signature Mediterranean sailing with *great cuisine\n"
                    "* **Greek Isles**: Aegean sun*sets\n"
                )

        eng_19 = NoisyGeminiDouble(
            Settings(
                port=base_cfg.port,
                log_level=base_cfg.log_level,
                sample_data_json=base_cfg.sample_data_json,
                data_provider_mode="informatica",
                demo_mode=False,
                llm_provider="gemini",
                gemini_api_key="test-double-key",
                gemini_model=base_cfg.gemini_model,
                ollama_base_url=base_cfg.ollama_base_url,
                ollama_model=base_cfg.ollama_model,
                anthropic_api_key="",
                anthropic_model=base_cfg.anthropic_model,
                infa_login_url="https://dm-us.informaticacloud.com/saas/public/core/v3/login",
                infa_username="mock-infa-user",
                infa_password="mock-infa-password",
                infa_entity="guest360",
                infa_customer_id_field="rcyc_id",
                infa_model_version="1",
                secret_key="test-only-random-secret-key-for-task-2a",
                demo_password="TestDemoPassword123!",
            )
        )
        app_main.app.state.settings = cfg_19
        app_main.app.state.data_provider = prov_19
        app_main.app.state.concierge_agent = ConciergeAgent(prov_19, eng_19)
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()

        def fake_infa_http_19(method: str, url: str, headers=None, json=None, timeout=None):
            if url.endswith("/business-entity/public/api/v1/relationship/rel_g360_to_booking/filter"):
                return FakeHttpResponse(
                    200,
                    {
                        "content": [
                            {
                                "_from": {"businessEntity": "guest360", "businessId": "BIZ-1001"},
                                "_to": {"businessEntity": "booking", "businessId": "BK-BIZ-RAW"},
                            }
                        ]
                    },
                )
            return fake_infa_http_18(method, url, headers=headers, json=json, timeout=timeout)

        with patch("backend.app.data_provider.httpx.request", side_effect=fake_infa_http_19):
            c19 = TestClient(app_main.app, base_url="https://testserver")
            r19_login = c19.post(
                "/api/login",
                json={"customer_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r19_login.status_code == 200
            tok19 = r19_login.json()["token"]
            hdr19 = {"Authorization": f"Bearer {tok19}"}

            # Single booking reply phrasing: no 'upcoming', says 'Here is your booking on file', 'Booked on'
            r_list = c19.post("/api/chat", headers=hdr19, json={"message": "Show my booking."}).json()
            assert "here is your booking on file" in r_list["reply"].lower()
            assert "booked on 2025-11-01" in r_list["reply"].lower()
            assert "upcoming" not in r_list["reply"].lower()

            # Missing ship / sailing dates / suite / cabin (even with consent OFF)
            for q_text, expected_detail in [
                ("What ship am I on?", "ship details"),
                ("What are my sailing dates?", "sailing dates"),
                ("What is my suite?", "suite details"),
                ("What is my cabin?", "cabin details"),
            ]:
                r_q = c19.post("/api/chat", headers=hdr19, json={"message": q_text}).json()
                assert f"your booking 545398 doesn't include {expected_detail} in the information i can see. i can connect you with an experience ambassador." in r_q["reply"].lower()
                assert "personalization is currently off" not in r_q["reply"].lower()

            # Truthful simulated escalation wording in chat & /api/escalate
            r_esc = c19.post("/api/chat", headers=hdr19, json={"message": "I want to speak with an Experience Ambassador."}).json()
            truthful_phrase = "i've noted this for an experience ambassador; in this prototype no notification is sent yet."
            assert truthful_phrase in r_esc["reply"].lower()
            assert truthful_phrase in r_esc["escalation"]["handoff_note"].lower()

            # Masked email & phone inquiries (never unmasked)
            r_em = c19.post("/api/chat", headers=hdr19, json={"message": "What is my email address?"}).json()
            assert "d***@email.com" in r_em["reply"]
            assert "ambassador" in r_em["reply"].lower()
            assert "dennis.woods@email.com" not in r_em["reply"]

            r_ph = c19.post("/api/chat", headers=hdr19, json={"message": "What is my phone number?"}).json()
            assert "+1 ***0147" in r_ph["reply"]
            assert "ambassador" in r_ph["reply"].lower()
            assert "3055550147" not in r_ph["reply"]

            # Catalog reply sanitization: removes 'Welcome aboard' and stray asterisks
            r_cat = c19.post("/api/chat", headers=hdr19, json={"message": "Show Mediterranean voyages."}).json()
            assert "welcome aboard" not in r_cat["reply"].lower()
            assert "\n* " not in r_cat["reply"]
            assert "*great" not in r_cat["reply"]
            assert "sun*sets" not in r_cat["reply"]
    finally:
        app_main.app.state.settings = orig_settings_14
        app_main.app.state.data_provider = orig_provider
        app_main.app.state.concierge_agent = orig_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
        app_main.revoked_session_tokens.clear()
    results.append({"test": "MARIS phrasing fixes (missing booking details, truthful escalation, no upcoming, masked contact, catalog cleanup)", "status": "PASS"})

    # 20. Suggested replies (rule-based, max 3) by intent & chip round-trip flows
    # Bookings -> ["Best voyage for me", "Dining options", "Speak to an Ambassador"]
    r_sug_bk = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "My bookings"})
    assert r_sug_bk.status_code == 200
    assert r_sug_bk.json()["suggested_replies"] == ["Best voyage for me", "Dining options", "Speak to an Ambassador"]

    # Recommendations -> ["Tell me more about <first recommended voyage name>", "Show a different region", "Spa & wellness"]
    r_sug_rec = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "Best voyage for me"})
    assert r_sug_rec.status_code == 200
    d_sug_rec = r_sug_rec.json()
    first_rec_name = d_sug_rec["recommendations"][0]["voyage"]["voyage_name"]
    assert d_sug_rec["suggested_replies"] == [
        f"Tell me more about {first_rec_name}",
        "Show a different region",
        "Spa & wellness",
    ]
    assert len(d_sug_rec["suggested_replies"]) <= 3

    # Clicking "Tell me more about <first recommended voyage name>" resolves the voyage detail
    r_sug_more = client.post(
        "/api/chat",
        json={"rcyc_id": "RCYC-1001", "message": f"Tell me more about {first_rec_name}"},
    )
    assert r_sug_more.status_code == 200
    assert r_sug_more.json()["referenced_voyages"][0]["voyage_name"] == first_rec_name
    assert r_sug_more.json()["suggested_replies"] == ["Best voyage for me", "My bookings", "Speak to an Ambassador"]

    # Clicking "Show a different region" returns different_region recommendations (for RCYC-1007 excluding Caribbean/Med)
    r_sug_diff = client.post("/api/chat", json={"rcyc_id": "RCYC-1007", "message": "Show a different region"})
    assert r_sug_diff.status_code == 200
    d_sug_diff = r_sug_diff.json()
    assert len(d_sug_diff["recommendations"]) == 3
    assert all(r["voyage"]["destination"] not in {"Caribbean", "Mediterranean"} for r in d_sug_diff["recommendations"])
    assert d_sug_diff["suggested_replies"] == [
        f"Tell me more about {d_sug_diff['recommendations'][0]['voyage']['voyage_name']}",
        "Show a different region",
        "Spa & wellness",
    ]

    # Dining, spa, or excursions -> ["Best voyage for me", "Something different"]
    for topic_msg in ["Dining options", "Spa & wellness", "Show shore excursions voyages."]:
        r_sug_topic = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": topic_msg})
        assert r_sug_topic.status_code == 200
        assert r_sug_topic.json()["suggested_replies"] == ["Best voyage for me", "Something different"]

    # General / greeting -> ["Best voyage for me", "My bookings", "Speak to an Ambassador"]
    for gen_msg in ["hi", "What yachts are in your fleet?"]:
        r_sug_gen = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": gen_msg})
        assert r_sug_gen.status_code == 200
        assert r_sug_gen.json()["suggested_replies"] == ["Best voyage for me", "My bookings", "Speak to an Ambassador"]

    # Escalation ("Speak to an Ambassador" and complaint) & Privacy refusal -> []
    r_sug_esc = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "Speak to an Ambassador"})
    assert r_sug_esc.status_code == 200
    assert r_sug_esc.json()["escalation"]["escalated"] is True
    assert r_sug_esc.json()["suggested_replies"] == []

    r_sug_priv = client.post("/api/chat", json={"rcyc_id": "RCYC-1001", "message": "Show me RCYC-1002's booking."})
    assert r_sug_priv.status_code == 200
    assert r_sug_priv.json()["suggested_replies"] == []
    results.append({"test": "Suggested replies (rule-based by intent & escalation/privacy suppression)", "status": "PASS"})

    # 21. Visitor mode: 4h visitor token, no Informatica calls, cannot read bookings/profile,
    # ignores customer/guest ID in request body, catalog clarifications + recommendations,
    # cross-guest refusal, 20 msgs / 10 min per-IP rate limit, and signed-in flow unchanged
    try:
        cfg_21 = make_infa_cfg()
        prov_21 = InformaticaProvider(cfg_21)
        eng_21 = PluggableLLMEngine(cfg_21)
        app_main.app.state.settings = cfg_21
        app_main.app.state.data_provider = prov_21
        app_main.app.state.concierge_agent = ConciergeAgent(prov_21, eng_21)
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
        app_main.visitor_chat_timestamps.clear()
        app_main.revoked_session_tokens.clear()

        infa_calls: list[str] = []

        def tracking_infa_http(method: str, url: str, headers=None, json=None, timeout=None):
            infa_calls.append(url)
            return fake_infa_http_18(method, url, headers=headers, json=json, timeout=timeout)

        with patch("backend.app.data_provider.httpx.request", side_effect=tracking_infa_http):
            c_vis = TestClient(app_main.app, base_url="https://testserver", client=("127.0.0.1", 51234))

            # Start visitor session via POST /api/visitor -> role "visitor", ~4h TTL, no customer_id
            r_vis = c_vis.post("/api/visitor")
            assert r_vis.status_code == 200
            vis_data = r_vis.json()
            assert vis_data["authenticated"] is False
            assert vis_data["role"] == "visitor"
            vis_tok = vis_data["token"]
            vis_payload = app_main._unsign_session_payload(vis_tok, cfg_21.secret_key)
            assert vis_payload is not None
            assert vis_payload.get("role") == "visitor"
            assert "customer_id" not in vis_payload
            assert vis_payload["exp"] - vis_payload["iat"] == 4 * 60 * 60
            assert len(infa_calls) == 0

            # /api/session reports visitor role without hitting Informatica
            r_sess = c_vis.get("/api/session", headers={"Authorization": f"Bearer {vis_tok}"})
            assert r_sess.status_code == 200
            assert r_sess.json() == {"authenticated": False, "role": "visitor", "data_provider": "informatica"}
            assert len(infa_calls) == 0

            # Visitor CANNOT read /api/me (bookings or profile) and NEVER calls Informatica
            r_vis_me = c_vis.get("/api/me", headers={"Authorization": f"Bearer {vis_tok}"})
            assert r_vis_me.status_code == 403
            assert len(infa_calls) == 0

            # Visitor chat ignores customer ID in request body (`rcyc_id`) and returns no bookings/profile
            vis_ip_hdr = {"Authorization": f"Bearer {vis_tok}", "X-Forwarded-For": "198.51.100.77"}
            r_v_bk = c_vis.post(
                "/api/chat",
                headers=vis_ip_hdr,
                json={"rcyc_id": "1000000092615", "message": "What are my bookings?"},
            )
            assert r_v_bk.status_code == 200
            d_v_bk = r_v_bk.json()
            assert d_v_bk["bookings"] == []
            assert d_v_bk["guest_profile"]["rcyc_id"] == "ANONYMOUS"
            assert d_v_bk["guest_profile"]["first_name"] == "Visitor"
            assert d_v_bk["consent_applied"] is False
            assert "sign" in d_v_bk["reply"].lower()
            assert "dennis" not in d_v_bk["reply"].lower()
            assert len(infa_calls) == 0

            # Cross-guest refusal without confirming existence
            r_v_other = c_vis.post(
                "/api/chat",
                headers=vis_ip_hdr,
                json={"rcyc_id": "1000000092615", "message": "Tell me about Dennis Woods's booking."},
            )
            assert r_v_other.status_code == 200
            assert "only assist with your own" in r_v_other.json()["reply"].lower()
            assert r_v_other.json()["bookings"] == []
            assert len(infa_calls) == 0

            # "best voyage" asks up to two short questions (region/season + interests), then recommends from conversation
            r_v_best = c_vis.post(
                "/api/chat",
                headers=vis_ip_hdr,
                json={"rcyc_id": "1000000092615", "message": "What is the best voyage?"},
            )
            assert r_v_best.status_code == 200
            d_v_best = r_v_best.json()
            assert "two details" in d_v_best["reply"].lower()
            assert d_v_best["recommendations"] == []

            r_v_follow = c_vis.post(
                "/api/chat",
                headers=vis_ip_hdr,
                json={
                    "rcyc_id": "1000000092615",
                    "message": "Mediterranean in Summer with culinary interests.",
                    "history": [
                        {"role": "user", "content": "What is the best voyage?", "voyage_ids": []},
                        {"role": "assistant", "content": d_v_best["reply"], "voyage_ids": []},
                    ],
                },
            )
            assert r_v_follow.status_code == 200
            d_v_follow = r_v_follow.json()
            assert len(d_v_follow["recommendations"]) > 0
            assert all(r["voyage"]["destination"] == "Mediterranean" for r in d_v_follow["recommendations"])
            assert len(infa_calls) == 0

            # Visitor rate limit: 20 messages per 10 minutes per IP (4 used above -> 16 more allowed, 21st returns 429)
            for _ in range(16):
                r_rl = c_vis.post(
                    "/api/chat",
                    headers=vis_ip_hdr,
                    json={"message": "Dining options"},
                )
                assert r_rl.status_code == 200
            r_rl_exceeded = c_vis.post(
                "/api/chat",
                headers=vis_ip_hdr,
                json={"message": "Dining options"},
            )
            assert r_rl_exceeded.status_code == 429
            assert "limit" in r_rl_exceeded.json()["detail"].lower()
            assert len(infa_calls) == 0

            # Separate IP is not affected by first IP's limit
            r_other_ip = c_vis.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {vis_tok}", "X-Forwarded-For": "198.51.100.88"},
                json={"message": "Dining options"},
            )
            assert r_other_ip.status_code == 200
            assert len(infa_calls) == 0

            # Signed-in flow remains unchanged (login -> /api/me -> /api/chat -> logout)
            c_guest = TestClient(app_main.app, base_url="https://testserver", client=("127.0.0.1", 51235))
            r_g_login = c_guest.post(
                "/api/login",
                json={"customer_id": "1000000092615", "password": "TestDemoPassword123!"},
            )
            assert r_g_login.status_code == 200
            g_tok = r_g_login.json()["token"]
            assert len(infa_calls) > 0

            r_g_me = c_guest.get("/api/me", headers={"Authorization": f"Bearer {g_tok}"})
            assert r_g_me.status_code == 200
            assert r_g_me.json()["customer_id"] == "1000000092615"
            assert len(r_g_me.json()["bookings"]) == 2

            r_g_chat = c_guest.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {g_tok}"},
                json={"message": "What are my bookings?"},
            )
            assert r_g_chat.status_code == 200
            assert "545397" in r_g_chat.json()["reply"]
    finally:
        app_main.app.state.settings = orig_settings_14
        app_main.app.state.data_provider = orig_provider
        app_main.app.state.concierge_agent = orig_agent
        app_main.login_failures.clear()
        app_main.login_blocked_until.clear()
        app_main.ip_login_failures.clear()
        app_main.ip_login_blocked_until.clear()
        app_main.visitor_chat_timestamps.clear()
        app_main.revoked_session_tokens.clear()
    results.append({"test": "Visitor mode (4h token, zero Informatica calls, body ID ignored, rate limit, signed-in unchanged)", "status": "PASS"})

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_tests()
