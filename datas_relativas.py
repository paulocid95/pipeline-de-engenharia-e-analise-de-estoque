"""Datas relativas para os dados de demonstração.

O pipeline grava as datas do dia em que rodou. Para a demonstração não
"envelhecer", o painel desloca todas as datas pela distância entre a última
carga e hoje: uma ocorrência de 44 dias antes da carga continua aparecendo
como "44 dias atrás", não importa quando o app for aberto.

Usado apenas nos dados de demonstração (banco), nunca em planilhas do usuário.
"""

from datetime import date, datetime

import pandas as pd


def data_referencia(serie_datas: pd.Series) -> date | None:
    """Dia da carga mais recente (base para o deslocamento)."""
    validas = pd.to_datetime(serie_datas, errors="coerce").dropna()
    if validas.empty:
        return None
    return pd.Timestamp(validas.max()).date()


def dias_desde(referencia: date | None, hoje: date) -> int:
    """Quantos dias se passaram desde a carga (nunca negativo)."""
    if referencia is None:
        return 0
    return max(0, (hoje - referencia).days)


def _somente_datas(serie: pd.Series) -> bool:
    """True se a coluna guarda datas puras (date), e não data e hora."""
    valores = serie.dropna()
    return not valores.empty and valores.map(
        lambda v: isinstance(v, date) and not isinstance(v, datetime)
    ).all()


def deslocar_datas(df: pd.DataFrame, colunas: list[str], dias: int) -> pd.DataFrame:
    """Avança as colunas de data em `dias`, mantendo o tipo original de cada coluna."""
    if dias == 0 or df.empty:
        return df
    df = df.copy()
    delta = pd.Timedelta(days=dias)
    for coluna in colunas:
        if coluna not in df.columns:
            continue
        so_data = _somente_datas(df[coluna])
        deslocada = pd.to_datetime(df[coluna], errors="coerce") + delta
        if so_data:
            df[coluna] = [None if pd.isna(v) else v.date() for v in deslocada]
        else:
            df[coluna] = deslocada
    return df
