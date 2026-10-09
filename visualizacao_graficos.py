"""Passo 5: Visualização de Dados e Geração de Gráficos Executivos.

Este script lê a base consolidada em 'dados_processados/estoque_consolidado_limpo.csv'
e utiliza matplotlib e seaborn para criar gráficos executivos em alta resolução (300 DPI):
1. 'graficos/valor_por_categoria.png' : Capital retido por categoria com destaque semântico em Smartphones.
2. 'graficos/distribuicao_estoque_fornecedor.png': Comparativo de volume físico e variedade de SKUs por fornecedor.
3. 'graficos/alerta_ruptura_estoque.png': Produtos com estoque zerado ranqueados por ticket sem truncamento de rótulos.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import seaborn as sns


# ==============================================================================
# CONFIGURAÇÃO DE ESTILO E FORMATAÇÃO
# ==============================================================================
def configurar_estilo_visual() -> None:
    """Configura o tema global e parâmetros tipográficos do matplotlib e seaborn."""
    sns.set_theme(style="whitegrid", font="sans-serif")
    plt.rcParams.update({
        "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.labelweight": "bold",
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "figure.titlesize": 15,
        "figure.titleweight": "bold",
        "figure.facecolor": "#ffffff",
        "axes.facecolor": "#fafbfc",
        "grid.color": "#e2e8f0",
        "grid.linestyle": "--",
        "grid.alpha": 0.6,
    })


def formatar_brl(valor: float) -> str:
    """Formata valor numérico para o padrão monetário brasileiro (R$ 1.234,56)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ==============================================================================
