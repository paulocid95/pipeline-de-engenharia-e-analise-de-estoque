"""Previsão de demanda por produto e sugestão de compra.

Como funciona:
1. Calendário da loja: descobre pelos dados em que dias da semana a loja não vende
   (ex.: fechada aos domingos) e os dias atípicos sem nenhuma venda (feriados).
   Esses dias ficam fora do cálculo e a previsão não espera vendas neles.
2. Competição de modelos: para cada produto, quatro modelos preveem as últimas
   semanas "escondidas" do histórico. O que errar menos é usado na previsão.
     - Holt-Winters (ETS): nível, tendência amortecida e sazonalidade semanal.
     - Croston (SBA): demanda intermitente (vende em dias soltos).
     - Média móvel semanal: média recente ajustada pelo perfil de cada dia da semana.
     - Ingênuo sazonal: repete a última semana (referência mínima).
3. Incerteza: o erro do teste vira uma faixa de 90% em torno da previsão.
4. Compra: quanto pedir para cobrir o prazo de entrega + o período desejado +
   a segurança, arredondado para o lote mínimo do fornecedor recomendado.
"""

import math
import warnings
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

MODELOS = {
    "holt_winters": "Holt-Winters",
    "croston": "Croston (SBA)",
    "media_semanal": "Média móvel semanal",
    "ingenuo": "Ingênuo sazonal",
}
SEM_HISTORICO = "Sem histórico suficiente"
SEM_VENDAS = "Sem vendas no período"

HORIZONTE_MAXIMO = 180          # dias à frente calculados (para achar a data de ruptura)
Z_90 = 1.645                    # faixa de 90%
ALFA_CROSTON = 0.1
PENALIDADE_INGENUO = 1.25
MINIMO_DIAS_COM_VENDA = 3
MINIMO_DIAS_ABERTOS = 14
MINIMO_UNIDADES = 6
LIMITE_CONFIANCA = {"Alta": 0.2, "Média": 0.4}        # erro semanal até 20% = alta; até 40% = média
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@dataclass
class Parametros:
    horizonte: int = 30                 # dias que a compra deve cobrir depois de chegar
    seguranca: int = 7                  # dias extras de cobertura para absorver variações
    janela: int = 90                    # dias de histórico usados
    prazo_manual: int | None = None     # None = prazo do fornecedor recomendado
    prazo_padrao: int = 7               # quando o produto não tem cotação


@dataclass
class Calendario:
    fechados: set                       # dias da semana sem vendas (0 = segunda)
    feriados: set                       # datas atípicas sem nenhuma venda
    abertos: list                       # datas abertas dentro da janela, em ordem

    def descricao(self) -> str:
        if not self.fechados:
            texto = "Loja aberta todos os dias"
        else:
            texto = "Loja fechada: " + ", ".join(DIAS_SEMANA[d] for d in sorted(self.fechados))
        if self.feriados:
            texto += f" · {len(self.feriados)} dia(s) atípico(s) sem vendas ignorado(s)"
        return texto


@dataclass
class ResultadoPrevisao:
    tabela: pd.DataFrame                # uma linha por produto
    series: dict = field(default_factory=dict)      # sku -> DataFrame(data, real, previsto, inferior, superior)
    calendario: Calendario | None = None


# ------------------------------------------------------------------------------
# Calendário da loja
# ------------------------------------------------------------------------------
def detectar_calendario(vendas: pd.DataFrame, hoje: date, janela: int) -> Calendario:
    datas = [hoje - timedelta(days=d) for d in range(janela, 0, -1)]
    totais = vendas.groupby("data")["quantidade_vendida"].sum() if not vendas.empty else pd.Series(dtype=float)
    total_do_dia = {d: float(totais.get(d, 0)) for d in datas}

    fechados = set()
    for dia in range(7):
        do_dia = [d for d in datas if d.weekday() == dia]
        if len(do_dia) >= 2 and sum(total_do_dia[d] > 0 for d in do_dia) / len(do_dia) < 0.25:
            fechados.add(dia)

    # Dia sem nenhuma venda numa loja que costuma vender bastante = feriado/dia atípico
    positivos = [t for t in total_do_dia.values() if t > 0]
    feriados = set()
    if positivos and float(np.median(positivos)) >= 5:
        feriados = {d for d in datas if d.weekday() not in fechados and total_do_dia[d] == 0}

    abertos = [d for d in datas if d.weekday() not in fechados and d not in feriados]
    return Calendario(fechados, feriados, abertos)


