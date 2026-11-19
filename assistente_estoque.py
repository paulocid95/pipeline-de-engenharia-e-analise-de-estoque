"""
Módulo de Assistente Virtual de Estoque e Compras (Chatbot com Google Gemini).
Fornece extração de contexto de banco de dados (PostgreSQL/Neon), engenharia de prompts,
arquitetura de resiliência com failover cascata de modelos Gemini e reserva gratuita no Groq,
e entrega fluida via st.write_stream sem cortes ou truncamentos.
"""

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Generator

import httpx
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
import streamlit as st

from datas_relativas import data_referencia, deslocar_datas, dias_desde
from regras_fornecedores import (
    ROTULO_CLASSE,
    avaliar_cotacoes,
    motivo_derrota,
    opcoes_por_produto,
    ranking_fornecedores,
)

# Erros técnicos vão só para o log do servidor (visível apenas ao dono do app),
# nunca para a tela, para não expor host, usuário do banco ou detalhes da API.
logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURAÇÃO DE MODELOS E RESILIÊNCIA EM CASCATA
# ==============================================================================
# Modelos em ordem prioritária de failover caso ocorra sobrecarga (503) ou cota diária excedida (429)
MODELOS_CASCADE = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]
MODELO_PADRAO = MODELOS_CASCADE[0]

# Reserva gratuita: Groq (API compatível com a da OpenAI). Só é usado se todos os modelos do Gemini falharem.
# O catálogo gratuito do Groq muda sem aviso: se um modelo sair, o próximo da lista é tentado.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELOS_GROQ = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b"]
# O plano gratuito do Groq aceita poucos tokens por minuto: contexto enxuto, histórico curto e resposta menor
MENSAGENS_GROQ = 4
MAX_TOKENS_GROQ = 2000
ITENS_CONTEXTO_ENXUTO = 10

# Proteção da cota da API Gemini em um app público (sem login)
LIMITE_PERGUNTAS_SESSAO = 10
INTERVALO_MINIMO_SEGUNDOS = 5
# Cada pergunta faz no máximo 1 chamada por modelo da cascata (até 4 no total)
TIMEOUT_CHAMADA_MS = 30_000


def verificar_limite_perguntas(
    perguntas_feitas: int,
    ultimo_envio: float | None,
    agora: float,
    limite: int = LIMITE_PERGUNTAS_SESSAO,
    intervalo_minimo: float = INTERVALO_MINIMO_SEGUNDOS,
) -> str | None:
    """Retorna a mensagem de bloqueio, ou None se a pergunta pode ser enviada."""
    if perguntas_feitas >= limite:
        return (
            f"Você atingiu o limite de {limite} perguntas por sessão. "
            "Este limite protege a cota da API nesta demonstração pública."
        )
    if ultimo_envio is not None and agora - ultimo_envio < intervalo_minimo:
        espera = intervalo_minimo - (agora - ultimo_envio)
        return f"Aguarde {espera:.0f} segundo(s) antes de enviar outra pergunta."
    return None


# ==============================================================================
# 1. GESTÃO DE CREDENCIAIS E CHAVE DE API (SECRETS COM FALLBACK)
# ==============================================================================
def obter_chave_gemini() -> str:
    """Recupera a chave de API do Gemini a partir do st.secrets ou os.environ."""
    # 1. Tenta carregar do st.secrets (Streamlit Community Cloud ou .streamlit/secrets.toml)
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass

    # 2. Fallback para variáveis de ambiente locais (.env)
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key.strip()

    return ""


def obter_chave_groq() -> str:
    """Chave da reserva Groq (opcional): st.secrets ou os.environ."""
    try:
        if "GROQ_API_KEY" in st.secrets:
            return str(st.secrets["GROQ_API_KEY"]).strip()
    except Exception:
        pass
    return (os.getenv("GROQ_API_KEY") or "").strip()


def provedores_ativos(chave_gemini: str, chave_groq: str) -> list[str]:
    """Quem pode receber as perguntas (citado no aviso de privacidade)."""
    return [nome for nome, chave in (("Google Gemini", chave_gemini), ("Groq", chave_groq)) if chave] or ["Google Gemini"]


