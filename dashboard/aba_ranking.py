"""Aba: Ranking & Risco de Fornecedores."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.componentes import cartoes_fornecedores
from dashboard.graficos import CORES_FORNECEDOR, exibir_grafico
from regras_fornecedores import (
    ICONE_CLASSE,
    LIMITE_BOM,
    LIMITE_MEDIO,
    PESOS,
    ROTULO_CLASSE,
    ROTULOS_GRAVIDADE,
    ROTULOS_STATUS,
    ROTULOS_TIPO,
    calcular_penalidades,
    ranking_fornecedores,
)


def _explicacao_nota() -> None:
    with st.expander("ℹ️ Como a nota é calculada", expanded=False):
        st.markdown(
            f"""
A nota vai de **0 a 100** e combina quatro fatores:

| Fator | Peso | O que mede |
| :--- | :---: | :--- |
| Preço | {PESOS['preco']:.0%} | Distância da melhor oferta de cada produto (10% mais caro = 75) |
| Prazo | {PESOS['prazo']:.0%} | Dias a mais que a entrega mais rápida (cada dia = −12 pontos) |
| Lote mínimo | {PESOS['lote']:.0%} | Tamanho do lote comparado ao menor lote oferecido |
| Confiabilidade | {PESOS['confiabilidade']:.0%} | Começa em 100 e perde pontos a cada problema dos últimos 12 meses |

**Na confiabilidade**, cada problema pesa conforme a **gravidade**, **quando aconteceu** (problemas
resolvidos perdem metade do peso a cada ~4 meses) e **se foi resolvido** (resolver rápido pesa pouco;
um problema em aberto pesa o máximo e piora com o tempo).

