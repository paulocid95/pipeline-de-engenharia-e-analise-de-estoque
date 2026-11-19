"""Reconhecimento de abas e colunas: cabeçalho fora do lugar, nomes variados e tipo de cada tabela."""

from dataclasses import dataclass, field

import pandas as pd

from .texto import normalizar, vazio

ESTOQUE, COTACOES, OCORRENCIAS, VENDAS = "estoque", "cotacoes", "ocorrencias", "vendas"
TIPOS = [ESTOQUE, COTACOES, OCORRENCIAS, VENDAS]
NOMES_TIPO = {ESTOQUE: "Estoque", COTACOES: "Cotações", OCORRENCIAS: "Ocorrências", VENDAS: "Vendas"}

_SKU = ["sku", "codigo", "cod", "cod item", "codigo item", "codigo do item", "codigo produto", "codigo do produto",
        "cod produto", "id produto", "id do produto", "id", "ref", "referencia", "part number", "ean"]
_PRODUTO = ["produto", "nome produto", "nome do produto", "nm produto", "descricao do produto", "descricao produto",
            "item", "mercadoria", "artigo", "product", "peca", "nome item", "nome da peca", "modelo"]
_FORNECEDOR = ["fornecedor", "fornec", "forn", "nome fornecedor", "razao social", "supplier", "vendor", "distribuidor"]
_PRECO = ["preco", "preco unit", "preco unitario", "valor", "valor unit", "valor unitario", "vl unit", "vlr unit",
          "custo", "custo unitario", "price", "valor brl", "preco brl"]
_DATA = ["data", "dt", "date", "dia"]

# Para cada tipo de tabela: coluna canônica -> nomes aceitos (já normalizados)
ESQUEMAS: dict[str, dict[str, list[str]]] = {
    ESTOQUE: {
        "sku": _SKU,
        "produto": _PRODUTO + ["descricao", "nome"],
        "categoria": ["categoria", "depto", "departamento", "tipo produto", "tipo do produto", "grupo", "familia",
                      "segmento", "linha", "secao", "tipo"],
        "fornecedor": _FORNECEDOR,
        "preco": _PRECO,
        "quantidade": ["quantidade", "qtd", "qtde", "qtd disp", "qtde disp", "qtd disponivel", "quantidade disponivel",
                       "estoque", "estoque atual", "estoque disponivel", "saldo", "saldo estoque", "disponivel",
                       "unidades", "quantity", "stock", "qtd estoque"],
        "estoque_minimo": ["estoque minimo", "est minimo", "est min", "estoque min", "minimo", "ponto de reposicao",
                           "ponto reposicao", "qtd minima", "estoque seguranca", "estoque de seguranca"],
    },
    COTACOES: {
        "sku": _SKU,
        "produto": _PRODUTO,
        "fornecedor": _FORNECEDOR,
        "preco": _PRECO + ["valor cotado", "preco cotado", "cotacao", "valor da cotacao", "preco ofertado"],
        "prazo_dias": ["prazo", "prazo entrega", "prazo de entrega", "prazo dias", "lead time", "dias entrega",
                       "dias para entrega", "entrega", "tempo entrega", "tempo de entrega"],
        "lote_minimo": ["lote", "lote minimo", "lote min", "pedido minimo", "qtd minima", "quantidade minima", "moq"],
        "data": _DATA + ["data cotacao", "data da cotacao", "dt cotacao", "validade"],
    },
    OCORRENCIAS: {
        "fornecedor": _FORNECEDOR,
        "produto": _PRODUTO,
        "tipo": ["tipo", "ocorrencia", "tipo ocorrencia", "tipo de ocorrencia", "problema", "tipo problema",
                 "tipo de problema", "motivo", "categoria", "incidente"],
        "gravidade": ["gravidade", "severidade", "criticidade", "impacto", "prioridade", "nivel"],
        "data": _DATA + ["data ocorrencia", "data da ocorrencia", "dt ocorrencia", "data abertura", "abertura",
                         "data registro", "registrado em"],
        "status": ["status", "situacao", "andamento", "estado"],
        "data_resolucao": ["resolvido em", "data resolucao", "data da resolucao", "data de resolucao", "resolucao",
                           "data fechamento", "fechamento", "fechado em", "encerramento", "data encerramento",
                           "concluido em"],
        "descricao": ["descricao", "detalhe", "detalhes", "observacao", "observacoes", "obs", "comentario",
                      "historico"],
    },
    VENDAS: {
        "data": _DATA + ["data venda", "data da venda", "dt venda", "data pedido", "emissao", "data emissao"],
        "sku": _SKU,
        "produto": _PRODUTO + ["descricao"],
        "quantidade": ["qtd vendida", "quantidade vendida", "qtde vendida", "vendas", "vendido", "qtd", "qtde",
                       "quantidade", "unidades vendidas", "unidades", "saida", "saidas"],
    },
}

# Colunas obrigatórias (cada item é uma alternativa: basta uma das colunas do grupo)
OBRIGATORIAS: dict[str, list[tuple[str, ...]]] = {
    ESTOQUE: [("produto", "sku"), ("quantidade",), ("preco",)],
    COTACOES: [("produto", "sku"), ("fornecedor",), ("preco",)],
    OCORRENCIAS: [("fornecedor",), ("tipo",), ("data",)],
    VENDAS: [("data",), ("produto", "sku"), ("quantidade",)],
}

ROTULOS_COLUNA = {
    "sku": "Código / SKU", "produto": "Produto", "categoria": "Categoria", "fornecedor": "Fornecedor",
    "preco": "Preço", "quantidade": "Quantidade", "estoque_minimo": "Estoque mínimo", "prazo_dias": "Prazo de entrega",
    "lote_minimo": "Lote mínimo", "data": "Data", "tipo": "Tipo de ocorrência", "gravidade": "Gravidade",
    "status": "Situação", "data_resolucao": "Data de resolução", "descricao": "Descrição",
}

