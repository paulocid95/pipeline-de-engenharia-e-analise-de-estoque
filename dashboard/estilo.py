"""Estilo visual (CSS) do dashboard."""

import streamlit as st


def aplicar_estilo() -> None:
    """Injeta o CSS customizado (cards de métricas, banners e abas)."""
    st.markdown("""
    <style>
        /* Tipografia e títulos estilo SaaS */
        h1 {
            font-weight: 800 !important;
            letter-spacing: -0.025em !important;
            color: #0f172a !important;
        }
        h2, h3 {
            font-weight: 700 !important;
            letter-spacing: -0.015em !important;
            color: #1e293b !important;
        }

        /* Cards de métricas modernos */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 16px 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            transition: all 0.2s ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
            border-color: #cbd5e1;
        }
        div[data-testid="stMetric"] label {
            font-weight: 600;
            color: #64748b !important;
            font-size: 0.86rem !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-weight: 750;
            color: #0f172a !important;
            font-size: 1.6rem !important;
        }

        /* Banners contextuais de introdução de abas */
        .tab-banner {
            background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
            border-left: 4px solid #2563eb;
            border-radius: 8px;
            padding: 12px 18px;
            margin-bottom: 22px;
            color: #334155;
            font-size: 0.94rem;
            line-height: 1.5;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
        }
        .tab-banner strong {
            color: #0f172a;
        }

        /* Abas estilizadas */
        button[data-baseweb="tab"] {
            font-size: 0.98rem;
            font-weight: 600;
            padding: 10px 18px;
        }
    </style>
    """, unsafe_allow_html=True)
