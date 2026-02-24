from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="BRD Interpretation Pipeline", version="0.1.0")


class Traceability(BaseModel):
    section: str = Field(..., description="BRD section identifier such as 4.2.1")
    excerpt: str = Field(..., min_length=1, description="Verbatim BRD excerpt")


class AcceptanceCriterion(BaseModel):
    id: str
    gherkin: str = Field(..., description="Given/When/Then only when derivable from BRD")
    traceability: Traceability


class Story(BaseModel):
    id: str
    title: str
    description: str
    traceability: list[Traceability]
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)


class Epic(BaseModel):
    id: str
    title: str
    description: str
    traceability: list[Traceability]


class ProductDefinitionPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epics: list[Epic]
    stories: list[Story]
    acceptance_criteria: list[AcceptanceCriterion]
    traceability_links: list[Traceability]
    ambiguity_flags: list[str]
    questions_for_human: list[str]


class TestCase(BaseModel):
    id: str
    story_id: str
    scenario: str
    expected_result: str
    traceability: Traceability


class CoverageLink(BaseModel):
    requirement_ref: str
    test_case_id: str


class RiskAnnotation(BaseModel):
    story_id: str
    risk: str
    severity: Literal["low", "medium", "high"]
    traceability: Traceability


class RejectedItem(BaseModel):
    item_id: str
    reason: str


class TestDesignPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validated_stories: list[Story]
    manual_test_cases: list[TestCase]
    edge_cases: list[TestCase]
    risk_annotations: list[RiskAnnotation]
    rejected_items_with_reason: list[RejectedItem]
    coverage_map: list[CoverageLink]


class BRDUpload(BaseModel):
    brd_id: UUID = Field(default_factory=uuid4)
    title: str
    content: str


class IngestionResponse(BaseModel):
    brd_id: UUID
    uploaded_at: datetime
    structure_detected: bool
    note: str


class ApprovalRequest(BaseModel):
    brd_id: UUID
    pdp: ProductDefinitionPackage
    tdp: TestDesignPackage
    approved: bool


class JiraSyncPreview(BaseModel):
    allowed: bool
    message: str
    actions: list[str]


BRD_STORE: dict[UUID, BRDUpload] = {}


PO_SYSTEM_PROMPT = """You are part of a dual-agent enterprise system designed to convert Business Requirement Documents (BRDs) into Jira-ready delivery artifacts under strict human supervision.

SYSTEM PRINCIPLES:
- BRD is the single source of truth.
- Never invent functionality.
- If not found in BRD, return INSUFFICIENT SOURCE EVIDENCE.
- Determinism over creativity.

ROLE: PRODUCT_OWNER_AGENT
OUTPUT: Product Definition Package JSON with epics, stories, acceptance_criteria, traceability_links, ambiguity_flags, questions_for_human.
"""

QA_SYSTEM_PROMPT = """ROLE: QA_AGENT
OBJECTIVE: Validate each story is testable and traceable.
MUST:
- challenge vague ACs
- add edge and negative scenarios derived strictly from BRD logic
- reject weak traceability
MUST NOT:
- add functionality
- modify business intent
OUTPUT: Test Design Package JSON.
If unsupported by source: INSUFFICIENT SOURCE EVIDENCE.
"""


class PromptResponse(BaseModel):
    role: Literal["PRODUCT_OWNER_AGENT", "QA_AGENT"]
    system_prompt: str


class CritiqueLoopResult(BaseModel):
    passed: bool
    critique_rounds: int
    blockers: list[str]


def _enforce_traceability(pdp: ProductDefinitionPackage, tdp: TestDesignPackage) -> list[str]:
    issues: list[str] = []
    if not pdp.traceability_links:
        issues.append("PDP has no global traceability links.")

    for story in pdp.stories:
        if not story.traceability:
            issues.append(f"Story {story.id} missing traceability.")
        for ac in story.acceptance_criteria:
            if not ac.traceability.excerpt.strip():
                issues.append(f"AC {ac.id} has empty traceability excerpt.")

    for test_case in [*tdp.manual_test_cases, *tdp.edge_cases]:
        if not test_case.traceability.excerpt.strip():
            issues.append(f"Test case {test_case.id} has missing traceability excerpt.")

    return issues


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestionResponse)
def ingest_brd(payload: BRDUpload) -> IngestionResponse:
    BRD_STORE[payload.brd_id] = payload
    return IngestionResponse(
        brd_id=payload.brd_id,
        uploaded_at=datetime.utcnow(),
        structure_detected=True,
        note="Guided extraction staged: structure detection → clause segmentation → intent classification → rule extraction → story mapping.",
    )


@app.get("/prompts/po", response_model=PromptResponse)
def get_po_prompt() -> PromptResponse:
    return PromptResponse(role="PRODUCT_OWNER_AGENT", system_prompt=PO_SYSTEM_PROMPT)


@app.get("/prompts/qa", response_model=PromptResponse)
def get_qa_prompt() -> PromptResponse:
    return PromptResponse(role="QA_AGENT", system_prompt=QA_SYSTEM_PROMPT)


@app.post("/critique-loop", response_model=CritiqueLoopResult)
def critique_loop(pdp: ProductDefinitionPackage, tdp: TestDesignPackage) -> CritiqueLoopResult:
    issues = _enforce_traceability(pdp, tdp)
    return CritiqueLoopResult(
        passed=not issues,
        critique_rounds=1 if not issues else 2,
        blockers=issues,
    )


@app.post("/approve-sync", response_model=JiraSyncPreview)
def approve_and_preview_sync(payload: ApprovalRequest) -> JiraSyncPreview:
    if payload.brd_id not in BRD_STORE:
        raise HTTPException(status_code=404, detail="BRD not found")

    if not payload.approved:
        return JiraSyncPreview(
            allowed=False,
            message="Human approval required before Jira writes.",
            actions=[],
        )

    issues = _enforce_traceability(payload.pdp, payload.tdp)
    if issues:
        return JiraSyncPreview(
            allowed=False,
            message="Traceability validation failed.",
            actions=issues,
        )

    return JiraSyncPreview(
        allowed=True,
        message="Approved. Backend service may now execute Jira APIs.",
        actions=[
            "create_issue",
            "update_description",
            "add_attachment",
            "set_story_points",
            "assign_user",
            "link_epic",
            "add_test_cases",
        ],
    )


def main() -> None:
    print("Run with: uvicorn main:app --reload")


if __name__ == "__main__":
    main()
