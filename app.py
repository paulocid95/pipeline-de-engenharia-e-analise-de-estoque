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
# ESTILIZAÇÃO CSS CUSTOMIZADA (SaaS MODERNO & CARDS EXECUTIVOS)
# ==============================================================================
st.markdown("""
<style>
    /* Tipografia e títulos estilo SaaS */
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.025em !important;
        color: #0f172a !important;
    }
    h2, h3 {
        font-weight: 700 !important;
        letter-spacing: -0.015em !important;
        color: #1e293b !important;
    }

    /* Cards de métricas modernos */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        transition: all 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
        border-color: #cbd5e1;
    }
    div[data-testid="stMetric"] label {
        font-weight: 600;
        color: #64748b !important;
        font-size: 0.86rem !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-weight: 750;
        color: #0f172a !important;
        font-size: 1.6rem !important;
    }

    /* Banners contextuais de introdução de abas */
    .tab-banner {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border-left: 4px solid #2563eb;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 22px;
        color: #334155;
        font-size: 0.94rem;
        line-height: 1.5;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
    }
    .tab-banner strong {
        color: #0f172a;
    }

    /* Abas estilizadas */
    button[data-baseweb="tab"] {
        font-size: 0.98rem;
        font-weight: 600;
        padding: 10px 18px;
    }
</style>
""", unsafe_allow_html=True)

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


@st.cache_data(ttl=60)
def carregar_dados_cotacoes() -> pd.DataFrame:
    """Consulta analítica de cotações concorrentes unida às dimensões e status atual."""
    query = """
        SELECT
            c.id_cotacao,
            p.sku,
            p.nome_produto,
            cat.nome_categoria,
            p.preco_unitario AS preco_referencia,
            c.fornecedor AS fornecedor_cotacao,
            c.preco_cotado,
            c.lote_minimo,
            c.prazo_dias,
            c.data_cotacao,
            f.status_reposicao,
            f.quantidade_disponivel
        FROM core.fato_cotacoes c
        JOIN core.dim_produtos p ON c.id_produto = p.id_produto
        LEFT JOIN core.dim_categorias cat ON p.id_categoria = cat.id_categoria
        LEFT JOIN (
            SELECT DISTINCT ON (id_produto)
                id_produto,
                status_reposicao,
                quantidade_disponivel,
                data_carga
            FROM core.fato_estoque
            ORDER BY id_produto, data_carga DESC
        ) f ON p.id_produto = f.id_produto
        ORDER BY p.sku, c.preco_cotado ASC;
    """
    return pd.read_sql(text(query), engine)


df = carregar_dados_analiticos()
df_cot = carregar_dados_cotacoes()


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

# Aplicação dos filtros em Estoque
df_filtrado = df.copy()
if categoria_selecionada != "Todas":
    df_filtrado = df_filtrado[df_filtrado["nome_categoria"] == categoria_selecionada]
if fornecedor_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["fornecedor"] == fornecedor_selecionado]
if status_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["status_reposicao"] == status_selecionado]

# Aplicação dos filtros em Cotações
df_cot_filtrado = df_cot.copy()
if categoria_selecionada != "Todas":
    df_cot_filtrado = df_cot_filtrado[df_cot_filtrado["nome_categoria"] == categoria_selecionada]
if fornecedor_selecionado != "Todos":
    df_cot_filtrado = df_cot_filtrado[df_cot_filtrado["fornecedor_cotacao"] == fornecedor_selecionado]
if status_selecionado != "Todos":
    df_cot_filtrado = df_cot_filtrado[df_cot_filtrado["status_reposicao"] == status_selecionado]

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
tab_visao_geral, tab_fornecedores, tab_compras, tab_tabela = st.tabs([
    "📊 Visão Geral & Ruptura",
    "🏭 Análise de Fornecedores",
    "💡 Inteligência de Compras",
    "📋 Tabela Operacional & Exportação",
])


# ------------------------------------------------------------------------------
# ABA 1: VISÃO GERAL & RUPTURA
# ------------------------------------------------------------------------------
with tab_visao_geral:
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