# ==============================================================================
# 2. EXTRAÇÃO DE CONTEXTO ANALÍTICO DO BANCO (GROUND TRUTH / IN-MEMORY CACHE)
# ==============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def extrair_contexto_executivo_estoque(_engine: Engine, enxuto: bool = False) -> str:
    """Extrai uma síntese executiva e altamente estruturada da situação atual do estoque

    e cotações de fornecedores. Cruza diretamente produtos críticos e em alerta
    com a matriz concorrente de fornecedores para municiar a LLM com contexto completo.
    """
    if _engine is None:
        return "Erro: Conexão com o banco de dados não disponível."

    try:
        # 1. Consulta do snapshot mais recente do estoque por produto
        query_estoque = """
            SELECT DISTINCT ON (p.sku)
                p.sku,
                p.nome_produto,
                c.nome_categoria,
                p.preco_unitario,
                p.estoque_minimo,
                f.quantidade_disponivel,
                f.valor_total_estoque,
                f.status_reposicao,
                f.data_carga
            FROM core.dim_produtos p
            LEFT JOIN core.dim_categorias c ON p.id_categoria = c.id_categoria
            LEFT JOIN core.fato_estoque f ON p.id_produto = f.id_produto
            ORDER BY p.sku, f.data_carga DESC NULLS LAST;
        """
        df_est = pd.read_sql(text(query_estoque), _engine)

        # 2. Consulta de cotações dos fornecedores
        query_cotacoes = """
            SELECT
                p.sku,
                p.nome_produto,
                c.fornecedor,
                c.preco_cotado,
                c.lote_minimo,
                c.prazo_dias
            FROM core.fato_cotacoes c
            JOIN core.dim_produtos p ON c.id_produto = p.id_produto
            ORDER BY p.sku, c.preco_cotado ASC;
        """
        df_cot = pd.read_sql(text(query_cotacoes), _engine)

    except Exception:
        logger.exception("Falha ao obter contexto do banco para o assistente")
        return "Aviso de banco: Não foi possível obter o contexto atualizado no momento."

    # 3. Histórico de ocorrências (vazio se o pipeline ainda não gerou a tabela)
    try:
        df_oc = pd.read_sql(text(
            "SELECT fornecedor, tipo, gravidade, data_ocorrencia, status, data_resolucao FROM core.fato_ocorrencias;"
        ), _engine)
    except Exception:
        logger.exception("Histórico de ocorrências indisponível para o assistente")
        df_oc = pd.DataFrame(columns=["fornecedor", "tipo", "gravidade", "data_ocorrencia", "status", "data_resolucao"])

    # Datas relativas: a demonstração não envelhece (mesma regra do painel)
    dias = dias_desde(data_referencia(df_est["data_carga"]), date.today())
    df_oc = deslocar_datas(df_oc, ["data_ocorrencia", "data_resolucao"], dias)
    return montar_contexto(df_est, df_cot, df_oc, date.today(), enxuto=enxuto)


def dados_planilha_para_contexto(estoque: pd.DataFrame, cotacoes, ocorrencias) -> tuple:
    """Converte os dados higienizados da planilha enviada para o formato usado em montar_contexto."""
    df_est = estoque.copy()
    if "estoque_minimo" not in df_est.columns:
        df_est["estoque_minimo"] = None
    if cotacoes is None or cotacoes.empty:
        df_cot = pd.DataFrame(columns=["sku", "nome_produto", "fornecedor", "preco_cotado", "lote_minimo", "prazo_dias"])
    else:
        df_cot = cotacoes.rename(columns={"fornecedor_cotacao": "fornecedor"})[
            ["sku", "nome_produto", "fornecedor", "preco_cotado", "lote_minimo", "prazo_dias"]]
    if ocorrencias is None:
        ocorrencias = pd.DataFrame(columns=["fornecedor", "tipo", "gravidade", "data_ocorrencia", "status", "data_resolucao"])
    return df_est, df_cot, ocorrencias


def _inteiro(valor) -> int:
    return int(valor) if valor is not None and pd.notna(valor) else 0