**Classes:** 🟢 Bom ({LIMITE_BOM}+) · 🟡 Médio ({LIMITE_MEDIO} a {LIMITE_BOM - 1}) · 🔴 Perigoso (abaixo de {LIMITE_MEDIO}).
Um **processo judicial** ou problema **crítico sem solução** classifica como Perigoso direto, seja qual for a nota.
"""
        )


def _tabela_ranking(ranking: pd.DataFrame) -> None:
    tabela = ranking.copy()
    tabela.insert(0, "posicao", range(1, len(tabela) + 1))
    tabela["classe"] = tabela["classe"].map(lambda c: f"{ICONE_CLASSE[c]} {ROTULO_CLASSE[c]}")
    st.dataframe(
        tabela[[
            "posicao", "fornecedor", "classe", "nota_final", "nota_preco", "nota_prazo",
            "nota_lote", "nota_confiabilidade", "ocorrencias_12m", "sem_solucao", "dias_medios_resolucao",
        ]],
        column_config={
            "posicao": st.column_config.NumberColumn("#", format="%d"),
            "fornecedor": st.column_config.TextColumn("Fornecedor"),
            "classe": st.column_config.TextColumn("Classe"),
            # Azul neutro: a classe (Bom/Médio/Perigoso) já está na coluna ao lado
            "nota_final": st.column_config.ProgressColumn(
                "Nota final", min_value=0, max_value=100, format="%.0f", color="#3987e5",
            ),
            "nota_preco": st.column_config.NumberColumn("Preço", format="%.0f"),
            "nota_prazo": st.column_config.NumberColumn("Prazo", format="%.0f"),
            "nota_lote": st.column_config.NumberColumn("Lote", format="%.0f"),
            "nota_confiabilidade": st.column_config.NumberColumn("Confiabilidade", format="%.0f"),
            "ocorrencias_12m": st.column_config.NumberColumn("Ocorrências (12m)", format="%d"),
            "sem_solucao": st.column_config.NumberColumn("Sem solução", format="%d"),
            "dias_medios_resolucao": st.column_config.NumberColumn("Dias p/ resolver (média)", format="%.1f"),
        },
        hide_index=True,
        width="stretch",
    )


def _grafico_tipos(ocorrencias: pd.DataFrame, ordem_fornecedores: list[str]) -> None:
    """Mapa de calor: quantas ocorrências de cada tipo cada fornecedor teve em 12 meses."""
    no_periodo = ocorrencias[ocorrencias["penalidade"] > 0]
    # Tipos nas linhas (rótulos legíveis na horizontal) e fornecedores nas colunas, pela letra
    contagem = (
        no_periodo.assign(tipo_rotulo=no_periodo["tipo"].map(ROTULOS_TIPO))
        .pivot_table(index="tipo_rotulo", columns="fornecedor", values="tipo", aggfunc="count", fill_value=0)
        .reindex(index=list(ROTULOS_TIPO.values()), columns=ordem_fornecedores, fill_value=0)
    )
    letras = [f.replace("Fornecedor ", "") for f in contagem.columns]
    fig = go.Figure(go.Heatmap(
        z=contagem.where(contagem > 0).values,  # zero fica em branco
        x=letras,
        y=contagem.index,
        text=[[str(v) if v else "" for v in linha] for linha in contagem.values],
        texttemplate="%{text}",
        textfont=dict(size=13),
        customdata=[[f"Fornecedor {letra}" for letra in letras]] * len(contagem),
        # Rampa sólida de um só tom (claro = poucas, escuro = muitas): cores opacas deixam o
        # Plotly escolher texto preto ou branco com bom contraste nos modos claro e escuro
        colorscale=[[0, "#86b6ef"], [0.5, "#3987e5"], [1, "#184f95"]],
        showscale=False,
        xgap=3,
        ygap=3,
        hovertemplate="<b>%{customdata}</b><br>%{y}: %{z} ocorrência(s)<extra></extra>",
    ))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top", title=dict(text="Fornecedor", standoff=4))
    exibir_grafico(fig)


def _grafico_resolucao(ranking: pd.DataFrame) -> None:
    """Tempo médio para resolver os problemas, por fornecedor."""
    dados = ranking.dropna(subset=["dias_medios_resolucao"]).sort_values("dias_medios_resolucao")
    fig = go.Figure(go.Bar(
        x=dados["dias_medios_resolucao"],
        y=dados["fornecedor"],
        orientation="h",
        marker=dict(color=[CORES_FORNECEDOR.get(f, "#64748b") for f in dados["fornecedor"]]),
        text=[f"{d:.1f} dias" for d in dados["dias_medios_resolucao"]],
        textposition="outside",
        customdata=dados[["sem_solucao"]],
        hovertemplate="<b>%{y}</b><br>Tempo médio: %{x:.1f} dias<br>Sem solução: %{customdata[0]}<extra></extra>",
    ))
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=40, t=10, b=40),
        xaxis_title="Dias para resolver (média)",
        xaxis=dict(range=[0, float(dados["dias_medios_resolucao"].max()) * 1.25 if not dados.empty else 1]),
    )
    fig.update_yaxes(autorange="reversed")
    exibir_grafico(fig)


def _historico(ocorrencias: pd.DataFrame) -> None:
    col_f, col_t, col_s = st.columns(3)
    fornecedores = sorted(ocorrencias["fornecedor"].unique())
    filtro_forn = col_f.multiselect("Fornecedor", fornecedores, placeholder="Todos")
    filtro_tipo = col_t.multiselect("Tipo de problema", list(ROTULOS_TIPO.values()), placeholder="Todos")
    filtro_status = col_s.multiselect("Status", list(ROTULOS_STATUS.values()), placeholder="Todos")

    tabela = ocorrencias.copy()
    tabela["tipo_rotulo"] = tabela["tipo"].map(ROTULOS_TIPO)
    tabela["status_rotulo"] = tabela["status"].map(ROTULOS_STATUS)
    if filtro_forn:
        tabela = tabela[tabela["fornecedor"].isin(filtro_forn)]
    if filtro_tipo:
        tabela = tabela[tabela["tipo_rotulo"].isin(filtro_tipo)]
    if filtro_status:
        tabela = tabela[tabela["status_rotulo"].isin(filtro_status)]

    icones_status = {"RESOLVIDO": "✅", "EM_ANDAMENTO": "⏳", "ABERTO": "❗"}
    tabela["situacao"] = [
        f"{icones_status[s]} Resolvido em {int(dr)} dias" if s == "RESOLVIDO"
        else f"{icones_status[s]} {ROTULOS_STATUS[s]} há {int(da)} dias"
        for s, dr, da in zip(tabela["status"], tabela["dias_para_resolver"], tabela["dias_em_aberto"])
    ]
    tabela["gravidade_rotulo"] = tabela["gravidade"].map(ROTULOS_GRAVIDADE)
    tabela["produto"] = tabela["nome_produto"].fillna("—")

    st.caption(f"{len(tabela)} de {len(ocorrencias)} ocorrências")
    st.dataframe(
        tabela.sort_values("data_ocorrencia", ascending=False)[[
            "data_ocorrencia", "fornecedor", "tipo_rotulo", "gravidade_rotulo", "situacao", "produto", "descricao",
        ]],
        column_config={
            "data_ocorrencia": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "fornecedor": st.column_config.TextColumn("Fornecedor"),
            "tipo_rotulo": st.column_config.TextColumn("Tipo"),
            "gravidade_rotulo": st.column_config.TextColumn("Gravidade"),
            "situacao": st.column_config.TextColumn("Situação"),
            "produto": st.column_config.TextColumn("Produto"),
            "descricao": st.column_config.TextColumn("Descrição", width="large"),
        },
        hide_index=True,
        width="stretch",
    )


def renderizar(df_cot: pd.DataFrame, df_ocorrencias: pd.DataFrame) -> None:
    st.markdown(
        '<div class="tab-banner">🛡️ <strong>Cenário de Risco:</strong> Avaliação de cada fornecedor por preço, '
        "prazo, lote mínimo e histórico de problemas dos últimos 12 meses, com alertas de Bom, Médio ou Perigoso.</div>",
        unsafe_allow_html=True,
    )

    if df_ocorrencias.empty:
        st.info(
            "ℹ️ O histórico de ocorrências ainda não foi gerado. Rode `python pipeline_completo.py` "
            "(ou `python gerar_ocorrencias_fornecedores.py`) para criar o ranking."
        )
        return

    hoje = date.today()
    ranking = ranking_fornecedores(
        df_cot, df_ocorrencias, hoje, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao",
    )
    ocorrencias = calcular_penalidades(df_ocorrencias, hoje)

    st.subheader("🚦 Alertas por Fornecedor")
    st.caption("Avaliação geral de cada fornecedor, considerando todas as cotações (não muda com os filtros da barra lateral).")
    cartoes_fornecedores(ranking)
    _explicacao_nota()

    st.subheader("🏆 Ranking de Fornecedores")
    _tabela_ranking(ranking)

    col_tipos, col_resolucao = st.columns(2)
    with col_tipos:
        st.markdown("##### 🧩 Problemas por tipo (12 meses)")
        _grafico_tipos(ocorrencias, ranking["fornecedor"].tolist())
    with col_resolucao:
        st.markdown("##### ⏱️ Tempo médio para resolver")
        _grafico_resolucao(ranking)

    st.subheader("📜 Histórico de Ocorrências")
    _historico(ocorrencias)
