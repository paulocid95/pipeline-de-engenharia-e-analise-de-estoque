"""Aba: Previsão de Demanda e sugestão de compra."""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard import pedido
from dashboard.componentes import aviso_dados_faltando
from dashboard.formatacao import formatar_moeda_brl
from dashboard.graficos import COR_DESTAQUE, COR_NEUTRA, exibir_grafico
from previsao_demanda import (
    LIMITE_CONFIANCA,
    SEM_HISTORICO,
    SEM_VENDAS,
    Parametros,
    ResultadoPrevisao,
    prever_estoque,
)

HORIZONTES = [7, 14, 30, 60]
JANELAS = [30, 60, 90]
_PADRAO = Parametros()
_FUNDO_FALTA = "background-color: rgba(239, 68, 68, 0.16)"
ICONE_CONFIANCA = {"Alta": "🎯 Alta", "Média": "〰️ Média", "Baixa": "❔ Baixa"}


# ------------------------------------------------------------------------------
# Parâmetros (lidos antes das abas, para a Visão Geral e a IA usarem os mesmos valores)
# ------------------------------------------------------------------------------
def parametros_atuais() -> Parametros:
    ss = st.session_state
    automatico = ss.get("prev_prazo_auto", True)
    return Parametros(
        horizonte=int(ss.get("prev_horizonte", _PADRAO.horizonte)),
        seguranca=int(ss.get("prev_seguranca", _PADRAO.seguranca)),
        janela=int(ss.get("prev_janela", _PADRAO.janela)),
        prazo_manual=None if automatico else int(ss.get("prev_prazo", _PADRAO.prazo_padrao)),
    )


@st.cache_data(show_spinner="📈 Calculando a previsão de cada produto...", max_entries=12, ttl=900)
def calcular(estoque: pd.DataFrame, vendas: pd.DataFrame, hoje: date, horizonte: int, seguranca: int, janela: int,
             prazo_manual: int | None, cotacoes: pd.DataFrame | None) -> ResultadoPrevisao:
    parametros = Parametros(horizonte=horizonte, seguranca=seguranca, janela=janela, prazo_manual=prazo_manual)
    return prever_estoque(estoque, vendas, hoje, parametros, cotacoes)


def _controles(tem_cotacoes: bool) -> None:
    with st.container(border=True):
        st.markdown("**⚙️ Parâmetros da previsão**")
        c1, c2, c3, c4 = st.columns(4)
        c1.selectbox("📅 A compra deve cobrir quantos dias?", HORIZONTES, index=HORIZONTES.index(_PADRAO.horizonte),
                     key="prev_horizonte", format_func=lambda d: f"{d} dias",
                     help="Depois que o pedido chegar, o estoque deve durar este período.")
        c2.slider("🛟 Estoque de segurança (dias)", 0, 30, _PADRAO.seguranca, key="prev_seguranca",
                  help="Dias extras de venda guardados para absorver variações e atrasos.")
        c3.selectbox("🗂️ Histórico usado", JANELAS, index=JANELAS.index(_PADRAO.janela), key="prev_janela",
                     format_func=lambda d: f"Últimos {d} dias",
                     help="Menos dias reage mais rápido a mudanças; mais dias é mais estável.")
        with c4:
            automatico = st.toggle("🚚💨 Prazo automático", value=True, key="prev_prazo_auto",
                                   disabled=not tem_cotacoes,
                                   help="Usa o prazo de entrega do fornecedor com a melhor nota (nunca um 🔴).")
            st.number_input("Prazo de reposição (dias)", 1, 120, _PADRAO.prazo_padrao, key="prev_prazo",
                            disabled=automatico and tem_cotacoes)


