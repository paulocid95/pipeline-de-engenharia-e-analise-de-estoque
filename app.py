"""Dashboard Executivo de Estoque (Streamlit).

Este arquivo monta a página: filtros, indicadores e abas.
O conteúdo de cada aba fica em dashboard/aba_*.py.
"""

import pandas as pd
import streamlit as st

from assistente_estoque import renderizar_interface_chat
from dashboard import aba_compras, aba_fornecedores, aba_tabela, aba_visao_geral
from dashboard.dados import carregar_dados_analiticos, carregar_dados_cotacoes, obter_conexao
from dashboard.estilo import aplicar_estilo
from dashboard.formatacao import formatar_moeda_brl

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Dashboard Executivo de Estoque",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

aplicar_estilo()

engine = obter_conexao()
df = carregar_dados_analiticos()
df_cot = carregar_dados_cotacoes()


# ==============================================================================
# 2. BARRA LATERAL - FILTROS DINÂMICOS
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
if engine is not None:
    st.sidebar.caption("🟢 **Banco Conectado:** PostgreSQL (Neon)")
else:
    st.sidebar.caption("🟠 **Modo:** Snapshot Local de Contingência")
if not df.empty and "data_carga" in df.columns:
    ultima_atualizacao = pd.to_datetime(df["data_carga"].max()).strftime("%d/%m/%Y %H:%M:%S")
    st.sidebar.caption(f"🕒 **Última Carga:** {ultima_atualizacao}")

if st.sidebar.button("🔄 Atualizar Dados", width="stretch"):
    st.cache_data.clear()
    st.rerun()


# ==============================================================================
# 3. CABEÇALHO E SCORECARDS EXECUTIVOS
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
# 4. ESTRUTURA MODULAR EM ABAS (st.tabs)
# ==============================================================================
tab_visao_geral, tab_fornecedores, tab_compras, tab_tabela, tab_assistente = st.tabs([
    "📊 Visão Geral & Ruptura",
    "🏭 Análise de Fornecedores",
    "💡 Inteligência de Compras",
    "📋 Tabela Operacional & Exportação",
    "🤖 Assistente IA & Compras",
])


with tab_visao_geral:
    aba_visao_geral.renderizar(df_filtrado, valor_total)

with tab_fornecedores:
    aba_fornecedores.renderizar(df_filtrado)

with tab_compras:
    aba_compras.renderizar(df_cot_filtrado)

with tab_tabela:
    aba_tabela.renderizar(df_filtrado)

with tab_assistente:
    renderizar_interface_chat(engine)
