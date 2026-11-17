"""Componentes visuais reutilizáveis: cabeçalho de destaque e cartões de indicadores."""

from html import escape

import streamlit as st


def cabecalho(titulo: str, texto: str, conectado: bool, chips: list[str]) -> None:
    """Renderiza o cabeçalho com gradiente, status da conexão e etiquetas de contexto."""
    if conectado:
        status = '<span class="chip"><i class="pulso"></i>Ao vivo · PostgreSQL (Neon)</span>'
    else:
        status = '<span class="chip"><i class="pulso pulso--offline"></i>Snapshot local de contingência</span>'
    etiquetas = "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)

    st.markdown(
        '<div class="hero">'
        '<div class="hero-brilho hero-brilho--a"></div><div class="hero-brilho hero-brilho--b"></div>'
        '<div class="hero-conteudo">'
        '<span class="hero-selo">📦 Supply Intelligence</span>'
        f'<div class="hero-titulo" role="heading" aria-level="1">{escape(titulo)}</div>'
        f'<p class="hero-texto">{escape(texto)}</p>'
        f'<div class="hero-chips">{status}{etiquetas}</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )


# Partículas de cada efeito de hover (elementos <i> escondidos até a animação começar)
_PARTICULAS = {
    "caixa": ["📱", "🎧", "🔌"],    # eletrônicos que entram na caixa
    "moedas": ["🪙"] * 5,            # moedas caindo ao redor do saco
    "sirene": [""] * 8,              # raios de luz saindo da sirene
    "alerta": [],                    # o próprio triângulo cresce e vibra
}


def _icone(icone: str, efeito: str) -> str:
    particulas = "".join(f'<i class="fx">{p}</i>' for p in _PARTICULAS.get(efeito, []))
    return (
        f'<span class="kpi-icone fx-{escape(efeito)}">'
        f'<span class="kpi-glifo">{escape(icone)}</span>'
        f'<span class="fx-camada" aria-hidden="true">{particulas}</span>'
        "</span>"
    )


def cartoes_kpi(cartoes: list[dict]) -> None:
    """Renderiza uma grade responsiva de indicadores.

    Cada cartão é um dicionário com: icone, rotulo, valor, detalhe, tom
    ("marca", "positivo", "critico" ou "alerta") e efeito de hover
    ("caixa", "moedas", "sirene" ou "alerta").
    """
    blocos = "".join(
        f'<div class="kpi kpi--{escape(c.get("tom", "marca"))}">'
        f'<div class="kpi-topo">{_icone(c["icone"], c.get("efeito", ""))}'
        f'<span class="kpi-rotulo">{escape(c["rotulo"])}</span></div>'
        f'<div class="kpi-valor">{escape(str(c["valor"]))}</div>'
        f'<div class="kpi-detalhe">{escape(c.get("detalhe", ""))}</div>'
        "</div>"
        for c in cartoes
    )
    st.markdown(f'<div class="kpi-zona"><div class="kpi-grid">{blocos}</div></div>', unsafe_allow_html=True)
