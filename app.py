import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
import streamlit as st

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Dashboard Executivo de Estoque",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# 2. CONEXÃO COM O BANCO DE DADOS (POSTGRESQL / NEON)
# ==============================================================================
load_dotenv()
database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)


@st.cache_resource
def obter_conexao():
    """Cria e reutiliza o pool de conexões do SQLAlchemy com o banco de dados."""
    return create_engine(database_url)


engine = obter_conexao()


# ==============================================================================
# 3. CONSULTA ANALÍTICA COM CACHE E ENRIQUECIMENTO DIMENSIONAL
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_dados_analiticos() -> pd.DataFrame:
    """Consulta analítica no PostgreSQL (traz apenas o snapshot mais recente por SKU).
    
    Inclui dimensões de produto, categoria e fornecedor com deduplicação via DISTINCT ON.
    """
    query = """
        SELECT DISTINCT ON (p.sku)
            p.sku,
            p.nome_produto,
            c.nome_categoria,
            COALESCE(p.fornecedor, 'Não Informado') AS fornecedor,
            p.preco_unitario,
            f.quantidade_disponivel,
            f.valor_total_estoque,
            f.status_reposicao,
            f.data_carga
        FROM core.fato_estoque f
        JOIN core.dim_produtos p ON f.id_produto = p.id_produto
        LEFT JOIN core.dim_categorias c ON p.id_categoria = c.id_categoria
        ORDER BY p.sku, f.data_carga DESC;
    """
    df_raw = pd.read_sql(text(query), engine)

    # Fallback de integridade: se algum fornecedor estiver ausente, enriquece com a base consolidada
    if df_raw["fornecedor"].isna().any() or (df_raw["fornecedor"] == "Não Informado").any():
        caminho_csv = Path("dados_processados") / "estoque_consolidado_limpo.csv"
        if caminho_csv.exists():
            df_csv = pd.read_csv(caminho_csv)
            mapa_forn = dict(zip(df_csv["id_produto"], df_csv["fornecedor"]))
            df_raw["fornecedor"] = df_raw["fornecedor"].replace("Não Informado", pd.NA).fillna(df_raw["sku"].map(mapa_forn)).fillna("Não Informado")

    return df_raw.sort_values(by="valor_total_estoque", ascending=False)


df = carregar_dados_analiticos()


# ==============================================================================
# 4. FUNÇÕES UTILITÁRIAS DE FORMATAÇÃO
# ==============================================================================
def formatar_moeda_brl(valor: float) -> str:
    """Formata valor para a representação monetária brasileira (R$ 1.234,56)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ==============================================================================
# 5. BARRA LATERAL - FILTROS DINÂMICOS
# ==============================================================================
st.sidebar.header("🔍 Filtros de Consulta")

# Filtro 1: Categoria
categorias_disponiveis = ["Todas"] + sorted(df["nome_categoria"].dropna().unique().tolist())
categoria_selecionada = st.sidebar.selectbox("Filtrar por Categoria:", categorias_disponiveis)

# Filtro 2: Fornecedor
fornecedores_disponiveis = ["Todos"] + sorted(df["fornecedor"].dropna().unique().tolist())
fornecedor_selecionado = st.sidebar.selectbox("Filtrar por Fornecedor:", fornecedores_disponiveis)

# Filtro 3: Status de Reposição
status_disponiveis = ["Todos"] + sorted(df["status_reposicao"].dropna().unique().tolist())
status_selecionado = st.sidebar.selectbox("Filtrar por Status de Reposição:", status_disponiveis)

# Aplicação dos filtros
df_filtrado = df.copy()
if categoria_selecionada != "Todas":
    df_filtrado = df_filtrado[df_filtrado["nome_categoria"] == categoria_selecionada]
if fornecedor_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["fornecedor"] == fornecedor_selecionado]
if status_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["status_reposicao"] == status_selecionado]

# Rodapé da sidebar
st.sidebar.divider()
st.sidebar.caption("🟢 **Banco Conectado:** PostgreSQL (Neon)")
if not df.empty and "data_carga" in df.columns:
    ultima_atualizacao = pd.to_datetime(df["data_carga"].max()).strftime("%d/%m/%Y %H:%M:%S")
    st.sidebar.caption(f"🕒 **Última Carga:** {ultima_atualizacao}")


# ==============================================================================
# 6. CABEÇALHO E SCORECARDS EXECUTIVOS
# ==============================================================================
st.title("📦 Monitoramento e Gestão Analítica de Estoque")
st.markdown("Painel executivo com atualização em tempo real conectado à infraestrutura de dados no **PostgreSQL (Neon)**.")

st.divider()

col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

total_itens = int(df_filtrado["quantidade_disponivel"].sum())
valor_total = float(df_filtrado["valor_total_estoque"].sum())
itens_criticos = int((df_filtrado["status_reposicao"] == "CRITICO").sum())
itens_alerta = int((df_filtrado["status_reposicao"] == "ALERTA").sum())

col_kpi1.metric("📦 Volume Físico Total", f"{total_itens:,} un".replace(",", "."))
col_kpi2.metric("💰 Capital Imobilizado", formatar_moeda_brl(valor_total))
col_kpi3.metric("🚨 Produtos Críticos (Zerados)", itens_criticos)
col_kpi4.metric("⚠️ Produtos em Alerta", itens_alerta)

st.divider()


# ==============================================================================
# 7. ESTRUTURA MODULAR EM ABAS (st.tabs)
# ==============================================================================
tab_visao_geral, tab_fornecedores, tab_tabela = st.tabs([
    "📊 Visão Geral & Ruptura",
    "🏭 Análise de Fornecedores",
    "📋 Tabela Operacional & Exportação",
])


# ------------------------------------------------------------------------------
# ABA 1: VISÃO GERAL & RUPTURA
# ------------------------------------------------------------------------------
with tab_visao_geral:
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


# ------------------------------------------------------------------------------
# ABA 2: ANÁLISE DE FORNECEDORES
# ------------------------------------------------------------------------------
with tab_fornecedores:
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
        st.plotly_chart(fig_comparativo, use_container_width=True)

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
            use_container_width=True,
        )
    else:
        st.info("ℹ️ Nenhum dado de fornecedor correspondente aos filtros selecionados.")


# ------------------------------------------------------------------------------
# ABA 3: TABELA OPERACIONAL & EXPORTAÇÃO
# ------------------------------------------------------------------------------
with tab_tabela:
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

    # Botão de exportação em CSV
    csv_bytes = df_exibicao.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        st.download_button(
            label="📥 Exportar Dados Filtrados (CSV)",
            data=csv_bytes,
            file_name="relatorio_estoque_filtrado.csv",
            mime="text/csv",
            help="Download do conjunto de dados atualmente filtrado em formato compatível com Excel.",
        )
    with col_info:
        st.caption(f"📊 **Total de registros disponíveis para download:** {len(df_exibicao)} produtos filtrados.")