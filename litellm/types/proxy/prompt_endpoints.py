from typing import Literal

from pydantic import BaseModel, ConfigDict


class TestPromptRequest(BaseModel):
    dotprompt_content: str
    prompt_variables: dict[str, object] | None = None
    conversation_history: list[dict[str, str]] | None = None


class PromptRecommendationsRequest(BaseModel):
    dotprompt_content: str
    prompt_variables: dict[str, object] | None = None
    reviewer_model: str | None = None


class Recommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Literal[
        "clarity", "specificity", "structure", "examples", "output_format", "variables", "token_efficiency"
    ]
    severity: Literal["high", "medium", "low"]
    excerpt: str
    issue: str
    suggestion: str


class PromptRecommendations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendations: tuple[Recommendation, ...]
    improved_prompt: str


class PromptRecommendationsResponse(PromptRecommendations):
    original_tokens: int
    improved_tokens: int
