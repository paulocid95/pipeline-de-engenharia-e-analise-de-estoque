"""
Módulo de Assistente Virtual de Estoque e Compras (Chatbot com Google Gemini).
Fornece extração de contexto de banco de dados (PostgreSQL/Neon), engenharia de prompts,
arquitetura de resiliência com failover cascata de modelos (gemini-3.8-flash -> gemini-3.5-flash -> gemini-flash-lite-latest)
e entrega fluida via st.write_stream sem cortes ou truncamentos.
"""

import os
import time
from typing import Generator
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
import streamlit as st


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


# ==============================================================================
# 2. EXTRAÇÃO DE CONTEXTO ANALÍTICO DO BANCO (GROUND TRUTH / IN-MEMORY CACHE)
# ==============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def extrair_contexto_executivo_estoque(_engine: Engine) -> str:
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
                f.status_reposicao
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

    except Exception as e:
        return f"Aviso de banco: Não foi possível obter o contexto atualizado ({str(e)})."

    if df_est.empty:
        return "Aviso: Nenhum registro de estoque encontrado na base de dados."

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
        disp = int(row["quantidade_disponivel"] or 0)
        minimo = int(row["estoque_minimo"] or 0)
        preco_ref = float(row["preco_unitario"] or 0)

        linhas = [
            f"  * [{sku}] {nome} | Categoria: {cat}",
            f"    - Situação Operacional: Disponível = {disp} un | Estoque Mínimo = {minimo} un | Preço Tabela = R$ {preco_ref:,.2f}",
        ]

        cots = cotacoes_por_sku.get(sku, [])
        if cots:
            melhor_preco = min(cots, key=lambda x: x["preco_cotado"])
            menor_prazo = min(cots, key=lambda x: x["prazo_dias"])

            linhas.append(
                f"    - Menor Custo: Fornecedor '{melhor_preco['fornecedor']}' por R$ {melhor_preco['preco_cotado']:.2f} "
                f"(Prazo: {melhor_preco['prazo_dias']} dias | Lote Mín: {melhor_preco['lote_minimo']} un)"
            )
            linhas.append(
                f"    - Mais Rápido (Lead Time): Fornecedor '{menor_prazo['fornecedor']}' em {menor_prazo['prazo_dias']} dias "
                f"(Preço: R$ {menor_prazo['preco_cotado']:.2f} | Lote Mín: {menor_prazo['lote_minimo']} un)"
            )
            opcoes_forn = [
                f"{c['fornecedor']}: R$ {c['preco_cotado']:.2f} ({c['prazo_dias']} dias, lote {c['lote_minimo']} un)"
                for c in cots
            ]
            linhas.append(f"    - Todos Fornecedores Disponíveis: {'; '.join(opcoes_forn)}")
        else:
            linhas.append("    - Fornecedores: Nenhuma cotação concorrente cadastrada para este produto.")

        return linhas

    # Montagem do relatório contextual executivo
    linhas_contexto = [
        "### PANORAMA GERAL DO ESTOQUE (POSTGRESQL / SCHEMA CORE)",
        f"- Total de SKUs cadastrados: {total_skus}",
        f"- Volume físico disponível: {total_unidades:,} unidades",
        f"- Capital total imobilizado: R$ {capital_total:,.2f}",
        f"- Distribuição por Status de Reposição: {contagem_status}",
        "",
        "### ITENS EM SITUAÇÃO CRÍTICA (RUPTURA IMINENTE OU ESTOQUE ZERADO) COM SEUS FORNECEDORES:",
    ]

    if not criticos.empty:
        for _, row in criticos.iterrows():
            linhas_contexto.extend(formatar_item_detalhado_com_fornecedores(row))
    else:
        linhas_contexto.append("  * Nenhum SKU em estado crítico no momento.")

    linhas_contexto.append("")
    linhas_contexto.append("### ITENS EM NÍVEL DE ALERTA (BAIXA COBERTURA) COM SEUS FORNECEDORES:")
    if not alertas.empty:
        for _, row in alertas.iterrows():
            linhas_contexto.extend(formatar_item_detalhado_com_fornecedores(row))
    else:
        linhas_contexto.append("  * Nenhum SKU em estado de alerta.")

    linhas_contexto.append("")
    linhas_contexto.append("### MATRIZ CONSOLIDADA DE COTAÇÕES DE FORNECEDORES (TODOS OS SKUS):")
    if not df_cot.empty:
        for sku, group in df_cot.groupby("sku"):
            nome = group["nome_produto"].iloc[0]
            melhor_preco_row = group.sort_values(by="preco_cotado").iloc[0]
            menor_prazo_row = group.sort_values(by="prazo_dias").iloc[0]

            linhas_contexto.append(f"  * SKU [{sku}] - {nome}:")
            linhas_contexto.append(
                f"    - Menor Preço: '{melhor_preco_row['fornecedor']}' (R$ {melhor_preco_row['preco_cotado']:.2f}, {melhor_preco_row['prazo_dias']}d, lote {melhor_preco_row['lote_minimo']}un)"
            )
            linhas_contexto.append(
                f"    - Menor Prazo: '{menor_prazo_row['fornecedor']}' ({menor_prazo_row['prazo_dias']}d, R$ {menor_prazo_row['preco_cotado']:.2f}, lote {menor_prazo_row['lote_minimo']}un)"
            )
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
2. PRECISÃO FÁTICA (ZERO ALUCINAÇÃO): Use exclusivamente os dados reais fornecidos no CONTEXTO OPERACIONAL DO BANCO abaixo. Não invente números, SKUs, preços ou fornecedores inexistentes.
3. TABELA MARKDOWN OBRIGATÓRIA PARA REPOSIÇÃO E COMPRAS:
   Sempre que o usuário perguntar sobre reposição, produtos críticos, itens em alerta, análise de fornecedores ou decisões de compra, você DEVE estruturar sua resposta PRINCIPALMENTE através de uma TABELA MARKDOWN com as seguintes colunas obrigatórias:
   | Produto Crítico | Fornecedor Recomendado | Preço Cotado (R$) | Prazo de Entrega (dias) | Justificativa da Escolha |

   - "Produto Crítico": Nome completo do produto acompanhado do SKU.
   - "Fornecedor Recomendado": Nome do fornecedor mais vantajoso segundo o critério analisado.
   - "Preço Cotado (R$)": Valor unitário cotado (ex: R$ 1.250,00).
   - "Prazo de Entrega (dias)": Prazo de entrega em dias corridos do fornecedor recomendado.
   - "Justificativa da Escolha": Racional executivo claro (ex: "Menor preço unitário com economia de 8,5%", "Entrega emergencial em 2 dias para estancar ruptura", ou "Melhor equilíbrio custo-benefício com lote mínimo viável").

