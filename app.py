import json

import streamlit as st

from memory import (
    list_projects,
    load_chapter,
    load_chapter_outline,
    load_memory,
    load_outline,
    save_chapter,
    save_chapter_outline,
    save_memory,
    save_outline,
)
from skills import (
    generate_chapter_outline,
    generate_outline,
    update_memory_from_chapter,
    write_chapter,
)


def format_memory(memory: dict) -> str:
    return json.dumps(memory, ensure_ascii=False, indent=2)


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

    memory_text = st.text_area(
        "编辑 memory.json",
        value=format_memory(memory),
        height=500
    )

    if st.button("保存设定"):
        try:
            new_memory = json.loads(memory_text)
            save_memory(project_name, new_memory)
            st.success("已保存")
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

    if st.button("写正文"):
        chapter = write_chapter(project_name, chapter_no, chapter_outline)
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


def render_project_files_page(project_name: str):
    st.subheader("项目文件预览")

    outline = load_outline(project_name)
    if outline:
        with st.expander("outline.md", expanded=True):
            st.markdown(outline)

    chapter_no = st.number_input("预览章节编号", min_value=1, value=1, key="preview_chapter_no")
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    chapter = load_chapter(project_name, chapter_no)

    if chapter_outline:
        with st.expander(f"chapter_outlines/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter_outline)

    if chapter:
        with st.expander(f"chapters/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter)


st.set_page_config(page_title="NovelForge", layout="wide")
st.title("NovelForge：同人小说 Agent 工作台")

project_name = init_project_state()
render_sidebar(project_name)
memory = load_memory(project_name)

st.caption(f"当前项目：`{project_name}`")

page = st.sidebar.radio(
    "功能",
    ["设定库", "生成大纲", "生成细纲", "写章节", "文件预览"]
)

if page == "设定库":
    render_memory_page(project_name, memory)
elif page == "生成大纲":
    render_outline_page(project_name)
elif page == "生成细纲":
    render_chapter_outline_page(project_name)
elif page == "写章节":
    render_chapter_page(project_name)
elif page == "文件预览":
    render_project_files_page(project_name)
