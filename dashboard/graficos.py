"""Tema único dos gráficos Plotly e paletas de cores do painel."""

import plotly.graph_objects as go
import streamlit as st

CORES_STATUS = {
    "CRITICO": "#ef4444",
    "ALERTA": "#f59e0b",
    "NORMAL": "#10b981",
    "EXCESSO": "#3b82f6",
}

# Paleta validada (scripts/validate_palette.js) para os modos claro e escuro e para
# daltonismo. Evita verde e vermelho, reservados às classes Bom e Perigoso.
CORES_FORNECEDOR = {
    "Fornecedor A": "#3987e5",  # azul
    "Fornecedor B": "#d95926",  # laranja
    "Fornecedor C": "#199e70",  # verde-água
    "Fornecedor D": "#c98500",  # âmbar
    "Fornecedor E": "#d55181",  # magenta
    "Fornecedor F": "#9085e9",  # violeta
}

COR_DESTAQUE = "#2563eb"
COR_NEUTRA = "#94a3b8"
_GRADE = "rgba(148, 163, 184, 0.22)"
_TRANSPARENTE = "rgba(0, 0, 0, 0)"


def estilizar_grafico(fig: go.Figure) -> go.Figure:
    """Aplica o visual padrão: fundo transparente, cantos arredondados e grade suave.

    Sem cores de fundo ou de texto fixas, o gráfico acompanha o tema claro/escuro do Streamlit.
    """
    fig.update_layout(
        paper_bgcolor=_TRANSPARENTE,
        plot_bgcolor=_TRANSPARENTE,
        barcornerradius=8,
        title_font_color=None,
        hoverlabel=dict(font_size=13),
        # Sem zoom por arraste: no celular o gesto precisa rolar a página, não o gráfico
        dragmode=False,
    )
    fig.update_xaxes(gridcolor=_GRADE, zeroline=False, tickfont_color=None, fixedrange=True, automargin=True)
    fig.update_yaxes(gridcolor=_GRADE, zeroline=False, tickfont_color=None, fixedrange=True, automargin=True)
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    fig.update_traces(marker_line_width=0, selector=dict(type="pie"))
    return fig


def exibir_grafico(fig: go.Figure) -> None:
    """Aplica o tema e renderiza o gráfico sem a barra de ferramentas do Plotly."""
    estilizar_grafico(fig)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
