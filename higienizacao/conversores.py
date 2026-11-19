"""Conversão de valores escritos de qualquer jeito (preço, quantidade, prazo, data)."""

import re
from datetime import date, datetime, timedelta

import pandas as pd

from .texto import normalizar, vazio

_NUMERO = re.compile(r"[-+]?\d[\d.,]*")
_EXTENSO = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20,
}
_EPOCA_EXCEL = datetime(1899, 12, 30)


def _interpretar_separadores(token: str) -> float:
    """'1.234,56', '1,234.56', '1234.56', '12,5' e '4.599' (milhar) viram número."""
    negativo = token.startswith("-")
    token = token.lstrip("+-")
    virgula, ponto = token.rfind(","), token.rfind(".")
    if virgula >= 0 and ponto >= 0:
        # O separador que aparece por último é o decimal
        if virgula > ponto:
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif virgula >= 0:
        partes = token.split(",")
        if len(partes) > 2:                      # 1,234,567 -> milhares
            token = token.replace(",", "")
        else:
            token = token.replace(",", ".")      # 12,5 -> decimal (padrão brasileiro)
    elif ponto >= 0:
        partes = token.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3 and partes[0] != "0"):
            token = token.replace(".", "")       # 4.599 ou 1.234.567 -> milhares
    valor = float(token)
    return -valor if negativo else valor


def para_numero(valor) -> float | None:
    """Converte preço/quantidade/prazo escrito de qualquer forma. None se não houver número."""
    if vazio(valor):
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if pd.isna(valor) else float(valor)
    texto = str(valor).replace(" ", " ")
    achado = _NUMERO.search(texto.replace(" ", ""))
    if achado:
        try:
            return _interpretar_separadores(achado.group())
        except ValueError:
            return None
    palavra = normalizar(texto).split(" ")[0] if normalizar(texto) else ""
    return float(_EXTENSO[palavra]) if palavra in _EXTENSO else None


def para_data(valor) -> date | None:
    """Datas como célula de data, '05/03/2026', '05.03.2026', '2026-03-05', '05/03/26' ou número serial do Excel."""
    if vazio(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if isinstance(valor, (int, float)):
        if 20000 <= valor <= 80000:              # serial do Excel (1954 a 2119)
            return (_EPOCA_EXCEL + timedelta(days=float(valor))).date()
        return None
    texto = str(valor).strip()
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", texto):
        formatos = ["%Y-%m-%d"]
        texto = texto[:10]
    else:
        texto = re.split(r"\s+", texto)[0]
        formatos = ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y"]
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None
