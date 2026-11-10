"""Conexão do dashboard com o PostgreSQL (Neon) e consultas analíticas com cache."""

import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from db import normalizar_url_banco
from regras_estoque import classificar_status

load_dotenv()
try:
    database_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))
except Exception:
    database_url = os.getenv("DATABASE_URL")


@st.cache_resource
def obter_conexao():
    """Cria e reutiliza o pool de conexões do SQLAlchemy com o banco de dados Neon/Postgres com pre-ping e keepalive."""
    if not database_url:
        return None
    url_otimizada = normalizar_url_banco(database_url)
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 180,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }
    try:
        return create_engine(url_otimizada, **engine_kwargs)
    except Exception:
        # Fallback para a URL original com pre-ping e pool_recycle habilitados
        try:
            return create_engine(database_url, pool_pre_ping=True, pool_recycle=180)
        except Exception:
            try:
                return create_engine(database_url)
            except Exception:
                return None



def executar_query_com_retry(query_str: str, max_tentativas: int = 3) -> pd.DataFrame:
    """Executa consultas SQL com mecanismo de retry automático contra oscilações e quedas de conexão do Neon."""
    engine = obter_conexao()
    if engine is None:
        raise ConnectionError("Nenhuma conexão de banco configurada ou disponível.")
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            return pd.read_sql(text(query_str), engine)
        except Exception as e:
            ultimo_erro = e
            # Em caso de SSL closed ou timeout, descarta conexões mortas do pool
            try:
                engine.dispose()
            except Exception:
                pass
            if tentativa < max_tentativas:
                time.sleep(0.5 * tentativa)
    raise ultimo_erro


# ==============================================================================
# 3. CONSULTA ANALÍTICA COM CACHE E ENRIQUECIMENTO DIMENSIONAL
# ==============================================================================
@st.cache_data(ttl=300)
def carregar_dados_analiticos() -> pd.DataFrame:
    """Consulta analítica no PostgreSQL (traz apenas o snapshot mais recente por SKU).
    
    Inclui dimensões de produto, categoria e fornecedor com deduplicação via DISTINCT ON.
    """
    query = """
        SELECT DISTINCT ON (p.sku)
            p.sku,
            p.nome_produto,
            c.nome_categoria,
            COALESCE(p.fornecedor, 'Não Informado') AS fornecedor,
            p.preco_unitario,
            f.quantidade_disponivel,
            f.valor_total_estoque,
            f.status_reposicao,
            f.data_carga
        FROM core.fato_estoque f
        JOIN core.dim_produtos p ON f.id_produto = p.id_produto
        LEFT JOIN core.dim_categorias c ON p.id_categoria = c.id_categoria
        ORDER BY p.sku, f.data_carga DESC;
    """
    try:
        df_raw = executar_query_com_retry(query)
    except Exception as e:
        # Fallback de contingência caso o Neon esteja momentaneamente reiniciando
        caminho_csv = Path("dados_processados") / "estoque_consolidado_limpo.csv"
        if caminho_csv.exists():
            df_csv = pd.read_csv(caminho_csv)
            df_raw = pd.DataFrame({
                "sku": df_csv["id_produto"],
                "nome_produto": df_csv["produto"],
                "nome_categoria": df_csv["categoria"],
                "fornecedor": df_csv["fornecedor"],
                "preco_unitario": df_csv["preco"],
                "quantidade_disponivel": df_csv["estoque"],
                "valor_total_estoque": df_csv["preco"] * df_csv["estoque"],
                "status_reposicao": df_csv["estoque"].apply(classificar_status),
                "data_carga": pd.Timestamp.now(),
            })
            st.warning("⚠️ Conexão com o banco Neon em reinicialização rápida. Exibindo dados do snapshot local de contingência.")
        else:
            raise e

    # Fallback de integridade: se algum fornecedor estiver ausente, enriquece com a base consolidada
    if df_raw["fornecedor"].isna().any() or (df_raw["fornecedor"] == "Não Informado").any():
        caminho_csv = Path("dados_processados") / "estoque_consolidado_limpo.csv"
        if caminho_csv.exists():
            df_csv = pd.read_csv(caminho_csv)
            mapa_forn = dict(zip(df_csv["id_produto"], df_csv["fornecedor"]))
            df_raw["fornecedor"] = df_raw["fornecedor"].replace("Não Informado", pd.NA).fillna(df_raw["sku"].map(mapa_forn)).fillna("Não Informado")

    return df_raw.sort_values(by="valor_total_estoque", ascending=False)


@st.cache_data(ttl=300)
def carregar_dados_cotacoes() -> pd.DataFrame:
    """Consulta analítica de cotações concorrentes unida às dimensões e status atual."""
    query = """
        SELECT
            c.id_cotacao,
            p.sku,
            p.nome_produto,
            cat.nome_categoria,
            p.preco_unitario AS preco_referencia,
            c.fornecedor AS fornecedor_cotacao,
            c.preco_cotado,
            c.lote_minimo,
            c.prazo_dias,
            c.data_cotacao,
            f.status_reposicao,
            f.quantidade_disponivel
        FROM core.fato_cotacoes c
        JOIN core.dim_produtos p ON c.id_produto = p.id_produto
        LEFT JOIN core.dim_categorias cat ON p.id_categoria = cat.id_categoria
        LEFT JOIN (
            SELECT DISTINCT ON (id_produto)
                id_produto,
                status_reposicao,
                quantidade_disponivel,
                data_carga
            FROM core.fato_estoque
            ORDER BY id_produto, data_carga DESC
        ) f ON p.id_produto = f.id_produto
        ORDER BY p.sku, c.preco_cotado ASC;
    """
    try:
        return executar_query_com_retry(query)
    except Exception:
        return pd.DataFrame(columns=[
            "id_cotacao", "sku", "nome_produto", "nome_categoria", "preco_referencia",
            "fornecedor_cotacao", "preco_cotado", "lote_minimo", "prazo_dias",
            "data_cotacao", "status_reposicao", "quantidade_disponivel"
        ])
