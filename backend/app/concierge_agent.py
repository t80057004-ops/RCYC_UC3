"""Core orchestrator for MARIS RCYC Concierge Agent calling only GuestDataProvider."""

from __future__ import annotations

import re

from backend.app.config import logger
from backend.app.data_provider import GuestDataProvider, InformaticaProvider, build_anonymous_profile
from backend.app.escalation_engine import evaluate_escalation
from backend.app.llm_engine import PluggableLLMEngine
from backend.app.models import (
    Booking,
    ChatRequest,
    ChatResponse,
    EscalationInfo,
    GuestProfile,
    Voyage,
    VoyageRecommendation,
    to_public_profile,
)
from backend.app.recommendation_engine import detect_query_focus, recommend_voyages

DIETARY_KEYWORDS = [
    "dietary",
    "diet",
    "gluten",
    "celiac",
    "vegan",
    "vegetarian",
    "kosher",
    "halal",
    "lactose",
    "dairy-free",
    "nut-free",
]

ACCESSIBILITY_LOCAL_KEYWORDS = [
    "accessible",
    "accessibility",
    "wheelchair",
    "mobility",
    "elevator",
    "step-free",
]


GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|greetings|hola|bonjour)[\s!.,?]*$",
    re.IGNORECASE,
)
THANKS_PATTERNS = re.compile(
    r"^\s*(thanks|thank you|thx|many thanks|much appreciated|appreciate it|cheers)[\s!.,?]*$",
    re.IGNORECASE,
)
RCYC_ID_REGEX = re.compile(r"\bRCYC-\d{3,6}\b", re.IGNORECASE)

DESTINATION_ALIASES: dict[str, list[str]] = {
    "Mediterranean": ["mediterranean", "med", "amalfi", "positano", "santorini", "riviera", "mallorca", "greece", "italy", "monaco"],
    "Caribbean": ["caribbean", "st. barths", "st barths", "barbuda", "grenadines", "tobago cays", "st. lucia", "virgin gorda"],
    "Alaska": ["alaska", "glacier bay", "hubbard", "tracy arm", "misty fjords", "juneau", "ketchikan", "sitka"],
    "Northern Europe": ["northern europe", "fjord", "norway", "norwegian", "baltic", "stockholm", "iceland", "reykjavik", "copenhagen"],
    "Asia": ["asia", "japan", "kyoto", "tokyo", "vietnam", "ha long", "thailand", "singapore", "hong kong"],
    "Antarctica": ["antarctica", "antarctic", "drake passage", "south georgia", "penguin", "polar"],
}


def _build_unknown_profile(rcyc_id: str) -> GuestProfile:
    return GuestProfile(
        rcyc_id=rcyc_id,
        first_name="Guest",
        last_name="",
        loyalty_tier="Unverified",
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
        profile_label="ID Not Found",
        guest_status="unknown",
    )


def _build_suggested_replies(
    intent: str,
    recommendations: list[VoyageRecommendation],
    referenced_voyages: list[Voyage],
    escalation: EscalationInfo,
    user_message: str,
) -> list[str]:
    if escalation.escalated or intent == "refuse_other_guest":
        return []
    lowered = user_message.lower()
    if intent == "booking_inquiry" or any(kw in lowered for kw in ["booking", "reservation", "sailing"]):
        return ["Best voyage for me", "Dining options", "Speak to an Ambassador"]
    if recommendations or referenced_voyages or intent in {"recommendation", "different_region", "voyage_detail", "region_catalog"}:
        names = [r.voyage.voyage_name for r in recommendations[:2]] + [v.voyage_name for v in referenced_voyages[:2]]
        unique_names = list(dict.fromkeys(names))[:2]
        if unique_names:
            return unique_names + ["Speak to an Ambassador"]
    if any(kw in lowered for kw in ["dining", "spa", "wellness", "excursion", "shore", "food"]):
        return ["Best voyage for me", "Something different", "Speak to an Ambassador"]
    if intent in {"greeting", "thanks"}:
        return ["Best voyage for me", "Dining options", "Speak to an Ambassador"]
    return ["Best voyage for me", "My bookings", "Speak to an Ambassador"]