# 1. CAPITAL RETIDO POR CATEGORIA (PALETA SEMÂNTICA & DESTAQUE FOCAL)
# ==============================================================================
def gerar_grafico_valor_categoria(df: pd.DataFrame, pasta_saida: Path) -> Path:
    """Gera gráfico de barras horizontais do capital retido por categoria.
    
    Aplica o princípio de foco de atenção (preattentive attributes) para evidenciar
    a concentração de 80,9% do capital imobilizado na categoria de Smartphones,
    mantendo categorias secundárias em tons neutros de apoio.
    """
    df_cat = df.groupby("categoria", as_index=False).agg(
        valor_total=("valor_total", "sum"),
        unidades=("estoque", "sum"),
    ).sort_values(by="valor_total", ascending=True)

    total_global = df_cat["valor_total"].sum()
    df_cat["pct"] = (df_cat["valor_total"] / total_global) * 100

    fig, ax = plt.subplots(figsize=(10.5, 5.5), dpi=300)

    # Cores semânticas: azul cobalto para Smartphones (foco) e cinza-ardósia para demais
    cor_focal = "#1d4ed8"
    cor_neutra = "#94a3b8"
    borda_focal = "#1e3a8a"
    borda_neutra = "#64748b"

    cores_barras = [cor_focal if cat == "Smartphones" else cor_neutra for cat in df_cat["categoria"]]
    bordas_barras = [borda_focal if cat == "Smartphones" else borda_neutra for cat in df_cat["categoria"]]

    barras = ax.barh(
        df_cat["categoria"],
        df_cat["valor_total"],
        color=cores_barras,
        edgecolor=bordas_barras,
        linewidth=1.0,
        height=0.52,
    )

    # Grid sutil apenas no eixo numérico (X)
    ax.xaxis.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)

    # Rótulos de dados: valores monetários absolutos e percentuais explicitados
    for barra, pct, val, cat in zip(barras, df_cat["pct"], df_cat["valor_total"], df_cat["categoria"]):
        largura = barra.get_width()
        texto = f"{formatar_brl(val)}  ({pct:.1f}%)"
        is_foco = cat == "Smartphones"
        ax.text(
            largura + (total_global * 0.015),
            barra.get_y() + barra.get_height() / 2,
            texto,
            va="center",
            ha="left",
            fontsize=10.5,
            fontweight="bold" if is_foco else "normal",
            color="#1e3a8a" if is_foco else "#334155",
        )

    # Configuração de eixos e formatação executiva
    ax.set_xlim(0, df_cat["valor_total"].max() * 1.35)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"R$ {x/1e3:.0f}k" if x > 0 else "R$ 0"))
    ax.set_title("Capital Financeiro Total Retido em Estoque por Categoria", pad=18)
    ax.set_xlabel("Montante Retido (R$)", labelpad=10)
    ax.set_ylabel("Categoria", labelpad=10)

    # Nota de rodapé executiva destacando a concentração
    fig.text(
        0.5,
        -0.03,
        f"Montante Financeiro Consolidado: {formatar_brl(total_global)}  |  Smartphones concentram 80,9% do capital retido",
        ha="center",
        fontsize=10.5,
        fontstyle="italic",
        color="#475569",
    )

    sns.despine(top=True, right=True, left=False, bottom=False)

    arquivo_saida = pasta_saida / "valor_por_categoria.png"
    plt.savefig(arquivo_saida, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return arquivo_saida


# ==============================================================================
# 2. DISTRIBUIÇÃO FÍSICA E SKUs POR FORNECEDOR
# ==============================================================================
def gerar_grafico_distribuicao_fornecedor(df: pd.DataFrame, pasta_saida: Path) -> Path:
    """Gera gráfico comparativo de volume físico de estoque vs. diversidade de SKUs."""
    df_forn = df.groupby("fornecedor", as_index=False).agg(
        unidades=("estoque", "sum"),
        skus=("id_produto", "count"),
        valor_total=("valor_total", "sum"),
    ).sort_values(by="unidades", ascending=False)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)

    # Painel 1: Unidades Físicas em Estoque
    cores_unidades = ["#2563eb", "#3b82f6", "#60a5fa"]
    barras1 = ax1.bar(
        df_forn["fornecedor"],
        df_forn["unidades"],
        color=cores_unidades,
        edgecolor="#1e293b",
        linewidth=0.8,
        width=0.52,
    )
    for barra in barras1:
        altura = barra.get_height()
        ax1.text(
            barra.get_x() + barra.get_width() / 2,
            altura + 6,
            f"{int(altura)} un",
            ha="center",
            va="bottom",
            fontweight="bold",
            color="#0f172a",
        )
    ax1.set_ylim(0, df_forn["unidades"].max() * 1.18)
    ax1.set_title("Volume Físico Total (Unidades)", pad=15)
    ax1.set_ylabel("Quantidade de Peças", labelpad=8)
    ax1.set_xlabel("Fornecedor", labelpad=8)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax1.xaxis.grid(False)
    ax1.set_axisbelow(True)

    # Painel 2: Variedade de Catálogo (SKUs Ativos)
    cores_skus = ["#0d9488", "#14b8a6", "#2dd4bf"]
    barras2 = ax2.bar(
        df_forn["fornecedor"],
        df_forn["skus"],
        color=cores_skus,
        edgecolor="#1e293b",
        linewidth=0.8,
        width=0.52,
    )
    for barra in barras2:
        altura = barra.get_height()
        ax2.text(
            barra.get_x() + barra.get_width() / 2,
            altura + 0.25,
            f"{int(altura)} SKUs",
            ha="center",
            va="bottom",
            fontweight="bold",
            color="#0f172a",
        )
    ax2.set_ylim(0, 11)
    ax2.set_title("Diversidade de Catálogo (SKUs Ativos)", pad=15)
    ax2.set_ylabel("Número de Produtos", labelpad=8)
    ax2.set_xlabel("Fornecedor", labelpad=8)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax2.xaxis.grid(False)
    ax2.set_axisbelow(True)

    fig.suptitle("Comparativo de Fornecedores: Volume Físico vs. Variedade de Catálogo", y=1.03)
    sns.despine(top=True, right=True)

    arquivo_saida = pasta_saida / "distribuicao_estoque_fornecedor.png"
    plt.savefig(arquivo_saida, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return arquivo_saida


# ==============================================================================
# 3. ALERTA DE RUPTURA DE ESTOQUE (PRODUTOS ZERADOS SEM TRUNCAMENTO)
# ==============================================================================
def gerar_grafico_alerta_ruptura(df: pd.DataFrame, pasta_saida: Path) -> Path:
    """Gera gráfico destacando os itens com estoque zerado ranqueados por ticket unitário.
    
    Correções de legibilidade aplicadas:
    - Quebra de linha entre o nome completo do produto e o fornecedor (f"{produto}\\n[{fornecedor}]"),
      eliminando reticências e truncamentos visuais.
    - Dimensões ampliadas e margens calculadas com bbox_inches='tight' para visualização nítida.
    - Ordenação decrescente do topo à base por potencial de faturamento/preço unitário.
    """
    df_rup = df[df["estoque"] == 0].copy()
    # No barh do Matplotlib, ordenação ascendente no DataFrame plota o maior valor no topo do gráfico
    df_rup = df_rup.sort_values(by="preco", ascending=True)

    # Rótulo em duas linhas sem truncamento: Linha 1 = Nome do Produto; Linha 2 = Fornecedor
    df_rup["rotulo_completo"] = [
        f"{prod}\n[{forn}]" for prod, forn in zip(df_rup["produto"], df_rup["fornecedor"])
    ]

    fig, ax = plt.subplots(figsize=(12, 7.2), dpi=300)

    # Paleta semântica em degradê de alerta (tons quentes de risco operacional)
    paleta_alerta = sns.color_palette("YlOrRd", n_colors=len(df_rup))

    barras = ax.barh(
        df_rup["rotulo_completo"],
        df_rup["preco"],
        color=paleta_alerta,
        edgecolor="#7f1d1d",
        linewidth=0.8,
        height=0.62,
    )

    # Grid sutil apenas no eixo horizontal (preço)
    ax.xaxis.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)

    # Formatação dos rótulos de dados nas barras
    max_preco = df_rup["preco"].max()
    for barra, preco, cat in zip(barras, df_rup["preco"], df_rup["categoria"]):
        largura = barra.get_width()
        texto = f"{formatar_brl(preco)}  •  {cat}"
        ax.text(
            largura + (max_preco * 0.02),
            barra.get_y() + barra.get_height() / 2,
            texto,
            va="center",
            ha="left",
            fontsize=9.8,
            fontweight="bold",
            color="#991b1b",
        )

    # Limites e eixos
    ax.set_xlim(0, max_preco * 1.38)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"R$ {x/1e3:.1f}k" if x >= 1000 else f"R$ {x:.0f}"))
    ax.set_title("Alerta de Ruptura de Estoque: Produtos Zerados (Ordem por Ticket)", pad=18)
    ax.set_xlabel("Preço Unitário / Potencial de Faturamento Unitário (R$)", labelpad=10)
    ax.set_ylabel("Produto / [Fornecedor]", labelpad=10)

    # Subtítulo executivo
    fig.text(
        0.5,
        -0.03,
        "Itens que demandam reposição prioritária pelo alto valor unitário e risco iminente de perda de receita.",
        ha="center",
        fontsize=10.5,
        fontstyle="italic",
        color="#7f1d1d",
    )

    sns.despine(top=True, right=True, left=False, bottom=False)

    arquivo_saida = pasta_saida / "alerta_ruptura_estoque.png"
    plt.savefig(arquivo_saida, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return arquivo_saida


# ==============================================================================
# EXECUÇÃO PRINCIPAL
# ==============================================================================
def main() -> None:
    diretorio_raiz = Path(__file__).parent
    caminho_dados = diretorio_raiz / "dados_processados" / "estoque_consolidado_limpo.csv"
    pasta_graficos = diretorio_raiz / "graficos"
    pasta_graficos.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" INICIANDO GERAÇÃO DE GRÁFICOS EXECUTIVOS COM MATPLOTLIB & SEABORN")
    print("=" * 80)

    if not caminho_dados.exists():
        raise FileNotFoundError(f"Base de dados não encontrada: {caminho_dados.resolve()}")

    # 1. Carrega dados e calcula valor financeiro
    df = pd.read_csv(caminho_dados)
    df["valor_total"] = df["preco"] * df["estoque"]

    # 2. Configura estética dos gráficos
    configurar_estilo_visual()

    # 3. Geração e salvamento das imagens em 300 DPI
    grafico1 = gerar_grafico_valor_categoria(df, pasta_graficos)
    print(f"[OK] Gráfico 1 gerado: {grafico1.name} (Resolução: 300 DPI | Destaque Focal: Smartphones)")

    grafico2 = gerar_grafico_distribuicao_fornecedor(df, pasta_graficos)
    print(f"[OK] Gráfico 2 gerado: {grafico2.name} (Resolução: 300 DPI | Comparativo Fornecedores)")

    grafico3 = gerar_grafico_alerta_ruptura(df, pasta_graficos)
    print(f"[OK] Gráfico 3 gerado: {grafico3.name} (Resolução: 300 DPI | Rótulos Completos Sem Truncamento)")

    print("=" * 80)
    print(" TODOS OS GRÁFICOS FORAM SALVOS COM SUCESSO NA PASTA:")
    print(f" -> {pasta_graficos.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