def montar_contexto(
    df_est: pd.DataFrame, df_cot: pd.DataFrame, df_oc: pd.DataFrame, hoje: date, origem: str = "POSTGRESQL / SCHEMA CORE",
    enxuto: bool = False,
) -> str:
    """Síntese executiva do estoque, cotações e ranking de fornecedores para a IA (sem acessar o banco).

    `enxuto`: versão curta para a reserva Groq (limite baixo de tokens): só panorama, ranking e os
    primeiros itens críticos e em alerta, sem a lista completa de fornecedores e sem os demais produtos.
    """
    # Ranking de risco e melhor opção por produto (mesmas regras do painel)
    ranking = pd.DataFrame()
    opcoes_sku: dict = {}
    if not df_cot.empty:
        ranking = ranking_fornecedores(df_cot, df_oc, hoje, chave_produto="sku", coluna_fornecedor="fornecedor")
        cot_avaliadas = avaliar_cotacoes(df_cot, ranking, chave_produto="sku", coluna_fornecedor="fornecedor")
        opcoes_sku = opcoes_por_produto(cot_avaliadas, chave_produto="sku")

    if df_est.empty:
        return "Aviso: Nenhum registro de estoque encontrado."

    # Agregações de alto nível
    total_skus = len(df_est)
    total_unidades = int(df_est["quantidade_disponivel"].fillna(0).sum())
    capital_total = float(df_est["valor_total_estoque"].fillna(0).sum())

    contagem_status = df_est["status_reposicao"].value_counts().to_dict()
    criticos = df_est[df_est["status_reposicao"] == "CRITICO"]
    alertas = df_est[df_est["status_reposicao"] == "ALERTA"]

    # Mapeamento ágil de cotações por SKU
    cotacoes_por_sku: dict[str, list[dict]] = {}
    if not df_cot.empty:
        for sku, grp in df_cot.groupby("sku"):
            cotacoes_por_sku[str(sku)] = grp.sort_values(by="preco_cotado").to_dict(orient="records")

    def formatar_item_detalhado_com_fornecedores(row) -> list[str]:
        sku = str(row["sku"])
        nome = row["nome_produto"]
        cat = row["nome_categoria"]
        disp = _inteiro(row["quantidade_disponivel"])
        minimo = _inteiro(row["estoque_minimo"])
        preco_ref = float(row["preco_unitario"]) if pd.notna(row["preco_unitario"]) else 0.0

        linhas = [
            f"  * [{sku}] {nome} | Categoria: {cat}",
            f"    - Situação Operacional: Disponível = {disp} un | Estoque Mínimo = {minimo} un | Preço Tabela = R$ {preco_ref:,.2f}",
        ]

        cots = cotacoes_por_sku.get(sku, [])
        op = opcoes_sku.get(sku)
        if cots and op is not None:
            linhas.extend(_linhas_opcoes(op))
            opcoes_forn = [
                f"{c['fornecedor']} [{_classe_fornecedor(c['fornecedor'])}]: R$ {c['preco_cotado']:.2f} "
                f"({c['prazo_dias']} dias, lote {c['lote_minimo']} un)"
                for c in cots
            ]
            if not enxuto:
                linhas.append(f"    - Todos Fornecedores Disponíveis: {'; '.join(opcoes_forn)}")
        else:
            linhas.append("    - Fornecedores: Nenhuma cotação concorrente cadastrada para este produto.")

        return linhas

    classes_por_fornecedor = (
        {r.fornecedor: f"{ROTULO_CLASSE[r.classe]}, nota {r.nota_final:.0f}" for r in ranking.itertuples()}
        if not ranking.empty else {}
    )

    def _classe_fornecedor(fornecedor: str) -> str:
        return classes_por_fornecedor.get(fornecedor, "sem avaliação")

    def _descrever(c) -> str:
        return (
            f"'{c['fornecedor']}' [{ROTULO_CLASSE[c['classe']]}] R$ {c['preco_cotado']:.2f}, "
            f"{int(c['prazo_dias'])} dias, lote {int(c['lote_minimo'])} un, nota da proposta {c['nota_cotacao']:.0f}"
        )

    def _linhas_opcoes(op: dict) -> list[str]:
        melhor = op["melhor"]
        linhas = [f"    - MELHOR OPÇÃO GERAL (recomendar): {_descrever(melhor)}"]
        rotulos = {"mais_barato": "Alternativa mais barata", "mais_rapido": "Alternativa mais rápida",
                   "menor_lote": "Alternativa de menor lote"}
        for criterio, rotulo in rotulos.items():
            alt = op[criterio]
            if alt is None:
                linhas.append(f"    - {rotulo}: a própria melhor opção")
            else:
                linhas.append(f"    - {rotulo}: {_descrever(alt)} | Por que não venceu: {motivo_derrota(alt, melhor)}")
        return linhas

    # Montagem do relatório contextual executivo
    linhas_contexto = [
        f"### PANORAMA GERAL DO ESTOQUE ({origem})",
        f"- Total de SKUs cadastrados: {total_skus}",
        f"- Volume físico disponível: {total_unidades:,} unidades",
        f"- Capital total imobilizado: R$ {capital_total:,.2f}",
        f"- Distribuição por Status de Reposição: {contagem_status}",
        "",
        "### RANKING E RISCO DE FORNECEDORES (nota 0-100: preço 30%, prazo 20%, lote 10%, confiabilidade 40%)",
    ]
    if not ranking.empty:
        sem_historico = df_oc.empty
        for posicao, r in enumerate(ranking.itertuples(), start=1):
            linhas_contexto.append(
                f"  {posicao}. {r.fornecedor}: {ROTULO_CLASSE[r.classe].upper()} | nota {r.nota_final:.0f} | "
                f"confiabilidade {r.nota_confiabilidade:.0f} | {r.ocorrencias_12m} ocorrências em 12 meses "
                f"({r.sem_solucao} sem solução) | Motivo: {r.motivo}"
            )
        if sem_historico:
            linhas_contexto.append("  (Atenção: sem histórico de ocorrências; confiabilidade considerada 100.)")
    else:
        linhas_contexto.append("  * Ranking indisponível: nenhuma cotação registrada.")
    linhas_contexto += [
        "",
        "### ITENS EM SITUAÇÃO CRÍTICA (RUPTURA IMINENTE OU ESTOQUE ZERADO) COM SEUS FORNECEDORES:",
    ]

    def _detalhar(itens: pd.DataFrame) -> None:
        mostrar = itens.head(ITENS_CONTEXTO_ENXUTO) if enxuto else itens
        for _, row in mostrar.iterrows():
            linhas_contexto.extend(formatar_item_detalhado_com_fornecedores(row))
        if len(mostrar) < len(itens):
            linhas_contexto.append(
                f"  * (Resumo: mais {len(itens) - len(mostrar)} itens nesta situação não detalhados; "
                "avise o usuário que a lista está resumida.)"
            )

    if not criticos.empty:
        _detalhar(criticos)
    else:
        linhas_contexto.append("  * Nenhum SKU em estado crítico no momento.")

    linhas_contexto.append("")
    linhas_contexto.append("### ITENS EM NÍVEL DE ALERTA (BAIXA COBERTURA) COM SEUS FORNECEDORES:")
    if not alertas.empty:
        _detalhar(alertas)
    else:
        linhas_contexto.append("  * Nenhum SKU em estado de alerta.")

    if enxuto:
        return "\n".join(linhas_contexto)
    linhas_contexto.append("")
    linhas_contexto.append("### DEMAIS PRODUTOS (SITUAÇÃO NORMAL OU EXCESSO) COM SUAS OPÇÕES DE FORNECEDOR:")
    # Produtos críticos e em alerta já foram detalhados acima: aqui entram só os demais
    ja_detalhados = set(criticos["sku"].astype(str)) | set(alertas["sku"].astype(str))
    if opcoes_sku:
        for sku, op in opcoes_sku.items():
            if str(sku) in ja_detalhados:
                continue
            linhas_contexto.append(f"  * SKU [{sku}] - {op['melhor']['nome_produto']}:")
            linhas_contexto.extend(_linhas_opcoes(op))
    else:
        linhas_contexto.append("  * Nenhuma cotação de fornecedor registrada.")

    return "\n".join(linhas_contexto)


