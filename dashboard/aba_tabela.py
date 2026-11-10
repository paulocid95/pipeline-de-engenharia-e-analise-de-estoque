"""Aba 4: Tabela Operacional & Exportação."""

import pandas as pd
import streamlit as st

from dashboard.formatacao import gerar_excel_estilizado


def renderizar(df_filtrado: pd.DataFrame) -> None:
    st.markdown(
        '<div class="tab-banner">📋 <strong>Cenário Tático & Auditoria:</strong> Consulta detalhada de todos os itens cadastrados com filtros dinâmicos e extração em formato Excel (.xlsx) profissionalmente estilizado ou CSV para rotinas executivas.</div>',
        unsafe_allow_html=True,
    )
    st.subheader("📋 Tabela Operacional e Extração de Dados")
    st.markdown("Visualização analítica linha a linha dos produtos cadastrados com opções de ordenação e exportação de relatório.")

    # Colunas de ordenação e exibição
    colunas_exibicao = [
        "sku", "nome_produto", "nome_categoria", "fornecedor",
        "preco_unitario", "quantidade_disponivel", "valor_total_estoque", "status_reposicao"
    ]
    df_exibicao = df_filtrado[colunas_exibicao].copy()

    # Tabela analítica com formatação elegante de números e moeda
    st.dataframe(
        df_exibicao,
        column_config={
            "sku": st.column_config.TextColumn("SKU"),
            "nome_produto": st.column_config.TextColumn("Produto"),
            "nome_categoria": st.column_config.TextColumn("Categoria"),
            "fornecedor": st.column_config.TextColumn("Fornecedor"),
            "preco_unitario": st.column_config.NumberColumn("Preço Unitário", format="R$ %.2f"),
            "quantidade_disponivel": st.column_config.NumberColumn("Estoque Disponível", format="%d un"),
            "valor_total_estoque": st.column_config.NumberColumn("Valor em Estoque", format="R$ %.2f"),
            "status_reposicao": st.column_config.TextColumn("Status de Reposição"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Geração dos arquivos de exportação em memória (Excel estilizado e CSV)
    excel_bytes = gerar_excel_estilizado(df_exibicao)
    csv_bytes = df_exibicao.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")

    col_btn_xlsx, col_btn_csv, col_info = st.columns([1.6, 1.3, 2.5])
    with col_btn_xlsx:
        st.download_button(
            label="📊 Exportar Relatório Excel (.xlsx)",
            data=excel_bytes,
            file_name="relatorio_estoque_executivo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download do relatório profissional formatado em Excel com cabeçalho estilizado, autoajuste de colunas e moeda em R$.",
            type="primary",
            use_container_width=True,
        )
    with col_btn_csv:
        st.download_button(
            label="📥 Exportar Dados (CSV)",
            data=csv_bytes,
            file_name="relatorio_estoque_filtrado.csv",
            mime="text/csv",
            help="Download dos dados filtrados em formato texto CSV padrão (separador ponto e vírgula).",
            use_container_width=True,
        )
    with col_info:
        st.caption(f"📊 **Total de registros disponíveis para download:** {len(df_exibicao)} produtos filtrados.")
