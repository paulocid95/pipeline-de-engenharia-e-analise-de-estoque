"""Histórico simulado de vendas diárias por produto (dados de demonstração).

Determinístico: o mesmo SKU sempre tem o mesmo ritmo de vendas, e as datas são
relativas a `hoje`, então o histórico nunca envelhece. Usado na planilha de
exemplo e, depois, na previsão de demanda.
"""

import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

DIAS_HISTORICO = 90

# Segunda a domingo: sexta e sábado vendem mais, domingo vende menos
FATOR_DIA_SEMANA = [1.0, 0.95, 0.95, 1.0, 1.15, 1.3, 0.7]


def _gerador(sku: str, seed: int) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(f"{seed}-{sku}".encode("utf-8")))


def simular_vendas(
    produtos: pd.DataFrame, hoje: date, dias: int = DIAS_HISTORICO, seed: int = 42,
) -> pd.DataFrame:
    """Vendas diárias dos últimos `dias` dias (até ontem) para cada produto.

    `produtos` precisa das colunas `sku` e `nome_produto`.
    Retorna: data, sku, nome_produto, quantidade_vendida.
    """
    datas = [hoje - timedelta(days=d) for d in range(dias, 0, -1)]
    fatores = np.array([FATOR_DIA_SEMANA[d.weekday()] for d in datas])
    linhas = []
    for sku, nome in produtos[["sku", "nome_produto"]].drop_duplicates("sku").itertuples(index=False):
        rng = _gerador(str(sku), seed)
        ritmo = rng.uniform(0.3, 6.0)                 # unidades por dia, em média
        tendencia = np.linspace(1 - rng.uniform(-0.25, 0.25), 1, dias)   # leve alta ou queda
        qtds = rng.poisson(ritmo * fatores * tendencia)
        linhas.extend(
            {"data": d, "sku": sku, "nome_produto": nome, "quantidade_vendida": int(q)}
            for d, q in zip(datas, qtds)
        )
    return pd.DataFrame(linhas, columns=["data", "sku", "nome_produto", "quantidade_vendida"])
