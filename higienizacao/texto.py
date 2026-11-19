"""Utilidades de texto usadas em toda a higienização."""

import re
import unicodedata

import pandas as pd


def vazio(valor) -> bool:
    """True para None, NaN e textos em branco."""
    if valor is None:
        return True
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(valor, str) and not valor.strip()


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar(valor) -> str:
    """Chave de comparação: minúsculas, sem acentos e só letras/números separados por um espaço."""
    if vazio(valor):
        return ""
    texto = sem_acentos(str(valor)).lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def limpar_texto(valor) -> str:
    """Remove espaços sobrando (início, fim e duplicados) mantendo maiúsculas e acentos."""
    if vazio(valor):
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def _nota_variante(texto: str) -> tuple:
    """Quanto maior, mais 'bem escrito' parece o texto (para escolher o nome de exibição)."""
    misto = texto != texto.upper() and texto != texto.lower()
    sujo = "_" in texto or texto != texto.strip() or "  " in texto
    return (misto, not sujo)


def melhor_variante(variantes) -> str:
    """Entre várias grafias do mesmo nome, escolhe a mais comum entre as bem escritas."""
    contagem: dict[str, int] = {}
    for v in variantes:
        t = limpar_texto(v)
        if t:
            contagem[t] = contagem.get(t, 0) + 1
    if not contagem:
        return ""
    return max(contagem, key=lambda t: (_nota_variante(t), contagem[t]))
