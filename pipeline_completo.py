import logging
import subprocess
import sys
import time

# Configuração profissional de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def executar_modulo(nome_script, descricao):
    """Executa um módulo em Python como subprocesso e valida o código de saída."""
    logging.info(f"Iniciando: {descricao} ({nome_script})...")
    inicio = time.time()

    # Executa o script usando o mesmo interpretador Python ativo
    resultado = subprocess.run([sys.executable, nome_script], capture_output=False)

    duracao = round(time.time() - inicio, 2)

    if resultado.returncode == 0:
        logging.info(f"Concluído com sucesso: {descricao} em {duracao}s\n")
        return True
    else:
        logging.error(f"Falha crítica ao executar {nome_script} (Código de erro: {resultado.returncode})")
        return False


def orquestrar_pipeline():
    logging.info("=" * 60)
    logging.info("INICIANDO ORQUESTRAÇÃO DO PIPELINE DE DADOS (ETL)")
    logging.info("=" * 60)

    tempo_total_inicio = time.time()

    # Fluxo ordenado de execução
    etapas = [
        ("gerar_dados_brutos.py", "Etapa 1/6: Extração/Simulação de Dados Brutos"),
        ("limpeza_padronizacao.py", "Etapa 2/6: Limpeza e Padronização dos Dados"),
        ("criar_tabelas.py", "Etapa 3/6: Verificação do Schema e Tabelas DDL"),
        ("carregar_dados.py", "Etapa 4/6: Carga e Upsert no PostgreSQL (Neon)"),
        ("gerar_cotacoes_fornecedores.py", "Etapa 5/6: Geração e Carga das Cotações de Fornecedores"),
        ("consultar_banco.py", "Etapa 6/6: Auditoria e Validação Final do Banco"),
    ]

    for script, descricao in etapas:
        sucesso = executar_modulo(script, descricao)
        if not sucesso:
            logging.error("O pipeline foi interrompido devido a um erro na etapa anterior.")
            sys.exit(1)

    tempo_total = round(time.time() - tempo_total_inicio, 2)
    logging.info("=" * 60)
    logging.info(f"PIPELINE EXECUTADO COM SUCESSO DE PONTA A PONTA EM {tempo_total}s")
    logging.info("=" * 60)


if __name__ == "__main__":
    orquestrar_pipeline()