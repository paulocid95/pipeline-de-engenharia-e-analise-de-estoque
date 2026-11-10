from sqlalchemy import text

from db import criar_engine

print("Tentando conectar ao PostgreSQL no Neon...")

try:
    engine = criar_engine()
    with engine.connect() as conexao:
        resultado = conexao.execute(text("SELECT version();"))
        print("\nConexão realizada com sucesso!")
        print(f"Versão do Banco: {resultado.fetchone()[0]}")
except Exception as e:
    print(f"\nErro ao conectar: {e}")