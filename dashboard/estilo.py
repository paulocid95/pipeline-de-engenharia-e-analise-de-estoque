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
@container (max-width: 280px) { .kpi-grid { grid-template-columns: minmax(0, 1fr); } }
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
.kpi-valor { font-size: clamp(1.05rem, 12.5cqi, 1.85rem); white-space: nowrap; font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; }
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
div[data-testid="stMetric"] [data-testid="stMetricDelta"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] * { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
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

/* ---------- Efeitos de hover dos ícones dos cartões ----------
   Cada animação roda uma vez ao passar o mouse e volta sozinha ao estado normal. */
.kpi-icone { position: relative; }
.kpi-glifo { display: inline-block; line-height: 1; }
.fx-camada { position: absolute; inset: 0; pointer-events: none; }
.fx-camada .fx {
    position: absolute;
    left: 50%;
    top: 50%;
    font-style: normal;
    font-size: 0.8rem;
    line-height: 1;
    opacity: 0;
    transform: translate(-50%, -50%);
}

/* Caixa (volume físico): a caixa abre e eletrônicos caem dentro dela */
@keyframes caixa-abrir {
    0%   { transform: scale(1); }
    12%  { transform: scale(1.15, 0.82); }
    26%  { transform: scale(0.92, 1.18) translateY(-3px); }
    40%  { transform: scale(1.05, 0.96); }
    55%  { transform: scale(1.08, 0.92) translateY(1px); }
    70%  { transform: scale(1.08, 0.92) translateY(1px); }
    85%  { transform: scale(1.08, 0.92) translateY(1px); }
    100% { transform: scale(1); }
}
@keyframes caixa-item {
    0%   { opacity: 0; transform: translate(calc(-50% + var(--x)), calc(-50% - 30px)) scale(1); }
    20%  { opacity: 1; }
    65%  { opacity: 1; transform: translate(calc(-50% + var(--x) * 0.3), calc(-50% - 4px)) scale(0.85) rotate(var(--r)); }
    100% { opacity: 0; transform: translate(-50%, -50%) scale(0.1); }
}
.fx-caixa .fx:nth-of-type(1) { --x: -9px; --r: -20deg; }
.fx-caixa .fx:nth-of-type(2) { --x: 9px;  --r: 18deg; }
.fx-caixa .fx:nth-of-type(3) { --x: 0px;  --r: 8deg; }
.kpi:hover .fx-caixa .kpi-glifo { animation: caixa-abrir 1.7s ease-in-out; }
.kpi:hover .fx-caixa .fx { animation: caixa-item 0.8s ease-in both; }
.kpi:hover .fx-caixa .fx:nth-of-type(1) { animation-delay: 0.35s; }
.kpi:hover .fx-caixa .fx:nth-of-type(2) { animation-delay: 0.65s; }
.kpi:hover .fx-caixa .fx:nth-of-type(3) { animation-delay: 0.95s; }

/* Saco de dinheiro (capital imobilizado): balança e moedas de ouro caem ao redor */
@keyframes saco-balancar {
    0%, 100% { transform: rotate(0) scale(1); }
    15% { transform: rotate(-12deg) scale(1.12); }
    30% { transform: rotate(10deg) scale(1.12); }
    45% { transform: rotate(-7deg) scale(1.08); }
    60% { transform: rotate(4deg) scale(1.04); }
    75% { transform: rotate(-2deg) scale(1); }
}
@keyframes moeda-cair {
    0%   { opacity: 0; transform: translate(calc(-50% + var(--x)), calc(-50% - 22px)) rotate(0); }
    15%  { opacity: 1; }
    75%  { opacity: 1; }
    100% { opacity: 0; transform: translate(calc(-50% + var(--x)), calc(-50% + 34px)) rotate(var(--r)); }
}
.fx-moedas .fx { font-size: 0.72rem; }
.fx-moedas .fx:nth-of-type(1) { --x: -24px; --r: 300deg; }
.fx-moedas .fx:nth-of-type(2) { --x: 22px;  --r: -280deg; }
.fx-moedas .fx:nth-of-type(3) { --x: -12px; --r: 240deg; }
.fx-moedas .fx:nth-of-type(4) { --x: 14px;  --r: -320deg; }
.fx-moedas .fx:nth-of-type(5) { --x: 28px;  --r: 360deg; }
.kpi:hover .fx-moedas .kpi-glifo { animation: saco-balancar 1.2s ease-in-out; }
.kpi:hover .fx-moedas .fx { animation: moeda-cair 1s cubic-bezier(0.5, 0, 0.9, 0.6) both; }
.kpi:hover .fx-moedas .fx:nth-of-type(2) { animation-delay: 0.15s; }
.kpi:hover .fx-moedas .fx:nth-of-type(3) { animation-delay: 0.3s; }
.kpi:hover .fx-moedas .fx:nth-of-type(4) { animation-delay: 0.45s; }
.kpi:hover .fx-moedas .fx:nth-of-type(5) { animation-delay: 0.6s; }

/* Sirene (produtos críticos): pisca em vermelho e solta raios de luz */
@keyframes sirene-piscar {
    0%, 25%, 50%, 75%, 100% { background: color-mix(in srgb, var(--critico) 18%, transparent); box-shadow: none; }
    12%, 37%, 62%, 87% { background: color-mix(in srgb, var(--critico) 70%, transparent); box-shadow: 0 0 16px 4px rgba(239, 68, 68, 0.7); }
}
@keyframes sirene-glifo {
    0%, 25%, 50%, 75%, 100% { transform: scale(1); filter: none; }
    12%, 37%, 62%, 87% { transform: scale(1.18); filter: drop-shadow(0 0 6px #ff3b3b) brightness(1.3); }
}
@keyframes sirene-raio {
    0%   { opacity: 0; transform: translate(-50%, -50%) rotate(var(--a)) translateY(-16px) scaleY(0.3); }
    35%  { opacity: 1; transform: translate(-50%, -50%) rotate(var(--a)) translateY(-24px) scaleY(1); }
    100% { opacity: 0; transform: translate(-50%, -50%) rotate(var(--a)) translateY(-31px) scaleY(0.4); }
}
.fx-sirene .fx { width: 2px; height: 7px; border-radius: 2px; background: #f87171; box-shadow: 0 0 4px #ef4444; }
.fx-sirene .fx:nth-of-type(1) { --a: 0deg; }
.fx-sirene .fx:nth-of-type(2) { --a: 45deg; }
.fx-sirene .fx:nth-of-type(3) { --a: 90deg; }
.fx-sirene .fx:nth-of-type(4) { --a: 135deg; }
.fx-sirene .fx:nth-of-type(5) { --a: 180deg; }
.fx-sirene .fx:nth-of-type(6) { --a: 225deg; }
.fx-sirene .fx:nth-of-type(7) { --a: 270deg; }
.fx-sirene .fx:nth-of-type(8) { --a: 315deg; }
.kpi:hover .kpi-icone.fx-sirene { animation: sirene-piscar 1.6s linear; }
.kpi:hover .fx-sirene .kpi-glifo { animation: sirene-glifo 1.6s linear; }
.kpi:hover .fx-sirene .fx { animation: sirene-raio 0.8s ease-out 2; }

/* Triângulo (produtos em alerta): cresce, vibra e volta ao tamanho normal */
@keyframes alerta-tremer {
    0%   { transform: scale(1) rotate(0); }
    14%  { transform: scale(1.4) rotate(0); }
    20%  { transform: scale(1.4) rotate(-12deg); }
    26%  { transform: scale(1.4) rotate(12deg); }
    32%  { transform: scale(1.4) rotate(-10deg); }
    38%  { transform: scale(1.4) rotate(10deg); }
    44%  { transform: scale(1.4) rotate(-7deg); }
    50%  { transform: scale(1.4) rotate(7deg); }
    56%  { transform: scale(1.4) rotate(-3deg); }
    62%  { transform: scale(1.4) rotate(0); }
    100% { transform: scale(1) rotate(0); }
}
@keyframes alerta-brilho {
    0%, 100% { box-shadow: none; }
    15%, 60% { box-shadow: 0 0 14px 3px rgba(245, 158, 11, 0.65); }
}
.kpi:hover .kpi-icone.fx-alerta { animation: alerta-brilho 1.3s ease-in-out; }
.kpi:hover .fx-alerta .kpi-glifo { animation: alerta-tremer 1.3s ease-in-out; }

/* ---------- Cartões de alerta dos fornecedores (aba Ranking & Risco) ---------- */
.forn-zona { container-type: inline-size; margin-bottom: 24px; }
.forn-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
@container (max-width: 820px) { .forn-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@container (max-width: 480px) { .forn-grid { grid-template-columns: minmax(0, 1fr); } }
.forn {
    --classe: var(--alerta);
    position: relative;
    border-radius: 16px;
    padding: 16px 18px;
    background: var(--superficie);
    border: 1px solid var(--borda);
    border-top: 4px solid var(--classe);
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    animation: surgir 0.5s ease both;
}
.forn:hover { transform: translateY(-3px); box-shadow: var(--sombra); }
.forn--bom      { --classe: var(--positivo); }
.forn--medio    { --classe: var(--alerta); }
.forn--perigoso { --classe: var(--critico); animation: surgir 0.5s ease both, perigo 1.6s ease-in-out 0.5s 3; }
@keyframes perigo {
    0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    50%      { box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.35); }
}
.forn-topo { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.forn-nome { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; }
.forn-cor { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.forn-selo {
    font-size: 0.78rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 999px;
    white-space: nowrap;
    background: color-mix(in srgb, var(--classe) 16%, transparent);
    border: 1px solid color-mix(in srgb, var(--classe) 45%, transparent);
}
.forn-nota { display: flex; align-items: baseline; gap: 4px; }
.forn-nota-valor { font-size: 2rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; }
.forn-nota-max { font-size: 0.85rem; opacity: 0.6; }
.forn-barra { height: 6px; border-radius: 999px; background: var(--superficie-forte); margin: 10px 0 12px; overflow: hidden; }
.forn-barra span { display: block; height: 100%; border-radius: 999px; background: var(--classe); }
.forn-motivo { font-size: 0.88rem; line-height: 1.4; min-height: 2.5em; }
.forn-meta { font-size: 0.76rem; opacity: 0.6; margin-top: 8px; }

/* Celular e telas estreitas */
@media (max-width: 640px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    h2 { font-size: 1.35rem !important; }
    h3 { font-size: 1.15rem !important; }
    h5 { font-size: 1rem !important; }

    .hero { padding: 22px 18px; border-radius: 16px; margin-bottom: 14px; }
    .hero-selo { font-size: 0.66rem; }
    .hero-texto { font-size: 0.9rem; margin-bottom: 14px; }
    .chip { font-size: 0.74rem; padding: 5px 10px; }
    .hero-brilho--a { width: 180px; height: 180px; }
    .hero-brilho--b { display: none; }

    .kpi-grid { gap: 10px; }
    .kpi { padding: 14px 14px; border-radius: 14px; }
    .kpi-topo { gap: 8px; margin-bottom: 8px; }
    .kpi-icone { width: 30px; height: 30px; font-size: 0.95rem; border-radius: 8px; }
    .kpi-rotulo { font-size: 0.66rem; letter-spacing: 0.04em; }
    .kpi-detalhe { font-size: 0.74rem; }

    .tab-banner { font-size: 0.88rem; padding: 11px 14px; margin-bottom: 16px; }
    .stTabs [role="tab"] { padding: 7px 12px; font-size: 0.88rem; }

    /* Métricas nativas: duas por linha em vez de uma */
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) { flex-wrap: wrap; gap: 10px; }
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div[data-testid="stColumn"] {
        min-width: calc(50% - 5px) !important;
        flex: 1 1 calc(50% - 5px) !important;
        width: calc(50% - 5px) !important;
    }
    div[data-testid="stMetric"] { padding: 12px 14px; }
    div[data-testid="stMetric"] label { font-size: 0.68rem !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.2rem !important; }

    /* Alvos de toque confortáveis */
    .stButton button, .stDownloadButton button { min-height: 44px; }
}

/* Aviso de dados faltando (planilha enviada sem alguma aba) */
.falta {
    display: flex; gap: 14px; align-items: flex-start;
    padding: 16px 18px; margin: 4px 0 10px;
    border: 1px dashed var(--borda); border-left: 4px solid var(--marca);
    border-radius: 14px; background: var(--superficie);
    animation: surgir .5s ease both;
}
.falta-icone { font-size: 1.7rem; line-height: 1; }
.falta-titulo { font-weight: 700; font-size: 1.02rem; margin-bottom: 4px; }
.falta p { margin: 0 0 4px; font-size: .93rem; }
.falta-opc { opacity: .75; font-size: .88rem; }

/* Frase de privacidade do assistente de IA */
@keyframes ia-borda { to { --ia-giro: 360deg; } }
@keyframes ia-brilho { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes ia-cadeado {
    0%, 100% { transform: rotate(0) scale(1); }
    10% { transform: rotate(-14deg) scale(1.15); }
    20% { transform: rotate(12deg) scale(1.15); }
    30% { transform: rotate(0) scale(1); }
}
@property --ia-giro { syntax: "<angle>"; inherits: false; initial-value: 0deg; }
.ia-aviso {
    position: relative; isolation: isolate; display: flex; align-items: center; gap: 14px;
    padding: 16px 20px; margin: 6px 0 18px; border-radius: 16px;
    background: var(--superficie);
    box-shadow: 0 10px 34px -14px rgba(124, 58, 237, .55);
    animation: surgir .6s ease both;
}
/* Borda em gradiente girando: a máscara deixa o gradiente só na borda, o fundo segue o tema */
.ia-aviso::before {
    content: ""; position: absolute; inset: 0; z-index: -1; padding: 2px; border-radius: inherit;
    background: conic-gradient(from var(--ia-giro), #2563eb, #7c3aed, #ec4899, #f59e0b, #10b981, #2563eb);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ia-borda 4s linear infinite; pointer-events: none;
}
.ia-aviso-icone { font-size: 1.9rem; animation: ia-cadeado 3s ease-in-out infinite; }
.ia-aviso-texto {
    font-size: 1.08rem; font-weight: 600; line-height: 1.45;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899, #8b5cf6, #3b82f6);
    background-size: 300% 100%;
    -webkit-background-clip: text; background-clip: text; color: transparent;
    animation: ia-brilho 6s ease-in-out infinite;
}
.ia-aviso-texto b { font-weight: 800; }
@media (max-width: 640px) {
    .ia-aviso { padding: 13px 14px; gap: 10px; }
    .ia-aviso-texto { font-size: .96rem; }
}

/* Respeita quem prefere menos movimento */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


def aplicar_estilo() -> None:
    """Injeta o CSS customizado do painel."""
    st.markdown(_CSS, unsafe_allow_html=True)
