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
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(255,255,255,0.96), rgba(246,247,251,0.98)),
                var(--nf-bg);
            color: var(--nf-text);
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
            padding-top: 1rem;
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
            display: inline-flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.25rem;
            min-height: 2rem;
            padding: 0.28rem 0.7rem;
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            background: var(--nf-panel-soft);
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
            min-height: 7.25rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 0.55rem;
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

        @media (max-width: 760px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .nf-hero {
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

