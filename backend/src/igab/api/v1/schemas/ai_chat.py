"""Wire shapes for the chat panel.

The page context is a discriminated union rather than a pre-rendered sentence.
The client knows which page it is on and the server decides what that means, so
an unknown `kind` is a 422 here rather than a blob nobody notices being ignored.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel


class BudgetPageContext(ApiModel):
    kind: Literal["budget"]
    month: str
    selected_category_names: list[str] = Field(default_factory=list, max_length=20)


class AccountPageContext(ApiModel):
    kind: Literal["account"]
    account_name: str | None = None


class ReportsPageContext(ApiModel):
    kind: Literal["reports"]
    tab: str


class SimplePageContext(ApiModel):
    """Pages whose identity is the whole context."""

    kind: Literal[
        "accounts",
        "transactions",
        "liabilities",
        "liability",
        "assets",
        "asset",
        "guide",
        "wishlist",
        "scheduled",
        "payees",
        "settings",
        "ai-activity",
        "activity",
        "import",
    ]


PageContext = Annotated[
    BudgetPageContext | AccountPageContext | ReportsPageContext | SimplePageContext,
    Field(discriminator="kind"),
]


class ChatRequest(ApiModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    page_context: PageContext | None = None
    #: The browser's date. Report methods use the server clock internally, but
    #: anything the tool layer resolves itself must use the user's — near
    #: midnight the two disagree about what "this month" is.
    client_today: str | None = None


class ChatMessageResponse(ApiModel):
    id: uuid.UUID
    role: str
    content: str
    thinking: str | None = None
    tool_calls: list[dict] | None = None
    grounding: dict | None = None
    created_at: datetime
    ai_call_id: uuid.UUID | None = None


class ConversationResponse(ApiModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailResponse(ApiModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]


class AICallResponse(ApiModel):
    """One model round trip, as the activity log lists it."""

    id: uuid.UUID
    feature: str
    feature_label: str
    model: str
    endpoint: str
    status: str
    error: str | None
    round: int
    duration_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    tool_call_count: int
    created_at: datetime


class AICallDetailResponse(AICallResponse):
    """Everything recorded about a call, for the transparency view."""

    system: str | None = None
    messages: list[dict] = Field(default_factory=list)
    response: str | None = None
    thinking: str | None = None
    tools: list[dict] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    payload_pruned: bool = False


class AICallListResponse(ApiModel):
    calls: list[AICallResponse]
    total_count: int
