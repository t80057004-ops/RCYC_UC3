"""Experience Ambassador (EA) escalation rules and simulated handoff context builder."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.ea_intent import has_keyword, wants_human
from backend.app.models import (
    ChatTurn,
    EscalationContextPacket,
    EscalationInfo,
    GuestProfile,
)


COMPLAINT_KEYWORDS = [
    "refund",
    "complaint",
    "complain",
    "problem",
    "issue",
    "dissatisfied",
    "unhappy",
    "disappointed",
    "compensation",
    "reimburse",
    "dispute",
    "terrible",
    "awful",
    "unacceptable",
    "ruined",
    "billing error",
    "overcharged",
    "cancel my booking",
]

EXPLICIT_EA_KEYWORDS = [
    "experience ambassador",
    "speak to an ambassador",
    "speak with an ambassador",
    "talk to an ambassador",
    "human agent",
    "speak to a human",
    "talk to a human",
    "real person",
    "speak to a person",
    "speak to someone",
    "talk to someone",
    "live agent",
    "representative",
    "concierge manager",
    "supervisor",
    "escalate",
]

VIP_COMPLEX_KEYWORDS = [
    "private charter",
    "charter the yacht",
    "bespoke",
    "custom arrangement",
    "customized arrangement",
    "customize",
    "custom itinerary",
    "helicopter",
    "private jet",
    "buyout",
    "multi-suite",
    "multiple suites",
    "private chef",
    "private celebration",
    "private event",
    "private yacht",
    "exclusive access",
    "tailored arrangement",
]

MEDICAL_ACCESSIBILITY_KEYWORDS = [
    "medical emergency",
    "emergency",
    "doctor",
    "hospital",
    "oxygen",
    "dialysis",
    "severe allergy",
    "allergy",
    "allergies",
    "allergic",
    "anaphylaxis",
    "epipen",
    "wheelchair",
    "accessibility",
    "accessible suite",
    "mobility",
    "hearing loop",
    "disability",
    "medical equipment",
]


def evaluate_escalation(
    profile: GuestProfile,
    message: str,
    history: list[ChatTurn],
) -> EscalationInfo:
    """Evaluate all 5 RCYC Experience Ambassador escalation rules."""
    triggered_rules: list[str] = []
    reasons: list[str] = []

    # Rule 1: Unresolved open complaint on Guest 360 profile (generic reason only)
    if profile.open_complaint_status:
        triggered_rules.append("UNRESOLVED_OPEN_COMPLAINT")
        reasons.append("Guest has an open service inquiry on file requiring Experience Ambassador follow-up.")

    # Rule 2: Refunds, complaints, problems, or dissatisfaction in message
    if has_keyword(message, COMPLAINT_KEYWORDS):
        triggered_rules.append("COMPLAINT_OR_REFUND_INQUIRY")
        reasons.append("Guest raised a refund, service concern, or dissatisfaction inquiry.")

    # Rule 3: VIP guest requesting a complex or customized arrangement (generic reason only)
    if profile.vip_status and has_keyword(message, VIP_COMPLEX_KEYWORDS):
        triggered_rules.append("VIP_CUSTOM_ARRANGEMENT")
        reasons.append("Guest requested a bespoke or multi-party private arrangement.")

    # Rule 4: Medical emergencies, serious allergies, or accessibility arrangements requiring human coordination
    if has_keyword(message, MEDICAL_ACCESSIBILITY_KEYWORDS):
        triggered_rules.append("MEDICAL_ALLERGY_OR_ACCESSIBILITY")
        reasons.append(
            "Inquiry involves medical, severe allergy, or specialized accessibility coordination."
        )

    # Rule 5: Explicit request for an Experience Ambassador (checks last guest message only)
    if wants_human(message):
        triggered_rules.append("EXPLICIT_EA_REQUEST")
        reasons.append("Guest explicitly requested to speak with an Experience Ambassador.")

    if not triggered_rules:
        return EscalationInfo(escalated=False)

    context_turns = [{"role": t.role, "content": t.content} for t in history[-6:]]
    context_turns.append({"role": "user", "content": message})

    packet = EscalationContextPacket(
        rcyc_id=profile.rcyc_id,
        guest_name=profile.full_name,
        loyalty_tier=profile.loyalty_tier,
        guest_status=profile.guest_status,
        user_message=message,
        conversation_context=context_turns,
        open_complaint_status=profile.open_complaint_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return EscalationInfo(
        escalated=True,
        trigger_rules=triggered_rules,
        reason=" ".join(reasons),
        handoff_note=(
            "I've noted this for an Experience Ambassador; in this prototype no notification is sent yet."
        ),
        context_packet=packet,
    )
