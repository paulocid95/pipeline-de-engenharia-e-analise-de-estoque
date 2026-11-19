"""Higienização de planilhas enviadas pelo usuário.

Fluxo: ler_arquivo (bytes -> tabelas brutas) -> preparar (descobre tipo e colunas)
-> higienizar (limpa, padroniza, liga as tabelas e gera o relatório).
"""

from .colunas import COTACOES, ESTOQUE, NOMES_TIPO, OCORRENCIAS, ROTULOS_COLUNA, TIPOS, VENDAS
from .leitura import LINHAS_MAXIMAS, TAMANHO_MAXIMO_MB, ErroArquivo, TabelaBruta, ler_arquivo
from .processador import Duvida, EntradaTabela, ItemRelatorio, Resultado, higienizar, preparar, remapear

__all__ = [
    "COTACOES", "ESTOQUE", "NOMES_TIPO", "OCORRENCIAS", "ROTULOS_COLUNA", "TIPOS", "VENDAS",
    "LINHAS_MAXIMAS", "TAMANHO_MAXIMO_MB", "ErroArquivo", "TabelaBruta", "ler_arquivo",
    "Duvida", "EntradaTabela", "ItemRelatorio", "Resultado", "higienizar", "preparar", "remapear",
]
