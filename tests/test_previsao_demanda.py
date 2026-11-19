from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from previsao_demanda import (
    SEM_VENDAS,
    Parametros,
    detectar_calendario,
    dias_ate_acabar,
    fornecedor_para_compra,
    prever_estoque,
    quantidade_sugerida,
    texto_para_ia,
)
from simulacao_vendas import simular_vendas

HOJE = date(2026, 11, 18)


def _vendas(sku: str, por_dia, dias: int = 90, fechados=(6,), seed: int = 1) -> pd.DataFrame:
    """Vendas Poisson com taxa `por_dia` (número ou função do dia da semana)."""
    rng = np.random.default_rng(seed)
    linhas = []
    for d in range(dias, 0, -1):
        data = HOJE - timedelta(days=d)
        if data.weekday() in fechados:
            continue
        taxa = por_dia(data.weekday()) if callable(por_dia) else por_dia
        q = int(rng.poisson(taxa))
        if q:
            linhas.append({"data": data, "sku": sku, "nome_produto": sku, "quantidade_vendida": q})
    return pd.DataFrame(linhas)


def _estoque(*itens) -> pd.DataFrame:
    return pd.DataFrame([{"sku": s, "nome_produto": s, "quantidade_disponivel": q, "preco_unitario": 10.0}
                         for s, q in itens])


def test_calendario_detecta_domingo_fechado_e_loja_online_aberta_todo_dia():
    fisica = _vendas("A", 8)
    assert detectar_calendario(fisica, HOJE, 90).fechados == {6}
    online = _vendas("A", 8, fechados=())
    assert detectar_calendario(online, HOJE, 90).fechados == set()


def test_feriado_sem_vendas_e_ignorado():
    v = _vendas("A", 20)
    feriado = HOJE - timedelta(days=30)
    if feriado.weekday() == 6:
        feriado -= timedelta(days=1)
    v = v[v["data"] != feriado]
    cal = detectar_calendario(v, HOJE, 90)
    assert feriado in cal.feriados and feriado not in cal.abertos


def test_previsao_regular_acompanha_o_ritmo_e_zera_dias_fechados():
    r = prever_estoque(_estoque(("A", 100)), _vendas("A", 10), HOJE, Parametros(horizonte=28))
    linha = r.tabela.iloc[0]
    # 10 por dia aberto, 6 dias abertos por semana -> ~8,6 por dia corrido
    assert linha["media_diaria"] == pytest.approx(10 * 6 / 7, rel=0.2)
    serie = r.series["A"]
    domingos = [p for d, p in zip(serie["datas"], serie["previsto"]) if d.weekday() == 6]
    assert all(p == 0 for p in domingos)
    assert linha["modelo"] in {"Holt-Winters", "Média móvel semanal", "Croston (SBA)", "Ingênuo sazonal"}


def test_padrao_semanal_e_aprendido():
    # Sábado vende o triplo
    r = prever_estoque(_estoque(("A", 500)), _vendas("A", lambda d: 15 if d == 5 else 5), HOJE)
    serie = r.series["A"]
    sabados = [p for d, p in zip(serie["datas"][:28], serie["previsto"][:28]) if d.weekday() == 5]
    tercas = [p for d, p in zip(serie["datas"][:28], serie["previsto"][:28]) if d.weekday() == 1]
    assert np.mean(sabados) > 2 * np.mean(tercas)


def test_demanda_intermitente_nao_explode():
    v = _vendas("CARO", 0.3)
    r = prever_estoque(_estoque(("CARO", 5)), v, HOJE)
    linha = r.tabela.iloc[0]
    assert linha["media_diaria"] == pytest.approx(0.3 * 6 / 7, abs=0.2)


def test_produto_sem_vendas_nao_gera_compra():
    r = prever_estoque(_estoque(("A", 10), ("PARADO", 3)), _vendas("A", 5), HOJE)
    parado = r.tabela.set_index("sku").loc["PARADO"]
    assert parado["modelo"] == SEM_VENDAS and parado["quantidade_sugerida"] == 0
    assert parado["dias_ate_acabar"] is None or pd.isna(parado["dias_ate_acabar"])


