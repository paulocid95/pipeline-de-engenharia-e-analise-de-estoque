import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Carrega as variáveis de ambiente do arquivo .env
load_dotenv()
database_url = os.getenv("DATABASE_URL")

# Compatibilidade de protocolo com SQLAlchemy
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Cria o pool de conexão do SQLAlchemy
engine = create_engine(database_url)

# 2. Definição do DDL (Estrutura e integridade do banco)
ddl_query = """
-- Cria o schema dedicado para a aplicação
CREATE SCHEMA IF NOT EXISTS core;

-- Tabela de Categorias (Dimensão)
CREATE TABLE IF NOT EXISTS core.dim_categorias (
    id_categoria INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_categoria VARCHAR(100) NOT NULL UNIQUE
);

-- Tabela de Produtos (Dimensão de cadastro)
CREATE TABLE IF NOT EXISTS core.dim_produtos (
    id_produto INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    nome_produto VARCHAR(255) NOT NULL,
    id_categoria INT REFERENCES core.dim_categorias(id_categoria) ON DELETE SET NULL,
    preco_unitario NUMERIC(10, 2) NOT NULL CHECK (preco_unitario >= 0),
    estoque_minimo INT NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0)
);

-- Tabela Fato: Histórico e snapshots do estoque
CREATE TABLE IF NOT EXISTS core.fato_estoque (
    id_registro BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_carga TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    id_produto INT NOT NULL REFERENCES core.dim_produtos(id_produto) ON DELETE CASCADE,
    quantidade_disponivel INT NOT NULL CHECK (quantidade_disponivel >= 0),
    valor_total_estoque NUMERIC(14, 2) NOT NULL CHECK (valor_total_estoque >= 0),
    status_reposicao VARCHAR(20) NOT NULL CHECK (status_reposicao IN ('NORMAL', 'ALERTA', 'CRITICO', 'EXCESSO'))
);

-- Tabela Fato: Cotações de Fornecedores (Procurement Analytics)
CREATE TABLE IF NOT EXISTS core.fato_cotacoes (
    id_cotacao SERIAL PRIMARY KEY,
    id_produto INT NOT NULL REFERENCES core.dim_produtos(id_produto) ON DELETE CASCADE,
    fornecedor VARCHAR(50) NOT NULL,
    preco_cotado NUMERIC(10, 2) NOT NULL CHECK (preco_cotado >= 0),
    lote_minimo INT NOT NULL DEFAULT 1 CHECK (lote_minimo >= 1),
    prazo_dias INT NOT NULL DEFAULT 5 CHECK (prazo_dias >= 0),
    data_cotacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Criação de índices estratégicos para acelerar consultas e filtros
CREATE INDEX IF NOT EXISTS idx_fato_data_carga ON core.fato_estoque (data_carga DESC);
CREATE INDEX IF NOT EXISTS idx_fato_status ON core.fato_estoque (status_reposicao);
CREATE INDEX IF NOT EXISTS idx_produtos_sku ON core.dim_produtos (sku);
CREATE INDEX IF NOT EXISTS idx_cotacoes_produto ON core.fato_cotacoes (id_produto);
CREATE INDEX IF NOT EXISTS idx_cotacoes_fornecedor ON core.fato_cotacoes (fornecedor);
CREATE INDEX IF NOT EXISTS idx_cotacoes_data ON core.fato_cotacoes (data_cotacao DESC);
"""

def provisionar_banco():
    print("Provisionando schema e tabelas no PostgreSQL (Neon)...")
    try:
        # engine.begin() abre a transação, executa e dá COMMIT automaticamente
        with engine.begin() as conexao:
            conexao.execute(text(ddl_query))
        print("Schema 'core', tabelas dimensionais, tabela fato e índices criados com sucesso!")
    except Exception as e:
        print(f"Erro ao provisionar banco de dados: {e}")

if __name__ == "__main__":
    provisionar_banco()