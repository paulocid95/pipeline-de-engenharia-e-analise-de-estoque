import io
import random
import re
from datetime import date

import pandas as pd
import pytest
from openpyxl import load_workbook

from planilha_exemplo import (
    fornecedor_baguncado,
    montar_planilha_exemplo,
    preco_baguncado,
    quantidade_baguncada,
)
from simulacao_vendas import simular_vendas

HOJE = date(2026, 11, 18)

ESTOQUE = pd.DataFrame({
    "sku": ["FA001", "B-101", "SKU-C02", "FA004"],
    "nome_produto": ["Galaxy S23 128GB", "Galaxy A54 5G", "iPhone 15 Pro", "Carregador Turbo 30W"],
    "nome_categoria": ["Smartphones", "Smartphones", "Smartphones", "Carregadores"],
    "fornecedor": ["Fornecedor A", "Fornecedor B", "Fornecedor C", "Fornecedor A"],
    "preco_unitario": [4299.0, 1799.0, 7499.0, 89.9],
    "quantidade_disponivel": [15, 0, 4, 120],
})
COTACOES = pd.DataFrame({
    "sku": ["FA001", "FA001"], "nome_produto": ["Galaxy S23 128GB"] * 2,
    "fornecedor_cotacao": ["Fornecedor B", "Fornecedor D"], "preco_cotado": [4100.5, 3899.0],
    "lote_minimo": [5, 20], "prazo_dias": [4, 9],
})
OCORRENCIAS = pd.DataFrame({
    "fornecedor": ["Fornecedor D"], "nome_produto": [None], "tipo": ["JUDICIAL"], "gravidade": ["ALTA"],
    "data_ocorrencia": [date(2026, 10, 5)], "status": ["ABERTO"], "data_resolucao": [None],
    "descricao": ["Processo por quebra de contrato"],
})


def _numero(valor) -> float:
    """Desfaz os formatos de preço usados na planilha (só para conferir nos testes)."""
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).replace("R$", "").strip()
    if "," in s and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return float(s)


def _quantidade(valor) -> int:
    if valor in ("", None):
        return 0
    return int(float(re.match(r"\d+(?:,\d+)?", str(valor)).group().replace(",", ".")))


@pytest.fixture(scope="module")
def planilha():
    return montar_planilha_exemplo(ESTOQUE, COTACOES, OCORRENCIAS, HOJE)


def test_tem_todas_as_abas(planilha):
    wb = load_workbook(io.BytesIO(planilha))
    assert wb.sheetnames == ["Instruções", "Estoque", "Cotações", "Ocorrências", "Vendas"]


def test_estoque_parece_relatorio_de_erp(planilha):
    ws = load_workbook(io.BytesIO(planilha))["Estoque"]
    assert ws["A1"].value.startswith("Relatório de posição de estoque")
    assert ws["A3"].value == "Cód. Item"                 # cabeçalho fora da primeira linha
    assert ws.cell(row=ws.max_row, column=1).value == "TOTAL"


def test_bagunca_e_reversivel_no_estoque(planilha):
    df = pd.read_excel(io.BytesIO(planilha), sheet_name="Estoque", header=2, dtype=object).fillna("")
    df = df[df["Cód. Item"] != "TOTAL"]
    # Quantidade total e preços voltam exatamente aos originais (mesmo com SKUs duplicados)
    por_sku = df.groupby("Cód. Item")["Qtd Disp."].apply(lambda s: sum(_quantidade(v) for v in s))
    assert por_sku.to_dict() == dict(zip(ESTOQUE["sku"], ESTOQUE["quantidade_disponivel"]))
    precos = df.groupby("Cód. Item")["Preço Unit."].first().map(_numero)
    assert precos.to_dict() == pytest.approx(dict(zip(ESTOQUE["sku"], ESTOQUE["preco_unitario"])))


def test_planilha_e_deterministica():
    a = montar_planilha_exemplo(ESTOQUE, COTACOES, OCORRENCIAS, HOJE)
    b = montar_planilha_exemplo(ESTOQUE, COTACOES, OCORRENCIAS, HOJE)
    ler = lambda x: pd.read_excel(io.BytesIO(x), sheet_name=None)
    for aba, df in ler(a).items():
        pd.testing.assert_frame_equal(df, ler(b)[aba])


def test_ocorrencias_usam_rotulos_legiveis(planilha):
    df = pd.read_excel(io.BytesIO(planilha), sheet_name="Ocorrências")
    assert df.loc[0, "Ocorrência"] == "Processo judicial"
    assert df.loc[0, "Situação"].lower() == "em aberto"


@pytest.mark.parametrize("valor", [0.5, 89.9, 1234.5, 7499.0, 12345.67])
def test_formatos_de_preco_voltam_ao_valor(valor):
    rng = random.Random(1)
    for _ in range(30):
        assert _numero(preco_baguncado(valor, rng)) == pytest.approx(valor)


def test_formatos_de_quantidade_e_fornecedor():
    rng = random.Random(3)
    for _ in range(30):
        assert _quantidade(quantidade_baguncada(12, rng)) == 12
        variacao = fornecedor_baguncado("Fornecedor A", rng)
        assert "a" in variacao.lower()


def test_vendas_deterministicas_e_relativas_a_hoje():
    v1 = simular_vendas(ESTOQUE, HOJE, dias=30)
    v2 = simular_vendas(ESTOQUE, HOJE, dias=30)
    pd.testing.assert_frame_equal(v1, v2)
    assert 0 < len(v1) <= 30 * len(ESTOQUE)
    assert v1["data"].max() <= date(2026, 11, 17)          # até ontem
    assert (v1["quantidade_vendida"] > 0).all()            # só os dias com venda


def test_vendas_simuladas_parecem_de_loja_real():
    from simulacao_vendas import perfil_do_produto
    produtos = pd.DataFrame({"sku": [f"S{i}" for i in range(40)], "nome_produto": [f"P{i}" for i in range(40)],
                             "preco_unitario": [5000.0] * 20 + [50.0] * 20})
    v = simular_vendas(produtos, HOJE)
    assert not (pd.to_datetime(v["data"]).dt.weekday == 6).any()          # fechada aos domingos
    perfis = {perfil_do_produto(s, p) for s, p in zip(produtos["sku"], produtos["preco_unitario"])}
    assert perfis == {"regular", "alta", "queda", "esporadico"}


def test_planilha_respeita_limite_de_linhas(planilha):
    abas = pd.read_excel(io.BytesIO(planilha), sheet_name=None)
    assert all(len(df) <= 10_000 for df in abas.values())
