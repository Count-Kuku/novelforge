"""Generation rules management page."""
from __future__ import annotations

import streamlit as st

from memory import (
    add_rule_conflict_resolution,
    delete_rule_conflict_resolution,
    load_global_rules,
    load_project_rules,
    load_rule_conflict_resolutions,
    load_story_rules,
    list_stories,
    merge_global_rules_to_project,
    merge_global_rules_to_story,
    merge_project_rules_to_global,
    merge_project_rules_to_story,
    merge_story_rules_to_global,
    merge_story_rules_to_project,
    save_global_rules,
    save_project_rules,
    save_story_rules,
)
from skills import save_rule_text

RULE_SCOPE_OPTIONS = {
    "all": "通用",
    "outline": "全书大纲",
    "chapter_outline": "章节细纲",
    "write": "正文写作",
    "review": "章节审阅",
    "setting_extraction": "设定提炼",
}

def _render_rule_editor(title: str, storage_key: str, rules: dict) -> dict:
    st.subheader(title)
    updated = {}
    for scope, label in RULE_SCOPE_OPTIONS.items():
        updated[scope] = [line.strip() for line in st.text_area(
            f"{label}规则（每行一条）",
            value="\n".join(rules.get(scope, [])),
            height=120,
            key=f"{storage_key}_{scope}",
            help="每行写一条必须长期遵守的硬约束。可切换的文风、节奏和描写偏好建议放到提示词选项。",
        ).split("\n") if line.strip()]
    return updated

def _render_rules_copy_tools(project_name: str, story_id: str, current_story_name: str):
    st.markdown("#### 规则复制与导入")
    st.caption("用于在项目规则和故事规则之间同步长期生成约束。项目规则会被所有故事继承，故事规则只覆盖当前故事。")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("从项目导入规则", use_container_width=True):
            merge_project_rules_to_story(project_name, story_id)
            st.success(f"已将项目规则复制到 {current_story_name}")
            st.rerun()

    with col_b:
        other_stories = [s for s in list_stories(project_name) if s.get("story_id") != story_id]
        if other_stories:
            selected_story = st.selectbox(
                "从其他故事导入",
                options=[s.get("story_id") for s in other_stories],
                format_func=lambda sid: next((s.get("name", sid) for s in other_stories if s.get("story_id") == sid), sid),
                key=f"rules_import_story_{story_id}",
                label_visibility="collapsed",
            )
            if st.button("导入故事规则", use_container_width=True, key=f"import_rules_{story_id}"):
                save_story_rules(project_name, story_id, load_story_rules(project_name, selected_story))
                imported_name = next((s.get("name", selected_story) for s in other_stories if s.get("story_id") == selected_story), selected_story)
                st.success(f"已从 {imported_name} 导入规则")
                st.rerun()
        else:
            st.caption("没有其他故事可导入。")

    with col_c:
        if st.button("设为项目默认规则", use_container_width=True):
            merge_story_rules_to_project(project_name, story_id)
            st.success(f"已将 {current_story_name} 的规则合并为项目默认规则")
            st.rerun()

    with st.expander("全局规则同步", expanded=False):
        st.caption("全局规则会影响所有项目。建议只放跨项目稳定偏好，例如输出语言、审阅标准、文风禁忌；具体角色、世界观和剧情要求更适合留在项目或故事规则。")
        global_col_a, global_col_b = st.columns(2)
        with global_col_a:
            if st.button("全局规则合并到项目", use_container_width=True):
                merge_global_rules_to_project(project_name)
                st.success("已将全局规则合并到项目规则")
                st.rerun()
            if st.button("项目规则合并到全局", use_container_width=True):
                merge_project_rules_to_global(project_name)
                st.success("已将项目规则合并到全局规则")
                st.rerun()
        with global_col_b:
            if st.button("全局规则合并到当前故事", use_container_width=True):
                merge_global_rules_to_story(project_name, story_id)
                st.success(f"已将全局规则合并到 {current_story_name}")
                st.rerun()
            if st.button("当前故事规则合并到全局", use_container_width=True):
                merge_story_rules_to_global(project_name, story_id)
                st.success(f"已将 {current_story_name} 的规则合并到全局规则")
                st.rerun()

