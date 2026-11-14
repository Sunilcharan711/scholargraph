from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.chat import ChatResponse

Dimension = Literal[
    "objective",
    "methodology",
    "dataset",
    "architecture",
    "evaluation",
    "findings",
    "limitations",
    "future_work",
]

QUESTIONS: dict[str, str] = {
    "objective": "What research problem and objective does this paper address?",
    "methodology": "What methods and procedures does this paper use?",
    "dataset": "What datasets, sample sizes and data sources does this paper use?",
    "architecture": "What model or system architecture does this paper describe?",
    "evaluation": "What evaluation metrics, baselines and experiments does this paper report?",
    "findings": "What specific findings and measured results does this paper report?",
    "limitations": "What limitations and threats to validity does this paper explicitly state?",
    "future_work": "What future work does this paper explicitly propose?",
}


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_ids: list[UUID] = Field(min_length=2, max_length=4)
    # One dimension per request bounds local generation time; clients accumulate rows.
    dimension: Dimension = "methodology"
    mode: Literal["dense", "bm25", "hybrid"] = "hybrid"
    rerank: bool = False

    @field_validator("paper_ids")
    @classmethod
    def distinct_papers(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("Choose distinct papers")
        return values


class ComparisonCell(BaseModel):
    paper_id: UUID
    title: str
    answer: ChatResponse | None = None
    error: str | None = None


class CompareResponse(BaseModel):
    dimension: Dimension
    question: str
    cells: list[ComparisonCell]
    latency_ms: float