# Palavras no nome da aba/arquivo que denunciam o tipo
_PISTAS_NOME = {
    ESTOQUE: ["estoque", "inventario", "posicao", "stock", "saldo"],
    COTACOES: ["cotac", "orcament", "proposta", "preco forn", "quote"],
    OCORRENCIAS: ["ocorr", "incident", "problema", "reclama", "nao conform", "chamado"],
    VENDAS: ["venda", "saida", "faturamento", "sales"],
}


def _pontuar(cabecalho: str, nomes: list[str]) -> int:
    """Pontua o casamento: igual vale mais; conter o nome como palavras inteiras vale o tamanho do nome."""
    if not cabecalho:
        return 0
    melhor = 0
    alvo = f" {cabecalho} "
    for nome in nomes:
        if cabecalho == nome:
            melhor = max(melhor, 1000 + len(nome))
        elif f" {nome} " in alvo:
            melhor = max(melhor, len(nome))
    return melhor


def mapear_colunas(cabecalhos: list, tipo: str) -> dict[str, int]:
    """Coluna canônica -> índice da coluna na tabela. Cada coluna é usada uma única vez."""
    normalizados = [normalizar(c) for c in cabecalhos]
    candidatos = []
    for canonica, nomes in ESQUEMAS[tipo].items():
        for i, cab in enumerate(normalizados):
            pontos = _pontuar(cab, nomes)
            if pontos:
                candidatos.append((pontos, canonica, i))
    mapa: dict[str, int] = {}
    usadas: set[int] = set()
    for pontos, canonica, i in sorted(candidatos, key=lambda c: -c[0]):
        if canonica not in mapa and i not in usadas:
            mapa[canonica] = i
            usadas.add(i)
    return mapa


def faltando(mapa: dict, tipo: str) -> list[tuple[str, ...]]:
    """Grupos de colunas obrigatórias que não foram encontrados."""
    return [grupo for grupo in OBRIGATORIAS[tipo] if not any(c in mapa for c in grupo)]


def encontrar_cabecalho(bruta: pd.DataFrame, tipo: str | None = None, max_linhas: int = 15) -> tuple[int, int]:
    """Linha do cabeçalho (procura nas primeiras linhas) e quantas colunas ela reconhece."""
    tipos = [tipo] if tipo else TIPOS
    melhor_linha, melhor_qtd = 0, 0
    for linha in range(min(max_linhas, len(bruta))):
        valores = list(bruta.iloc[linha])
        if sum(not vazio(v) for v in valores) < 2:
            continue
        qtd = max(len(mapear_colunas(valores, t)) for t in tipos)
        if qtd > melhor_qtd:
            melhor_linha, melhor_qtd = linha, qtd
    return melhor_linha, melhor_qtd


@dataclass
class Deteccao:
    tipo: str | None
    linha_cabecalho: int
    cabecalhos: list
    mapa: dict = field(default_factory=dict)
    confianca: float = 0.0


# Abas de apoio que nunca são dados (ex.: o relatório da planilha limpa que o próprio app gera)
_NOMES_IGNORADOS = ["relatorio da limpeza", "leia me", "readme"]


def detectar_tipo(bruta: pd.DataFrame, nome: str = "") -> Deteccao:
    """Descobre se a tabela é Estoque, Cotações, Ocorrências ou Vendas (pelo nome e pelas colunas)."""
    linha, _ = encontrar_cabecalho(bruta)
    cabecalhos = list(bruta.iloc[linha]) if len(bruta) else []
    nome_norm = normalizar(nome)
    if any(n in nome_norm for n in _NOMES_IGNORADOS):
        return Deteccao(None, linha, cabecalhos)
    melhor = Deteccao(None, linha, cabecalhos)
    melhor_pontos = 0.0
    for tipo in TIPOS:
        mapa = mapear_colunas(cabecalhos, tipo)
        obrig = OBRIGATORIAS[tipo]
        atendidas = len(obrig) - len(faltando(mapa, tipo))
        pontos = atendidas * 2 + len(mapa) * 0.5
        if any(p in nome_norm for p in _PISTAS_NOME[tipo]):
            pontos += 4
        # Colunas que só existem num tipo de tabela ajudam a desempatar
        if tipo == VENDAS and "quantidade" in mapa and normalizar(cabecalhos[mapa["quantidade"]]).find("vend") >= 0:
            pontos += 3
        if tipo == OCORRENCIAS and "tipo" in mapa and "preco" not in mapear_colunas(cabecalhos, ESTOQUE):
            pontos += 1
        if tipo == COTACOES and ({"prazo_dias", "lote_minimo"} & mapa.keys()):
            pontos += 2
        if tipo == ESTOQUE and "quantidade" in mapa and "preco" in mapa and "fornecedor" not in mapa:
            pontos += 1
        if atendidas == len(obrig) and pontos > melhor_pontos:
            melhor_pontos = pontos
            melhor = Deteccao(tipo, linha, cabecalhos, mapa, pontos)
    if melhor.tipo is None:
        # Nenhum tipo completo: devolve o mais provável para o usuário corrigir (ou None se nada casa)
        for tipo in TIPOS:
            mapa = mapear_colunas(cabecalhos, tipo)
            pontos = len(mapa) + (4 if any(p in nome_norm for p in _PISTAS_NOME[tipo]) else 0)
            if len(mapa) >= 2 and pontos > melhor_pontos:
                melhor_pontos = pontos
                melhor = Deteccao(tipo, linha, cabecalhos, mapa, pontos)
    return melhor
