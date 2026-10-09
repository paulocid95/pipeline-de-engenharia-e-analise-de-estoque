"""Passo 6: Geração e Ingestão de Cotações Competitivas (Procurement Analytics).

Este script lê os produtos cadastrados em 'core.dim_produtos' e 'core.fato_estoque',
simula propostas comerciais realistas de múltiplos fornecedores concorrentes
(Fornecedor A, B e C) e grava os dados na tabela 'core.fato_cotacoes' no PostgreSQL (Neon).

Regras de negócio implementadas:
- 2 a 3 propostas de fornecedores distintos por SKU.
- Variação estocástica do preço cotado: entre -15% e +10% do preço de tabela.
- Lote mínimo escalonado por valor agregado (itens caros: 2 a 10 un; itens de giro: 15 a 60 un).
- Lead time operacional: 3 a 14 dias úteis.
- Inserção em lote idempotente sob transação atômica (engine.begin).
"""

from datetime import datetime, timezone
import os
import random
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Configuração e conexão com o banco de dados
load_dotenv()
database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("A variável DATABASE_URL não foi encontrada no arquivo .env.")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(database_url)

FORNECEDORES_HOMOLOGADOS = ["Fornecedor A", "Fornecedor B", "Fornecedor C"]


def carregar_produtos_referencia(conexao):
    """Consulta os produtos ativos e seu preço de referência/estoque mais recente."""
    query = """
        SELECT DISTINCT ON (p.id_produto)
            p.id_produto,
            p.sku,
            p.nome_produto,
            p.preco_unitario,
            f.status_reposicao,
            f.quantidade_disponivel
        FROM core.dim_produtos p
        LEFT JOIN core.fato_estoque f ON p.id_produto = f.id_produto
        ORDER BY p.id_produto, f.data_carga DESC;
    """
    return conexao.execute(text(query)).fetchall()


def simular_cotacoes_produtos(produtos, seed: int = 42) -> list[dict]:
    """Gera o payload de cotações concorrentes para cada produto da base."""
    # Seed opcional para garantir consistência e reprodutibilidade de análises
    if seed is not None:
        random.seed(seed)

    payload_cotacoes = []
    timestamp_atual = datetime.now(timezone.utc)

    for prod in produtos:
        id_produto = prod.id_produto
        preco_base = float(prod.preco_unitario)

        # Sorteia entre 2 a 3 fornecedores concorrentes distintos para o mesmo SKU
        qtd_fornecedores = random.randint(2, 3)
        fornecedores_selecionados = random.sample(FORNECEDORES_HOMOLOGADOS, k=qtd_fornecedores)

        for forn in fornecedores_selecionados:
            # 1. Preço cotado varia entre 85% e 110% do preço de tabela
            fator_variacao = random.uniform(0.85, 1.10)
            preco_cotado = round(preco_base * fator_variacao, 2)

            # 2. Lote mínimo ajustado pelo valor agregado do item
            if preco_base > 1000.0:
                lote_minimo = random.randint(2, 10)
            else:
                lote_minimo = random.randint(15, 60)

            # 3. Prazo de entrega entre 3 e 14 dias úteis
            prazo_dias = random.randint(3, 14)

            payload_cotacoes.append({
                "id_produto": id_produto,
                "fornecedor": forn,
                "preco_cotado": preco_cotado,
                "lote_minimo": lote_minimo,
                "prazo_dias": prazo_dias,
                "data_cotacao": timestamp_atual,
            })

    return payload_cotacoes


def executar_carga_cotacoes() -> None:
    """Executa a transação atômica de limpeza e carga em lote no PostgreSQL Neon."""
    print("=" * 80)
    print(" INICIANDO GERAÇÃO DE COTAÇÕES DE FORNECEDORES (PROCUREMENT ANALYTICS)")
    print("=" * 80)

    with engine.begin() as conexao:
        # 1. Leitura dos produtos
        produtos = carregar_produtos_referencia(conexao)
        total_produtos = len(produtos)
        print(f"[1/3] Produtos identificados na base dimensional: {total_produtos} SKUs")

        if total_produtos == 0:
            print("[ALERTA] Nenhum produto encontrado em core.dim_produtos. Carga abortada.")
            return

        # 2. Simulação das cotações
        payload = simular_cotacoes_produtos(produtos)
        total_cotacoes = len(payload)
        print(f"[2/3] Total de cotações concorrentes geradas: {total_cotacoes} propostas")

        # 3. Limpeza do lote e inserção em lote atômica
        print("[3/3] Gravando cotações em 'core.fato_cotacoes' no PostgreSQL (Neon)...")
        conexao.execute(text("TRUNCATE TABLE core.fato_cotacoes RESTART IDENTITY CASCADE;"))

        insert_query = """
            INSERT INTO core.fato_cotacoes (
                id_produto,
                fornecedor,
                preco_cotado,
                lote_minimo,
                prazo_dias,
                data_cotacao
            ) VALUES (
                :id_produto,
                :fornecedor,
                :preco_cotado,
                :lote_minimo,
                :prazo_dias,
                :data_cotacao
            );
        """
        conexao.execute(text(insert_query), payload)

    print("=" * 80)
    print("[OK] CARGA CONCLUÍDA COM SUCESSO!")
    print(f" -> Total de SKUs cotados : {total_produtos}")
    print(f" -> Cotações inseridas    : {total_cotacoes}")
    print(f" -> Média de propostas/SKU: {total_cotacoes / total_produtos:.2f}")
    print("=" * 80)


if __name__ == "__main__":
    executar_carga_cotacoes()