# ==============================================================================
# 3. CAMADA DE INTEGRAÇÃO COM GOOGLE GEMINI API (FAILOVER & STREAMING RESILIENTE)
# ==============================================================================
def construir_prompt_sistema(contexto_banco: str) -> str:
    """Gera as diretrizes de governança e a persona de consultor executivo da LLM."""
    return f"""Você é o Assistente Executivo Sênior de Estoque e Inteligência de Compras (Procurement & Inventory Analytics).
Sua missão é auxiliar gestores de logística, compradores e diretores de supply chain a tomarem decisões rápidas, precisas e embasadas em dados reais.

DIRETRIZES FUNDAMENTAIS DE COMPORTAMENTO:
1. IDIOMA E TOM: Responda estritamente em Português do Brasil (PT-BR), com tom profissional, executivo, analítico e objetivo.
2. PRECISÃO FÁTICA (ZERO ALUCINAÇÃO): Use exclusivamente os dados reais fornecidos no CONTEXTO OPERACIONAL abaixo. Não invente números, SKUs, preços ou fornecedores inexistentes.
3. TABELA MARKDOWN OBRIGATÓRIA PARA REPOSIÇÃO E COMPRAS:
   Sempre que o usuário perguntar sobre reposição, produtos críticos, itens em alerta, análise de fornecedores ou decisões de compra, você DEVE estruturar sua resposta PRINCIPALMENTE através de uma TABELA MARKDOWN com as seguintes colunas obrigatórias:
   | Produto Crítico | Fornecedor Recomendado | Classificação | Preço Cotado (R$) | Prazo de Entrega (dias) | Justificativa da Escolha |

   - "Produto Crítico": Nome completo do produto acompanhado do SKU.
   - "Fornecedor Recomendado": Nome do fornecedor mais vantajoso segundo o critério analisado.
   - "Classificação": Classe do fornecedor no ranking de risco, com ícone: 🟢 Bom, 🟡 Médio ou 🔴 Perigoso, e a nota (ex: "🟢 Bom (86)").
   - "Preço Cotado (R$)": Valor unitário cotado (ex: R$ 1.250,00).
   - "Prazo de Entrega (dias)": Prazo de entrega em dias corridos do fornecedor recomendado.
   - "Justificativa da Escolha": Racional executivo claro (ex: "Melhor nota geral: preço competitivo e fornecedor confiável", "Entrega emergencial em 2 dias para estancar ruptura", ou "Melhor equilíbrio custo-benefício com lote mínimo viável").

4. CRITÉRIOS DE DECISÃO DE COMPRAS E RISCO DE FORNECEDORES:
   - Por padrão, recomende a "MELHOR OPÇÃO GERAL" de cada produto informada no contexto. Ela combina preço, prazo, lote mínimo e confiabilidade (histórico de atrasos, defeitos, itens errados, processos judiciais, divergências, falhas de atendimento e avarias).
   - Nunca recomende como opção principal um fornecedor 🔴 Perigoso. Se ele for o mais barato ou o mais rápido, cite-o apenas como alternativa, com um aviso explícito e o motivo (ex: "o Fornecedor D é R$ 190,00 mais barato, mas está 🔴 Perigoso: processo judicial em aberto há 44 dias").
   - Se o foco for "menor preço" ou "urgência": destaque a alternativa mais barata ou mais rápida informada no contexto, mas sempre mostre a classificação dela e compare com a melhor opção geral.
   - Após a tabela, liste as alternativas relevantes (mais barata, mais rápida, menor lote) com a diferença de preço, de prazo ou de lote e o motivo de não terem vencido, deixando claro que a decisão final é do usuário.
   - Se perguntarem sobre um fornecedor, use o RANKING E RISCO DE FORNECEDORES: classe, nota, ocorrências em 12 meses, problemas sem solução e motivo principal.

5. COMPLETUDE E NÃO TRUNCAMENTO:
   - Apresente a relação completa de TODOS os produtos críticos identificados sem cortar a resposta.
   - Após a tabela Markdown, inclua sempre um resumo executivo com estimativas de investimento e recomendações práticas para a equipe de compras.

---
CONTEXTO OPERACIONAL ATUALIZADO (DADOS DO ESTOQUE):
{contexto_banco}
---
"""


