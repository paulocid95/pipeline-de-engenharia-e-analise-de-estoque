import pandas as pd
from sqlalchemy import text

from db import criar_engine

engine = criar_engine()


def consultar_dados():
    print("--- 1. CONTAGEM DE REGISTROS POR TABELA ---")
    query_contagem = """
        SELECT 
            (SELECT COUNT(*) FROM core.dim_categorias) AS total_categorias,
            (SELECT COUNT(*) FROM core.dim_produtos) AS total_produtos,
            (SELECT COUNT(*) FROM core.fato_estoque) AS total_registros_fato,
            (SELECT COUNT(DISTINCT data_carga) FROM core.fato_estoque) AS total_cargas_historicas;
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


if __name__ == "__main__":
    consultar_dados()