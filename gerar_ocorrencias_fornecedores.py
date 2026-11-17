"""Passo 7: Geração do Histórico de Ocorrências com Fornecedores (Ranking & Risco).

Simula 12 meses de problemas reais de suprimentos (atrasos, defeitos, itens errados,
processos judiciais, divergências de nota fiscal, falhas de atendimento e avarias no
transporte) e grava em 'core.fato_ocorrencias' no PostgreSQL (Neon).

Cada fornecedor segue um perfil de comportamento, para o ranking mostrar as três classes:
- A: atrasa com frequência, mas resolve rápido          -> Médio
- B: ágil e confiável                                   -> Bom
- C: barato, com problemas pontuais de qualidade        -> Médio
- D: o mais barato, com defeitos e processo judicial     -> Perigoso
- E: mais caro e quase sem problemas                    -> Bom
- F: muitos problemas no passado, melhorou recentemente -> Médio

A geração usa semente fixa: rodar de novo produz o mesmo histórico (relativo à data de hoje).
"""

from datetime import date, timedelta
import random
import sys

from sqlalchemy import text

from db import criar_engine
from regras_fornecedores import ROTULOS_TIPO

# Tipos de problema que não se referem a um produto específico
TIPOS_SEM_PRODUTO = {"JUDICIAL", "FALHA_ATENDIMENTO"}

# Dias para resolver, por velocidade de resolução
FAIXAS_RESOLUCAO = {"rapida": (1, 5), "media": (7, 20), "lenta": (25, 70)}

# Cada item: (tipo, gravidade, quantidade, (idade mínima, idade máxima) em dias, resolução)
# resolução: "rapida" | "media" | "lenta" (resolvidas) | "andamento" | "aberto" (sem solução)
PERFIS_OCORRENCIAS = {
    "Fornecedor A": [
        ("ATRASO", "ALTA", 4, (20, 300), "media"),
        ("ATRASO", "MEDIA", 6, (15, 330), "media"),
        ("ATRASO", "BAIXA", 2, (10, 300), "rapida"),
        ("ITEM_ERRADO_FALTANDO", "MEDIA", 2, (30, 250), "media"),
        ("FALHA_ATENDIMENTO", "BAIXA", 1, (40, 200), "rapida"),
        ("ATRASO", "ALTA", 1, (5, 20), "andamento"),
    ],
    "Fornecedor B": [
        ("ATRASO", "BAIXA", 2, (30, 320), "rapida"),
        ("AVARIA_TRANSPORTE", "BAIXA", 1, (60, 280), "rapida"),
        ("DIVERGENCIA_PRECO_NF", "BAIXA", 1, (90, 340), "rapida"),
    ],
    "Fornecedor C": [
        ("DEFEITO", "MEDIA", 3, (30, 330), "media"),
        ("ITEM_ERRADO_FALTANDO", "MEDIA", 3, (20, 300), "media"),
        ("DIVERGENCIA_PRECO_NF", "MEDIA", 2, (40, 260), "media"),
        ("DEFEITO", "ALTA", 1, (10, 40), "andamento"),
    ],
    "Fornecedor D": [
        ("JUDICIAL", "CRITICA", 1, (40, 50), "aberto"),
        ("DEFEITO", "ALTA", 5, (20, 330), "lenta"),
        ("AVARIA_TRANSPORTE", "MEDIA", 3, (15, 280), "media"),
        ("DIVERGENCIA_PRECO_NF", "ALTA", 2, (30, 240), "lenta"),
        ("FALHA_ATENDIMENTO", "MEDIA", 2, (5, 60), "aberto"),
        ("FALHA_ATENDIMENTO", "MEDIA", 1, (5, 30), "andamento"),
    ],
    "Fornecedor E": [
        ("DIVERGENCIA_PRECO_NF", "BAIXA", 1, (60, 300), "rapida"),
        ("ATRASO", "BAIXA", 1, (100, 340), "rapida"),
    ],
    "Fornecedor F": [
        # Fase ruim, há 6 a 11 meses
        ("DEFEITO", "ALTA", 3, (180, 330), "lenta"),
        ("JUDICIAL", "ALTA", 1, (240, 300), "lenta"),
        ("FALHA_ATENDIMENTO", "MEDIA", 3, (180, 330), "media"),
        ("ATRASO", "MEDIA", 3, (180, 330), "media"),
        # Fase recente, bem melhor
        ("ATRASO", "BAIXA", 1, (20, 120), "rapida"),
    ],
}


