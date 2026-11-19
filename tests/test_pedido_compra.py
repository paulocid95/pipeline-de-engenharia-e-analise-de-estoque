from datetime import date
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from pedido_compra import (
    SEM_FORNECEDOR,
    abaixo_do_lote,
    itens_do_pedido,
    itens_sugeridos,
    motivo,
    nome_da_aba,
    planilha_pedido,
    resumo_por_fornecedor,
)
from previsao_demanda import Parametros, prever_estoque
from simulacao_vendas import simular_vendas

HOJE = date(2026, 11, 18)


def _tabela() -> pd.DataFrame:
    base = dict(estoque=5, media_diaria=1.0, prazo=5, lote=10, preco=2.5, vai_faltar=False, dias_ate_acabar=20)
    return pd.DataFrame([
        {**base, "sku": "A", "nome_produto": "Arroz", "fornecedor": "Bom Ltda", "quantidade_sugerida": 20,
         "vai_faltar": True, "dias_ate_acabar": 2},
        {**base, "sku": "B", "nome_produto": "Feijão", "fornecedor": "Bom Ltda", "quantidade_sugerida": 10},
        {**base, "sku": "C", "nome_produto": "Café", "fornecedor": "Rápido/Express: SA", "quantidade_sugerida": 30,
         "prazo": 2, "preco": 10.0},
        {**base, "sku": "D", "nome_produto": "Sal", "fornecedor": None, "quantidade_sugerida": 3, "lote": 1},
        {**base, "sku": "E", "nome_produto": "Parado", "fornecedor": "Bom Ltda", "quantidade_sugerida": 0},
    ])


def test_itens_sugeridos_marca_so_quem_precisa_e_poe_quem_vai_faltar_primeiro():
    itens = itens_sugeridos(_tabela(), Parametros())
    assert list(itens["sku"]) == ["A", "B", "C", "D"]          # E não precisa de compra; A vai faltar
    assert itens["incluir"].all()
    assert itens.loc[3, "fornecedor"] == SEM_FORNECEDOR
    assert "antes do pedido chegar" in itens.loc[0, "motivo"]
    assert itens.loc[1, "motivo"].startswith("Cobre 30 dias")


def test_motivo_estoque_zerado():
    assert motivo({"dias_ate_acabar": 0, "vai_faltar": True, "prazo": 5}, Parametros()) == "Estoque zerado"


def test_desmarcados_e_quantidade_zero_ficam_fora():
    itens = itens_sugeridos(_tabela(), Parametros())
    itens.loc[1, "incluir"] = False
    itens.loc[2, "quantidade"] = 0
    assert list(itens_do_pedido(itens)["sku"]) == ["A", "D"]


def test_resumo_por_fornecedor_e_lote():
    itens = itens_do_pedido(itens_sugeridos(_tabela(), Parametros()))
    resumo = resumo_por_fornecedor(itens, HOJE).set_index("fornecedor")
    assert resumo.loc["Bom Ltda", "itens"] == 2 and resumo.loc["Bom Ltda", "total"] == 75.0
    assert resumo.loc["Rápido/Express: SA", "chegada"] == date(2026, 11, 20)
    itens.loc[0, "quantidade"] = 15                              # lote de 10
    assert list(abaixo_do_lote(itens)["sku"]) == ["A"]


def test_nome_da_aba_valido_e_sem_repetir():
    usados = {"resumo"}
    assert nome_da_aba("Rápido/Express: SA", usados) == "Rápido Express  SA"
    longo = "Distribuidora de Alimentos do Brasil Central"
    a, b = nome_da_aba(longo, usados), nome_da_aba(longo, usados)
    assert len(a) <= 31 and len(b) <= 31 and a != b
    assert nome_da_aba("Resumo", usados) == "Resumo (2)"


def test_planilha_tem_resumo_e_uma_aba_por_fornecedor_com_formulas():
    itens = itens_sugeridos(_tabela(), Parametros())
    itens.loc[1, "incluir"] = False
    livro = load_workbook(BytesIO(planilha_pedido(itens, HOJE)))
    assert livro.sheetnames[0] == "Resumo" and len(livro.sheetnames) == 4
    bom = livro["Bom Ltda"]
    assert bom["A1"].value == "Pedido de compra: Bom Ltda"
    assert [bom.cell(row=5, column=c).value for c in (1, 3, 5)] == ["A", 20, 2.5]
    assert bom["F5"].value == "=C5*E5" and bom["F6"].value == "=SUM(F5:F5)"
    assert bom["H5"].value.date() == date(2026, 11, 23) and "antes do pedido chegar" in bom["I5"].value
    resumo = livro["Resumo"]
    linhas = {resumo.cell(row=r, column=1).value: r for r in range(5, 9)}
    assert resumo.cell(row=linhas["Bom Ltda"], column=4).value == "='Bom Ltda'!F6"
    assert resumo.cell(row=linhas["Total geral"], column=4).value == "=SUM(D5:D7)"


def test_planilha_vazia_nao_quebra():
    itens = itens_sugeridos(_tabela(), Parametros())
    itens["incluir"] = False
    livro = load_workbook(BytesIO(planilha_pedido(itens, HOJE)))
    assert livro.sheetnames == ["Resumo"] and livro["Resumo"]["A5"].value == "Nenhum item selecionado."


def test_pedido_da_demonstracao_completa():
    produtos = pd.DataFrame({
        "sku": [f"P{i:02d}" for i in range(15)], "nome_produto": [f"Produto {i}" for i in range(15)],
        "preco_unitario": 50.0, "quantidade_disponivel": [i % 4 for i in range(15)],
    })
    previsao = prever_estoque(produtos, simular_vendas(produtos, HOJE), HOJE)
    itens = itens_sugeridos(previsao.tabela, Parametros())
    assert not itens.empty and (itens["quantidade"] > 0).all()
    livro = load_workbook(BytesIO(planilha_pedido(itens, HOJE)))
    assert livro.sheetnames == ["Resumo", SEM_FORNECEDOR]        # sem cotações: um fornecedor a definir
