"""Regras do ranking de fornecedores: nota única (0-100), classificação e motivo do alerta.

A nota combina quatro fatores:
- Preço (30%), prazo (20%) e lote mínimo (10%), comparando cada cotação com as
  concorrentes do mesmo produto;
- Confiabilidade (40%), que parte de 100 e perde pontos a cada ocorrência no histórico.

Classes: Bom (75+), Médio (50-74) e Perigoso (abaixo de 50). Um processo judicial ou
um problema crítico sem solução classifica como Perigoso direto, seja qual for a nota.
"""

from datetime import date

import pandas as pd

FORNECEDORES = [f"Fornecedor {letra}" for letra in "ABCDEF"]

PESOS = {"preco": 0.30, "prazo": 0.20, "lote": 0.10, "confiabilidade": 0.40}

LIMITE_BOM = 75
LIMITE_MEDIO = 50

JANELA_DIAS = 365       # só ocorrências dos últimos 12 meses entram na nota
MEIA_VIDA_DIAS = 120    # uma ocorrência resolvida perde metade do peso a cada ~4 meses

PENALIDADE_GRAVIDADE = {"BAIXA": 2.0, "MEDIA": 5.0, "ALTA": 10.0, "CRITICA": 25.0}
PESO_TIPO = {"JUDICIAL": 1.5, "FALHA_ATENDIMENTO": 0.7}  # demais tipos: 1.0

ROTULOS_TIPO = {
    "ATRASO": "Atraso na entrega",
    "DEFEITO": "Item com defeito ou quebrado",
    "ITEM_ERRADO_FALTANDO": "Item errado ou faltando",
    "JUDICIAL": "Processo judicial",
    "DIVERGENCIA_PRECO_NF": "Divergência de preço ou nota fiscal",
    "FALHA_ATENDIMENTO": "Falha de atendimento",
    "AVARIA_TRANSPORTE": "Avaria no transporte",
}
ROTULOS_STATUS = {"RESOLVIDO": "Resolvido", "EM_ANDAMENTO": "Em andamento", "ABERTO": "Em aberto"}
ROTULOS_GRAVIDADE = {"BAIXA": "Baixa", "MEDIA": "Média", "ALTA": "Alta", "CRITICA": "Crítica"}

ROTULO_CLASSE = {"BOM": "Bom", "MEDIO": "Médio", "PERIGOSO": "Perigoso"}
ICONE_CLASSE = {"BOM": "🟢", "MEDIO": "🟡", "PERIGOSO": "🔴"}


# ------------------------------------------------------------------------------
# Confiabilidade (histórico de ocorrências)
# ------------------------------------------------------------------------------
def fator_recencia(idade_dias: int) -> float:
    """Peso de uma ocorrência resolvida conforme a idade: 1.0 hoje, 0.5 após MEIA_VIDA_DIAS."""
    return 0.5 ** (max(idade_dias, 0) / MEIA_VIDA_DIAS)


def fator_resolucao(resolvido: bool, dias: int) -> float:
    """Multiplicador pela situação da ocorrência.

    Resolvida: de 0.35 (resolvida no mesmo dia) até 0.80 (60 dias ou mais para resolver).
    Sem solução: de 1.0 até 1.5 conforme o tempo em aberto (90 dias ou mais).
    """
    if resolvido:
        return 0.35 + 0.45 * min(max(dias, 0), 60) / 60
    return 1.0 + 0.5 * min(max(dias, 0), 90) / 90


def penalidade(
    tipo: str,
    gravidade: str,
    status: str,
    data_ocorrencia: date,
    data_resolucao: date | None,
    data_ref: date,
) -> float:
    """Pontos que uma ocorrência tira da confiabilidade do fornecedor."""
    idade = (data_ref - data_ocorrencia).days
    if idade > JANELA_DIAS or idade < 0:
        return 0.0

    base = PENALIDADE_GRAVIDADE[gravidade] * PESO_TIPO.get(tipo, 1.0)
    if status == "RESOLVIDO":
        dias_para_resolver = (data_resolucao - data_ocorrencia).days
        return base * fator_resolucao(True, dias_para_resolver) * fator_recencia(idade)
    # Problema sem solução continua atual: não perde peso com o tempo, só piora
    return base * fator_resolucao(False, idade)


def _como_data(valor) -> date | None:
    if valor is None or pd.isna(valor):
        return None
    return pd.Timestamp(valor).date()


