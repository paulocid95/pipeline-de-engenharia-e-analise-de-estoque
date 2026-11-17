from datetime import date

import pandas as pd
from sqlalchemy import text

from db import criar_engine
from regras_fornecedores import ROTULO_CLASSE, ranking_fornecedores

engine = criar_engine()


def consultar_dados():
    print("--- 1. CONTAGEM DE REGISTROS POR TABELA ---")
    query_contagem = """
        SELECT 
            (SELECT COUNT(*) FROM core.dim_categorias) AS total_categorias,
            (SELECT COUNT(*) FROM core.dim_produtos) AS total_produtos,
            (SELECT COUNT(*) FROM core.fato_estoque) AS total_registros_fato,
            (SELECT COUNT(DISTINCT data_carga) FROM core.fato_estoque) AS total_cargas_historicas,
            (SELECT COUNT(*) FROM core.fato_cotacoes) AS total_cotacoes,
            (SELECT COUNT(*) FROM core.fato_ocorrencias) AS total_ocorrencias;
    """
    df_contagem = pd.read_sql(text(query_contagem), engine)
    print(df_contagem.to_string(index=False))

    # A fato guarda um snapshot por execução do pipeline; o resumo usa só a carga mais recente
    # para não somar o mesmo estoque várias vezes.
    print("\n--- 2. RESUMO DE ESTOQUE POR STATUS (CARGA MAIS RECENTE) ---")
    query_status = """
        SELECT
            f.status_reposicao,
            COUNT(DISTINCT f.id_produto) AS qtd_produtos,
            SUM(f.quantidade_disponivel) AS estoque_total_itens,
            ROUND(SUM(f.valor_total_estoque), 2) AS valor_total_reais
        FROM core.fato_estoque f
        WHERE f.data_carga = (SELECT MAX(data_carga) FROM core.fato_estoque)
        GROUP BY f.status_reposicao
        ORDER BY valor_total_reais DESC;
    """
    df_status = pd.read_sql(text(query_status), engine)
    print(df_status.to_string(index=False))

    print("\n--- 3. RANKING E RISCO DE FORNECEDORES ---")
    df_cot = pd.read_sql(text("SELECT id_produto, fornecedor, preco_cotado, prazo_dias, lote_minimo FROM core.fato_cotacoes;"), engine)
    df_oc = pd.read_sql(text("SELECT * FROM core.fato_ocorrencias;"), engine)
    ranking = ranking_fornecedores(df_cot, df_oc, date.today())
    ranking["classe"] = ranking["classe"].map(ROTULO_CLASSE)
    print(ranking[["fornecedor", "nota_final", "classe", "nota_confiabilidade", "ocorrencias_12m", "sem_solucao", "motivo"]].to_string(index=False))


if __name__ == "__main__":
    consultar_dados()