from datetime import date, datetime

import pandas as pd

from datas_relativas import data_referencia, deslocar_datas, dias_desde
from regras_fornecedores import calcular_penalidades


def test_data_referencia_usa_a_carga_mais_recente():
    serie = pd.Series(pd.to_datetime(["2026-01-10 08:00", "2026-03-05 22:00", None], utc=True))
    assert data_referencia(serie) == date(2026, 3, 5)


def test_data_referencia_vazia_retorna_none():
    assert data_referencia(pd.Series([], dtype="datetime64[ns]")) is None


def test_dias_desde_nunca_e_negativo():
    assert dias_desde(date(2026, 3, 5), date(2026, 3, 15)) == 10
    assert dias_desde(date(2026, 3, 5), date(2026, 3, 1)) == 0
    assert dias_desde(None, date(2026, 3, 1)) == 0


def test_deslocar_datas_preserva_datas_puras_e_vazios():
    df = pd.DataFrame({
        "data_ocorrencia": [date(2026, 1, 1), date(2026, 2, 1)],
        "data_resolucao": [date(2026, 1, 20), None],
    })
    resultado = deslocar_datas(df, ["data_ocorrencia", "data_resolucao"], 30)
    assert list(resultado["data_ocorrencia"]) == [date(2026, 1, 31), date(2026, 3, 3)]
    assert resultado["data_resolucao"].iloc[0] == date(2026, 2, 19)
    assert resultado["data_resolucao"].iloc[1] is None
    # Original intacto
    assert df["data_ocorrencia"].iloc[0] == date(2026, 1, 1)


def test_deslocar_datas_com_data_e_hora():
    df = pd.DataFrame({"data_cotacao": pd.to_datetime(["2026-01-01 10:30"], utc=True)})
    resultado = deslocar_datas(df, ["data_cotacao", "coluna_inexistente"], 2)
    assert resultado["data_cotacao"].iloc[0] == pd.Timestamp("2026-01-03 10:30", tz="UTC")


def test_deslocar_zero_dias_nao_altera():
    df = pd.DataFrame({"data_ocorrencia": [date(2026, 1, 1)]})
    assert deslocar_datas(df, ["data_ocorrencia"], 0) is df


def test_ranking_nao_envelhece_apos_deslocamento():
    """Um ano depois, a ocorrência em aberto continua com a mesma idade."""
    carga = date(2026, 1, 1)
    df = pd.DataFrame({
        "fornecedor": ["Fornecedor D"], "tipo": ["JUDICIAL"], "gravidade": ["ALTA"],
        "data_ocorrencia": [date(2025, 11, 18)], "status": ["ABERTO"], "data_resolucao": [None],
    })
    hoje = datetime(2027, 1, 1).date()
    deslocado = deslocar_datas(df, ["data_ocorrencia", "data_resolucao"], dias_desde(carga, hoje))

    original = calcular_penalidades(df, carga)
    agora = calcular_penalidades(deslocado, hoje)
    assert agora["dias_em_aberto"].iloc[0] == original["dias_em_aberto"].iloc[0] == 44
    assert agora["penalidade"].iloc[0] == original["penalidade"].iloc[0]
