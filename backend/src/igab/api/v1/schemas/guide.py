import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ConceptInfo(BaseModel):
    """A concept the roadmap can ask about, and how it may be corrected."""

    key: str
    label: str
    kind: str
    binds_to: list[str]
    prompt: str
    caveat: str
    auto: bool
    allows_external: bool
    us_only: bool
    aliases: list[str]


class SignalResponse(BaseModel):
    key: str
    #: False when the user asked us to leave this concept alone.
    tracked: bool
    #: 'auto' | 'manual' | 'external' | 'manual+external' | 'dismissed'
    #: | 'answer' | 'off'
    source: str
    #: True/False when known, None when detection could not tell. Never guessed.
    met: bool | None = None
    #: Detected plus self-reported, in the concept's own units.
    value: Decimal | None = None
    detected_value: Decimal | None = None
    #: Self-reported and never blended into any report — Guide only.
    external_value: Decimal | None = None
    external_declared: bool = False
    external_as_of: date | None = None
    target: Decimal | None = None
    reason: str = ""
    entities: dict[str, list[str]] = Field(default_factory=dict)
    #: Things worth mentioning that did not count — a debt with no rate on
    #: record. A gap in the data is a nudge, not a silence.
    gaps: list[str] = Field(default_factory=list)
    note: str | None = None


class SignalsResponse(BaseModel):
    personalization: bool
    concepts: list[SignalResponse]


class CandidateOption(BaseModel):
    id: str
    name: str
    detail: str | None = None


class CandidatesResponse(BaseModel):
    concept_key: str
    options: dict[str, list[CandidateOption]]


class BindingUpdate(BaseModel):
    """One concept's whole answer — the endpoint replaces rather than merges."""

    #: 'auto' resets to the app's own guess and deletes every stored row.
    mode: str = Field(pattern="^(auto|manual|dismissed|answer|external)$")
    entity_ids: dict[str, list[uuid.UUID]] | None = None
    answer: bool | None = None
    #: Declare money held outside IGAB alongside anything bound above.
    external: bool = False
    #: Optional on purpose: "I have this covered" is a complete answer, and
    #: requiring a figure invites an invented one.
    external_amount: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_shape(self) -> "BindingUpdate":
        if self.mode == "answer" and self.answer is None:
            raise ValueError("answer is required when mode is 'answer'")
        if self.mode == "external" and not self.external:
            # Saying mode='external' without setting the flag would store
            # nothing and silently read as a reset.
            self.external = True
        return self


class PreferencesUpdate(BaseModel):
    personalization: bool | None = None
    checkup: bool | None = None


class PreferencesResponse(BaseModel):
    personalization: bool
    checkup: bool


class StepUpdate(BaseModel):
    #: null clears the mark and returns the step to undecided.
    state: str | None = Field(default=None, pattern="^(done|skipped)$")


class GuideOverview(BaseModel):
    """Everything the Guide needs to render, in one round trip."""

    concepts: list[ConceptInfo]
    thresholds: dict[str, int]
    preferences: PreferencesResponse
    progress: dict[str, str]