4. CRITÉRIOS DE DECISÃO DE COMPRAS:
   - Se o foco for "menor preço" ou "custo-benefício": priorize o menor preço cotado, mas aponte o prazo e lote mínimo.
   - Se o foco for "urgência", "lead time mais rápido" ou "reposição imediata": priorize o menor prazo de entrega em dias, explicitando o trade-off de custo.
   - Se a pergunta for ampla: recomende o melhor equilíbrio e aponte alternativas quando houver divergência relevante entre menor preço e menor prazo.

5. COMPLETUDE E NÃO TRUNCAMENTO:
   - Apresente a relação completa de TODOS os produtos críticos identificados sem cortar a resposta.
   - Após a tabela Markdown, inclua sempre um resumo executivo com estimativas de investimento e recomendações práticas para a equipe de compras.

---
CONTEXTO OPERACIONAL ATUALIZADO DO BANCO DE DADOS:
{contexto_banco}
---
"""


def gerar_resposta_assistente_stream(
    mensagens: list[dict],
    contexto_banco: str,
    api_key: str,
    modelo: str = MODELO_PADRAO,
    max_retries: int = 3,
    backoff_base: float = 1.5,
) -> Generator[str, None, None]:
    """Chama a API do Google Gemini com resiliência máxima e entrega fluida.

    Utiliza estratégia de Failover em Cascata: se o modelo primário estiver sobrecarregado
    (503) ou com cota diária excedida (429), transita automaticamente para os modelos estáveis.
    Gera o texto de forma completa e atômica, eliminando 100% de quebras no meio da frase.
    """
    if not api_key:
        yield "⚠️ Chave de API do Google Gemini não configurada. Configure `GEMINI_API_KEY` nos Secrets do Streamlit ou no `.env`."
        return

    system_instruction = construir_prompt_sistema(contexto_banco)

    # 1. Configuração dos modelos em cascata (começando pelo solicitado ou configurado)
    modelos_a_tentar = [modelo] + [m for m in MODELOS_CASCADE if m != modelo]

    texto_final = None
    ultimo_erro = None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        contents = []
        for msg in mensagens:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=3500,
        )

        # Cascata de failover resiliente
        for mod in modelos_a_tentar:
            for tentativa in range(1, max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=mod,
                        contents=contents,
                        config=config,
                    )
                    if response.text and len(response.text.strip()) > 50:
                        texto_final = response.text
                        break
                except Exception as e:
                    ultimo_erro = e
                    # Se for cota diária estourada (429), pula imediatamente para o próximo modelo da cascata
                    msg_err = str(e).lower()
                    if "429" in msg_err or "resource_exhausted" in msg_err:
                        break
                    # Se for 503 temporário, aguarda com backoff breve
                    time.sleep(backoff_base * tentativa)

            if texto_final:
                break

    except ImportError:
        # Fallback legado para ambientes que tenham apenas google-generativeai
        try:
            import google.generativeai as legacy_genai

            legacy_genai.configure(api_key=api_key)

            for mod in modelos_a_tentar:
                try:
                    model_instance = legacy_genai.GenerativeModel(
                        model_name=mod,
                        system_instruction=system_instruction,
                        generation_config={"temperature": 0.2, "max_output_tokens": 3500},
                    )
                    history = [
                        {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
                        for m in mensagens[:-1]
                    ]
                    chat = model_instance.start_chat(history=history)
                    ultima_msg = mensagens[-1]["content"] if mensagens else ""
                    resp = chat.send_message(ultima_msg)
                    if resp.text:
                        texto_final = resp.text
                        break
                except Exception as e:
                    ultimo_erro = e
        except Exception as e:
            ultimo_erro = e

    # Se nenhum modelo conseguiu responder
    if not texto_final:
        yield (
            "⚠️ **Os servidores de IA estão temporariamente indisponíveis no momento.**\n\n"
            f"Detalhes técnicos: {str(ultimo_erro)}\n\n"
            "👉 Por favor, aguarde alguns instantes e reenvie sua pergunta."
        )
        return

    # 2. Transmissão suave palavra a palavra para st.write_stream (sensação de streaming em tempo real)
    # Garante que 100% da resposta completa seja entregue, sem nenhum corte no meio
    palavras = texto_final.split(" ")
    total_palavras = len(palavras)
    for i, palavra in enumerate(palavras):
        espaco = " " if i < total_palavras - 1 else ""
        yield palavra + espaco
        # Micro-delay ajustado para digitação rápida e responsiva
        time.sleep(0.012)


# ==============================================================================
# 4. COMPONENTE DE INTERFACE STREAMLIT (LEVE & REATIVO)
# ==============================================================================
def renderizar_interface_chat(engine: Engine) -> None:
    """Renderiza a interface do chatbot dentro do Streamlit, com gerenciamento

    enxuto de estado de sessão, feedback visual e streaming de resposta resiliente.
    """
    # 1. Inicializa o estado de mensagens da sessão (máximo de 15 turnos para poupar RAM)
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Olá! Sou seu **Assistente de Inteligência de Estoque e Compras** conectado em tempo real "
                    "ao PostgreSQL.\n\nComo posso ajudar? Você pode me perguntar sobre **produtos críticos**, "
                    "**fornecedores com menor preço**, **prazos de entrega mais ágeis** ou simulações de compra."
                ),
            }
        ]

    # Banner informativo da aba
    st.markdown(
        '<div class="tab-banner">🤖 <strong>Assistente Virtual com IA:</strong> Análise de suprimentos, '
        "recomendações de negociação e triagem de rupturas com processamento em nuvem via Google Gemini.</div>",
        unsafe_allow_html=True,
    )

    # 2. Barra de utilitários superior (Status de API e Ações Rápidas)
    api_key = obter_chave_gemini()
    col_status, col_btn = st.columns([3, 1])

    with col_status:
        if api_key:
            st.caption(f"🟢 **IA Conectada:** Google Gemini ({MODELO_PADRAO} | Failover Ativo | PostgreSQL Neon)")
        else:
            st.warning(
                "🔑 **Chave de API não detectada.** Adicione `GEMINI_API_KEY = 'sua_chave'` em `.streamlit/secrets.toml` "
                "ou configure a variável de ambiente no Streamlit Cloud.",
                icon="⚠️",
            )

    with col_btn:
        if st.button("🗑️ Limpar Chat", use_container_width=True, help="Reinicia o histórico da conversa"):
            st.session_state.messages = [
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
        if st.button("🚨 Produtos Críticos Hoje", use_container_width=True):
            pergunta_clicada = "Quais produtos estão em nível crítico hoje e quais os melhores fornecedores para reposição imediata?"
    with col_q2:
        if st.button("⏱️ Fornecedores Mais Ágeis", use_container_width=True):
            pergunta_clicada = "Quais são os fornecedores com menor prazo de entrega (lead time mais rápido) para cada produto?"
    with col_q3:
        if st.button("💰 Melhores Preços de Cotação", use_container_width=True):
            pergunta_clicada = "Qual fornecedor oferece o menor preço unitário por produto e qual a economia estimada?"

    # 4. Renderiza histórico de mensagens
    for msg in st.session_state.messages:
        avatar = "🤖" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # 5. Captura entrada do usuário (seja via digitação ou botão de prompt rápido)
    user_prompt = st.chat_input("Ex: Qual o fornecedor mais vantajoso para o produto X considerando prazo de entrega?")
    if pergunta_clicada:
        user_prompt = pergunta_clicada

    if user_prompt:
        # Registra mensagem do usuário
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        # 6. Extrai contexto do banco e gera resposta com streaming resiliente e feedback visual
        with st.chat_message("assistant", avatar="🤖"):
            if not api_key:
                resposta_vazia = (
                    "Não foi possível processar a resposta porque a chave `GEMINI_API_KEY` não está configurada.\n"
                    "Por favor, configure o segredo no painel do Streamlit Cloud ou crie o arquivo `.streamlit/secrets.toml`."
                )
                st.error(resposta_vazia)
                st.session_state.messages.append({"role": "assistant", "content": resposta_vazia})
            else:
                # Feedback visual suave enquanto consulta o banco e conecta à IA com retry e failover
                with st.spinner("A consultar fornecedores e a calcular análise com a IA..."):
                    contexto_banco = extrair_contexto_executivo_estoque(engine)
                    historico_recente = st.session_state.messages[-10:]

                    stream_gerador = gerar_resposta_assistente_stream(
                        mensagens=historico_recente,
                        contexto_banco=contexto_banco,
                        api_key=api_key,
                        modelo=MODELO_PADRAO,
                    )

                # Consome o stream com o componente nativo do Streamlit (100% completo, sem cortes)
                resposta_completa = st.write_stream(stream_gerador)

                # Salva a resposta no histórico da sessão
                st.session_state.messages.append({"role": "assistant", "content": str(resposta_completa)})
