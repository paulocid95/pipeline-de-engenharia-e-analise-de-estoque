"""Planilha limpa para o usuário baixar: uma aba por tabela, já padronizada (e que pode ser enviada de novo)."""

from io import BytesIO

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from regras_fornecedores import ROTULOS_GRAVIDADE, ROTULOS_STATUS, ROTULOS_TIPO

NOME_ARQUIVO_LIMPO = "meus_dados_higienizados.xlsx"

ROTULOS_SITUACAO_ESTOQUE = {"CRITICO": "Crítico", "ALERTA": "Alerta", "NORMAL": "Normal", "EXCESSO": "Excesso"}

# Aba -> (coluna do painel -> cabeçalho na planilha). Os cabeçalhos são reconhecidos pela própria higienização.
_ABAS = {
    "Estoque": {
        "sku": "Código", "nome_produto": "Produto", "nome_categoria": "Categoria", "fornecedor": "Fornecedor",
        "preco_unitario": "Preço unitário", "quantidade_disponivel": "Quantidade", "estoque_minimo": "Estoque mínimo",
        "status_reposicao": "Situação",
    },
    "Cotações": {
        "sku": "Código", "nome_produto": "Produto", "fornecedor_cotacao": "Fornecedor", "preco_cotado": "Preço cotado",
        "prazo_dias": "Prazo de entrega (dias)", "lote_minimo": "Lote mínimo", "data_cotacao": "Data da cotação",
    },
    "Ocorrências": {
        "data_ocorrencia": "Data da ocorrência", "fornecedor": "Fornecedor", "nome_produto": "Produto",
        "tipo": "Tipo de problema", "gravidade": "Gravidade", "status": "Situação",
        "data_resolucao": "Data de resolução", "descricao": "Descrição",
    },
    "Vendas": {"data": "Data", "sku": "Código", "nome_produto": "Produto", "quantidade_vendida": "Quantidade vendida"},
}
_MOEDA = {"Preço unitário", "Preço cotado"}
_DATAS = {"Data da cotação", "Data da ocorrência", "Data de resolução", "Data"}
_COR_CABECALHO = "2F62C9"


def _tabela(df: pd.DataFrame, colunas: dict) -> pd.DataFrame:
    tabela = df[[c for c in colunas if c in df.columns]].copy()
    traducoes = {"status_reposicao": ROTULOS_SITUACAO_ESTOQUE, "tipo": ROTULOS_TIPO,
                 "gravidade": ROTULOS_GRAVIDADE, "status": ROTULOS_STATUS}
    for coluna, rotulos in traducoes.items():
        if coluna in tabela.columns:
            tabela[coluna] = tabela[coluna].map(lambda v, r=rotulos: r.get(v, v))
    for coluna in tabela.columns:
        if colunas[coluna] in _DATAS:
            tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.date
    return tabela.rename(columns=colunas)


def _formatar(aba, tabela: pd.DataFrame) -> None:
    for i, cabecalho in enumerate(tabela.columns, start=1):
        celula = aba.cell(row=1, column=i)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=_COR_CABECALHO)
        celula.alignment = Alignment(horizontal="center", vertical="center")
        valores = tabela[cabecalho].astype(str).replace({"None": "", "nan": "", "NaT": ""})
        largura = max([len(str(cabecalho)), *valores.str.len().tolist()]) if len(valores) else len(str(cabecalho))
        aba.column_dimensions[get_column_letter(i)].width = min(max(largura + 3, 10), 60)
        formato = "R$ #,##0.00" if cabecalho in _MOEDA else "DD/MM/YYYY" if cabecalho in _DATAS else None
        if formato:
            for linha in range(2, len(tabela) + 2):
                aba.cell(row=linha, column=i).number_format = formato
    aba.freeze_panes = "A2"


def planilha_higienizada(resultado) -> bytes:
    """Excel com Estoque, Cotações, Ocorrências e Vendas limpos, mais o relatório do que foi corrigido."""
    fontes = {"Estoque": resultado.estoque, "Cotações": resultado.cotacoes,
              "Ocorrências": resultado.ocorrencias, "Vendas": resultado.vendas}
    saida = BytesIO()
    with pd.ExcelWriter(saida, engine="openpyxl") as escritor:
        for nome, df in fontes.items():
            if df is None or df.empty:
                continue
            tabela = _tabela(df, _ABAS[nome])
            tabela.to_excel(escritor, sheet_name=nome, index=False)
            _formatar(escritor.sheets[nome], tabela)

        relatorio = pd.DataFrame(
            [{"Tabela": i.aba, "O que foi feito": i.mensagem, "Linhas afetadas": i.quantidade}
             for i in resultado.relatorio if i.quantidade]
            + [{"Tabela": d["aba"], "O que foi feito": f"Linha {d['linha']} descartada: {d['motivo']}",
                "Linhas afetadas": 1} for d in resultado.descartes]
        )
        if not relatorio.empty:
            relatorio.to_excel(escritor, sheet_name="Relatório da limpeza", index=False)
            _formatar(escritor.sheets["Relatório da limpeza"], relatorio)
    return saida.getvalue()
