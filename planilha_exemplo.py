"""Planilha de exemplo (Excel) com os dados da demonstração, bagunçados de propósito.

A ideia: o visitante baixa, envia de volta e vê a higienização acontecer.
Toda bagunça é reversível (mesmo valor escrito de outro jeito), então depois da
limpeza os números voltam a ser exatamente os da demonstração.
"""

import io
import random
from datetime import date

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from regras_estoque import LIMITE_ALERTA, LIMITE_EXCESSO
from regras_fornecedores import ROTULOS_GRAVIDADE, ROTULOS_STATUS, ROTULOS_TIPO
from simulacao_vendas import simular_vendas

NOME_ARQUIVO = "supply_intelligence_planilha_exemplo.xlsx"

SINONIMOS_CATEGORIA = {
    "Smartphones": ["celular", "Celulares", "SMARTPHONE"],
    "Fones de Ouvido": ["fone", "Audio", "FONES"],
    "Carregadores": ["carregador", "Acessórios - Carregador", "CARREGADORES"],
}


# ------------------------------------------------------------------------------
# Formas "bagunçadas" de escrever o mesmo valor
# ------------------------------------------------------------------------------
def _br(valor: float) -> str:
    """1234.5 -> '1.234,50'"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preco_baguncado(valor: float, rng: random.Random):
    return rng.choice([
        valor,                         # número de verdade
        f"R$ {_br(valor)}",            # R$ 1.234,50
        _br(valor),                    # 1.234,50
        f"{valor:.2f}",                # 1234.50 (texto)
        f"R${valor:,.2f}",             # R$1,234.50 (formato americano)
    ])


def quantidade_baguncada(qtd: int, rng: random.Random):
    if qtd == 0 and rng.random() < 0.5:
        return ""                      # zerado vira célula vazia
    return rng.choice([qtd, qtd, f"{qtd} un", f"{qtd},0", f"{qtd} pçs"])


def fornecedor_baguncado(nome: str, rng: random.Random) -> str:
    letra = nome.split()[-1]
    return rng.choice([nome, f"{nome.upper()} LTDA", f"forn. {letra.lower()}", f"Fornecedor_{letra}", f" {nome.lower()} "])


def texto_baguncado(texto: str, rng: random.Random) -> str:
    return rng.choice([texto, texto, texto.upper(), texto.lower(), f"  {texto} ", texto.replace(" ", "  ", 1)])


def _variacao_caixa(texto: str, rng: random.Random) -> str:
    return rng.choice([texto, texto.upper(), texto.lower()])


def categoria_baguncada(categoria: str, rng: random.Random) -> str:
    if rng.random() < 0.15:
        return ""                      # sem categoria: deduzida pelo nome do produto
    return rng.choice([categoria, categoria.lower(), *SINONIMOS_CATEGORIA.get(categoria, [])])


def data_baguncada(valor, rng: random.Random):
    if valor is None or pd.isna(valor):
        return ""
    d = pd.Timestamp(valor).date()
    return rng.choice([d, d.strftime("%d/%m/%Y"), d.isoformat(), d.strftime("%d.%m.%Y")])


def prazo_baguncado(dias: int, rng: random.Random):
    return rng.choice([dias, f"{dias} dias", f"{dias}d", f"{dias} dia(s)"])


# ------------------------------------------------------------------------------
# Abas
# ------------------------------------------------------------------------------
def aba_estoque(df: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    linhas = []
    for r in df.itertuples(index=False):
        qtd = int(r.quantidade_disponivel)
        # Alguns SKUs aparecem duplicados, com a quantidade dividida em duas linhas
        partes = [qtd] if qtd < 2 or rng.random() > 0.12 else [qtd // 2, qtd - qtd // 2]
        for parte in partes:
            linhas.append({
                "Cód. Item": r.sku,
                "Descrição do Produto": texto_baguncado(r.nome_produto, rng),
                "Depto": categoria_baguncada(r.nome_categoria, rng),
                "Fornec.": fornecedor_baguncado(r.fornecedor, rng),
                "Preço Unit.": preco_baguncado(float(r.preco_unitario), rng),
                "Qtd Disp.": quantidade_baguncada(parte, rng),
            })
    return pd.DataFrame(linhas)


def aba_cotacoes(df: pd.DataFrame, rng: random.Random, hoje: date) -> pd.DataFrame:
    return pd.DataFrame([{
        "SKU": r.sku,
        "Item": texto_baguncado(r.nome_produto, rng),
        "Fornecedor": fornecedor_baguncado(r.fornecedor_cotacao, rng),
        "Valor Cotado": preco_baguncado(float(r.preco_cotado), rng),
        "Prazo Entrega": prazo_baguncado(int(r.prazo_dias), rng),
        "Lote Mín.": rng.choice([int(r.lote_minimo), f"{int(r.lote_minimo)} un"]),
        "Data Cotação": data_baguncada(hoje, rng),
    } for r in df.itertuples(index=False)])


def aba_ocorrencias(df: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    return pd.DataFrame([{
        "Fornecedor": fornecedor_baguncado(r.fornecedor, rng),
        "Produto": "" if r.nome_produto is None or pd.isna(r.nome_produto) else r.nome_produto,
        "Ocorrência": ROTULOS_TIPO.get(r.tipo, r.tipo),
        "Gravidade": _variacao_caixa(ROTULOS_GRAVIDADE.get(r.gravidade, r.gravidade), rng),
        "Data": data_baguncada(r.data_ocorrencia, rng),
        "Situação": _variacao_caixa(ROTULOS_STATUS.get(r.status, r.status), rng),
        "Resolvido em": data_baguncada(r.data_resolucao, rng),
        "Descrição": r.descricao,
    } for r in df.itertuples(index=False)])


def aba_vendas(df_estoque: pd.DataFrame, rng: random.Random, hoje: date) -> pd.DataFrame:
    vendas = simular_vendas(df_estoque, hoje)
    return pd.DataFrame({
        "Data": vendas["data"],
        "SKU": vendas["sku"],
        "Produto": vendas["nome_produto"],
        "Qtd Vendida": [q if rng.random() > 0.05 else f"{q} un" for q in vendas["quantidade_vendida"]],
    })


INSTRUCOES = [
    ("Supply Intelligence: planilha de exemplo", "titulo"),
    ("", None),
    ("Esta planilha tem os mesmos dados da demonstração, mas BAGUNÇADOS DE PROPÓSITO,", None),
    ("do jeito que costumam sair de sistemas e planilhas do dia a dia. Envie de volta pelo", None),
    ("botão \"Analisar minha planilha\" e veja a higienização acontecer.", None),
    ("", None),
    ("O que você vai encontrar de bagunça", "sub"),
    ("• Preços em vários formatos: R$ 1.234,50 / 1.234,50 / 1234.50 / R$1,234.50", None),
    ("• Quantidades com texto (\"12 un\", \"12,0\", \"12 pçs\") e células vazias", None),
    ("• O mesmo fornecedor escrito de jeitos diferentes (\"FORNECEDOR A LTDA\", \"forn. a\")", None),
    ("• Produtos com espaços sobrando e maiúsculas/minúsculas misturadas", None),
    ("• Categorias com sinônimos ou em branco, SKUs duplicados e datas em formatos diferentes", None),
    ("• Na aba Estoque: título acima do cabeçalho e uma linha de TOTAL no final", None),
    ("", None),
    ("Abas e colunas", "sub"),
    ("Estoque (obrigatória): produto, quantidade e preço. Opcionais: SKU, categoria, fornecedor, estoque mínimo.", None),
    ("Cotações: produto (ou SKU), fornecedor e preço. Opcionais: prazo de entrega e lote mínimo.", None),
    ("Ocorrências: fornecedor, tipo e data. Opcionais: gravidade, situação, data de resolução, descrição.", None),
    ("Vendas: data, produto (ou SKU) e quantidade vendida. Usada na previsão de demanda.", None),
    ("", None),
    ("Para usar com os seus dados", "sub"),
    ("• Os nomes das colunas não precisam ser iguais aos daqui: o sistema reconhece variações.", None),
    ("• Pode enviar um Excel com abas ou arquivos CSV separados (até 5 MB e 10 mil linhas cada).", None),
    (f"• Limites de status: informe os do seu negócio ou usamos o padrão (alerta até {LIMITE_ALERTA} unidades, excesso acima de {LIMITE_EXCESSO}).", None),
    ("• Seus dados ficam só na sua sessão e não são gravados.", None),
]


# ------------------------------------------------------------------------------
# Montagem do arquivo
# ------------------------------------------------------------------------------
def _ajustar_larguras(ws, inicio: int = 1) -> None:
    for col in ws.iter_cols(min_row=inicio):
        maior = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, maior + 2), 60)


def _destacar_cabecalho(ws, linha: int) -> None:
    for c in ws[linha]:
        if c.value is not None:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2F62C9")


def montar_planilha_exemplo(
    df_estoque: pd.DataFrame,
    df_cotacoes: pd.DataFrame,
    df_ocorrencias: pd.DataFrame,
    hoje: date,
    seed: int = 42,
) -> bytes:
    """Gera o Excel de exemplo (bytes) a partir dos dados da demonstração."""
    rng = random.Random(seed)
    estoque = aba_estoque(df_estoque.sort_values("sku"), rng)
    cotacoes = aba_cotacoes(df_cotacoes, rng, hoje)
    ocorrencias = aba_ocorrencias(df_ocorrencias, rng)
    vendas = aba_vendas(df_estoque, rng, hoje)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame().to_excel(writer, sheet_name="Instruções")
        estoque.to_excel(writer, sheet_name="Estoque", index=False, startrow=2)
        cotacoes.to_excel(writer, sheet_name="Cotações", index=False)
        ocorrencias.to_excel(writer, sheet_name="Ocorrências", index=False)
        vendas.to_excel(writer, sheet_name="Vendas", index=False)

        # Instruções
        ws = writer.sheets["Instruções"]
        for i, (texto, estilo) in enumerate(INSTRUCOES, start=1):
            celula = ws.cell(row=i, column=1, value=texto)
            if estilo == "titulo":
                celula.font = Font(bold=True, size=16, color="2F62C9")
            elif estilo == "sub":
                celula.font = Font(bold=True, size=12)
        ws.column_dimensions["A"].width = 110

        # Estoque: título acima do cabeçalho e linha de TOTAL, como num relatório de ERP
        ws = writer.sheets["Estoque"]
        ws["A1"] = f"Relatório de posição de estoque - exportado em {hoje.strftime('%d/%m/%Y')}"
        ws["A1"].font = Font(bold=True, size=13)
        linha_total = len(estoque) + 4
        ws.cell(row=linha_total, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=linha_total, column=6, value=int(df_estoque["quantidade_disponivel"].sum())).font = Font(bold=True)
        _destacar_cabecalho(ws, 3)
        _ajustar_larguras(ws, inicio=3)

        for nome in ("Cotações", "Ocorrências", "Vendas"):
            ws = writer.sheets[nome]
            _destacar_cabecalho(ws, 1)
            _ajustar_larguras(ws)
            ws.freeze_panes = "A2"
        for ws in writer.sheets.values():
            for linha in ws.iter_rows():
                for c in linha:
                    if isinstance(c.value, date):
                        c.number_format = "DD/MM/YYYY"
                        c.alignment = Alignment(horizontal="left")

    return buffer.getvalue()