def _indicadores(tabela: pd.DataFrame) -> None:
    contagem = tabela["confianca"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⏳ Vão faltar antes da reposição", int(tabela["vai_faltar"].sum()), border=True)
    c2.metric("🛒 Produtos para comprar", int((tabela["quantidade_sugerida"] > 0).sum()), border=True)
    c3.metric("💰 Custo dos pedidos", formatar_moeda_brl(float(tabela["custo_pedido"].sum())), border=True)
    c4.metric("🎯 Confiança alta", f"{contagem.get('Alta', 0)} de {len(tabela)}", border=True,
              help=f"{contagem.get('Alta', 0)} alta · {contagem.get('Média', 0)} média · "
                   f"{contagem.get('Baixa', 0)} baixa (erro no teste das últimas semanas)")


def _situacao(linha) -> str:
    if linha["modelo"] == SEM_VENDAS:
        return "💤 Sem vendas"
    if linha["vai_faltar"]:
        return "⏳ Vai faltar"
    if linha["quantidade_sugerida"] > 0:
        return "🛒 Comprar"
    return "✅ Coberto"


def _acaba_em(linha) -> str:
    dias = linha["dias_ate_acabar"]
    if dias is None or pd.isna(dias):
        return "Mais de 6 meses"
    if dias == 0:
        return "Já zerado"
    return f"{int(dias)} dias ({linha['data_ruptura']:%d/%m})"


def _tabela(tabela: pd.DataFrame) -> None:
    falta = tabela["vai_faltar"].tolist()
    exibicao = pd.DataFrame({
        "Situação": [_situacao(l) for l in tabela.to_dict("records")],
        "Produto": tabela["nome_produto"],
        "Estoque": tabela["estoque"],
        "Venda prevista/dia": tabela["media_diaria"],
        "Acaba em": [_acaba_em(l) for l in tabela.to_dict("records")],
        "Prazo": tabela["prazo"],
        "Comprar": tabela["quantidade_sugerida"],
        "Fornecedor": tabela["fornecedor"].fillna("—"),
        "Custo": tabela["custo_pedido"],
        "Modelo": tabela["modelo"],
        "Erro": tabela["erro"].map(lambda e: "—" if e is None or pd.isna(e) else "> 100%" if e > 1 else f"{e:.0%}"),
        "Confiança": tabela["confianca"].map(ICONE_CONFIANCA),
    }).reset_index(drop=True)
    estilo = exibicao.style.apply(lambda l: [_FUNDO_FALTA if falta[l.name] else ""] * len(l), axis=1)
    st.dataframe(
        estilo,
        column_config={
            "Estoque": st.column_config.NumberColumn(format="%d un"),
            "Venda prevista/dia": st.column_config.NumberColumn(format="%.1f un"),
            "Prazo": st.column_config.NumberColumn("Prazo entrega", format="%d dias"),
            "Comprar": st.column_config.NumberColumn("Comprar (un)", format="%d"),
            "Custo": st.column_config.NumberColumn("Custo do pedido", format="R$ %.2f"),
            "Erro": st.column_config.TextColumn("Erro no teste",
                                                  help="Quanto o modelo errou o total de cada semana ao prever as "
                                                       "últimas semanas do histórico (escondidas dele)."),
        },
        hide_index=True,
        width="stretch",
    )


def _grafico(resultado: ResultadoPrevisao, linha: dict, parametros: Parametros, hoje: date) -> None:
    serie = resultado.series[linha["sku"]]
    historico = serie["historico"]
    dias_futuros = linha["prazo"] + parametros.horizonte
    futuras = serie["datas"][:dias_futuros]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=historico["data"], y=historico["real"], name="Vendas reais", marker_color=COR_NEUTRA,
                         hovertemplate="%{x|%d/%m}: %{y:.0f} un<extra>Vendido</extra>"))
    fig.add_trace(go.Scatter(x=futuras, y=serie["superior"][:dias_futuros], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=futuras, y=serie["inferior"][:dias_futuros], mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(37, 99, 235, 0.18)", name="Faixa provável (90%)",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=futuras, y=serie["previsto"][:dias_futuros], mode="lines+markers", name="Previsão",
                             line=dict(color=COR_DESTAQUE, width=2.5), marker=dict(size=4),
                             hovertemplate="%{x|%d/%m}: %{y:.1f} un<extra>Previsto</extra>"))
    fig.add_vline(x=hoje, line_dash="dot", line_color=COR_NEUTRA)
    chegada = hoje + timedelta(days=linha["prazo"])
    fig.add_vline(x=chegada, line_dash="dash", line_color="#10b981")
    fig.add_annotation(x=chegada, y=1, yref="paper", text="🚚💨 pedido chega", showarrow=False, yanchor="bottom")
    if linha["data_ruptura"] is not None and not pd.isna(linha["data_ruptura"]) and linha["dias_ate_acabar"]:
        fig.add_vline(x=linha["data_ruptura"], line_dash="dash", line_color="#ef4444")
        fig.add_annotation(x=linha["data_ruptura"], y=0.9, yref="paper", text="⏳ estoque acaba", showarrow=False,
                           yanchor="bottom", font=dict(color="#ef4444"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15), yaxis_title="Unidades por dia")
    exibir_grafico(fig)


