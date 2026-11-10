"""Formatação monetária e exportação de relatórios em Excel."""

import io

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def formatar_moeda_brl(valor: float) -> str:
    """Formata valor para a representação monetária brasileira (R$ 1.234,56)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_excel_estilizado(df: pd.DataFrame) -> bytes:
    """Gera uma planilha Excel (.xlsx) altamente estilizada e profissional em memória via openpyxl.
    
    Aplica formatação institucional com cabeçalho azul-escuro, autoajuste de largura de colunas,
    formatação monetária em R$ e alinhamento tático de dados operacionais.
    """
    df_export = df.rename(columns={
        "sku": "SKU",
        "nome_produto": "Produto",
        "nome_categoria": "Categoria",
        "fornecedor": "Fornecedor",
        "preco_unitario": "Preço Unitário",
        "quantidade_disponivel": "Quantidade em Estoque",
        "valor_total_estoque": "Valor Total em Estoque",
        "status_reposicao": "Status de Reposição"
    })

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Estoque_Consolidado", index=False)
        ws = writer.sheets["Estoque_Consolidado"]
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        # 1. Cabeçalho destacado institucional (Azul-Escuro e Branco)
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 28

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align

        # 2. Bordas e formatação das linhas de dados
        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        col_nomes = [cell.value for cell in ws[1]]
        idx_sku = col_nomes.index("SKU") + 1 if "SKU" in col_nomes else None
        idx_qtd = col_nomes.index("Quantidade em Estoque") + 1 if "Quantidade em Estoque" in col_nomes else None
        idx_status = col_nomes.index("Status de Reposição") + 1 if "Status de Reposição" in col_nomes else None
        idx_preco = col_nomes.index("Preço Unitário") + 1 if "Preço Unitário" in col_nomes else None
        idx_total = col_nomes.index("Valor Total em Estoque") + 1 if "Valor Total em Estoque" in col_nomes else None

        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            ws.row_dimensions[row[0].row].height = 20
            for cell in row:
                cell.font = Font(name="Calibri", size=10)
                cell.border = thin_border
                c_idx = cell.column

                # 4. Alinhamento centralizado em SKU, Quantidade e Status de Reposição
                if c_idx in [idx_sku, idx_qtd, idx_status]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                # 3. Formatação monetária adequada em colunas financeiras
                elif c_idx in [idx_preco, idx_total]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = '"R$" #,##0.00'
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

                if c_idx == idx_qtd:
                    cell.number_format = "#,##0"

        # 1. Autoajuste da largura de todas as colunas para que nenhum texto fique cortado
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if cell.number_format and "R$" in cell.number_format:
                    val = f"R$ {val},00"
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    return output.getvalue()
