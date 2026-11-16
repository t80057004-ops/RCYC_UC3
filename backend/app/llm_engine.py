"""Pluggable LLM Engine supporting rule_based, server-side Gemini, Ollama, and Anthropic with silent fallback."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.app.config import Settings, logger, settings
from backend.app.models import (
    Booking,
    EscalationInfo,
    GuestProfile,
    Voyage,
    VoyageRecommendation,
)

RULE_ONLY_INTENTS = {
    "greeting",
    "thanks",
    "refuse_other_guest",
    "contact_inquiry",
    "booking_inquiry",
    "visitor_signin_required",
    "visitor_clarify",
    "suite_catalog",
    "catalog_overview",
    "escalation",
    "complaint",
    "refund",
    "medical",
    "dietary",
    "accessibility",
    "human_escalation",
}


def _strip_models_prefix(model_name: str) -> str:
    return model_name.removeprefix("models/").strip()


def list_gemini_models(api_key: str) -> list[dict[str, Any]]:
    """Call Gemini ListModels and return only model names and supportedGenerationMethods."""
    if not api_key:
        return []
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    headers = {"x-goog-api-key": api_key, "User-Agent": "aistudio-build"}
    with httpx.Client(timeout=8.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    models: list[dict[str, Any]] = []
    for item in data.get("models", []):
        name = str(item.get("name", ""))
        methods = list(item.get("supportedGenerationMethods", []))
        models.append({"name": name, "supportedGenerationMethods": methods})
        logger.info("ListModels | name=%s supportedGenerationMethods=%s", name, methods)
    return models


def choose_generate_content_model(models: list[dict[str, Any]], configured_model: str) -> str:
    """Choose a stable (non-preview) model supporting generateContent strictly from ListModels results."""
    valid_names = [
        _strip_models_prefix(m["name"])
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    if not valid_names:
        return ""

    stable_names = [
        name
        for name in valid_names
        if "preview" not in name.lower()
        and "tts" not in name.lower()
        and "image" not in name.lower()
        and "transcribe" not in name.lower()
        and "computer-use" not in name.lower()
        and "robotics" not in name.lower()
        and name.lower().startswith("gemini-")
    ]
    pool = stable_names or valid_names

    desired = _strip_models_prefix(configured_model)
    if desired and desired in pool:
        return desired

    for preferred in ("gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"):
        if preferred in pool:
            return preferred

    return pool[0]


def _format_currency(amount: int) -> str:
    return f"${amount:,}"


_USED_FIELD_LABELS: dict[str, str] = {
    "preferred_destinations": "preferred regions",
    "sailed_regions": "sailed regions",
    "preferred_suite": "preferred suite",
    "interest_focus": "interest focus",
    "bookings": "bookings",
    "past_voyages": "past voyages",
}


def _clean_catalog_reply(text: str) -> str:
    """Remove repetitive 'Welcome aboard' openings, normalize '* ' bullets, and strip stray asterisks."""
    cleaned = re.sub(
        r"^\s*Welcome aboard(?:[^.!?\n]*[.!,:]\s*|\s+)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    normalized_lines: list[str] = []
    for line in cleaned.splitlines():
        line = re.sub(r"^(\s*)\*\s+", r"\1- ", line)
        # Preserve balanced **bold** spans, then strip any stray unmatched asterisks
        tokens: list[str] = []

        def _hold_bold(match: re.Match[str]) -> str:
            tokens.append(match.group(0))
            return f"\x00BOLD{len(tokens) - 1}\x00"

        line = re.sub(r"\*\*[^*\n]+\*\*", _hold_bold, line)
        line = line.replace("*", "")
        for idx, tok in enumerate(tokens):
            line = line.replace(f"\x00BOLD{idx}\x00", tok)
        normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()


def build_rule_based_reply(
    *,
    profile: GuestProfile,
    bookings: list[Booking],
    intent: str,
    consent_applied: bool,
    recommendations: list[VoyageRecommendation],
    referenced_voyages: list[Voyage],
    escalation: EscalationInfo,
    user_message: str,
    missing_booking_fact: str = "",
    used_profile_fields: list[str] | None = None,
    masked_contact: dict[str, str | None] | None = None,
    visitor_mode: bool = False,
) -> str:
    """Deterministic, warm MARIS response strictly grounded in catalog and profile records."""
    known_guest = (not visitor_mode) and profile.guest_status in {"returning", "new"}
    salutation_name = f", {profile.first_name}" if known_guest and profile.first_name else ""

    if intent == "refuse_other_guest":
        return (
            "For privacy and guest confidentiality, I can only assist with your own verified profile "
            "and cannot share details or bookings for another guest."
        )

    if intent == "visitor_signin_required":
        return (
            "Bookings, personal profile details, and personalized account recommendations require signing in with your Customer ID. "
            "While browsing as a guest, you can explore our **Voyage Collection**, ask about regions, suites, dining, spa & wellness, or shore excursions, "
            "speak with an **Experience Ambassador**, or **sign in** from the top menu for bookings and personalized help."
        )

    if intent == "visitor_clarify":
        return (
            "I would be glad to recommend voyages from our collection based on what you are looking for. Could you share up to two details?\n\n"
            "- **Preferred region or season** (for example, Mediterranean, Caribbean, Alaska, Northern Europe, Asia, or Antarctica — or Spring, Summer, Autumn, or Winter)\n"
            "- **Your interests** (such as culinary & dining, spa & wellness, shore excursions & adventure, or cultural exploration)\n\n"
            "You can also browse the **Voyage Collection**, speak with an **Experience Ambassador**, or **sign in** for bookings and personalized recommendations."
        )

    if intent == "greeting":
        if visitor_mode:
            return (
                "Hello and welcome to The Ritz-Carlton Yacht Collection! "
                "I can help you explore our **Voyage Collection**, regions, suites, dining, spa & wellness, and shore excursions, "
                "connect you with an **Experience Ambassador**, or you may **sign in** for bookings and personalized recommendations."
            )
        if known_guest:
            return (
                f"Hello{salutation_name}! Welcome to The Ritz-Carlton Yacht Collection. "
                "How may I assist you today with our voyages, suites, onboard dining, or your reservations?"
            )
        return (
            "Hello and welcome to The Ritz-Carlton Yacht Collection! "
            "How may I assist you today with exploring our voyages, suites, or onboard experiences?"
        )

    if intent == "thanks":
        if visitor_mode:
            return (
                "You are most welcome. Feel free to explore our **Voyage Collection**, ask about another destination or onboard experience, "
                "speak with an **Experience Ambassador**, or **sign in** anytime for bookings and personalized assistance."
            )
        return (
            f"You are most welcome{salutation_name}. Please let me know whenever I may assist you further "
            "with your yachting plans."
        )

    if intent == "dietary" and not escalation.escalated:
        diet_note = ""
        if consent_applied and profile.dietary_requirements and profile.dietary_requirements != "None":
            diet_note = (
                f" I see your saved preference on file (`{profile.dietary_requirements}`), and our culinary team will note it."
            )
        return (
            f"Our onboard culinary teams accommodate a wide range of dietary preferences, including vegetarian, vegan, gluten-free, kosher-style, and custom preparations.{diet_note} "
            "If you have severe allergies or require advance galley coordination, I can connect you with an Experience Ambassador."
        )

    if intent == "accessibility" and not escalation.escalated:
        acc_note = ""
        if consent_applied and profile.accessibility_requirements and profile.accessibility_requirements != "None":
            acc_note = " I also see accessibility preferences noted on your file."
        return (
            f"We offer accessible suites and tailored embarkation assistance across the fleet.{acc_note} "
            "I can connect you with an Experience Ambassador to confirm specific suite availability and onboard arrangements."
        )

    if escalation.escalated:
        rules = set(escalation.trigger_rules)
        truthful_handoff = "I've noted this for an Experience Ambassador; in this prototype no notification is sent yet."
        if "UNRESOLVED_OPEN_COMPLAINT" in rules or "COMPLAINT_OR_REFUND_INQUIRY" in rules:
            return (
                f"Thank you for reaching out{salutation_name}. Your experience with us is of utmost importance. "
                f"{truthful_handoff}"
            )
        if "MEDICAL_ALLERGY_OR_ACCESSIBILITY" in rules:
            return (
                f"Thank you for sharing those requirements{salutation_name}. Specialized onboard coordination requires an Experience Ambassador. "
                f"{truthful_handoff}"
            )
        if "VIP_CUSTOM_ARRANGEMENT" in rules:
            return (
                f"Certainly{salutation_name}. Bespoke arrangements of this nature are handled by our Senior Experience Ambassadors. "
                f"{truthful_handoff}"
            )
        return f"Certainly{salutation_name}. {truthful_handoff}"

    if intent == "contact_inquiry":
        if profile.guest_status in {"anonymous", "unknown"}:
            return (
                "I do not have contact details on file for an unauthenticated visitor. "
                "An Experience Ambassador can help with guest profile updates."
            )
        lowered = user_message.lower()
        wants_email = any(kw in lowered for kw in ["email", "e-mail"])
        wants_phone = any(kw in lowered for kw in ["phone", "telephone", "mobile"])
        email_val = (masked_contact or {}).get("email")
        phone_val = (masked_contact or {}).get("phone")

        if wants_email and not wants_phone:
            if email_val:
                return f"The email shown in your Guest Details is `{email_val}`. An Experience Ambassador can help with any changes."
            return "No email address is shown in your Guest Details. An Experience Ambassador can help with any changes."
        if wants_phone and not wants_email:
            if phone_val:
                return f"The phone number shown in your Guest Details is `{phone_val}`. An Experience Ambassador can help with any changes."
            return "No phone number is shown in your Guest Details. An Experience Ambassador can help with any changes."

        lines: list[str] = []
        if email_val:
            lines.append(f"- **Email:** `{email_val}`")
        if phone_val:
            lines.append(f"- **Phone:** `{phone_val}`")
        if not lines:
            return "No email or phone number is shown in your Guest Details. An Experience Ambassador can help with any changes."
        return (
            "Here are the contact details shown in your Guest Details:\n\n"
            + "\n".join(lines)
            + "\n\nAn Experience Ambassador can help with any changes."
        )

    if intent == "booking_inquiry":
        if profile.guest_status in {"anonymous", "unknown"}:
            return (
                "I do not have reservation records for an unauthenticated visitor. "
                "If you would like assistance locating or reviewing a booking, I would be happy to connect you with an Experience Ambassador."
            )
        if not consent_applied and not bookings:
            return (
                "Personalization is currently off on your profile, so I cannot access your personal booking or voyage records here. "
                "I would be glad to connect you with an Experience Ambassador for reservation assistance, or share general voyage details."
            )

        lowered = user_message.lower()
        asks_past_count = any(kw in lowered for kw in ["how many", "past voyage", "voyages have i", "previous voyage"])

        if asks_past_count and "booking" not in lowered and "next" not in lowered:
            prev_note = (
                f" (most recently in {profile.previous_voyage_region})"
                if profile.previous_voyage_region and profile.previous_voyage_region != "None"
                else ""
            )
            if bookings:
                return (
                    f"According to your records{salutation_name}, you have completed **{profile.past_voyages}** "
                    f"past voyage{'s' if profile.past_voyages != 1 else ''}{prev_note}, and you currently have "
                    f"**{len(bookings)}** booking{'s' if len(bookings) != 1 else ''} on file."
                )
            return (
                f"According to your records{salutation_name}, you have completed **{profile.past_voyages}** "
                f"past voyage{'s' if profile.past_voyages != 1 else ''}{prev_note}, with no bookings currently on file."
            )

        if not bookings:
            return (
                f"You currently have **no bookings** on file{salutation_name}. "
                "Would you like me to suggest a voyage or connect you with an Experience Ambassador?"
            )

        if missing_booking_fact:
            detail_tokens = [tok.strip() for tok in missing_booking_fact.split(",") if tok.strip()]
            detail_replies: list[str] = []
            missing_any = False
            for b in bookings:
                missing_labels: list[str] = []
                present_parts: list[str] = []
                for tok in detail_tokens:
                    if tok == "ship":
                        if (b.ship or "").strip():
                            present_parts.append(f"ship: {b.ship}")
                        else:
                            missing_labels.append("ship details")
                    elif tok == "sailing_dates":
                        if (b.sailing_dates or "").strip():
                            present_parts.append(f"sailing dates: {b.sailing_dates}")
                        else:
                            missing_labels.append("sailing dates")
                    elif tok == "suite":
                        if (b.suite_category or "").strip():
                            present_parts.append(f"suite: {b.suite_category}")
                        else:
                            missing_labels.append("suite details")
                    elif tok == "cabin":
                        missing_labels.append("cabin details")
                if missing_labels:
                    missing_any = True
                    joined_missing = " or ".join(dict.fromkeys(missing_labels))
                    msg = f"Your booking {b.booking_id} doesn't include {joined_missing} in the information I can see. I can connect you with an Experience Ambassador."
                    if present_parts:
                        msg = f"Booking {b.booking_id} lists {'; '.join(present_parts)}. {msg}"
                    detail_replies.append(msg)
                elif present_parts:
                    label = f"{b.booking_id} ({b.voyage_name})" if b.voyage_name else b.booking_id
                    detail_replies.append(f"Booking {label} lists {'; '.join(present_parts)}.")
            if missing_any or detail_replies:
                return "\n\n".join(detail_replies)

        def _format_booking_line(b: Booking, include_missing_dates_note: bool) -> str:
            if b.voyage_name:
                head = f"- **{b.voyage_name}** (`{b.voyage_id}`, Booking `{b.booking_id}`)"
            else:
                head = f"- **Booking `{b.booking_id}`**" + (f" · Voyage No. `{b.voyage_id}`" if b.voyage_id else "")
            parts: list[str] = []
            if b.destination:
                parts.append(b.destination)
            if b.ship:
                parts.append(b.ship)
            if b.suite_category:
                parts.append(b.suite_category)
            if b.booked_on:
                parts.append(f"Booked on {b.booked_on}")
            if b.status_label:
                parts.append(b.status_label)
            elif b.status_code:
                parts.append(f"Status: {b.status_code}")
            if b.sailing_dates:
                parts.append(f"Sailing {b.sailing_dates}")
            elif include_missing_dates_note:
                parts.append("Sailing dates not listed in record")
            return f"{head}: " + " · ".join(parts) if parts else head

        lines = [_format_booking_line(b, bool(b.voyage_name)) for b in bookings]
        return (
            f"Here {'is your booking on file' if len(bookings) == 1 else f'are your {len(bookings)} bookings on file'}{salutation_name}:\n\n"
            + "\n".join(lines)
            + "\n\nIf you need details not shown here, I can gladly connect you with an Experience Ambassador."
        )

    if intent == "suite_catalog":
        suite_examples = []
        for v in referenced_voyages[:3]:
            suite_examples.append(
                f"- **{v.voyage_name}** (`{v.voyage_id}`, {v.yacht_name}): {v.suite_availability}"
            )
        examples_block = ("\n\n" + "\n".join(suite_examples)) if suite_examples else ""
        return (
            "Across our fleet (*Evrima*, *Ilma*, and *Luminara*), our catalog offers **Terrace Suite**, **Signature Suite**, "
            "**Grand Suite**, **View Suite**, and **Owner's Suite** accommodations (availability varies by sailing)."
            f"{examples_block}\n\n"
            "You can browse the **Voyage Collection** for suite details by itinerary, speak with an **Experience Ambassador** "
            "for live availability, or **sign in** for bookings and personalized help."
        )

    if intent == "catalog_overview":
        lines = [
            f"- **{v.voyage_name}** (`{v.voyage_id}`, {v.destination}) — {v.duration} nights · {v.season} · From **{_format_currency(v.price)}** per guest"
            for v in referenced_voyages
        ]
        highlights_block = ("\n\n" + "\n".join(lines)) if lines else ""
        return (
            "Our **Voyage Collection** features 12 curated sailings across the **Mediterranean**, **Caribbean**, **Alaska**, "
            "**Northern Europe**, **Asia**, and **Antarctica** aboard *Evrima*, *Ilma*, and *Luminara*."
            f"{highlights_block}\n\n"
            "You can open **Voyage Collection** in the header to browse every itinerary, ask about a specific region or experience, "
            "speak with an **Experience Ambassador**, or **sign in** for bookings and personalized help."
        )

    if intent == "voyage_detail" and referenced_voyages:
        v = referenced_voyages[0]
        visitor_footer = (
            "\n\nYou can also browse our **Voyage Collection**, speak with an **Experience Ambassador**, or **sign in** for bookings and personalized help."
            if visitor_mode
            else ""
        )
        return (
            f"Here are the catalog details for **{v.voyage_name}** (`{v.voyage_id}`) aboard {v.yacht_name}:\n\n"
            f"- **Region & Season:** {v.destination} · {v.season} · {v.duration} nights · From {_format_currency(v.price)} per guest\n"
            f"- **Ports:** {v.itinerary_ports}\n"
            f"- **Highlights:** {v.highlights}\n"
            f"- **Culinary:** {v.culinary_experiences}\n"
            f"- **Wellness:** {v.wellness_experiences}\n"
            f"- **Suites Available:** {v.suite_availability}"
            f"{visitor_footer}"
        )

    if intent == "region_catalog" and referenced_voyages:
        region_name = referenced_voyages[0].destination
        lines = [
            f"- **{v.voyage_name}** (`{v.voyage_id}`, {v.yacht_name}): {v.duration} nights · {v.season} · From **{_format_currency(v.price)}** per guest · Suites: {v.suite_availability}"
            for v in referenced_voyages
        ]
        consent_note = (
            "Personalization is currently off, so I am sharing our general catalog options. "
            if known_guest and not consent_applied
            else ""
        )
        visitor_footer = (
            "\n\nYou can browse the full **Voyage Collection**, speak with an **Experience Ambassador**, or **sign in** for personalized assistance."
            if visitor_mode
            else ""
        )
        return (
            f"{consent_note}We currently offer **{len(referenced_voyages)}** {region_name} voyage{'s' if len(referenced_voyages) != 1 else ''}:\n\n"
            + "\n".join(lines)
            + visitor_footer
        )

    if recommendations:
        if visitor_mode:
            intro = "Based on what you shared in this conversation, here are catalog voyages that match your interests:\n\n"
        elif known_guest and not consent_applied:
            intro = (
                "Personalization is currently off on your profile, so I am sharing general voyage options from our catalog without using your personal history:\n\n"
            )
        elif intent == "different_region":
            if consent_applied and (profile.sailed_regions or profile.previous_voyage_region not in {"", "None"}):
                sailed_list = ", ".join(profile.sailed_regions) if profile.sailed_regions else profile.previous_voyage_region
                intro = (
                    f"Exploring beyond your previous sailing regions ({sailed_list}), here are three voyages in new destinations:\n\n"
                )
            else:
                intro = "Here are three voyages across distinct regions of our collection:\n\n"
        elif consent_applied:
            labels = [_USED_FIELD_LABELS[f] for f in (used_profile_fields or []) if f in _USED_FIELD_LABELS]
            if labels:
                intro = f"Personalized using your {', '.join(labels)}{salutation_name}, here are three curated voyages for you:\n\n"
            else:
                intro = (
                    f"With personalization active (no saved region, suite, or voyage history fields on file yet){salutation_name}, "
                    "here are three curated voyages from our catalog:\n\n"
                )
        else:
            intro = "Here are three signature voyages from our current collection:\n\n"

        rec_lines = []
        for idx, rec in enumerate(recommendations, start=1):
            v = rec.voyage
            reason_summary = " ".join(rec.match_reasons[:2])
            rec_lines.append(
                f"{idx}. **{v.voyage_name}** (`{v.voyage_id}`) — {v.destination} · {v.duration} nights · "
                f"From **{_format_currency(v.price)}** ({v.yacht_name}, {v.season})\n"
                f"   {reason_summary}"
            )
        visitor_footer = (
            "\n\nYou can also browse our **Voyage Collection**, speak with an **Experience Ambassador**, or **sign in** for bookings and personalized help."
            if visitor_mode
            else ""
        )
        return intro + "\n".join(rec_lines) + visitor_footer

    # Concise general inquiry without unsolicited recommendations
    if visitor_mode:
        return (
            "I would be glad to help you explore our **Voyage Collection** across the Mediterranean, Caribbean, Alaska, "
            "Northern Europe, Asia, and Antarctica—including suites, dining, spa & wellness, and shore excursions. "
            "You can also speak with an **Experience Ambassador** or **sign in** for bookings and personalized assistance."
        )

    if profile.guest_status == "unknown":
        return (
            "I could not verify that ID in our sample directory. You may select a sample guest from Demo mode or ask about our destinations and voyages."
        )

    return (
        f"I would be pleased to help{salutation_name}. You can ask me for personalized voyage recommendations, "
        "explore Mediterranean, Caribbean, Alaska, Northern Europe, Asia, or Antarctica itineraries, check your bookings on file, or connect with an Experience Ambassador."
    )


class PluggableLLMEngine:
    """Server-side LLM phrasing engine with silent rule-based fallback."""

    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or settings
        self.available_models: list[dict[str, Any]] = []
        self.selected_gemini_model: str = _strip_models_prefix(self.cfg.gemini_model)
        self.last_gemini_check: dict[str, Any] = {}

    def refresh_gemini_models(self) -> list[dict[str, Any]]:
        """Discover Gemini models via ListModels and pick a valid generateContent model."""
        if not self.cfg.gemini_api_key:
            return []
        self.available_models = list_gemini_models(self.cfg.gemini_api_key)
        chosen = choose_generate_content_model(self.available_models, self.cfg.gemini_model)
        if chosen:
            self.selected_gemini_model = chosen
            logger.info("Selected Gemini model supporting generateContent: %s", chosen)
        return self.available_models

    def generate_reply(
        self,
        *,
        profile: GuestProfile,
        bookings: list[Booking],
        intent: str,
        consent_applied: bool,
        recommendations: list[VoyageRecommendation],
        referenced_voyages: list[Voyage],
        escalation: EscalationInfo,
        user_message: str,
        missing_booking_fact: str = "",
        used_profile_fields: list[str] | None = None,
        masked_contact: dict[str, str | None] | None = None,
        visitor_mode: bool = False,
    ) -> tuple[str, str, bool]:
        """Generate grounded response. Falls back silently to rule_based on any failure."""
        rule_reply = build_rule_based_reply(
            profile=profile,
            bookings=bookings,
            intent=intent,
            consent_applied=consent_applied,
            recommendations=recommendations,
            referenced_voyages=referenced_voyages,
            escalation=escalation,
            user_message=user_message,
            missing_booking_fact=missing_booking_fact,
            used_profile_fields=used_profile_fields,
            masked_contact=masked_contact,
            visitor_mode=visitor_mode,
        )

        # Deterministic safety, privacy, booking, contact, complaint, refund, medical,
        # dietary, accessibility, visitor clarifying/sign-in, and escalation turns NEVER call Gemini.
        if escalation.escalated or intent in RULE_ONLY_INTENTS:
            return rule_reply, "rule_based", False

        provider = self.cfg.llm_provider
        if provider == "rule_based":
            return rule_reply, "rule_based", False

        facts = self._build_facts_payload(
            profile=profile,
            intent=intent,
            consent_applied=consent_applied,
            recommendations=recommendations,
            referenced_voyages=referenced_voyages,
            user_message=user_message,
        )

        if provider == "gemini":
            try:
                text = self._call_gemini(facts)
                if text:
                    text = _clean_catalog_reply(text)
                    if (not visitor_mode) and profile.guest_status in {"returning", "new"} and not consent_applied:
                        if "personalization is currently off" not in text.lower():
                            text = (
                                "Personalization is currently off on your profile, so I am sharing general voyage options from our catalog without using your personal history:\n\n"
                                + text
                            )
                    elif (not visitor_mode) and consent_applied and recommendations:
                        labels = [_USED_FIELD_LABELS[f] for f in (used_profile_fields or []) if f in _USED_FIELD_LABELS]
                        if labels:
                            text += f"\n\nPersonalized using your {', '.join(labels)}."
                        else:
                            text += "\n\nNo saved region, suite, or voyage history fields were on file; recommendations come from the public catalog."
                    return text, f"gemini:{self.selected_gemini_model}", False
            except Exception as exc:
                logger.warning("Gemini phrasing unavailable (%s); falling back silently to rule_based.", exc)
                return rule_reply, "rule_based", True

        if provider == "ollama":
            try:
                text = self._call_ollama(facts)
                if text:
                    return text, f"ollama:{self.cfg.ollama_model}", False
            except Exception as exc:
                logger.warning("Ollama failed (%s); falling back silently to rule_based.", exc)
                return rule_reply, "rule_based", True

        if provider == "anthropic":
            try:
                text = self._call_anthropic(facts)
                if text:
                    return text, f"anthropic:{self.cfg.anthropic_model}", False
            except Exception as exc:
                logger.warning("Anthropic failed (%s); falling back silently to rule_based.", exc)
                return rule_reply, "rule_based", True

        return rule_reply, "rule_based", False

    def _build_facts_payload(
        self,
        *,
        profile: GuestProfile,
        intent: str,
        consent_applied: bool,
        recommendations: list[VoyageRecommendation],
        referenced_voyages: list[Voyage],
        user_message: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_message": user_message,
            "intent": intent,
            "catalog_voyages": [
                {
                    "voyage_id": r.voyage.voyage_id,
                    "voyage_name": r.voyage.voyage_name,
                    "destination": r.voyage.destination,
                    "duration": r.voyage.duration,
                    "price": r.voyage.price,
                    "season": r.voyage.season,
                    "suites": r.voyage.suite_availability,
                    "highlights": r.voyage.highlights,
                }
                for r in recommendations
            ]
            + [
                {
                    "voyage_id": v.voyage_id,
                    "voyage_name": v.voyage_name,
                    "destination": v.destination,
                    "duration": v.duration,
                    "price": v.price,
                    "season": v.season,
                    "suites": v.suite_availability,
                    "ports": v.itinerary_ports,
                    "highlights": v.highlights,
                    "culinary": v.culinary_experiences,
                    "wellness": v.wellness_experiences,
                }
                for v in referenced_voyages
            ],
        }
        if consent_applied and profile.first_name:
            payload["first_name"] = profile.first_name
        return payload

    def _system_prompt(self) -> str:
        return (
            "You are MARIS, the luxury yacht concierge for The Ritz-Carlton Yacht Collection. "
            "Phrase a warm, concise response strictly from the supplied JSON facts. "
            "CRITICAL RULES: "
            "1. Use ONLY voyage names, destinations, durations, prices, seasons, suites, highlights, and ports present in catalog_voyages. "
            "2. NEVER invent dates, prices, availability, preferred suites, past sailings, loyalty tiers, or personal preferences not in the JSON. "
            "3. Do NOT include any numeric match scores or technical labels like 'rule_based' or 'Guest 360'. "
            "4. If first_name is absent from the JSON, do not address the guest by name. "
            "5. Do NOT open with 'Welcome aboard' or repetitive greetings; answer directly, use '- ' for bullets, and avoid stray asterisks."
        )

    def _call_gemini(self, facts: dict[str, Any]) -> str:
        if not self.cfg.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not configured in server environment.")

        if not self.available_models and "invalid" not in self.cfg.gemini_api_key.lower():
            try:
                self.refresh_gemini_models()
            except Exception as exc:
                logger.warning("Gemini ListModels lookup skipped (%s).", exc)

        model_name = self.selected_gemini_model or _strip_models_prefix(self.cfg.gemini_model)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build",
            "x-goog-api-key": self.cfg.gemini_api_key,
        }
        payload = {
            "systemInstruction": {"parts": [{"text": self._system_prompt()}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(facts)}]}],
        }
        http_status: int | str = "error"
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                http_status = resp.status_code
                resp.raise_for_status()
                data = resp.json()

            candidates = data.get("candidates") or []
            if not candidates:
                self.last_gemini_check = {"model": model_name, "http_status": http_status, "phrasing_source": "fallback"}
                logger.info("Gemini phrasing | model=%s http_status=%s phrasing_source=fallback", model_name, http_status)
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
            source = "gemini" if text else "fallback"
            self.last_gemini_check = {"model": model_name, "http_status": http_status, "phrasing_source": source}
            logger.info("Gemini phrasing | model=%s http_status=%s phrasing_source=%s", model_name, http_status, source)
            return text
        except httpx.HTTPStatusError as exc:
            http_status = exc.response.status_code
            err_msg = ""
            try:
                err_msg = str(exc.response.json().get("error", {}).get("message", ""))[:160]
            except Exception:
                err_msg = str(exc.response.reason_phrase or "")[:160]
            self.last_gemini_check = {"model": model_name, "http_status": http_status, "phrasing_source": "fallback", "reason": err_msg}
            logger.info("Gemini phrasing | model=%s http_status=%s phrasing_source=fallback", model_name, http_status)
            raise
        except Exception:
            self.last_gemini_check = {"model": model_name, "http_status": http_status, "phrasing_source": "fallback"}
            logger.info("Gemini phrasing | model=%s http_status=%s phrasing_source=fallback", model_name, http_status)
            raise

    def _call_ollama(self, facts: dict[str, Any]) -> str:
        payload = {
            "model": self.cfg.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(facts)},
            ],
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(f"{self.cfg.ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return str(data.get("message", {}).get("content", "")).strip()

    def _call_anthropic(self, facts: dict[str, Any]) -> str:
        if not self.cfg.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured.")
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key)
        message = client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=500,
            system=self._system_prompt(),
            messages=[{"role": "user", "content": json.dumps(facts)}],
        )
        blocks = [getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text"]
        return "\n".join(blocks).strip()

    def generate_conversation_title(self, user_message: str) -> str:
        """Generate a 2-5 word title using Gemini when GEMINI_API_KEY is set, with rule-based fallback."""
        clean_input = str(user_message or "").strip()
        if not clean_input:
            return "General question"

        if self.cfg.gemini_api_key:
            try:
                raw_title = self._call_gemini_for_title(clean_input)
                validated = _validate_gemini_title(raw_title)
                if validated:
                    return validated
            except Exception as exc:
                logger.info("Gemini title generation fallback (%s).", exc)

        return _build_rule_based_title(clean_input)

    def _call_gemini_for_title(self, user_message: str) -> str:
        if not self.cfg.gemini_api_key:
            return ""
        if not self.available_models and "invalid" not in self.cfg.gemini_api_key.lower():
            try:
                self.refresh_gemini_models()
            except Exception as exc:
                logger.warning("Gemini ListModels lookup skipped (%s).", exc)

        model_name = self.selected_gemini_model or _strip_models_prefix(self.cfg.gemini_model)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build",
            "x-goog-api-key": self.cfg.gemini_api_key,
        }
        system_prompt = (
            "Write a short 2 to 5 word title describing what the guest asked. "
            "Rules: maximum 5 words, plain text only, do not repeat the full question verbatim, "
            "no personal names, no IDs or reference numbers, no email addresses, no phone numbers, and no quote marks."
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        }
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return " ".join(p.get("text", "") for p in parts if p.get("text")).strip()


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{5,}\d)")
_ID_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b|#\w+")
_QUOTE_CHARS_RE = re.compile(r"[\"'`“”‘’]+")


def _strip_pii_from_title(text: str) -> str:
    """Remove emails, phone numbers, IDs, quote marks, and stray punctuation from any title."""
    cleaned = _EMAIL_RE.sub(" ", str(text or ""))
    cleaned = _PHONE_RE.sub(" ", cleaned)
    cleaned = _ID_TOKEN_RE.sub(" ", cleaned)
    cleaned = _QUOTE_CHARS_RE.sub("", cleaned)
    cleaned = re.sub(r"[*_#\[\]{}()<>|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;!?-/")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _validate_gemini_title(raw_title: str) -> str | None:
    """Ensure Gemini title is 2-5 words, clean, non-empty, and free of quotes/PII."""
    if not raw_title:
        return None
    first_line = str(raw_title).splitlines()[0].strip()
    cleaned = _strip_pii_from_title(first_line)
    if not cleaned:
        return None
    if cleaned.lower() in {"new chat", "new conversation", "untitled"}:
        return None
    words = [w for w in cleaned.split() if w]
    if not (2 <= len(words) <= 5):
        return None
    if len(cleaned) > 52:
        return None
    return " ".join(words)


def _build_rule_based_title(message: str) -> str:
    """Deterministic 2-5 word title from intent/topic keywords."""
    lower = str(message or "").lower()

    if any(
        kw in lower
        for kw in (
            "ambassador",
            "representative",
            "human",
            "speak to",
            "talk to",
            "complaint",
            "refund",
            "dispute",
            "medical",
            "allergy",
            "wheelchair",
            "accessibility",
        )
    ):
        return "Speak to an Ambassador"

    if any(
        kw in lower
        for kw in (
            "booking",
            "bookings",
            "reservation",
            "reservations",
            "booked",
            "sailing date",
            "sailing dates",
            "which ship",
            "what ship",
            "cabin",
            "my trip",
            "my cruise",
            "my voyage",
        )
    ):
        return "My bookings"

    if any(kw in lower for kw in ("loyalty", "tier", "marriott", "bonvoy", "vip", "membership", "points")):
        return "Loyalty tier question"

    if any(
        kw in lower
        for kw in (
            "best voyage",
            "recommend",
            "recommendation",
            "suggest",
            "for me",
            "something different",
            "which voyage",
            "pick a voyage",
            "tailored",
        )
    ):
        return "Best voyage recommendation"

    if any(kw in lower for kw in ("dining", "restaurant", "culinary", "food", "chef", "wine", "cuisine", "dietary")):
        return "Dining options"

    if any(kw in lower for kw in ("spa", "wellness", "massage", "fitness", "salon", "thermal")):
        return "Spa and wellness"

    if any(kw in lower for kw in ("excursion", "excursions", "shore", "tour", "tours", "port", "ports", "adventure")):
        return "Shore excursions"

    region_titles = [
        (("mediterranean",), "Mediterranean voyages"),
        (("caribbean",), "Caribbean voyages"),
        (("alaska",), "Alaska voyages"),
        (("northern europe", "baltic", "norway", "scandinavia", "iceland"), "Northern Europe voyages"),
        (("asia", "japan"), "Asia voyages"),
        (("antarctica",), "Antarctica voyages"),
        (("greek", "greece"), "Greek Isles voyages"),
        (("italy", "italian", "amalfi"), "Italy voyages"),
        (("spain", "spanish"), "Spain voyages"),
        (("france", "french riviera", "riviera"), "French Riviera voyages"),
    ]
    for keywords, title in region_titles:
        if any(kw in lower for kw in keywords):
            return title

    if any(kw in lower for kw in ("email", "e-mail", "phone", "telephone", "mobile", "contact")):
        return "Contact details question"

    if any(kw in lower for kw in ("suite", "suites", "penthouse", "terrace", "loft")):
        return "Suite options inquiry"

    if any(kw in lower for kw in ("price", "cost", "fare", "pricing", "rate")):
        return "Voyage pricing question"

    if any(kw in lower for kw in ("yacht", "yachts", "evrima", "ilma", "luminara", "fleet")):
        return "Yacht fleet details"

    if any(kw in lower for kw in ("catalog", "collection", "voyages", "voyage", "itinerary", "itineraries", "cruises")):
        return "Voyage collection inquiry"

    return _strip_pii_from_title("General question") or "General question"

