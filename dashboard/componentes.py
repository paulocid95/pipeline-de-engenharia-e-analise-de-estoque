"""Componentes visuais reutilizáveis: cabeçalho de destaque e cartões de indicadores."""

from html import escape

import streamlit as st


def cabecalho(titulo: str, texto: str, conectado: bool | None, chips: list[str]) -> None:
    """Renderiza o cabeçalho com gradiente, status da conexão (None = sem status) e etiquetas de contexto."""
    if conectado is None:
        status = ""
    elif conectado:
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


def cartoes_fornecedores(ranking) -> None:
    """Cartões de alerta, um por fornecedor, na ordem do ranking.

    `ranking` vem de regras_fornecedores.ranking_fornecedores.
    """
    from dashboard.graficos import CORES_FORNECEDOR
    from regras_fornecedores import ICONE_CLASSE, ROTULO_CLASSE

    blocos = []
    for posicao, linha in enumerate(ranking.itertuples(), start=1):
        classe = str(linha.classe).lower()
        nota = float(linha.nota_final)
        cor = CORES_FORNECEDOR.get(linha.fornecedor, "#64748b")
        sem_solucao = int(linha.sem_solucao)
        meta = f"#{posicao} no ranking · {int(linha.ocorrencias_12m)} ocorrências em 12 meses"
        if sem_solucao:
            meta += f" · {sem_solucao} sem solução"
        blocos.append(
            f'<div class="forn forn--{escape(classe)}">'
            '<div class="forn-topo">'
            f'<span class="forn-nome"><i class="forn-cor" style="background:{escape(cor)}"></i>{escape(linha.fornecedor)}</span>'
            f'<span class="forn-selo">{ICONE_CLASSE[linha.classe]} {escape(ROTULO_CLASSE[linha.classe])}</span>'
            "</div>"
            f'<div class="forn-nota"><span class="forn-nota-valor">{nota:.0f}</span><span class="forn-nota-max">/100</span></div>'
            f'<div class="forn-barra" role="img" aria-label="Nota {nota:.0f} de 100"><span style="width:{nota:.0f}%"></span></div>'
            f'<div class="forn-motivo">{escape(linha.motivo)}</div>'
            f'<div class="forn-meta">{escape(meta)}</div>'
            "</div>"
        )
    st.markdown(f'<div class="forn-zona"><div class="forn-grid">{"".join(blocos)}</div></div>', unsafe_allow_html=True)
