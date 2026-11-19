"""Dashboard Executivo de Estoque (Streamlit).

Este arquivo monta a página: filtros, indicadores e abas.
O conteúdo de cada aba fica em dashboard/aba_*.py.
"""

from datetime import date

import pandas as pd
import streamlit as st

from assistente_estoque import renderizar_interface_chat
from dashboard import aba_compras, aba_fornecedores, aba_ranking, aba_tabela, aba_visao_geral, pagina_inicial
from dashboard.dados import (
    carregar_dados_analiticos,
    carregar_dados_cotacoes,
    carregar_ocorrencias,
    obter_conexao,
)
from dashboard.estilo import aplicar_estilo
from dashboard.componentes import cabecalho, cartoes_kpi
from dashboard.formatacao import formatar_moeda_brl
from regras_estoque import LIMITE_ALERTA
from regras_fornecedores import avaliar_cotacoes, ranking_fornecedores

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Dashboard Executivo de Estoque",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="auto",
)

# Página inicial (apresentação) até o visitante escolher abrir a demonstração
if st.query_params.get("tela") != "painel":
    pagina_inicial.renderizar()
    st.stop()


def _voltar_ao_inicio() -> None:
    st.query_params.pop("tela", None)


aplicar_estilo()

engine = obter_conexao()
df = carregar_dados_analiticos()
df_cot = carregar_dados_cotacoes()
df_ocorrencias = carregar_ocorrencias()

# Ranking de fornecedores e nota de cada cotação (preço, prazo, lote e confiabilidade)
ranking = ranking_fornecedores(
    df_cot, df_ocorrencias, date.today(), chave_produto="sku", coluna_fornecedor="fornecedor_cotacao",
)
df_cot_avaliado = avaliar_cotacoes(df_cot, ranking, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")


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
total_itens = int(df_filtrado["quantidade_disponivel"].sum())
valor_total = float(df_filtrado["valor_total_estoque"].sum())
itens_criticos = int((df_filtrado["status_reposicao"] == "CRITICO").sum())
itens_alerta = int((df_filtrado["status_reposicao"] == "ALERTA").sum())

total_skus = len(df_filtrado)
pct_criticos = (itens_criticos / total_skus * 100) if total_skus else 0
valor_medio_sku = (valor_total / total_skus) if total_skus else 0

chips = [f"📦 {len(df)} SKUs monitorados"]
if not df.empty and "data_carga" in df.columns:
    chips.insert(0, f"🕒 Última carga: {pd.to_datetime(df['data_carga'].max()).strftime('%d/%m/%Y %H:%M')}")

st.button("← Voltar ao início", type="tertiary", on_click=_voltar_ao_inicio)

cabecalho(
    titulo="Monitoramento e Gestão Analítica de Estoque",
    texto="Painel executivo com saúde do estoque, concentração de fornecedores e inteligência de compras em um só lugar.",
    conectado=engine is not None,
    chips=chips,
)

cartoes_kpi([
    {
        "icone": "📦", "rotulo": "Volume físico", "tom": "marca", "efeito": "caixa",
        "valor": f"{total_itens:,} un".replace(",", "."),
        "detalhe": f"{total_skus} SKUs no filtro atual",
    },
    {
        "icone": "💰", "rotulo": "Capital imobilizado", "tom": "positivo", "efeito": "moedas",
        "valor": formatar_moeda_brl(valor_total),
        "detalhe": f"Média de {formatar_moeda_brl(valor_medio_sku)} por SKU",
    },
    {
        "icone": "🚨", "rotulo": "Produtos críticos", "tom": "critico", "efeito": "sirene",
        "valor": itens_criticos,
        "detalhe": f"{pct_criticos:.0f}% dos SKUs com estoque zerado",
    },
    {
        "icone": "⚠️", "rotulo": "Produtos em alerta", "tom": "alerta", "efeito": "alerta",
        "valor": itens_alerta,
        "detalhe": f"Com até {LIMITE_ALERTA} unidades em estoque",
    },
])


# ==============================================================================
# 4. ESTRUTURA MODULAR EM ABAS (st.tabs)
# ==============================================================================
tab_visao_geral, tab_fornecedores, tab_compras, tab_ranking, tab_tabela, tab_assistente = st.tabs([
    "📊 Visão Geral & Ruptura",
    "🏭 Análise de Fornecedores",
    "💡 Inteligência de Compras",
    "🛡️ Ranking & Risco",
    "📋 Tabela Operacional & Exportação",
    "🤖 Assistente IA & Compras",
])


with tab_visao_geral:
    aba_visao_geral.renderizar(df_filtrado, valor_total)

with tab_fornecedores:
    aba_fornecedores.renderizar(df_filtrado)

with tab_compras:
    aba_compras.renderizar(df_cot_filtrado, df_cot_avaliado)

with tab_ranking:
    aba_ranking.renderizar(df_cot, df_ocorrencias)

with tab_tabela:
    aba_tabela.renderizar(df_filtrado)

with tab_assistente:
    renderizar_interface_chat(engine)
