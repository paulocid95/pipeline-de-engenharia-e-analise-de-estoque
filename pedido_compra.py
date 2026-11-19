"""Pedido de compra em Excel a partir da sugestão da previsão de demanda.

Uma aba de resumo e uma aba por fornecedor, pronta para enviar. O subtotal e os
totais são fórmulas, então quem abrir o arquivo pode mudar uma quantidade e os
valores se atualizam.
"""

import re
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from previsao_demanda import Parametros

SEM_FORNECEDOR = "Fornecedor a definir"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUNAS_ITENS = ["incluir", "sku", "produto", "fornecedor", "quantidade", "lote", "preco", "prazo", "motivo"]

_COR_CABECALHO = "2F62C9"
_COR_TOTAL = "E8EEFB"
_MOEDA = 'R$ #,##0.00'
_DATA = "DD/MM/YYYY"
_PROIBIDOS = re.compile(r"[\[\]:*?/\\]")


def motivo(linha: dict, parametros: Parametros) -> str:
    """Frase curta explicando por que o item está no pedido."""
    dias = linha.get("dias_ate_acabar")
    if dias is not None and not pd.isna(dias) and int(dias) == 0:
        return "Estoque zerado"
    if linha.get("vai_faltar"):
        return f"Acaba em {int(dias)} dia(s), antes do pedido chegar ({linha['prazo']} dias)"
    return f"Cobre {parametros.horizonte} dias de vendas + {parametros.seguranca} de segurança"


def itens_sugeridos(tabela: pd.DataFrame, parametros: Parametros) -> pd.DataFrame:
    """Produtos com sugestão de compra, já marcados para entrar no pedido (os que vão faltar primeiro)."""
    sugeridos = tabela[tabela["quantidade_sugerida"] > 0]
    if sugeridos.empty:
        return pd.DataFrame(columns=COLUNAS_ITENS)
    sugeridos = sugeridos.assign(_ordem=~sugeridos["vai_faltar"]).sort_values(["_ordem", "dias_ate_acabar"])
    return pd.DataFrame({
        "incluir": True,
        "sku": sugeridos["sku"].astype(str),
        "produto": sugeridos["nome_produto"],
        "fornecedor": sugeridos["fornecedor"].fillna(SEM_FORNECEDOR),
        "quantidade": sugeridos["quantidade_sugerida"].astype(int),
        "lote": sugeridos["lote"].astype(int),
        "preco": sugeridos["preco"].astype(float),
        "prazo": sugeridos["prazo"].astype(int),
        "motivo": [motivo(l, parametros) for l in sugeridos.to_dict("records")],
    }).reset_index(drop=True)


def itens_do_pedido(itens: pd.DataFrame) -> pd.DataFrame:
    """Só o que vai para o arquivo: marcado e com quantidade maior que zero."""
    if itens.empty:
        return itens
    escolhidos = itens[itens["incluir"].fillna(False).astype(bool)].copy()
    escolhidos["quantidade"] = pd.to_numeric(escolhidos["quantidade"], errors="coerce").fillna(0).astype(int)
    return escolhidos[escolhidos["quantidade"] > 0].reset_index(drop=True)


