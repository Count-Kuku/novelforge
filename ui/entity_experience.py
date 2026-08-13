"""Creator-facing live projections for characters, worlds, timelines and relationships."""

from __future__ import annotations

import html
import json
from uuid import uuid4

import streamlit as st

from novelforge.domain.knowledge_entities import (
    SETTING_ENTITY_CATEGORY_GROUPS,
    build_character_entity_cards,
    build_setting_entity_cards,
    timeline_item_sort_key,
)
from novelforge.services.memory import (
    load_knowledge_base,
    load_knowledge_category,
    load_knowledge_graph,
    load_knowledge_revisions,
    update_confirmed_knowledge_item_record,
    upsert_knowledge_category_item_record,
)
from ui.common import scoped_widget_key
from ui.knowledge_type_editor import render_typed_knowledge_fields
from ui.labels import label_knowledge_category
from ui.layout import render_empty_state, render_stat_strip


WORLD_CENTER_CATEGORIES = {
    "world_rules": "规则",
    "locations": "地点",
    "organizations": "组织",
    "abilities": "力量体系",
    "items": "物品",
    "constraints": "硬约束",
}


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def _status_meta(item: dict) -> tuple[str, str, str]:
    confidence = float(item.get("confidence") or 0.7)
    status = str(item.get("canon_status") or item.get("status") or "confirmed")
    if confidence < 0.45:
        return "高风险", "danger", f"置信度 {confidence:.2f}"
    if confidence < 0.7 or status in {"unknown", "pending", "mixed"}:
        return "需留意", "warning", f"{status} · {confidence:.2f}"
    return "已确认", "success", f"{status} · {confidence:.2f}"


def _render_badges(item: dict, *, revision_count: int = 0) -> None:
    label, tone, detail = _status_meta(item)
    badges = [
        f'<span class="nf-entity-badge nf-entity-{tone}">{html.escape(label)} · {html.escape(detail)}</span>'
    ]
    worldline = str(item.get("worldline_label") or item.get("worldline_id") or "通用")
    badges.append(f'<span class="nf-entity-badge">资料版本 · {html.escape(worldline)}</span>')
    if revision_count:
        badges.append(f'<span class="nf-entity-badge">修订 · {revision_count}</span>')
    st.markdown('<div class="nf-entity-badge-row">' + "".join(badges) + "</div>", unsafe_allow_html=True)


def _render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption("尚未绑定可展示的来源；可在知识详情中补充证据。")
        return
    chips = []
    for source in sources[:12]:
        title = str(source.get("title") or "未命名来源")
        origin = str(source.get("origin") or "")
        tooltip = f' title="{html.escape(origin)}"' if origin else ""
        chips.append(f'<span class="nf-entity-source"{tooltip}>↗ {html.escape(title)}</span>')
    st.markdown('<div class="nf-entity-source-row">' + "".join(chips) + "</div>", unsafe_allow_html=True)


def _render_fact_list(label: str, values: list[str], *, empty_text: str = "暂无") -> None:
    st.markdown(f"##### {label}")
    if values:
        st.markdown("\n".join(f"- {value}" for value in values[:12]))
    else:
        st.caption(empty_text)


def _knowledge_item_for_card(project_name: str, category: str, card: dict) -> dict:
    knowledge_id = str(card.get("primary_knowledge_id") or "")
    return next(
        (
            item for item in load_knowledge_category(project_name, category)
            if str(item.get("id") or item.get("knowledge_id") or "") == knowledge_id
        ),
        {},
    )


