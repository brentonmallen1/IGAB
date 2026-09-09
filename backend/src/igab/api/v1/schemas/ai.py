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
    #: Best first — most names covered, fewest other payees swallowed. Empty
    #: only for an empty request: the last candidate is derived from the names
    #: themselves and matches all of them by construction.
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
    #: The assistant's model through its own fallback chain (override → main).
    chat_model: str
    #: Whether it can call tools, from the same probe the chat route gates
    #: on. None = unknown, never "unsupported".
    chat_model_tools: bool | None = None
    #: What the model advertises it can take, and what the app will ask for.
    chat_model_context_length: int | None = None
    chat_num_ctx: int | None = None


class OllamaModelInfo(ApiModel):
    name: str
    size: int
    capabilities: list[str]
    context_length: int | None = None


class OllamaModelsResponse(ApiModel):
    models: list[OllamaModelInfo]
