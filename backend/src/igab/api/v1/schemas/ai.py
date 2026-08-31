from igab.api.v1.schemas.base import ApiModel


class SuggestCategoryRequest(ApiModel):
    payee_name: str
    amount: float
    memo: str | None = None


class SuggestCategoryResponse(ApiModel):
    category_id: str | None
    category_name: str | None
    confidence: float


class SuggestRegexRequest(ApiModel):
    names: list[str]


class SuggestRegexResponse(ApiModel):
    #: Most specific first; empty when the model produced nothing usable.
    patterns: list[str]


class InsightsResponse(ApiModel):
    insights: str


class AIStatusResponse(ApiModel):
    enabled: bool
    available: bool
    host: str | None
    model: str | None
    #: Raw ollama_vision_model setting (None when no override is set).
    vision_model: str | None
    #: The model receipt scans will actually use — the vision override when
    #: set, otherwise the main model. Resolved server-side so the UI never
    #: re-implements the fallback chain.
    receipt_model: str
    #: Whether that model supports vision, from the same /api/show probe the
    #: worker gates receipt scans on. None = unknown (Ollama unreachable, or
    #: too old to report capabilities) — never render that as "unsupported".
    receipt_model_vision: bool | None = None


class OllamaModelInfo(ApiModel):
    name: str
    size: int
    capabilities: list[str]


class OllamaModelsResponse(ApiModel):
    models: list[OllamaModelInfo]