def _render_rule_conflict_resolution_tools(project_name: str, story_id: str, current_story_name: str):
    st.markdown("#### 冲突解决机制")
    st.caption("默认优先级：人工裁决 > 故事规则 > 项目规则 > 全局规则；同层级内，当前能力的专用规则优先于通用规则。")

    with st.expander("人工冲突裁决", expanded=False):
        layer_options = {
            "当前故事": "story",
            "当前项目": "project",
            "全局": "global",
        }
        col_scope, col_layer = st.columns(2)
        scope_label = col_scope.selectbox(
            "适用能力",
            options=list(RULE_SCOPE_OPTIONS.values()),
            key=f"rule_conflict_scope_{story_id}",
        )
        layer_label = col_layer.selectbox(
            "裁决保存位置",
            options=list(layer_options.keys()),
            key=f"rule_conflict_layer_{story_id}",
        )
        title = st.text_input(
            "裁决标题",
            key=f"rule_conflict_title_{story_id}",
            placeholder="例如：节奏规则冲突、视角规则冲突",
        )
        decision = st.text_area(
            "裁决内容",
            height=100,
            key=f"rule_conflict_decision_{story_id}",
            placeholder="例如：当“快节奏推进”和“日常慢热”冲突时，当前故事优先日常慢热，但章节结尾保留推进钩子。",
        )
        if st.button("保存人工裁决", key=f"save_rule_conflict_{story_id}", use_container_width=True):
            if not decision.strip():
                st.warning("请先填写裁决内容。")
            else:
                scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
                layer = layer_options[layer_label]
                add_rule_conflict_resolution(project_name, layer, scope, title, decision, story_id=story_id)
                st.success("已保存人工冲突裁决")
                st.rerun()

        st.markdown("##### 已保存裁决")
        layer_display = [
            ("故事", "story", current_story_name),
            ("项目", "project", project_name),
            ("全局", "global", "所有项目"),
        ]
        has_items = False
        for layer_label_text, layer, owner in layer_display:
            items = load_rule_conflict_resolutions(project_name, layer, story_id=story_id)
            if not items:
                continue
            has_items = True
            st.markdown(f"**{layer_label_text}裁决 · {owner}**")
            for item in items:
                scope_name = RULE_SCOPE_OPTIONS.get(item.get("scope", "all"), item.get("scope", "all"))
                row_cols = st.columns([4, 1])
                with row_cols[0]:
                    st.caption(f"{scope_name} / {item.get('title', '')}")
                    st.write(item.get("decision", ""))
                with row_cols[1]:
                    if st.button("删除", key=f"delete_rule_conflict_{layer}_{item.get('id')}", use_container_width=True):
                        delete_rule_conflict_resolution(project_name, layer, item.get("id", ""), story_id=story_id)
                        st.success("已删除裁决")
                        st.rerun()
        if not has_items:
            st.caption("暂无人工裁决。")

def render_rules_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break

    st.subheader("生成规则（长期硬约束）")
    st.caption("把这里当成“模型不能违背的边界”。它适合保存角色底线、世界观事实、禁忌、视角限制、一致性要求等长期约束；如果只是某次想换文风或节奏，请放到提示词选项。规则生效优先级：故事 > 项目 > 全局。")
    st.info("判断标准：这条要求被违反会导致设定错误、剧情矛盾或越过底线，就放到生成规则；只是影响表达口味，就放到提示词选项。")

    with st.expander("快速记录新要求", expanded=True):
        rule_text = st.text_area(
            "输入必须长期遵守的要求",
            height=140,
            key="rule_capture_text",
            placeholder="例如：主角不能主动伤害无辜者；全文保持第三人称有限视角；魔法不能复活已彻底死亡的人。",
            help="适合放硬约束、禁忌、世界观边界和一致性要求。",
        )
        col1, col2, col3 = st.columns(3)
        scope_label = col1.selectbox("适用能力", options=list(RULE_SCOPE_OPTIONS.values()), key="rule_capture_scope")
        target_label = col2.selectbox("保存位置", options=["故事规则", "项目规则", "全局规则"], key="rule_capture_target")

        if st.button("保存要求为规则"):
            scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
            target = "story" if target_label == "故事规则" else ("project" if target_label == "项目规则" else "global")
            try:
                result = save_rule_text(project_name, scope, target, rule_text, story_id=story_id)
                if result.get("status") == "saved":
                    st.success(f"已保存到{target_label} / {scope_label}")
                    st.rerun()
                else:
                    st.warning("未提取到有效规则。")
            except Exception as exc:
                st.error(f"保存失败：{exc}")

    _render_rules_copy_tools(project_name, story_id, current_story_name)
    _render_rule_conflict_resolution_tools(project_name, story_id, current_story_name)
    st.divider()

    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    story_rules = load_story_rules(project_name, story_id)

    tab1, tab2, tab3 = st.tabs(["故事规则", "项目规则", "全局规则"])

    with tab1:
        updated_story_rules = _render_rule_editor(f"故事规则：{current_story_name}", f"story_rules_{story_id}", story_rules)
        if st.button("保存故事规则"):
            save_story_rules(project_name, story_id, updated_story_rules)
            st.success(f"已保存 {current_story_name} 的故事规则")

    with tab2:
        updated_project_rules = _render_rule_editor(f"项目规则：{project_name}", "project_rules", project_rules)
        if st.button("保存项目规则"):
            save_project_rules(project_name, updated_project_rules)
            st.success("项目规则已保存")

    with tab3:
        updated_global_rules = _render_rule_editor("全局规则", "global_rules", global_rules)
        if st.button("保存全局规则"):
            save_global_rules(updated_global_rules)
            st.success("全局规则已保存")

