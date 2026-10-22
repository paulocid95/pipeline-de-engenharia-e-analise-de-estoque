import os
from pathlib import Path
import time
import io
from dotenv import load_dotenv
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
import streamlit as st
from assistente_estoque import renderizar_interface_chat

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
try:
    database_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))
except Exception:
    database_url = os.getenv("DATABASE_URL")


def normalizar_url_banco(url: str) -> str:
    """Normaliza o esquema da URL para compatibilidade garantida com drivers PostgreSQL no SQLAlchemy."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@st.cache_resource
def obter_conexao():
    """Cria e reutiliza o pool de conexões do SQLAlchemy com o banco de dados Neon/Postgres com pre-ping e keepalive."""
    url_otimizada = normalizar_url_banco(database_url)
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 180,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }
    try:
        return create_engine(url_otimizada, **engine_kwargs)
    except Exception:
        # Fallback para a URL original com pre-ping e pool_recycle habilitados
        try:
            return create_engine(database_url, pool_pre_ping=True, pool_recycle=180)
        except Exception:
            return create_engine(database_url)


engine = obter_conexao()


def executar_query_com_retry(query_str: str, max_tentativas: int = 3) -> pd.DataFrame:
    """Executa consultas SQL com mecanismo de retry automático contra oscilações e quedas de conexão do Neon."""
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            return pd.read_sql(text(query_str), engine)
        except Exception as e:
            ultimo_erro = e
            # Em caso de SSL closed ou timeout, descarta conexões mortas do pool
            try:
                engine.dispose()
            except Exception:
                pass
            if tentativa < max_tentativas:
                time.sleep(0.5 * tentativa)
    raise ultimo_erro


# ==============================================================================
# 3. CONSULTA ANALÍTICA COM CACHE E ENRIQUECIMENTO DIMENSIONAL
# ==============================================================================
@st.cache_data(ttl=300)
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
    try:
        df_raw = executar_query_com_retry(query)
    except Exception as e:
        # Fallback de contingência caso o Neon esteja momentaneamente reiniciando
        caminho_csv = Path("dados_processados") / "estoque_consolidado_limpo.csv"
        if caminho_csv.exists():
            df_csv = pd.read_csv(caminho_csv)
            df_raw = pd.DataFrame({
                "sku": df_csv["id_produto"],
                "nome_produto": df_csv["produto"],
                "nome_categoria": df_csv["categoria"],
                "fornecedor": df_csv["fornecedor"],
                "preco_unitario": df_csv["preco"],
                "quantidade_disponivel": df_csv["estoque"],
                "valor_total_estoque": df_csv["preco"] * df_csv["estoque"],
                "status_reposicao": df_csv["estoque"].apply(
                    lambda q: "CRITICO" if q <= 5 else ("ALERTA" if q <= 15 else "NORMAL")
                ),
                "data_carga": pd.Timestamp.now(),
            })
            st.warning("⚠️ Conexão com o banco Neon em reinicialização rápida. Exibindo dados do snapshot local de contingência.")
        else:
            raise e

    # Fallback de integridade: se algum fornecedor estiver ausente, enriquece com a base consolidada
    if df_raw["fornecedor"].isna().any() or (df_raw["fornecedor"] == "Não Informado").any():
        caminho_csv = Path("dados_processados") / "estoque_consolidado_limpo.csv"
        if caminho_csv.exists():
            df_csv = pd.read_csv(caminho_csv)
            mapa_forn = dict(zip(df_csv["id_produto"], df_csv["fornecedor"]))
            df_raw["fornecedor"] = df_raw["fornecedor"].replace("Não Informado", pd.NA).fillna(df_raw["sku"].map(mapa_forn)).fillna("Não Informado")

    return df_raw.sort_values(by="valor_total_estoque", ascending=False)


@st.cache_data(ttl=300)
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
    try:
        return executar_query_com_retry(query)
    except Exception:
        return pd.DataFrame(columns=[
            "id_cotacao", "sku", "nome_produto", "nome_categoria", "preco_referencia",
            "fornecedor_cotacao", "preco_cotado", "lote_minimo", "prazo_dias",
            "data_cotacao", "status_reposicao", "quantidade_disponivel"
        ])


df = carregar_dados_analiticos()
df_cot = carregar_dados_cotacoes()


# ==============================================================================
# 4. FUNÇÕES UTILITÁRIAS DE FORMATAÇÃO E EXPORTAÇÃO
# ==============================================================================
def formatar_moeda_brl(valor: float) -> str:
    """Formata valor para a representação monetária brasileira (R$ 1.234,56)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_excel_estilizado(df: pd.DataFrame) -> bytes:
    """Gera uma planilha Excel (.xlsx) altamente estilizada e profissional em memória via openpyxl.
    
    Aplica formatação institucional com cabeçalho azul-escuro, autoajuste de largura de colunas,
    formatação monetária em R$ e alinhamento tático de dados operacionais.
    """
    df_export = df.rename(columns={
        "sku": "SKU",
        "nome_produto": "Produto",
        "nome_categoria": "Categoria",
        "fornecedor": "Fornecedor",
        "preco_unitario": "Preço Unitário",
        "quantidade_disponivel": "Quantidade em Estoque",
        "valor_total_estoque": "Valor Total em Estoque",
        "status_reposicao": "Status de Reposição"
    })

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Estoque_Consolidado", index=False)
        ws = writer.sheets["Estoque_Consolidado"]
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        # 1. Cabeçalho destacado institucional (Azul-Escuro e Branco)
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 28

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align

        # 2. Bordas e formatação das linhas de dados
        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        col_nomes = [cell.value for cell in ws[1]]
        idx_sku = col_nomes.index("SKU") + 1 if "SKU" in col_nomes else None
        idx_qtd = col_nomes.index("Quantidade em Estoque") + 1 if "Quantidade em Estoque" in col_nomes else None
        idx_status = col_nomes.index("Status de Reposição") + 1 if "Status de Reposição" in col_nomes else None
        idx_preco = col_nomes.index("Preço Unitário") + 1 if "Preço Unitário" in col_nomes else None
        idx_total = col_nomes.index("Valor Total em Estoque") + 1 if "Valor Total em Estoque" in col_nomes else None

        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            ws.row_dimensions[row[0].row].height = 20
            for cell in row:
                cell.font = Font(name="Calibri", size=10)
                cell.border = thin_border
                c_idx = cell.column

                # 4. Alinhamento centralizado em SKU, Quantidade e Status de Reposição
                if c_idx in [idx_sku, idx_qtd, idx_status]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                # 3. Formatação monetária adequada em colunas financeiras
                elif c_idx in [idx_preco, idx_total]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = '"R$" #,##0.00'
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

                if c_idx == idx_qtd:
                    cell.number_format = "#,##0"

        # 1. Autoajuste da largura de todas as colunas para que nenhum texto fique cortado
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if cell.number_format and "R$" in cell.number_format:
                    val = f"R$ {val},00"
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    return output.getvalue()


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

