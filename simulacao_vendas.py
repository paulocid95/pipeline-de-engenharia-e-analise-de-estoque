"""Histórico simulado de vendas diárias por produto (dados de demonstração).

Determinístico: o mesmo SKU sempre tem o mesmo comportamento, e as datas são
relativas a `hoje`, então o histórico nunca envelhece. Usado na planilha de
exemplo e na previsão de demanda da demonstração.

Para parecer uma loja de verdade:
- a loja fecha aos domingos (não há vendas nesse dia);
- cada produto tem um perfil: venda regular, em alta, em queda ou esporádica
  (produtos caros costumam vender poucas unidades, em dias soltos);
- como num relatório de sistema, só aparecem os dias em que o produto vendeu.
"""

import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

DIAS_HISTORICO = 90
DIAS_FECHADOS = {6}                     # domingo (weekday 6)

# Segunda a sábado: sexta e sábado vendem mais
FATOR_DIA_SEMANA = [0.9, 0.85, 0.9, 1.0, 1.2, 1.4, 0.0]

PERFIS = ("regular", "alta", "queda", "esporadico")
PRECO_ESPORADICO = 3000.0               # acima disso o produto tende a vender em dias soltos


def _gerador(sku: str, seed: int) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(f"{seed}-{sku}".encode("utf-8")))


def perfil_do_produto(sku: str, preco: float | None, seed: int = 42) -> str:
    """Perfil de vendas determinístico de cada SKU."""
    sorteio = _gerador(f"perfil-{sku}", seed).random()
    if preco is not None and preco >= PRECO_ESPORADICO and sorteio < 0.6:
        return "esporadico"
    if sorteio < 0.15:
        return "esporadico"
    if sorteio < 0.4:
        return "alta"
    if sorteio < 0.6:
        return "queda"
    return "regular"


def _quantidades(perfil: str, fatores: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    dias = len(fatores)
    if perfil == "esporadico":
        # Vende em ~10 a 30% dos dias abertos, de 1 a 2 unidades
        chance = rng.uniform(0.10, 0.30)
        vende = rng.random(dias) < chance * (fatores > 0)
        return np.where(vende, rng.integers(1, 3, dias), 0)
    ritmo = rng.uniform(0.5, 3.0)                                         # unidades por dia aberto
    inicio, fim = {"regular": (rng.uniform(0.9, 1.1), 1.0),
                   "alta": (rng.uniform(0.45, 0.65), 1.0),
                   "queda": (1.0, rng.uniform(0.45, 0.65))}[perfil]
    tendencia = np.linspace(inicio, fim, dias)
    return rng.poisson(ritmo * fatores * tendencia)


def simular_vendas(
    produtos: pd.DataFrame, hoje: date, dias: int = DIAS_HISTORICO, seed: int = 42,
) -> pd.DataFrame:
    """Vendas diárias dos últimos `dias` dias (até ontem) para cada produto.

    `produtos` precisa das colunas `sku` e `nome_produto` (e, se tiver, `preco_unitario`).
    Retorna só os dias com venda: data, sku, nome_produto, quantidade_vendida.
    """
    datas = [hoje - timedelta(days=d) for d in range(dias, 0, -1)]
    fatores = np.array([FATOR_DIA_SEMANA[d.weekday()] for d in datas])
    colunas = ["sku", "nome_produto"] + (["preco_unitario"] if "preco_unitario" in produtos.columns else [])
    linhas = []
    for registro in produtos[colunas].drop_duplicates("sku").to_dict("records"):
        sku = str(registro["sku"])
        preco = registro.get("preco_unitario")
        perfil = perfil_do_produto(sku, float(preco) if preco is not None and pd.notna(preco) else None, seed)
        qtds = _quantidades(perfil, fatores, _gerador(sku, seed))
        linhas.extend(
            {"data": d, "sku": registro["sku"], "nome_produto": registro["nome_produto"], "quantidade_vendida": int(q)}
            for d, q in zip(datas, qtds) if q > 0
        )
    return pd.DataFrame(linhas, columns=["data", "sku", "nome_produto", "quantidade_vendida"])