# ------------------------------------------------------------------------------
# Modelos (recebem a série dos dias abertos e os dias da semana a prever)
# ------------------------------------------------------------------------------
def _ingenuo(y: np.ndarray, dias_y: list, dias_futuros: list) -> np.ndarray:
    ultimo = {}
    for valor, dia in zip(y, dias_y):
        ultimo[dia] = valor
    media = float(np.mean(y)) if len(y) else 0.0
    return np.array([ultimo.get(d, media) for d in dias_futuros], dtype=float)


def _perfil_semanal(y: np.ndarray, dias_y: list) -> dict:
    """Peso de cada dia da semana (1 = dia médio; sábado forte > 1)."""
    media_geral = float(np.mean(y)) if len(y) else 0.0
    if media_geral == 0:
        return {}
    return {dia: float(np.mean([v for v, d in zip(y, dias_y) if d == dia])) / media_geral for dia in set(dias_y)}


def _media_semanal(y: np.ndarray, dias_y: list, dias_futuros: list) -> np.ndarray:
    if not len(y) or float(np.mean(y)) == 0:
        return np.zeros(len(dias_futuros))
    nivel = float(np.mean(y[-28:]))
    perfil = _perfil_semanal(y, dias_y)
    return np.array([nivel * perfil.get(d, 1.0) for d in dias_futuros])


def _croston(y: np.ndarray, dias_y: list, dias_futuros: list) -> np.ndarray:
    """Croston com a correção SBA (Syntetos-Boylan): tamanho médio da venda / intervalo médio."""
    indices = np.flatnonzero(y > 0)
    if len(indices) == 0:
        return np.zeros(len(dias_futuros))
    tamanho = float(y[indices[0]])
    intervalo = float(indices[0] + 1)
    anterior = indices[0]
    for i in indices[1:]:
        tamanho += ALFA_CROSTON * (float(y[i]) - tamanho)
        intervalo += ALFA_CROSTON * (float(i - anterior) - intervalo)
        anterior = i
    taxa = (1 - ALFA_CROSTON / 2) * tamanho / max(intervalo, 1.0)
    # Distribui a taxa pelos dias da semana conforme o padrão da loja (o total da semana não muda)
    perfil = _perfil_semanal(y, dias_y) if np.mean(y > 0) >= 0.5 else {}
    return np.array([taxa * perfil.get(d, 1.0) for d in dias_futuros])


def _holt_winters(y: np.ndarray, dias_y: list, dias_futuros: list) -> np.ndarray | None:
    periodo = len(set(dias_y))
    if periodo < 2 or len(y) < 3 * periodo or np.mean(y > 0) < 0.5:
        return None
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            modelo = ExponentialSmoothing(
                y.astype(float), trend="add", damped_trend=True, seasonal="add",
                seasonal_periods=periodo, initialization_method="estimated",
            ).fit()
            previsto = np.asarray(modelo.forecast(len(dias_futuros)), dtype=float)
        except Exception:
            return None
    return previsto if np.all(np.isfinite(previsto)) else None


_FUNCOES = {"holt_winters": _holt_winters, "croston": _croston, "media_semanal": _media_semanal, "ingenuo": _ingenuo}


def _aparar_picos(y: np.ndarray) -> np.ndarray:
    """Limita picos isolados (promoções, compras atípicas) para não inflarem a previsão."""
    if len(y) < 10 or np.mean(y > 0) < 0.5:
        return y
    q1, q3 = np.percentile(y, [25, 75])
    return np.minimum(y, q3 + 3 * max(q3 - q1, 1.0))