@dataclass
class Resposta:
    texto: str
    origem: str | None = None       # "Google Gemini (modelo)" ou "Groq (modelo)"; None = falha


MSG_SEM_CHAVE = (
    "⚠️ Nenhuma chave de IA configurada. Configure `GEMINI_API_KEY` (e, opcionalmente, `GROQ_API_KEY`) "
    "nos Secrets do Streamlit ou no `.env`."
)
MSG_INDISPONIVEL = (
    "⚠️ **Os servidores de IA estão temporariamente indisponíveis no momento.**\n\n"
    "👉 Por favor, aguarde alguns instantes e reenvie sua pergunta."
)


def _tentar_gemini(mensagens, system_instruction, api_key, modelo, max_retries, backoff_base) -> tuple:
    """Cascata de modelos Gemini. Devolve (texto, modelo) ou (None, último erro)."""
    modelos_a_tentar = [modelo] + [m for m in MODELOS_CASCADE if m != modelo]
    ultimo_erro = None
    try:
        from google import genai
        from google.genai import types

        # Tempo limite por chamada: um modelo travado passa a vez ao próximo em vez de prender o usuário
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_CHAMADA_MS))
        contents = [
            types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=m["content"])])
            for m in mensagens
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_instruction, temperature=0.2, max_output_tokens=3500,
        )
        for mod in modelos_a_tentar:
            for tentativa in range(1, max_retries + 1):
                try:
                    response = client.models.generate_content(model=mod, contents=contents, config=config)
                    if response.text and len(response.text.strip()) > 50:
                        return response.text, mod
                except Exception as e:
                    ultimo_erro = e
                    # Cota diária estourada (429): pula direto para o próximo modelo da cascata
                    msg_err = str(e).lower()
                    if "429" in msg_err or "resource_exhausted" in msg_err:
                        break
                    time.sleep(backoff_base * tentativa)   # 503 temporário: espera um pouco
    except Exception as e:
        ultimo_erro = e
    return None, ultimo_erro


