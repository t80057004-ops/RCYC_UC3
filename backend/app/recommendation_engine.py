"""Explainable Voyage Recommendation Engine with strict consent enforcement."""

from __future__ import annotations

from backend.app.models import GuestProfile, Voyage, VoyageRecommendation


EXPERIENCE_KEYWORDS: dict[str, list[str]] = {
    "culinary": ["culinary", "dining", "food", "chef", "wine", "sommelier", "gastronomy", "tasting", "michelin", "kaiseki"],
    "wellness": ["wellness", "spa", "massage", "yoga", "sauna", "thermal", "relax", "meditation", "mindfulness", "holistic"],
    "adventure": ["adventure", "shore excursion", "excursions", "hiking", "kayak", "kayaking", "expedition", "zodiac", "snorkel", "helicopter", "active", "trek"],
    "cultural": ["cultural", "culture", "museum", "history", "art", "heritage", "temple", "palace", "gallery", "architecture"],
}

# Explicit, transparent scoring weights (max = 100)
WEIGHT_PREFERRED_REGION = 30
WEIGHT_INTEREST_FOCUS = 25
WEIGHT_SUITE_AVAILABILITY = 20
WEIGHT_NEW_REGION = 25


def detect_query_focus(query: str) -> list[str]:
    lowered = query.lower()
    return [focus for focus, kws in EXPERIENCE_KEYWORDS.items() if any(kw in lowered for kw in kws)]


def recommend_voyages(
    profile: GuestProfile,
    voyages: list[Voyage],
    query: str = "",
    destination_filter: list[str] | None = None,
    focus_filter: list[str] | None = None,
    different_from_previous: bool = False,
    top_k: int = 3,
) -> tuple[list[VoyageRecommendation], list[str], bool]:
    """
    Filter and score voyages strictly from catalog and profile attributes.

    Returns:
        (top_recommendations, used_profile_fields, consent_applied)
    """
    query_focuses = focus_filter or detect_query_focus(query)
    dest_filter_lower = {d.lower() for d in (destination_filter or [])}

    is_recognized = profile.guest_status in {"returning", "new"}
    consent_applied = bool(is_recognized and profile.personalization_consent)

    # Strict consent gating: when consent is off, ZERO profile fields are used
    used_fields: list[str] = []
    if consent_applied:
        if profile.preferred_destinations:
            used_fields.append("preferred_destinations")
        if profile.interest_focus:
            used_fields.append("interest_focus")
        if profile.preferred_suite and profile.preferred_suite.strip().lower() not in {"not specified", "none"}:
            used_fields.append("preferred_suite")
        if profile.sailed_regions or (profile.previous_voyage_region not in {"", "None"}):
            used_fields.append("sailed_regions")

    # 1. Catalog filtering by region and/or focus
    candidates = list(voyages)
    if dest_filter_lower:
        regional = [v for v in candidates if v.destination.lower() in dest_filter_lower]
        if regional:
            candidates = regional

    if query_focuses:
        focused = [v for v in candidates if any(f in v.primary_focus for f in query_focuses)]
        if focused:
            candidates = focused

    # Exclude all sailed regions when "Something different" is requested with consent
    sailed_lower = {r.lower() for r in profile.sailed_regions}
    if profile.previous_voyage_region and profile.previous_voyage_region != "None":
        sailed_lower.add(profile.previous_voyage_region.lower())

    if different_from_previous and consent_applied and sailed_lower:
        unexplored = [v for v in candidates if v.destination.lower() not in sailed_lower]
        if unexplored:
            candidates = unexplored

    # 2. Explainable scoring
    scored: list[VoyageRecommendation] = []
    for voyage in candidates:
        breakdown: dict[str, int] = {
            "preferred_region": 0,
            "interest_focus": 0,
            "preferred_suite_availability": 0,
            "new_region_vs_last_voyage": 0,
        }
        reasons: list[str] = []

        if consent_applied:
            pref_dest_lower = {d.lower() for d in profile.preferred_destinations}
            region_targets = pref_dest_lower if pref_dest_lower else sailed_lower
            if voyage.destination.lower() in region_targets and not different_from_previous:
                breakdown["preferred_region"] = WEIGHT_PREFERRED_REGION
                if pref_dest_lower:
                    reasons.append(f"Matches your preferred region ({voyage.destination}).")
                else:
                    reasons.append(f"Matches your previously sailed region ({voyage.destination}).")

            effective_focus = set(query_focuses) if query_focuses else set(profile.interest_focus)
            focus_hits = [f for f in effective_focus if f in voyage.primary_focus]
            if focus_hits:
                breakdown["interest_focus"] = WEIGHT_INTEREST_FOCUS
                reasons.append(f"Aligned with {', '.join(focus_hits)} experiences aboard {voyage.yacht_name}.")

            if profile.preferred_suite and profile.preferred_suite.lower() in voyage.suite_availability.lower():
                breakdown["preferred_suite_availability"] = WEIGHT_SUITE_AVAILABILITY
                reasons.append(f"{profile.preferred_suite} is available.")

            if sailed_lower:
                if voyage.destination.lower() not in sailed_lower:
                    breakdown["new_region_vs_last_voyage"] = WEIGHT_NEW_REGION
                    reasons.append(f"Explores a new region ({voyage.destination}) beyond your past sailings.")
            else:
                # New guest (0 voyages): every region is a fresh discovery
                breakdown["new_region_vs_last_voyage"] = WEIGHT_NEW_REGION
                reasons.append(f"Curated inaugural discovery in {voyage.destination}.")
        else:
            # Generic catalog scoring (zero profile data used)
            if query_focuses:
                focus_hits = [f for f in query_focuses if f in voyage.primary_focus]
                if focus_hits:
                    breakdown["interest_focus"] = WEIGHT_INTEREST_FOCUS
                    reasons.append(f"Featured for {', '.join(focus_hits)} experiences.")
            if dest_filter_lower and voyage.destination.lower() in dest_filter_lower:
                breakdown["preferred_region"] = WEIGHT_PREFERRED_REGION
                reasons.append(f"Curated {voyage.destination} sailing aboard {voyage.yacht_name}.")
            if not reasons:
                reasons.append(f"{voyage.duration} nights aboard {voyage.yacht_name} ({voyage.season}).")

        total_score = sum(breakdown.values())
        scored.append(
            VoyageRecommendation(
                voyage=voyage,
                score=total_score,
                match_reasons=list(dict.fromkeys(reasons)),
                score_breakdown=breakdown,
            )
        )

    scored.sort(key=lambda r: (-r.score, r.voyage.price))
    return scored[:top_k], list(dict.fromkeys(used_fields)), consent_applied
