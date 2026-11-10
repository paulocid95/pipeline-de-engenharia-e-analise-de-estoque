"""Aba 2: Análise de Fornecedores."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.formatacao import formatar_moeda_brl


def renderizar(df_filtrado: pd.DataFrame) -> None:
    st.markdown(
        '<div class="tab-banner">🏭 <strong>Cenário de Parcerias:</strong> Análise da concentração de compras, dependência de fornecedores e distribuição de volume físico por parceiro comercial.</div>',
        unsafe_allow_html=True,
    )
    st.subheader("🏭 Desempenho e Distribuição por Fornecedor")

    df_forn = df_filtrado.groupby("fornecedor", as_index=False).agg(
        unidades=("quantidade_disponivel", "sum"),
        skus=("sku", "count"),
        valor_total=("valor_total_estoque", "sum"),
        ticket_medio=("preco_unitario", "mean"),
    ).sort_values(by="unidades", ascending=False)

    if not df_forn.empty:
        # Métricas resumidas no topo da aba
        cols_metricas = st.columns(len(df_forn))
        for i, (_, row) in enumerate(df_forn.iterrows()):
            with cols_metricas[i]:
                st.metric(
                    label=f"🏢 {row['fornecedor']}",
                    value=f"{int(row['unidades']):,} un".replace(",", "."),
                    delta=f"{formatar_moeda_brl(row['valor_total'])}",
                    help=f"SKUs: {int(row['skus'])} | Ticket Médio: {formatar_moeda_brl(row['ticket_medio'])}",
                )

        st.markdown("<br>", unsafe_allow_html=True)

        # Gráfico Comparativo Interativo com Dois Painéis Lado a Lado
        fig_comparativo = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Volume Físico Total de Peças", "Diversidade de SKUs Ativos"),
            horizontal_spacing=0.12,
        )

        # Painel 1: Volume Físico
        fig_comparativo.add_trace(
            go.Bar(
                x=df_forn["fornecedor"],
                y=df_forn["unidades"],
                marker=dict(color=["#2563eb", "#3b82f6", "#60a5fa"][:len(df_forn)], line=dict(color="#1e293b", width=0.8)),
                text=[f"{int(u)} un" for u in df_forn["unidades"]],
                textposition="outside",
                name="Volume Físico",
                hovertemplate="<b>%{x}</b><br>Volume: %{y} unidades<extra></extra>",
            ),
            row=1, col=1,
        )

        # Painel 2: Diversidade de SKUs
        fig_comparativo.add_trace(
            go.Bar(
                x=df_forn["fornecedor"],
                y=df_forn["skus"],
                marker=dict(color=["#0d9488", "#14b8a6", "#2dd4bf"][:len(df_forn)], line=dict(color="#1e293b", width=0.8)),
                text=[f"{int(s)} SKUs" for s in df_forn["skus"]],
                textposition="outside",
                name="Variedade de SKUs",
                hovertemplate="<b>%{x}</b><br>Diversidade: %{y} SKUs<extra></extra>",
            ),
            row=1, col=2,
        )

        fig_comparativo.update_layout(
            showlegend=False,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=420,
            margin=dict(l=20, r=20, t=50, b=40),
        )
        fig_comparativo.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
        st.plotly_chart(fig_comparativo, width="stretch")

        # Tabela Consolidada Executiva por Fornecedor
        st.markdown("##### 📌 Tabela de Participação dos Fornecedores")
        total_unid_global = df_forn["unidades"].sum()
        total_val_global = df_forn["valor_total"].sum()

        df_forn_tab = df_forn.copy()
        df_forn_tab["share_volume"] = (df_forn_tab["unidades"] / (total_unid_global if total_unid_global > 0 else 1)) * 100
        df_forn_tab["share_capital"] = (df_forn_tab["valor_total"] / (total_val_global if total_val_global > 0 else 1)) * 100

        st.dataframe(
            df_forn_tab[[
                "fornecedor", "unidades", "share_volume",
                "valor_total", "share_capital", "skus", "ticket_medio"
            ]],
            column_config={
                "fornecedor": st.column_config.TextColumn("Fornecedor"),
                "unidades": st.column_config.NumberColumn("Volume Total", format="%d un"),
                "share_volume": st.column_config.NumberColumn("Share Volume", format="%.1f%%"),
                "valor_total": st.column_config.NumberColumn("Capital Imobilizado", format="R$ %.2f"),
                "share_capital": st.column_config.NumberColumn("Share Capital", format="%.1f%%"),
                "skus": st.column_config.NumberColumn("SKUs Ativos", format="%d"),
                "ticket_medio": st.column_config.NumberColumn("Ticket Médio", format="R$ %.2f"),
            },
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("ℹ️ Nenhum dado de fornecedor correspondente aos filtros selecionados.")