def _descricao(tipo: str, rng: random.Random) -> str:
    modelos = {
        "ATRASO": lambda: f"Entrega realizada {rng.randint(2, 12)} dias após o prazo combinado",
        "DEFEITO": lambda: f"{rng.randint(1, 15)} unidade(s) com defeito ou quebradas no lote recebido",
        "ITEM_ERRADO_FALTANDO": lambda: rng.choice([
            f"Pedido entregue com {rng.randint(1, 10)} unidade(s) faltando",
            "Modelo diferente do pedido entregue no lote",
        ]),
        "JUDICIAL": lambda: rng.choice([
            "Ação judicial por quebra de contrato de fornecimento",
            "Processo por cobrança indevida e descumprimento contratual",
        ]),
        "DIVERGENCIA_PRECO_NF": lambda: f"Nota fiscal {rng.randint(3, 18)}% acima do valor da cotação aprovada",
        "FALHA_ATENDIMENTO": lambda: f"Sem retorno do atendimento por {rng.randint(3, 15)} dias",
        "AVARIA_TRANSPORTE": lambda: f"Carga avariada no frete: {rng.randint(1, 8)} volume(s) danificado(s)",
    }
    return modelos.get(tipo, lambda: ROTULOS_TIPO[tipo])()


def simular_ocorrencias(ids_produtos: list[int], data_ref: date, seed: int = 42) -> list[dict]:
    """Gera o histórico de ocorrências de todos os fornecedores, relativo a data_ref."""
    rng = random.Random(seed)
    ocorrencias = []

    for fornecedor, itens in PERFIS_OCORRENCIAS.items():
        for tipo, gravidade, quantidade, (idade_min, idade_max), resolucao in itens:
            for _ in range(quantidade):
                data_oc = data_ref - timedelta(days=rng.randint(idade_min, idade_max))

                if resolucao in FAIXAS_RESOLUCAO:
                    data_res = data_oc + timedelta(days=rng.randint(*FAIXAS_RESOLUCAO[resolucao]))
                    if data_res > data_ref:
                        # Ainda não deu tempo de resolver
                        status, data_res = "EM_ANDAMENTO", None
                    else:
                        status = "RESOLVIDO"
                else:
                    status = "EM_ANDAMENTO" if resolucao == "andamento" else "ABERTO"
                    data_res = None

                id_produto = None
                if tipo not in TIPOS_SEM_PRODUTO and ids_produtos:
                    id_produto = rng.choice(ids_produtos)

                ocorrencias.append({
                    "fornecedor": fornecedor,
                    "id_produto": id_produto,
                    "tipo": tipo,
                    "gravidade": gravidade,
                    "data_ocorrencia": data_oc,
                    "status": status,
                    "data_resolucao": data_res,
                    "descricao": _descricao(tipo, rng),
                })

    return sorted(ocorrencias, key=lambda o: o["data_ocorrencia"])


def executar_carga_ocorrencias() -> None:
    """Gera o histórico e substitui o conteúdo de core.fato_ocorrencias em uma transação."""
    print("=" * 80)
    print(" GERAÇÃO DO HISTÓRICO DE OCORRÊNCIAS COM FORNECEDORES (RANKING & RISCO)")
    print("=" * 80)

    engine = criar_engine()
    with engine.begin() as conexao:
        ids_produtos = [linha[0] for linha in conexao.execute(
            text("SELECT id_produto FROM core.dim_produtos ORDER BY id_produto;")
        )]
        if not ids_produtos:
            print("[ERRO] Nenhum produto encontrado em core.dim_produtos. Carga abortada.")
            sys.exit(1)

        payload = simular_ocorrencias(ids_produtos, date.today())
        print(f"[1/2] Ocorrências simuladas (12 meses): {len(payload)}")

        print("[2/2] Gravando em 'core.fato_ocorrencias' no PostgreSQL (Neon)...")
        conexao.execute(text("TRUNCATE TABLE core.fato_ocorrencias RESTART IDENTITY;"))
        conexao.execute(
            text("""
                INSERT INTO core.fato_ocorrencias
                    (fornecedor, id_produto, tipo, gravidade, data_ocorrencia, status, data_resolucao, descricao)
                VALUES
                    (:fornecedor, :id_produto, :tipo, :gravidade, :data_ocorrencia, :status, :data_resolucao, :descricao);
            """),
            payload,
        )

    sem_solucao = sum(1 for o in payload if o["status"] != "RESOLVIDO")
    print("=" * 80)
    print(f"[OK] {len(payload)} ocorrências gravadas ({sem_solucao} sem solução).")
    print("=" * 80)


if __name__ == "__main__":
    executar_carga_ocorrencias()
