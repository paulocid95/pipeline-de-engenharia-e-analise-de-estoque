"""Unificação de nomes (fornecedores, produtos, categorias) e tradução de ocorrências para os códigos do sistema."""

import re
from difflib import SequenceMatcher

from limpeza_padronizacao import deduzir_categoria
from regras_fornecedores import ROTULOS_GRAVIDADE, ROTULOS_STATUS, ROTULOS_TIPO

from .texto import limpar_texto, melhor_variante, normalizar

# ------------------------------------------------------------------------------
# Fornecedores
# ------------------------------------------------------------------------------
_SUFIXOS_EMPRESA = {"ltda", "me", "mei", "eireli", "epp", "sa", "s a", "inc", "llc", "ltd"}
_SUFIXO_FINAL = re.compile(r"[\s,.\-]+(ltda|me|mei|eireli|epp|s\.?\s?a|inc|llc|ltd)\.?$", re.IGNORECASE)
_ABREVIACOES = {"forn": "fornecedor", "fornec": "fornecedor", "fornecedora": "fornecedor",
                "distrib": "distribuidora", "dist": "distribuidora", "com": "comercio", "ind": "industria"}
_PALAVRAS_GENERICAS = {"fornecedor", "distribuidora", "comercio", "industria", "de", "da", "do", "e", "the"}


def chave_fornecedor(nome) -> str:
    """'FORNECEDOR A LTDA', 'forn. a' e 'Fornecedor_A' viram a mesma chave: 'fornecedor a'."""
    palavras = [_ABREVIACOES.get(p, p) for p in normalizar(nome).split()]
    texto = " ".join(palavras)
    for sufixo in sorted(_SUFIXOS_EMPRESA, key=len, reverse=True):
        if texto.endswith(" " + sufixo):
            texto = texto[: -len(sufixo) - 1]
    return texto.strip()


def nome_de_exibicao(chave: str, variantes) -> str:
    """Nome bonito do fornecedor: a melhor grafia original, sem sufixos como LTDA."""
    candidatas = [_SUFIXO_FINAL.sub("", limpar_texto(v)) for v in variantes if chave_fornecedor(v) == chave]
    melhor = melhor_variante(candidatas)
    bem_escrito = melhor and melhor != melhor.upper() and melhor != melhor.lower() and "_" not in melhor
    if bem_escrito and normalizar(melhor) == chave:
        return melhor
    return " ".join(p.upper() if len(p) == 1 else p.capitalize() for p in chave.split())


def parecidos(a: str, b: str, limite: float = 0.8) -> float | None:
    """Similaridade entre duas chaves, ignorando palavras genéricas ('fornecedor', 'distribuidora'...).

    Retorna a similaridade se forem suspeitos de ser o mesmo, senão None.
    """
    sa = " ".join(p for p in a.split() if p not in _PALAVRAS_GENERICAS)
    sb = " ".join(p for p in b.split() if p not in _PALAVRAS_GENERICAS)
    if not sa or not sb or sa == sb or min(len(sa), len(sb)) < 3:
        return None
    razao = SequenceMatcher(None, sa, sb).ratio()
    return razao if razao >= limite else None


def contido(a: str, b: str) -> bool:
    """Um nome é o outro com palavras a mais: 'mundo pet' e 'mundo pet atacado', 'nutrivale' e
    'nutrivale distribuidora'. Palavras genéricas não contam e o nome menor precisa ter ao menos 4 letras."""
    pa = {p for p in a.split() if p not in _PALAVRAS_GENERICAS}
    pb = {p for p in b.split() if p not in _PALAVRAS_GENERICAS}
    if a == b or not pa or not pb:
        return False
    menor, maior = sorted((pa, pb), key=len)
    return menor <= maior and len("".join(menor)) >= 4


# ------------------------------------------------------------------------------
# Categorias
# ------------------------------------------------------------------------------
CATEGORIA_OUTROS = "Outros"


def loja_de_eletronicos(produtos) -> bool:
    """A tradução de categorias de eletrônicos ('celular' → Smartphones) só vale quando a maioria dos
    produtos é de eletrônicos; num pet shop, 'ACESSORIOS' não pode virar 'Carregadores'."""
    nomes = [p for p in produtos if limpar_texto(p)]
    return bool(nomes) and sum(deduzir_categoria(p, "") != CATEGORIA_OUTROS for p in nomes) * 2 >= len(nomes)


def nome_de_categoria(variantes) -> str:
    """Melhor grafia de uma categoria da planilha: 'RACOES' → 'Racoes', 'vestuário' → 'Vestuário'."""
    melhor = melhor_variante(variantes)
    if melhor == melhor.upper():
        melhor = melhor.capitalize()
    return melhor[:1].upper() + melhor[1:]