def resumo_por_fornecedor(itens: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Uma linha por fornecedor: itens, unidades, total e chegada prevista (pelo maior prazo)."""
    if itens.empty:
        return pd.DataFrame(columns=["fornecedor", "itens", "unidades", "total", "prazo", "chegada"])
    resumo = (itens.assign(total=itens["quantidade"] * itens["preco"])
              .groupby("fornecedor", as_index=False, sort=False)
              .agg(itens=("sku", "count"), unidades=("quantidade", "sum"), total=("total", "sum"),
                   prazo=("prazo", "max")))
    resumo["chegada"] = [hoje + timedelta(days=int(p)) for p in resumo["prazo"]]
    return resumo.sort_values("total", ascending=False).reset_index(drop=True)


def abaixo_do_lote(itens: pd.DataFrame) -> pd.DataFrame:
    """Itens cuja quantidade não respeita o lote mínimo do fornecedor."""
    if itens.empty:
        return itens
    return itens[(itens["quantidade"] < itens["lote"]) | (itens["quantidade"] % itens["lote"].clip(lower=1) != 0)]


def nome_da_aba(fornecedor: str, usados: set) -> str:
    """Nome válido no Excel (até 31 caracteres, sem []:*?/\\) e sem repetir."""
    base = _PROIBIDOS.sub(" ", str(fornecedor)).strip().strip("'")[:31] or "Fornecedor"
    nome, n = base, 2
    while nome.lower() in usados:
        sufixo = f" ({n})"
        nome, n = base[: 31 - len(sufixo)] + sufixo, n + 1
    usados.add(nome.lower())
    return nome


# ------------------------------------------------------------------------------
# Excel
# ------------------------------------------------------------------------------
def _titulo(aba, texto: str, subtitulo: str) -> None:
    aba["A1"] = texto
    aba["A1"].font = Font(bold=True, size=14, color=_COR_CABECALHO)
    aba["A2"] = subtitulo
    aba["A2"].font = Font(italic=True, color="64748B")


def _cabecalho(aba, linha: int, colunas: list[str]) -> None:
    for i, nome in enumerate(colunas, start=1):
        celula = aba.cell(row=linha, column=i, value=nome)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=_COR_CABECALHO)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _linha_total(aba, linha: int, colunas: int) -> None:
    borda = Border(top=Side(style="thin", color=_COR_CABECALHO))
    for i in range(1, colunas + 1):
        celula = aba.cell(row=linha, column=i)
        celula.font = Font(bold=True)
        celula.fill = PatternFill("solid", fgColor=_COR_TOTAL)
        celula.border = borda


def _larguras(aba, larguras: list[int]) -> None:
    for i, largura in enumerate(larguras, start=1):
        aba.column_dimensions[get_column_letter(i)].width = largura


_COLUNAS_FORNECEDOR = ["Código", "Produto", "Quantidade", "Lote mínimo", "Preço unitário", "Subtotal",
                       "Prazo (dias)", "Chegada prevista", "Motivo da compra"]


def _aba_fornecedor(livro, nome_aba: str, fornecedor: str, itens: pd.DataFrame, hoje: date) -> None:
    aba = livro.create_sheet(nome_aba)
    _titulo(aba, f"Pedido de compra: {fornecedor}", f"Gerado em {hoje:%d/%m/%Y} · chegada considerando pedido feito hoje")
    _cabecalho(aba, 4, _COLUNAS_FORNECEDOR)
    primeira = 5
    for n, item in enumerate(itens.to_dict("records")):
        r = primeira + n
        valores = [item["sku"], item["produto"], int(item["quantidade"]), int(item["lote"]), float(item["preco"]),
                   f"=C{r}*E{r}", int(item["prazo"]), hoje + timedelta(days=int(item["prazo"])), item["motivo"]]
        for c, valor in enumerate(valores, start=1):
            aba.cell(row=r, column=c, value=valor)
        aba.cell(row=r, column=5).number_format = _MOEDA
        aba.cell(row=r, column=6).number_format = _MOEDA
        aba.cell(row=r, column=8).number_format = _DATA
    ultima = primeira + len(itens) - 1
    total = ultima + 1
    aba.cell(row=total, column=1, value="Total")
    aba.cell(row=total, column=3, value=f"=SUM(C{primeira}:C{ultima})")
    aba.cell(row=total, column=6, value=f"=SUM(F{primeira}:F{ultima})").number_format = _MOEDA
    _linha_total(aba, total, len(_COLUNAS_FORNECEDOR))
    _larguras(aba, [14, 38, 12, 12, 16, 16, 12, 16, 52])
    aba.freeze_panes = "A5"


def planilha_pedido(itens: pd.DataFrame, hoje: date) -> bytes:
    """Excel com a aba Resumo e uma aba por fornecedor. `itens` no formato de `itens_sugeridos`."""
    itens = itens_do_pedido(itens)
    resumo = resumo_por_fornecedor(itens, hoje)
    livro = Workbook()
    aba = livro.active
    aba.title = "Resumo"
    _titulo(aba, "Pedido de compra", f"Gerado em {hoje:%d/%m/%Y} pelo Supply Intelligence")
    colunas = ["Fornecedor", "Itens", "Unidades", "Total do pedido", "Maior prazo (dias)", "Chegada prevista", "Aba"]
    _cabecalho(aba, 4, colunas)
    usados = {"resumo"}
    for n, linha in enumerate(resumo.to_dict("records")):
        r = 5 + n
        nome_aba = nome_da_aba(linha["fornecedor"], usados)
        valores = [linha["fornecedor"], int(linha["itens"]), int(linha["unidades"]), f"='{nome_aba}'!F{5 + int(linha['itens'])}",
                   int(linha["prazo"]), linha["chegada"], nome_aba]
        for c, valor in enumerate(valores, start=1):
            aba.cell(row=r, column=c, value=valor)
        aba.cell(row=r, column=4).number_format = _MOEDA
        aba.cell(row=r, column=6).number_format = _DATA
        aba.cell(row=r, column=7).hyperlink = f"#'{nome_aba}'!A1"
        aba.cell(row=r, column=7).font = Font(color="2563EB", underline="single")
        _aba_fornecedor(livro, nome_aba, linha["fornecedor"], itens[itens["fornecedor"] == linha["fornecedor"]], hoje)
    if resumo.empty:
        aba.cell(row=5, column=1, value="Nenhum item selecionado.")
    else:
        total = 5 + len(resumo)
        aba.cell(row=total, column=1, value="Total geral")
        aba.cell(row=total, column=2, value=f"=SUM(B5:B{total - 1})")
        aba.cell(row=total, column=3, value=f"=SUM(C5:C{total - 1})")
        aba.cell(row=total, column=4, value=f"=SUM(D5:D{total - 1})").number_format = _MOEDA
        _linha_total(aba, total, len(colunas))
    _larguras(aba, [30, 8, 11, 18, 16, 16, 24])
    saida = BytesIO()
    livro.save(saida)
    return saida.getvalue()


def nome_arquivo(hoje: date) -> str:
    return f"pedido_de_compra_{hoje:%Y-%m-%d}.xlsx"
