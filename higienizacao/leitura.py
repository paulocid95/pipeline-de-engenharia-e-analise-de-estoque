"""Leitura de arquivos enviados (Excel com abas ou CSV) em tabelas brutas, sem interpretar nada ainda."""

import csv
import io
from dataclasses import dataclass

import pandas as pd

TAMANHO_MAXIMO_MB = 5
LINHAS_MAXIMAS = 10_000


class ErroArquivo(ValueError):
    """Problema no arquivo que impede a leitura (mensagem pronta para mostrar ao usuário)."""


@dataclass
class TabelaBruta:
    origem: str            # "arquivo.xlsx › Aba" ou "arquivo.csv"
    nome: str              # nome da aba ou do arquivo (usado como pista do tipo)
    dados: pd.DataFrame    # sem cabeçalho definido (header=None), valores como vieram


def _limpar_bordas(df: pd.DataFrame) -> pd.DataFrame:
    """Tira linhas e colunas totalmente vazias."""
    df = df.astype(object).where(df.notna(), None)
    df = df.map(lambda v: None if isinstance(v, str) and not v.strip() else v)
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    df.columns = range(df.shape[1])
    return df


def _ler_csv(conteudo: bytes) -> pd.DataFrame:
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    # Separador: o que aparece com mais frequência nas primeiras linhas (fora de aspas)
    amostra = texto.splitlines()[:30]
    contagem = {s: sum(len(next(csv.reader([l], delimiter=s), [])) - 1 for l in amostra) for s in ";,\t|"}
    separador = max(contagem, key=contagem.get)
    # csv.reader aceita linhas com quantidades diferentes de colunas (títulos, totais...)
    linhas = [l for l in csv.reader(io.StringIO(texto), delimiter=separador) if any(c.strip() for c in l)]
    largura = max((len(l) for l in linhas), default=0)
    return pd.DataFrame([l + [""] * (largura - len(l)) for l in linhas], dtype=object)


def ler_arquivo(nome: str, conteudo: bytes) -> list[TabelaBruta]:
    """Transforma um arquivo enviado em uma lista de tabelas (uma por aba ou uma por CSV)."""
    if len(conteudo) > TAMANHO_MAXIMO_MB * 1024 * 1024:
        raise ErroArquivo(f"“{nome}” tem mais de {TAMANHO_MAXIMO_MB} MB. Divida o arquivo ou envie só as colunas necessárias.")
    extensao = nome.lower().rsplit(".", 1)[-1]
    try:
        if extensao in ("xlsx", "xlsm", "xls"):
            abas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None, dtype=object)
            tabelas = [TabelaBruta(f"{nome} › {aba}", aba, df) for aba, df in abas.items()]
        elif extensao in ("csv", "txt"):
            tabelas = [TabelaBruta(nome, nome.rsplit(".", 1)[0], _ler_csv(conteudo))]
        else:
            raise ErroArquivo(f"“{nome}” não é Excel (.xlsx) nem CSV.")
    except ErroArquivo:
        raise
    except Exception as erro:  # arquivo corrompido, senha, formato inesperado...
        raise ErroArquivo(f"Não foi possível abrir “{nome}”. Confira se o arquivo não está corrompido ou protegido por senha.") from erro

    resultado = []
    for t in tabelas:
        dados = _limpar_bordas(t.dados)
        if dados.empty:
            continue
        if len(dados) > LINHAS_MAXIMAS + 20:     # folga para título e linha de total
            raise ErroArquivo(f"“{t.origem}” tem {len(dados):,} linhas; o limite é {LINHAS_MAXIMAS:,}.".replace(",", "."))
        resultado.append(TabelaBruta(t.origem, t.nome, dados))
    return resultado