def deduzir_pela_planilha(produto, categoria_por_palavra: dict) -> str:
    """Categoria de um produto sem categoria, pelos produtos da planilha que começam com a mesma palavra."""
    palavras = normalizar(produto).split()
    return categoria_por_palavra.get(palavras[0], CATEGORIA_OUTROS) if palavras else CATEGORIA_OUTROS


def categoria_padrao(categoria, produto) -> tuple[str, bool]:
    """Categoria final e se ela foi deduzida (vazia na planilha), para lojas de eletrônicos."""
    cat = limpar_texto(categoria)
    if not cat:
        return deduzir_categoria(produto, ""), True
    oficial = deduzir_categoria("", cat)          # sinônimos do nosso ramo ('celular', 'Audio'...)
    if oficial != "Outros":
        return oficial, False
    return cat[0].upper() + cat[1:], False        # categoria própria do usuário (ex.: 'Vestuário')


# ------------------------------------------------------------------------------
# Ocorrências
# ------------------------------------------------------------------------------
TIPO_OUTROS = "OUTROS"

# Ordem importa: as expressões mais específicas vêm antes
_PALAVRAS_TIPO = [
    ("JUDICIAL", ["judicial", "processo", "acao judicial", "juridic", "tribunal", "litigio", "advogad", "procon"]),
    ("DIVERGENCIA_PRECO_NF", ["nota fiscal", "nf", "nfe", "divergencia de preco", "preco divergente",
                              "preco errado", "cobranca", "fatura", "boleto"]),
    ("AVARIA_TRANSPORTE", ["avaria", "transporte", "amassad", "embalagem danificada", "caixa danificada",
                           "danificado na entrega", "frete"]),
    ("ITEM_ERRADO_FALTANDO", ["errad", "faltand", "faltou", "falta", "incomplet", "trocad", "diferente do pedido"]),
    ("DEFEITO", ["defeit", "quebrad", "nao funciona", "estragad", "danificad", "queimad", "com problema"]),
    ("ATRASO", ["atras", "demora", "fora do prazo", "entrega tardia", "nao entregue", "prazo"]),
    ("FALHA_ATENDIMENTO", ["atendimento", "sem retorno", "suporte", "nao responde", "comunicacao", "sac"]),
]
_PALAVRAS_GRAVIDADE = [
    ("CRITICA", ["critic", "gravissim", "urgent", "critical", "muito alta", "altissim"]),
    ("BAIXA", ["baix", "leve", "low", "pequen", "minim"]),
    ("MEDIA", ["medi", "moderad", "medium", "normal", "regular"]),
    ("ALTA", ["alta", "alto", "grave", "high", "serio", "importante"]),
]
_PALAVRAS_STATUS = [
    ("RESOLVIDO", ["resolvid", "concluid", "fechad", "finalizad", "solucionad", "encerrad", "ok", "resolvido"]),
    ("EM_ANDAMENTO", ["andamento", "analise", "tratativa", "tratamento", "aguardando", "em curso", "progresso"]),
    ("ABERTO", ["abert", "novo", "pendente", "nao resolvid", "sem solucao", "open"]),
]


def _contem(texto: str, termos: list[str]) -> bool:
    alvo = f" {texto} "
    return any(f" {t}" in alvo for t in termos)


def _por_rotulo(texto: str, rotulos: dict) -> str | None:
    for codigo, rotulo in rotulos.items():
        if texto in (normalizar(codigo), normalizar(rotulo)):
            return codigo
    return None


def tipo_ocorrencia(valor) -> str:
    """Traduz o tipo escrito pelo usuário para um dos códigos do sistema (ou OUTROS)."""
    texto = normalizar(valor)
    if not texto:
        return TIPO_OUTROS
    exato = _por_rotulo(texto, ROTULOS_TIPO)
    if exato:
        return exato
    for codigo, termos in _PALAVRAS_TIPO:
        if _contem(texto, termos):
            return codigo
    return TIPO_OUTROS


def gravidade(valor) -> str | None:
    texto = normalizar(valor)
    if not texto:
        return None
    exato = _por_rotulo(texto, ROTULOS_GRAVIDADE)
    if exato:
        return exato
    if texto.isdigit():                            # escalas numéricas 1-4
        return {1: "BAIXA", 2: "MEDIA", 3: "ALTA"}.get(int(texto), "CRITICA")
    # "não resolvido"/"muito alta" precisam ser vistos antes das palavras simples
    for codigo, termos in _PALAVRAS_GRAVIDADE:
        if _contem(texto, termos):
            return codigo
    return None


def status_ocorrencia(valor) -> str | None:
    texto = normalizar(valor)
    if not texto:
        return None
    exato = _por_rotulo(texto, ROTULOS_STATUS)
    if exato:
        return exato
    if _contem(texto, ["nao resolvid", "sem solucao", "nao solucionad"]):
        return "ABERTO"
    for codigo, termos in _PALAVRAS_STATUS:
        if _contem(texto, termos):
            return codigo
    return None