def _erro(previsto: np.ndarray, real: np.ndarray, media_treino: float, periodo: int) -> float:
    """WAPE semanal: erro absoluto das vendas somadas por semana / vendas totais do período testado.

    Para decidir compra importa acertar o total de cada semana, não o dia exato de cada venda
    (o sobe e desce diário é ruído natural e nenhum modelo consegue prever).
    """
    blocos = max(len(real) // periodo, 1)
    erro = sum(abs(float(f.sum()) - float(a.sum()))
               for f, a in zip(np.array_split(previsto, blocos), np.array_split(real, blocos)))
    base = float(real.sum()) or max(media_treino * len(real), 1.0)
    return erro / base


def competir(y: np.ndarray, dias_y: list) -> tuple[str, float, float]:
    """Testa os modelos nas últimas semanas do histórico. Devolve (modelo vencedor, erro, desvio diário)."""
    periodo = max(len(set(dias_y)), 1)
    teste = min(3 * periodo, max(periodo, len(y) // 4))
    treino, real = y[:-teste], y[-teste:]
    dias_treino, dias_teste = dias_y[:-teste], dias_y[-teste:]
    treino_ajustado = _aparar_picos(treino)
    media_treino = float(np.mean(treino)) if len(treino) else 0.0

    # Venda esporádica: só modelos feitos para isso (o "ingênuo" copiaria uma semana sem vendas)
    intermitente = np.mean(treino > 0) < 0.5
    candidatos = ("croston", "media_semanal") if intermitente else tuple(_FUNCOES)

    resultados = []
    for nome in candidatos:
        previsto = _FUNCOES[nome](treino_ajustado, dias_treino, dias_teste)
        if previsto is None:
            continue
        previsto = np.clip(previsto, 0, None)
        erro = _erro(previsto, real, media_treino, periodo)
        # O ingênuo é a referência mínima: copia uma única semana (com todo o ruído dela), então só
        # vence se for claramente melhor que os outros
        criterio = erro * (PENALIDADE_INGENUO if nome == "ingenuo" else 1.0)
        resultados.append((criterio, list(_FUNCOES).index(nome), nome, previsto, erro))
    _, _, vencedor, previsto, erro = min(resultados, key=lambda r: (r[0], r[1]))
    desvio = max(float(np.std(previsto - real)), math.sqrt(max(media_treino, 0.0)) * 0.5)
    return vencedor, erro, desvio


def confianca(erro: float | None) -> str:
    if erro is None:
        return "Baixa"
    for rotulo, limite in LIMITE_CONFIANCA.items():
        if erro <= limite:
            return rotulo
    return "Baixa"


# ------------------------------------------------------------------------------
# Previsão de um produto
# ------------------------------------------------------------------------------
def _datas_futuras(hoje: date, calendario: Calendario) -> list:
    return [hoje + timedelta(days=d) for d in range(HORIZONTE_MAXIMO)]


def prever_produto(serie: pd.Series, calendario: Calendario, hoje: date) -> dict:
    """`serie`: vendas por data (só dias com venda). Devolve modelo, erro, previsão diária e faixa."""
    abertos = calendario.abertos
    y = np.array([float(serie.get(d, 0.0)) for d in abertos])
    dias_y = [d.weekday() for d in abertos]
    futuras = _datas_futuras(hoje, calendario)
    abertas_futuras = [d for d in futuras if d.weekday() not in calendario.fechados]
    dias_futuros = [d.weekday() for d in abertas_futuras]

    if y.sum() == 0:
        modelo, erro, desvio, diario = SEM_VENDAS, None, 0.0, np.zeros(len(abertas_futuras))
    elif len(y) < MINIMO_DIAS_ABERTOS or (y > 0).sum() < MINIMO_DIAS_COM_VENDA or y.sum() < MINIMO_UNIDADES:
        modelo, erro = SEM_HISTORICO, None
        diario = np.full(len(abertas_futuras), float(y.mean()))
        desvio = float(np.std(y)) if len(y) > 1 else float(y.mean())
    else:
        modelo, erro, desvio = competir(y, dias_y)
        diario = _FUNCOES[modelo](_aparar_picos(y), dias_y, dias_futuros)
        if diario is None:                         # Holt-Winters falhou no ajuste final
            modelo, diario = "media_semanal", _media_semanal(_aparar_picos(y), dias_y, dias_futuros)
        diario = np.clip(np.asarray(diario, dtype=float), 0, None)

    por_data = dict(zip(abertas_futuras, diario))
    previsto = np.array([por_data.get(d, 0.0) for d in futuras])
    aberto = np.array([d in por_data for d in futuras])
    margem = np.where(aberto, Z_90 * desvio, 0.0)
    return {
        "modelo": modelo, "erro": erro, "desvio": desvio,
        "datas": futuras, "previsto": previsto,
        "inferior": np.clip(previsto - margem, 0, None), "superior": previsto + margem,
        "historico": pd.DataFrame({"data": abertos, "real": y}),
    }


def dias_ate_acabar(estoque: float, previsto: np.ndarray) -> int | None:
    """Dias corridos até a previsão acumulada consumir o estoque (None = não acaba no horizonte calculado)."""
    if estoque <= 0:
        return 0
    acumulado = np.cumsum(previsto)
    indice = int(np.searchsorted(acumulado, estoque, side="left"))
    return indice if indice < len(previsto) else None


def quantidade_sugerida(necessidade: float, lote: int) -> int:
    if necessidade <= 0:
        return 0
    lote = max(int(lote or 1), 1)
    return int(math.ceil(necessidade / lote) * lote)


# ------------------------------------------------------------------------------
# Fornecedor recomendado para a compra
# ------------------------------------------------------------------------------
def fornecedor_para_compra(ofertas: pd.DataFrame | None) -> dict | None:
    """Melhor oferta pela nota, nunca de fornecedor 🔴 Perigoso. None = sem oferta aceitável."""
    if ofertas is None or ofertas.empty:
        return None
    aceitaveis = ofertas[ofertas["classe"] != "PERIGOSO"] if "classe" in ofertas.columns else ofertas
    if aceitaveis.empty:
        return None
    ordem = ["nota_cotacao", "preco_cotado"] if "nota_cotacao" in aceitaveis.columns else ["preco_cotado"]
    crescente = [False, True] if len(ordem) == 2 else [True]
    melhor = aceitaveis.sort_values(ordem, ascending=crescente).iloc[0]
    return {
        "fornecedor": melhor["fornecedor_cotacao"], "prazo": int(melhor["prazo_dias"]),
        "lote": int(melhor["lote_minimo"]), "preco": float(melhor["preco_cotado"]),
        "classe": melhor.get("classe"),
    }


# ------------------------------------------------------------------------------
# Previsão de todos os produtos
# ------------------------------------------------------------------------------
def prever_estoque(
    estoque: pd.DataFrame,
    vendas: pd.DataFrame,
    hoje: date,
    parametros: Parametros | None = None,
    cotacoes_avaliadas: pd.DataFrame | None = None,
) -> ResultadoPrevisao:
    """Previsão, data de ruptura e sugestão de compra para cada produto do estoque."""
    p = parametros or Parametros()
    vendas = vendas.copy()
    vendas["data"] = pd.to_datetime(vendas["data"]).dt.date
    inicio = hoje - timedelta(days=p.janela)
    vendas = vendas[(vendas["data"] >= inicio) & (vendas["data"] < hoje)]
    calendario = detectar_calendario(vendas, hoje, p.janela)
    por_sku = {sku: grupo.groupby("data")["quantidade_vendida"].sum() for sku, grupo in vendas.groupby("sku")}
    ofertas_por_sku = (
        dict(tuple(cotacoes_avaliadas.groupby("sku")))
        if cotacoes_avaliadas is not None and not cotacoes_avaliadas.empty else {}
    )

    linhas, series = [], {}
    for item in estoque.to_dict("records"):
        sku = item["sku"]
        resultado = prever_produto(por_sku.get(sku, pd.Series(dtype=float)), calendario, hoje)
        previsto = resultado["previsto"]
        qtd_estoque = float(item["quantidade_disponivel"] or 0)

        oferta = fornecedor_para_compra(ofertas_por_sku.get(sku))
        prazo = p.prazo_manual if p.prazo_manual is not None else (oferta["prazo"] if oferta else p.prazo_padrao)
        lote = oferta["lote"] if oferta else 1
        preco = oferta["preco"] if oferta else float(item.get("preco_unitario") or 0)

        media_diaria = float(previsto[: p.horizonte].mean()) if p.horizonte else 0.0
        demanda_prazo = float(previsto[:prazo].sum())
        demanda_cobertura = float(previsto[: prazo + p.horizonte].sum())
        seguranca_un = media_diaria * p.seguranca
        necessidade = demanda_cobertura + seguranca_un - qtd_estoque
        qtd = quantidade_sugerida(necessidade, lote)
        acaba_em = dias_ate_acabar(qtd_estoque, previsto)

        linhas.append({
            "sku": sku,
            "nome_produto": item["nome_produto"],
            "estoque": int(qtd_estoque),
            "media_diaria": round(media_diaria, 2),
            "demanda_horizonte": round(float(previsto[: p.horizonte].sum()), 1),
            "dias_ate_acabar": acaba_em,
            "data_ruptura": hoje + timedelta(days=acaba_em) if acaba_em is not None else None,
            "prazo": int(prazo),
            "vai_faltar": acaba_em is not None and acaba_em < prazo and media_diaria > 0,
            "demanda_prazo": round(demanda_prazo, 1),
            "seguranca_un": round(seguranca_un, 1),
            "quantidade_sugerida": qtd,
            "fornecedor": oferta["fornecedor"] if oferta else None,
            "lote": int(lote),
            "preco": preco,
            "custo_pedido": round(qtd * preco, 2),
            "modelo": MODELOS.get(resultado["modelo"], resultado["modelo"]),
            "erro": None if resultado["erro"] is None else round(resultado["erro"], 3),
            "confianca": confianca(resultado["erro"]),
        })
        series[sku] = resultado
    tabela = pd.DataFrame(linhas)
    if not tabela.empty:
        tabela = tabela.sort_values(["vai_faltar", "dias_ate_acabar"], ascending=[False, True], na_position="last",
                                    ignore_index=True)
    return ResultadoPrevisao(tabela, series, calendario)


def texto_para_ia(resultado: ResultadoPrevisao, parametros: Parametros, limite: int | None = None) -> str:
    """Resumo da previsão para o contexto do assistente de IA."""
    t = resultado.tabela
    if t.empty:
        return ""
    linhas = [
        "### PREVISÃO DE DEMANDA E SUGESTÃO DE COMPRA",
        f"- Parâmetros: compra cobre {parametros.horizonte} dias após chegar + {parametros.seguranca} dias de segurança; "
        f"histórico usado: {parametros.janela} dias. {resultado.calendario.descricao() if resultado.calendario else ''}",
        f"- Produtos que vão faltar antes da reposição chegar: {int(t['vai_faltar'].sum())}",
        f"- Custo total dos pedidos sugeridos: R$ {t['custo_pedido'].sum():,.2f}",
    ]
    mostrar = t if limite is None else t.head(limite)
    for r in mostrar.itertuples():
        acaba = "não acaba nos próximos 6 meses" if pd.isna(r.dias_ate_acabar) else (
            "já está zerado" if r.dias_ate_acabar == 0 else f"acaba em {r.dias_ate_acabar} dias ({r.data_ruptura:%d/%m/%Y})")
        compra = (f"comprar {r.quantidade_sugerida} un de {r.fornecedor or 'fornecedor a definir'} "
                  f"(R$ {r.custo_pedido:,.2f})" if r.quantidade_sugerida else "não precisa comprar agora")
        aviso = " | ⏳ VAI FALTAR ANTES DA REPOSIÇÃO" if r.vai_faltar else ""
        linhas.append(
            f"  * [{r.sku}] {r.nome_produto}: estoque {r.estoque} un, venda prevista {r.media_diaria:.1f} un/dia, "
            f"{acaba}, prazo {r.prazo} dias, {compra}. Modelo: {r.modelo} (confiança {r.confianca}){aviso}"
        )
    if limite is not None and len(t) > limite:
        linhas.append(f"  * (Mais {len(t) - limite} produtos sem urgência não listados.)")
    return "\n".join(linhas)
