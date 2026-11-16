"""Estilo visual (CSS) do dashboard.

As cores de superfície e borda são translúcidas e o texto herda a cor do tema,
para o painel ficar legível tanto no modo claro quanto no escuro.
"""

import streamlit as st

_CSS = """
<style>
:root {
    --marca: #2563eb;
    --marca-2: #7c3aed;
    --critico: #ef4444;
    --alerta: #f59e0b;
    --positivo: #10b981;
    --superficie: rgba(148, 163, 184, 0.10);
    --superficie-forte: rgba(148, 163, 184, 0.16);
    --borda: rgba(148, 163, 184, 0.28);
    --sombra: 0 8px 24px -12px rgba(15, 23, 42, 0.35);
}

@keyframes surgir {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulsar {
    0%   { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }
    70%  { box-shadow: 0 0 0 9px rgba(52, 211, 153, 0); }
    100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
}
@keyframes deslizar-gradiente {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes flutuar {
    0%, 100% { transform: translate(0, 0) scale(1); }
    50%      { transform: translate(-18px, 14px) scale(1.08); }
}

/* Tipografia */
h1, h2, h3 { letter-spacing: -0.02em !important; font-weight: 700 !important; }
.block-container { padding-top: 2.2rem; }

/* Cabeçalho de destaque */
.hero {
    position: relative;
    overflow: hidden;
    border-radius: 20px;
    padding: 30px 34px;
    margin-bottom: 20px;
    color: #ffffff;
    background: linear-gradient(120deg, #1e3a8a, #2563eb, #7c3aed, #2563eb, #1e3a8a);
    background-size: 300% 300%;
    animation: deslizar-gradiente 18s ease infinite, surgir 0.6s ease both;
    box-shadow: 0 18px 40px -18px rgba(37, 99, 235, 0.65);
}
.hero-brilho {
    position: absolute;
    border-radius: 50%;
    filter: blur(50px);
    opacity: 0.45;
    animation: flutuar 12s ease-in-out infinite;
    pointer-events: none;
}
.hero-brilho--a { width: 260px; height: 260px; right: -60px; top: -110px; background: #a78bfa; }
.hero-brilho--b { width: 200px; height: 200px; right: 22%; bottom: -130px; background: #38bdf8; animation-delay: -6s; }
.hero-conteudo { position: relative; }
.hero-selo {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    padding: 5px 12px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.28);
}
.hero-titulo {
    font-size: clamp(1.5rem, 2.6vw, 2.25rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.15;
    margin: 14px 0 8px;
}
.hero-texto { font-size: 1rem; opacity: 0.88; max-width: 62ch; margin: 0 0 18px; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    padding: 6px 13px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.28);
    border: 1px solid rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(6px);
}
.pulso { width: 9px; height: 9px; border-radius: 50%; background: #34d399; animation: pulsar 1.8s infinite; }
.pulso--offline { background: #fbbf24; animation: none; }

/* Cartões de indicadores: 4 por linha, 2 em telas médias, 1 em telas estreitas */
.kpi-zona { container-type: inline-size; margin-bottom: 22px; }
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
@container (max-width: 760px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@container (max-width: 380px) { .kpi-grid { grid-template-columns: minmax(0, 1fr); } }
.kpi {
    position: relative;
    overflow: hidden;
    border-radius: 16px;
    padding: 18px 20px;
    background: var(--superficie);
    border: 1px solid var(--borda);
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    container-type: inline-size;
    animation: surgir 0.55s ease both;
}
.kpi::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 4px;
    background: var(--tom, var(--marca));
}
.kpi:hover { transform: translateY(-4px); box-shadow: var(--sombra); border-color: var(--tom, var(--marca)); }
.kpi:nth-child(2) { animation-delay: 0.07s; }
.kpi:nth-child(3) { animation-delay: 0.14s; }
.kpi:nth-child(4) { animation-delay: 0.21s; }
.kpi--marca    { --tom: var(--marca); }
.kpi--positivo { --tom: var(--positivo); }
.kpi--critico  { --tom: var(--critico); }
.kpi--alerta   { --tom: var(--alerta); }
.kpi-topo { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.kpi-icone {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: 10px;
    font-size: 1.1rem;
    background: color-mix(in srgb, var(--tom, var(--marca)) 18%, transparent);
}
.kpi-rotulo { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.7; }
.kpi-valor { font-size: clamp(1.15rem, 12.5cqi, 1.85rem); white-space: nowrap; font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; }
.kpi-detalhe { font-size: 0.84rem; opacity: 0.65; margin-top: 6px; }

/* Métricas nativas (usadas dentro das abas) */
div[data-testid="stMetric"] {
    background: var(--superficie);
    border: 1px solid var(--borda);
    border-radius: 14px;
    padding: 16px 18px;
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    animation: surgir 0.5s ease both;
}
div[data-testid="stMetric"]:hover { transform: translateY(-3px); box-shadow: var(--sombra); border-color: var(--marca); }
div[data-testid="stMetric"] label { font-weight: 700; font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.7; }
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] * { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-weight: 800; font-size: 1.5rem !important; letter-spacing: -0.02em; }

/* Banner de introdução de cada aba */
.tab-banner {
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(124, 58, 237, 0.10));
    border: 1px solid rgba(37, 99, 235, 0.25);
    border-left: 4px solid var(--marca);
    border-radius: 12px;
    padding: 13px 18px;
    margin-bottom: 22px;
    font-size: 0.94rem;
    line-height: 1.5;
    animation: surgir 0.45s ease both;
}

/* Abas em formato de pílula */
.stTabs [role="tablist"] {
    gap: 6px;
    padding: 6px;
    border-radius: 14px;
    background: var(--superficie);
    border: 1px solid var(--borda);
    margin-bottom: 16px;
}
.stTabs [role="tablist"]::after,
.stTabs [role="tablist"]::before,
.stTabs [role="tab"]::after,
.stTabs .react-aria-SelectionIndicator,
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }
.stTabs [role="tab"] {
    border-radius: 10px;
    padding: 8px 16px;
    height: auto;
    font-weight: 600;
    border: none !important;
    transition: background 0.2s ease, box-shadow 0.2s ease;
}
.stTabs [role="tab"]:hover { background: var(--superficie-forte); }
.stTabs [role="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, var(--marca), var(--marca-2));
    box-shadow: 0 6px 16px -8px rgba(37, 99, 235, 0.9);
}
.stTabs [role="tab"][aria-selected="true"] p { color: #ffffff !important; }

/* Gráficos, tabelas e painéis */
div[data-testid="stPlotlyChart"] {
    border-radius: 16px;
    border: 1px solid var(--borda);
    background: var(--superficie);
    overflow: hidden;
    transition: box-shadow 0.25s ease, border-color 0.25s ease;
    animation: surgir 0.6s ease both;
}
div[data-testid="stPlotlyChart"]:hover { box-shadow: var(--sombra); border-color: rgba(37, 99, 235, 0.45); }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; animation: surgir 0.6s ease both; }
div[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--borda); }
div[data-testid="stChatMessage"] {
    background: var(--superficie);
    border: 1px solid var(--borda);
    border-radius: 14px;
    animation: surgir 0.4s ease both;
}

/* Botões */
.stButton button, .stDownloadButton button {
    border-radius: 10px;
    font-weight: 600;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.stButton button:hover:not(:disabled), .stDownloadButton button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 8px 18px -10px rgba(37, 99, 235, 0.8);
    border-color: var(--marca);
}

/* Barra lateral */
section[data-testid="stSidebar"] { border-right: 1px solid var(--borda); }

/* Respeita quem prefere menos movimento */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


def aplicar_estilo() -> None:
    """Injeta o CSS customizado do painel."""
    st.markdown(_CSS, unsafe_allow_html=True)
