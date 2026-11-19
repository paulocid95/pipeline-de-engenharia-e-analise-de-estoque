"""Montar e baixar o pedido de compra (aba Previsão) e o atalho na aba Compras."""

import zlib
from datetime import date

import pandas as pd
import streamlit as st

from dashboard.formatacao import formatar_moeda_brl
from pedido_compra import (
    MIME_XLSX,
    abaixo_do_lote,
    itens_do_pedido,
    itens_sugeridos,
    nome_arquivo,
    planilha_pedido,
    resumo_por_fornecedor,
)
from previsao_demanda import Parametros


def _chave(base: pd.DataFrame) -> str:
    """Muda quando a sugestão muda (filtros ou parâmetros), para não aplicar edições antigas em outra lista."""
    assinatura = "|".join(f"{s}:{q}" for s, q in zip(base["sku"], base["quantidade"]))
    return f"pedido_editor_{zlib.crc32(assinatura.encode('utf-8'))}"


def itens_atuais(base: pd.DataFrame) -> pd.DataFrame:
    """A sugestão com as mudanças que o usuário fez na tabela editável."""
    itens = base.copy()
    edicoes = st.session_state.get(_chave(base), {}).get("edited_rows", {})
    for linha, mudancas in edicoes.items():
        for coluna, valor in mudancas.items():
            if coluna in ("incluir", "quantidade") and int(linha) < len(itens):
                itens.at[int(linha), coluna] = valor
    return itens


def _botao_download(itens: pd.DataFrame, hoje: date, chave: str, rotulo: str = "📥 Baixar pedido de compra (Excel)") -> None:
    st.download_button(
        rotulo, data=lambda: planilha_pedido(itens, hoje), file_name=nome_arquivo(hoje), mime=MIME_XLSX,
        type="primary", on_click="ignore", key=chave, disabled=itens_do_pedido(itens).empty,
        help="Uma aba de resumo e uma aba por fornecedor, com preço, subtotal, prazo, chegada prevista e motivo.",
    )


def _resumo(itens: pd.DataFrame, hoje: date) -> None:
    escolhidos = itens_do_pedido(itens)
    resumo = resumo_por_fornecedor(escolhidos, hoje)
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Itens no pedido", len(escolhidos), border=True)
    c2.metric("🏭 Fornecedores", len(resumo), border=True)
    c3.metric("💰 Total do pedido", formatar_moeda_brl(float(resumo["total"].sum()) if not resumo.empty else 0.0),
              border=True)
    if not resumo.empty:
        st.caption(" · ".join(f"**{r.fornecedor}**: {r.itens} item(ns), {formatar_moeda_brl(r.total)}, "
                              f"chega {r.chegada:%d/%m}" for r in resumo.itertuples()))
    fora_do_lote = abaixo_do_lote(escolhidos)
    if not fora_do_lote.empty:
        st.warning("⚠️ Quantidade fora do lote mínimo do fornecedor em: "
                   + ", ".join(f"**{r.produto}** (lote de {r.lote})" for r in fora_do_lote.itertuples())
                   + ". O fornecedor pode recusar ou arredondar o pedido.")


def editor(tabela: pd.DataFrame, parametros: Parametros, hoje: date) -> None:
    """Tabela editável (marcar itens e ajustar quantidades), resumo e botão de download."""
    st.subheader("📝 Pedido de compra")
    base = itens_sugeridos(tabela, parametros)
    if base.empty:
        st.success("✅ Nenhum produto precisa de compra com os parâmetros atuais.")
        return
    st.caption("Já vêm marcados os produtos com sugestão de compra. Desmarque o que não quiser ou ajuste a "
               "quantidade; o arquivo terá uma aba por fornecedor, pronta para enviar.")
    editado = st.data_editor(
        base,
        key=_chave(base),
        column_order=["incluir", "produto", "fornecedor", "quantidade", "lote", "preco", "prazo", "motivo"],
        column_config={
            "incluir": st.column_config.CheckboxColumn("Incluir"),
            "produto": st.column_config.TextColumn("Produto", disabled=True),
            "fornecedor": st.column_config.TextColumn("Fornecedor", disabled=True),
            "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0, step=1, format="%d",
                                                        help="Sugestão já arredondada pelo lote mínimo."),
            "lote": st.column_config.NumberColumn("Lote mínimo", format="%d", disabled=True),
            "preco": st.column_config.NumberColumn("Preço unitário", format="R$ %.2f", disabled=True),
            "prazo": st.column_config.NumberColumn("Prazo", format="%d dias", disabled=True),
            "motivo": st.column_config.TextColumn("Motivo da compra", disabled=True),
        },
        hide_index=True,
        width="stretch",
    )
    _resumo(editado, hoje)
    _botao_download(editado, hoje, chave="baixar_pedido_previsao")


def atalho(tabela: pd.DataFrame | None, parametros: Parametros, hoje: date) -> None:
    """Na aba Compras: o mesmo pedido (com as mudanças feitas na aba Previsão) para baixar direto."""
    if tabela is None:
        return
    base = itens_sugeridos(tabela, parametros)
    if base.empty:
        return
    itens = itens_atuais(base)
    escolhidos = itens_do_pedido(itens)
    total = float((escolhidos["quantidade"] * escolhidos["preco"]).sum()) if not escolhidos.empty else 0.0
    with st.container(border=True):
        st.markdown(f"**📝 Pedido de compra pronto:** {len(escolhidos)} item(ns) de "
                    f"{escolhidos['fornecedor'].nunique() if not escolhidos.empty else 0} fornecedor(es), "
                    f"total de {formatar_moeda_brl(total)}.")
        st.caption("Calculado pela previsão de demanda. Para escolher os itens ou mudar quantidades, use a aba "
                   "📈 Previsão de Demanda.")
        _botao_download(itens, hoje, chave="baixar_pedido_compras")
