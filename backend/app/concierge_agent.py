"""Core orchestrator for MARIS RCYC Concierge Agent calling only GuestDataProvider."""

from __future__ import annotations

import difflib
import re

from backend.app.config import logger
from backend.app.data_provider import GuestDataProvider, InformaticaProvider, build_anonymous_profile
from backend.app.escalation_engine import evaluate_escalation
from backend.app.llm_engine import PluggableLLMEngine
from backend.app.models import (
    Booking,
    ChatRequest,
    ChatResponse,
    ChatTurn,
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

YACHT_ALIASES: dict[str, list[str]] = {
    "Ilma": ["llma", "ilma", "ilmaa"],
    "Evrima": ["evrima", "eviram", "evirma", "evrema", "evrma"],
    "Luminara": ["luminara", "lumnara", "lumina", "luminar", "luminaria"],
}

_YACHT_FUZZY_STOPWORDS = {"film", "alma", "lima", "mail", "time", "line", "from", "what"}

_SEASON_MONTH_ORDER: dict[str, int] = {
    "spring": 3,
    "summer": 6,
    "autumn": 9,
    "fall": 9,
}


def _voyage_season_sort_key(voyage: Voyage, catalog_idx: int) -> tuple[int, int, int, int]:
    """Sort voyages chronologically by upcoming date/season when available, then catalog order."""
    sailing_date = str(getattr(voyage, "sailing_dates", "") or "").strip()
    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", sailing_date)
    if date_match:
        return (0, int(date_match.group(1)), int(date_match.group(2)), catalog_idx)

    season_raw = str(voyage.season or "").strip().lower()
    year_match = re.search(r"(\d{4})(?:\s*-\s*\d{2,4})?", season_raw)
    year = int(year_match.group(1)) if year_match else 9999
    if "winter" in season_raw:
        # "Winter 2026-27" starts in Dec 2026 before Spring 2027; single-year "Winter 2027" sorts in Jan 2027.
        month = 12 if "-" in season_raw else 1
        return (1, year, month, catalog_idx)
    for token, month in _SEASON_MONTH_ORDER.items():
        if token in season_raw:
            return (1, year, month, catalog_idx)
    return (2, year, 99, catalog_idx)


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


SEASON_ALIASES: dict[str, list[str]] = {
    "Spring": ["spring", "cherry blossom", "april", "may"],
    "Summer": ["summer", "june", "july", "august", "midnight sun"],
    "Autumn": ["autumn", "fall", "september", "october", "november"],
    "Winter": ["winter", "december", "january", "february", "march"],
}

VISITOR_CLARIFY_MARKER = "could you share up to two details?"


def _detect_superlative(lowered: str) -> tuple[str, str, str] | None:
    if re.search(
        r"\b(cheapest|most affordable|lowest price|lowest fare|lowest cost|least expensive|most economical|budget)\b",
        lowered,
    ):
        return ("price", "min", "cheapest")
    if re.search(
        r"\b(most expensive|highest price|highest fare|highest cost|priciest|costliest)\b",
        lowered,
    ):
        return ("price", "max", "most expensive")
    if re.search(r"\b(shortest|fewest nights|fewest days|briefest)\b", lowered):
        return ("duration", "min", "shortest")
    if re.search(r"\b(longest|most nights|most days)\b", lowered):
        return ("duration", "max", "longest")
    return None


def _detect_ordinal_index(lowered: str) -> int | None:
    if re.search(r"\b(first[-\s]?time|my\s+first|at\s+first)\b", lowered):
        return None
    if re.search(
        r"(?:\bthe\s+(?:first|1st)\b|\b(?:first|1st)\s+(?:one|voyage|itinerary|sailing|cruise|option)\b|^\s*(?:first|1st)\s*[?.!]*$)",
        lowered,
    ):
        return 0
    if re.search(
        r"(?:\bthe\s+(?:second|2nd)\b|\b(?:second|2nd)\s+(?:one|voyage|itinerary|sailing|cruise|option)\b|^\s*(?:second|2nd)\s*[?.!]*$)",
        lowered,
    ):
        return 1
    if re.search(
        r"(?:\bthe\s+(?:third|3rd)\b|\b(?:third|3rd)\s+(?:one|voyage|itinerary|sailing|cruise|option)\b|^\s*(?:third|3rd)\s*[?.!]*$)",
        lowered,
    ):
        return 2
    if re.search(
        r"(?:\bthe\s+(?:fourth|4th)\b|\b(?:fourth|4th)\s+(?:one|voyage|itinerary|sailing|cruise|option)\b|^\s*(?:fourth|4th)\s*[?.!]*$)",
        lowered,
    ):
        return 3
    if re.search(
        r"(?:\bthe\s+last\s+(?:one|voyage|itinerary|sailing|cruise|option)\b|^\s*(?:the\s+)?last\s*[?.!]*$)",
        lowered,
    ) and not re.search(r"\bmy\s+last\b", lowered):
        return -1
    return None


def _has_singular_voyage_anaphor(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(that voyage|this voyage|that cruise|this cruise|that sailing|this sailing|that itinerary|this itinerary|this one|that one|the voyage|it|its)\b",
            lowered,
        )
    )


def _has_plural_voyage_anaphor(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(those voyages|these voyages|those options|these options|those ones|these ones|those sailings|these sailings|those cruises|these cruises|both voyages|both of them|all of them|them|they|their)\b",
            lowered,
        )
    )