def _render_authoritative_editor(project_name: str, category: str, item: dict, scope: str) -> None:
    knowledge_id = str(item.get("id") or item.get("knowledge_id") or "")
    if not knowledge_id:
        return
    revisions = load_knowledge_revisions(project_name, knowledge_id)
    with st.expander(f"编辑权威知识 · 已有 {len(revisions)} 个修订", expanded=False):
        st.caption("保存后会生成新修订；角色卡、世界观卡、时间轴和关系图随即重新投影。")
        with st.form(scoped_widget_key("entity_authoritative_edit", project_name, scope, knowledge_id)):
            name = st.text_input("名称", value=str(item.get("name") or ""))
            summary = st.text_area("摘要", value=str(item.get("summary") or ""), height=120)
            typed_data = render_typed_knowledge_fields(category, item)
            reason = st.text_input("修订说明", value="从实体视图编辑")
            saved = st.form_submit_button("保存为新修订", type="primary", width="stretch")
        if saved:
            if not name.strip():
                st.error("名称不能为空。")
                return
            updated = {
                **item,
                "name": name.strip(),
                "summary": summary.strip(),
                "typed_data": typed_data,
                "schema_version": 2,
                "revision_reason": reason.strip() or "从实体视图编辑",
            }
            if update_confirmed_knowledge_item_record(
                project_name, category, knowledge_id, updated,
            ):
                st.success("权威知识已保存；所有聚合视图将使用新修订。")
                st.rerun()
            st.error("保存失败：知识可能已被其他窗口归档。")


def _render_character_center(project_name: str) -> None:
    cards = build_character_entity_cards(project_name)
    if not cards:
        render_empty_state("角色中心还是空的", "在知识条目中新增或确认角色，关系与事件会自动聚合到这里。")
        return
    keyword = st.text_input(
        "筛选角色", placeholder="名称、别名或摘要",
        key=scoped_widget_key("character_center_keyword", project_name),
    ).strip().casefold()
    filtered = [
        card for card in cards
        if not keyword or keyword in " ".join([
            str(card.get("name") or ""), str(card.get("summary") or ""),
            " ".join(card.get("aliases") or []),
        ]).casefold()
    ]
    if not filtered:
        render_empty_state("没有匹配角色", "清空筛选词，或确认角色名称与别名是否已保存。")
        return
    selected_id = st.selectbox(
        "选择角色", options=[str(card.get("id") or "") for card in filtered],
        format_func=lambda card_id: next(str(card.get("name") or card_id) for card in filtered if str(card.get("id") or "") == card_id),
        key=scoped_widget_key("character_center_selected", project_name),
    )
    card = next(card for card in filtered if str(card.get("id") or "") == selected_id)
    item = _knowledge_item_for_card(project_name, "characters", card)
    render_stat_strip([
        ("角色", len(cards)), ("关系", len(card.get("relationships", []))),
        ("能力", len(card.get("abilities", []))), ("道具", len(card.get("items", []))),
        ("参与事件", len(card.get("events", []))),
    ])
    st.markdown(f"### {card.get('name') or '未命名角色'}")
    _render_badges(item or card, revision_count=len(load_knowledge_revisions(project_name, str(card.get("primary_knowledge_id") or ""))))
    if card.get("summary"):
        st.write(card["summary"])
    profile = card.get("profile") if isinstance(card.get("profile"), dict) else {}
    if profile:
        st.dataframe([{"字段": key, "内容": value} for key, value in profile.items()], width="stretch", hide_index=True)
    left, right = st.columns(2)
    with left:
        _render_fact_list("关系", card.get("relationships", []))
        _render_fact_list("能力", card.get("abilities", []))
        _render_fact_list("道具", card.get("items", []))
    with right:
        _render_fact_list("参与事件", card.get("events", []))
        _render_fact_list("对白风格", card.get("dialogue_style", []))
        _render_fact_list("硬约束", card.get("constraints", []))
    st.markdown("##### 来源")
    _render_sources(card.get("sources", []))
    _render_authoritative_editor(project_name, "characters", item, "character")


