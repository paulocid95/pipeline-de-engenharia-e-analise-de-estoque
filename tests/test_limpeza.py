import numpy as np
import pandas as pd
import pytest

from limpeza_padronizacao import (
    COLUNAS_CANONICAS,
    deduzir_categoria,
    processar_fornecedor,
    sanitizar_estoque,
    sanitizar_preco,
)


# ------------------------------------------------------------------------------
# sanitizar_preco
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("R$ 4.299,00", 4299.00),   # moeda + milhar com ponto + decimal com vírgula
        ("R$ 89,90", 89.90),
        ("149,90", 149.90),
        ("1.350,00", 1350.00),
        ("4299.90", 4299.90),       # formato com ponto decimal
        ("  45  ", 45.0),
    ],
)
def test_sanitizar_preco_converte_formatos_validos(bruto, esperado):
    resultado = sanitizar_preco(pd.Series([bruto]))
    assert resultado.iloc[0] == pytest.approx(esperado)


@pytest.mark.parametrize("bruto", ["consultar", "0,00", "-10", "", None, np.nan])
def test_sanitizar_preco_invalida_textos_zerados_e_nulos(bruto):
    resultado = sanitizar_preco(pd.Series([bruto], dtype=object))
    assert pd.isna(resultado.iloc[0])


# ------------------------------------------------------------------------------
# sanitizar_estoque
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("15", 15),
        ("15 un", 15),        # sufixo de texto
        ("30.0", 30),         # número com casa decimal
        ("SEM ESTOQUE", 0),
        ("sem estoque", 0),
        ("-3", 0),            # negativo vira zero
        ("", 0),
        (None, 0),
        (np.nan, 0),
    ],
)
def test_sanitizar_estoque(bruto, esperado):
    resultado = sanitizar_estoque(pd.Series([bruto], dtype=object))
    assert resultado.iloc[0] == esperado


def test_sanitizar_estoque_retorna_inteiros():
    resultado = sanitizar_estoque(pd.Series(["10", "30.0", "SEM ESTOQUE"]))
    assert pd.api.types.is_integer_dtype(resultado)


# ------------------------------------------------------------------------------
# deduzir_categoria
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "produto, categoria, esperado",
    [
        ("Galaxy S23", "Smartfone", "Smartphones"),             # erro de digitação na categoria
        ("Fone P2", "FONE DE OUVIDO", "Fones de Ouvido"),        # caixa alta
        ("Fone TWS", "audio / fone ouvido", "Fones de Ouvido"),
        ("Carregador 30W", "carregadores", "Carregadores"),
        ("Xiaomi Redmi Note 13", None, "Smartphones"),           # categoria nula: deduz pelo nome
        ("Headphone bluetoth", np.nan, "Fones de Ouvido"),
        ("Base Indussão 15W", "", "Carregadores"),
        ("Mouse sem fio", "", "Outros"),                         # sem pista: Outros
    ],
)
def test_deduzir_categoria(produto, categoria, esperado):
    assert deduzir_categoria(produto, categoria) == esperado


# ------------------------------------------------------------------------------
# processar_fornecedor (fluxo completo de um arquivo)
# ------------------------------------------------------------------------------
def test_processar_fornecedor_padroniza_e_descarta_sem_preco(tmp_path, capsys):
    csv = tmp_path / "fornecedor_x.csv"
    csv.write_text(
        "codigo,nome,tipo,valor,qtd\n"
        'X1,Galaxy  S23,Smartfone,"R$ 4.299,00",15 un\n'
        'X2,Fone TWS,,"R$ 99,90",-3\n'
        "X3,Carregador 20W,carregadores,consultar,10\n",
        encoding="utf-8",
    )
    config = {
        "arquivo": "fornecedor_x.csv",
        "fornecedor_nome": "Fornecedor X",
        "de_para": {
            "codigo": "id_produto",
            "nome": "produto",
            "tipo": "categoria",
            "valor": "preco",
            "qtd": "estoque",
        },
    }

    df, metricas = processar_fornecedor("Fornecedor X", config, tmp_path)

    assert list(df.columns) == COLUNAS_CANONICAS
    assert metricas["qtd_inicial"] == 3
    assert metricas["qtd_final"] == 2          # X3 descartado por preço inválido
    assert metricas["descartes_preco"] == 1
    assert metricas["estoques_negativos_ajustados"] == 1

    x1 = df.set_index("id_produto").loc["X1"]
    assert x1["produto"] == "Galaxy S23"       # espaço duplo removido
    assert x1["categoria"] == "Smartphones"
    assert x1["preco"] == pytest.approx(4299.00)
    assert x1["estoque"] == 15
    assert x1["fornecedor"] == "Fornecedor X"

    x2 = df.set_index("id_produto").loc["X2"]
    assert x2["categoria"] == "Fones de Ouvido"  # deduzida pelo nome
    assert x2["estoque"] == 0                    # negativo ajustado
