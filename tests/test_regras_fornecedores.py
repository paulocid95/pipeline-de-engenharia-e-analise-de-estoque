from datetime import date, timedelta

import pandas as pd
import pytest

from gerar_ocorrencias_fornecedores import simular_ocorrencias
from regras_fornecedores import (
    PESOS,
    avaliar_cotacoes,
    calcular_penalidades,
    classe_por_nota,
    classificar,
    fator_recencia,
    fator_resolucao,
    notas_cotacoes,
    penalidade,
    ranking_fornecedores,
)

HOJE = date(2026, 11, 17)


def ocorrencia(fornecedor="Fornecedor X", tipo="ATRASO", gravidade="MEDIA",
               dias_atras=10, status="RESOLVIDO", dias_para_resolver=3):
    data_oc = HOJE - timedelta(days=dias_atras)
    data_res = data_oc + timedelta(days=dias_para_resolver) if status == "RESOLVIDO" else None
    return {
        "fornecedor": fornecedor, "tipo": tipo, "gravidade": gravidade,
        "data_ocorrencia": data_oc, "status": status, "data_resolucao": data_res,
    }


# ------------------------------------------------------------------------------
# Penalidade de cada ocorrência
# ------------------------------------------------------------------------------
def test_pesos_somam_100_por_cento():
    assert sum(PESOS.values()) == pytest.approx(1.0)


def test_recencia_cai_pela_metade_a_cada_meia_vida():
    assert fator_recencia(0) == pytest.approx(1.0)
    assert fator_recencia(120) == pytest.approx(0.5)
    assert fator_recencia(240) == pytest.approx(0.25)


def test_resolucao_rapida_pesa_menos_que_lenta_e_que_aberta():
    rapida = fator_resolucao(True, 1)
    lenta = fator_resolucao(True, 60)
    aberta = fator_resolucao(False, 10)
    assert rapida < lenta < aberta


def test_problema_aberto_piora_com_o_tempo_ate_o_limite():
    assert fator_resolucao(False, 0) == pytest.approx(1.0)
    assert fator_resolucao(False, 45) == pytest.approx(1.25)
    assert fator_resolucao(False, 90) == pytest.approx(1.5)
    assert fator_resolucao(False, 400) == pytest.approx(1.5)


def test_ocorrencia_fora_da_janela_de_12_meses_nao_conta():
    antiga = HOJE - timedelta(days=400)
    assert penalidade("ATRASO", "ALTA", "RESOLVIDO", antiga, antiga + timedelta(days=2), HOJE) == 0.0


def test_gravidade_aumenta_a_penalidade():
    d = HOJE - timedelta(days=10)
    leve = penalidade("ATRASO", "BAIXA", "ABERTO", d, None, HOJE)
    critica = penalidade("ATRASO", "CRITICA", "ABERTO", d, None, HOJE)
    assert critica > leve * 10


def test_problema_sem_solucao_nao_perde_peso_com_o_tempo():
    recente = penalidade("DEFEITO", "ALTA", "ABERTO", HOJE - timedelta(days=100), None, HOJE)
    resolvido = penalidade("DEFEITO", "ALTA", "RESOLVIDO", HOJE - timedelta(days=100),
                           HOJE - timedelta(days=97), HOJE)
    assert recente > resolvido * 3


# ------------------------------------------------------------------------------
# Notas de preço, prazo e lote
# ------------------------------------------------------------------------------
def test_melhor_oferta_recebe_100_e_as_demais_perdem_pela_distancia():
    cot = pd.DataFrame({
        "id_produto": [1, 1, 1],
        "fornecedor": ["A", "B", "C"],
        "preco_cotado": [100.0, 110.0, 150.0],
        "prazo_dias": [3, 4, 20],
        "lote_minimo": [10, 20, 40],
    })
    notas = notas_cotacoes(cot).set_index("fornecedor")
    assert notas.loc["A", ["nota_preco", "nota_prazo", "nota_lote"]].tolist() == [100, 100, 100]
    assert notas.loc["B", "nota_preco"] == pytest.approx(75)   # 10% acima
    assert notas.loc["B", "nota_prazo"] == pytest.approx(88)   # 1 dia a mais
    assert notas.loc["B", "nota_lote"] == pytest.approx(50)    # lote 2x
    assert notas.loc["C", ["nota_preco", "nota_prazo", "nota_lote"]].tolist() == [0, 0, 0]


def test_produto_com_uma_unica_cotacao_recebe_100():
    cot = pd.DataFrame({"id_produto": [7], "fornecedor": ["A"], "preco_cotado": [50.0],
                        "prazo_dias": [9], "lote_minimo": [30]})
    notas = notas_cotacoes(cot).iloc[0]
    assert (notas["nota_preco"], notas["nota_prazo"], notas["nota_lote"]) == (100, 100, 100)


# ------------------------------------------------------------------------------
# Classificação
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("nota, esperado", [(100, "BOM"), (75, "BOM"), (74.9, "MEDIO"),
                                            (50, "MEDIO"), (49.9, "PERIGOSO"), (0, "PERIGOSO")])
def test_faixas_de_classe(nota, esperado):
    assert classe_por_nota(nota) == esperado


def test_processo_judicial_aberto_classifica_como_perigoso_mesmo_com_nota_alta():
    oc = calcular_penalidades(pd.DataFrame([
        ocorrencia(tipo="JUDICIAL", gravidade="ALTA", dias_atras=45, status="ABERTO"),
    ]), HOJE)
    classe, motivo = classificar(95, oc)
    assert classe == "PERIGOSO"
    assert motivo == "Processo judicial em aberto há 45 dias"


