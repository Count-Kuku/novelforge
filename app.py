import json

import streamlit as st

from memory import (
    list_projects,
    load_chapter,
    load_chapter_outline,
    load_memory,
    load_outline,
    load_review,
    load_review_json,
    save_chapter,
    save_chapter_outline,
    save_memory,
    save_outline,
)
from skills import (
    compact_memory,
    generate_chapter_outline,
    generate_outline,
    review_chapter,
    pipeline_plan_write_review_update,
    update_memory_from_chapter,
    write_chapter,
)


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
        "目标字数（如 2500-3500）",
        value="2500-3500"
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
    existing_review = load_review(project_name, chapter_no)
    existing_review_json = load_review_json(project_name, chapter_no) or {}

    chapter_text = st.text_area(
        "待审阅正文",
        value=existing_chapter,
        height=450,
        key=f"review_chapter_text_{chapter_no}"
    )

    if st.button("生成审阅意见"):
        review = review_chapter(project_name, chapter_no, chapter_text)
        st.session_state[f"review_{chapter_no}"] = review

    review_text = st.text_area(
        "审阅结果",
        value=st.session_state.get(f"review_{chapter_no}", existing_review),
        height=450,
        key=f"review_result_text_{chapter_no}"
    )

    if review_text:
        st.markdown(review_text)

    if existing_review_json:
        st.caption("结构化审阅状态")
        cols = st.columns(3)
        cols[0].metric("Status", existing_review_json.get("status", "-"))
        cols[1].metric("Issues", len(existing_review_json.get("issues", [])))
        cols[2].metric("Strengths", len(existing_review_json.get("strengths", [])))


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


st.set_page_config(page_title="NovelForge", layout="wide")
st.title("NovelForge：同人小说 Agent 工作台")

project_name = init_project_state()
render_sidebar(project_name)
memory = load_memory(project_name)

st.caption(f"当前项目：`{project_name}`")

page = st.sidebar.radio(
    "功能",
    ["设定库", "生成大纲", "生成细纲", "写章节", "章节审阅", "一键流水线", "文件预览"]
)

if page == "设定库":
    render_memory_page(project_name, memory)
elif page == "生成大纲":
    render_outline_page(project_name)
elif page == "生成细纲":
    render_chapter_outline_page(project_name)
elif page == "写章节":
    render_chapter_page(project_name)
elif page == "章节審阅":
    render_review_page(project_name)
elif page == "一键流水线":
    render_pipeline_page(project_name)
elif page == "文件预览":
    render_project_files_page(project_name)