def _render_world_center(project_name: str) -> None:
    cards = build_setting_entity_cards(project_name)
    if not cards:
        render_empty_state("世界观中心还是空的", "新增或确认规则、地点、组织、力量体系等正式知识后会自动出现。")
        return
    category_filter = st.multiselect(
        "设定类型", options=list(WORLD_CENTER_CATEGORIES), default=list(WORLD_CENTER_CATEGORIES),
        format_func=lambda value: WORLD_CENTER_CATEGORIES[value],
        key=scoped_widget_key("world_center_categories", project_name),
    )
    keyword = st.text_input(
        "筛选世界设定", placeholder="名称、摘要或标签",
        key=scoped_widget_key("world_center_keyword", project_name),
    ).strip().casefold()
    filtered = [
        card for card in cards
        if card.get("setting_type") in category_filter
        and (not keyword or keyword in " ".join([
            str(card.get("name") or ""), str(card.get("summary") or ""),
            " ".join(card.get("tags") or []),
        ]).casefold())
    ]
    if not filtered:
        render_empty_state("没有匹配设定", "调整类型或搜索词后再试。")
        return
    selected_id = st.selectbox(
        "选择设定", options=[str(card.get("id") or "") for card in filtered],
        format_func=lambda card_id: next(
            f"{WORLD_CENTER_CATEGORIES.get(str(card.get('setting_type')), card.get('setting_type'))} · {card.get('name')}"
            for card in filtered if str(card.get("id") or "") == card_id
        ),
        key=scoped_widget_key("world_center_selected", project_name),
    )
    card = next(card for card in filtered if str(card.get("id") or "") == selected_id)
    category = str(card.get("setting_type") or "world_rules")
    item = _knowledge_item_for_card(project_name, category, card)
    counts = {key: sum(1 for card in cards if card.get("setting_type") == key) for key in WORLD_CENTER_CATEGORIES}
    render_stat_strip([(label, counts[key]) for key, label in list(WORLD_CENTER_CATEGORIES.items())[:5]])
    st.markdown(f"### {card.get('name') or '未命名设定'}")
    _render_badges(item or card, revision_count=len(load_knowledge_revisions(project_name, str(card.get("primary_knowledge_id") or ""))))
    if card.get("summary"):
        st.write(card["summary"])
    profile = card.get("profile") if isinstance(card.get("profile"), dict) else {}
    if profile:
        st.dataframe([{"字段": key, "内容": value} for key, value in profile.items()], width="stretch", hide_index=True)
    left, right = st.columns(2)
    with left:
        _render_fact_list("规则与要点", card.get("rules", []))
        _render_fact_list("关联实体", card.get("related_entities", []))
    with right:
        _render_fact_list("相关事件", card.get("timeline", []))
        _render_fact_list("冲突", card.get("conflicts", []), empty_text="未发现明确冲突关系")
    st.markdown("##### 来源")
    _render_sources(card.get("sources", []))
    _render_authoritative_editor(project_name, category, item, "world")


def _timeline_row(item: dict) -> dict:
    typed = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
    return {
        "顺序": typed.get("order_hint") or "-",
        "时间": typed.get("time") or "未注明",
        "事件": item.get("name") or "未命名事件",
        "参与者": "、".join(_as_list(typed.get("participants"))),
        "地点": "、".join(_as_list(typed.get("locations"))),
        "结果/影响": "；".join(_as_list(typed.get("outcomes")))[:240],
        "状态": _status_meta(item)[0],
    }


