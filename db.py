"""Conexão centralizada com o PostgreSQL (Neon) para todos os scripts do projeto."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


def normalizar_url_banco(url: str) -> str:
    """Força o driver psycopg2 na URL do banco.

    O SQLAlchemy 2.1+ usa o driver psycopg (v3) por padrão em URLs 'postgresql://'.
    O projeto usa o psycopg2, então o driver é declarado explicitamente.
    """
    if not url:
        return ""
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def obter_database_url() -> str:
    """Lê a DATABASE_URL do ambiente (.env) e falha com mensagem clara se não existir."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("A variável DATABASE_URL não foi encontrada no arquivo .env.")
    return normalizar_url_banco(database_url)


def criar_engine(**kwargs) -> Engine:
    """Cria a engine do SQLAlchemy com pre-ping para lidar com o Neon serverless."""
    kwargs.setdefault("pool_pre_ping", True)
    return create_engine(obter_database_url(), **kwargs)