if st.sidebar.button("🔄 Atualizar Dados", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


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
tab_visao_geral, tab_fornecedores, tab_compras, tab_tabela, tab_assistente = st.tabs([
    "📊 Visão Geral & Ruptura",
    "🏭 Análise de Fornecedores",
    "💡 Inteligência de Compras",
    "📋 Tabela Operacional & Exportação",
    "🤖 Assistente IA & Compras",
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

        # 4. Painel Executivo de Trade-off Logístico vs. Financeiro
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.markdown("##### ⚖️ Matriz Comparativa de Trade-off: Custo vs. Agilidade Logística")
            st.caption("Comparativo consolidado por parceiro: contraste direto entre tempo de atendimento logístico e competitividade de preço negociado.")
        with col_t2:
            categorias_tradeoff = ["Todas as Categorias"] + sorted(df_cot_filtrado["nome_categoria"].dropna().unique().tolist())
            cat_tradeoff_selecionada = st.selectbox(
                "Filtrar Categoria na Análise:",
                categorias_tradeoff,
                key="sel_cat_tradeoff",
            )

        df_analise_tradeoff = df_cot_filtrado.copy()
        if cat_tradeoff_selecionada != "Todas as Categorias":
            df_analise_tradeoff = df_analise_tradeoff[df_analise_tradeoff["nome_categoria"] == cat_tradeoff_selecionada]

        if not df_analise_tradeoff.empty:
            # Cálculo de saving individual por cotação frente à tabela de referência
            df_analise_tradeoff["saving_pct_item"] = (
                (df_analise_tradeoff["preco_referencia"] - df_analise_tradeoff["preco_cotado"]) 
                / df_analise_tradeoff["preco_referencia"]
            ) * 100

            resumo_fornecedores = df_analise_tradeoff.groupby("fornecedor_cotacao").agg(
                prazo_medio=("prazo_dias", "mean"),
                preco_medio=("preco_cotado", "mean"),
                saving_medio=("saving_pct_item", "mean"),
                lote_medio=("lote_minimo", "mean"),
                total_itens=("id_cotacao", "count")
            ).reset_index()

            # Identificação de lideranças de trade-off
            mais_agil = resumo_fornecedores.loc[resumo_fornecedores["prazo_medio"].idxmin()]
            mais_economico = resumo_fornecedores.loc[resumo_fornecedores["saving_medio"].idxmax()]
            menor_lote = resumo_fornecedores.loc[resumo_fornecedores["lote_medio"].idxmin()]

            # 3 Cards de Síntese Executiva no Topo
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric(
                "⚡ Líder em Agilidade (Menor Prazo)",
                f"{mais_agil['fornecedor_cotacao']}",
                f"{mais_agil['prazo_medio']:.1f} dias médios",
                delta_color="normal"
            )
            kpi2.metric(
                "💰 Líder em Custo (Maior Saving)",
                f"{mais_economico['fornecedor_cotacao']}",
                f"+{mais_economico['saving_medio']:.1f}% vs tabela",
                delta_color="normal"
            )
            kpi3.metric(
                "📦 Menor Compromisso de Compra",
                f"{menor_lote['fornecedor_cotacao']}",
                f"{menor_lote['lote_medio']:.0f} un / pedido",
                delta_color="off"
            )

            st.markdown("<br>", unsafe_allow_html=True)

            # Dois Gráficos de Barras Horizontais Límpidos (Zero Sobreposição)
            col_g1, col_g2 = st.columns(2)

            paleta_fornecedores = {
                "Fornecedor A": "#2563eb",  # Azul Royal
                "Fornecedor B": "#0d9488",  # Teal / Verde-azulado
                "Fornecedor C": "#f59e0b",  # Âmbar / Laranja
            }

            with col_g1:
                # Gráfico 1: Prazo Médio (quanto menor, mais ágil)
                df_prazo = resumo_fornecedores.sort_values(by="prazo_medio", ascending=False)
                fig_prazo = go.Figure(
                    go.Bar(
                        x=df_prazo["prazo_medio"],
                        y=df_prazo["fornecedor_cotacao"],
                        orientation="h",
                        marker=dict(
                            color=[paleta_fornecedores.get(f, "#64748b") for f in df_prazo["fornecedor_cotacao"]],
                            line=dict(width=0),
                        ),
                        text=[f"<b>{p:.1f} dias úteis</b>" for p in df_prazo["prazo_medio"]],
                        textposition="auto",
                        textfont=dict(color="#ffffff", size=13),
                        hovertemplate="<b>%{y}</b><br>Prazo Médio: %{x:.1f} dias úteis<extra></extra>",
                    )
                )
                fig_prazo.update_layout(
                    title=dict(text="<b>🚚 Agilidade Logística</b> (Prazo Médio de Entrega)", font=dict(size=14, color="#1e293b")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=260,
                    margin=dict(t=45, b=25, l=10, r=20),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        title="Dias Úteis (menor barra = mais ágil)",
                        zeroline=False,
                    ),
                    yaxis=dict(
                        showgrid=False,
                        tickfont=dict(size=12, color="#0f172a"),
                    ),
                )
                st.plotly_chart(fig_prazo, use_container_width=True)

            with col_g2:
                # Gráfico 2: Saving Médio (% de Desconto frente à referência)
                df_saving = resumo_fornecedores.sort_values(by="saving_medio", ascending=True)
                fig_saving = go.Figure(
                    go.Bar(
                        x=df_saving["saving_medio"],
                        y=df_saving["fornecedor_cotacao"],
                        orientation="h",
                        marker=dict(
                            color=[paleta_fornecedores.get(f, "#64748b") for f in df_saving["fornecedor_cotacao"]],
                            line=dict(width=0),
                        ),
                        text=[f"<b>+{s:.1f}% saving</b>" for s in df_saving["saving_medio"]],
                        textposition="auto",
                        textfont=dict(color="#ffffff", size=13),
                        hovertemplate="<b>%{y}</b><br>Economia Média: %{x:.2f}%<extra></extra>",
                    )
                )
                fig_saving.update_layout(
                    title=dict(text="<b>💰 Competitividade de Custo</b> (Saving Médio vs. Tabela)", font=dict(size=14, color="#1e293b")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=260,
                    margin=dict(t=45, b=25, l=10, r=20),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        title="% de Economia em Relação ao Preço Base",
                        ticksuffix="%",
                        zeroline=False,
                    ),
                    yaxis=dict(
                        showgrid=False,
                        tickfont=dict(size=12, color="#0f172a"),
                    ),
                )
                st.plotly_chart(fig_saving, use_container_width=True)

            # 4. Quadro Sintético de Decisão de Compra
            st.markdown("###### 📋 Quadro Sintético de Decisão de Compra")
            
            def classificar_estrategia(row):
                if row["fornecedor_cotacao"] == mais_agil["fornecedor_cotacao"] and row["fornecedor_cotacao"] == mais_economico["fornecedor_cotacao"]:
                    return "⭐ Campeão Geral: Melhor Preço e Entrega Mais Rápida"
                elif row["fornecedor_cotacao"] == mais_agil["fornecedor_cotacao"]:
                    return "🚀 Entrega Rápida: Indicado para Reposições Urgentes e Rupturas"
                elif row["fornecedor_cotacao"] == mais_economico["fornecedor_cotacao"]:
                    return "💡 Menor Custo: Indicado para Compras Programadas de Alto Volume"
                elif row["fornecedor_cotacao"] == menor_lote["fornecedor_cotacao"]:
                    return "📦 Baixo Volume: Indicado para Testes de Demanda e Estoque Enxuto"
                else:
                    return "⚖️ Oferta Equilibrada: Alternativa Concorrencial"

            df_tabela_tradeoff = resumo_fornecedores.copy()
            df_tabela_tradeoff["recomendacao"] = df_tabela_tradeoff.apply(classificar_estrategia, axis=1)

            st.dataframe(
                df_tabela_tradeoff[[
                    "fornecedor_cotacao", "prazo_medio", "saving_medio", "preco_medio", "lote_medio", "recomendacao"
                ]],
                column_config={
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor Parceiro"),
                    "prazo_medio": st.column_config.NumberColumn("Prazo Médio", format="%.1f dias úteis"),
                    "saving_medio": st.column_config.NumberColumn("Saving Médio", format="+%.1f%%"),
                    "preco_medio": st.column_config.NumberColumn("Preço Médio Cotado", format="R$ %.2f"),
                    "lote_medio": st.column_config.NumberColumn("Lote Mínimo Médio", format="%.0f un"),
                    "recomendacao": st.column_config.TextColumn("Recomendação Estratégica"),
                },
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Nenhuma cotação encontrada para a categoria selecionada.")

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


# ------------------------------------------------------------------------------
# ABA 5: ASSISTENTE DE IA & INTELIGÊNCIA DE COMPRAS
# ------------------------------------------------------------------------------
with tab_assistente:
    renderizar_interface_chat(engine)