def _asks_similar_voyages(lowered: str) -> bool:
    if re.search(
        r"\b(similar voyages?|similar itineraries|similar sailings?|similar cruises?|anything like this|something like this|anything like it|something like it|anything like that|something like that|anything similar|something similar|more like this|more like it|comparable voyages?)\b",
        lowered,
    ):
        return True
    return "similar" in lowered and bool(
        re.search(r"\b(voyage|voyages|itinerary|itineraries|cruise|cruises|sailing|sailings|option|options|trips?)\b", lowered)
    )


def _detect_catalog_attributes(lowered: str) -> list[str]:
    attrs: list[str] = []
    if re.search(
        r"\b(embark|embarkation|embarkment|departure port|depart from|departs from|start from|starts from|starting port|homeport|home port|board in|boarding port|leave from|begin in)\b",
        lowered,
    ):
        attrs.append("embarkation")
    if re.search(
        r"\b(how many days|how many nights|how long|duration|number of days|number of nights|length of)\b",
        lowered,
    ):
        attrs.append("duration")
    if re.search(r"\b(price|prices|pricing|cost|costs|how much|fare|fares|rate|rates)\b", lowered):
        attrs.append("price")
    if re.search(
        r"\b(destinations?|ports?|stops?|route|routes|cover|covers|visit|visits|itinerary|itineraries|where does it go|where do they go)\b",
        lowered,
    ):
        attrs.append("destinations")
    if re.search(r"\b(ship|ships|yacht|yachts|vessel|which boat)\b", lowered):
        attrs.append("ship")
    if re.search(r"\b(season|seasons|time of year|what month|months|when does it sail|when do they sail|when is it)\b", lowered):
        attrs.append("season")
    if re.search(r"\b(suite|suites|cabin|cabins|stateroom|staterooms|room types|accommodations)\b", lowered):
        attrs.append("suites")
    return attrs


