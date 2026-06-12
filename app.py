import json

import streamlit as st
from urllib.parse import urlparse

from memory import (
    create_project,
    delete_retrieval_source_file,
    load_analysis_report,
    load_global_rules,
    list_projects,
    list_retrieval_source_files,
    load_chapter,
    load_chapter_outline,
    load_memory,
    load_outline,
    load_project_rules,
    load_review,
    load_review_json,
    save_chapter,
    save_chapter_outline,
    save_global_rules,
    save_memory,
    save_outline,
    save_project_rules,
    list_pipeline_runs,
    load_pipeline_run,
    retrieval_sources_path,
)
from project_manager import (
    delete_analysis_report,
    delete_chapter_analysis_bundle,
    delete_chapter_bundle,
    delete_chapter_content,
    delete_chapter_outline,
    delete_chapter_review,
    delete_outline,
    delete_pipeline_run,
    delete_project,
    get_project_summary,
    list_analysis_reports,
    list_chapter_inventory,
    list_project_runs,
    list_retrieval_sources,
    rename_project,
    save_analysis_resource,
    save_retrieval_source_content,
    save_review_resources,
)
from retrieval import build_structured_external_source_payload, rebuild_retrieval_assets, ingest_external_source_file, load_retrieval_index, retrieve_context
from skills import (
    analyze_characters,
    analyze_foreshadowing,
    analyze_timeline,
    compact_memory,
    detect_potential_conflicts,
    discuss_chapter,
    discuss_chapter_turn,
    discuss_outline,
    discuss_outline_turn,
    generate_chapter_outline,
    generate_outline,
    get_retrieval_trace,
    organize_reference_html,
    organize_reference_url,
    organize_reference_text,
    review_chapter,
    run_consistency_check,
    pipeline_plan_write_review_update,
    save_rule_text,
    update_memory_from_chapter,
    write_chapter,
)


RULE_SCOPE_OPTIONS = {
    "all": "通用",
    "outline": "全书大纲",
    "chapter_outline": "章节细纲",
    "write": "正文写作",
    "review": "章节审阅",
    "memory_update": "设定更新",
}


NEW_PROJECT_INPUT_KEY = "new_project_name_input"
NEW_PROJECT_DIALOG_FLAG = "show_new_project_dialog"


def _discussion_messages_key(kind: str, suffix: str = "") -> str:
    return f"discussion_messages:{kind}:{suffix}" if suffix else f"discussion_messages:{kind}"


def _discussion_result_key(kind: str, suffix: str = "") -> str:
    return f"discussion_result:{kind}:{suffix}" if suffix else f"discussion_result:{kind}"


def _discussion_input_key(kind: str, suffix: str = "") -> str:
    return f"discussion_input:{kind}:{suffix}" if suffix else f"discussion_input:{kind}"


def _append_discussion_message(key: str, role: str, content: str):
    content = str(content or "").strip()
    if not content:
        return
    messages = list(st.session_state.get(key, []))
    messages.append({"role": role, "content": content})
    st.session_state[key] = messages


def _render_discussion_chat(messages: list[dict]):
    if not messages:
        st.caption("当前还没有讨论消息。")
        return
    for item in messages:
        role = "user" if item.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(str(item.get("content", "") or ""))


def _render_discussion_summary(discussion_result: dict, empty_message: str):
    discussion = discussion_result.get("data", {}).get("discussion", {}) if discussion_result else {}
    report_markdown = discussion_result.get("data", {}).get("report_markdown", "") if discussion_result else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown)
    render_step_validation(discussion_result)
    render_step_json_expander("讨论结构化结果", discussion)


def _resource_browser_selection_key(project_name: str) -> str:
    return f"resource_browser_selection:{project_name}"


def _set_resource_browser_selection(project_name: str, resource: dict):
    st.session_state[_resource_browser_selection_key(project_name)] = resource


def _get_resource_browser_selection(project_name: str) -> dict:
    return dict(st.session_state.get(_resource_browser_selection_key(project_name), {}))


def render_step_status_message(step_result: dict, success_message: str, failure_prefix: str):
    if not step_result:
        return

    status = step_result.get("status")
    if status == "completed":
        st.success(success_message)
    elif status == "skipped":
        warnings = step_result.get("warnings") or []
        st.info(warnings[0] if warnings else "步骤已跳过。")
    else:
        st.error(f"{failure_prefix}{step_result.get('error', 'unknown error')}")


def render_step_validation(step_result: dict):
    validation = step_result.get("validation", {})
    if validation.get("status") == "passed":
        st.caption(f"Schema validated: {validation.get('schema_name', '-')}")
    elif validation.get("status") == "failed":
        schema_name = validation.get("schema_name", "-")
        errors = validation.get("errors") or []
        message = errors[0] if errors else validation.get("message", "Schema validation failed.")
        st.caption(f"Schema failed: {schema_name} / {message}")


def render_step_json_expander(title: str, payload: dict):
    if not payload:
        return
    with st.expander(title, expanded=False):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")


def render_step_retrieval(step_result: dict, title: str, fallback_hits: list[dict] | None = None):
    hits = step_result.get("retrieval_hits", []) if step_result else []
    render_retrieval_hits_block(hits or (fallback_hits or []), title)


def _render_rule_editor(title: str, storage_key: str, rules: dict) -> dict:
    st.subheader(title)
    updated = {}
    for scope, label in RULE_SCOPE_OPTIONS.items():
        updated[scope] = [line.strip() for line in st.text_area(
            f"{label}规则（每行一条）",
            value="\n".join(rules.get(scope, [])),
            height=120,
            key=f"{storage_key}_{scope}"
        ).split("\n") if line.strip()]
    return updated


def render_rules_page(project_name: str):
    st.subheader("交互规则中心")
    st.caption("将长期要求存成全局规则或项目规则，系统会在对应能力里自动注入这些约束。")

    with st.expander("快速记录新要求", expanded=True):
        rule_text = st.text_area("输入你的要求", height=140, key="rule_capture_text")
        col1, col2 = st.columns(2)
        scope_label = col1.selectbox("适用能力", options=list(RULE_SCOPE_OPTIONS.values()), key="rule_capture_scope")
        target_label = col2.selectbox("保存位置", options=["项目规则", "全局规则"], key="rule_capture_target")

        if st.button("保存要求为规则"):
            scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
            target = "project" if target_label == "项目规则" else "global"
            try:
                result = save_rule_text(project_name, scope, target, rule_text)
                if result.get("status") == "saved":
                    st.success(f"已保存到{target_label} / {scope_label}")
                    st.rerun()
                else:
                    st.warning("未提取到有效规则。")
            except Exception as exc:
                st.error(f"保存失败：{exc}")

    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)

    tab1, tab2 = st.tabs(["项目规则", "全局规则"])

    with tab1:
        updated_project_rules = _render_rule_editor(f"项目规则：{project_name}", "project_rules", project_rules)
        if st.button("保存项目规则"):
            save_project_rules(project_name, updated_project_rules)
            st.success("项目规则已保存")

    with tab2:
        updated_global_rules = _render_rule_editor("全局规则", "global_rules", global_rules)
        if st.button("保存全局规则"):
            save_global_rules(updated_global_rules)
            st.success("全局规则已保存")