def test_problema_critico_sem_solucao_classifica_como_perigoso():
    oc = calcular_penalidades(pd.DataFrame([
        ocorrencia(tipo="DEFEITO", gravidade="CRITICA", dias_atras=12, status="EM_ANDAMENTO"),
    ]), HOJE)
    classe, motivo = classificar(90, oc)
    assert classe == "PERIGOSO"
    assert "sem solução há 12 dias" in motivo


def test_processo_judicial_ja_resolvido_nao_forca_perigoso():
    oc = calcular_penalidades(pd.DataFrame([
        ocorrencia(tipo="JUDICIAL", gravidade="ALTA", dias_atras=200, dias_para_resolver=60),
    ]), HOJE)
    classe, _ = classificar(80, oc)
    assert classe == "BOM"


def test_motivo_aponta_o_tipo_de_problema_que_mais_pesou():
    oc = calcular_penalidades(pd.DataFrame(
        [ocorrencia(tipo="ATRASO", gravidade="MEDIA", dias_atras=d) for d in (10, 30, 60)]
        + [ocorrencia(tipo="ATRASO", gravidade="MEDIA", dias_atras=5, status="ABERTO")]
        + [ocorrencia(tipo="FALHA_ATENDIMENTO", gravidade="BAIXA", dias_atras=20)]
    ), HOJE)
    _, motivo = classificar(60, oc)
    assert motivo == "Atraso na entrega: 4 ocorrências em 12 meses (1 sem solução)"


def test_fornecedor_sem_ocorrencias_tem_historico_limpo():
    vazio = calcular_penalidades(pd.DataFrame(columns=[
        "fornecedor", "tipo", "gravidade", "data_ocorrencia", "status", "data_resolucao"]), HOJE)
    classe, motivo = classificar(80, vazio)
    assert classe == "BOM"
    assert motivo.startswith("Histórico limpo")


# ------------------------------------------------------------------------------
# Ranking e avaliação de cotações
# ------------------------------------------------------------------------------
def _cotacoes_exemplo():
    return pd.DataFrame({
        "id_produto": [1, 1, 2, 2],
        "fornecedor": ["Fornecedor A", "Fornecedor B", "Fornecedor A", "Fornecedor B"],
        "preco_cotado": [100.0, 105.0, 50.0, 48.0],
        "prazo_dias": [3, 5, 4, 4],
        "lote_minimo": [10, 10, 20, 30],
    })


def test_ranking_combina_os_quatro_fatores_com_os_pesos():
    oc = pd.DataFrame([ocorrencia(fornecedor="Fornecedor B", gravidade="ALTA", dias_atras=5, status="ABERTO")])
    rk = ranking_fornecedores(_cotacoes_exemplo(), oc, HOJE).set_index("fornecedor")
    linha = rk.loc["Fornecedor B"]
    esperado = (PESOS["preco"] * linha["nota_preco"] + PESOS["prazo"] * linha["nota_prazo"]
                + PESOS["lote"] * linha["nota_lote"] + PESOS["confiabilidade"] * linha["nota_confiabilidade"])
    assert linha["nota_final"] == pytest.approx(esperado, abs=0.1)
    assert rk.loc["Fornecedor A", "nota_confiabilidade"] == 100
    assert linha["sem_solucao"] == 1


def test_avaliar_cotacoes_usa_a_confiabilidade_do_fornecedor():
    oc = pd.DataFrame([ocorrencia(fornecedor="Fornecedor B", tipo="JUDICIAL", gravidade="CRITICA",
                                  dias_atras=30, status="ABERTO")])
    rk = ranking_fornecedores(_cotacoes_exemplo(), oc, HOJE)
    cot = avaliar_cotacoes(_cotacoes_exemplo(), rk)
    produto_2 = cot[cot["id_produto"] == 2].set_index("fornecedor")
    # B é mais barato no produto 2, mas o processo judicial derruba a nota da cotação
    assert produto_2.loc["Fornecedor B", "nota_preco"] == 100
    assert produto_2.loc["Fornecedor B", "classe"] == "PERIGOSO"
    assert produto_2.loc["Fornecedor A", "nota_cotacao"] > produto_2.loc["Fornecedor B", "nota_cotacao"]


# ------------------------------------------------------------------------------
# Gerador do histórico
# ------------------------------------------------------------------------------
def test_gerador_e_deterministico_e_respeita_as_regras_da_tabela():
    a = simular_ocorrencias([1, 2, 3], HOJE)
    b = simular_ocorrencias([1, 2, 3], HOJE)
    assert a == b
    for o in a:
        assert (o["status"] == "RESOLVIDO") == (o["data_resolucao"] is not None)
        assert o["data_ocorrencia"] <= HOJE
        if o["data_resolucao"] is not None:
            assert o["data_ocorrencia"] <= o["data_resolucao"] <= HOJE
        if o["tipo"] in ("JUDICIAL", "FALHA_ATENDIMENTO"):
            assert o["id_produto"] is None


def test_gerador_cobre_os_seis_fornecedores_e_o_processo_judicial_do_d():
    oc = pd.DataFrame(simular_ocorrencias([1, 2, 3], HOJE))
    assert sorted(oc["fornecedor"].unique()) == [f"Fornecedor {l}" for l in "ABCDEF"]
    judicial_d = oc[(oc["fornecedor"] == "Fornecedor D") & (oc["tipo"] == "JUDICIAL")]
    assert (judicial_d["status"] == "ABERTO").all() and len(judicial_d) == 1