_PENSAMENTO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _tentar_groq(mensagens, system_instruction, api_key, cliente: httpx.Client | None = None) -> tuple:
    """Reserva Groq: tenta os modelos gratuitos em ordem. Devolve (texto, modelo) ou (None, último erro)."""
    corpo_mensagens = [{"role": "system", "content": system_instruction}] + [
        {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
        for m in mensagens[-MENSAGENS_GROQ:]
    ]
    ultimo_erro = None
    proprio = cliente is None
    cliente = cliente or httpx.Client(timeout=TIMEOUT_CHAMADA_MS / 1000)
    try:
        for modelo in MODELOS_GROQ:
            try:
                r = cliente.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": modelo, "messages": corpo_mensagens, "temperature": 0.2,
                          "max_tokens": MAX_TOKENS_GROQ},
                )
                if r.status_code != 200:
                    # 404/400: modelo saiu do catálogo; 413/429: limite do plano gratuito -> próximo modelo
                    ultimo_erro = f"Groq {modelo}: HTTP {r.status_code}"
                    continue
                texto = r.json()["choices"][0]["message"].get("content") or ""
                texto = _PENSAMENTO.sub("", texto).strip()      # alguns modelos devolvem o raciocínio
                if len(texto) > 50:
                    return texto, modelo
                ultimo_erro = f"Groq {modelo}: resposta vazia"
            except Exception as e:
                ultimo_erro = e
    finally:
        if proprio:
            cliente.close()
    return None, ultimo_erro


def obter_resposta(
    mensagens: list[dict],
    contexto_banco: str,
    api_key: str,
    chave_groq: str = "",
    contexto_enxuto: str | None = None,
    modelo: str = MODELO_PADRAO,
    max_retries: int = 1,
    backoff_base: float = 1.5,
    cliente_groq: httpx.Client | None = None,
) -> Resposta:
    """Pergunta ao Gemini (cascata de modelos) e, se todos falharem, à reserva Groq com o contexto enxuto."""
    if not api_key and not chave_groq:
        return Resposta(MSG_SEM_CHAVE)
    erros = []
    if api_key:
        texto, info = _tentar_gemini(mensagens, construir_prompt_sistema(contexto_banco), api_key, modelo,
                                     max_retries, backoff_base)
        if texto:
            return Resposta(texto, f"Google Gemini ({info})")
        erros.append(info)
    if chave_groq:
        prompt = construir_prompt_sistema(contexto_enxuto or contexto_banco)
        texto, info = _tentar_groq(mensagens, prompt, chave_groq, cliente_groq)
        if texto:
            return Resposta(texto, f"Groq ({info.split('/')[-1]})")
        erros.append(info)
    logger.error("Falha em todos os provedores de IA: %r", erros)
    return Resposta(MSG_INDISPONIVEL)


