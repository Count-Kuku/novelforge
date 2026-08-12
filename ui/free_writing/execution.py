"""Execute routed commands and正文 generation for the free-writing composer."""

from __future__ import annotations

import streamlit as st

from novelforge.services.memory import update_creative_session
from novelforge.services.model_readiness import require_chat_ready
from novelforge.workflows.creative_actions import (
    execute_creative_action,
    plan_creative_action,
)
from novelforge.workflows.interactive_writing import (
    create_writing_session,
    generate_writing_fragment,
)
from ui.common import scoped_session_key
from ui.streaming import run_with_stream

from .shared import (
    action_mode_key,
    last_result_key,
    pending_active_session_key,
)


def _ensure_action_session(
    project_name: str, story_id: str, session_id: str, bundle: dict,
    request: str, config: dict, session_options: dict,
) -> str:
    if bundle:
        return session_id
    created = create_writing_session(
        project_name, story_id, session_goal=request,
        writing_guidance=config["writing_guidance"],
        target_chapter_no=session_options["target_chapter_no"],
        auto_extract_mode=session_options["auto_extract_mode"],
    )
    effective_session_id = str(created["session_id"])
    st.session_state[pending_active_session_key(project_name, story_id)] = effective_session_id
    return effective_session_id


def run_creative_action(
    project_name: str, story_id: str, session_id: str, bundle: dict,
    request: str, config: dict, session_options: dict,
) -> None:
    try:
        effective_session_id = _ensure_action_session(
            project_name, story_id, session_id, bundle, request, config, session_options,
        )
        action_run = plan_creative_action(
            project_name, story_id, effective_session_id, request,
        )
        if not action_run.get("requires_confirmation"):
            execute_creative_action(project_name, str(action_run.get("action_id") or ""))
        st.session_state[
            scoped_session_key(
                "creative_user_input_clear", project_name, story_id,
                effective_session_id,
            )
        ] = True
        st.rerun()
    except Exception as exc:
        st.error(f"创作命令执行失败：{exc}")


def run_creative_generation(
    project_name: str,
    story_id: str,
    session_id: str,
    bundle: dict,
    action: str,
    branch_id: str | None,
    user_message: str,
    config: dict,
    session_options: dict,
) -> None:
    try:
        require_chat_ready(action="自由创作")
        effective_session_id = session_id
        if not bundle:
            created = create_writing_session(
                project_name,
                story_id,
                session_goal=user_message,
                writing_guidance=config["writing_guidance"],
                target_chapter_no=session_options["target_chapter_no"],
                auto_extract_mode=session_options["auto_extract_mode"],
            )
            effective_session_id = str(created["session_id"])
            st.session_state[
                pending_active_session_key(project_name, story_id)
            ] = effective_session_id
        else:
            update_creative_session(
                project_name,
                effective_session_id,
                {
                    "writing_guidance": config["writing_guidance"],
                    "target_chapter_no": session_options["target_chapter_no"],
                    "auto_extract_mode": session_options["auto_extract_mode"],
                },
                story_id=story_id,
            )

        result = run_with_stream(
            "正在生成创作片段...",
            generate_writing_fragment,
            project_name,
            story_id,
            effective_session_id,
            user_message,
            action_type=action,
            word_count=config["word_count"],
            writing_guidance=config["writing_guidance"],
            prompt_option_ids=config["prompt_option_ids"],
            manual_knowledge_ids=config["manual_knowledge_ids"],
            branch_from_fragment_id=branch_id,
        )
        st.session_state[
            last_result_key(project_name, story_id, effective_session_id)
        ] = result
        st.session_state[action_mode_key(effective_session_id)] = "continue"
        st.session_state[
            scoped_session_key(
                "creative_user_input_clear",
                project_name,
                story_id,
                effective_session_id,
            )
        ] = True
        st.rerun()
    except Exception as exc:
        st.error(f"生成失败：{exc}")
