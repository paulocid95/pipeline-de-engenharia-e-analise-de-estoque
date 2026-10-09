import os
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Carregar variáveis de ambiente do arquivo .env
load_dotenv()
database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if not database_url:
    raise ValueError("A variável DATABASE_URL não foi encontrada no arquivo .env.")

engine = create_engine(database_url, echo=False)


def carregar_pipeline():
    # 2. Localização determinística do arquivo canônico
    caminho_arquivo = os.path.join("dados_processados", "estoque_consolidado_limpo.csv")
    
    if not os.path.exists(caminho_arquivo):
        print(f"Erro: Arquivo canônico não encontrado em '{caminho_arquivo}'.")
        print("Certifique-se de executar 'limpeza_padronizacao.py' antes da carga.")
        return

    print(f"Lendo dados limpos de: {caminho_arquivo}")
    df = pd.read_csv(caminho_arquivo)

    # 3. Engenharia de atributos e regras de negócio para a tabela fato
    df["preco"] = pd.to_numeric(df["preco"], errors="coerce").fillna(0.0)
    df["estoque"] = pd.to_numeric(df["estoque"], errors="coerce").fillna(0).astype(int)
    df["valor_total"] = (df["preco"] * df["estoque"]).round(2)

    def classificar_status(qtd: int) -> str:
        if qtd == 0:
            return "CRITICO"
        if qtd <= 15:
            return "ALERTA"
        if qtd > 100:
            return "EXCESSO"
        return "NORMAL"

    df["status_reposicao"] = df["estoque"].apply(classificar_status)

    # Timestamp uniforme para todo o lote de ingestão
    timestamp_lote = datetime.now(timezone.utc)

    print("Iniciando transação atômica de carga no PostgreSQL...")

    with engine.begin() as conexao:
        # 4. Inserção em lote de Categorias (dim_categorias)
        categorias_unicas = df["categoria"].dropna().unique().tolist()
        payload_categorias = [{"nome": str(cat).strip()} for cat in categorias_unicas]

        if payload_categorias:
            conexao.execute(
                text("""
                    INSERT INTO core.dim_categorias (nome_categoria)
                    VALUES (:nome)
                    ON CONFLICT (nome_categoria) DO NOTHING;
                """),
                payload_categorias,
            )

        # Mapa em memória: nome_categoria -> id_categoria
        resultado_cats = conexao.execute(
            text("SELECT id_categoria, nome_categoria FROM core.dim_categorias;")
        ).fetchall()
        mapa_categorias = {nome: id_cat for id_cat, nome in resultado_cats}

        # 5. Inserção / Atualização em lote de Produtos (dim_produtos)
        payload_produtos = []
        for _, linha in df.iterrows():
            nome_cat = str(linha["categoria"]).strip()
            payload_produtos.append({
                "sku": str(linha["id_produto"]).strip(),
                "nome": str(linha["produto"]).strip(),
                "id_cat": mapa_categorias.get(nome_cat),
                "preco": float(linha["preco"]),
            })

        if payload_produtos:
            conexao.execute(
                text("""
                    INSERT INTO core.dim_produtos (sku, nome_produto, id_categoria, preco_unitario, estoque_minimo)
                    VALUES (:sku, :nome, :id_cat, :preco, 10)
                    ON CONFLICT (sku) DO UPDATE SET
                        nome_produto = EXCLUDED.nome_produto,
                        id_categoria = EXCLUDED.id_categoria,
                        preco_unitario = EXCLUDED.preco_unitario;
                """),
                payload_produtos,
            )

        # Mapa em memória: sku -> id_produto_banco
        resultado_prods = conexao.execute(
            text("SELECT id_produto, sku FROM core.dim_produtos;")
        ).fetchall()
        mapa_produtos = {sku: id_prod for id_prod, sku in resultado_prods}

        # 6. Inserção em lote na Tabela Fato (fato_estoque) com snapshot sincronizado
        payload_fato = []
        for _, linha in df.iterrows():
            sku_val = str(linha["id_produto"]).strip()
            id_prod_banco = mapa_produtos.get(sku_val)

            if id_prod_banco:
                payload_fato.append({
                    "id_prod": id_prod_banco,
                    "qtd": int(linha["estoque"]),
                    "val_total": float(linha["valor_total"]),
                    "status": linha["status_reposicao"],
                    "data_carga": timestamp_lote,
                })

        if payload_fato:
            conexao.execute(
                text("""
                    INSERT INTO core.fato_estoque 
                    (id_produto, quantidade_disponivel, valor_total_estoque, status_reposicao, data_carga)
                    VALUES (:id_prod, :qtd, :val_total, :status, :data_carga);
                """),
                payload_fato,
            )

    print(f"Carga concluída com sucesso no schema 'core'! ({len(payload_fato)} registros processados em lote).")


if __name__ == "__main__":
    carregar_pipeline()