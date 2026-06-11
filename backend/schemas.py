from typing import Literal
from pydantic import BaseModel


class ChecklistItem(BaseModel):
    section: str
    item_id: str
    question: str = ""       # item description text, used for RAG query
    response: Literal["Yes", "No", "NA"]
    remark: str


class AssessRequest(BaseModel):
    inspection_id: str
    ro_name: str
    items: list[ChecklistItem]


class AssessResponse(BaseModel):
    inspection_id: str
    ro_name: str
    overall_risk: str
    final_risk_index: float
    compliance_score: float
    numerical_risk_score: float
    semantic_risk_score: float
    hidden_risks: int
    section_flags: dict[str, float]
    label_counts: dict[str, int]