def calcular_penalidades(df_ocorrencias: pd.DataFrame, data_ref: date) -> pd.DataFrame:
    """Devolve as ocorrências com as colunas penalidade, dias_para_resolver e dias_em_aberto."""
    df = df_ocorrencias.copy()
    if df.empty:
        return df.assign(penalidade=[], dias_para_resolver=[], dias_em_aberto=[])

    datas_oc = df["data_ocorrencia"].map(_como_data)
    datas_res = df["data_resolucao"].map(_como_data)
    resolvido = df["status"] == "RESOLVIDO"

    df["penalidade"] = [
        penalidade(t, g, s, d_oc, d_res, data_ref)
        for t, g, s, d_oc, d_res in zip(df["tipo"], df["gravidade"], df["status"], datas_oc, datas_res)
    ]
    df["dias_para_resolver"] = [
        (d_res - d_oc).days if ok else None for ok, d_oc, d_res in zip(resolvido, datas_oc, datas_res)
    ]
    df["dias_em_aberto"] = [
        None if ok else (data_ref - d_oc).days for ok, d_oc in zip(resolvido, datas_oc)
    ]
    return df


# ------------------------------------------------------------------------------
# Preço, prazo e lote (comparação entre cotações do mesmo produto)
# ------------------------------------------------------------------------------
# Quanto cada fator perde por ficar longe da melhor oferta do mesmo produto
PONTOS_POR_PCT_PRECO = 2.5   # preço 10% acima do melhor -> 75; 40% acima -> 0
PONTOS_POR_DIA_PRAZO = 12.0  # 1 dia a mais que o mais rápido -> 88; 8+ dias -> 0
PONTOS_POR_PCT_LOTE = 0.5    # lote 2x o menor -> 50; 3x -> 0


def _limitar(serie: pd.Series) -> pd.Series:
    return serie.clip(lower=0.0, upper=100.0)


def notas_cotacoes(df_cotacoes: pd.DataFrame, chave_produto: str = "id_produto") -> pd.DataFrame:
    """Adiciona nota_preco, nota_prazo e nota_lote a cada cotação.

    A melhor oferta do produto em cada fator recebe 100; as demais perdem pontos
    proporcionalmente à distância dela.
    """
    df = df_cotacoes.copy()
    grupos = df.groupby(chave_produto)

    melhor_preco = grupos["preco_cotado"].transform("min")
    pct_acima = (df["preco_cotado"] / melhor_preco - 1) * 100
    df["nota_preco"] = _limitar(100 - PONTOS_POR_PCT_PRECO * pct_acima)

    dias_a_mais = df["prazo_dias"] - grupos["prazo_dias"].transform("min")
    df["nota_prazo"] = _limitar(100 - PONTOS_POR_DIA_PRAZO * dias_a_mais)

    menor_lote = grupos["lote_minimo"].transform("min")
    pct_lote = (df["lote_minimo"] / menor_lote - 1) * 100
    df["nota_lote"] = _limitar(100 - PONTOS_POR_PCT_LOTE * pct_lote)
    return df


# ------------------------------------------------------------------------------
# Classificação e motivo do alerta
# ------------------------------------------------------------------------------
def classe_por_nota(nota: float) -> str:
    if nota >= LIMITE_BOM:
        return "BOM"
    if nota >= LIMITE_MEDIO:
        return "MEDIO"
    return "PERIGOSO"


def classificar(nota: float, ocorrencias_fornecedor: pd.DataFrame) -> tuple[str, str]:
    """Devolve (classe, motivo principal) de um fornecedor.

    `ocorrencias_fornecedor` deve vir de calcular_penalidades (com penalidade e dias_em_aberto).
    """
    df = ocorrencias_fornecedor
    if not df.empty:
        sem_solucao = df[df["status"] != "RESOLVIDO"]
        graves = sem_solucao[(sem_solucao["tipo"] == "JUDICIAL") | (sem_solucao["gravidade"] == "CRITICA")]
        if not graves.empty:
            mais_antigo = graves.sort_values("dias_em_aberto", ascending=False).iloc[0]
            dias = int(mais_antigo["dias_em_aberto"])
            if mais_antigo["tipo"] == "JUDICIAL":
                return "PERIGOSO", f"Processo judicial em aberto há {dias} dias"
            rotulo = ROTULOS_TIPO[mais_antigo["tipo"]]
            return "PERIGOSO", f"{rotulo} crítico sem solução há {dias} dias"

    classe = classe_por_nota(nota)
    no_periodo = df[df["penalidade"] > 0] if not df.empty else df
    if no_periodo.empty or no_periodo["penalidade"].sum() < 3:
        return classe, "Histórico limpo: poucos problemas, resolvidos rapidamente"

    por_tipo = no_periodo.groupby("tipo")["penalidade"].sum().sort_values(ascending=False)
    tipo_principal = por_tipo.index[0]
    do_tipo = no_periodo[no_periodo["tipo"] == tipo_principal]
    qtd = len(do_tipo)
    abertas = int((do_tipo["status"] != "RESOLVIDO").sum())
    motivo = f"{ROTULOS_TIPO[tipo_principal]}: {qtd} {'ocorrência' if qtd == 1 else 'ocorrências'} em 12 meses"
    if abertas:
        motivo += f" ({abertas} sem solução)"
    return classe, motivo