def _build_suggested_replies(
    intent: str,
    recommendations: list[VoyageRecommendation],
    referenced_voyages: list[Voyage],
    escalation: EscalationInfo,
    user_message: str,
    visitor_mode: bool = False,
    detected_yachts: list[str] | None = None,
    catalog_yachts: list[str] | None = None,
    clarify_candidates: list[Voyage] | None = None,
) -> list[str]:
    if escalation.escalated or intent == "refuse_other_guest":
        return []
    if intent == "clarify_voyage":
        cands = list(clarify_candidates or referenced_voyages)
        if cands:
            sugs = [f"Tell me more about {v.voyage_name}" for v in cands[:2]]
            sugs.append("Which one is the cheapest?")
            return sugs[:3]
    if intent in {"superlative_compare", "catalog_attribute", "similar_voyages"}:
        if visitor_mode:
            if referenced_voyages:
                return [
                    "Do you have any similar voyages?",
                    "Voyage Collection",
                    "Sign in for personal help",
                ]
            return ["Voyage Collection", "Experience Ambassador", "Sign in for personal help"]
        if referenced_voyages:
            v = referenced_voyages[0]
            return [
                f"Tell me more about {v.voyage_name}",
                "Do you have any similar voyages?",
                "Best voyage for me",
            ]
    if intent == "yacht_catalog":
        yachts_used = list(detected_yachts or [])
        all_yachts = list(catalog_yachts or [])
        other_yachts = [y for y in all_yachts if y not in yachts_used]
        compare_target = other_yachts[0] if other_yachts else (all_yachts[0] if all_yachts else "")
        suggestions: list[str] = []
        if referenced_voyages:
            suggestions.append(f"Tell me more about {referenced_voyages[0].voyage_name}")
        if compare_target:
            suggestions.append(f"Compare with {compare_target}")
        suggestions.append("Best voyage for me")
        return suggestions[:3]
    if intent == "card_focus":
        focus_voyages = [r.voyage for r in recommendations] if recommendations else referenced_voyages
        if visitor_mode:
            if focus_voyages:
                return [
                    f"Tell me more about {focus_voyages[0].voyage_name}",
                    "Voyage Collection",
                    "Sign in for personal help",
                ]
            return [
                "Voyage Collection",
                "Experience Ambassador",
                "Sign in for personal help",
            ]
        if focus_voyages:
            return [
                f"Tell me more about {focus_voyages[0].voyage_name}",
                "Best voyage for me",
                "Speak to an Ambassador",
            ]
        return ["Best voyage for me", "My bookings", "Speak to an Ambassador"]
    if visitor_mode:
        if recommendations:
            return [
                f"Tell me more about {recommendations[0].voyage.voyage_name}",
                "Voyage Collection",
                "Sign in for personal help",
            ]
        if intent == "voyage_detail" and referenced_voyages:
            return [
                "Voyage Collection",
                "Experience Ambassador",
                "Sign in for personal help",
            ]
        if referenced_voyages:
            return [
                "Dining options",
                "Voyage Collection",
                "Sign in for personal help",
            ]
        return [
            "Voyage Collection",
            "Experience Ambassador",
            "Sign in for personal help",
        ]
    lowered = user_message.lower()
    if intent == "booking_inquiry":
        return ["Best voyage for me", "Dining options", "Speak to an Ambassador"]
    if intent == "dietary" or any(
        kw in lowered
        for kw in [
            "dining",
            "culinary",
            "restaurant",
            "food",
            "spa",
            "wellness",
            "excursion",
            "shore",
        ]
    ):
        return ["Best voyage for me", "Something different"]
    if recommendations:
        return [
            f"Tell me more about {recommendations[0].voyage.voyage_name}",
            "Show a different region",
            "Spa & wellness",
        ]
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

    def _detect_yachts(self, text: str, all_voyages: list[Voyage]) -> list[str]:
        catalog_yachts = list(
            dict.fromkeys(
                v.yacht_name.strip()
                for v in all_voyages
                if v.yacht_name and v.yacht_name.strip()
            )
        )
        if not catalog_yachts or not text:
            return []

        canonical_by_lower = {y.lower(): y for y in catalog_yachts}
        alias_to_canonical: dict[str, str] = {}
        for y in catalog_yachts:
            alias_to_canonical[y.lower()] = y
            for alias in YACHT_ALIASES.get(y, []):
                alias_to_canonical[alias.lower()] = y

        hits: list[tuple[int, str]] = []
        canonical_keys = list(canonical_by_lower.keys())
        for match in re.finditer(r"\b([A-Za-z]+)(?:'s)?\b", text):
            token = match.group(1).lower()
            pos = match.start()
            if token in alias_to_canonical:
                hits.append((pos, alias_to_canonical[token]))
            elif len(token) >= 4 and token not in _YACHT_FUZZY_STOPWORDS:
                close = difflib.get_close_matches(token, canonical_keys, n=1, cutoff=0.75)
                if close:
                    hits.append((pos, canonical_by_lower[close[0]]))

        hits.sort(key=lambda item: item[0])
        ordered: list[str] = []
        for _, yacht in hits:
            if yacht not in ordered:
                ordered.append(yacht)
        return ordered

    def _mentions_catalog_entity(self, text: str, all_voyages: list[Voyage]) -> bool:
        if self._detect_yachts(text, all_voyages) or self._detect_destinations(text):
            return True
        lowered = text.lower()
        for v in all_voyages:
            if (
                v.voyage_id.lower() in lowered
                or v.voyage_name.lower() in lowered
                or v.destination.lower() in lowered
            ):
                return True
            for seg in re.split(r"\s*[&·,/]\s*", v.voyage_name.lower()):
                seg = seg.strip()
                if len(seg) >= 6 and seg in lowered:
                    return True
        return False

    def _detect_voyage_in_text(self, text: str, voyages: list[Voyage]) -> Voyage | None:
        lowered = text.lower()
        for v in voyages:
            if v.voyage_id.lower() in lowered or v.voyage_name.lower() in lowered:
                return v
        return None

    def _detect_seasons(self, text: str) -> list[str]:
        lowered = text.lower()
        return [
            season
            for season, kws in SEASON_ALIASES.items()
            if any(re.search(rf"\b{re.escape(kw)}\b", lowered) for kw in kws)
        ]

    def _extract_visitor_preferences(
        self, request: ChatRequest, history: list[ChatTurn] | None = None
    ) -> tuple[list[str], list[str], list[str]]:
        """Extract regions, seasons, and interests ONLY from visitor user turns in this conversation."""
        turns = history if history is not None else request.history
        user_texts = [t.content for t in turns if t.role == "user" and t.content]
        user_texts.append(request.message)
        combined = "\n".join(user_texts)

        regions: list[str] = []
        for txt in reversed(user_texts):
            for region in self._detect_destinations(txt):
                if region not in regions:
                    regions.append(region)

        seasons: list[str] = []
        for txt in reversed(user_texts):
            for season in self._detect_seasons(txt):
                if season not in seasons:
                    seasons.append(season)

        focuses = detect_query_focus(combined)
        lowered_combined = combined.lower()
        extra_focus_map = {
            "culinary": ["dining", "culinary", "food", "restaurant", "cuisine"],
            "wellness": ["spa", "wellness", "relax", "relaxation"],
            "adventure": ["excursion", "excursions", "shore", "adventure", "outdoor", "active"],
            "cultural": ["culture", "cultural", "art", "history", "museum", "heritage"],
        }
        for focus, kws in extra_focus_map.items():
            if focus not in focuses and any(kw in lowered_combined for kw in kws):
                focuses.append(focus)

        return regions, seasons, focuses

    def _recommend_for_visitor(
        self,
        *,
        voyages: list[Voyage],
        regions: list[str],
        seasons: list[str],
        focuses: list[str],
        top_k: int = 3,
    ) -> list[VoyageRecommendation]:
        region_set = {r.lower() for r in regions}
        season_set = {s.lower() for s in seasons}
        focus_set = {f.lower() for f in focuses}

        candidates = list(voyages)
        if region_set:
            matched_region = [v for v in candidates if v.destination.lower() in region_set]
            if matched_region:
                candidates = matched_region
        if season_set:
            matched_season = [
                v for v in candidates if any(s in v.season.lower() for s in season_set)
            ]
            if matched_season:
                candidates = matched_season
        if focus_set:
            matched_focus = [
                v for v in candidates if any(f in [pf.lower() for pf in v.primary_focus] for f in focus_set)
            ]
            if matched_focus:
                candidates = matched_focus

        scored: list[VoyageRecommendation] = []
        for v in candidates:
            score = 0
            reasons: list[str] = []
            if region_set and v.destination.lower() in region_set:
                score += 30
                reasons.append(f"Matches your {v.destination} preference from this conversation.")
            if season_set and any(s in v.season.lower() for s in season_set):
                score += 25
                reasons.append(f"Sails in {v.season}.")
            focus_hits = [f for f in focuses if f.lower() in [pf.lower() for pf in v.primary_focus]]
            if focus_hits:
                score += 25
                reasons.append(f"Features {', '.join(focus_hits)} experiences aboard {v.yacht_name}.")
            if not reasons:
                reasons.append(f"{v.duration} nights in {v.destination} aboard {v.yacht_name} ({v.season}).")
            scored.append(
                VoyageRecommendation(
                    voyage=v,
                    score=score,
                    match_reasons=reasons,
                    score_breakdown={},
                )
            )
        scored.sort(key=lambda r: (-r.score, r.voyage.price))
        return scored[:top_k]

    def _select_diverse_voyages(
        self,
        voyages: list[Voyage],
        limit: int = 3,
        preferred_destinations: list[str] | None = None,
    ) -> list[Voyage]:
        """Pick up to `limit` voyages from distinct destinations first, then remaining matches."""
        ordered = list(voyages)
        if preferred_destinations:
            pref_lower = [d.strip().lower() for d in preferred_destinations if d and d.strip()]
            ordered.sort(
                key=lambda v: (
                    0 if v.destination.lower() in pref_lower else 1,
                    pref_lower.index(v.destination.lower()) if v.destination.lower() in pref_lower else 999,
                )
            )

        selected: list[Voyage] = []
        seen_dests: set[str] = set()
        seen_ids: set[str] = set()
        for v in ordered:
            if v.destination not in seen_dests:
                selected.append(v)
                seen_dests.add(v.destination)
                seen_ids.add(v.voyage_id)
            if len(selected) >= limit:
                return selected

        for v in ordered:
            if v.voyage_id not in seen_ids:
                selected.append(v)
                seen_ids.add(v.voyage_id)
            if len(selected) >= limit:
                break
        return selected

    def _is_other_guest_request(
        self,
        message: str,
        active_profile: GuestProfile,
        visitor_mode: bool = False,
    ) -> bool:
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

        if visitor_mode and any(
            kw in lowered for kw in ["booking", "bookings", "reservation", "reservations", "profile", "account", "booked"]
        ):
            if re.search(r"\b[A-Z][a-z]{1,20}\s+[A-Z][a-z]{1,20}'s\b", message) or re.search(
                r"\b(?:about|for|check|is)\s+[A-Z][a-z]{1,20}\s+[A-Z][a-z]{1,20}\b", message
            ):
                return True

        # Check if user asks about another sample guest by name (local sample list only in mock mode)
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

    def _extract_voyages_from_text(self, text: str, voyages: list[Voyage]) -> list[Voyage]:
        lowered = (text or "").lower()
        if not lowered:
            return []
        hits: list[tuple[int, Voyage]] = []
        for v in voyages:
            pos_id = lowered.find(v.voyage_id.lower())
            pos_name = lowered.find(v.voyage_name.lower())
            positions = [p for p in (pos_id, pos_name) if p >= 0]
            if positions:
                hits.append((min(positions), v))
        hits.sort(key=lambda item: item[0])
        ordered: list[Voyage] = []
        seen: set[str] = set()
        for _, v in hits:
            if v.voyage_id not in seen:
                seen.add(v.voyage_id)
                ordered.append(v)
        return ordered

    def _resolve_last_voyages_from_context(
        self,
        *,
        effective_history: list[ChatTurn],
        voyages: list[Voyage],
        explicit_last_voyages: list[str] | None = None,
    ) -> list[Voyage]:
        by_id = {v.voyage_id.upper(): v for v in voyages}
        if explicit_last_voyages is not None:
            resolved: list[Voyage] = []
            seen: set[str] = set()
            for vid in explicit_last_voyages:
                key = str(vid or "").strip().upper()
                if key in by_id and key not in seen:
                    seen.add(key)
                    resolved.append(by_id[key])
            return resolved

        for turn in reversed(effective_history):
            if turn.role != "assistant":
                continue
            if turn.voyage_ids:
                resolved = []
                seen = set()
                for vid in turn.voyage_ids:
                    key = str(vid or "").strip().upper()
                    if key in by_id and key not in seen:
                        seen.add(key)
                        resolved.append(by_id[key])
                return resolved
            return self._extract_voyages_from_text(turn.content or "", voyages)
        return []

    def _find_similar_voyages(
        self,
        base_voyages: list[Voyage],
        all_voyages: list[Voyage],
        limit: int = 3,
    ) -> list[Voyage]:
        excluded_ids = {v.voyage_id.upper() for v in base_voyages}
        base_regions = {v.destination.lower() for v in base_voyages if v.destination}
        base_durations = [v.duration for v in base_voyages if v.duration]

        scored: list[tuple[tuple[int, int, int], Voyage]] = []
        for cand in all_voyages:
            if cand.voyage_id.upper() in excluded_ids:
                continue
            same_region = cand.destination.lower() in base_regions
            min_dur_diff = min((abs(cand.duration - d) for d in base_durations), default=999)
            similar_duration = min_dur_diff <= 3
            if not same_region and not similar_duration:
                continue
            rank = (
                0 if same_region else (1 if min_dur_diff == 0 else 2),
                min_dur_diff,
                cand.price,
            )
            scored.append((rank, cand))

        scored.sort(key=lambda item: item[0])
        return [v for _, v in scored[:limit]]

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
        visitor_mode: bool = False,
        conversation_history: list[ChatTurn] | None = None,
        last_voyages: list[str] | None = None,
    ) -> ChatResponse:
        effective_history = list(
            (conversation_history if conversation_history is not None else request.history)[-8:]
        )
        previous_assistant_text = ""
        for turn in reversed(effective_history):
            if turn.role == "assistant" and turn.content:
                previous_assistant_text = turn.content
                break

        is_infa_provider = isinstance(self.data_provider, InformaticaProvider)
        if visitor_mode:
            profile = build_anonymous_profile()
            guest_recognized = False
            bookings: list[Booking] = []
        else:
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
                bookings = []
            elif profile.guest_status == "anonymous":
                guest_recognized = False
                bookings = []
            else:
                guest_recognized = True
                bookings = self.data_provider.getBookings(profile.rcyc_id)

        consent_applied = bool((not visitor_mode) and guest_recognized and profile.personalization_consent)
        allow_booking_records = bool((not visitor_mode) and (consent_applied or (guest_recognized and is_infa_provider)))
        used_fields: list[str] = []
        lowered = request.message.lower().strip()

        # 1. Cross-guest privacy refusal (strictly before anything else)
        if self._is_other_guest_request(request.message, profile, visitor_mode=visitor_mode):
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent="refuse_other_guest",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                visitor_mode=visitor_mode,
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
        if request.attachment is None and (GREETING_PATTERNS.match(request.message) or THANKS_PATTERNS.match(request.message)):
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
                visitor_mode=visitor_mode,
            )
            sugs = _build_suggested_replies(intent, [], [], EscalationInfo(escalated=False), request.message, visitor_mode=visitor_mode)
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
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 3. Experience Ambassador Escalation Check (complaint, refund, medical, allergy, wheelchair, human)
        escalation = evaluate_escalation(profile, request.message, effective_history)
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
                visitor_mode=visitor_mode,
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

        # 3a. Structured Welcome Card Focus Selection (no LLM needed)
        if request.focus is not None:
            all_voyages = self.data_provider.listVoyages()
            all_destinations = list(dict.fromkeys(v.destination for v in all_voyages))
            focus_val = request.focus
            focus_recs: list[VoyageRecommendation] = []
            focus_refs: list[Voyage] = []

            if focus_val == "voyages":
                pref_dests = list(profile.preferred_destinations) if consent_applied else None
                focus_refs = self._select_diverse_voyages(
                    all_voyages,
                    limit=3,
                    preferred_destinations=pref_dests,
                )
                if consent_applied and profile.preferred_destinations:
                    used_fields.append("preferred_destinations")
            else:
                if focus_val == "culinary":
                    focus_tokens = ["culinary"]
                elif focus_val == "wellness":
                    focus_tokens = ["wellness"]
                else:
                    focus_tokens = ["adventure", "cultural"]

                token_set = {t.lower() for t in focus_tokens}
                filtered_voyages = [
                    v
                    for v in all_voyages
                    if any(pf.lower() in token_set for pf in v.primary_focus)
                ]

                if consent_applied:
                    focus_recs, rec_fields, consent_applied = recommend_voyages(
                        profile=profile,
                        voyages=filtered_voyages,
                        query=request.message,
                        focus_filter=focus_tokens,
                        top_k=3,
                    )
                    used_fields.extend(rec_fields)
                else:
                    focus_refs = self._select_diverse_voyages(filtered_voyages, limit=3)

            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=bookings if consent_applied else [],
                intent="card_focus",
                consent_applied=consent_applied,
                recommendations=focus_recs,
                referenced_voyages=focus_refs,
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                visitor_mode=visitor_mode,
                card_focus=focus_val,
                all_destinations=all_destinations,
            )
            sugs = _build_suggested_replies(
                "card_focus",
                focus_recs,
                focus_refs,
                EscalationInfo(escalated=False),
                request.message,
                visitor_mode=visitor_mode,
            )
            focus_context_ids = [r.voyage.voyage_id for r in focus_recs] + [v.voyage_id for v in focus_refs]
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=bookings if consent_applied else [],
                guest_recognized=guest_recognized,
                guest_status=profile.guest_status,
                consent_applied=consent_applied,
                used_profile_fields=list(dict.fromkeys(used_fields)),
                recommendations=focus_recs,
                referenced_voyages=focus_refs,
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
                context_voyage_ids=focus_context_ids,
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
                visitor_mode=visitor_mode,
            )
            sugs = _build_suggested_replies(local_intent, [], [], EscalationInfo(escalated=False), request.message, visitor_mode=visitor_mode)
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
                suggested_replies=sugs,
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
        if asks_contact and not visitor_mode:
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
            sugs = _build_suggested_replies("contact_inquiry", [], [], EscalationInfo(escalated=False), request.message)
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
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
            )

        # 4. Yacht Catalog, Follow-up Context Resolution & Booking Questions
        all_voyages = self.data_provider.listVoyages()
        catalog_yachts = list(
            dict.fromkeys(
                v.yacht_name.strip()
                for v in all_voyages
                if v.yacht_name and v.yacht_name.strip()
            )
        )
        explicit_voyage = self._detect_voyage_in_text(request.message, all_voyages)
        detected_yachts = self._detect_yachts(request.message, all_voyages)
        detected_regions = self._detect_destinations(request.message)
        last_voyages_objs = self._resolve_last_voyages_from_context(
            effective_history=effective_history,
            voyages=all_voyages,
            explicit_last_voyages=last_voyages,
        )

        superlative = _detect_superlative(lowered)
        ordinal_idx = _detect_ordinal_index(lowered)
        asks_similar = _asks_similar_voyages(lowered)
        catalog_attrs = _detect_catalog_attributes(lowered)
        has_singular_anaphor = _has_singular_voyage_anaphor(lowered)
        has_plural_anaphor = _has_plural_voyage_anaphor(lowered)

        explicit_personal_booking = any(
            kw in lowered
            for kw in [
                "my booking",
                "my bookings",
                "my reservation",
                "my reservations",
                "booking details",
                "upcoming booking",
                "my ship",
                "my yacht",
                "my suite",
                "my cabin",
                "when do i sail",
                "when am i sailing",
                "how many voyages",
                "past voyages",
                "voyages have i",
                "sailing date",
                "sailing dates",
                "am i booked",
                "on file",
            ]
        )
        asks_next_personal_voyage = (
            "next voyage" in lowered
            and not detected_yachts
            and not last_voyages_objs
            and superlative is None
            and ordinal_idx is None
        )
        has_catalog_context_or_ref = bool(
            explicit_voyage is not None
            or superlative is not None
            or asks_similar
            or ordinal_idx is not None
            or "embarkation" in catalog_attrs
            or (
                last_voyages_objs
                and (has_singular_anaphor or has_plural_anaphor or catalog_attrs)
            )
            or detected_regions
        )

        if (
            detected_yachts
            and explicit_voyage is None
            and not explicit_personal_booking
            and superlative is None
            and not asks_similar
            and ordinal_idx is None
        ):
            active_yachts = list(detected_yachts)
            if "compare" in lowered and len(active_yachts) == 1:
                for turn in reversed(effective_history[-4:]):
                    prev_yachts = self._detect_yachts(turn.content or "", all_voyages)
                    prev_other = [y for y in prev_yachts if y not in active_yachts]
                    if prev_other:
                        active_yachts = [prev_other[0], active_yachts[0]]
                        break

            asks_next_voyage = any(
                kw in lowered
                for kw in [
                    "next voyage",
                    "next sailing",
                    "upcoming voyage",
                    "upcoming sailing",
                    "earliest voyage",
                    "soonest",
                ]
            )
            indexed_voyages = list(enumerate(all_voyages))
            region_set = {r.lower() for r in detected_regions}
            no_region_match = False
            yacht_referenced: list[Voyage] = []

            if region_set:
                matched_groups: list[Voyage] = []
                for y in active_yachts:
                    yacht_pairs = [
                        (idx, v)
                        for idx, v in indexed_voyages
                        if v.yacht_name.lower() == y.lower() and v.destination.lower() in region_set
                    ]
                    yacht_pairs.sort(key=lambda pair: _voyage_season_sort_key(pair[1], pair[0]))
                    matched_groups.extend(v for _, v in yacht_pairs)
                if matched_groups:
                    yacht_referenced = matched_groups
                else:
                    no_region_match = True

            if not yacht_referenced:
                for y in active_yachts:
                    yacht_pairs = [
                        (idx, v)
                        for idx, v in indexed_voyages
                        if v.yacht_name.lower() == y.lower()
                    ]
                    yacht_pairs.sort(key=lambda pair: _voyage_season_sort_key(pair[1], pair[0]))
                    yacht_referenced.extend(v for _, v in yacht_pairs)

            yacht_context: dict[str, object] = {
                "yachts": active_yachts,
                "regions": detected_regions,
                "no_region_match": no_region_match,
                "asks_next_voyage": asks_next_voyage,
            }
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent="yacht_catalog",
                consent_applied=consent_applied,
                recommendations=[],
                referenced_voyages=yacht_referenced,
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                used_profile_fields=[],
                visitor_mode=visitor_mode,
                attachment=request.attachment,
                yacht_context=yacht_context,
            )
            sugs = _build_suggested_replies(
                "yacht_catalog",
                [],
                yacht_referenced,
                EscalationInfo(escalated=False),
                request.message,
                visitor_mode=visitor_mode,
                detected_yachts=active_yachts,
                catalog_yachts=catalog_yachts,
            )
            logger.info(
                "Chat handled | id=%s status=%s consent=%s intent=yacht_catalog recs=0 refs=%d escalated=False",
                profile.rcyc_id,
                profile.guest_status,
                consent_applied,
                len(yacht_referenced),
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
                referenced_voyages=yacht_referenced,
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
                context_voyage_ids=[v.voyage_id for v in yacht_referenced],
            )

        has_catalog_framing = explicit_voyage is not None or any(
            kw in lowered
            for kw in [
                "suite options",
                "suites available",
                "available suites",
                "what suites",
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
            and not has_catalog_context_or_ref
            and (
                any(kw in lowered for kw in ["my ", "booking", "reservation", "am i", "do i", "have i", "on file"])
                or (allow_booking_records and bool(bookings))
            )
        )
        asks_booking = explicit_personal_booking or asks_next_personal_voyage or asks_booking_detail_nouns

        if visitor_mode and (
            asks_booking
            or asks_contact
            or any(
                kw in lowered
                for kw in [
                    "my profile",
                    "my details",
                    "my loyalty",
                    "loyalty tier",
                    "am i vip",
                    "my account",
                    "who am i",
                    "what is my name",
                    "my name",
                    "my points",
                    "sign in for personal help",
                    "check my booking",
                    "view my booking",
                ]
            )
        ):
            reply, provider_used, fallback = self.llm_engine.generate_reply(
                profile=profile,
                bookings=[],
                intent="visitor_signin_required",
                consent_applied=False,
                recommendations=[],
                referenced_voyages=[],
                escalation=EscalationInfo(escalated=False),
                user_message=request.message,
                visitor_mode=True,
            )
            sugs = _build_suggested_replies(
                "visitor_signin_required", [], [], EscalationInfo(escalated=False), request.message, visitor_mode=True
            )
            return ChatResponse(
                reply=reply,
                guest_profile=to_public_profile(profile),
                bookings=[],
                guest_recognized=False,
                guest_status=profile.guest_status,
                consent_applied=False,
                used_profile_fields=[],
                recommendations=[],
                referenced_voyages=[],
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
                context_voyage_ids=[],
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
            sugs = _build_suggested_replies("booking_inquiry", [], [], EscalationInfo(escalated=False), request.message)
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
                suggested_replies=sugs,
                escalation=EscalationInfo(escalated=False),
                llm_provider_used=provider_used,
                llm_fallback_triggered=fallback,
                context_voyage_ids=[],
            )

        # 5. Catalog, Context Follow-ups, Detail, and Recommendation Handling
        detected_focuses = detect_query_focus(request.message)

        asks_recommend = any(
            kw in lowered
            for kw in [
                "best voyage for me",
                "best voyage",
                "suggest",
                "recommend",
                "dining options",
                "shore excursions",
                "spa & wellness",
                "something different",
                "different region",
            ]
        )
        asks_best_voyage = any(
            kw in lowered
            for kw in [
                "best voyage",
                "which voyage",
                "pick a voyage",
                "help me choose",
                "recommend a voyage",
                "suggest a voyage",
            ]
        )
        asks_highlights = any(
            kw in lowered for kw in ["highlight", "itinerary", "ports", "this voyage", "this itinerary", "tell me more"]
        )
        asks_different = any(
            kw in lowered
            for kw in [
                "something different",
                "different region",
                "different from my previous",
                "new region",
                "unlike my last",
            ]
        )
        asks_region_catalog = bool(detected_regions) and any(
            kw in lowered for kw in ["price", "cost", "how much", "available", "which ", "voyages", "mediterranean", "alaska", "caribbean", "asia", "antarctica", "northern europe"]
        )
        asks_suite_catalog = (
            bool(re.search(r"\b(suite|suites|penthouse|terrace suite|owner's suite|grand suite|view suite|signature suite)\b", lowered))
            and explicit_voyage is None
            and not detected_regions
            and not last_voyages_objs
        )
        asks_collection_overview = any(
            kw in lowered for kw in ["voyage collection", "browse catalog", "all voyages", "full collection"]
        ) and not detected_regions and not detected_focuses

        intent = "general"
        recommendations: list[VoyageRecommendation] = []
        referenced_voyages: list[Voyage] = []
        followup_context: dict[str, object] | None = None
        clarify_candidates: list[Voyage] = []

        visitor_clarified_in_history = visitor_mode and any(
            t.role == "assistant" and VISITOR_CLARIFY_MARKER in (t.content or "").lower()
            for t in effective_history
        )
        visitor_regions, visitor_seasons, visitor_focuses = (
            self._extract_visitor_preferences(request, effective_history) if visitor_mode else ([], [], [])
        )

        # 5a. Superlative comparison ("cheapest", "most affordable", "lowest price", "longest", "shortest")
        if superlative is not None and not explicit_voyage:
            metric_field, direction, label = superlative
            pool = list(all_voyages)
            scope_note = "From our Voyage Collection"
            if detected_regions or detected_yachts:
                if detected_regions:
                    r_set = {r.lower() for r in detected_regions}
                    pool = [v for v in pool if v.destination.lower() in r_set]
                if detected_yachts:
                    y_set = {y.lower() for y in detected_yachts}
                    pool = [v for v in pool if v.yacht_name.lower() in y_set]
                if not pool:
                    pool = list(all_voyages)
                else:
                    scope_note = "From the matching catalog voyages"
            elif last_voyages_objs:
                pool = list(last_voyages_objs)
                scope_note = "Of the voyages shown"

            values = [getattr(v, metric_field) for v in pool]
            target_val = min(values) if direction == "min" else max(values)
            winners = [v for v in pool if getattr(v, metric_field) == target_val]
            intent = "superlative_compare"
            referenced_voyages = winners
            followup_context = {"metric": metric_field, "direction": direction, "label": label, "scope_note": scope_note}

        # 5b. Similar voyages ("similar voyages", "anything like this")
        elif asks_similar:
            if (
                explicit_voyage is None
                and ordinal_idx is None
                and not detected_regions
                and has_singular_anaphor
                and not has_plural_anaphor
                and re.search(r"\b(that voyage|this voyage|this one|that one|it)\b", lowered)
                and len(last_voyages_objs) > 1
            ):
                intent = "clarify_voyage"
                clarify_candidates = list(last_voyages_objs)
                followup_context = {"candidates": clarify_candidates}
            else:
                base_voyages: list[Voyage] = []
                if explicit_voyage is not None:
                    base_voyages = [explicit_voyage]
                elif ordinal_idx is not None and last_voyages_objs:
                    idx = ordinal_idx if ordinal_idx >= 0 else len(last_voyages_objs) - 1
                    if 0 <= idx < len(last_voyages_objs):
                        base_voyages = [last_voyages_objs[idx]]
                elif last_voyages_objs and not detected_regions and not detected_yachts:
                    base_voyages = list(last_voyages_objs)
                elif detected_regions or detected_yachts:
                    base_voyages = [
                        v
                        for v in all_voyages
                        if (not detected_regions or v.destination.lower() in {r.lower() for r in detected_regions})
                        and (not detected_yachts or v.yacht_name.lower() in {y.lower() for y in detected_yachts})
                    ]

                if base_voyages:
                    intent = "similar_voyages"
                    referenced_voyages = self._find_similar_voyages(base_voyages, all_voyages, limit=3)
                    followup_context = {"discussed_names": [v.voyage_name for v in base_voyages]}
                elif last_voyages_objs:
                    intent = "clarify_voyage"
                    clarify_candidates = list(last_voyages_objs)
                    followup_context = {"candidates": clarify_candidates}
                else:
                    intent = "general"

        # 5c. Ordinal selection ("the first", "the second", "the third", "the last one")
        elif ordinal_idx is not None and explicit_voyage is None:
            if not last_voyages_objs:
                intent = "general"
            else:
                resolved_idx = ordinal_idx if ordinal_idx >= 0 else len(last_voyages_objs) - 1
                if 0 <= resolved_idx < len(last_voyages_objs):
                    chosen = last_voyages_objs[resolved_idx]
                    referenced_voyages = [chosen]
                    if catalog_attrs and not asks_highlights:
                        intent = "catalog_attribute"
                        followup_context = {"attrs": catalog_attrs}
                    elif catalog_attrs and any(a != "destinations" for a in catalog_attrs):
                        intent = "catalog_attribute"
                        followup_context = {"attrs": catalog_attrs}
                    else:
                        intent = "voyage_detail"
                else:
                    intent = "clarify_voyage"
                    clarify_candidates = list(last_voyages_objs)
                    followup_context = {"candidates": clarify_candidates}

        # 5d. Explicit voyage detail or specific attribute question
        elif explicit_voyage is not None:
            referenced_voyages = [explicit_voyage]
            if catalog_attrs and (
                not asks_highlights
                or "embarkation" in catalog_attrs
                or any(a in {"duration", "price", "ship", "season", "suites"} for a in catalog_attrs)
            ):
                intent = "catalog_attribute"
                followup_context = {"attrs": catalog_attrs}
            else:
                intent = "voyage_detail"

        # 5e. Context anaphor / attribute follow-up referring to previous MARIS reply
        elif (
            last_voyages_objs
            and not detected_regions
            and not detected_yachts
            and not asks_best_voyage
            and not asks_different
            and not asks_collection_overview
            and (has_singular_anaphor or has_plural_anaphor or catalog_attrs or asks_highlights)
        ):
            if len(last_voyages_objs) > 1 and not has_plural_anaphor:
                intent = "clarify_voyage"
                clarify_candidates = list(last_voyages_objs)
                followup_context = {"candidates": clarify_candidates}
            elif catalog_attrs:
                intent = "catalog_attribute"
                referenced_voyages = list(last_voyages_objs)
                followup_context = {"attrs": catalog_attrs}
            else:
                intent = "voyage_detail"
                referenced_voyages = [last_voyages_objs[0]]

        # 5f. Region + explicit catalog attribute question (when not asking for region overview/recommendations)
        elif (
            detected_regions
            and catalog_attrs
            and not asks_best_voyage
            and not asks_recommend
            and not asks_different
            and any(a in {"duration", "embarkation", "season", "ship", "destinations"} for a in catalog_attrs)
        ):
            region_set = {r.lower() for r in detected_regions}
            matched = [v for v in all_voyages if v.destination.lower() in region_set]
            if matched:
                intent = "catalog_attribute"
                referenced_voyages = matched
                followup_context = {"attrs": catalog_attrs}

        elif visitor_mode and (asks_best_voyage or (visitor_clarified_in_history and not asks_suite_catalog and not asks_collection_overview)):
            if not visitor_regions and not visitor_seasons and not visitor_focuses and not visitor_clarified_in_history:
                intent = "visitor_clarify"
            else:
                intent = "recommendation"
                recommendations = self._recommend_for_visitor(
                    voyages=all_voyages,
                    regions=visitor_regions,
                    seasons=visitor_seasons,
                    focuses=visitor_focuses,
                    top_k=3,
                )
        elif asks_collection_overview:
            intent = "catalog_overview"
            seen_dest: set[str] = set()
            for v in all_voyages:
                if v.destination not in seen_dest:
                    seen_dest.add(v.destination)
                    referenced_voyages.append(v)
                if len(referenced_voyages) >= 3:
                    break
        elif asks_suite_catalog:
            intent = "suite_catalog"
            referenced_voyages = all_voyages[:3]
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

        llm_referenced_voyages = referenced_voyages
        is_ununderstood_fallback = False
        if intent == "general" and self._mentions_catalog_entity(request.message, all_voyages):
            llm_referenced_voyages = all_voyages
            if detected_regions:
                region_set = {r.lower() for r in detected_regions}
                referenced_voyages = [v for v in all_voyages if v.destination.lower() in region_set]
            else:
                partial_matches = [
                    v
                    for v in all_voyages
                    if any(
                        len(seg.strip()) >= 6 and seg.strip() in lowered
                        for seg in re.split(r"\s*[&·,/]\s*", v.voyage_name.lower())
                    )
                ]
                if partial_matches:
                    referenced_voyages = partial_matches[:3]
        elif intent == "general" and not recommendations and not referenced_voyages and request.attachment is None:
            is_ununderstood_fallback = True
            llm_referenced_voyages = all_voyages

        recent_messages_payload = (
            [{"role": t.role, "content": t.content} for t in effective_history[-8:]]
            if is_ununderstood_fallback
            else None
        )

        reply, provider_used, fallback = self.llm_engine.generate_reply(
            profile=profile,
            bookings=bookings if consent_applied else [],
            intent=intent,
            consent_applied=consent_applied,
            recommendations=recommendations,
            referenced_voyages=llm_referenced_voyages,
            escalation=EscalationInfo(escalated=False),
            user_message=request.message,
            used_profile_fields=used_fields,
            visitor_mode=visitor_mode,
            attachment=request.attachment,
            followup_context=followup_context,
            previous_assistant_text=previous_assistant_text,
            recent_messages=recent_messages_payload,
            is_fallback=is_ununderstood_fallback,
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

        sugs = _build_suggested_replies(
            intent,
            recommendations,
            referenced_voyages,
            EscalationInfo(escalated=False),
            request.message,
            visitor_mode=visitor_mode,
            detected_yachts=detected_yachts,
            catalog_yachts=catalog_yachts,
            clarify_candidates=clarify_candidates,
        )
        if intent == "clarify_voyage" and clarify_candidates:
            context_voyage_ids = [v.voyage_id for v in clarify_candidates]
        else:
            context_voyage_ids = [r.voyage.voyage_id for r in recommendations] + [
                v.voyage_id for v in referenced_voyages
            ]

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
            context_voyage_ids=list(dict.fromkeys(context_voyage_ids)),
        )
