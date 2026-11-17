"""Passo 6: Geração e Ingestão de Cotações Competitivas (Procurement Analytics).

Este script lê os produtos cadastrados em 'core.dim_produtos' e 'core.fato_estoque',
simula propostas comerciais realistas de múltiplos fornecedores concorrentes
(Fornecedor A a F) e grava os dados na tabela 'core.fato_cotacoes' no PostgreSQL (Neon).

Regras de negócio implementadas:
- 3 a 4 propostas de fornecedores distintos por SKU.
- Cada fornecedor tem um perfil comercial (faixa de preço, prazo e tamanho de lote).
- Lote mínimo escalonado por valor agregado (itens caros: 2 a 10 un; itens de giro: 15 a 60 un),
  ajustado pelo perfil do fornecedor.
- Inserção em lote idempotente sob transação atômica (engine.begin).
"""

from datetime import datetime, timezone
import random
import sys
from sqlalchemy import text

from db import criar_engine
from regras_fornecedores import FORNECEDORES

# 1. Conexão centralizada (ver db.py)
engine = criar_engine()

FORNECEDORES_HOMOLOGADOS = FORNECEDORES

# Perfil comercial de cada fornecedor: faixa de preço (fator sobre o preço de tabela),
# faixa de prazo em dias úteis e multiplicador do lote mínimo.
PERFIS_COTACAO = {
    "Fornecedor A": {"preco": (0.97, 1.08), "prazo": (2, 6), "lote": 1.2},   # rápido no papel
    "Fornecedor B": {"preco": (0.95, 1.06), "prazo": (3, 7), "lote": 1.0},   # ágil e confiável
    "Fornecedor C": {"preco": (0.88, 0.99), "prazo": (7, 14), "lote": 1.3},  # barato e mais lento
    "Fornecedor D": {"preco": (0.80, 0.90), "prazo": (5, 12), "lote": 1.6},  # o mais barato
    "Fornecedor E": {"preco": (1.04, 1.15), "prazo": (3, 8), "lote": 0.5},   # caro, lotes pequenos
    "Fornecedor F": {"preco": (0.98, 1.10), "prazo": (6, 12), "lote": 1.1},  # intermediário
}


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

        # Sorteia entre 3 e 4 fornecedores concorrentes distintos para o mesmo SKU
        qtd_fornecedores = random.randint(3, 4)
        fornecedores_selecionados = random.sample(FORNECEDORES_HOMOLOGADOS, k=qtd_fornecedores)

        for forn in fornecedores_selecionados:
            perfil = PERFIS_COTACAO[forn]

            # 1. Preço cotado conforme a faixa do perfil do fornecedor
            preco_cotado = round(preco_base * random.uniform(*perfil["preco"]), 2)

            # 2. Lote mínimo pelo valor agregado do item, ajustado pelo perfil
            if preco_base > 1000.0:
                lote_base = random.randint(2, 10)
            else:
                lote_base = random.randint(15, 60)
            lote_minimo = max(1, round(lote_base * perfil["lote"]))

            # 3. Prazo de entrega na faixa do perfil (dias úteis)
            prazo_dias = random.randint(*perfil["prazo"])

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
            print("[ERRO] Nenhum produto encontrado em core.dim_produtos. Carga abortada.")
            sys.exit(1)

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
