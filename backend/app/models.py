"""Pydantic data models for MARIS RCYC Guest Concierge."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB

ATTACHMENT_EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

AllowedAttachmentMime = Literal[
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
]


GuestRecognitionStatus = Literal["returning", "new", "anonymous", "unknown"]


class Booking(BaseModel):
    """Reservation record linked to a guest profile."""

    booking_id: str
    rcyc_id: str
    voyage_id: str
    voyage_name: str
    destination: str
    ship: str
    suite_category: str
    booked_on: str
    sailing_dates: str | None = None
    status_code: str = "C"
    status_label: str = ""


class GuestProfile(BaseModel):
    """Unified guest profile returned by GuestDataProvider.getProfile()."""

    rcyc_id: str
    first_name: str
    last_name: str
    loyalty_tier: str
    past_voyages: int = 0
    previous_voyage_region: str = "None"
    sailed_regions: list[str] = Field(default_factory=list)
    preferred_suite: str = "Terrace Suite"
    interest_focus: list[str] = Field(default_factory=list)
    ancillary_purchase_preferences: list[str] = Field(default_factory=list)
    preferred_destinations: list[str] = Field(default_factory=list)
    dietary_requirements: str = "None"
    accessibility_requirements: str = "None"
    vip_status: bool = False
    open_complaint_status: bool = False
    complaint_summary: str = ""
    personalization_consent: bool = True
    consent_assumed: bool = False
    profile_label: str = ""
    guest_status: GuestRecognitionStatus = "returning"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class PublicGuestProfile(BaseModel):
    """Minimized guest profile safe for browser responses (sensitive fields omitted)."""

    rcyc_id: str
    first_name: str
    last_name: str
    loyalty_tier: str
    past_voyages: int = 0
    previous_voyage_region: str = "None"
    sailed_regions: list[str] = Field(default_factory=list)
    preferred_suite: str = "Terrace Suite"
    interest_focus: list[str] = Field(default_factory=list)
    ancillary_purchase_preferences: list[str] = Field(default_factory=list)
    preferred_destinations: list[str] = Field(default_factory=list)
    open_complaint_status: bool = False
    personalization_consent: bool = True
    consent_assumed: bool = False
    profile_label: str = ""
    guest_status: GuestRecognitionStatus = "returning"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def to_public_profile(profile: GuestProfile) -> PublicGuestProfile:
    """Strip server-only fields before returning guest profile to the browser."""
    return PublicGuestProfile(
        rcyc_id=profile.rcyc_id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        loyalty_tier=profile.loyalty_tier,
        past_voyages=profile.past_voyages,
        previous_voyage_region=profile.previous_voyage_region,
        sailed_regions=list(profile.sailed_regions),
        preferred_suite=profile.preferred_suite,
        interest_focus=list(profile.interest_focus),
        ancillary_purchase_preferences=list(profile.ancillary_purchase_preferences),
        preferred_destinations=list(profile.preferred_destinations),
        open_complaint_status=profile.open_complaint_status,
        personalization_consent=profile.personalization_consent,
        consent_assumed=profile.consent_assumed,
        profile_label=profile.profile_label,
        guest_status=profile.guest_status,
    )


class GuestSummary(BaseModel):
    """Sample guest option for the demo picker."""

    rcyc_id: str
    full_name: str
    loyalty_tier: str
    past_voyages: int
    open_complaint_status: bool
    personalization_consent: bool
    profile_label: str
    guest_status: GuestRecognitionStatus


class Voyage(BaseModel):
    """RCYC Voyage catalog entry returned by GuestDataProvider.listVoyages()."""

    voyage_id: str
    voyage_name: str
    destination: str
    yacht_name: str
    itinerary_ports: str
    duration: int
    price: int
    season: str
    highlights: str
    culinary_experiences: str
    wellness_experiences: str
    adventure_experiences: str
    cultural_experiences: str
    suite_availability: str
    primary_focus: list[str] = Field(default_factory=list)


class VoyageRecommendation(BaseModel):
    """Scored voyage recommendation with transparent weight breakdown (for Demo insights)."""

    voyage: Voyage
    score: int
    match_reasons: list[str]
    score_breakdown: dict[str, int] = Field(default_factory=dict)


class EscalationContextPacket(BaseModel):
    """Context passed to an Experience Ambassador during simulated handoff (sensitive notes kept server-side)."""

    rcyc_id: str
    guest_name: str
    loyalty_tier: str
    guest_status: str
    user_message: str
    conversation_context: list[dict[str, str]]
    open_complaint_status: bool
    timestamp: str


class EscalationInfo(BaseModel):
    """Structured escalation state returned with chat responses."""

    escalated: bool = False
    trigger_rules: list[str] = Field(default_factory=list)
    reason: str = ""
    handoff_note: str = ""
    context_packet: EscalationContextPacket | None = Field(default=None, exclude=True)


class ChatTurn(BaseModel):
    """A single turn in conversation history."""

    role: Literal["user", "assistant"]
    content: str
    voyage_ids: list[str] = Field(default_factory=list)


ChatFocus = Literal["voyages", "culinary", "wellness", "adventure_cultural"]


class ChatAttachment(BaseModel):
    """In-memory single file attachment sent to Gemini as inlineData (never persisted)."""

    name: str = Field(..., min_length=1, max_length=255)
    mime_type: AllowedAttachmentMime
    data_base64: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = Path(str(v or "").strip()).name
        ext = Path(clean).suffix.lower()
        if ext not in ATTACHMENT_EXTENSION_TO_MIME:
            raise ValueError("Unsupported file type. Allowed: .pdf, .txt, .png, .jpg, .jpeg, .webp.")
        return clean

    @field_validator("data_base64")
    @classmethod
    def validate_data_base64(cls, v: str) -> str:
        compact = "".join(str(v or "").split())
        if not compact:
            raise ValueError("Attached file is empty.")
        if len(compact) > 14_500_000:
            raise ValueError("Attached file exceeds the 10 MB limit.")
        try:
            decoded = base64.b64decode(compact, validate=True)
        except Exception as exc:
            raise ValueError("Invalid base64 file content.") from exc
        if not decoded:
            raise ValueError("Attached file is empty.")
        if len(decoded) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Attached file exceeds the 10 MB limit.")
        return compact

    @model_validator(mode="after")
    def validate_extension_mime_match(self) -> "ChatAttachment":
        ext = Path(self.name).suffix.lower()
        expected_mime = ATTACHMENT_EXTENSION_TO_MIME.get(ext)
        if expected_mime != self.mime_type:
            raise ValueError("File extension does not match the attached MIME type.")
        return self


class ChatRequest(BaseModel):
    """Incoming chat message payload."""

    rcyc_id: str | None = Field(
        default=None,
        description="Sample RCYC_ID or 'ANONYMOUS' / empty for visitor.",
    )
    conversation_id: str | None = Field(default=None, max_length=128)
    message: str = Field(default="", max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)
    focus: ChatFocus | None = Field(
        default=None,
        description="Optional card focus filter: 'voyages', 'culinary', 'wellness', or 'adventure_cultural'.",
    )
    attachment: ChatAttachment | None = None

    @model_validator(mode="after")
    def validate_message_or_attachment(self) -> "ChatRequest":
        if self.attachment is None and len(self.message) < 1:
            raise ValueError("String should have at least 1 character")
        if self.attachment is not None and not self.message.strip():
            self.message = "Please review the attached file."
        return self


class GuestContextResponse(BaseModel):
    """Profile + bookings bundle returned when selecting a sample guest."""

    status: Literal["found", "not_found", "anonymous"]
    profile: PublicGuestProfile | None = None
    bookings: list[Booking] = Field(default_factory=list)
    escalation: bool = False


class ChatResponse(BaseModel):
    """Structured response from MARIS Concierge."""

    reply: str
    guest_profile: PublicGuestProfile
    bookings: list[Booking] = Field(default_factory=list)
    guest_recognized: bool
    guest_status: GuestRecognitionStatus
    consent_applied: bool
    used_profile_fields: list[str] = Field(default_factory=list)
    recommendations: list[VoyageRecommendation] = Field(default_factory=list)
    referenced_voyages: list[Voyage] = Field(default_factory=list)
    suggested_replies: list[str] = Field(default_factory=list)
    escalation: EscalationInfo = Field(default_factory=EscalationInfo)
    llm_provider_used: str = "rule_based"
    llm_fallback_triggered: bool = False
    conversation_id: str | None = None
    conversation_title: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    user_created_at: str | None = None
    assistant_created_at: str | None = None
    context_voyage_ids: list[str] = Field(default_factory=list, exclude=True)


class ConversationTitleRequest(BaseModel):
    """Request payload containing only the first guest message for title generation."""

    message: str = Field(..., min_length=1, max_length=2000)


class ConversationTitleResponse(BaseModel):
    """Short 2-5 word conversation title."""

    title: str


class ConversationSummary(BaseModel):
    """Saved conversation metadata item (never includes raw Informatica data or email/phone)."""

    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    """List of conversations owned by the signed-in guest."""

    conversations: list[ConversationSummary] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    """Persisted chat message with optional guest feedback vote."""

    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: str
    vote: Literal["up", "down"] | None = None


class ConversationDetailResponse(BaseModel):
    """Full conversation messages for the signed-in guest."""

    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ConversationMessage] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    """Optional title when explicitly creating a conversation."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None

    @field_validator("title")
    @classmethod
    def validate_optional_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = str(v).strip()
        if not trimmed or len(trimmed) > 80:
            raise ValueError("Conversation title must be between 1 and 80 characters.")
        return trimmed


class RenameConversationRequest(BaseModel):
    """Rename conversation request (1-80 characters after trimming)."""

    model_config = ConfigDict(extra="ignore")

    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        trimmed = str(v or "").strip()
        if not trimmed or len(trimmed) > 80:
            raise ValueError("Conversation title must be between 1 and 80 characters.")
        return trimmed


class FeedbackRequest(BaseModel):
    """Helpful / Not helpful vote payload for an assistant reply."""

    model_config = ConfigDict(extra="ignore")

    conversation_id: str = Field(..., min_length=1, max_length=128)
    message_id: str = Field(..., min_length=1, max_length=128)
    vote: Literal["up", "down"]

    @field_validator("conversation_id", "message_id")
    @classmethod
    def validate_non_empty_id(cls, v: str) -> str:
        trimmed = str(v or "").strip()
        if not trimmed:
            raise ValueError("Identifier must not be empty.")
        return trimmed


class FeedbackResponse(BaseModel):
    """Confirmed persisted feedback state."""

    conversation_id: str
    message_id: str
    vote: Literal["up", "down"]


