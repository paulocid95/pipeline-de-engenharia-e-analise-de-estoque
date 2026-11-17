"""Tema único dos gráficos Plotly e paletas de cores do painel."""

import plotly.graph_objects as go
import streamlit as st

CORES_STATUS = {
    "CRITICO": "#ef4444",
    "ALERTA": "#f59e0b",
    "NORMAL": "#10b981",
    "EXCESSO": "#3b82f6",
}

CORES_FORNECEDOR = {
    "Fornecedor A": "#2563eb",
    "Fornecedor B": "#0d9488",
    "Fornecedor C": "#f59e0b",
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