def _explicar_compra(linha: dict, parametros: Parametros) -> None:
    if linha["modelo"] == SEM_VENDAS:
        st.info("💤 Este produto não teve vendas no período analisado, então não sugerimos compra.")
        return
    demanda_cobertura = linha["media_diaria"] * parametros.horizonte
    st.markdown(
        f"""
**Como chegamos na quantidade:**
- Venda prevista até o pedido chegar ({linha['prazo']} dias): **{linha['demanda_prazo']:.0f} un**
- Venda prevista nos {parametros.horizonte} dias seguintes: **≈ {demanda_cobertura:.0f} un**
- Segurança ({parametros.seguranca} dias): **{linha['seguranca_un']:.0f} un**
- Menos o estoque atual: **−{linha['estoque']} un**
- Arredondado para o lote mínimo de **{linha['lote']} un**: **{linha['quantidade_sugerida']} un**
  {f"de **{linha['fornecedor']}** (≈ {formatar_moeda_brl(linha['custo_pedido'])})" if linha['fornecedor'] else ''}
"""
    )
    if linha["modelo"] == SEM_HISTORICO:
        st.caption("❔ Pouco histórico: usamos a média simples das vendas. Confira antes de comprar.")
    else:
        erro = "mais de 100%" if linha["erro"] > 1 else f"{linha['erro']:.0%}"
        st.caption(f"Modelo vencedor: **{linha['modelo']}** · errou {erro} do total semanal "
                   f"ao prever as últimas semanas · confiança **{linha['confianca'].lower()}**.")


def _como_funciona() -> None:
    with st.expander("ℹ️ Como a previsão funciona"):
        st.markdown(
            f"""
1. **Calendário da loja:** descobrimos pelos dados em que dias a loja não vende (ex.: fechada aos domingos)
   e os dias atípicos sem nenhuma venda (feriados). Eles ficam fora do cálculo e a previsão não espera vendas
   neles. Lojas online, que vendem todos os dias, são reconhecidas automaticamente.
2. **Competição de modelos:** escondemos as últimas semanas do histórico de cada produto, pedimos para cada
   modelo prevê-las e comparamos com o que realmente vendeu. O que errar menos faz a previsão:
   - **Holt-Winters:** acompanha tendência (alta ou queda) e o padrão de cada dia da semana;
   - **Croston (SBA):** feito para produtos que vendem em dias soltos (venda esporádica);
   - **Média móvel semanal:** média recente ajustada pelo dia da semana; estável com pouco histórico;
   - **Ingênuo sazonal:** repete a última semana; é a referência mínima.
3. **Picos isolados** (promoções, uma compra grande atípica) são limitados para não inflarem a previsão.
4. **Confiança:** erro semanal no teste até {LIMITE_CONFIANCA['Alta']:.0%} = alta, até
   {LIMITE_CONFIANCA['Média']:.0%} = média, acima disso = baixa.
5. **Limite:** com poucos meses de vendas não dá para prever datas especiais do ano (Natal, Black Friday).
   Para isso são precisos 1 a 2 anos de histórico.
"""
        )


def renderizar(resultado: ResultadoPrevisao | None, parametros: Parametros, skus_filtrados, hoje: date,
               tem_cotacoes: bool, usuario: bool) -> None:
    st.markdown(
        '<div class="tab-banner">📈 <strong>Previsão de Demanda:</strong> quanto cada produto deve vender, quando o '
        "estoque acaba e quanto comprar de quem, com o modelo estatístico que melhor acertou o histórico de cada item.</div>",
        unsafe_allow_html=True,
    )
    if resultado is None:
        aviso_dados_faltando("vendas", "Com o histórico de vendas prevemos quando cada produto acaba e quanto "
                                       "comprar.", chave="falta_vendas_previsao")
        return

    _controles(tem_cotacoes)
    st.caption(f"🗓️ {resultado.calendario.descricao()} · previsão a partir de {hoje:%d/%m/%Y}")
    if not tem_cotacoes:
        st.caption("ℹ️ Sem cotações: usamos o prazo informado acima, lote de 1 unidade e o preço do estoque.")

    tabela = resultado.tabela[resultado.tabela["sku"].isin(set(skus_filtrados))]
    if tabela.empty:
        st.info("ℹ️ Nenhum produto nos filtros selecionados.")
        return
    _indicadores(tabela)
    st.subheader("🛒 Sugestão de compra por produto")
    st.caption("Em vermelho: produtos que vão acabar antes de um pedido feito hoje chegar.")
    _tabela(tabela)
    pedido.editor(tabela, parametros, hoje)

    st.subheader("🔍 Previsão de um produto")
    nomes = dict(zip(tabela["nome_produto"], tabela["sku"]))
    escolhido = st.selectbox("Produto", list(nomes), key="prev_produto")
    linha = tabela[tabela["sku"] == nomes[escolhido]].iloc[0].to_dict()
    col_grafico, col_texto = st.columns([2, 1])
    with col_grafico:
        _grafico(resultado, linha, parametros, hoje)
    with col_texto:
        _explicar_compra(linha, parametros)
    _como_funciona()
