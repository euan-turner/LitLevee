"""Typed models over the SQLite schema (`schema.sql`).

Plain Pydantic models, not an ORM -- `db/repository.py` reads/writes rows by
hand and (de)serializes JSON columns into/out of these. Matches the design
doc's tech table ("Models: Pydantic/dataclasses").
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RelevanceCategory(StrEnum):
    """Section 12's four-way relevance category."""

    CORE = "core"
    INTERESTING = "interesting"
    PERIPHERAL = "peripheral"
    IRRELEVANT = "irrelevant"


# Categories that belong in the daily digest (section 12: "The daily digest
# should normally include only Core and Interesting papers").
DIGESTIBLE_CATEGORIES = (RelevanceCategory.CORE, RelevanceCategory.INTERESTING)


class FeedbackType(StrEnum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    MORE_LIKE_THIS = "more_like_this"
    SAVE = "save"


class LandscapeCategory(StrEnum):
    FOUNDATIONS = "foundations"
    MAJOR_APPROACHES = "major_approaches"
    RECENT_WORK = "recent_work"
    ADJACENT = "adjacent"


class FunnelStage(StrEnum):
    """How far a candidate made it through the relevance funnel (section 11)."""

    METADATA = "metadata"
    LEXICAL = "lexical"
    EMBEDDING = "embedding"
    LLM = "llm"


# --- Research direction (section 4) ---------------------------------------


class Scope(BaseModel):
    included: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class VenuePriority(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)


class Seeds(BaseModel):
    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class Monitoring(BaseModel):
    enabled: bool = True
    frequency: str = "daily"
    publication_window_hours: int = 48


class Priority(BaseModel):
    core: list[str] = Field(default_factory=list)
    interesting: list[str] = Field(default_factory=list)
    peripheral: list[str] = Field(default_factory=list)


class ResearchDirection(BaseModel):
    id: str
    name: str
    research_question: str
    scope: Scope = Field(default_factory=Scope)
    topics: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    priority: Priority = Field(default_factory=Priority)
    venues: VenuePriority = Field(default_factory=VenuePriority)
    seeds: Seeds = Field(default_factory=Seeds)
    monitoring: Monitoring = Field(default_factory=Monitoring)


# --- Papers ------------------------------------------------------------


class Author(BaseModel):
    id: int | None = None
    name: str
    normalized_name: str


class Institution(BaseModel):
    id: int | None = None
    name: str
    normalized_name: str


class Paper(BaseModel):
    id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)

    publication_date: datetime | None = None
    venue: str | None = None

    doi: str | None = None
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    openalex_id: str | None = None

    url: str | None = None
    pdf_url: str | None = None
    source: str
    citation_count: int | None = None

    content_hash: str
    first_seen_at: datetime
    last_updated_at: datetime


# --- Analysis (agent_seed/paper_analysis_schema.json) -----------------------


class AnalysisContext(BaseModel):
    why_relevant: str
    research_direction: str
    subtopics: list[str] = Field(default_factory=list)


class EvaluationEnvironment(BaseModel):
    hardware: str = "Not specified in the available paper text."
    software: str = "Not specified in the available paper text."
    workload: str = "Not specified in the available paper text."


class EvaluationResult(BaseModel):
    metric: str
    improvement: str
    comparison: str


class Evaluation(BaseModel):
    baselines: list[str] = Field(default_factory=list)
    environment: EvaluationEnvironment = Field(default_factory=EvaluationEnvironment)
    results: list[EvaluationResult] = Field(default_factory=list)
    summary: str


class PaperAnalysis(BaseModel):
    context: AnalysisContext
    objectives: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    evaluation: Evaluation


# --- Relevance funnel result (section 12) -----------------------------------


class RelevanceJudgement(BaseModel):
    relevant: bool
    score: float = Field(ge=0.0, le=1.0)
    direction: str
    subtopics: list[str] = Field(default_factory=list)
    category: RelevanceCategory
    reason: str


class PaperDirectionMatch(BaseModel):
    paper_id: str
    direction_id: str
    relevance_score: float | None = None
    relevance_category: RelevanceCategory
    reason: str | None = None
    subtopics: list[str] = Field(default_factory=list)
    stage_reached: FunnelStage
    analysed: bool = False
    analysis: PaperAnalysis | None = None
    digested_at: datetime | None = None
    created_at: datetime


# --- Landscape (section 6) --------------------------------------------------


class LandscapeEntry(BaseModel):
    id: int | None = None
    direction_id: str
    category: LandscapeCategory
    paper_id: str
    rank: int
    signal_summary: str | None = None
    delivered_at: datetime | None = None
    created_at: datetime


# --- Feedback (section 34) --------------------------------------------------


class Feedback(BaseModel):
    id: int | None = None
    paper_id: str
    direction_id: str | None = None
    feedback_type: FeedbackType
    feedback_text: str | None = None
    created_at: datetime


# --- Runs (section 30 observability) ----------------------------------------


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILURE = "failure"


class Run(BaseModel):
    id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    direction_ids: list[str] = Field(default_factory=list)
    providers_queried: list[str] = Field(default_factory=list)
    papers_discovered: int = 0
    papers_deduplicated: int = 0
    papers_rejected: int = 0
    papers_analysed: int = 0
    papers_surfaced: int = 0
    llm_calls: int = 0
    slack_status: str | None = None
    error: str | None = None