class ConciergeAgent:
    """Coordinates intent handling, privacy checks, escalation, recommendations, and LLM phrasing."""

    def __init__(self, data_provider: GuestDataProvider, llm_engine: PluggableLLMEngine) -> None:
        self.data_provider = data_provider
        self.llm_engine = llm_engine

    def _detect_destinations(self, text: str) -> list[str]:
        lowered = text.lower()
        return [
            region
            for region, kws in DESTINATION_ALIASES.items()
            if any(kw in lowered for kw in kws)
        ]

    def _detect_voyage_in_text(self, text: str, voyages: list[Voyage]) -> Voyage | None:
        lowered = text.lower()
        for v in voyages:
            if v.voyage_id.lower() in lowered or v.voyage_name.lower() in lowered:
                return v
        return None

    def _is_other_guest_request(self, message: str, active_profile: GuestProfile) -> bool:
        lowered = message.lower()
        if any(
            phrase in lowered
            for phrase in [
                "another guest",
                "other guest",
                "someone else",
                "other passenger",
                "another passenger",
                "other member",
                "different guest",
            ]
        ):
            return True

        # Check if user typed a different RCYC_ID or long Customer ID in the message
        for match in RCYC_ID_REGEX.findall(message):
            if match.upper() != active_profile.rcyc_id.upper():
                return True
        for num in re.findall(r"\b\d{7,30}\b", message):
            if num != active_profile.rcyc_id:
                return True

        # Check if user asks about another sample guest by name
        sample_guests = self.data_provider.listSampleGuests()
        for g in sample_guests:
            if g.rcyc_id.upper() == active_profile.rcyc_id.upper():
                continue
            first = g.full_name.split()[0].lower() if g.full_name else ""
            full = g.full_name.lower()
            if full and full in lowered:
                return True
            if first and re.search(rf"\b{re.escape(first)}\b", lowered) and any(
                kw in lowered for kw in ["booking", "profile", "voyage", "detail", "info", "about", "status", "complaint"]
            ):
                return True

        return False

    def _resolve_last_voyage_from_history(self, request: ChatRequest, voyages: list[Voyage]) -> Voyage | None:
        by_id = {v.voyage_id.upper(): v for v in voyages}
        for turn in reversed(request.history):
            for vid in turn.voyage_ids:
                if vid.upper() in by_id:
                    return by_id[vid.upper()]
            found = self._detect_voyage_in_text(turn.content, voyages)
            if found:
                return found
        return None

    def handle_chat(
        self,
        request: ChatRequest,
        session_customer_id: str | None = None,
    ) -> ChatResponse:
        is_infa_provider = isinstance(self.data_provider, InformaticaProvider)
        if session_customer_id is not None:
            requested_id = session_customer_id.strip()
        else:
            requested_id = (request.rcyc_id or "ANONYMOUS").strip()
            if not is_infa_provider:
                requested_id = requested_id.upper()
        profile = self.data_provider.getProfile(requested_id)

        if profile is None:
            profile = _build_unknown_profile(requested_id)
            guest_recognized = False
            bookings: list[Booking] = []
        elif profile.guest_status == "anonymous":
            guest_recognized = False
            bookings = []
        else:
            guest_recognized = True
            bookings = self.data_provider.getBookings(profile.rcyc_id)

        consent_applied = bool(guest_recognized and profile.personalization_consent)
        allow_booking_records = bool(consent_applied or (guest_recognized and is_infa_provider))
        used_fields: list[str] = []
        lowered = request.message.lower().strip()

        # 1. Cross-guest privacy refusal (strictly before anything else)
        if self._is_other_guest_request(request.message, profile):
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent="refuse_other_guest",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if consent_applied else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=[],
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 2. Greetings & Thanks — warm short reply, ZERO voyage recommendations
        if GREETING_PATTERNS.match(request.message) or THANKS_PATTERNS.match(request.message):
            intent = "greeting" if GREETING_PATTERNS.match(request.message) else "thanks"
            if consent_applied:
                used_fields.append("first_name")
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent=intent,
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if consent_applied else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=used_fields,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 3. Experience Ambassador Escalation Check (complaint, refund, medical, allergy, wheelchair, human)
        escalation = evaluate_escalation(profile, request.message, request.history)
        if escalation.escalated:
            if consent_applied:
                used_fields.extend(["rcyc_id", "loyalty_tier"])
                if profile.open_complaint_status:
                    used_fields.append("open_complaint_status")
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=bookings if consent_applied else [],
                intent="escalation",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=escalation,
                user_message=request.message,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if consent_applied else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                recommendations=[],
                referenced_voyages=[],
                escalation=escalation,
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 3b. Local-only Dietary & Accessibility inquiries (never sent to Gemini)
        if any(kw in lowered for kw in DIETARY_KEYWORDS) or any(kw in lowered for kw in ACCESSIBILITY_LOCAL_KEYWORDS):
            local_intent = "accessibility" if any(kw in lowered for kw in ACCESSIBILITY_LOCAL_KEYWORDS) else "dietary"
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent=local_intent,
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if consent_applied else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 3c. Masked contact details inquiry (email / phone) — rule-only, never sends contact info to Gemini
        asks_contact = any(
            kw in lowered
            for kw in [
                "email",
                "e-mail",
                "phone",
                "telephone",
                "mobile number",
                "contact details",
                "contact info",
            ]
        )
        if asks_contact:
            masked_contact = self.data_provider.getMaskedContactInfo(profile.rcyc_id) if guest_recognized else {"email": None, "phone": None}
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent="contact_inquiry",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                masked_contact=masked_contact,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if allow_booking_records else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 4. Booking & Past Voyage Questions
        all_voyages = self.data_provider.listVoyages()
        explicit_voyage = self._detect_voyage_in_text(request.message, all_voyages)
        has_catalog_framing = explicit_voyage is not None or any(
            kw in lowered
            for kw in [
                "suite options",
                "suites available",
                "available suites",
                "catalog",
                "collection",
                "recommend",
                "suggest",
                "show me",
                "voyages",
            ]
        )
        asks_booking_detail_nouns = (
            bool(re.search(r"\b(ship|yacht|suite|cabin|cabins|suites)\b", lowered))
            and not has_catalog_framing
            and (
                any(kw in lowered for kw in ["my ", "booking", "reservation", "am i", "do i", "have i", "on file"])
                or (allow_booking_records and bool(bookings))
            )
        )
        asks_booking = (
            any(
                kw in lowered
                for kw in [
                    "my booking",
                    "my bookings",
                    "booking details",
                    "upcoming booking",
                    "next voyage",
                    "how many voyages",
                    "past voyages",
                    "voyages have i",
                    "sailing date",
                    "sailing dates",
                    "when do i sail",
                    "when am i sailing",
                    "my reservation",
                    "my reservations",
                ]
            )
            or asks_booking_detail_nouns
        )
        if asks_booking:
            missing_fact = ""
            if allow_booking_records:
                if consent_applied:
                    used_fields.extend(["past_voyages", "bookings"])
                requested_details: list[str] = []
                if any(kw in lowered for kw in ["date", "dates", "when do i sail", "when am i sailing", "embark", "depart"]):
                    requested_details.append("sailing_dates")
                if re.search(r"\b(ship|yacht)\b", lowered):
                    requested_details.append("ship")
                if re.search(r"\bsuite\b", lowered):
                    requested_details.append("suite")
                if re.search(r"\bcabin\b", lowered):
                    requested_details.append("cabin")
                if requested_details and bookings:
                    missing_fact = ",".join(requested_details)

            visible_bookings = bookings if allow_booking_records else []
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=visible_bookings,
                intent="booking_inquiry",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                missing_booking_fact=missing_fact,
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=visible_bookings,
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 5. Catalog, Detail, and Recommendation Handling
        detected_regions = self._detect_destinations(request.message)
        detected_focuses = detect_query_focus(request.message)

        asks_recommend = any(
            kw in lowered
            for kw in [
                "best voyage for me",
                "suggest",
                "recommend",
                "dining options",
                "shore excursions",
                "spa & wellness",
                "something different",
            ]
        )
        asks_highlights = any(
            kw in lowered for kw in ["highlight", "itinerary", "ports", "this voyage", "this itinerary", "tell me more"]
        )
        asks_different = any(
            kw in lowered for kw in ["something different", "different from my previous", "new region", "unlike my last"]
        )
        asks_region_catalog = bool(detected_regions) and any(
            kw in lowered for kw in ["price", "cost", "how much", "available", "which ", "voyages", "mediterranean", "alaska", "caribbean", "asia", "antarctica", "northern europe"]
        )

        intent = "general"
        recommendations: list[VoyageRecommendation] = []
        referenced_voyages: list[Voyage] = []

        if explicit_voyage is not None:
            intent = "voyage_detail"
            referenced_voyages = [explicit_voyage]
        elif asks_highlights and not detected_regions:
            ctx_voyage = self._resolve_last_voyage_from_history(request, all_voyages)
            if ctx_voyage is not None:
                intent = "voyage_detail"
                referenced_voyages = [ctx_voyage]
        elif asks_different:
            intent = "different_region"
            recommendations, rec_fields, consent_applied = recommend_voyages(
                profile=profile,
                voyages=all_voyages,
                query=request.message,
                destination_filter=detected_regions or None,
                focus_filter=detected_focuses or None,
                different_from_previous=True,
                top_k=3,
            )
            used_fields.extend(rec_fields)
        elif asks_recommend or detected_focuses:
            intent = "recommendation"
            recommendations, rec_fields, consent_applied = recommend_voyages(
                profile=profile,
                voyages=all_voyages,
                query=request.message,
                destination_filter=detected_regions or None,
                focus_filter=detected_focuses or None,
                different_from_previous=False,
                top_k=3,
            )
            used_fields.extend(rec_fields)
        elif asks_region_catalog:
            intent = "region_catalog"
            referenced_voyages = [
                v for v in all_voyages if v.destination.lower() in {r.lower() for r in detected_regions}
            ]

        reply, provider_used, fallback = self.llm_engine.generate_reply(
            profile=profile,
            bookings=bookings if consent_applied else [],
            intent=intent,
            consent_applied=consent_applied,
            recommendations=recommendations,
            referenced_voyages=referenced_voyages,
            escalation=EscalationInfo(escalated=False),
            user_message=request.message,
            used_profile_fields=used_fields,
        )

        logger.info(
            "Chat handled | id=%s status=%s consent=%s intent=%s recs=%d refs=%d escalated=False",
            profile.rcyc_id,
            profile.guest_status,
            consent_applied,
            intent,
            len(recommendations),
            len(referenced_voyages),
        )

        sugs = _build_suggested_replies(intent, recommendations, referenced_voyages, EscalationInfo(escalated=False), request.message)
        return ChatResponse(
            reply=reply,
            guest_profile=to_public_profile(profile),
            bookings=bookings if consent_applied else [],
            guest_recognized=guest_recognized,
            guest_status=profile.guest_status,
            consent_applied=consent_applied,
            used_profile_fields=list(dict.fromkeys(used_fields)),
            recommendations=recommendations,
            referenced_voyages=referenced_voyages,
            suggested_replies=sugs,
            escalation=EscalationInfo(escalated=False),
            llm_provider_used=provider_used,
            llm_fallback_triggered=fallback,
        )