def _render_timeline(project_name: str) -> None:
    events = [item for item in load_knowledge_category(project_name, "timeline_events") if isinstance(item, dict)]
    if not events:
        render_empty_state("时间轴还是空的", "新增或确认事件与时间线知识后，可以在这里排序和筛选。")
        return
    participants = sorted({value for item in events for value in _as_list((item.get("typed_data") or {}).get("participants"))})
    locations = sorted({value for item in events for value in _as_list((item.get("typed_data") or {}).get("locations"))})
    col_a, col_b, col_c = st.columns(3)
    selected_people = col_a.multiselect("参与者", participants, key=scoped_widget_key("timeline_people", project_name))
    selected_places = col_b.multiselect("地点", locations, key=scoped_widget_key("timeline_places", project_name))
    order = col_c.selectbox("排序", ["正序", "倒序", "新修订优先"], key=scoped_widget_key("timeline_sort", project_name))
    keyword = st.text_input("搜索事件", placeholder="事件、摘要、起因或结果", key=scoped_widget_key("timeline_keyword", project_name)).strip().casefold()
    filtered = []
    for item in events:
        typed = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
        people = _as_list(typed.get("participants"))
        places = _as_list(typed.get("locations"))
        if selected_people and not set(selected_people).intersection(people):
            continue
        if selected_places and not set(selected_places).intersection(places):
            continue
        if keyword and keyword not in json.dumps(item, ensure_ascii=False).casefold():
            continue
        filtered.append(item)
    if order == "新修订优先":
        filtered.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    else:
        filtered.sort(key=timeline_item_sort_key, reverse=order == "倒序")
    st.caption(f"显示 {len(filtered)} / {len(events)} 个事件")
    if not filtered:
        render_empty_state("没有匹配事件", "调整参与者、地点或关键词筛选。")
        return
    st.dataframe([_timeline_row(item) for item in filtered], width="stretch", hide_index=True)
    selected_id = st.selectbox(
        "查看并编辑事件", options=[str(item.get("id") or item.get("knowledge_id") or "") for item in filtered],
        format_func=lambda item_id: next(str(item.get("name") or item_id) for item in filtered if str(item.get("id") or item.get("knowledge_id") or "") == item_id),
        key=scoped_widget_key("timeline_selected", project_name),
    )
    item = next(item for item in filtered if str(item.get("id") or item.get("knowledge_id") or "") == selected_id)
    _render_badges(item, revision_count=len(load_knowledge_revisions(project_name, selected_id)))
    if item.get("summary"):
        st.write(item["summary"])
    _render_authoritative_editor(project_name, "timeline_events", item, "timeline")


def _graph_dot(graph: dict) -> str:
    def quote(value: str) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

    lines = ["digraph Knowledge {", "rankdir=LR;", 'graph [bgcolor="transparent", overlap=false];',
             'node [shape=box, style="rounded,filled", fillcolor="#edf4ff", color="#9bb7e8", fontname="Microsoft YaHei"];',
             'edge [color="#667085", fontname="Microsoft YaHei", fontsize=10];']
    edges = list(graph.get("edges") or [])[:80]
    node_ids = {str(edge.get("source_node_id")) for edge in edges} | {str(edge.get("target_node_id")) for edge in edges}
    for node in graph.get("nodes") or []:
        if str(node.get("node_id")) in node_ids:
            lines.append(f"{quote(node.get('node_id'))} [label={quote(node.get('name'))}];")
    for edge in edges:
        connector = "->"
        attrs = [f"label={quote(edge.get('relation_type') or '关联')}"]
        if edge.get("direction") in {"undirected", "bidirectional"}:
            attrs.append("dir=both" if edge.get("direction") == "bidirectional" else "dir=none")
        lines.append(f"{quote(edge.get('source_node_id'))} {connector} {quote(edge.get('target_node_id'))} [{', '.join(attrs)}];")
    lines.append("}")
    return "\n".join(lines)