@st.dialog("新建项目")
def render_new_project_dialog(existing_projects: list[str]):
    candidate_name = st.text_input("项目名", key=NEW_PROJECT_INPUT_KEY).strip()
    col1, col2 = st.columns(2)

    if col1.button("确认创建", use_container_width=True):
        if not candidate_name:
            st.error("项目名不能为空。")
            return
        if candidate_name in existing_projects:
            st.error("该项目已存在，请使用项目切换。")
            return

        created_project = create_project(candidate_name)
        st.session_state["project_name"] = created_project
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()

    if col2.button("取消", use_container_width=True):
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()


def init_project_state() -> str | None:
    projects = list_projects()

    project_name = st.session_state.get("project_name")
    if project_name:
        if project_name not in projects:
            create_project(project_name)
        return project_name

    if projects:
        st.session_state["project_name"] = projects[0]
        return projects[0]

    return None


def render_sidebar(project_name: str | None, projects: list[str]):
    if projects:
        st.sidebar.caption("已有项目")
        selected_project = st.sidebar.selectbox(
            "快速切换",
            options=projects,
            index=projects.index(project_name) if project_name in projects else 0,
            key="project_switcher"
        )
        if selected_project != project_name:
            st.session_state["project_name"] = selected_project
            st.rerun()

    if st.sidebar.button("新建项目", use_container_width=True):
        st.session_state[NEW_PROJECT_INPUT_KEY] = ""
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = True

    if st.session_state.get(NEW_PROJECT_DIALOG_FLAG):
        render_new_project_dialog(projects)


def render_memory_page(project_name: str, memory: dict):
    st.subheader("当前故事状态")
    st.caption("这里维护的是生成时始终优先注入的核心状态。长文本资料、原作证据、历史正文与分析报告仍通过检索知识库按需召回。")

    changed = False
    new_memory = dict(memory)

    new_title = st.text_input("书名", value=memory.get("title", ""))
    if new_title != memory.get("title"):
        new_memory["title"] = new_title
        changed = True

    new_genre = st.text_input("类型", value=memory.get("genre", ""))
    if new_genre != memory.get("genre"):
        new_memory["genre"] = new_genre
        changed = True

    new_canon_mode = st.text_input(
        "原作对齐方式（如：严格贴合 / 轻度 AU / 完全 AU）",
        value=memory.get("canon_mode", "")
    )
    if new_canon_mode != memory.get("canon_mode", ""):
        new_memory["canon_mode"] = new_canon_mode
        changed = True

    new_au_rules = st.text_area(
        "AU 规则（每行一条）",
        value="\n".join(memory.get("au_rules", [])),
        height=100
    )
    au_rule_items = [line.strip() for line in new_au_rules.split("\n") if line.strip()]
    if au_rule_items != memory.get("au_rules", []):
        new_memory["au_rules"] = au_rule_items
        changed = True

    new_world = st.text_area(
        "世界观（每行一条）",
        value="\n".join(memory.get("world", [])),
        height=120
    )
    world_items = [line.strip() for line in new_world.split("\n") if line.strip()]
    if world_items != memory.get("world", []):
        new_memory["world"] = world_items
        changed = True

    new_characters = st.text_area(
        "角色（每行一条）",
        value="\n".join(memory.get("characters", [])),
        height=150
    )
    character_items = [line.strip() for line in new_characters.split("\n") if line.strip()]
    if character_items != memory.get("characters", []):
        new_memory["characters"] = character_items
        changed = True

    new_relationships = st.text_area(
        "角色关系（每行一条）",
        value="\n".join(memory.get("relationships", [])),
        height=120
    )
    relationship_items = [line.strip() for line in new_relationships.split("\n") if line.strip()]
    if relationship_items != memory.get("relationships", []):
        new_memory["relationships"] = relationship_items
        changed = True

    new_timeline = st.text_area(
        "时间线（每行一条）",
        value="\n".join(memory.get("timeline", [])),
        height=120
    )
    timeline_items = [line.strip() for line in new_timeline.split("\n") if line.strip()]
    if timeline_items != memory.get("timeline", []):
        new_memory["timeline"] = timeline_items
        changed = True

    new_foreshadowing = st.text_area(
        "伏笔（每行一条）",
        value="\n".join(memory.get("foreshadowing", [])),
        height=120
    )
    foreshadowing_items = [line.strip() for line in new_foreshadowing.split("\n") if line.strip()]
    if foreshadowing_items != memory.get("foreshadowing", []):
        new_memory["foreshadowing"] = foreshadowing_items
        changed = True

    new_constraints = st.text_area(
        "当前硬性约束（每行一条）",
        value="\n".join(memory.get("active_constraints", [])),
        height=100
    )
    constraint_items = [line.strip() for line in new_constraints.split("\n") if line.strip()]
    if constraint_items != memory.get("active_constraints", []):
        new_memory["active_constraints"] = constraint_items
        changed = True

    col1, col2 = st.columns(2)
    if col1.button("保存设定"):
        save_memory(project_name, new_memory)
        st.success("已保存")
        st.rerun()

    if col2.button("精简设定库"):
        with st.spinner("正在压缩旧设定..."):
            result = compact_memory(project_name)
        if result.get("status") == "accepted":
            st.success("设定库已精简")
            st.rerun()
        else:
            st.error(f"精简失败：{result.get('reason', 'unknown')}")

    with st.expander("原始 JSON（高级编辑）", expanded=False):
        raw_json = st.text_area(
            "memory.json",
            value=json.dumps(new_memory, ensure_ascii=False, indent=2),
            height=400
        )
        if st.button("从 JSON 保存"):
            try:
                parsed = json.loads(raw_json)
                save_memory(project_name, parsed)
                st.success("已保存")
                st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"JSON 格式错误：{exc}")


