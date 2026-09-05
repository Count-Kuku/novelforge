"""Web research and search schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)

class WebSearchHit(NovelForgeSchema):
    """Normalized result returned by a web-search provider."""

    result_id: str
    provider: str
    query: str
    title: str = ""
    url: str
    description: str = ""
    extra_snippets: list[str] = Field(default_factory=list)
    language: str = ""
    published_at: str = ""
    rank: int = Field(default=0, ge=0)

    @field_validator("extra_snippets", mode="before")
    @classmethod
    def _normalize_extra_snippets(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebSearchResult(NovelForgeSchema):
    """One provider response plus its normalized result rows."""

    provider: str
    query: str
    results: list[WebSearchHit] = Field(default_factory=list)
    more_results_available: bool = False
    requested_count: int = Field(default=0, ge=0)


class FetchedWebPage(NovelForgeSchema):
    """Safe, cleaned representation of one downloaded web page."""

    requested_url: str
    final_url: str
    title: str = ""
    description: str = ""
    text: str
    content_hash: str
    fetched_at: str
    status_code: int = Field(ge=100, le=599)
    content_type: str = ""
    byte_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebResearchBranch(NovelForgeSchema):
    """A bounded, independently searchable branch of a research plan."""

    branch_id: str
    label: str
    query: str
    source_kind: Literal["official", "secondary", "community", "fanon", "general"] = "general"
    preferred_domains: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=20)

    @field_validator("preferred_domains", "excluded_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchPlan(NovelForgeSchema):
    """Structured planner output used by the bounded research graph."""

    topic: str
    objective: str = ""
    branches: list[WebResearchBranch] = Field(default_factory=list)
    max_search_rounds: int = Field(default=1, ge=1, le=3)
    max_pages: int = Field(default=12, ge=1, le=50)
    notes: list[str] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchSourceAssessment(NovelForgeSchema):
    """Explainable authority assessment for one discovered source."""

    url: str
    source_kind: Literal["official", "secondary", "community", "fanon", "general"] = "general"
    authority: Literal["official", "curated", "community", "unknown"] = "unknown"
    score: float = Field(default=0.3, ge=0.0, le=1.0)
    rationale: str = ""
    signals: list[str] = Field(default_factory=list)

    @field_validator("signals", mode="before")
    @classmethod
    def _normalize_signals(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchEvidence(NovelForgeSchema):
    """A quote that can be traced back to a fetched page."""

    source_url: str
    source_title: str = ""
    quote: str
    source_kind: Literal["official", "secondary", "community", "fanon", "general"] = "general"
    authority: Literal["official", "curated", "community", "unknown"] = "unknown"
    content_hash: str = ""
    source_relative_path: str = ""
    claim_id: str = ""
    stance: Literal["support", "contradict"] = "support"


class WebResearchClaim(NovelForgeSchema):
    """One source-bounded claim extracted from untrusted web content."""

    claim_id: str
    category: Literal[
        "characters",
        "items",
        "abilities",
        "world_rules",
        "locations",
        "organizations",
        "timeline_events",
        "relationships",
        "writing_style",
        "dialogue_style",
        "narrative_techniques",
    ]
    name: str
    statement: str
    details: dict[str, str] = Field(default_factory=dict)
    evidence: list[WebResearchEvidence] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_url: str
    source_title: str = ""
    source_kind: Literal["official", "secondary", "community", "fanon", "general"] = "general"
    authority: Literal["official", "curated", "community", "unknown"] = "unknown"
    tags: list[str] = Field(default_factory=list)

    @field_validator("details", mode="before")
    @classmethod
    def _normalize_claim_details(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key).strip(): _stringify_item(item)
            for key, item in value.items()
            if str(key).strip() and _stringify_item(item)
        }

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_claim_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchPageExtraction(NovelForgeSchema):
    source_url: str
    source_title: str = ""
    source_summary: str = ""
    claims: list[WebResearchClaim] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    candidate_claim_count: int = Field(default=0, ge=0)
    rejected_claim_count: int = Field(default=0, ge=0)

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_page_notes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchVerificationDecision(NovelForgeSchema):
    """Semantic merge/conflict decision produced by the verifier role."""

    decision_id: str
    category: Literal[
        "characters",
        "items",
        "abilities",
        "world_rules",
        "locations",
        "organizations",
        "timeline_events",
        "relationships",
        "writing_style",
        "dialogue_style",
        "narrative_techniques",
    ]
    name: str
    summary: str
    details: dict[str, str] = Field(default_factory=dict)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("supporting_claim_ids", "contradicting_claim_ids", "tags", mode="before")
    @classmethod
    def _normalize_decision_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("details", mode="before")
    @classmethod
    def _normalize_decision_details(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key).strip(): _stringify_item(item)
            for key, item in value.items()
            if str(key).strip() and _stringify_item(item)
        }


class WebResearchVerificationResult(NovelForgeSchema):
    decisions: list[WebResearchVerificationDecision] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_verification_notes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class VerifiedWebResearchClaim(NovelForgeSchema):
    """Human-review candidate after deterministic evidence validation."""

    claim_id: str
    category: str
    name: str
    summary: str
    details: dict[str, str] = Field(default_factory=dict)
    evidence: list[WebResearchEvidence] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    authority: Literal["official", "curated", "community", "unknown"] = "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    verification_status: Literal["supported", "single_source", "contested", "rejected"] = "single_source"
    verification_rationale: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator(
        "supporting_claim_ids",
        "contradicting_claim_ids",
        "source_urls",
        "source_kinds",
        "tags",
        mode="before",
    )
    @classmethod
    def _normalize_verified_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class WebResearchEvaluation(NovelForgeSchema):
    planned_branch_count: int = Field(default=0, ge=0)
    covered_branch_count: int = Field(default=0, ge=0)
    branch_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_hit_count: int = Field(default=0, ge=0)
    unique_hit_count: int = Field(default=0, ge=0)
    duplicate_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    unique_domain_count: int = Field(default=0, ge=0)
    source_kind_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    fetch_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    candidate_claim_count: int = Field(default=0, ge=0)
    rejected_claim_count: int = Field(default=0, ge=0)
    evidence_valid_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    corroboration_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    authority_distribution: dict[str, int] = Field(default_factory=dict)
