"""Top-level Streamlit layout and style helpers."""
from __future__ import annotations

import html

import streamlit as st

def apply_app_style():
    st.markdown(
        """
        <style>
        :root {
            color-scheme: light;
            --nf-bg: #f8fbff;
            --nf-panel: #ffffff;
            --nf-border: #dbe6f2;
            --nf-text: #1f2937;
            --nf-muted: #66758a;
            --nf-accent: #6b9edb;
            --nf-accent-strong: #4d7fbd;
            --nf-accent-soft: #eef6ff;
            --nf-danger: #b42318;
            --nf-shadow: 0 16px 42px rgba(44, 82, 130, 0.08);
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(255,255,255,0.9), rgba(248,251,255,0.98)),
                var(--nf-bg);
            color: var(--nf-text);
        }

        [data-testid="stSidebar"] {
            background: #f3f8ff;
            border-right: 1px solid var(--nf-border);
        }

        [data-testid="stSidebar"] * {
            color: var(--nf-text);
        }

        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--nf-muted);
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] div,
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] svg,
        [data-testid="stSidebar"] [data-baseweb="select"] svg path,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
            font-weight: 650 !important;
        }

        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] [data-testid="stPopover"] button {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
            font-weight: 650 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] .stButton > button p,
        [data-testid="stSidebar"] .stButton > button span,
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button span,
        [data-testid="stSidebar"] button svg,
        [data-testid="stSidebar"] button svg path {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: var(--nf-accent-soft) !important;
            border-color: var(--nf-accent) !important;
            color: var(--nf-accent-strong) !important;
        }

        [data-testid="stSidebar"] button:hover,
        [data-testid="stSidebar"] button:hover * {
            color: var(--nf-accent-strong) !important;
            fill: var(--nf-accent-strong) !important;
            -webkit-text-fill-color: var(--nf-accent-strong) !important;
        }

        [data-testid="stSidebar"] .stButton > button:disabled,
        [data-testid="stSidebar"] .stButton > button[disabled],
        [data-testid="stSidebar"] .stButton > button:disabled *,
        [data-testid="stSidebar"] .stButton > button[disabled] *,
        [data-testid="stSidebar"] button:disabled,
        [data-testid="stSidebar"] button[disabled],
        [data-testid="stSidebar"] button:disabled *,
        [data-testid="stSidebar"] button[disabled] * {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .block-container {
            max-width: 1320px;
            padding-top: 1.4rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        div[data-testid="stMetric"] {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            box-shadow: 0 10px 28px rgba(44, 82, 130, 0.05);
        }

        div[data-testid="stMetric"] label {
            color: var(--nf-muted);
        }

        .nf-hero {
            background: transparent;
            border: 0;
            border-bottom: 1px solid var(--nf-border);
            border-radius: 0;
            padding: 0.05rem 0 0.65rem;
            box-shadow: none;
            margin-bottom: 0.75rem;
        }

        .nf-kicker {
            color: var(--nf-accent);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.3rem;
        }

        .nf-title {
            color: var(--nf-text);
            font-size: 1.12rem;
            line-height: 1.25;
            font-weight: 750;
            margin: 0;
        }

        .nf-subtitle {
            color: var(--nf-muted);
            margin-top: 0.35rem;
            margin-bottom: 0;
        }

        .nf-header-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.4rem;
        }

        .nf-header-meta span {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            min-height: 1.65rem;
            padding: 0.15rem 0.55rem;
            border: 1px solid var(--nf-border);
            border-radius: 999px;
            background: #ffffff;
            color: var(--nf-muted);
            font-size: 0.82rem;
            line-height: 1.25;
        }

        .nf-header-meta b {
            color: var(--nf-text);
            font-weight: 650;
        }

        .nf-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.8rem;
            margin: 1rem 0;
        }

        .nf-card {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 10px 26px rgba(44, 82, 130, 0.05);
        }

        .nf-card-title {
            font-weight: 700;
            color: var(--nf-text);
            margin-bottom: 0.35rem;
        }

        .nf-card-copy {
            color: var(--nf-muted);
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .active-profile-card {
            border-left: 4px solid var(--nf-accent) !important;
        }

        .nf-sidebar-title {
            font-size: 1.05rem;
            font-weight: 750;
            margin: 0.2rem 0 0.2rem;
        }

        .nf-sidebar-meta {
            color: var(--nf-muted);
            font-size: 0.82rem;
            line-height: 1.45;
            margin-bottom: 0.8rem;
        }

        .nf-sidebar-note {
            margin: 0.65rem 0 0.45rem;
            padding: 0.65rem 0.75rem;
            border-radius: 8px;
            border: 1px solid #c9ddf5;
            background: #eaf4ff;
            color: var(--nf-text);
            font-size: 0.84rem;
            line-height: 1.5;
        }

        .nf-sidebar-note strong {
            color: var(--nf-text);
            font-weight: 700;
        }

        .stButton > button {
            border-radius: 8px;
            border: 1px solid var(--nf-border);
            background: var(--nf-panel) !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp .stButton button,
        .stApp [data-testid="stButton"] button,
        .stApp [data-testid="stFormSubmitButton"] button,
        .stApp button[data-testid^="stBaseButton"] {
            border-radius: 8px;
            border: 1px solid var(--nf-border) !important;
            background: var(--nf-panel) !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stButton > button[kind="primary"],
        .stButton > button[data-kind="primary"],
        .stApp .stButton button[kind="primary"],
        .stApp .stButton button[data-kind="primary"],
        .stApp [data-testid="stButton"] button[kind="primary"],
        .stApp [data-testid="stButton"] button[data-kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"],
        .stApp button[data-testid^="stBaseButton"][kind="primary"],
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"] {
            background: var(--nf-accent) !important;
            color: #ffffff !important;
            border-color: var(--nf-accent-strong) !important;
            font-weight: 650 !important;
        }

        .stButton > button[kind="primary"] *,
        .stButton > button[data-kind="primary"] *,
        .stButton > button[kind="primary"] [data-testid="stMarkdownContainer"],
        .stButton > button[data-kind="primary"] [data-testid="stMarkdownContainer"],
        .stButton > button[kind="primary"] [data-testid="stMarkdownContainer"] *,
        .stButton > button[data-kind="primary"] [data-testid="stMarkdownContainer"] *,
        .stApp .stButton button[kind="primary"] *,
        .stApp .stButton button[data-kind="primary"] *,
        .stApp [data-testid="stButton"] button[kind="primary"] *,
        .stApp [data-testid="stButton"] button[data-kind="primary"] *,
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"] *,
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"] *,
        .stApp button[data-testid^="stBaseButton"][kind="primary"] *,
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"] * {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-kind="primary"]:hover,
        .stApp .stButton button[kind="primary"]:hover,
        .stApp .stButton button[data-kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[data-kind="primary"]:hover,
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"]:hover,
        .stApp button[data-testid^="stBaseButton"][kind="primary"]:hover,
        .stApp button[data-testid^="stBaseButton"][data-kind="primary"]:hover {
            background: var(--nf-accent-strong) !important;
            color: #ffffff !important;
            border-color: #3869a8 !important;
        }

        .stButton > button:hover,
        .stApp .stButton button:hover,
        .stApp [data-testid="stButton"] button:hover,
        .stApp [data-testid="stFormSubmitButton"] button:hover,
        .stApp button[data-testid^="stBaseButton"]:hover {
            border-color: var(--nf-accent);
            color: var(--nf-accent);
        }

        .stButton > button:disabled,
        .stButton > button[disabled],
        .stButton > button:disabled *,
        .stButton > button[disabled] *,
        .stApp .stButton button:disabled,
        .stApp .stButton button[disabled],
        .stApp .stButton button:disabled *,
        .stApp .stButton button[disabled] *,
        .stApp [data-testid="stButton"] button:disabled,
        .stApp [data-testid="stButton"] button[disabled],
        .stApp [data-testid="stButton"] button:disabled *,
        .stApp [data-testid="stButton"] button[disabled] *,
        .stApp [data-testid="stFormSubmitButton"] button:disabled,
        .stApp [data-testid="stFormSubmitButton"] button[disabled],
        .stApp [data-testid="stFormSubmitButton"] button:disabled *,
        .stApp [data-testid="stFormSubmitButton"] button[disabled] *,
        .stApp button[data-testid^="stBaseButton"]:disabled,
        .stApp button[data-testid^="stBaseButton"][disabled],
        .stApp button[data-testid^="stBaseButton"]:disabled *,
        .stApp button[data-testid^="stBaseButton"][disabled] * {
            background: #f2f4f7 !important;
            color: #667085 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #667085 !important;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            background: var(--nf-panel) !important;
            color: var(--nf-text) !important;
            overflow: hidden;
        }

        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] details > summary,
        div[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
        div[data-testid="stExpander"] [data-testid="stMarkdownContainer"],
        div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] *,
        div[data-testid="stExpander"] p,
        div[data-testid="stExpander"] span,
        div[data-testid="stExpander"] label {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        div[data-testid="stExpander"] details > summary {
            background: #f8fafc !important;
            border-bottom: 1px solid var(--nf-border);
        }

        div[data-testid="stExpander"] details[open] > summary {
            background: var(--nf-accent-soft) !important;
        }

        .stApp label,
        .stApp [data-testid="stWidgetLabel"],
        .stApp [data-testid="stMarkdownContainer"],
        .stApp [data-testid="stMarkdownContainer"] p,
        .stApp [role="radiogroup"] label,
        .stApp [data-testid="stCheckbox"] label {
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp input,
        .stApp textarea,
        .stApp [data-baseweb="select"] > div {
            background: #ffffff !important;
            color: var(--nf-text) !important;
            border-color: var(--nf-border) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp [data-baseweb="select"] svg,
        .stApp [data-baseweb="select"] svg *,
        .stApp div[data-testid="stExpander"] svg,
        .stApp div[data-testid="stExpander"] svg *,
        .stApp [data-testid="stPopover"] > button svg,
        .stApp [data-testid="stPopover"] > button svg * {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            stroke: var(--nf-text) !important;
        }

        div[data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="popover"] [role="option"] {
            background: #ffffff !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp .stCodeBlock,
        .stApp [data-testid="stCodeBlock"],
        .stApp pre,
        .stApp .stCodeBlock pre,
        .stApp [data-testid="stCodeBlock"] pre,
        .stApp pre code,
        .stApp .stCodeBlock code,
        .stApp [data-testid="stCodeBlock"] code {
            background: #f8fafc !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp .stCodeBlock pre,
        .stApp [data-testid="stCodeBlock"] pre,
        .stApp pre {
            border-radius: 8px !important;
            border: 1px solid var(--nf-border) !important;
            padding: 1rem 1.1rem !important;
            line-height: 1.55 !important;
        }

        .stApp pre *,
        .stApp pre span,
        .stApp pre .token,
        .stApp pre code *,
        div[data-testid="stExpander"] pre *,
        div[data-testid="stExpander"] pre span,
        div[data-testid="stExpander"] pre .token {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            stroke: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp .stCodeBlock *,
        .stApp [data-testid="stCodeBlock"] *,
        div[data-testid="stExpander"] .stCodeBlock *,
        div[data-testid="stExpander"] [data-testid="stCodeBlock"] * {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            stroke: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp [data-testid="stJson"],
        .stApp [data-testid="stJson"] > div,
        .stApp [data-testid="stJson"] .react-json-view,
        .stApp [data-testid="stDataFrame"],
        .stApp [data-testid="stDataFrame"] > div {
            background: #ffffff !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp [data-testid="stJson"] *,
        .stApp [data-testid="stDataFrame"] *,
        .stApp table,
        .stApp table * {
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .stApp table,
        .stApp thead,
        .stApp tbody,
        .stApp tr,
        .stApp th,
        .stApp td {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
        }

        .stApp input::placeholder,
        .stApp textarea::placeholder {
            color: #98a2b3 !important;
            -webkit-text-fill-color: #98a2b3 !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div {
            padding-left: 0.55rem !important;
            overflow: visible !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] div {
            overflow: visible !important;
        }

        .stApp [data-baseweb="tag"] {
            display: inline-flex !important;
            align-items: center !important;
            min-width: 3rem !important;
            min-height: 1.75rem !important;
            margin: 0.12rem 0.25rem 0.12rem 0.28rem !important;
            padding: 0.18rem 0.5rem 0.18rem 0.72rem !important;
            background: var(--nf-accent) !important;
            color: #ffffff !important;
            border-color: var(--nf-accent-strong) !important;
            border-radius: 8px !important;
            overflow: visible !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        .stApp [data-baseweb="tag"] *,
        .stApp [data-baseweb="tag"] svg,
        .stApp [data-baseweb="tag"] svg * {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: nowrap !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        .stAlert,
        .stAlert div,
        .stAlert p,
        .stAlert span,
        div[data-testid="stAlert"] div,
        div[data-testid="stAlert"] p,
        div[data-testid="stAlert"] span {
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        label[data-baseweb="radio"] {
            gap: 0.45rem !important;
        }

        label[data-baseweb="radio"]:has(input:checked) > div:first-child {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
        }

        label[data-baseweb="radio"]:has(input:checked) > div:first-child > div {
            background: #ffffff !important;
            border-color: #ffffff !important;
        }

        label[data-baseweb="radio"]:not(:has(input:checked)) > div:first-child {
            background: rgba(255, 255, 255, 0.14) !important;
            border-color: rgba(238, 247, 246, 0.55) !important;
        }

        label[data-baseweb="checkbox"] {
            gap: 0.45rem !important;
        }

        label[data-baseweb="checkbox"] > div:first-child {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
        }

        label[data-baseweb="checkbox"] > span:first-child {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
            color: var(--nf-text) !important;
        }

        label[data-baseweb="checkbox"]:has(input:checked) > div:first-child {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
        }

        label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
        }

        label[data-baseweb="checkbox"]:has(input:checked) > div:first-child svg,
        label[data-baseweb="checkbox"]:has(input:checked) > div:first-child svg *,
        label[data-baseweb="checkbox"]:has(input:checked) > div:first-child path,
        label[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,
        label[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg *,
        label[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
        }

        .stApp input[type="checkbox"],
        .stApp input[type="radio"] {
            accent-color: var(--nf-accent);
        }

        [data-testid="stSidebar"],
        [data-testid="stSidebar"] .nf-sidebar-title,
        [data-testid="stSidebar"] .nf-sidebar-meta,
        [data-testid="stSidebar"] .nf-sidebar-note,
        [data-testid="stSidebar"] .nf-sidebar-note *,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [role="radiogroup"] label,
        [data-testid="stSidebar"] [role="radiogroup"] label *,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] .nf-sidebar-meta,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
            color: var(--nf-muted) !important;
            -webkit-text-fill-color: var(--nf-muted) !important;
        }

        [data-testid="stSidebar"] .nf-sidebar-note,
        [data-testid="stSidebar"] .nf-sidebar-note * {
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .nf-sidebar-note strong {
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] button [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] button [data-testid="stMarkdownContainer"] *,
        [data-testid="stSidebar"] button [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stPopover"] button,
        [data-testid="stSidebar"] [data-testid="stPopover"] button *,
        [data-testid="stSidebar"] [data-testid="stPopover"] button [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stPopover"] button [data-testid="stMarkdownContainer"] *,
        [data-testid="stSidebar"] [data-testid="stPopover"] button [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] *,
        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] p {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: #98a2b3 !important;
            -webkit-text-fill-color: #98a2b3 !important;
        }

        html body .stApp button[data-testid^="stBaseButton"],
        html body .stApp [data-testid="stButton"] button[data-testid^="stBaseButton"],
        html body .stApp [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"] {
            background: #ffffff !important;
            border: 1px solid var(--nf-border) !important;
            color: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        html body .stApp button[data-testid^="stBaseButton"] *,
        html body .stApp [data-testid="stButton"] button[data-testid^="stBaseButton"] *,
        html body .stApp [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"] * {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            stroke: var(--nf-text) !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        html body .stApp button[data-testid^="stBaseButton"][kind="primary"],
        html body .stApp button[data-testid^="stBaseButton"][data-kind="primary"] {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        html body .stApp button[data-testid^="stBaseButton"][kind="primary"] *,
        html body .stApp button[data-testid^="stBaseButton"][data-kind="primary"] * {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        html body .stApp button[data-testid^="stBaseButton"]:disabled,
        html body .stApp button[data-testid^="stBaseButton"][disabled],
        html body .stApp button[data-testid^="stBaseButton"]:disabled *,
        html body .stApp button[data-testid^="stBaseButton"][disabled] * {
            background: #f2f4f7 !important;
            border-color: var(--nf-border) !important;
            color: #667085 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #667085 !important;
        }

        html body .stApp label[data-baseweb="checkbox"] > div:first-child {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
        }

        html body .stApp label[data-baseweb="checkbox"] > span:first-child {
            background: #ffffff !important;
            border-color: var(--nf-border) !important;
        }

        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > div:first-child {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
        }

        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
            background: var(--nf-accent) !important;
            border-color: var(--nf-accent-strong) !important;
        }

        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > div:first-child *,
        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > div:first-child svg,
        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > div:first-child path,
        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > span:first-child *,
        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,
        html body .stApp label[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] > div,
        html body .stApp .stMultiSelect [data-baseweb="select"] > div > div {
            padding-left: 0.65rem !important;
            overflow: visible !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            margin-left: 0.45rem !important;
            padding-left: 0.78rem !important;
            overflow: visible !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_app_header(project_name: str | None, page: str, memory: dict | None):
    title = html.escape(str((memory or {}).get("title") or project_name or "未选择项目"))
    genre = html.escape(str((memory or {}).get("genre") or "未设置类型"))
    canon_mode = html.escape(str((memory or {}).get("canon_mode") or "未设置原作对齐"))
    page_label = html.escape(str(page))
    project_label = html.escape(str(project_name or "-"))
    st.markdown(
        f"""
        <div class="nf-hero">
            <div class="nf-kicker">NovelForge</div>
            <div class="nf-title">{page_label}</div>
            <div class="nf-header-meta">
                <span>作品 <b>{title}</b></span>
                <span>项目 <b>{project_label}</b></span>
                <span>类型 <b>{genre}</b></span>
                <span>原作对齐 <b>{canon_mode}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

