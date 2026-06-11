import json

import streamlit as st

from memory import (
    load_analysis_report,
    load_global_rules,
    list_projects,
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
)
from skills import (
    analyze_characters,
    analyze_foreshadowing,
    analyze_timeline,
    compact_memory,
    generate_chapter_outline,
    generate_outline,
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


def init_project_state() -> str:
    projects = list_projects()
    default_project = st.session_state.get("project_name") or (projects[0] if projects else "my_fanfic")

    project_name = st.sidebar.text_input("项目名", value=default_project).strip()
    if not project_name:
        project_name = default_project

    st.session_state["project_name"] = project_name
    return project_name


def render_sidebar(project_name: str):
    projects = list_projects()
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


def render_memory_page(project_name: str, memory: dict):
    st.subheader("当前设定库")

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
    user_idea = st.text_area("你的小说想法", height=200)

    if st.button("生成全书大纲"):
        outline = generate_outline(project_name, user_idea)
        st.session_state["outline"] = outline

    outline_text = st.text_area(
        "大纲内容",
        value=st.session_state.get("outline", existing_outline),
        height=500
    )

    if st.button("保存大纲"):
        save_outline(project_name, outline_text)
        st.success("大纲已保存")


def render_chapter_outline_page(project_name: str):
    st.subheader("章节细纲")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    requirement = st.text_area("本章要求", height=200)

    if st.button("生成章节细纲"):
        outline = generate_chapter_outline(project_name, chapter_no, requirement)
        st.session_state[f"chapter_outline_{chapter_no}"] = outline

    outline_text = st.text_area(
        "章节细纲内容",
        value=st.session_state.get(f"chapter_outline_{chapter_no}", existing_outline),
        height=500
    )

    if st.button("保存章节细纲"):
        save_chapter_outline(project_name, chapter_no, outline_text)
        st.success(f"第 {chapter_no} 章细纲已保存")


def render_chapter_page(project_name: str):
    st.subheader("章节正文")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no)

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
        chapter = write_chapter(project_name, chapter_no, chapter_outline, word_count)
        st.session_state[f"chapter_{chapter_no}"] = chapter

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
        st.code(result, language="json")


def render_review_page(project_name: str):
    st.subheader("章节审阅")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="review_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    review_text_key = f"review_result_text_{chapter_no}"
    chapter_text_key = f"review_chapter_text_{chapter_no}"

    existing_review = load_review(project_name, chapter_no)
    existing_review_json = load_review_json(project_name, chapter_no) or {}

    chapter_text = st.text_area(
        "待审阅正文",
        value=existing_chapter,
        height=450,
        key=chapter_text_key
    )

    if st.button("生成审阅意见"):
        try:
            review = review_chapter(project_name, chapter_no, chapter_text)
            st.session_state[f"review_{chapter_no}"] = review
            st.session_state[review_text_key] = review
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
        st.success("流水线完成")

        errors = result.get("errors", {})

        st.subheader("执行状态")
        steps = [
            ("章节细纲", "chapter_outline", True),
            ("写作正文", "write_chapter", result.get("chapter_outline") is not None),
            ("审阅", "review_chapter", result.get("review_markdown") is not None),
            ("更新记忆", "memory_update", result.get("memory_update_result") is not None),
        ]
        for label, key, success in steps:
            if key in errors:
                st.error(f"{label}：{errors[key]}")
            elif success:
                st.success(f"{label}：完成")
            else:
                st.info(f"{label}：已跳过（前置步骤未完成）")

        st.subheader("结果预览")
        with st.expander("章节细纲", expanded=True):
            st.markdown(result.get("chapter_outline", "") or "（未生成）")
        with st.expander("章节正文", expanded=True):
            st.markdown(result.get("chapter", "") or "（未生成）")
        with st.expander("审阅报告", expanded=True):
            st.markdown(result.get("review_markdown", "") or "（未生成）")
        review = result.get("review") or {}
        if review:
            st.caption("结构化审阅状态")
            cols = st.columns(3)
            cols[0].metric("Status", review.get("status", "-"))
            cols[1].metric("Issues", len(review.get("issues", [])))
            cols[2].metric("Strengths", len(review.get("strengths", [])))
            with st.expander("审阅 JSON", expanded=False):
                st.code(json.dumps(review, ensure_ascii=False, indent=2), language="json")
        with st.expander("记忆更新结果", expanded=True):
            st.code(json.dumps(result.get("memory_update_result", {}), ensure_ascii=False, indent=2), language="json")


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

    if st.button("执行分析"):
        try:
            label, handler = analysis_options[selected_type]
            with st.spinner(f"正在生成{label}..."):
                report = handler(project_name, chapter_no, chapter_text)
            st.session_state[f"analysis_{selected_type}_{chapter_no}"] = report
            st.session_state[report_text_key] = report
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


st.set_page_config(page_title="NovelForge", layout="wide")
st.title("NovelForge：同人小说 Agent 工作台")

project_name = init_project_state()
render_sidebar(project_name)
memory = load_memory(project_name)

st.caption(f"当前项目：`{project_name}`")

page = st.sidebar.radio(
    "功能",
    ["设定库", "交互规则", "生成大纲", "生成细纲", "写章节", "章节审阅", "一致性分析", "一键流水线", "文件预览"]
)

if page == "设定库":
    render_memory_page(project_name, memory)
elif page == "交互规则":
    render_rules_page(project_name)
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