def test_ruptura_prevista_antes_da_reposicao_e_compra_pelo_lote():
    cot = pd.DataFrame([
        {"sku": "A", "fornecedor_cotacao": "Perigoso SA", "prazo_dias": 2, "lote_minimo": 1, "preco_cotado": 5.0,
         "classe": "PERIGOSO", "nota_cotacao": 90},
        {"sku": "A", "fornecedor_cotacao": "Bom Ltda", "prazo_dias": 10, "lote_minimo": 25, "preco_cotado": 8.0,
         "classe": "BOM", "nota_cotacao": 80},
    ])
    p = Parametros(horizonte=14, seguranca=3)
    r = prever_estoque(_estoque(("A", 20)), _vendas("A", 10), HOJE, p, cot)
    linha = r.tabela.iloc[0]
    assert linha["fornecedor"] == "Bom Ltda" and linha["prazo"] == 10      # nunca o 🔴
    assert linha["vai_faltar"]                                             # 20 un duram ~2-3 dias, prazo 10
    assert linha["quantidade_sugerida"] % 25 == 0 and linha["quantidade_sugerida"] > 0
    assert linha["custo_pedido"] == pytest.approx(linha["quantidade_sugerida"] * 8.0)


def test_prazo_manual_substitui_o_do_fornecedor():
    r = prever_estoque(_estoque(("A", 20)), _vendas("A", 10), HOJE, Parametros(prazo_manual=1))
    assert r.tabela.iloc[0]["prazo"] == 1


def test_auxiliares():
    assert dias_ate_acabar(0, np.array([1.0, 1.0])) == 0
    assert dias_ate_acabar(3, np.array([1.0, 1.0, 1.0, 1.0])) == 2
    assert dias_ate_acabar(100, np.array([1.0, 1.0])) is None
    assert quantidade_sugerida(0, 10) == 0
    assert quantidade_sugerida(11, 10) == 20
    assert quantidade_sugerida(3.2, 1) == 4
    assert fornecedor_para_compra(None) is None


def test_demo_completa_roda_e_gera_texto_para_ia():
    produtos = pd.DataFrame({
        "sku": [f"P{i:02d}" for i in range(25)], "nome_produto": [f"Produto {i}" for i in range(25)],
        "preco_unitario": [5000.0 if i % 3 == 0 else 80.0 for i in range(25)],
        "quantidade_disponivel": [i % 7 * 5 for i in range(25)],
    })
    produtos.loc[24, "quantidade_disponivel"] = 100_000           # não acaba nos próximos 6 meses
    vendas = simular_vendas(produtos, HOJE)
    r = prever_estoque(produtos, vendas, HOJE)
    assert len(r.tabela) == 25 and r.calendario.fechados == {6}
    assert r.tabela["confianca"].isin(["Alta", "Média", "Baixa"]).all()
    texto = texto_para_ia(r, Parametros(), limite=10)
    assert "PREVISÃO DE DEMANDA" in texto and "Mais 15 produtos" in texto


def test_previsao_com_a_planilha_enviada_pelo_usuario():
    from higienizacao import higienizar, ler_arquivo, preparar
    from planilha_exemplo import montar_planilha_exemplo
    from regras_fornecedores import avaliar_cotacoes, ranking_fornecedores
    from tests.test_planilha_exemplo import COTACOES, ESTOQUE, OCORRENCIAS

    arquivo = montar_planilha_exemplo(ESTOQUE, COTACOES, OCORRENCIAS, HOJE, seed=42)
    r = higienizar(preparar(ler_arquivo("exemplo.xlsx", arquivo)), hoje=HOJE)
    ranking = ranking_fornecedores(r.cotacoes, r.ocorrencias, HOJE, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")
    avaliadas = avaliar_cotacoes(r.cotacoes, ranking, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")
    prev = prever_estoque(r.estoque, r.vendas, HOJE, cotacoes_avaliadas=avaliadas)
    assert set(prev.tabela["sku"]) == set(r.estoque["sku"])
    assert prev.calendario.fechados == {6}                 # os dias ausentes foram entendidos como loja fechada
    perigosos = set(ranking.loc[ranking["classe"] == "PERIGOSO", "fornecedor"])
    assert not prev.tabela["fornecedor"].isin(perigosos).any()          # nunca sugere compra de 🔴
