from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- Iteration 1: nationwide catalog, saved profiles, recommendations ---------

# Cap on the serialized size of a profile payload. The per-field max_lengths
# already bound every field; this additional, simpler rule bounds the whole
# payload (e.g. many goals / long free text) without storing or logging it.
MAX_PROFILE_PAYLOAD_CHARS = 12_000


class ProfileData(BaseModel):
    """Optional citizen-provided profile signals for matching schemes.

    No field is required and nothing sensitive is collected. Fields are range-
    and length-validated (free text is stripped and must be non-empty when
    provided); the language field reserves a seam for the later Hindi UI (only
    ``en``/``hi`` are accepted). The whole serialized payload is capped so a
    single profile can never carry an unbounded amount of input.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=80)
    age: int | None = Field(default=None, ge=1, le=120)
    annual_income: float | None = Field(default=None, ge=0, le=1_000_000_000)
    occupation: str | None = Field(default=None, min_length=1, max_length=100)
    social_category: str | None = Field(default=None, min_length=1, max_length=50)
    gender: str | None = Field(default=None, min_length=1, max_length=50)
    rural: bool | None = None
    disability: bool | None = None
    family_size: int | None = Field(default=None, ge=1, le=100)
    goals: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=20
    )
    language: Literal["en", "hi"] | None = Field(
        default=None, description="Preferred language; 'en' or 'hi'."
    )

    @model_validator(mode="after")
    def _bound_serialized_payload(self) -> "ProfileData":
        # Simple whole-payload bound: reject oversized profiles with a normal
        # 422 validation error. The payload itself is never logged.
        if len(self.model_dump_json(exclude_none=True)) > MAX_PROFILE_PAYLOAD_CHARS:
            raise ValueError(
                "profile payload too large; shorten free-text fields or goals"
            )
        return self


class QueryRequest(BaseModel):
    # Iteration 4: minimum nontrivial length (whitespace-only input is stripped
    # and rejected) and a hard 2,000-character cap. Returned as a normal 422
    # validation error; the question text is never stored in logs.
    question: str = Field(min_length=2, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)

    # Iteration 2: optional language ("en" or "hi") and an optional saved
    # profile. Both are optional, so the original `{"question": "..."}` body
    # still validates unchanged.
    language: Literal["en", "hi"] = "en"
    profile: ProfileData | None = None


class Source(BaseModel):
    source: str
    content: str
    # Iteration 2: provenance metadata so clients can distinguish verified
    # sample records from directory seeds. All fields are optional with safe
    # defaults, so existing clients that read only `source`/`content` remain
    # valid and old vectors that lack these keys still serialize.
    jurisdiction: str | None = None
    state: str | None = None
    data_status: str | None = None
    last_verified: str | None = None
    source_url: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    # Backwards-compatible additions for the pre-made demo fallback. Clients
    # that only read `answer` and `sources` are unaffected; `mode` defaults to
    # "live" so existing callers keep working unchanged.
    mode: str = "live"
    notice: str | None = None
    # Iteration 2: echoes the (normalized) answer language. Optional with an
    # "en" default, so existing clients are unaffected.
    language: Literal["en", "hi"] = "en"


class ProfileCreateResponse(BaseModel):
    profile_id: str
    access_token: str  # shown only on creation; never stored or logged
    profile: ProfileData
    created_at: str
    updated_at: str


class ProfileResponse(BaseModel):
    profile_id: str
    profile: ProfileData
    created_at: str
    updated_at: str


class RecommendationRequest(BaseModel):
    profile: ProfileData
    question: str | None = Field(default=None, max_length=1000)
    # Iteration 2: optional answer language; defaults to English so existing
    # clients keep working unchanged.
    language: Literal["en", "hi"] = "en"


class RecommendationItem(BaseModel):
    id: str
    name: str
    jurisdiction: str
    # ``reason`` and ``benefits_or_scope`` are localized: they contain Hindi
    # text when ``RecommendationRequest.language`` is ``"hi"`` and English
    # otherwise. Current fields are preserved unchanged.
    reason: str
    benefits_or_scope: str
    source: str
    data_status: str
    last_verified: str | None = None
    # Iteration 3: optional verified per-scheme source URL when the catalog
    # record carries one (e.g. state/UT directory seeds). The UI keeps its
    # MyScheme portal fallback for records without one. Defaults to None, so
    # existing responses remain valid.
    source_url: str | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]
    disclaimer: str
    profile_state: str | None = None