# ------------------------------------------------------------------------------
# Ranking final
# ------------------------------------------------------------------------------
def ranking_fornecedores(
    df_cotacoes: pd.DataFrame,
    df_ocorrencias: pd.DataFrame,
    data_ref: date,
    chave_produto: str = "id_produto",
    coluna_fornecedor: str = "fornecedor",
) -> pd.DataFrame:
    """Uma linha por fornecedor, com as notas de cada fator, a nota final, a classe e o motivo."""
    cot = notas_cotacoes(df_cotacoes, chave_produto)
    medias = cot.groupby(coluna_fornecedor)[["nota_preco", "nota_prazo", "nota_lote"]].mean()

    oc = calcular_penalidades(df_ocorrencias, data_ref)
    fornecedores = sorted(set(FORNECEDORES) | set(medias.index) | set(oc.get("fornecedor", [])))

    linhas = []
    for forn in fornecedores:
        oc_forn = oc[oc["fornecedor"] == forn] if not oc.empty else oc
        confiabilidade = max(0.0, 100.0 - float(oc_forn["penalidade"].sum())) if not oc_forn.empty else 100.0
        # Fornecedor sem cotações recebe nota neutra (50) nos fatores comerciais
        preco = float(medias["nota_preco"].get(forn, 50.0))
        prazo = float(medias["nota_prazo"].get(forn, 50.0))
        lote = float(medias["nota_lote"].get(forn, 50.0))
        nota = (
            PESOS["preco"] * preco
            + PESOS["prazo"] * prazo
            + PESOS["lote"] * lote
            + PESOS["confiabilidade"] * confiabilidade
        )
        classe, motivo = classificar(nota, oc_forn)

        no_periodo = oc_forn[oc_forn["penalidade"] > 0] if not oc_forn.empty else oc_forn
        resolvidas = no_periodo[no_periodo["status"] == "RESOLVIDO"] if not no_periodo.empty else no_periodo
        linhas.append({
            "fornecedor": forn,
            "nota_preco": round(preco, 1),
            "nota_prazo": round(prazo, 1),
            "nota_lote": round(lote, 1),
            "nota_confiabilidade": round(confiabilidade, 1),
            "nota_final": round(nota, 1),
            "classe": classe,
            "motivo": motivo,
            "ocorrencias_12m": int(len(no_periodo)),
            "sem_solucao": int((no_periodo["status"] != "RESOLVIDO").sum()) if not no_periodo.empty else 0,
            "dias_medios_resolucao": (
                round(float(resolvidas["dias_para_resolver"].mean()), 1) if not resolvidas.empty else None
            ),
        })

    return (
        pd.DataFrame(linhas)
        .sort_values("nota_final", ascending=False)
        .reset_index(drop=True)
    )


def avaliar_cotacoes(
    df_cotacoes: pd.DataFrame,
    df_ranking: pd.DataFrame,
    chave_produto: str = "id_produto",
    coluna_fornecedor: str = "fornecedor",
) -> pd.DataFrame:
    """Nota de cada cotação: preço/prazo/lote da própria proposta + confiabilidade do fornecedor."""
    cot = notas_cotacoes(df_cotacoes, chave_produto)
    info = df_ranking.set_index("fornecedor")[["nota_confiabilidade", "classe", "motivo", "nota_final"]]
    cot = cot.join(info, on=coluna_fornecedor)
    cot["nota_cotacao"] = (
        PESOS["preco"] * cot["nota_preco"]
        + PESOS["prazo"] * cot["nota_prazo"]
        + PESOS["lote"] * cot["nota_lote"]
        + PESOS["confiabilidade"] * cot["nota_confiabilidade"].fillna(100.0)
    ).round(1)
    return cot
