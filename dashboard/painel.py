"""Painel executivo (filtros, indicadores e abas), alimentado pela demonstração ou pela planilha do usuário."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from assistente_estoque import renderizar_interface_chat
from dashboard import aba_compras, aba_fornecedores, aba_previsao, aba_ranking, aba_tabela, aba_visao_geral
from dashboard.componentes import aviso_dados_faltando, cabecalho, cartoes_kpi
from dashboard.estilo import aplicar_estilo
from dashboard.formatacao import formatar_moeda_brl
from regras_estoque import LIMITE_ALERTA
from previsao_demanda import texto_para_ia
from regras_fornecedores import avaliar_cotacoes, ranking_fornecedores

NAO_INFORMADO = "Não informado"
COLUNAS_COTACOES = [
    "id_cotacao", "sku", "nome_produto", "nome_categoria", "preco_referencia", "fornecedor_cotacao",
    "preco_cotado", "lote_minimo", "prazo_dias", "data_cotacao", "status_reposicao", "quantidade_disponivel",
]
COLUNAS_OCORRENCIAS = [
    "id_ocorrencia", "fornecedor", "nome_produto", "tipo", "gravidade", "data_ocorrencia", "status",
    "data_resolucao", "descricao",
]


@dataclass
class Fonte:
    """De onde vêm os dados do painel."""
    estoque: pd.DataFrame
    cotacoes: pd.DataFrame
    ocorrencias: pd.DataFrame
    vendas: pd.DataFrame | None = None     # histórico de vendas (None = não enviado)
    engine: object = None                  # conexão do banco (só na demonstração)
    usuario: bool = False                  # True = planilha enviada (dados só na sessão)
    limite_alerta: int = LIMITE_ALERTA
    enviado_em: datetime | None = None
    planilha_limpa: object = None          # callable que gera o Excel higienizado

    @classmethod
    def da_planilha(cls, resultado, limite_alerta: int, enviado_em: datetime, planilha_limpa) -> "Fonte":
        def ou_vazio(df, colunas):
            return df if df is not None else pd.DataFrame(columns=colunas)
        return cls(
            estoque=resultado.estoque,
            cotacoes=ou_vazio(resultado.cotacoes, COLUNAS_COTACOES),
            ocorrencias=ou_vazio(resultado.ocorrencias, COLUNAS_OCORRENCIAS),
            vendas=resultado.vendas if resultado.vendas is not None and not resultado.vendas.empty else None,
            usuario=True, limite_alerta=limite_alerta, enviado_em=enviado_em, planilha_limpa=planilha_limpa,
        )


def _voltar_ao_inicio() -> None:
    st.query_params.pop("tela", None)


def _filtrar(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    for coluna, valor in filtros.items():
        if valor is not None:
            df = df[df[coluna] == valor]
    return df


def _barra_lateral(fonte: Fonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    df, df_cot = fonte.estoque, fonte.cotacoes
    st.sidebar.header("🔍 Filtros de Consulta")
    categoria = st.sidebar.selectbox("Filtrar por Categoria:", ["Todas"] + sorted(df["nome_categoria"].dropna().unique().tolist()))
    fornecedor = st.sidebar.selectbox("Filtrar por Fornecedor:", ["Todos"] + sorted(df["fornecedor"].dropna().unique().tolist()))
    status = st.sidebar.selectbox("Filtrar por Status de Reposição:", ["Todos"] + sorted(df["status_reposicao"].dropna().unique().tolist()))

    categoria = None if categoria == "Todas" else categoria
    fornecedor = None if fornecedor == "Todos" else fornecedor
    status = None if status == "Todos" else status
    df_filtrado = _filtrar(df.copy(), {"nome_categoria": categoria, "fornecedor": fornecedor, "status_reposicao": status})
    df_cot_filtrado = _filtrar(df_cot.copy(), {"nome_categoria": categoria, "fornecedor_cotacao": fornecedor,
                                                "status_reposicao": status})

    st.sidebar.divider()
    if fonte.usuario:
        st.sidebar.caption("📂 **Fonte:** sua planilha (só nesta sessão)")
        if fonte.enviado_em:
            st.sidebar.caption(f"🕒 **Enviada às:** {fonte.enviado_em:%H:%M}")
        return df_filtrado, df_cot_filtrado

    if fonte.engine is not None:
        st.sidebar.caption("🟢 **Banco Conectado:** PostgreSQL (Neon)")
    else:
        st.sidebar.caption("🟠 **Modo:** Snapshot Local de Contingência")
    if not df.empty and "data_carga" in df.columns:
        st.sidebar.caption(f"🕒 **Última Carga:** {pd.to_datetime(df['data_carga'].max()):%d/%m/%Y %H:%M:%S}")
    if st.sidebar.button("🔄 Atualizar Dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    return df_filtrado, df_cot_filtrado


def _topo(fonte: Fonte) -> None:
    df = fonte.estoque
    if not fonte.usuario:
        st.button("← Voltar ao início", type="tertiary", on_click=_voltar_ao_inicio)
        chips = [f"📦 {len(df)} SKUs monitorados"]
        if not df.empty and "data_carga" in df.columns:
            chips.insert(0, f"🕒 Última carga: {pd.to_datetime(df['data_carga'].max()):%d/%m/%Y %H:%M}")
        cabecalho(
            titulo="Monitoramento e Gestão Analítica de Estoque",
            texto="Painel executivo com saúde do estoque, concentração de fornecedores e inteligência de compras em um só lugar.",
            conectado=fonte.engine is not None,
            chips=chips,
        )
        return

    from dashboard.pagina_envio import enviar_outra_planilha
    from higienizacao.exportacao import NOME_ARQUIVO_LIMPO

    with st.container(horizontal=True, wrap=True, gap="small", vertical_alignment="center"):
        st.button("← Voltar ao início", type="tertiary", on_click=_voltar_ao_inicio)
        st.button("📤 Enviar outra planilha", type="tertiary", on_click=enviar_outra_planilha, key="painel_enviar_outra")
        st.download_button(
            "📥 Baixar meus dados higienizados", data=fonte.planilha_limpa, file_name=NOME_ARQUIVO_LIMPO,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", on_click="ignore",
            type="tertiary", key="painel_baixar_limpa",
        )
    chips = ["📂 Seus dados", "🔒 Só nesta sessão", f"📦 {len(df)} produtos"]
    if fonte.enviado_em:
        chips.append(f"🕒 Enviada às {fonte.enviado_em:%H:%M}")
    cabecalho(
        titulo="Análise da sua planilha",
        texto="Os mesmos indicadores da demonstração, calculados com os dados que você enviou e higienizou.",
        conectado=None,
        chips=chips,
    )


def _indicadores(fonte: Fonte, df_filtrado: pd.DataFrame) -> float:
    total_itens = int(df_filtrado["quantidade_disponivel"].sum())
    valor_total = float(df_filtrado["valor_total_estoque"].sum())
    itens_criticos = int((df_filtrado["status_reposicao"] == "CRITICO").sum())
    itens_alerta = int((df_filtrado["status_reposicao"] == "ALERTA").sum())
    total_skus = len(df_filtrado)
    pct_criticos = (itens_criticos / total_skus * 100) if total_skus else 0
    valor_medio_sku = (valor_total / total_skus) if total_skus else 0

    detalhe_alerta = f"Com até {fonte.limite_alerta} unidades em estoque"
    if "estoque_minimo" in fonte.estoque.columns and fonte.estoque["estoque_minimo"].notna().any():
        detalhe_alerta = f"Até o estoque mínimo do produto (ou {fonte.limite_alerta} un)"

    cartoes_kpi([
        {"icone": "📦", "rotulo": "Volume físico", "tom": "marca", "efeito": "caixa",
         "valor": f"{total_itens:,} un".replace(",", "."), "detalhe": f"{total_skus} SKUs no filtro atual"},
        {"icone": "💰", "rotulo": "Capital imobilizado", "tom": "positivo", "efeito": "moedas",
         "valor": formatar_moeda_brl(valor_total), "detalhe": f"Média de {formatar_moeda_brl(valor_medio_sku)} por SKU"},
        {"icone": "🚨", "rotulo": "Produtos críticos", "tom": "critico", "efeito": "sirene",
         "valor": itens_criticos, "detalhe": f"{pct_criticos:.0f}% dos SKUs com estoque zerado"},
        {"icone": "⚠️", "rotulo": "Produtos em alerta", "tom": "alerta", "efeito": "alerta",
         "valor": itens_alerta, "detalhe": detalhe_alerta},
    ])
    return valor_total


def _previsao(fonte: Fonte, df_cot_avaliado: pd.DataFrame):
    """Previsão de demanda com os parâmetros escolhidos na aba (None se não há vendas)."""
    parametros = aba_previsao.parametros_atuais()
    hoje = date.today()
    if fonte.vendas is None or fonte.vendas.empty:
        return None, parametros, hoje
    # Planilha antiga: prevê a partir do dia seguinte à última venda registrada
    ultima = pd.to_datetime(fonte.vendas["data"]).max().date()
    hoje = min(hoje, ultima + timedelta(days=1))
    cotacoes = df_cot_avaliado if not df_cot_avaliado.empty else None
    previsao = aba_previsao.calcular(
        fonte.estoque, fonte.vendas, hoje, parametros.horizonte, parametros.seguranca, parametros.janela,
        parametros.prazo_manual, cotacoes,
    )
    return previsao, parametros, hoje


def renderizar(fonte: Fonte) -> None:
    aplicar_estilo()
    df_filtrado, df_cot_filtrado = _barra_lateral(fonte)

    # Ranking de fornecedores e nota de cada cotação (preço, prazo, lote e confiabilidade)
    df_cot = fonte.cotacoes
    if df_cot.empty:
        df_cot_avaliado = df_cot
    else:
        ranking = ranking_fornecedores(df_cot, fonte.ocorrencias, date.today(),
                                       chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")
        df_cot_avaliado = avaliar_cotacoes(df_cot, ranking, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")

    previsao, parametros, hoje = _previsao(fonte, df_cot_avaliado)

    _topo(fonte)
    valor_total = _indicadores(fonte, df_filtrado)

    (tab_visao_geral, tab_fornecedores, tab_compras, tab_ranking, tab_previsao, tab_tabela,
     tab_assistente) = st.tabs([
        "📊 Visão Geral & Ruptura",
        "🏭 Análise de Fornecedores",
        "💡 Inteligência de Compras",
        "🛡️ Ranking & Risco",
        "📈 Previsão de Demanda",
        "📋 Tabela Operacional & Exportação",
        "🤖 Assistente IA & Compras",
    ])

    with tab_visao_geral:
        aba_visao_geral.renderizar(df_filtrado, valor_total, previsao.tabela if previsao else None)

    with tab_fornecedores:
        if fonte.usuario and (fonte.estoque["fornecedor"] == NAO_INFORMADO).all():
            aviso_dados_faltando("fornecedor", "Sem o fornecedor de cada produto não dá para ver a concentração "
                                               "do estoque por fornecedor.", chave="falta_fornecedor_aba")
        else:
            aba_fornecedores.renderizar(df_filtrado)

    with tab_compras:
        if fonte.usuario and df_cot.empty:
            aba_compras.renderizar_cabecalho()
            aviso_dados_faltando("cotacoes", "Com as cotações comparamos preço, prazo e lote de cada fornecedor e "
                                             "simulamos a recompra.", chave="falta_cotacoes_compras")
        else:
            aba_compras.renderizar(df_cot_filtrado, df_cot_avaliado)

    with tab_ranking:
        aba_ranking.renderizar(df_cot, fonte.ocorrencias, usuario=fonte.usuario)

    with tab_previsao:
        aba_previsao.renderizar(previsao, parametros, df_filtrado["sku"], hoje,
                                tem_cotacoes=not df_cot.empty, usuario=fonte.usuario)

    with tab_tabela:
        aba_tabela.renderizar(df_filtrado)

    with tab_assistente:
        dados = (fonte.estoque, fonte.cotacoes, fonte.ocorrencias) if fonte.usuario else None
        texto_previsao = (texto_para_ia(previsao, parametros), texto_para_ia(previsao, parametros, limite=12)) \
            if previsao else None
        renderizar_interface_chat(fonte.engine, dados_usuario=dados, previsao=texto_previsao)
