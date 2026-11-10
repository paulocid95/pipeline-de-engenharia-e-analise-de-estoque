"""Módulo de DDL: Criação da Tabela Fato de Cotações (Procurement Analytics).

Este script provisiona no PostgreSQL (Neon) a tabela 'core.fato_cotacoes' para
armazenar cotações concorrentes de fornecedores, viabilizando análises de
otimização de custos de aquisição e saving em compras.
"""

from sqlalchemy import text

from db import criar_engine

# 1. Conexão centralizada (ver db.py)
engine = criar_engine()

# 2. Definição do DDL da Fato Cotações
ddl_fato_cotacoes = """
-- Criação da tabela fato de cotações para Procurement Analytics
CREATE TABLE IF NOT EXISTS core.fato_cotacoes (
    id_cotacao SERIAL PRIMARY KEY,
    id_produto INT NOT NULL REFERENCES core.dim_produtos(id_produto) ON DELETE CASCADE,
    fornecedor VARCHAR(50) NOT NULL,
    preco_cotado NUMERIC(10, 2) NOT NULL CHECK (preco_cotado >= 0),
    lote_minimo INT NOT NULL DEFAULT 1 CHECK (lote_minimo >= 1),
    prazo_dias INT NOT NULL DEFAULT 5 CHECK (prazo_dias >= 0),
    data_cotacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Índices estratégicos para acelerar consultas analíticas e junções com a dimensão
CREATE INDEX IF NOT EXISTS idx_cotacoes_produto ON core.fato_cotacoes (id_produto);
CREATE INDEX IF NOT EXISTS idx_cotacoes_fornecedor ON core.fato_cotacoes (fornecedor);
CREATE INDEX IF NOT EXISTS idx_cotacoes_data ON core.fato_cotacoes (data_cotacao DESC);
"""


def criar_tabela_cotacoes() -> None:
    """Executa o DDL de provisionamento da tabela fato_cotacoes no schema 'core'."""
    print("Provisionando tabela 'core.fato_cotacoes' no PostgreSQL (Neon)...")
    try:
        with engine.begin() as conexao:
            conexao.execute(text(ddl_fato_cotacoes))
        print("[OK] Tabela 'core.fato_cotacoes' e indices criados com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha ao criar tabela 'core.fato_cotacoes': {e}")
        raise


if __name__ == "__main__":
    criar_tabela_cotacoes()