def render_outline_page(project_name: str):
    st.subheader("全书大纲")

    existing_outline = load_outline(project_name)
    step_result = st.session_state.get("outline_step", {})
    user_idea = st.text_area("你的小说想法", height=200)

    messages_key = _discussion_messages_key("outline")
    result_key = _discussion_result_key("outline")
    input_key = _discussion_input_key("outline")
    discussion_step = st.session_state.get(result_key, {})

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论大纲方向"):
        try:
            result = discuss_outline(project_name, user_idea)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、可选方向和待确认问题，我们可以继续往下细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置讨论"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[input_key] = ""
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前收敛出的结论。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area("继续讨论", key=input_key, height=120, placeholder="例如：我更想突出成长线，但不要太早进入主线冲突。")
        if st.button("发送讨论消息", key="send_outline_discussion"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            elif not user_idea.strip():
                st.warning("请先填写你的小说想法。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_outline_turn(
                        project_name,
                        user_idea,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了当前讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[input_key] = ""
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成全书大纲"):
        result = generate_outline(project_name, user_idea)
        st.session_state["outline_step"] = result
        st.session_state["outline"] = result.get("data", {}).get("outline", "")

    outline_text = st.text_area(
        "大纲内容",
        value=st.session_state.get("outline", existing_outline),
        height=500
    )

    if st.button("保存大纲"):
        save_outline(project_name, outline_text)
        st.success("大纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次大纲生成使用的检索上下文", get_retrieval_trace(f"outline:{project_name}"))


def render_chapter_outline_page(project_name: str):
    st.subheader("章节细纲")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    step_result = st.session_state.get(f"chapter_outline_step_{chapter_no}", {})
    requirement = st.text_area("本章要求", height=200)

    suffix = str(chapter_no)
    messages_key = _discussion_messages_key("chapter", suffix)
    result_key = _discussion_result_key("chapter", suffix)
    input_key = _discussion_input_key("chapter", suffix)
    discussion_step = st.session_state.get(result_key, {})

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论本章方向"):
        try:
            result = discuss_chapter(project_name, chapter_no, requirement)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本章目标、可选方向和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置本章讨论"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[input_key] = ""
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示本章方向的当前结论。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area(
            "继续讨论本章",
            key=input_key,
            height=120,
            placeholder="例如：我希望这章更偏日常拉扯，不要太快进入正面冲突。"
        )
        if st.button("发送本章讨论消息", key=f"send_chapter_discussion_{chapter_no}"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            elif not requirement.strip():
                st.warning("请先填写本章要求。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_chapter_turn(
                        project_name,
                        chapter_no,
                        requirement,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本章讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[input_key] = ""
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成章节细纲"):
        result = generate_chapter_outline(project_name, chapter_no, requirement)
        st.session_state[f"chapter_outline_step_{chapter_no}"] = result
        st.session_state[f"chapter_outline_{chapter_no}"] = result.get("data", {}).get("chapter_outline", "")

    outline_text = st.text_area(
        "章节细纲内容",
        value=st.session_state.get(f"chapter_outline_{chapter_no}", existing_outline),
        height=500
    )

    if st.button("保存章节细纲"):
        save_chapter_outline(project_name, chapter_no, outline_text)
        st.success(f"第 {chapter_no} 章细纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次细纲生成使用的检索上下文",
        get_retrieval_trace(f"chapter_outline:{project_name}:{chapter_no}")
    )


def render_chapter_page(project_name: str):
    st.subheader("章节正文")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no)
    chapter_step = st.session_state.get(f"chapter_step_{chapter_no}", {})

    chapter_outline = st.text_area(
        "章节细纲",
        value=existing_outline,
        height=250
    )

    word_count = st.text_input(
        "目标字数（如 2000-2500）",
        value="2000-2500"
    )

    if st.button("写正文"):
        result = write_chapter(project_name, chapter_no, chapter_outline, word_count)
        st.session_state[f"chapter_step_{chapter_no}"] = result
        st.session_state[f"chapter_{chapter_no}"] = result.get("data", {}).get("chapter", "")

    chapter_text = st.text_area(
        "章节正文",
        value=st.session_state.get(f"chapter_{chapter_no}", existing_chapter),
        height=600
    )

    if st.button("保存正文"):
        save_chapter(project_name, chapter_no, chapter_text)
        st.success(f"第 {chapter_no} 章正文已保存")

    if st.button("根据正文更新设定库"):
        result = update_memory_from_chapter(project_name, chapter_no, chapter_text)
        st.session_state[f"memory_update_step_{chapter_no}"] = result
        render_step_status_message(result, "设定库更新成功", "设定库更新失败：")
        render_step_validation(result)
        render_step_json_expander("设定更新结果 JSON", result)

    render_step_validation(chapter_step)
    render_step_retrieval(
        chapter_step,
        "本次正文生成使用的检索上下文",
        get_retrieval_trace(f"write:{project_name}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(f"memory_update_step_{chapter_no}", {}),
        "本次设定更新使用的检索上下文",
        get_retrieval_trace(f"memory_update:{project_name}:{chapter_no}")
    )


def render_review_page(project_name: str):
    st.subheader("章节审阅")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="review_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    review_text_key = f"review_result_text_{chapter_no}"
    chapter_text_key = f"review_chapter_text_{chapter_no}"

    existing_review = load_review(project_name, chapter_no)
    existing_review_json = load_review_json(project_name, chapter_no) or {}
    review_step = st.session_state.get(f"review_step_{chapter_no}", {})

    chapter_text = st.text_area(
        "待审阅正文",
        value=existing_chapter,
        height=450,
        key=chapter_text_key
    )

    if st.button("生成审阅意见"):
        try:
            review_result = review_chapter(project_name, chapter_no, chapter_text)
            review_markdown = review_result.get("data", {}).get("review_markdown", "")
            st.session_state[f"review_{chapter_no}"] = review_markdown
            st.session_state[review_text_key] = review_markdown
            st.session_state[f"review_step_{chapter_no}"] = review_result
            st.rerun()
        except Exception as exc:
            st.error(f"生成审阅失败：{exc}")

    review_text = st.text_area(
        "审阅结果",
        value=st.session_state.get(f"review_{chapter_no}", existing_review),
        height=450,
        key=review_text_key
    )

    if review_text:
        st.markdown(review_text)

    latest_review_json = load_review_json(project_name, chapter_no) or existing_review_json

    if latest_review_json:
        st.caption("结构化审阅状态")
        cols = st.columns(3)
        cols[0].metric("Status", latest_review_json.get("status", "-"))
        cols[1].metric("Issues", len(latest_review_json.get("issues", [])))
        cols[2].metric("Strengths", len(latest_review_json.get("strengths", [])))

    render_step_validation(review_step)
    render_step_retrieval(
        review_step,
        "本次审阅使用的检索上下文",
        get_retrieval_trace(f"review:{project_name}:{chapter_no}")
    )


def render_project_overview_page(project_name: str):
    st.subheader("项目总览")
    summary = get_project_summary(project_name)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("正文章节", summary.get("chapter_count", 0))
    col2.metric("细纲章节", summary.get("chapter_outline_count", 0))
    col3.metric("审阅数量", summary.get("review_count", 0))
    col4.metric("分析报告", summary.get("analysis_count", 0))

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("流水线记录", summary.get("run_count", 0))
    col6.metric("外部资料", summary.get("retrieval_source_count", 0))
    col7.metric("章节摘要", summary.get("chapter_summary_count", 0))
    col8.metric("资源文件数", summary.get("resource_file_count", 0))

    st.caption(
        f"title={summary.get('title', project_name)} / genre={summary.get('genre', '-') or '-'} / canon_mode={summary.get('canon_mode', '-') or '-'} / updated_at={summary.get('updated_at', '-') or '-'}"
    )

    with st.expander("项目设置", expanded=False):
        new_name = st.text_input("重命名项目", value=project_name, key=f"rename_project_input_{project_name}")
        if st.button("保存新项目名"):
            try:
                renamed = rename_project(project_name, new_name)
                st.session_state["project_name"] = renamed
                st.success(f"项目已重命名为 `{renamed}`。")
                st.rerun()
            except Exception as exc:
                st.error(f"项目重命名失败：{exc}")

    with st.expander("危险操作", expanded=False):
        st.warning("删除项目会移除该项目下的全部设定、章节、审阅、分析、检索资料和运行记录。")
        confirm_value = st.text_input("输入项目名以确认删除", key=f"delete_project_confirm_{project_name}")
        if st.button("删除当前项目", type="primary"):
            if confirm_value.strip() != project_name:
                st.error("项目名确认不匹配，已取消删除。")
            else:
                deleted = delete_project(project_name)
                if deleted:
                    st.session_state.pop("project_name", None)
                    st.success(f"项目 `{project_name}` 已删除。")
                    st.rerun()
                else:
                    st.error("项目删除失败，目标项目可能不存在。")


def _build_resource_browser_items(project_name: str) -> list[dict]:
    items: list[dict] = []

    outline = load_outline(project_name)
    items.append({
        "id": "outline:root",
        "group": "outline",
        "label": "outline.md",
        "path_label": "全书大纲 / outline.md",
        "content": outline,
        "chapter_no": None,
        "analysis_type": "",
        "relative_path": "outline.md",
        "editable": True,
        "deletable": bool(outline.strip()),
    })

    chapter_inventory = list_chapter_inventory(project_name)
    for item in chapter_inventory:
        chapter_no = int(item.get("chapter_no", 0))
        if item.get("has_outline"):
            items.append({
                "id": f"chapter-outline:{chapter_no}",
                "group": "chapter_outline",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapter_outlines / chapter_{chapter_no:03d}.md",
                "content": item.get("outline_preview", ""),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"chapter_outlines/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
        if item.get("has_content"):
            items.append({
                "id": f"chapter-content:{chapter_no}",
                "group": "chapter_content",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapters / chapter_{chapter_no:03d}.md",
                "content": item.get("content_preview", ""),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"chapters/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
        if item.get("has_review_markdown") or item.get("has_review_json"):
            items.append({
                "id": f"review:{chapter_no}",
                "group": "review",
                "label": f"chapter_{chapter_no:03d}",
                "path_label": f"reviews / chapter_{chapter_no:03d}",
                "content": item.get("review_preview", ""),
                "review_payload": item.get("review_payload", {}),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"reviews/chapter_{chapter_no:03d}",
                "editable": True,
                "deletable": True,
            })

    for report in list_analysis_reports(project_name):
        chapter_no = report.get("chapter_no")
        report_path = report.get("path", "")
        content = ""
        if report_path:
            try:
                with open(report_path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except Exception:
                content = ""
        items.append({
            "id": f"analysis:{report.get('analysis_type', 'unknown')}:{chapter_no}",
            "group": "analysis",
            "label": report.get("file_name", "analysis.md"),
            "path_label": f"analysis / {report.get('file_name', 'analysis.md')}",
            "content": content,
            "chapter_no": chapter_no,
            "analysis_type": report.get("analysis_type", "unknown"),
            "relative_path": report.get("file_name", ""),
            "editable": True,
            "deletable": True,
        })

    for run in list_project_runs(project_name):
        run_content = load_pipeline_run(project_name, run.get("run_id", ""))
        items.append({
            "id": f"run:{run.get('run_id', '')}",
            "group": "run",
            "label": f"{run.get('run_id', '')}.json",
            "path_label": f"runs / {run.get('run_id', '')}.json",
            "content": run_content,
            "chapter_no": run.get("chapter_no"),
            "analysis_type": "",
            "run_id": run.get("run_id", ""),
            "relative_path": f"runs/{run.get('run_id', '')}.json",
            "editable": False,
            "deletable": True,
        })

    for source in list_retrieval_sources(project_name):
        items.append({
            "id": f"source:{source.get('relative_path', '')}",
            "group": "source",
            "label": source.get("relative_path", ""),
            "path_label": f"retrieval/sources / {source.get('relative_path', '')}",
            "content": source.get("preview", ""),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": source.get("relative_path", ""),
            "suffix": source.get("suffix", ""),
            "editable": True,
            "deletable": True,
        })

    return items


def _save_browser_resource(project_name: str, resource: dict, edited_content: str, edited_json_text: str = ""):
    group = resource.get("group")
    if group == "outline":
        save_outline(project_name, edited_content)
        return
    if group == "chapter_outline":
        save_chapter_outline(project_name, int(resource.get("chapter_no", 0)), edited_content)
        return
    if group == "chapter_content":
        save_chapter(project_name, int(resource.get("chapter_no", 0)), edited_content)
        return
    if group == "review":
        parsed = json.loads(edited_json_text) if edited_json_text.strip() else {}
        save_review_resources(project_name, int(resource.get("chapter_no", 0)), edited_content, parsed)
        return
    if group == "analysis":
        save_analysis_resource(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no", 0)), edited_content)
        return
    if group == "source":
        save_retrieval_source_content(project_name, str(resource.get("relative_path", "")), edited_content)
        rebuild_retrieval_assets(project_name, build_vectors=True)
        return
    raise ValueError(f"Unsupported resource group for save: {group}")


def _delete_browser_resource(project_name: str, resource: dict):
    group = resource.get("group")
    if group == "outline":
        return delete_outline(project_name)
    if group == "chapter_outline":
        return delete_chapter_outline(project_name, int(resource.get("chapter_no", 0)))
    if group == "chapter_content":
        return delete_chapter_content(project_name, int(resource.get("chapter_no", 0)))
    if group == "review":
        return delete_chapter_review(project_name, int(resource.get("chapter_no", 0)))
    if group == "analysis":
        return delete_analysis_report(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no", 0)))
    if group == "run":
        return delete_pipeline_run(project_name, str(resource.get("run_id", "")))
    if group == "source":
        deleted = delete_retrieval_source_file(project_name, str(resource.get("relative_path", "")))
        if deleted:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        return deleted
    raise ValueError(f"Unsupported resource group for delete: {group}")


def _render_resource_browser_detail(project_name: str, resource: dict):
    if not resource:
        st.caption("请先从左侧选择一个资源。")
        return

    st.markdown(f"### {resource.get('label', '')}")
    st.caption(resource.get("path_label", ""))

    group = resource.get("group")
    if group == "run":
        st.code(resource.get("content", ""), language="json")
        if st.button("删除该运行记录", key=f"browser_delete_{resource.get('id')}"):
            if _delete_browser_resource(project_name, resource):
                st.success("运行记录已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
        return

    edited_content = st.text_area(
        "内容",
        value=resource.get("content", ""),
        height=520,
        key=f"browser_editor_{resource.get('id')}"
    )

    edited_json_text = ""
    if group == "review":
        edited_json_text = st.text_area(
            "审阅 JSON",
            value=json.dumps(resource.get("review_payload", {}), ensure_ascii=False, indent=2),
            height=220,
            key=f"browser_json_{resource.get('id')}"
        )

    save_col, delete_col = st.columns(2)
    if resource.get("editable") and save_col.button("保存当前资源", key=f"browser_save_{resource.get('id')}"):
        try:
            _save_browser_resource(project_name, resource, edited_content, edited_json_text)
            st.success("资源已保存。")
            st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"JSON 格式错误：{exc}")
        except Exception as exc:
            st.error(f"保存资源失败：{exc}")

    if resource.get("deletable") and delete_col.button("删除当前资源", key=f"browser_delete_{resource.get('id')}"):
        try:
            if _delete_browser_resource(project_name, resource):
                st.success("资源已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
            else:
                st.warning("目标资源不存在。")
        except Exception as exc:
            st.error(f"删除资源失败：{exc}")


def render_resource_management_page(project_name: str):
    st.subheader("项目资源管理")
    browser_items = _build_resource_browser_items(project_name)
    selected = _get_resource_browser_selection(project_name)

    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### 资源浏览器")
        search_value = st.text_input("搜索资源", key=f"resource_browser_search_{project_name}")
        search_lower = search_value.strip().lower()

        chapter_inventory = list_chapter_inventory(project_name)
        runs = list_project_runs(project_name)
        sources = list_retrieval_sources(project_name)

        if chapter_inventory:
            chapter_numbers = [item.get("chapter_no") for item in chapter_inventory]
            bulk_chapter_selection = st.multiselect(
                "批量章节清理",
                options=chapter_numbers,
                format_func=lambda value: f"第 {int(value)} 章",
                key=f"resource_bulk_chapters_{project_name}"
            )
            if bulk_chapter_selection and st.button("清理所选章节", key=f"bulk_delete_chapters_{project_name}"):
                results = []
                for chapter_no in bulk_chapter_selection:
                    results.append({
                        "chapter_no": int(chapter_no),
                        "result": delete_chapter_bundle(project_name, int(chapter_no)),
                    })
                st.success(f"已批量清理章节资源：{json.dumps(results, ensure_ascii=False)}")
                st.rerun()

        if runs:
            bulk_runs = st.multiselect(
                "批量删除运行记录",
                options=[run.get("run_id") for run in runs],
                key=f"resource_bulk_runs_{project_name}"
            )
            if bulk_runs and st.button("删除所选运行记录", key=f"bulk_delete_runs_{project_name}"):
                deleted_count = 0
                for run_id in bulk_runs:
                    if delete_pipeline_run(project_name, str(run_id)):
                        deleted_count += 1
                st.success(f"已删除 {deleted_count} 条运行记录。")
                st.rerun()

        if sources:
            bulk_sources = st.multiselect(
                "批量删除外部资料",
                options=[source.get("relative_path") for source in sources],
                key=f"resource_bulk_sources_{project_name}"
            )
            if bulk_sources and st.button("删除所选外部资料", key=f"bulk_delete_sources_{project_name}"):
                deleted_count = 0
                for relative_path in bulk_sources:
                    try:
                        if delete_retrieval_source_file(project_name, str(relative_path)):
                            deleted_count += 1
                    except Exception:
                        continue
                if deleted_count:
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(f"已删除 {deleted_count} 份外部资料。")
                st.rerun()

        groups = [
            ("outline", "全书大纲"),
            ("chapter_outline", "章节细纲"),
            ("chapter_content", "章节正文"),
            ("review", "审阅结果"),
            ("analysis", "分析报告"),
            ("run", "流水线记录"),
            ("source", "外部资料"),
        ]

        for group_key, group_label in groups:
            group_items = [item for item in browser_items if item.get("group") == group_key]
            if search_lower:
                group_items = [
                    item for item in group_items
                    if search_lower in str(item.get("label", "")).lower()
                    or search_lower in str(item.get("path_label", "")).lower()
                ]
            if not group_items:
                continue
            st.markdown(f"**{group_label}**")
            for item in group_items:
                selected_flag = selected.get("id") == item.get("id")
                button_label = f"> {item.get('label')}" if selected_flag else item.get("label")
                if st.button(button_label, key=f"resource_select_{item.get('id')}", use_container_width=True):
                    _set_resource_browser_selection(project_name, item)
                    st.rerun()

    with right_col:
        st.markdown("### 资源详情")
        if selected and not any(item.get("id") == selected.get("id") for item in browser_items):
            selected = {}
            st.session_state[_resource_browser_selection_key(project_name)] = {}
        if not selected and browser_items:
            selected = browser_items[0]
            _set_resource_browser_selection(project_name, selected)
        _render_resource_browser_detail(project_name, selected)


def render_project_files_page(project_name: str):
    st.subheader("项目文件预览")

    outline = load_outline(project_name)
    if outline:
        with st.expander("outline.md", expanded=True):
            st.markdown(outline)

    chapter_no = st.number_input("预览章节编号", min_value=1, value=1, key="preview_chapter_no")
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    chapter = load_chapter(project_name, chapter_no)
    review = load_review(project_name, chapter_no)
    review_json = load_review_json(project_name, chapter_no)

    if chapter_outline:
        with st.expander(f"chapter_outlines/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter_outline)

    if chapter:
        with st.expander(f"chapters/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter)

    if review:
        with st.expander(f"reviews/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(review)
    if review_json:
        with st.expander(f"reviews/chapter_{chapter_no:03d}.json", expanded=False):
            st.code(json.dumps(review_json, ensure_ascii=False, indent=2), language="json")


def render_pipeline_page(project_name: str):
    st.subheader("一键流水线：细纲→写作→审阅→更新记忆")
    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="pipeline_chapter_no")
    requirement = st.text_area("本章要求", height=200, key="pipeline_requirement")
    word_count = st.text_input(
        "目标字数（如 2500-3500）",
        value="2500-3500",
        key="pipeline_word_count"
    )

    if st.button("执行流水线"):
        with st.status("执行中..."):
            result = pipeline_plan_write_review_update(
                project_name, chapter_no, requirement, word_count
            )
        pipeline = result.get("pipeline", {})
        if result.get("success"):
            st.success("流水线完成")
        else:
            st.warning("流水线已完成，但存在失败或拒绝的步骤")
        if result.get("halted"):
            st.caption(f"Pipeline halted: {result.get('halt_reason', '-')}")

        steps_result = result.get("steps", {}) or pipeline.get("steps", {})

        st.subheader("执行状态")
        steps = [
            ("章节细纲", "chapter_outline"),
            ("写作正文", "write_chapter"),
            ("审阅", "review_chapter"),
            ("更新记忆", "memory_update"),
        ]
        for label, key in steps:
            step_result = steps_result.get(key, {})
            step_status = step_result.get("status")
            if step_status == "completed":
                st.success(f"{label}：完成")
            elif step_status == "skipped":
                st.info(f"{label}：已跳过（前置步骤未完成）")
            else:
                st.error(f"{label}：{step_result.get('error', 'unknown error')}")
            render_step_validation(step_result)

        st.subheader("结果预览")
        with st.expander("章节细纲", expanded=True):
            st.markdown(result.get("chapter_outline", "") or steps_result.get("chapter_outline", {}).get("data", {}).get("chapter_outline", "") or "（未生成）")
        with st.expander("章节正文", expanded=True):
            st.markdown(result.get("chapter", "") or steps_result.get("write_chapter", {}).get("data", {}).get("chapter", "") or "（未生成）")
        with st.expander("审阅报告", expanded=True):
            st.markdown(result.get("review_markdown", "") or steps_result.get("review_chapter", {}).get("data", {}).get("review_markdown", "") or "（未生成）")
        review = result.get("review") or steps_result.get("review_chapter", {}).get("data", {}).get("review") or {}
        if review:
            st.caption("结构化审阅状态")
            cols = st.columns(3)
            cols[0].metric("Status", review.get("status", "-"))
            cols[1].metric("Issues", len(review.get("issues", [])))
            cols[2].metric("Strengths", len(review.get("strengths", [])))
            with st.expander("审阅 JSON", expanded=False):
                st.code(json.dumps(review, ensure_ascii=False, indent=2), language="json")
        render_step_json_expander("记忆更新结果", result.get("memory_update") or steps_result.get("memory_update", {}))
        render_step_json_expander("流水线状态对象", result)

        transitions = result.get("transition_log", [])
        if transitions:
            with st.expander("状态迁移记录", expanded=False):
                for index, item in enumerate(transitions, start=1):
                    st.markdown(
                        f"{index}. `{item.get('from_step', '-')}` -> `{item.get('to_step', '-')}` / {item.get('timestamp', '-')}"
                    )
                    if item.get("reason"):
                        st.caption(item.get("reason"))

        workflow_errors = result.get("errors", [])
        if workflow_errors:
            with st.expander("工作流错误记录", expanded=False):
                for index, item in enumerate(workflow_errors, start=1):
                    st.markdown(
                        f"{index}. step=`{item.get('step_name', '-')}` / type=`{item.get('error_type', 'unknown')}` / recoverable=`{item.get('recoverable', True)}`"
                    )
                    st.caption(item.get("message", ""))

        if result.get("resumable"):
            st.info(f"该运行具备恢复潜力，可从 `{result.get('last_successful_step', '-')}` 之后继续。")

        render_step_retrieval(steps_result.get("chapter_outline", {}), "流水线：细纲步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("write_chapter", {}), "流水线：写作步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("review_chapter", {}), "流水线：审阅步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("memory_update", {}), "流水线：记忆更新步骤使用的检索上下文")

    st.subheader("最近运行记录")
    run_ids = list_pipeline_runs(project_name, chapter_no)
    if not run_ids:
        st.caption("当前章节还没有运行记录。")
        return

    selected_run = st.selectbox("选择运行记录", options=run_ids, key=f"pipeline_run_select_{chapter_no}")
    if selected_run:
        run_content = load_pipeline_run(project_name, selected_run)
        if run_content.strip():
            run_data = json.loads(run_content)
            st.caption(
                f"run_id={run_data.get('run_id', '-')} / started_at={run_data.get('started_at', '-')} / finished_at={run_data.get('finished_at', '-')} / resumable={run_data.get('resumable', False)}"
            )
            if run_data.get("halted"):
                st.warning(f"halt_reason={run_data.get('halt_reason', '-')}")
            transitions = run_data.get("transition_log", [])
            if transitions:
                with st.expander("该运行的状态迁移记录", expanded=False):
                    for index, item in enumerate(transitions, start=1):
                        st.markdown(
                            f"{index}. `{item.get('from_step', '-')}` -> `{item.get('to_step', '-')}` / {item.get('timestamp', '-')}"
                        )
                        if item.get("reason"):
                            st.caption(item.get("reason"))
            workflow_errors = run_data.get("errors", [])
            if workflow_errors:
                with st.expander("该运行的错误记录", expanded=False):
                    for index, item in enumerate(workflow_errors, start=1):
                        st.markdown(
                            f"{index}. step=`{item.get('step_name', '-')}` / type=`{item.get('error_type', 'unknown')}` / recoverable=`{item.get('recoverable', True)}`"
                        )
                        st.caption(item.get("message", ""))
            render_step_json_expander("运行记录状态对象", run_data)


def render_analysis_page(project_name: str):
    st.subheader("一致性分析")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="analysis_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    chapter_text_key = f"analysis_chapter_text_{chapter_no}"
    chapter_text = st.text_area(
        "待分析正文",
        value=existing_chapter,
        height=400,
        key=chapter_text_key
    )

    analysis_options = {
        "consistency": ("总一致性检查", run_consistency_check),
        "characters": ("角色分析", analyze_characters),
        "timeline": ("时间线分析", analyze_timeline),
        "foreshadowing": ("伏笔分析", analyze_foreshadowing),
    }

    selected_type = st.selectbox(
        "分析类型",
        options=list(analysis_options.keys()),
        format_func=lambda key: analysis_options[key][0],
        key="analysis_type"
    )

    report_text_key = f"analysis_result_text_{selected_type}_{chapter_no}"
    existing_report = load_analysis_report(project_name, selected_type, chapter_no)
    step_state_key = f"analysis_step_{selected_type}_{chapter_no}"

    if st.button("执行分析"):
        try:
            label, handler = analysis_options[selected_type]
            with st.spinner(f"正在生成{label}..."):
                result = handler(project_name, chapter_no, chapter_text)
            report = result.get("data", {}).get("report_markdown", "")
            st.session_state[f"analysis_{selected_type}_{chapter_no}"] = report
            st.session_state[report_text_key] = report
            st.session_state[step_state_key] = result
            st.rerun()
        except Exception as exc:
            st.error(f"执行分析失败：{exc}")

    report_text = st.text_area(
        "分析结果",
        value=st.session_state.get(f"analysis_{selected_type}_{chapter_no}", existing_report),
        height=450,
        key=report_text_key
    )

    if report_text:
        st.markdown(report_text)

    analysis_step = st.session_state.get(step_state_key, {})
    analysis_data = analysis_step.get("data", {}).get("analysis") or {}
    render_step_json_expander("结构化分析结果", analysis_data)
    render_step_validation(analysis_step)
    render_step_retrieval(
        analysis_step,
        "本次分析使用的检索上下文",
        get_retrieval_trace(f"analysis:{selected_type}:{project_name}:{chapter_no}")
    )


def render_retrieval_hits_block(hits: list[dict], title: str):
    if not hits:
        return

    with st.expander(title, expanded=False):
        grouped = {"project": {}, "canon": {}, "reference": {}}
        for hit in hits:
            chunk = hit.get("chunk", {})
            scope = chunk.get("scope", "project") or "project"
            source_type = chunk.get("source_type", "unknown") or "unknown"
            grouped.setdefault(scope, {}).setdefault(source_type, []).append(hit)

        scope_labels = {
            "project": "Project Sources",
            "canon": "Canon Sources",
            "reference": "Reference Sources",
        }

        hit_index = 1
        for scope in ["project", "canon", "reference"]:
            source_groups = grouped.get(scope, {})
            if not source_groups:
                continue
            st.markdown(f"## {scope_labels.get(scope, scope.title())}")
            for source_type, source_hits in source_groups.items():
                st.markdown(f"### {source_type}")
                for hit in source_hits:
                    chunk = hit.get("chunk", {})
                    st.markdown(
                        f"#### [{hit_index}] mode={hit.get('retrieval_mode', 'lexical')} / score={hit.get('score', 0):.2f}"
                    )
                    if chunk.get("title"):
                        st.caption(chunk.get("title"))
                    matched_terms = hit.get("matched_terms", [])
                    authority = chunk.get("metadata", {}).get("authority", "unknown")
                    if matched_terms:
                        st.caption(f"matched: {', '.join(matched_terms)}")
                    st.caption(
                        f"authority={authority} / lexical={hit.get('lexical_score', 0):.2f} / semantic={hit.get('semantic_score', 0):.2f} / source={chunk.get('path', '-') }"
                    )
                    st.write(chunk.get("content", ""))
                    hit_index += 1

        potential_conflicts = detect_potential_conflicts(hits)
        if potential_conflicts:
            st.markdown("## Potential Conflicts")
            for index, conflict in enumerate(potential_conflicts, start=1):
                shared_terms = ", ".join(conflict.get("shared_terms", [])) or "(无)"
                project_chunk = conflict.get("project_hit", {}).get("chunk", {})
                external_chunk = conflict.get("external_hit", {}).get("chunk", {})
                project_authority = conflict.get("project_authority", project_chunk.get("metadata", {}).get("authority", "project"))
                external_authority = conflict.get("external_authority", external_chunk.get("metadata", {}).get("authority", "unknown"))
                severity = conflict.get("severity", "low")
                rationale = conflict.get("rationale", "")
                st.markdown(f"### [{index}] severity={severity} / shared_terms={shared_terms}")
                st.caption(
                    f"project: {project_chunk.get('source_type', 'unknown')} / {project_chunk.get('title', 'untitled')} / authority={project_authority}"
                )
                st.caption(
                    f"external: {external_chunk.get('scope', 'reference')} / {external_chunk.get('source_type', 'unknown')} / {external_chunk.get('title', 'untitled')} / authority={external_authority}"
                )
                if rationale:
                    st.caption(f"rationale: {rationale}")


def render_retrieval_page(project_name: str):
    st.subheader("RAG 检索中心")
    st.caption("管理项目内外资料索引，并预览当前检索结果。")

    source_type_options = {
        "external_source": "通用资料",
        "external_character_sheet": "角色资料",
        "external_location_sheet": "地点资料",
        "external_organization_sheet": "组织资料",
        "external_timeline_note": "时间线资料",
        "external_canon_event": "原作事件",
        "external_world_rule": "世界规则",
        "external_artifact_note": "道具资料",
    }

    def _import_organized_reference_entries(organized_result: dict, scope: str, authority: str, origin: str):
        entries = organized_result.get("entries", [])
        imported = 0
        for index, entry in enumerate(entries, start=1):
            payload = build_structured_external_source_payload(
                source_type=entry.get("source_type", "external_source"),
                scope=scope,
                title=entry.get("title", f"entry_{index}"),
                summary=entry.get("summary", ""),
                content=entry.get("content", ""),
                tags=entry.get("tags", []),
                metadata={
                    "authority": authority,
                    "source_origin": origin,
                    "organized_from_reference": True,
                },
                extra_fields=entry.get("extra_fields", {}),
            )
            entry_name = f"{organized_result.get('source_title', 'reference')}_{index:02d}"
            ingest_external_source_file(project_name, entry_name, json.dumps(payload, ensure_ascii=False, indent=2))
            imported += 1
        if imported:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        return imported

    try:
        manifest = load_retrieval_index(project_name)
        st.caption(
            f"当前索引：{manifest.document_count} documents / {manifest.chunk_count} chunks / built at {manifest.built_at} / embedding={'on' if manifest.embedding_enabled else 'off'} / model={manifest.embedding_model or '-'}"
        )
    except Exception as exc:
        manifest = None
        st.warning(f"索引读取失败：{exc}")

    col1, col2 = st.columns(2)
    if col1.button("重建检索索引"):
        with st.spinner("正在重建索引..."):
            manifest = rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(
            f"索引已重建：{manifest.document_count} documents / {manifest.chunk_count} chunks / embedding={'on' if manifest.embedding_enabled else 'off'}"
        )
        st.rerun()

    source_dir = retrieval_sources_path(project_name)
    col2.caption(f"外部资料目录：`{source_dir}`")

    with st.expander("管理已导入资料", expanded=False):
        existing_source_files = list_retrieval_source_files(project_name)
        if not existing_source_files:
            st.caption("当前没有已导入的外部资料文件。")
        else:
            selected_source_file = st.selectbox(
                "选择要删除的资料文件",
                options=existing_source_files,
                key="retrieval_source_delete_target"
            )
            st.caption("删除后会自动重建检索索引。")
            if st.button("删除所选资料"):
                try:
                    deleted = delete_retrieval_source_file(project_name, selected_source_file)
                    if deleted:
                        rebuild_retrieval_assets(project_name, build_vectors=True)
                        st.success(f"已删除资料：{selected_source_file}")
                        st.rerun()
                    else:
                        st.warning("目标资料不存在，可能已被删除。")
                except Exception as exc:
                    st.error(f"删除资料失败：{exc}")

    with st.expander("添加外部资料", expanded=False):
        source_name = st.text_input("资料名称", key="retrieval_source_name")
        source_scope = st.selectbox("资料范围", options=["reference", "canon"], key="retrieval_source_scope")
        source_authority = st.selectbox(
            "资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=1,
            key="retrieval_source_authority"
        )
        source_origin = st.text_input("来源标识/链接（可选）", key="retrieval_source_origin")
        source_type = st.selectbox(
            "资料模板",
            options=list(source_type_options.keys()),
            format_func=lambda key: source_type_options[key],
            key="retrieval_source_type"
        )
        source_title = st.text_input("显示标题（可选）", key="retrieval_source_title")
        source_summary = st.text_area("资料摘要（可选）", height=100, key="retrieval_source_summary")
        source_tags = st.text_input("标签（逗号分隔，可选）", key="retrieval_source_tags")
        source_content = st.text_area("资料正文", height=220, key="retrieval_source_content")

        col_a, col_b = st.columns(2)
        extra_field_1_label = col_a.text_input("扩展字段1名称（可选）", key="retrieval_extra_label_1")
        extra_field_1_value = col_a.text_area("扩展字段1内容", height=90, key="retrieval_extra_value_1")
        extra_field_2_label = col_b.text_input("扩展字段2名称（可选）", key="retrieval_extra_label_2")
        extra_field_2_value = col_b.text_area("扩展字段2内容", height=90, key="retrieval_extra_value_2")

        if st.button("保存外部资料"):
            if not source_name.strip() or not source_content.strip():
                st.error("资料名称和资料正文不能为空。")
            else:
                tags = [item.strip() for item in source_tags.split(",") if item.strip()]
                extra_fields = {}
                if extra_field_1_label.strip() and extra_field_1_value.strip():
                    extra_fields[extra_field_1_label.strip()] = extra_field_1_value.strip()
                if extra_field_2_label.strip() and extra_field_2_value.strip():
                    extra_fields[extra_field_2_label.strip()] = extra_field_2_value.strip()

                payload = build_structured_external_source_payload(
                    source_type=source_type,
                    scope=source_scope,
                    title=source_title.strip() or source_name.strip(),
                    summary=source_summary,
                    content=source_content,
                    tags=tags,
                    metadata={
                        "added_from_ui": True,
                        "template": source_type,
                        "authority": source_authority,
                        "source_origin": source_origin.strip(),
                    },
                    extra_fields=extra_fields,
                )
                ingest_external_source_file(project_name, source_name, json.dumps(payload, ensure_ascii=False, indent=2))
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success("外部资料已保存并重建索引。")
                st.rerun()

    with st.expander("整理粘贴资料并导入", expanded=False):
        paste_title = st.text_input("资料标题", key="organized_reference_title")
        paste_scope = st.selectbox("资料范围", options=["canon", "reference"], key="organized_reference_scope")
        paste_authority = st.selectbox(
            "资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=1,
            key="organized_reference_authority"
        )
        paste_origin = st.text_input("来源说明（可选）", key="organized_reference_origin")
        paste_text = st.text_area("粘贴原始资料", height=240, key="organized_reference_text")

        if st.button("整理粘贴资料"):
            if not paste_text.strip():
                st.error("请先粘贴原始资料。")
            else:
                try:
                    result = organize_reference_text(project_name, paste_title, paste_text)
                    st.session_state["organized_reference_result"] = result
                except Exception as exc:
                    st.error(f"整理失败：{exc}")

        organized_result = st.session_state.get("organized_reference_result", {})
        organized_payload = organized_result.get("data", {}).get("organized_reference", {})
        if organized_payload:
            st.markdown(organized_result.get("data", {}).get("report_markdown", ""))
            render_step_validation(organized_result)
            render_step_json_expander("整理结果 JSON", organized_payload)
            if st.button("将整理结果导入检索库"):
                imported = _import_organized_reference_entries(organized_payload, paste_scope, paste_authority, paste_origin)
                st.success(f"已导入 {imported} 条资料并重建索引。")
                st.rerun()

    with st.expander("从 URL 抓取并整理资料", expanded=False):
        url_value = st.text_input("页面 URL", key="reference_url_input")
        parsed_url = urlparse(url_value.strip()) if url_value.strip() else None
        default_url_title = parsed_url.netloc if parsed_url and parsed_url.netloc else ""
        url_title = st.text_input("页面标题（可选）", value=default_url_title, key="reference_url_title")
        url_scope = st.selectbox("URL 资料范围", options=["canon", "reference"], key="reference_url_scope")
        url_authority = st.selectbox(
            "URL 资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=0,
            key="reference_url_authority"
        )

        if st.button("抓取并整理 URL 资料"):
            if not url_value.strip():
                st.error("URL 不能为空。")
            else:
                try:
                    result = organize_reference_url(project_name, url_title or default_url_title or url_value.strip(), url_value.strip())
                    st.session_state["organized_reference_url_result"] = result
                except Exception as exc:
                    st.error(f"抓取或整理失败：{exc}")

        organized_url_result = st.session_state.get("organized_reference_url_result", {})
        organized_url_payload = organized_url_result.get("data", {}).get("organized_reference", {})
        if organized_url_payload:
            st.markdown(organized_url_result.get("data", {}).get("report_markdown", ""))
            render_step_validation(organized_url_result)
            render_step_json_expander("URL 整理结果 JSON", organized_url_payload)
            artifacts = organized_url_result.get("artifacts", {})
            if artifacts.get("source_url"):
                st.caption(f"source_url={artifacts.get('source_url')}")
            if st.button("将 URL 整理结果导入检索库"):
                imported = _import_organized_reference_entries(
                    organized_url_payload,
                    url_scope,
                    url_authority,
                    artifacts.get("source_url", url_value.strip()),
                )
                st.success(f"已导入 {imported} 条 URL 资料并重建索引。")
                st.rerun()

    if manifest and manifest.documents:
        with st.expander("索引来源预览", expanded=False):
            for doc in manifest.documents[:30]:
                st.markdown(f"- `{doc.source_type}` / `{doc.scope}` / `{doc.title or doc.doc_id}`")
            if len(manifest.documents) > 30:
                st.caption(f"仅显示前 30 项，共 {len(manifest.documents)} 项。")

    with st.expander("检索预览", expanded=True):
        query = st.text_area("检索查询", height=120, key="retrieval_query")
        top_k = st.slider("返回条数", min_value=1, max_value=12, value=6, key="retrieval_top_k")
        retrieval_mode = st.selectbox(
            "检索模式",
            options=["hybrid", "lexical", "semantic"],
            index=0,
            key="retrieval_mode"
        )
        scope_options = st.multiselect(
            "范围过滤",
            options=["project", "canon", "reference"],
            default=["project", "canon", "reference"],
            key="retrieval_scope_filter"
        )
        if st.button("执行检索"):
            try:
                hits = retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    retrieval_mode=retrieval_mode,
                )
                st.session_state["retrieval_hits"] = [hit.model_dump() for hit in hits]
            except Exception as exc:
                st.error(f"检索失败：{exc}")

        for hit in st.session_state.get("retrieval_hits", []):
            chunk = hit.get("chunk", {})
            st.markdown(
                f"### {chunk.get('source_type', 'unknown')} / {chunk.get('scope', 'project')} / mode={hit.get('retrieval_mode', 'lexical')} / score={hit.get('score', 0):.2f}"
            )
            if chunk.get("title"):
                st.caption(chunk.get("title"))
            st.write(chunk.get("content", ""))
            matched_terms = hit.get("matched_terms", [])
            if matched_terms:
                st.caption(f"matched: {', '.join(matched_terms)}")
            st.caption(
                f"lexical={hit.get('lexical_score', 0):.2f} / semantic={hit.get('semantic_score', 0):.2f} / source={chunk.get('path', '-') }"
            )


st.set_page_config(page_title="NovelForge", layout="wide")
st.title("NovelForge：同人小说 Agent 工作台")

project_name = init_project_state()
projects = list_projects()
render_sidebar(project_name, projects)

if project_name:
    memory = load_memory(project_name)
    st.caption(f"当前项目：`{project_name}`")
else:
    memory = None
    st.info("当前还没有项目。点击侧边栏“新建项目”开始创建。")

page = st.sidebar.radio(
    "项目管理",
    ["项目总览", "项目资源", "设定库", "交互规则", "RAG 检索", "生成大纲", "生成细纲", "写章节", "章节审阅", "一致性分析", "一键流水线", "文件预览"]
)

if not project_name:
    st.stop()
elif page == "项目总览":
    render_project_overview_page(project_name)
elif page == "项目资源":
    render_resource_management_page(project_name)
elif page == "设定库":
    render_memory_page(project_name, memory)
elif page == "交互规则":
    render_rules_page(project_name)
elif page == "RAG 检索":
    render_retrieval_page(project_name)
elif page == "生成大纲":
    render_outline_page(project_name)
elif page == "生成细纲":
    render_chapter_outline_page(project_name)
elif page == "写章节":
    render_chapter_page(project_name)
elif page == "章节审阅":
    render_review_page(project_name)
elif page == "一致性分析":
    render_analysis_page(project_name)
elif page == "一键流水线":
    render_pipeline_page(project_name)
elif page == "文件预览":
    render_project_files_page(project_name)