def _render_relationship_editor(project_name: str, relationships: list[dict]) -> None:
    options = ["__new__"] + [str(item.get("id") or item.get("knowledge_id") or "") for item in relationships]
    selected = st.selectbox(
        "编辑关系", options=options,
        format_func=lambda item_id: "新增关系" if item_id == "__new__" else next(str(item.get("name") or item_id) for item in relationships if str(item.get("id") or item.get("knowledge_id") or "") == item_id),
        key=scoped_widget_key("relationship_editor_selected", project_name),
    )
    item = {} if selected == "__new__" else next(item for item in relationships if str(item.get("id") or item.get("knowledge_id") or "") == selected)
    typed = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
    with st.form(scoped_widget_key("relationship_editor", project_name, selected)):
        col_a, col_b = st.columns(2)
        subject = col_a.text_input("主体 *", value=str(typed.get("subject") or ""))
        object_name = col_b.text_input("客体 *", value=str(typed.get("object") or ""))
        relation_type = st.text_input("关系类型 *", value=str(typed.get("relation_type") or ""), placeholder="例如：盟友、师徒、敌对")
        direction = st.selectbox(
            "方向", options=["directed", "bidirectional", "undirected"],
            index=["directed", "bidirectional", "undirected"].index(str(typed.get("direction") or "directed")) if str(typed.get("direction") or "directed") in {"directed", "bidirectional", "undirected"} else 0,
            format_func=lambda value: {"directed": "主体指向客体", "bidirectional": "双向", "undirected": "无方向"}[value],
        )
        status = st.text_input("关系状态", value=str(typed.get("status") or "进行中"))
        summary = st.text_area("说明", value=str(item.get("summary") or ""), height=90)
        saved = st.form_submit_button("保存关系并更新关系图", type="primary", width="stretch")
    if not saved:
        return
    if not subject.strip() or not object_name.strip() or not relation_type.strip():
        st.error("主体、客体和关系类型不能为空。")
        return
    knowledge_id = selected if selected != "__new__" else f"relationships_{uuid4().hex}"
    payload = {
        **item,
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": "relationships",
        "name": f"{subject.strip()} — {relation_type.strip()} — {object_name.strip()}",
        "summary": summary.strip() or f"{subject.strip()}与{object_name.strip()}的关系为{relation_type.strip()}。",
        "typed_data": {"subject": subject.strip(), "object": object_name.strip(), "relation_type": relation_type.strip(), "direction": direction, "status": status.strip()},
        "schema_version": 2,
        "scope": str(item.get("scope") or "project"),
        "authority": str(item.get("authority") or "project"),
        "status": "confirmed",
        "revision_reason": "从关系图编辑" if item else "从关系图新增",
    }
    if item:
        ok = update_confirmed_knowledge_item_record(project_name, "relationships", knowledge_id, payload)
    else:
        upsert_knowledge_category_item_record(project_name, "relationships", payload)
        ok = True
    if ok:
        st.success("关系知识已保存；关系图已由权威知识重新投影。")
        st.rerun()
    st.error("关系保存失败，原知识未改变。")


def _render_relationship_graph(project_name: str, story_id: str) -> None:
    relationships = [item for item in load_knowledge_category(project_name, "relationships") if isinstance(item, dict)]
    graph = load_knowledge_graph(project_name, story_id=story_id)
    keyword = st.text_input("筛选关系图", placeholder="角色、地点、组织或关系", key=scoped_widget_key("relationship_graph_keyword", project_name, story_id)).strip().casefold()
    if keyword:
        edges = [edge for edge in graph.get("edges", []) if keyword in " ".join([
            str(edge.get("source_name") or ""), str(edge.get("target_name") or ""), str(edge.get("relation_type") or ""),
        ]).casefold()]
        node_ids = {str(edge.get("source_node_id")) for edge in edges} | {str(edge.get("target_node_id")) for edge in edges}
        graph = {"edges": edges, "nodes": [node for node in graph.get("nodes", []) if str(node.get("node_id")) in node_ids]}
    render_stat_strip([("关系知识", len(relationships)), ("图节点", len(graph.get("nodes", []))), ("图连线", len(graph.get("edges", [])))])
    if graph.get("edges"):
        if len(graph["edges"]) > 80:
            st.warning("关系较多，画布只显示最近 80 条；筛选后可查看其余关系。")
        st.graphviz_chart(_graph_dot(graph), width="stretch")
        st.dataframe([
            {"主体": edge.get("source_name"), "关系": edge.get("relation_type"), "客体": edge.get("target_name"),
             "方向": edge.get("direction"), "置信度": edge.get("confidence")}
            for edge in graph.get("edges", [])
        ], width="stretch", hide_index=True)
    else:
        render_empty_state("还没有可绘制的关系", "新增包含主体、客体和关系类型的关系知识后会自动连线。")
    _render_relationship_editor(project_name, relationships)


def render_entity_experience(project_name: str, story_id: str) -> None:
    st.markdown("### 创作实体视图")
    st.caption("所有卡片和图表都从正式知识实时投影；编辑只写回权威知识及其修订历史。")
    view = st.segmented_control(
        "实体视图", options=["角色中心", "世界观中心", "时间轴", "关系图"], default="角色中心",
        key=scoped_widget_key("entity_experience_view", project_name, story_id), width="stretch",
    ) or "角色中心"
    if view == "角色中心":
        _render_character_center(project_name)
    elif view == "世界观中心":
        _render_world_center(project_name)
    elif view == "时间轴":
        _render_timeline(project_name)
    else:
        _render_relationship_graph(project_name, story_id)
