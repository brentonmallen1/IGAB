from pydantic import BaseModel


class SuggestCategoryRequest(BaseModel):
    payee_name: str
    amount: float
    memo: str | None = None


class SuggestCategoryResponse(BaseModel):
    category_id: str | None
    category_name: str | None
    confidence: float


class NormalizePayeeRequest(BaseModel):
    payee_name: str


class NormalizePayeeResponse(BaseModel):
    normalized_name: str


class InsightsResponse(BaseModel):
    insights: str


class PayeeCleanupEntry(BaseModel):
    id: str
    name: str


class PayeeCleanupGroup(BaseModel):
    canonical: str
    payees: list[PayeeCleanupEntry]


class AIStatusResponse(BaseModel):
    enabled: bool
    available: bool
    host: str | None
    model: str | None
    vision_model: str | None


class OllamaModelInfo(BaseModel):
    name: str
    size: int
    capabilities: list[str]


class OllamaModelsResponse(BaseModel):
    models: list[OllamaModelInfo]