def digitar(texto: str) -> Generator[str, None, None]:
    """Entrega a resposta palavra a palavra para st.write_stream (sensação de digitação, sem cortes)."""
    palavras = texto.split(" ")
    for i, palavra in enumerate(palavras):
        yield palavra + (" " if i < len(palavras) - 1 else "")
        time.sleep(0.012)


def gerar_resposta_assistente_stream(
    mensagens: list[dict],
    contexto_banco: str,
    api_key: str,
    modelo: str = MODELO_PADRAO,
    max_retries: int = 1,
    backoff_base: float = 1.5,
) -> Generator[str, None, None]:
    """Compatibilidade: resposta só do Gemini, já em formato de stream."""
    yield from digitar(obter_resposta(mensagens, contexto_banco, api_key, modelo=modelo,
                                      max_retries=max_retries, backoff_base=backoff_base).texto)


# ==============================================================================
# 4. COMPONENTE DE INTERFACE STREAMLIT (LEVE & REATIVO)
# ==============================================================================
def _rotulo_origem(origem: str) -> str:
    icone = "⚡" if origem.startswith("Groq") else "✨"
    return f"{icone} Respondido por {origem}"


def _exibir_contador(espaco) -> None:
    """Mostra quantas perguntas ainda restam na sessão."""
    restantes = max(LIMITE_PERGUNTAS_SESSAO - st.session_state.perguntas_feitas, 0)
    espaco.caption(f"💬 Perguntas restantes nesta sessão: **{restantes} de {LIMITE_PERGUNTAS_SESSAO}**")


