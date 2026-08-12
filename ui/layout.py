"""NovelForge 的全局视觉系统与通用页面组件。"""
from __future__ import annotations

import html
from collections.abc import Iterable, Sequence

import streamlit as st


def apply_app_style() -> None:
    """应用统一的桌面端、窄屏和交互状态样式。"""

    st.markdown(
        """
        <style>
        :root {
            color-scheme: light;
            --nf-bg: #f4f7fb;
            --nf-panel: #ffffff;
            --nf-panel-soft: #f8fafc;
            --nf-panel-muted: #f1f5f9;
            --nf-border: #e2e8f0;
            --nf-border-strong: #cbd5e1;
            --nf-text: #182230;
            --nf-muted: #667085;
            --nf-subtle: #98a2b3;
            --nf-accent: #315fba;
            --nf-accent-strong: #244a93;
            --nf-accent-soft: #edf4ff;
            --nf-success: #19715a;
            --nf-success-soft: #ecfdf3;
            --nf-warning: #9a5b13;
            --nf-warning-soft: #fff8e8;
            --nf-danger: #b42318;
            --nf-danger-soft: #fff1f0;
            --nf-radius-sm: 8px;
            --nf-radius: 12px;
            --nf-radius-lg: 16px;
            --nf-shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.04);
            --nf-shadow: 0 8px 24px rgba(16, 24, 40, 0.06);
        }

        html, body, .stApp,
        .stApp button, .stApp input, .stApp textarea, .stApp select {
            font-family: Inter, "SF Pro Text", "Segoe UI", "Microsoft YaHei UI",
                "Microsoft YaHei", system-ui, sans-serif;
        }

        .stApp {
            color: var(--nf-text);
            background:
                radial-gradient(circle at 85% -10%, rgba(49, 95, 186, 0.08), transparent 30rem),
                var(--nf-bg);
        }

        .stApp *, .stApp *::before, .stApp *::after {
            box-sizing: border-box;
        }

        #MainMenu, footer,
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }

        /* 页面框架 */
        .block-container {
            max-width: 1280px;
            padding: 1rem 2rem 4rem;
        }

        [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }

        h1, h2, h3, h4, h5 {
            color: var(--nf-text);
            letter-spacing: -0.015em;
        }

        h1 { font-size: 1.65rem; }
        h2 { font-size: 1.35rem; }
        h3 { font-size: 1.15rem; }
        h4, h5 { font-size: 1rem; }

        p, li {
            line-height: 1.62;
        }

        hr {
            margin: 1.15rem 0;
            border: 0;
            border-top: 1px solid var(--nf-border);
        }

        /* 侧栏 */
        [data-testid="stSidebar"] {
            min-width: 284px;
            background: rgba(248, 250, 252, 0.97);
            border-right: 1px solid var(--nf-border);
        }

        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0.75rem;
        }

        .nf-sidebar-brand {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            padding: 0.35rem 0.15rem 0.75rem;
        }

        .nf-sidebar-mark {
            display: grid;
            place-items: center;
            width: 2.15rem;
            height: 2.15rem;
            border-radius: 11px;
            color: #fff;
            background: linear-gradient(145deg, var(--nf-accent), #6e56cf);
            box-shadow: 0 6px 18px rgba(49, 95, 186, 0.24);
            font-size: 0.92rem;
            font-weight: 800;
        }

        .nf-sidebar-title {
            color: var(--nf-text);
            font-size: 1.02rem;
            font-weight: 780;
            line-height: 1.2;
        }

        .nf-sidebar-meta {
            color: var(--nf-muted);
            font-size: 0.76rem;
            line-height: 1.4;
            margin-top: 0.12rem;
        }

        .nf-sidebar-note {
            margin: 0.45rem 0;
            padding: 0.7rem 0.78rem;
            color: var(--nf-text);
            background: var(--nf-accent-soft);
            border: 1px solid #cfe0fb;
            border-radius: var(--nf-radius-sm);
            font-size: 0.82rem;
            line-height: 1.5;
        }

        [data-testid="stSidebar"] hr {
            margin: 0.8rem 0;
        }

        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: var(--nf-muted) !important;
            font-size: 0.76rem;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] > label p {
            color: var(--nf-muted) !important;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {
            gap: 0.16rem;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label {
            min-height: 2.25rem;
            padding: 0.38rem 0.5rem;
            border-radius: var(--nf-radius-sm);
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:hover {
            background: var(--nf-panel-muted);
        }

        /* 紧凑页头 */
        .nf-page-header {
            position: relative;
            overflow: hidden;
            padding: 1.05rem 1.2rem 0.95rem;
            margin: 0 0 0.85rem;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid var(--nf-border);
            border-radius: var(--nf-radius-lg);
            box-shadow: var(--nf-shadow-sm);
        }

        .nf-page-header::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 4px;
            background: linear-gradient(180deg, var(--nf-accent), #7157ca);
        }

        .nf-page-eyebrow {
            color: var(--nf-accent-strong);
            font-size: 0.72rem;
            font-weight: 780;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .nf-page-title {
            color: var(--nf-text);
            margin-top: 0.18rem;
            font-size: 1.48rem;
            font-weight: 790;
            line-height: 1.25;
            letter-spacing: -0.025em;
        }

        .nf-page-description {
            max-width: 58rem;
            margin-top: 0.28rem;
            color: var(--nf-muted);
            font-size: 0.9rem;
            line-height: 1.55;
        }

        .nf-page-context {
            display: flex;
            flex-wrap: wrap;
            gap: 0.38rem;
            margin-top: 0.68rem;
        }

        .nf-page-context span {
            display: inline-flex;
            align-items: center;
            gap: 0.32rem;
            min-width: 0;
            padding: 0.24rem 0.52rem;
            color: var(--nf-muted);
            background: var(--nf-panel-soft);
            border: 1px solid var(--nf-border);
            border-radius: 999px;
            font-size: 0.75rem;
            line-height: 1.35;
        }

        .nf-page-context b {
            max-width: 15rem;
            overflow: hidden;
            color: var(--nf-text);
            font-weight: 680;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* 区块与步骤 */
        .nf-section-heading {
            margin: 1.15rem 0 0.48rem;
        }

        .nf-section-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--nf-text);
            font-size: 1.06rem;
            font-weight: 760;
            line-height: 1.4;
        }

        .nf-section-title::before {
            content: "";
            width: 0.22rem;
            height: 1rem;
            flex: 0 0 auto;
            border-radius: 999px;
            background: var(--nf-accent);
        }

        .nf-section-caption {
            max-width: 60rem;
            margin: 0.22rem 0 0 0.72rem;
            color: var(--nf-muted);
            font-size: 0.86rem;
            line-height: 1.52;
        }

        .nf-step-heading {
            display: grid;
            grid-template-columns: 2rem minmax(0, 1fr);
            gap: 0.68rem;
            align-items: start;
            margin: 1rem 0 0.55rem;
        }

        .nf-step-number {
            display: grid;
            place-items: center;
            width: 2rem;
            height: 2rem;
            color: #fff;
            background: var(--nf-accent);
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 800;
        }

        .nf-step-title {
            color: var(--nf-text);
            font-size: 1rem;
            font-weight: 760;
            line-height: 1.35;
        }

        .nf-step-copy {
            margin-top: 0.12rem;
            color: var(--nf-muted);
            font-size: 0.84rem;
            line-height: 1.5;
        }

        /* 卡片与状态 */
        .nf-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.72rem;
            margin: 0.75rem 0;
        }

        .nf-card,
        .nf-status-item,
        .nf-empty-state,
        .nf-action-summary {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: var(--nf-radius);
            box-shadow: var(--nf-shadow-sm);
        }

        .nf-card { padding: 0.9rem; }

        .nf-card-title,
        .nf-action-title {
            color: var(--nf-text);
            font-size: 0.95rem;
            font-weight: 740;
            line-height: 1.4;
        }

        .nf-card-copy,
        .nf-action-copy {
            margin-top: 0.26rem;
            color: var(--nf-muted);
            font-size: 0.84rem;
            line-height: 1.5;
        }

        .nf-action-card-body {
            min-height: 5.6rem;
            padding: 0.12rem 0 0.3rem;
        }

        .nf-status-grid,
        .nf-stat-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 0.55rem;
        }

        .nf-status-grid { margin-top: 0.7rem; }

        .nf-status-item,
        .nf-stat-item {
            min-width: 0;
            padding: 0.68rem 0.75rem;
            background: var(--nf-panel-soft);
            border: 1px solid var(--nf-border);
            border-radius: var(--nf-radius-sm);
        }

        .nf-status-label,
        .nf-stat-label {
            color: var(--nf-muted);
            font-size: 0.73rem;
            line-height: 1.3;
        }

        .nf-status-value,
        .nf-stat-value {
            margin-top: 0.2rem;
            overflow-wrap: anywhere;
            color: var(--nf-text);
            font-size: 1.05rem;
            font-weight: 760;
            line-height: 1.3;
        }

        .nf-stat-hint {
            margin-top: 0.15rem;
            color: var(--nf-subtle);
            font-size: 0.7rem;
            line-height: 1.35;
        }

        .nf-empty-state {
            padding: 1.35rem 1rem;
            text-align: center;
            background: var(--nf-panel-soft);
        }

        .nf-empty-icon {
            display: grid;
            place-items: center;
            width: 2.4rem;
            height: 2.4rem;
            margin: 0 auto 0.55rem;
            color: var(--nf-accent-strong);
            background: var(--nf-accent-soft);
            border-radius: 999px;
            font-weight: 800;
        }

        .nf-empty-title {
            color: var(--nf-text);
            font-weight: 740;
        }

        .nf-empty-copy {
            max-width: 36rem;
            margin: 0.25rem auto 0;
            color: var(--nf-muted);
            font-size: 0.84rem;
            line-height: 1.55;
        }

        .nf-action-summary {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            padding: 0.68rem 0.8rem;
            border-left: 4px solid var(--nf-accent);
        }

        .nf-action-summary[data-tone="warning"] {
            background: var(--nf-warning-soft);
            border-left-color: var(--nf-warning);
        }

        .nf-action-summary[data-tone="danger"] {
            background: var(--nf-danger-soft);
            border-left-color: var(--nf-danger);
        }

        .nf-action-summary-label {
            color: var(--nf-muted);
            font-size: 0.74rem;
            font-weight: 700;
        }

        .nf-action-summary-value {
            margin-top: 0.1rem;
            color: var(--nf-text);
            font-size: 0.9rem;
            font-weight: 720;
        }

        .nf-action-summary-note {
            color: var(--nf-muted);
            font-size: 0.76rem;
            text-align: right;
        }

        .nf-selection-summary {
            padding: 0.55rem 0.7rem;
            color: var(--nf-text);
            background: var(--nf-accent-soft);
            border: 1px solid #d5e3fb;
            border-radius: var(--nf-radius-sm);
            font-size: 0.84rem;
            line-height: 1.5;
        }

        .nf-preset-card {
            min-height: 0;
        }

        .nf-preset-card-title { font-weight: 750; }
        .nf-preset-card-copy { margin-top: 0.3rem; font-size: 0.85rem; line-height: 1.5; }
        .nf-preset-card-effect { margin-top: 0.3rem; color: var(--nf-muted); font-size: 0.78rem; line-height: 1.45; }
        .active-profile-card { border-color: #b9cdf4 !important; box-shadow: 0 0 0 2px var(--nf-accent-soft); }
        .nf-button-align-spacer { min-height: 1.56rem; }

        /* Streamlit 容器、列和表单 */
        [data-testid="stHorizontalBlock"] {
            gap: 0.72rem;
            align-items: stretch;
        }

        [data-testid="stColumn"] {
            min-width: 0;
        }

        [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
            height: 100%;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--nf-border) !important;
            border-radius: var(--nf-radius) !important;
            background: var(--nf-panel);
            box-shadow: var(--nf-shadow-sm);
        }

        [data-testid="stForm"] {
            padding: 0.9rem !important;
            background: var(--nf-panel) !important;
            border: 1px solid var(--nf-border) !important;
            border-radius: var(--nf-radius) !important;
        }

        /* 标签和页签 */
        [data-baseweb="tab-list"] {
            gap: 0.25rem;
            padding: 0.24rem;
            overflow-x: auto !important;
            background: var(--nf-panel-muted);
            border: 1px solid var(--nf-border);
            border-radius: 10px;
            scrollbar-width: none;
        }

        [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }

        [data-baseweb="tab"] {
            flex: 1 1 0;
            min-width: max-content;
            min-height: 2.35rem;
            padding: 0.42rem 0.75rem;
            border-radius: 8px;
        }

        [data-baseweb="tab"][aria-selected="true"] {
            background: var(--nf-panel);
            box-shadow: var(--nf-shadow-sm);
        }

        [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
            display: none;
        }

        [data-testid="stButtonGroup"] [data-baseweb="button-group"],
        [data-testid="stSegmentedControl"] [data-baseweb="button-group"],
        [data-testid="stPills"] [data-baseweb="button-group"] {
            gap: 0.25rem;
            padding: 0.22rem;
            background: var(--nf-panel-muted);
            border: 1px solid var(--nf-border);
            border-radius: 10px;
        }

        /* 按钮 */
        .stApp [data-testid="stButton"] button,
        .stApp [data-testid="stFormSubmitButton"] button,
        .stApp button[data-testid^="stBaseButton"] {
            min-height: 2.45rem;
            border: 1px solid var(--nf-border-strong) !important;
            border-radius: var(--nf-radius-sm) !important;
            color: var(--nf-text) !important;
            background: var(--nf-panel) !important;
            box-shadow: var(--nf-shadow-sm);
            font-weight: 670 !important;
            transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }

        .stApp [data-testid="stButton"] button:hover,
        .stApp [data-testid="stFormSubmitButton"] button:hover,
        .stApp button[data-testid^="stBaseButton"]:hover {
            color: var(--nf-accent-strong) !important;
            background: var(--nf-accent-soft) !important;
            border-color: #9eb9e9 !important;
        }

        .stApp button[data-testid^="stBaseButton"][kind="primary"],
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"],
        .stApp [data-testid="stButton"] button[kind="primary"],
        .stApp [data-testid="stButton"] button[data-kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"] {
            color: #fff !important;
            background: linear-gradient(180deg, #3c6bc4 0%, var(--nf-accent) 100%) !important;
            border-color: var(--nf-accent-strong) !important;
            box-shadow: 0 6px 16px rgba(49, 95, 186, 0.2);
        }

        .stApp button[data-testid^="stBaseButton"][kind="primary"] *,
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"] *,
        .stApp [data-testid="stButton"] button[kind="primary"] *,
        .stApp [data-testid="stButton"] button[data-kind="primary"] *,
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"] * {
            color: #fff !important;
            fill: #fff !important;
            -webkit-text-fill-color: #fff !important;
        }

        .stApp button[data-testid^="stBaseButton"][kind="primary"]:hover,
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[data-kind="primary"]:hover {
            color: #fff !important;
            background: var(--nf-accent-strong) !important;
        }

        .stApp [data-testid="stButtonGroup"] button[kind="segmented_controlActive"],
        .stApp [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] {
            color: #fff !important;
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
            box-shadow: 0 4px 12px rgba(49, 95, 186, 0.18) !important;
        }

        .stApp [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] *,
        .stApp [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] * {
            color: #fff !important;
            fill: #fff !important;
            -webkit-text-fill-color: #fff !important;
        }

        .stApp button[data-testid^="stBaseButton"]:disabled,
        .stApp button[data-testid^="stBaseButton"][disabled],
        .stApp [data-testid="stButton"] button:disabled,
        .stApp [data-testid="stFormSubmitButton"] button:disabled,
        .stApp button[kind="primary"]:disabled {
            color: #7a8494 !important;
            background: #eef1f5 !important;
            border-color: #d9e0e8 !important;
            box-shadow: none !important;
            cursor: not-allowed !important;
        }

        .stApp button:focus-visible,
        .stApp input:focus-visible,
        .stApp textarea:focus-visible {
            outline: 3px solid rgba(49, 95, 186, 0.2) !important;
            outline-offset: 1px;
        }

        /* 输入控件 */
        .stApp input,
        .stApp textarea,
        .stApp [data-baseweb="select"] > div,
        .stApp [data-baseweb="base-input"] {
            color: var(--nf-text) !important;
            background: var(--nf-panel) !important;
            border-color: var(--nf-border-strong) !important;
            border-radius: var(--nf-radius-sm) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp input::placeholder,
        .stApp textarea::placeholder {
            color: var(--nf-subtle) !important;
            -webkit-text-fill-color: var(--nf-subtle) !important;
        }

        .stApp [data-testid="stWidgetLabel"] p {
            color: var(--nf-text) !important;
            font-size: 0.82rem;
            font-weight: 650;
        }

        .stApp [data-testid="stCaptionContainer"] p,
        .stApp .stCaption p {
            color: var(--nf-muted) !important;
            line-height: 1.5;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div {
            min-height: 2.55rem;
            max-height: 8.5rem;
            overflow-y: auto;
        }

        .stApp .stMultiSelect [data-baseweb="tag"] {
            color: var(--nf-accent-strong) !important;
            background: var(--nf-accent-soft) !important;
            border: 1px solid #cfe0fb;
            border-radius: 6px;
        }

        .stApp .stMultiSelect [data-baseweb="tag"] * {
            color: var(--nf-accent-strong) !important;
            fill: var(--nf-accent-strong) !important;
        }

        .stApp button[aria-label^="Help for"] {
            width: 1rem !important;
            min-width: 1rem !important;
            min-height: 1rem !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        /* 展开区、提示、指标和数据 */
        div[data-testid="stExpander"] {
            overflow: hidden;
            background: var(--nf-panel) !important;
            border: 1px solid var(--nf-border) !important;
            border-radius: var(--nf-radius) !important;
            box-shadow: var(--nf-shadow-sm);
        }

        div[data-testid="stExpander"] details > summary {
            min-height: 2.75rem;
            padding: 0.15rem 0.2rem;
            color: var(--nf-text) !important;
            background: var(--nf-panel-soft) !important;
        }

        div[data-testid="stExpander"] details > summary:hover,
        div[data-testid="stExpander"] details[open] > summary {
            background: var(--nf-accent-soft) !important;
        }

        div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            padding-top: 0.55rem;
        }

        div[data-testid="stMetric"] {
            min-height: 5.4rem;
            padding: 0.72rem 0.78rem;
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: var(--nf-radius);
            box-shadow: var(--nf-shadow-sm);
        }

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            color: var(--nf-muted) !important;
            font-size: 0.76rem !important;
        }

        div[data-testid="stMetricValue"] {
            color: var(--nf-text) !important;
            font-size: 1.28rem !important;
            font-weight: 760;
        }

        .stApp [data-testid="stAlert"] {
            border-radius: var(--nf-radius-sm);
            border-width: 1px;
        }

        .stApp [data-testid="stDataFrame"],
        .stApp [data-testid="stTable"] {
            overflow: hidden;
            border: 1px solid var(--nf-border) !important;
            border-radius: var(--nf-radius-sm);
        }

        .stApp [data-testid="stFileUploader"] section {
            padding: 0.8rem;
            background: var(--nf-panel-soft);
            border-color: var(--nf-border-strong);
            border-radius: var(--nf-radius);
        }

        .stApp pre,
        .stApp [data-testid="stCodeBlock"] pre {
            color: var(--nf-text) !important;
            background: #f8fafc !important;
            border: 1px solid var(--nf-border) !important;
            border-radius: var(--nf-radius-sm) !important;
        }

        /* 对话工作区 */
        .nf-discussion-brief {
            padding: 0.8rem;
            margin-bottom: 0.55rem;
            background: var(--nf-panel-soft);
            border: 1px solid var(--nf-border);
            border-radius: var(--nf-radius-sm);
        }

        .nf-discussion-brief-title {
            color: var(--nf-accent-strong);
            font-size: 0.78rem;
            font-weight: 760;
        }

        .nf-discussion-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.3rem;
            margin-top: 0.45rem;
        }

        .nf-discussion-chip {
            padding: 0.22rem 0.5rem;
            color: var(--nf-text);
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 999px;
            font-size: 0.74rem;
        }

        .nf-discussion-impact {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            gap: 0.45rem;
            margin-top: 0.5rem;
            color: var(--nf-muted);
            font-size: 0.78rem;
        }

        .nf-discussion-impact b { color: var(--nf-text); }
        .nf-discussion-note, .nf-discussion-empty-hint {
            margin-top: 0.4rem;
            color: var(--nf-muted);
            font-size: 0.78rem;
            line-height: 1.5;
        }

        .stApp [class*="st-key-nf-discussion-shell-"] {
            display: grid;
            gap: 0.7rem;
        }

        .stApp [class*="st-key-nf-discussion-input-"] > div,
        .stApp [class*="st-key-nf-discussion-output-"] > div {
            height: 100%;
        }

        .stApp [class*="st-key-nf-discussion-input-"] textarea {
            min-height: 8.5rem;
        }

        .stApp [class*="st-key-nf-discussion-output-"] {
            max-height: 44rem;
            overflow-y: auto;
        }

        /* 创作实体与固定作曲器 */
        .nf-entity-badge-row, .nf-entity-source-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin: 0.35rem 0 0.7rem;
        }

        .nf-entity-badge, .nf-entity-source {
            display: inline-flex;
            align-items: center;
            padding: 0.24rem 0.55rem;
            color: var(--nf-muted);
            background: var(--nf-panel-soft);
            border: 1px solid var(--nf-border);
            border-radius: 999px;
            font-size: 0.75rem;
            line-height: 1.35;
        }

        .nf-entity-success { color: var(--nf-success); background: var(--nf-success-soft); }
        .nf-entity-warning { color: var(--nf-warning); background: var(--nf-warning-soft); }
        .nf-entity-danger { color: var(--nf-danger); background: var(--nf-danger-soft); }
        .nf-entity-source { color: var(--nf-accent-strong); background: var(--nf-accent-soft); }

        .stApp [class*="st-key-nf-creative-composer-"] {
            position: sticky;
            bottom: 0.6rem;
            z-index: 20;
            padding: 0.75rem;
            background: rgba(255, 255, 255, 0.96);
            border: 1px solid var(--nf-border-strong);
            border-radius: var(--nf-radius-lg);
            box-shadow: 0 12px 34px rgba(16, 24, 40, 0.14);
            backdrop-filter: blur(12px);
        }

        /* 窄屏 */
        @media (max-width: 900px) {
            .block-container {
                padding: 0.75rem 1rem 3rem;
            }

            .nf-page-header {
                padding: 0.9rem 0.95rem 0.85rem;
            }

            .nf-page-title { font-size: 1.28rem; }
            .nf-page-context b { max-width: 10rem; }

            [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }

            [data-testid="stMain"] [data-testid="stColumn"] {
                flex: 1 1 15rem !important;
                width: 100% !important;
                min-width: min(15rem, 100%) !important;
            }

            [data-baseweb="tab-list"] {
                justify-content: flex-start;
                overflow-x: auto !important;
            }

            [data-baseweb="tab"] {
                flex: 0 0 auto;
            }

            .nf-stat-strip,
            .nf-status-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .nf-action-summary {
                align-items: flex-start;
                flex-direction: column;
            }

            .nf-action-summary-note { text-align: left; }
            .nf-discussion-impact { grid-template-columns: 1fr; }
        }

        @media (max-width: 560px) {
            .nf-page-context { display: grid; grid-template-columns: 1fr 1fr; }
            .nf-page-context span { min-width: 0; }
            .nf-stat-strip, .nf-status-grid { grid-template-columns: 1fr 1fr; }
            .nf-section-caption { margin-left: 0; }
            [data-testid="stMain"] [data-testid="stColumn"] { flex-basis: 100% !important; }

        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(project_name: str | None, page: str, memory: dict | None) -> None:
    """显示紧凑且一致的页面标题和项目上下文。"""

    try:
        from ui.navigation import PAGE_DESCRIPTIONS, PAGE_LABELS
    except Exception:
        PAGE_DESCRIPTIONS = {}
        PAGE_LABELS = {}

    payload = dict(memory or {})
    project_label = str(project_name or "未选择项目")
    title = str(payload.get("title") or project_name or "未命名作品")
    genre = str(payload.get("genre") or "未设置类型")
    canon_mode = str(payload.get("canon_mode") or "未设置参考方式")
    description = str(PAGE_DESCRIPTIONS.get(page, ""))
    page_label = str(PAGE_LABELS.get(page, page))
    context_items = [
        ("项目", project_label),
        ("作品", title),
        ("类型", genre),
        ("参考", canon_mode),
    ]
    context_html = "".join(
        f"<span>{html.escape(label)} <b>{html.escape(value)}</b></span>"
        for label, value in context_items
    )
    st.markdown(
        f"""
        <div class="nf-page-header">
            <div class="nf-page-eyebrow">NovelForge · Workspace</div>
            <div class="nf-page-title">{html.escape(page_label)}</div>
            {f'<div class="nf-page-description">{html.escape(description)}</div>' if description else ''}
            <div class="nf-page-context">{context_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, caption: str = "") -> None:
    """显示统一的内容区块标题。"""

    st.markdown(
        f"""
        <div class="nf-section-heading">
            <div class="nf-section-title" role="heading" aria-level="2">{html.escape(str(title))}</div>
            {f'<div class="nf-section-caption">{html.escape(str(caption))}</div>' if caption else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_step_heading(step: int | str, title: str, caption: str = "") -> None:
    """显示导入、规划等流程中的单个步骤。"""

    st.markdown(
        f"""
        <div class="nf-step-heading">
            <div class="nf-step-number">{html.escape(str(step))}</div>
            <div>
                <div class="nf-step-title">{html.escape(str(title))}</div>
                {f'<div class="nf-step-copy">{html.escape(str(caption))}</div>' if caption else ''}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_strip(items: Sequence[tuple[str, object] | tuple[str, object, str]]) -> None:
    """用紧凑状态条展示少量关键指标。"""

    blocks: list[str] = []
    for item in items:
        label, value = item[0], item[1]
        hint = item[2] if len(item) > 2 else ""
        blocks.append(
            "".join(
                [
                    '<div class="nf-stat-item">',
                    f'<div class="nf-stat-label">{html.escape(str(label))}</div>',
                    f'<div class="nf-stat-value">{html.escape(str(value))}</div>',
                    f'<div class="nf-stat-hint">{html.escape(str(hint))}</div>' if hint else "",
                    "</div>",
                ]
            )
        )
    st.markdown(f'<div class="nf-stat-strip">{"".join(blocks)}</div>', unsafe_allow_html=True)


def render_empty_state(title: str, description: str, *, icon: str = "＋") -> None:
    """显示不包含无效控件的统一空状态。"""

    st.markdown(
        f"""
        <div class="nf-empty-state">
            <div class="nf-empty-icon">{html.escape(str(icon))}</div>
            <div class="nf-empty-title">{html.escape(str(title))}</div>
            <div class="nf-empty-copy">{html.escape(str(description))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_summary(
    label: str,
    value: str,
    *,
    note: str = "",
    tone: str = "default",
) -> None:
    """在主操作旁显示其范围、成本或保存结果。"""

    safe_tone = tone if tone in {"default", "warning", "danger"} else "default"
    st.markdown(
        f"""
        <div class="nf-action-summary" data-tone="{safe_tone}">
            <div>
                <div class="nf-action-summary-label">{html.escape(str(label))}</div>
                <div class="nf-action-summary-value">{html.escape(str(value))}</div>
            </div>
            {f'<div class="nf-action-summary-note">{html.escape(str(note))}</div>' if note else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_selection_summary(parts: Iterable[str]) -> None:
    """显示当前筛选或处理范围，避免用大量已选标签表达。"""

    text = " · ".join(str(part) for part in parts if str(part).strip())
    if text:
        st.markdown(
            f'<div class="nf-selection-summary">{html.escape(text)}</div>',
            unsafe_allow_html=True,
        )
