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
            --nf-bg: #f6f7fb;
            --nf-panel: #ffffff;
            --nf-panel-soft: #f9fafb;
            --nf-border: #dde3eb;
            --nf-text: #172033;
            --nf-muted: #667085;
            --nf-accent: #356ac3;
            --nf-accent-strong: #244f9e;
            --nf-accent-soft: #edf4ff;
            --nf-green: #3f7d68;
            --nf-warm: #a86618;
            --nf-danger: #b42318;
            --nf-shadow: 0 14px 36px rgba(16, 24, 40, 0.08);
            --nf-shadow-soft: 0 8px 22px rgba(16, 24, 40, 0.05);
            --nf-page-top-offset: 0.75rem;
            --nf-top-safe-space: 0.85rem;
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(255,255,255,0.96), rgba(246,247,251,0.98)),
                var(--nf-bg);
            color: var(--nf-text);
        }

        .stApp *,
        .stApp *::before,
        .stApp *::after {
            box-sizing: border-box;
        }

        #MainMenu,
        footer,
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
        }

        [data-testid="stSidebar"] {
            background: #f8fafc;
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
            max-width: 1240px;
            padding-top: var(--nf-page-top-offset);
            padding-bottom: 4rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        h2, h3 {
            margin-top: 0.55rem;
            margin-bottom: 0.45rem;
        }

        hr {
            margin: 1.2rem 0;
            border-color: var(--nf-border);
        }

        div[data-testid="stMetric"] {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 0.95rem 1rem;
            box-shadow: var(--nf-shadow-soft);
        }

        div[data-testid="stMetric"] label {
            color: var(--nf-muted);
        }

        .nf-hero {
            background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
            border: 1px solid var(--nf-border);
            border-left: 4px solid var(--nf-accent);
            border-radius: 8px;
            padding: 1rem 1.1rem 0.95rem;
            box-shadow: var(--nf-shadow-soft);
            margin-top: var(--nf-top-safe-space) !important;
            margin-bottom: 1rem;
        }

        .nf-kicker {
            color: var(--nf-accent-strong);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.25rem;
        }

        .nf-title {
            color: var(--nf-text);
            font-size: 1.35rem;
            line-height: 1.25;
            font-weight: 750;
            margin: 0;
        }

        .nf-subtitle {
            color: var(--nf-muted);
            margin-top: 0.35rem;
            margin-bottom: 0;
            line-height: 1.55;
        }

        .nf-header-meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));
            gap: 0.45rem;
            margin-top: 0.75rem;
        }

        .nf-header-meta span {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            align-items: center;
            gap: 0.45rem;
            min-width: 0;
            min-height: 2rem;
            padding: 0.28rem 0.7rem;
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            background: var(--nf-panel-soft);
            color: var(--nf-muted);
            font-size: 0.82rem;
            line-height: 1.25;
            white-space: nowrap;
        }

        .nf-header-meta b {
            min-width: 0;
            color: var(--nf-text);
            font-weight: 650;
            text-align: right;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .nf-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 0.8rem;
            margin: 1rem 0;
        }

        .nf-card {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: var(--nf-shadow-soft);
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

        .nf-section-heading {
            margin: 1.15rem 0 0.65rem;
            padding-top: 0.15rem;
        }

        .nf-section-title {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: var(--nf-text);
            font-size: 1rem;
            font-weight: 750;
            line-height: 1.35;
            margin: 0;
        }

        .nf-section-title::before {
            content: "";
            width: 0.22rem;
            height: 1rem;
            border-radius: 8px;
            background: var(--nf-accent);
            display: inline-block;
        }

        .nf-section-caption {
            color: var(--nf-muted);
            font-size: 0.9rem;
            line-height: 1.55;
            margin-top: 0.25rem;
        }

        .nf-action-card-body {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            margin-bottom: 0.75rem;
        }

        .nf-action-title {
            color: var(--nf-text);
            font-size: 1rem;
            font-weight: 750;
            line-height: 1.35;
        }

        .nf-action-copy {
            color: var(--nf-muted);
            font-size: 0.9rem;
            line-height: 1.55;
        }

        .nf-status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.65rem;
            margin-top: 0.75rem;
        }

        .nf-status-item {
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            background: var(--nf-panel-soft);
            padding: 0.7rem 0.8rem;
        }

        .nf-status-label {
            color: var(--nf-muted);
            font-size: 0.78rem;
            line-height: 1.25;
            margin-bottom: 0.25rem;
        }

        .nf-status-value {
            color: var(--nf-text);
            font-size: 0.94rem;
            font-weight: 700;
            line-height: 1.35;
            overflow-wrap: anywhere;
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

        .stApp .stMultiSelect {
            margin-bottom: 0.85rem;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div {
            align-items: flex-start !important;
            min-height: 2.75rem !important;
            max-height: 8.75rem !important;
            padding: 0.35rem 2.7rem 0.35rem 0.55rem !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div > div {
            align-items: flex-start !important;
            align-content: flex-start !important;
            row-gap: 0.18rem !important;
            max-width: 100% !important;
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

        html body .stApp .stMultiSelect [data-baseweb="select"] > div {
            align-items: flex-start !important;
            min-height: 2.75rem !important;
            max-height: 8.75rem !important;
            padding: 0.35rem 2.7rem 0.35rem 0.65rem !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] > div > div {
            align-items: flex-start !important;
            align-content: flex-start !important;
            row-gap: 0.18rem !important;
            max-width: 100% !important;
            overflow: visible !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            max-width: 100% !important;
            margin-left: 0.45rem !important;
            padding-left: 0.78rem !important;
            overflow: hidden !important;
        }

        .nf-discussion-brief {
            display: grid;
            gap: 0.5rem;
            margin: 0.15rem 0 0.78rem;
            padding: 0.72rem 0.78rem;
            border: 1px solid #dbe5f2;
            border-radius: 8px;
            background: #f8fbff;
        }

        .nf-discussion-brief-title {
            color: var(--nf-accent-strong);
            font-size: 0.84rem;
            font-weight: 750;
            line-height: 1.3;
        }

        .nf-discussion-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.38rem;
        }

        .nf-discussion-chip {
            display: inline-flex;
            align-items: center;
            min-height: 1.78rem;
            padding: 0.18rem 0.58rem;
            border: 1px solid #d5deea;
            border-radius: 8px;
            background: #ffffff;
            color: var(--nf-text);
            font-size: 0.86rem;
            line-height: 1.35;
        }

        .nf-discussion-impact {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            gap: 0.45rem;
            align-items: start;
            color: var(--nf-muted);
            font-size: 0.86rem;
            line-height: 1.45;
        }

        .nf-discussion-impact span {
            color: var(--nf-muted);
            font-weight: 650;
            white-space: nowrap;
        }

        .nf-discussion-impact b {
            color: var(--nf-text);
            font-weight: 650;
            overflow-wrap: anywhere;
        }

        .nf-discussion-note {
            color: var(--nf-muted);
            font-size: 0.86rem;
            line-height: 1.45;
        }

        .nf-discussion-empty-hint {
            margin: 0.72rem 0 0.72rem !important;
            color: var(--nf-muted);
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .stApp [class*="st-key-nf-discussion-shell-"] {
            display: block;
            margin: 0.85rem 0 1.2rem;
        }

        .stApp [class*="st-key-nf-discussion-input-"] > div,
        .stApp [class*="st-key-nf-discussion-output-"] > div,
        .stApp [class*="st-key-nf-discussion-input-"] [data-testid="stVerticalBlockBorderWrapper"],
        .stApp [class*="st-key-nf-discussion-output-"] [data-testid="stVerticalBlockBorderWrapper"] {
            width: 100% !important;
            max-width: none !important;
            min-width: 0 !important;
        }
        .stApp [class*="st-key-nf-discussion-input-"] {
            position: relative;
            z-index: 1;
            overflow: visible;
            background: rgba(255, 255, 255, 0.98) !important;
            box-shadow: 0 12px 28px rgba(16, 24, 40, 0.08) !important;
        }
        .stApp [class*="st-key-nf-discussion-output-"] {
            max-height: 68vh;
            overflow-y: auto;
            scrollbar-gutter: stable;
            background: #ffffff !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] textarea {
            min-height: 5rem !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] [data-testid="stTextArea"] {
            padding: 0.1rem 0.1rem 0.28rem;
        }

        .stApp [data-baseweb="textarea"] {
            width: 100%;
            overflow: visible !important;
        }

        .stApp [data-baseweb="textarea"] > div {
            border: 1px solid var(--nf-border) !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: none !important;
            overflow: visible !important;
        }

        .stApp [data-baseweb="textarea"]:focus-within > div {
            border-color: var(--nf-accent) !important;
            box-shadow: 0 0 0 2px rgba(53, 106, 195, 0.12) !important;
        }

        .stApp [data-baseweb="textarea"] textarea,
        .stApp [data-baseweb="textarea"] textarea:focus {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            outline: 0 !important;
        }

        .stApp [class*="st-key-nf-discussion-output-"] .stChatMessage,
        .stApp [class*="st-key-nf-discussion-input-"] .stChatMessage {
            margin-bottom: 0.55rem;
        }

        .stApp [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--nf-border) !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: var(--nf-shadow-soft);
        }

        .stApp [data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: #c5d1e0 !important;
        }

        .stApp [data-baseweb="tab-list"] {
            gap: 0.35rem;
            background: #eef2f6;
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 0.25rem;
        }

        .stApp [data-baseweb="tab"] {
            border-radius: 8px;
            color: var(--nf-muted) !important;
            font-weight: 650;
            min-height: 2.35rem;
        }

        .stApp [aria-selected="true"][data-baseweb="tab"] {
            background: #ffffff;
            color: var(--nf-accent-strong) !important;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.08);
        }

        .stApp input,
        .stApp textarea,
        .stApp [data-baseweb="select"] > div {
            border-radius: 8px !important;
            min-height: 2.45rem !important;
            box-shadow: none !important;
        }

        .stApp textarea {
            line-height: 1.6 !important;
        }

        .stApp input:focus,
        .stApp textarea:focus,
        .stApp [data-baseweb="select"] > div:focus-within {
            border-color: var(--nf-accent) !important;
            box-shadow: 0 0 0 2px rgba(53, 106, 195, 0.12) !important;
        }

        .stApp .stButton button,
        .stApp [data-testid="stButton"] button,
        .stApp [data-testid="stFormSubmitButton"] button,
        .stApp button[data-testid^="stBaseButton"] {
            min-height: 2.45rem;
            font-weight: 650 !important;
            transition: border-color 120ms ease, background 120ms ease, color 120ms ease, transform 120ms ease;
        }

        .stApp .stButton button:hover,
        .stApp [data-testid="stButton"] button:hover,
        .stApp [data-testid="stFormSubmitButton"] button:hover,
        .stApp button[data-testid^="stBaseButton"]:hover {
            transform: translateY(-1px);
        }

        [data-testid="stSidebar"] [role="radiogroup"] label {
            border-radius: 8px;
            padding: 0.32rem 0.45rem;
        }

        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: #edf4ff;
            color: var(--nf-accent-strong) !important;
            font-weight: 700;
        }


        [data-testid="stSidebar"] label[data-baseweb="radio"]:not(:has(input:checked)) > div:first-child,
        [data-testid="stSidebar"] [role="radiogroup"] label:not(:has(input:checked)) > div:first-child {
            background: #ffffff !important;
            border: 1.5px solid #111827 !important;
        }

        [data-testid="stSidebar"] hr {
            margin: 0.85rem 0;
        }

        div[data-testid="stExpander"] {
            margin: 0.65rem 0;
            box-shadow: var(--nf-shadow-soft);
        }

        div[data-testid="stExpander"] details > summary {
            min-height: 2.55rem;
            align-items: center;
        }


        /* UI polish pass */
        .stApp {
            --nf-border-strong: #cbd5e1;
            --nf-panel-hover: #fbfdff;
            --nf-control-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
            --nf-control-shadow-hover: 0 8px 18px rgba(16, 24, 40, 0.08);
        }

        .block-container > div {
            gap: 0.72rem;
        }

        .nf-section-heading {
            margin: 1.35rem 0 0.72rem;
            padding: 0.15rem 0 0.1rem;
        }

        .nf-section-title {
            font-size: 1.03rem;
            letter-spacing: 0;
        }

        .nf-section-caption {
            max-width: 72rem;
            color: #6b7280;
        }

        html body .stApp button[data-testid^="stBaseButton"],
        html body .stApp [data-testid="stButton"] button,
        html body .stApp [data-testid="stFormSubmitButton"] button,
        .stApp .stButton > button {
            min-height: 2.58rem !important;
            padding: 0.48rem 0.85rem !important;
            border-radius: 8px !important;
            border-color: var(--nf-border-strong) !important;
            background: linear-gradient(180deg, #ffffff 0%, #f9fbfd 100%) !important;
            box-shadow: var(--nf-control-shadow) !important;
            line-height: 1.25 !important;
            white-space: normal !important;
        }

        html body .stApp button[data-testid^="stBaseButton"] p,
        html body .stApp [data-testid="stButton"] button p,
        html body .stApp [data-testid="stFormSubmitButton"] button p,
        .stApp .stButton > button p {
            line-height: 1.25 !important;
            margin: 0 !important;
        }

        html body .stApp button[data-testid^="stBaseButton"]:hover,
        html body .stApp [data-testid="stButton"] button:hover,
        html body .stApp [data-testid="stFormSubmitButton"] button:hover,
        .stApp .stButton > button:hover {
            background: var(--nf-panel-hover) !important;
            border-color: var(--nf-accent) !important;
            color: var(--nf-accent-strong) !important;
            box-shadow: var(--nf-control-shadow-hover) !important;
            transform: translateY(-1px);
        }

        html body .stApp button[data-testid^="stBaseButton"][kind="primary"],
        html body .stApp button[data-testid^="stBaseButton"][data-kind="primary"],
        .stApp [data-testid="stButton"] button[kind="primary"],
        .stApp [data-testid="stButton"] button[data-kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"],
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"] {
            background: linear-gradient(180deg, var(--nf-accent) 0%, var(--nf-accent-strong) 100%) !important;
            border-color: var(--nf-accent-strong) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(53, 106, 195, 0.22) !important;
        }

        html body .stApp button[data-testid^="stBaseButton"][kind="primary"]:hover,
        html body .stApp button[data-testid^="stBaseButton"][data-kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[kind="primary"]:hover,
        .stApp [data-testid="stButton"] button[data-kind="primary"]:hover,
        .stApp [data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
        .stApp [data-testid="stFormSubmitButton"] button[data-kind="primary"]:hover {
            background: linear-gradient(180deg, #315fb0 0%, #244f9e 100%) !important;
            box-shadow: 0 10px 22px rgba(53, 106, 195, 0.28) !important;
        }

        html body .stApp button[data-testid^="stBaseButton"]:disabled,
        html body .stApp button[data-testid^="stBaseButton"][disabled],
        .stApp [data-testid="stButton"] button:disabled,
        .stApp [data-testid="stFormSubmitButton"] button:disabled {
            box-shadow: none !important;
            transform: none !important;
        }

        div[data-testid="stExpander"] {
            border-color: var(--nf-border-strong) !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: 0 8px 22px rgba(16, 24, 40, 0.055) !important;
            margin: 0.82rem 0 !important;
        }

        div[data-testid="stExpander"] details > summary {
            min-height: 2.85rem !important;
            padding: 0.62rem 0.85rem !important;
            background: linear-gradient(180deg, #fbfcfe 0%, #f7f9fc 100%) !important;
            border-bottom: 1px solid transparent !important;
        }

        div[data-testid="stExpander"] details > summary:hover {
            background: #f3f7fd !important;
        }

        div[data-testid="stExpander"] details[open] > summary {
            background: #edf4ff !important;
            border-bottom-color: #d7e2f0 !important;
        }

        div[data-testid="stExpander"] details > summary p,
        div[data-testid="stExpander"] details > summary span {
            font-weight: 720 !important;
            line-height: 1.35 !important;
        }

        div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            padding: 0.85rem 1rem 1rem !important;
            background: #ffffff !important;
        }

        .stApp [data-testid="stStatus"] {
            border: 1px solid #d8e2ee !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: 0 10px 24px rgba(16, 24, 40, 0.065) !important;
            overflow: hidden !important;
        }

        .stApp [data-testid="stStatus"] details > summary {
            min-height: 2.85rem !important;
            background: #f7faff !important;
            border-bottom: 1px solid #e3eaf3 !important;
            font-weight: 720 !important;
        }

        .stApp [data-testid="stStatus"] [data-testid="stMarkdownContainer"] p {
            line-height: 1.55 !important;
        }

        .stApp [class*="st-key-nf-discussion-shell-"] {
            display: grid !important;
            gap: 0.78rem !important;
            width: 100% !important;
            max-width: none !important;
            justify-self: stretch !important;
            margin: 0.9rem 0 1.25rem !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"],
        .stApp [class*="st-key-nf-discussion-output-"] {
            display: block !important;
            box-sizing: border-box !important;
            width: 100% !important;
            max-width: none !important;
            min-width: 0 !important;
            justify-self: stretch !important;
            align-self: stretch !important;
            padding: 1.2rem 1.35rem !important;
            border: 1px solid #d6dee9 !important;
            border-radius: 8px !important;
            box-shadow: 0 10px 26px rgba(16, 24, 40, 0.06) !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            overflow: visible !important;
        }

        .stApp [class*="st-key-nf-discussion-output-"] {
            background: #ffffff !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] h5,
        .stApp [class*="st-key-nf-discussion-output-"] h5,
        .stApp [class*="st-key-nf-discussion-output-"] h3 {
            margin-top: 0.1rem !important;
            margin-bottom: 0.55rem !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #e0e7f0 !important;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.68) !important;
            background: #fbfdff !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] div[data-testid="stChatMessage"],
        .stApp [class*="st-key-nf-discussion-output-"] div[data-testid="stChatMessage"],
        .stApp [class*="st-key-nf-discussion-input-"] .stChatMessage,
        .stApp [class*="st-key-nf-discussion-output-"] .stChatMessage {
            border: 1px solid #e3eaf3 !important;
            border-radius: 8px !important;
            background: #fbfdff !important;
            padding: 0.62rem 0.72rem !important;
            margin-bottom: 0.58rem !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"] textarea {
            min-height: 6.25rem !important;
        }

        .stApp [data-baseweb="textarea"] > div,
        .stApp input,
        .stApp [data-baseweb="select"] > div {
            border-color: #d5deea !important;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035) !important;
        }

        .stApp [data-baseweb="textarea"]:focus-within > div,
        .stApp input:focus,
        .stApp [data-baseweb="select"] > div:focus-within {
            border-color: var(--nf-accent) !important;
            box-shadow: 0 0 0 3px rgba(53, 106, 195, 0.13) !important;
        }

        .stApp [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #d9e2ec !important;
            box-shadow: 0 8px 22px rgba(16, 24, 40, 0.052) !important;
        }

        .stApp [data-baseweb="tab-list"] {
            background: #f0f4f8 !important;
            border-color: #d8e2ee !important;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.55) !important;
        }

        .stApp [data-baseweb="tab"] {
            min-height: 2.45rem !important;
            padding: 0.35rem 0.82rem !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div {
            align-items: center !important;
            min-height: 2.8rem !important;
            max-height: 8.75rem !important;
            padding: 0.38rem 2.7rem 0.38rem 0.62rem !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div > div {
            display: flex !important;
            flex-wrap: wrap !important;
            align-items: center !important;
            align-content: center !important;
            gap: 0.38rem 0.48rem !important;
            min-height: 1.9rem !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            order: 1 !important;
            display: inline-flex !important;
            align-items: center !important;
            flex: 0 0 auto !important;
            min-width: 0 !important;
            max-width: 100% !important;
            min-height: 1.88rem !important;
            height: 1.88rem !important;
            margin: 0 !important;
            padding: 0 0.54rem 0 0.7rem !important;
            line-height: 1.88rem !important;
            overflow: hidden !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] *,
        .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] span,
        .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] button {
            line-height: 1.2 !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div > div > div:not([data-baseweb="tag"]) {
            order: 2 !important;
            display: flex !important;
            align-items: center !important;
            flex: 1 0 6.5rem !important;
            min-width: 4rem !important;
            min-height: 1.88rem !important;
            height: 1.88rem !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] input,
        .stApp .stMultiSelect [data-baseweb="select"] input:focus {
            width: 100% !important;
            min-height: 1.88rem !important;
            height: 1.88rem !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            outline: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            line-height: 1.88rem !important;
        }
        .stApp pre,
        .stApp .stCodeBlock pre,
        .stApp [data-testid="stCodeBlock"] pre {
            background: #f8fafc !important;
            border-color: #d9e2ec !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
        }

        /* Final alignment pass: keep Streamlit wrappers from shrinking to content width. */
        .stApp [data-testid="stVerticalBlock"],
        .stApp [data-testid="stVerticalBlock"] > div,
        .stApp [data-testid="stHorizontalBlock"],
        .stApp [data-testid="stElementContainer"],
        .stApp [data-testid="stVerticalBlockBorderWrapper"],
        .stApp [data-testid="stVerticalBlockBorderWrapper"] > div,
        .stApp [data-testid="stForm"],
        .stApp [data-testid="stForm"] > div,
        .stApp [data-testid="stTextArea"],
        .stApp [data-testid="stTextInput"],
        .stApp [data-testid="stSelectbox"],
        .stApp [data-testid="stMultiSelect"],
        .stApp .stMultiSelect {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
        }

        .stApp [data-testid="column"],
        .stApp [data-testid="column"] > div {
            min-width: 0 !important;
            max-width: 100% !important;
        }

        .stApp [data-testid="stVerticalBlock"] {
            align-items: stretch !important;
        }

        .stApp [data-testid="stButton"],
        .stApp [data-testid="stFormSubmitButton"] {
            min-width: 0 !important;
            max-width: 100% !important;
        }

        html body .stApp button[data-testid^="stBaseButton"],
        html body .stApp [data-testid="stButton"] button,
        html body .stApp [data-testid="stFormSubmitButton"] button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.38rem !important;
            text-align: center !important;
            vertical-align: middle !important;
            overflow-wrap: anywhere !important;
        }

        html body .stApp button[data-testid^="stBaseButton"] p,
        html body .stApp [data-testid="stButton"] button p,
        html body .stApp [data-testid="stFormSubmitButton"] button p {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: 1.2em !important;
            margin: 0 !important;
            text-align: center !important;
        }

        .stApp [class*="st-key-nf-discussion-shell-"],
        .stApp [class*="st-key-nf-discussion-shell-"] > div,
        .stApp [class*="st-key-nf-discussion-shell-"] [data-testid="stVerticalBlock"],
        .stApp [class*="st-key-nf-discussion-shell-"] [data-testid="stVerticalBlock"] > div,
        .stApp [class*="st-key-nf-discussion-shell-"] [data-testid="stElementContainer"],
        .stApp [class*="st-key-nf-discussion-input-"],
        .stApp [class*="st-key-nf-discussion-output-"],
        .stApp [class*="st-key-nf-discussion-input-"] > div,
        .stApp [class*="st-key-nf-discussion-output-"] > div,
        .stApp [class*="st-key-nf-discussion-input-"] [data-testid="stVerticalBlockBorderWrapper"],
        .stApp [class*="st-key-nf-discussion-output-"] [data-testid="stVerticalBlockBorderWrapper"] {
            width: 100% !important;
            inline-size: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            max-inline-size: 100% !important;
            flex: 1 1 auto !important;
            justify-self: stretch !important;
            align-self: stretch !important;
        }

        .stApp [data-testid="stElementContainer"]:has([class*="st-key-nf-discussion-shell-"]),
        .stApp [data-testid="stElementContainer"]:has([class*="st-key-nf-discussion-input-"]),
        .stApp [data-testid="stElementContainer"]:has([class*="st-key-nf-discussion-output-"]),
        .stApp [data-testid="stVerticalBlock"]:has([class*="st-key-nf-discussion-shell-"]),
        .stApp [data-testid="stVerticalBlock"]:has([class*="st-key-nf-discussion-input-"]),
        .stApp [data-testid="stVerticalBlock"]:has([class*="st-key-nf-discussion-output-"]) {
            display: block !important;
            width: 100% !important;
            inline-size: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            max-inline-size: 100% !important;
            flex: 1 1 auto !important;
            align-self: stretch !important;
            justify-self: stretch !important;
        }
        .stApp [class*="st-key-nf-discussion-shell-"] {
            margin-top: 0.7rem !important;
            margin-bottom: 1rem !important;
        }

        .stApp [class*="st-key-nf-discussion-input-"],
        .stApp [class*="st-key-nf-discussion-output-"] {
            overflow: visible !important;
        }

        .stApp [class*="st-key-nf-discussion-output-"] {
            overflow-y: auto !important;
        }

        .nf-discussion-brief {
            gap: 0.42rem !important;
            margin: 0.1rem 0 0.65rem !important;
            padding: 0.62rem 0.68rem !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div {
            align-items: center !important;
            padding-left: 0.7rem !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div > div {
            align-items: center !important;
            align-content: center !important;
            gap: 0.38rem 0.48rem !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] > div > div div:not([data-baseweb="tag"]) {
            border: 0 !important;
            outline: 0 !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        html body .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            margin: 0 !important;
            transform: none !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 1.18rem !important;
            height: 1.18rem !important;
            min-width: 1.18rem !important;
            min-height: 1.18rem !important;
            margin-left: 0.28rem !important;
            padding: 0 !important;
        }

        .stApp .stMultiSelect [data-baseweb="select"] input,
        .stApp .stMultiSelect [data-baseweb="select"] input:focus {
            border: 0 !important;
            outline: 0 !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        /* Main content vertical rhythm: keep labels, controls, and button text optically centered. */
        .stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] {
            min-height: 1.28rem !important;
            margin: 0 0 0.3rem !important;
            display: flex !important;
            align-items: flex-end !important;
            line-height: 1.28 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
        .stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] label,
        .stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] span {
            margin: 0 !important;
            line-height: 1.28 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stTextInput"],
        .stApp [data-testid="stMain"] [data-testid="stNumberInput"],
        .stApp [data-testid="stMain"] [data-testid="stSelectbox"],
        .stApp [data-testid="stMain"] [data-testid="stTextArea"],
        .stApp [data-testid="stMain"] [data-testid="stMultiSelect"] {
            margin-bottom: 0.48rem !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stTextInput"]),
        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stNumberInput"]),
        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stSelectbox"]),
        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stTextArea"]),
        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stMultiSelect"]) {
            padding-bottom: 0.42rem !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stTextInput"] input,
        .stApp [data-testid="stMain"] [data-testid="stNumberInput"] input {
            min-height: 2.56rem !important;
            padding-top: 0.58rem !important;
            padding-bottom: 0.58rem !important;
            line-height: 1.34 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            min-height: 2.56rem !important;
            display: flex !important;
            align-items: center !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
            align-items: center !important;
            min-height: 1.4rem !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stNumberInput"] button {
            min-height: 2.56rem !important;
            align-items: center !important;
            justify-content: center !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stTextArea"] [data-baseweb="textarea"] > div {
            align-items: flex-start !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stTextArea"] textarea {
            padding-top: 0.78rem !important;
            padding-bottom: 0.78rem !important;
            line-height: 1.55 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stButton"],
        .stApp [data-testid="stMain"] [data-testid="stFormSubmitButton"] {
            margin-top: 0.08rem !important;
            margin-bottom: 0.52rem !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stButton"]),
        .stApp [data-testid="stMain"] [data-testid="stElementContainer"]:has(> [data-testid="stFormSubmitButton"]) {
            padding-top: 0.08rem !important;
            padding-bottom: 0.5rem !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stButton"] button,
        .stApp [data-testid="stMain"] [data-testid="stFormSubmitButton"] button,
        .stApp [data-testid="stMain"] button[data-testid^="stBaseButton"] {
            min-height: 2.56rem !important;
            padding-top: 0.56rem !important;
            padding-bottom: 0.56rem !important;
            line-height: 1.24 !important;
        }

        .stApp [data-testid="stMain"] [data-testid="stButton"] button p,
        .stApp [data-testid="stMain"] [data-testid="stFormSubmitButton"] button p,
        .stApp [data-testid="stMain"] button[data-testid^="stBaseButton"] p {
            line-height: 1.24 !important;
        }

        .stApp [data-testid="stMain"] [class*="st-key-nf-discussion-input-"] {
            padding-top: 1.15rem !important;
            padding-bottom: 1.18rem !important;
        }

        .stApp [data-testid="stMain"] [class*="st-key-nf-discussion-input-"] [data-testid="stTextArea"] {
            margin-bottom: 0.55rem !important;
        }

        @media (max-width: 760px) {
            .block-container {
                padding-top: 0.65rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .nf-discussion-impact {
                grid-template-columns: 1fr;
                gap: 0.12rem;
            }
            .stApp [class*="st-key-nf-discussion-input-"] {
                overflow: visible;
            }
            .stApp [class*="st-key-nf-discussion-output-"] {
                max-height: 62vh;
            }

            .nf-hero {
                margin-top: 0.75rem !important;
                padding: 0.85rem;
            }

            .nf-title {
                font-size: 1.2rem;
            }

            .nf-header-meta {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_app_header(project_name: str | None, page: str, memory: dict | None):
    try:
        from ui.navigation import PAGE_DESCRIPTIONS
    except Exception:
        PAGE_DESCRIPTIONS = {}

    title = html.escape(str((memory or {}).get("title") or project_name or "未选择项目"))
    genre = html.escape(str((memory or {}).get("genre") or "未设置类型"))
    canon_mode = html.escape(str((memory or {}).get("canon_mode") or "未设置原作对齐"))
    page_label = html.escape(str(page))
    page_description = html.escape(str(PAGE_DESCRIPTIONS.get(page, "")))
    project_label = html.escape(str(project_name or "-"))
    st.markdown(
        f"""
        <div class="nf-hero">
            <div class="nf-kicker">NovelForge</div>
            <div class="nf-title">{page_label}</div>
            {f'<div class="nf-subtitle">{page_description}</div>' if page_description else ''}
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


def render_section_heading(title: str, caption: str = "") -> None:
    safe_title = html.escape(str(title))
    safe_caption = html.escape(str(caption or ""))
    st.markdown(
        f"""
        <div class="nf-section-heading">
            <div class="nf-section-title">{safe_title}</div>
            {f'<div class="nf-section-caption">{safe_caption}</div>' if safe_caption else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