def renderizar_interface_chat(engine: Engine, dados_usuario: tuple | None = None) -> None:
    """Renderiza a interface do chatbot dentro do Streamlit, com gerenciamento

    enxuto de estado de sessão, feedback visual e streaming de resposta resiliente.
    `dados_usuario`: (estoque, cotações, ocorrências) de uma planilha enviada; None = demonstração (banco).
    """
    usuario = dados_usuario is not None
    # Conversas separadas: a da demonstração não se mistura com a dos dados do usuário
    chave = "messages_planilha" if usuario else "messages"
    origem = "aos dados da sua planilha" if usuario else "em tempo real ao PostgreSQL"
    # 1. Inicializa o estado de mensagens da sessão (máximo de 15 turnos para poupar RAM)
    if chave not in st.session_state:
        st.session_state[chave] = [
            {
                "role": "assistant",
                "content": (
                    f"Olá! Sou seu **Assistente de Inteligência de Estoque e Compras** conectado {origem}."
                    "\n\nComo posso ajudar? Você pode me perguntar sobre **produtos críticos**, "
                    "**fornecedores com menor preço**, **prazos de entrega mais ágeis** ou simulações de compra."
                ),
            }
        ]
    mensagens = st.session_state[chave]

    # Contador de uso da sessão (não é zerado pelo botão "Limpar Chat")
    st.session_state.setdefault("perguntas_feitas", 0)
    st.session_state.setdefault("ultimo_envio", None)
    limite_atingido = st.session_state.perguntas_feitas >= LIMITE_PERGUNTAS_SESSAO

    # Banner informativo da aba
    st.markdown(
        '<div class="tab-banner">🤖 <strong>Assistente Virtual com IA:</strong> Análise de suprimentos, '
        "recomendações de negociação e triagem de rupturas com processamento em nuvem via Google Gemini.</div>",
        unsafe_allow_html=True,
    )
    if usuario:
        from dashboard.componentes import aviso_ia_privacidade
        aviso_ia_privacidade(provedores_ativos(obter_chave_gemini(), obter_chave_groq()))

    # 2. Barra de utilitários superior (Status de API e Ações Rápidas)
    api_key = obter_chave_gemini()
    chave_groq = obter_chave_groq()
    col_status, col_btn = st.columns([3, 1])

    with col_status:
        if api_key or chave_groq:
            fonte = "Sua planilha" if usuario else "PostgreSQL Neon"
            reserva = " + reserva Groq" if chave_groq and api_key else ""
            principal = "Google Gemini" if api_key else "Groq"
            st.caption(f"🟢 **IA Conectada:** {principal}{reserva} (Failover Ativo | {fonte})")
            contador = st.empty()
            _exibir_contador(contador)
        else:
            st.warning(
                "🔑 **Chave de API não detectada.** Adicione `GEMINI_API_KEY = 'sua_chave'` em `.streamlit/secrets.toml` "
                "ou configure a variável de ambiente no Streamlit Cloud.",
                icon="⚠️",
            )

    with col_btn:
        if st.button("🗑️ Limpar Chat", width="stretch", help="Reinicia o histórico da conversa"):
            st.session_state[chave] = [
                {
                    "role": "assistant",
                    "content": "Histórico reiniciado. Como posso te auxiliar com o estoque hoje?",
                }
            ]
            st.rerun()

    # 3. Sugestões de Perguntas Rápidas (Chips de Consulta Rápida)
    st.markdown("##### 💡 Sugestões de Análise Rápida:")
    col_q1, col_q2, col_q3 = st.columns(3)
    pergunta_clicada = None

    with col_q1:
        if st.button("🚨 Produtos Críticos Hoje", width="stretch", disabled=limite_atingido):
            pergunta_clicada = "Quais produtos estão em nível crítico hoje e quais os melhores fornecedores para reposição imediata?"
    with col_q2:
        if st.button("⏱️ Fornecedores Mais Ágeis", width="stretch", disabled=limite_atingido):
            pergunta_clicada = "Quais são os fornecedores com menor prazo de entrega (lead time mais rápido) para cada produto?"
    with col_q3:
        if st.button("💰 Melhores Preços de Cotação", width="stretch", disabled=limite_atingido):
            pergunta_clicada = "Qual fornecedor oferece o menor preço unitário por produto e qual a economia estimada?"

    # 4. Renderiza histórico de mensagens
    for msg in mensagens:
        avatar = "🤖" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg.get("origem"):
                st.caption(_rotulo_origem(msg["origem"]))

    # 5. Captura entrada do usuário (seja via digitação ou botão de prompt rápido)
    if limite_atingido:
        st.info(
            f"🔒 Limite de {LIMITE_PERGUNTAS_SESSAO} perguntas por sessão atingido. "
            "Este limite protege a cota da API nesta demonstração pública."
        )
    user_prompt = st.chat_input(
        "Ex: Qual o fornecedor mais vantajoso para o produto X considerando prazo de entrega?",
        disabled=limite_atingido,
    )
    if pergunta_clicada:
        user_prompt = pergunta_clicada

    if user_prompt:
        agora = time.time()
        bloqueio = verificar_limite_perguntas(
            st.session_state.perguntas_feitas, st.session_state.ultimo_envio, agora
        )
        if bloqueio:
            st.warning(f"⏳ {bloqueio}")
            return
        st.session_state.ultimo_envio = agora

        # Registra mensagem do usuário
        mensagens.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        # 6. Extrai contexto do banco e gera resposta com streaming resiliente e feedback visual
        with st.chat_message("assistant", avatar="🤖"):
            if not api_key and not chave_groq:
                st.error(MSG_SEM_CHAVE)
                mensagens.append({"role": "assistant", "content": MSG_SEM_CHAVE})
            else:
                st.session_state.perguntas_feitas += 1
                _exibir_contador(contador)
                with st.spinner("A consultar fornecedores e a calcular análise com a IA..."):
                    if usuario:
                        dados = dados_planilha_para_contexto(*dados_usuario)
                        origem_dados = "PLANILHA ENVIADA PELO USUÁRIO"
                        contexto = montar_contexto(*dados, date.today(), origem=origem_dados)
                        enxuto = montar_contexto(*dados, date.today(), origem=origem_dados, enxuto=True)
                    else:
                        contexto = extrair_contexto_executivo_estoque(engine)
                        enxuto = extrair_contexto_executivo_estoque(engine, enxuto=True)
                    resposta = obter_resposta(
                        mensagens=mensagens[-10:], contexto_banco=contexto, api_key=api_key,
                        chave_groq=chave_groq, contexto_enxuto=enxuto,
                    )

                # Entrega com efeito de digitação (100% completo, sem cortes)
                st.write_stream(digitar(resposta.texto))
                if resposta.origem:
                    st.caption(_rotulo_origem(resposta.origem))
                mensagens.append({"role": "assistant", "content": resposta.texto, "origem": resposta.origem})
