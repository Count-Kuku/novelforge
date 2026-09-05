"""Prompt templates and builders for every generation stage.

This package preserves the historic ``novelforge.core.prompts`` module API while
splitting the 2100+ line monolith into single-responsibility modules. Callers
keep importing from ``novelforge.core.prompts`` unchanged.
"""

from ._formatting import (
    RULE_LABELS,
    format_discussion_history,
    format_rules_for_prompt,
    format_story_state_guidance,
    merge_retrieval_context,
)
from .planning import (
    arc_outline_prompt,
    chapter_outline_prompt,
    discuss_arc_prompt,
    discuss_chapter_prompt,
    discuss_creative_profile_prompt,
    discuss_outline_prompt,
    discuss_volume_prompt,
    outline_prompt,
    volume_outline_prompt,
)
from .discussion_turns import (
    discuss_arc_turn_prompt,
    discuss_chapter_turn_prompt,
    discuss_creative_profile_turn_prompt,
    discuss_outline_turn_prompt,
    discuss_volume_turn_prompt,
)
from .writing import (
    compile_creative_fragments_prompt,
    compact_memory_prompt,
    creative_fragment_prompt,
    creative_session_summary_prompt,
    setting_extraction_prompt,
    update_memory_prompt,
    write_chapter_prompt,
)
from .analysis import (
    character_analysis_prompt,
    consistency_check_prompt,
    foreshadowing_analysis_prompt,
    organize_reference_prompt,
    review_chapter_prompt,
    timeline_analysis_prompt,
)
from .extraction import (
    EXTRACTION_MODE_INSTRUCTIONS,
    consolidate_extracted_knowledge_prompt,
    extract_reference_knowledge_prompt,
    recall_missed_knowledge_prompt,
)
from .evaluation import (
    arc_chapter_plan_prompt,
    comprehensive_chapter_evaluation_prompt,
    creative_structure_prompt,
    evaluate_chapter_prompt,
    plan_entity_context_query_prompt,
)

__all__ = [
    "RULE_LABELS",
    "format_story_state_guidance",
    "format_discussion_history",
    "format_rules_for_prompt",
    "merge_retrieval_context",
    "outline_prompt",
    "discuss_outline_prompt",
    "discuss_creative_profile_prompt",
    "volume_outline_prompt",
    "discuss_volume_prompt",
    "chapter_outline_prompt",
    "discuss_chapter_prompt",
    "arc_outline_prompt",
    "discuss_arc_prompt",
    "discuss_outline_turn_prompt",
    "discuss_volume_turn_prompt",
    "discuss_creative_profile_turn_prompt",
    "discuss_chapter_turn_prompt",
    "discuss_arc_turn_prompt",
    "write_chapter_prompt",
    "creative_fragment_prompt",
    "creative_session_summary_prompt",
    "compile_creative_fragments_prompt",
    "setting_extraction_prompt",
    "update_memory_prompt",
    "compact_memory_prompt",
    "review_chapter_prompt",
    "character_analysis_prompt",
    "timeline_analysis_prompt",
    "foreshadowing_analysis_prompt",
    "consistency_check_prompt",
    "organize_reference_prompt",
    "EXTRACTION_MODE_INSTRUCTIONS",
    "extract_reference_knowledge_prompt",
    "consolidate_extracted_knowledge_prompt",
    "recall_missed_knowledge_prompt",
    "creative_structure_prompt",
    "arc_chapter_plan_prompt",
    "evaluate_chapter_prompt",
    "comprehensive_chapter_evaluation_prompt",
    "plan_entity_context_query_prompt",
]