# ------------------------------------------------------------------------------
# ABA 2: ANÁLISE DE FORNECEDORES
# ------------------------------------------------------------------------------
with tab_fornecedores:
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
# ABA 3: INTELIGÊNCIA DE COMPRAS & COTAÇÕES (PROCUREMENT ANALYTICS)
# ------------------------------------------------------------------------------
with tab_compras:
    st.markdown(
        '<div class="tab-banner">💡 <strong>Cenário de Procurement:</strong> Auditoria de propostas concorrentes, identificação de saving potencial e otimização da relação custo vs. prazo de entrega.</div>',
        unsafe_allow_html=True,
    )
    st.subheader("💡 Inteligência de Compras e Cotações (Procurement Analytics)")
    st.caption("Central estratégica de negociação: simulação de cenários de recompra, concorrência direta e captura de saving unitário.")

    if not df_cot_filtrado.empty:
        # 1. Cards / Métricas no Topo
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)

        # Cálculo do Saving por SKU comparado à melhor proposta do mercado
        idx_melhores = df_cot_filtrado.groupby("sku")["preco_cotado"].idxmin()
        df_melhores_ofertas = df_cot_filtrado.loc[idx_melhores].copy()
        df_melhores_ofertas["saving_unitario"] = df_melhores_ofertas["preco_referencia"] - df_melhores_ofertas["preco_cotado"]
        df_melhores_ofertas["saving_pct"] = (df_melhores_ofertas["saving_unitario"] / df_melhores_ofertas["preco_referencia"]) * 100

        saving_medio_pct = df_melhores_ofertas["saving_pct"].mean()
        lead_time_medio = df_cot_filtrado["prazo_dias"].mean()

        vitorias_fornecedor = df_melhores_ofertas["fornecedor_cotacao"].value_counts()
        fornecedor_competitivo = vitorias_fornecedor.index[0] if not vitorias_fornecedor.empty else "N/A"
        vitorias_qtd = int(vitorias_fornecedor.iloc[0]) if not vitorias_fornecedor.empty else 0
        vitorias_pct = (vitorias_qtd / len(df_melhores_ofertas) * 100) if len(df_melhores_ofertas) > 0 else 0

        col_m1.metric(
            label="💰 Saving Potencial Médio",
            value=f"{saving_medio_pct:.1f}%",
            delta="Economia vs Tabela",
            help="Economia percentual média obtida optando pela melhor proposta concorrente de cada SKU.",
        )
        col_m2.metric(
            label="⏱️ Lead Time Médio",
            value=f"{lead_time_medio:.1f} dias",
            help="Prazo médio de entrega considerando todas as cotações ativas no filtro atual.",
        )
        col_m3.metric(
            label="🏆 Fornecedor Mais Competitivo",
            value=fornecedor_competitivo,
            delta=f"{vitorias_qtd} ofertas vencedoras ({vitorias_pct:.0f}%)",
            help="Fornecedor que apresentou o menor preço cotado no maior número de produtos.",
        )
        col_m4.metric(
            label="📑 Cotações Analisadas",
            value=f"{len(df_cot_filtrado)} propostas",
            help=f"Volume de propostas cobrindo {len(df_melhores_ofertas)} SKUs cadastrados.",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. Módulo de Cotações Brutas (Expander de Auditoria)
        with st.expander("📥 Ver Todas as Propostas em Aberto (Cotações Recebidas)", expanded=False):
            st.caption(f"Visão analítica completa das {len(df_cot_filtrado)} propostas comerciais submetidas pelos parceiros para auditoria de preços.")
            df_cot_brutas = df_cot_filtrado[[
                "sku", "nome_produto", "fornecedor_cotacao", "preco_cotado", "lote_minimo", "prazo_dias", "data_cotacao"
            ]].copy()
            st.dataframe(
                df_cot_brutas,
                column_config={
                    "sku": st.column_config.TextColumn("SKU"),
                    "nome_produto": st.column_config.TextColumn("Produto"),
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor"),
                    "preco_cotado": st.column_config.NumberColumn("Preço Cotado", format="R$ %.2f"),
                    "lote_minimo": st.column_config.NumberColumn("Lote Mínimo", format="%d un"),
                    "prazo_dias": st.column_config.NumberColumn("Prazo de Entrega", format="%d dias"),
                    "data_cotacao": st.column_config.DatetimeColumn("Data Cotação", format="DD/MM/YYYY HH:mm"),
                },
                hide_index=True,
                use_container_width=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. Simulador de Recompra para Ruptura / Alerta
        st.markdown("##### 🚨 Simulador de Recompra: Melhor Oferta para Itens em Ruptura ou Alerta")
        st.caption("Identificação automática do fornecedor mais vantajoso para os itens que demandam reposição operacional imediata.")

        df_reposicao_cot = df_melhores_ofertas[
            df_melhores_ofertas["status_reposicao"].isin(["CRITICO", "ALERTA"])
        ].copy()

        if not df_reposicao_cot.empty:
            df_reposicao_cot = df_reposicao_cot.sort_values(by="saving_unitario", ascending=False)
            
            df_reposicao_exibicao = df_reposicao_cot[[
                "status_reposicao", "nome_produto", "nome_categoria", "preco_referencia",
                "fornecedor_cotacao", "preco_cotado", "saving_unitario", "saving_pct",
                "lote_minimo", "prazo_dias"
            ]].copy()

            st.dataframe(
                df_reposicao_exibicao,
                column_config={
                    "status_reposicao": st.column_config.TextColumn("Status"),
                    "nome_produto": st.column_config.TextColumn("Produto"),
                    "nome_categoria": st.column_config.TextColumn("Categoria"),
                    "preco_referencia": st.column_config.NumberColumn("Preço de Tabela", format="R$ %.2f"),
                    "fornecedor_cotacao": st.column_config.TextColumn("Melhor Fornecedor"),
                    "preco_cotado": st.column_config.NumberColumn("Preço Cotado", format="R$ %.2f"),
                    "saving_unitario": st.column_config.NumberColumn("Saving Unitário", format="R$ %.2f"),
                    "saving_pct": st.column_config.NumberColumn("Saving (%)", format="%.1f%%"),
                    "lote_minimo": st.column_config.NumberColumn("Lote Mínimo", format="%d un"),
                    "prazo_dias": st.column_config.NumberColumn("Prazo", format="%d dias"),
                },
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("✅ **Nenhum produto em status CRÍTICO ou ALERTA** requer recompra urgente nos filtros atuais.")

        st.markdown("<br>", unsafe_allow_html=True)

        # 4. Análise Gráfica Redesenhada de Trade-off (Plotly Scatter Plot Intuitivo)
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.markdown("##### ⚖️ Matriz de Trade-off: Custo Unitário vs. Agilidade Logística")
            st.caption("Avaliação de equilíbrio entre preço negociado e tempo de atendimento para guiar compras inteligentes.")
            st.caption("💡 **Como interpretar:** Pontos no **canto inferior esquerdo** representam o cenário ideal (menor preço e entrega mais ágil). Pontos no **canto superior direito** indicam condições desfavoráveis (maior custo e maior prazo).")
        with col_t2:
            categorias_tradeoff = ["Todas as Categorias"] + sorted(df_cot_filtrado["nome_categoria"].dropna().unique().tolist())
            cat_tradeoff_selecionada = st.selectbox(
                "Filtrar Categoria no Gráfico:",
                categorias_tradeoff,
                key="sel_cat_tradeoff",
            )

        df_graf_tradeoff = df_cot_filtrado.copy()
        if cat_tradeoff_selecionada != "Todas as Categorias":
            df_graf_tradeoff = df_graf_tradeoff[df_graf_tradeoff["nome_categoria"] == cat_tradeoff_selecionada]

        paleta_fornecedores = {
            "Fornecedor A": "#2563eb",  # Azul Royal
            "Fornecedor B": "#0d9488",  # Verde-azulado / Teal
            "Fornecedor C": "#f59e0b",  # Âmbar / Laranja
        }

        fig_tradeoff = px.scatter(
            df_graf_tradeoff,
            x="prazo_dias",
            y="preco_cotado",
            color="fornecedor_cotacao",
            size="lote_minimo",
            color_discrete_map=paleta_fornecedores,
            labels={
                "prazo_dias": "Prazo de Entrega (Dias Úteis)",
                "preco_cotado": "Preço Cotado (R$)",
                "fornecedor_cotacao": "Fornecedor",
                "lote_minimo": "Lote Mínimo (unidades)",
            },
            custom_data=["nome_produto", "sku", "nome_categoria", "fornecedor_cotacao", "lote_minimo"],
        )

        fig_tradeoff.update_traces(
            hovertemplate=(
                "<b>Produto:</b> %{customdata[0]}<br>"
                "<b>SKU:</b> %{customdata[1]} | <b>Categoria:</b> %{customdata[2]}<br>"
                "<b>Fornecedor:</b> %{customdata[3]}<br>"
                "<b>Preço:</b> R$ %{y:,.2f}<br>"
                "<b>Prazo:</b> %{x} dias úteis<br>"
                "<b>Lote Mínimo:</b> %{customdata[4]} un<extra></extra>"
            )
        )

        # Configuração de layout com margens e respiro visual para as bolhas
        min_prazo = float(df_graf_tradeoff["prazo_dias"].min()) if not df_graf_tradeoff.empty else 0
        max_prazo = float(df_graf_tradeoff["prazo_dias"].max()) if not df_graf_tradeoff.empty else 15
        min_preco = float(df_graf_tradeoff["preco_cotado"].min()) if not df_graf_tradeoff.empty else 0
        max_preco = float(df_graf_tradeoff["preco_cotado"].max()) if not df_graf_tradeoff.empty else 1000

        fig_tradeoff.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=480,
            margin=dict(t=30, b=40, l=40, r=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig_tradeoff.update_xaxes(
            showgrid=True,
            gridcolor="#e2e8f0",
            title_text="Prazo de Entrega (Dias Úteis)",
            range=[max(0, min_prazo - 1.5), max_prazo + 1.5],
        )
        fig_tradeoff.update_yaxes(
            showgrid=True,
            gridcolor="#e2e8f0",
            title_text="Preço Cotado (R$)",
            range=[max(0, min_preco * 0.90), max_preco * 1.08],
        )
        st.plotly_chart(fig_tradeoff, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 5. Comparador Detalhado por SKU
        st.markdown("##### 🔍 Comparador Concorrencial por Produto")
        st.caption("Selecione um produto para auditar e comparar todas as propostas ativas submetidas pelos parceiros.")

        produtos_disponiveis = sorted(df_cot_filtrado["nome_produto"].unique().tolist())
        produto_selecionado = st.selectbox(
            "Selecione o Produto para Comparação Direta:",
            options=produtos_disponiveis,
            key="select_produto_cotacao",
        )

        df_sku_cot = df_cot_filtrado[df_cot_filtrado["nome_produto"] == produto_selecionado].sort_values(by="preco_cotado", ascending=True).copy()

        if not df_sku_cot.empty:
            preco_base_prod = float(df_sku_cot["preco_referencia"].iloc[0])
            menor_oferta = float(df_sku_cot["preco_cotado"].min())
            maior_oferta = float(df_sku_cot["preco_cotado"].max())
            spread_oferta = maior_oferta - menor_oferta

            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            col_p1.metric("Preço de Tabela (Base)", formatar_moeda_brl(preco_base_prod))
            col_p2.metric(
                "Menor Oferta (Best Price)",
                formatar_moeda_brl(menor_oferta),
                delta=f"-{((preco_base_prod - menor_oferta)/preco_base_prod)*100:.1f}%" if preco_base_prod > 0 else None,
            )
            col_p3.metric("Maior Oferta", formatar_moeda_brl(maior_oferta))
            col_p4.metric("Spread Concorrencial", formatar_moeda_brl(spread_oferta))

            # Flag de classificação
            df_sku_cot["resultado"] = [
                "🏆 Vencedora (Melhor Preço)" if p == menor_oferta else "Concorrente"
                for p in df_sku_cot["preco_cotado"]
            ]
            df_sku_cot["variacao_pct"] = ((df_sku_cot["preco_cotado"] - preco_base_prod) / preco_base_prod) * 100

            st.dataframe(
                df_sku_cot[[
                    "resultado", "fornecedor_cotacao", "preco_cotado", "variacao_pct",
                    "lote_minimo", "prazo_dias", "data_cotacao"
                ]],
                column_config={
                    "resultado": st.column_config.TextColumn("Status da Oferta"),
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor"),
                    "preco_cotado": st.column_config.NumberColumn("Preço Cotado", format="R$ %.2f"),
                    "variacao_pct": st.column_config.NumberColumn("Variação vs Tabela", format="%+.1f%%"),
                    "lote_minimo": st.column_config.NumberColumn("Lote Mínimo", format="%d un"),
                    "prazo_dias": st.column_config.NumberColumn("Prazo de Entrega", format="%d dias"),
                    "data_cotacao": st.column_config.DatetimeColumn("Data da Cotação", format="DD/MM/YYYY HH:mm"),
                },
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.info("ℹ️ Nenhuma cotação encontrada para os filtros selecionados.")


# ------------------------------------------------------------------------------
# ABA 4: TABELA OPERACIONAL & EXPORTAÇÃO
# ------------------------------------------------------------------------------
with tab_tabela:
    st.markdown(
        '<div class="tab-banner">📋 <strong>Cenário Tático & Auditoria:</strong> Consulta detalhada de todos os itens cadastrados com filtros flexíveis e extração em formato CSV para rotinas operacionais.</div>',
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