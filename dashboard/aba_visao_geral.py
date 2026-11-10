"""Aba 1: Visão Geral & Ruptura."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.formatacao import formatar_moeda_brl


def renderizar(df_filtrado: pd.DataFrame, valor_total: float) -> None:
    st.markdown(
        '<div class="tab-banner">🎯 <strong>Cenário Operacional:</strong> Diagnóstico da saúde do estoque e identificação imediata de SKUs zerados para priorização de recompra e mitigação de perda de receita.</div>',
        unsafe_allow_html=True,
    )
    col_graf1, col_graf2 = st.columns(2)

    # 1.1 Capital Imobilizado por Categoria (Barras Horizontais com Paleta Semântica)
    with col_graf1:
        st.subheader("Capital Imobilizado por Categoria")
        if valor_total > 0:
            df_cat = df_filtrado.groupby("nome_categoria", as_index=False).agg(
                valor_total=("valor_total_estoque", "sum"),
                unidades=("quantidade_disponivel", "sum"),
            ).sort_values(by="valor_total", ascending=True)

            total_cat = df_cat["valor_total"].sum()
            df_cat["pct"] = (df_cat["valor_total"] / total_cat) * 100
            max_valor_cat = df_cat["valor_total"].max()

            # Destaque focal em Smartphones (ou na categoria de maior representatividade)
            cores_barras = [
                "#1d4ed8" if cat == "Smartphones" else "#94a3b8"
                for cat in df_cat["nome_categoria"]
            ]

            fig_cat = go.Figure()
            fig_cat.add_trace(go.Bar(
                y=df_cat["nome_categoria"],
                x=df_cat["valor_total"],
                orientation="h",
                marker=dict(color=cores_barras, line=dict(color="#0f172a", width=0.8)),
                text=[f"{formatar_moeda_brl(v)} ({p:.1f}%)" for v, p in zip(df_cat["valor_total"], df_cat["pct"])],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>Capital Retido: R$ %{x:,.2f}<br>Participação: %{text}<extra></extra>",
            ))
            fig_cat.update_traces(cliponaxis=False)

            fig_cat.update_layout(
                xaxis_title="Montante Retido (R$)",
                yaxis_title="Categoria",
                xaxis=dict(showgrid=True, gridcolor="#e2e8f0", range=[0, max_valor_cat * 1.35]),
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                height=380,
                margin=dict(l=10, r=90, t=20, b=40),
            )
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("ℹ️ Não há capital imobilizado para os filtros selecionados (Estoque Zerado / R$ 0,00).")

    # 1.2 Distribuição do Status de Reposição (Gráfico de Rosca / Donut)
    with col_graf2:
        st.subheader("Distribuição do Status de Reposição")
        if len(df_filtrado) > 0:
            contagem_status = df_filtrado["status_reposicao"].value_counts().reset_index()
            contagem_status.columns = ["status_reposicao", "quantidade_skus"]

            paleta_status = {
                "CRITICO": "#dc2626",   # Vermelho
                "ALERTA": "#f59e0b",    # Laranja/Amarelo
                "NORMAL": "#16a34a",    # Verde
                "EXCESSO": "#2563eb",   # Azul
            }

            fig_status = px.pie(
                contagem_status,
                names="status_reposicao",
                values="quantidade_skus",
                hole=0.45,
                color="status_reposicao",
                color_discrete_map=paleta_status,
            )
            fig_status.update_traces(
                textposition="inside",
                textinfo="percent+label",
                marker=dict(line=dict(color="#ffffff", width=2)),
                hovertemplate="<b>%{label}</b><br>SKUs: %{value}<br>Proporção: %{percent}<extra></extra>",
            )
            fig_status.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                height=380,
                margin=dict(l=20, r=20, t=20, b=40),
            )
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("ℹ️ Nenhum dado disponível para os filtros selecionados.")

    # 1.3 Alerta de Ruptura de Estoque (Matriz de Recompra Prioritária)
    st.subheader("🚨 Alerta de Ruptura de Estoque: Matriz de Recompra Prioritária")
    st.caption("Classificação executiva de SKUs zerados por impacto financeiro unitário para direcionar o orçamento de reposição imediata.")
    df_ruptura = df_filtrado[df_filtrado["quantidade_disponivel"] == 0].copy()

    if not df_ruptura.empty:
        # Ordenação estrita do maior para o menor Preço Unitário
        df_ruptura = df_ruptura.sort_values(by="preco_unitario", ascending=False)

        def classificar_prioridade(preco: float) -> str:
            if preco >= 1000.0:
                return "🔴 ALTA PRIORIDADE"
            elif preco >= 200.0:
                return "🟡 MÉDIA PRIORIDADE"
            else:
                return "🔵 BAIXA PRIORIDADE"

        df_ruptura["prioridade"] = df_ruptura["preco_unitario"].apply(classificar_prioridade)

        df_ruptura_exibicao = df_ruptura[[
            "prioridade", "nome_produto", "nome_categoria", "fornecedor", "preco_unitario"
        ]].copy()

        st.dataframe(
            df_ruptura_exibicao,
            column_config={
                "prioridade": st.column_config.TextColumn("Prioridade"),
                "nome_produto": st.column_config.TextColumn("Produto"),
                "nome_categoria": st.column_config.TextColumn("Categoria"),
                "fornecedor": st.column_config.TextColumn("Fornecedor de Origem"),
                "preco_unitario": st.column_config.NumberColumn(
                    "Preço Unitário",
                    format="R$ %.2f",
                ),
            },
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("✅ **Nenhum produto zerado ou em ruptura crítica** para o conjunto de filtros aplicado.")
