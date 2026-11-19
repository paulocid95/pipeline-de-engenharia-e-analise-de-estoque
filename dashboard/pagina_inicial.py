"""Página inicial (apresentação do sistema) com os 3 botões de entrada.

O visual e os efeitos ficam em dashboard/inicio/ (estilo.css e efeitos.js).
Os botões são nativos do Streamlit, porque disparam ações do app
(abrir a demonstração, baixar a planilha, enviar arquivos).
"""

import base64
from datetime import date
from functools import cache
from pathlib import Path

import streamlit as st

from planilha_exemplo import NOME_ARQUIVO, montar_planilha_exemplo

PASTA = Path(__file__).parent / "inicio"
URL_GITHUB = "https://github.com/paulocid95/pipeline-de-engenharia-e-analise-de-estoque"


@cache
def _arquivo(nome: str) -> str:
    return (PASTA / nome).read_text(encoding="utf-8")


def _script(codigo: str) -> str:
    """Embala o JavaScript em base64.

    O filtro de segurança do st.html (DOMPurify) descarta scripts cujo texto
    contém trechos parecidos com tags (ex.: "<li>"); codificado, ele passa intacto.
    """
    b64 = base64.b64encode(codigo.encode("utf-8")).decode("ascii")
    return (
        "(function(){var b=Uint8Array.from(atob('" + b64 + "'),function(c){return c.charCodeAt(0)});"
        "(0,eval)(new TextDecoder().decode(b));})();"
    )


def _html(conteudo: str) -> None:
    st.html(conteudo, unsafe_allow_javascript=True)


@st.cache_data(ttl=300, show_spinner=False)
def _gerar_planilha(hoje: date) -> bytes:
    from dashboard.dados import carregar_dados_analiticos, carregar_dados_cotacoes, carregar_ocorrencias

    return montar_planilha_exemplo(
        carregar_dados_analiticos(), carregar_dados_cotacoes(), carregar_ocorrencias(), hoje,
    )


def _planilha_exemplo() -> bytes:
    """Gerada só quando o visitante clica em baixar (a página inicial não consulta o banco)."""
    return _gerar_planilha(date.today())


def _abrir_demonstracao() -> None:
    st.query_params["tela"] = "painel"


def _abrir_envio() -> None:
    st.query_params["tela"] = "envio"


FUNDO = """
<style>__CSS__</style>
<div id="si-fundo">
  <canvas id="si-rede"></canvas>
  <div class="si-blob si-b1"></div><div class="si-blob si-b2"></div><div class="si-blob si-b3"></div>
  <div id="si-luz"></div>
</div>
<script>__JS__</script>
"""

HEROI_TEXTO = """
<div class="si si-hero">
  <span class="si-tag"><span class="si-ponto"></span> Pipeline de dados + IA para estoque e compras</span>
  <h1>Sua planilha bagunçada vira <span class="si-grad">decisão de compra</span> em segundos.</h1>
  <p class="si-lead">Envie o arquivo do jeito que ele sai do seu sistema. O <b>Supply Intelligence</b> limpa e padroniza
  os dados, analisa seu estoque, ranqueia seus fornecedores por preço, prazo e confiabilidade e responde suas dúvidas
  com inteligência artificial.</p>
</div>
"""

HEROI_SELOS = """
<div class="si si-selos"><span>🔒 Seus dados ficam só na sua sessão</span><span>⚡ Resultado na hora</span><span>📱 Funciona no celular</span></div>
"""

HEROI_PAINEL = """
<div class="si si-palco">
  <div class="si-painel si-tilt">
    <div class="si-topo"><i></i><i></i><i></i><span>Exemplo ilustrativo</span></div>
    <div class="si-kpis">
      <div class="si-kpi"><small>Produtos</small><strong data-conta="248">0</strong></div>
      <div class="si-kpi"><small>Capital parado</small><strong>R$ <span data-conta="182">0</span> mil</strong></div>
      <div class="si-kpi"><small>Em ruptura</small><strong style="color:#ff7a8a" data-conta="7">0</strong></div>
    </div>
    <div class="si-barras">
      <div style="height:55%"></div><div style="height:80%;animation-delay:.3s"></div><div style="height:40%;animation-delay:.6s"></div>
      <div style="height:95%;animation-delay:.9s"></div><div style="height:65%;animation-delay:1.2s"></div><div style="height:75%;animation-delay:1.5s"></div>
    </div>
    <div class="si-forns">
      <span class="si-pill bom">🟢 Fornecedor B · 86</span><span class="si-pill med">🟡 Fornecedor A · 71</span><span class="si-pill per">🔴 Fornecedor D · 47</span>
    </div>
    <div class="si-chip-ia">🤖 <b>IA:</b> Compre o iPhone 15 com o Fornecedor B, entrega em 4 dias<span class="si-digitando"><i></i><i></i><i></i></span></div>
  </div>
</div>
"""

SECOES = """
<div class="si">
<section>
  <div class="si-rev">
    <span class="si-tag">Como funciona</span>
    <h2>Quatro passos, <span class="si-grad">zero trabalho manual</span></h2>
    <p class="si-lead">Clique em cada passo para ver em detalhes o que acontece com os seus dados.</p>
  </div>
  <div class="si-passos">
    <div class="si-card si-passo si-tilt si-rev" data-p="0">
      <div class="si-ilus"></div>
      <div class="si-num">PASSO 01</div><h3>Envie seus dados</h3>
      <p>Excel ou CSV, do jeito que sai do seu sistema.</p><div class="si-mais">Ver detalhes →</div>
    </div>
    <div class="si-card si-passo si-tilt si-rev" data-p="1">
      <div class="si-ilus"></div>
      <div class="si-num">PASSO 02</div><h3>Higienização automática</h3>
      <p>Formatos corrigidos, nomes unificados, duplicados resolvidos.</p><div class="si-mais">Ver detalhes →</div>
    </div>
    <div class="si-card si-passo si-tilt si-rev" data-p="2">
      <div class="si-ilus"></div>
      <div class="si-num">PASSO 03</div><h3>Análise inteligente</h3>
      <p>Status do estoque, ranking de fornecedores e melhor compra.</p><div class="si-mais">Ver detalhes →</div>
    </div>
    <div class="si-card si-passo si-tilt si-rev" data-p="3">
      <div class="si-ilus"></div>
      <div class="si-num">PASSO 04</div><h3>Pergunte à IA</h3>
      <p>Tire dúvidas em português sobre estoque e fornecedores.</p><div class="si-mais">Ver detalhes →</div>
    </div>
  </div>
  <div class="si-card si-detalhe" id="si-detalhe"></div>
</section>

<section>
  <div class="si-rev">
    <span class="si-tag">Higienização ao vivo</span>
    <h2>Do caos ao dado <span class="si-grad">pronto para análise</span></h2>
    <p class="si-lead">É assim que a planilha de um fornecedor costuma chegar. Clique em <b>Higienizar</b> e veja cada correção acontecer.</p>
  </div>
  <div class="si-card si-ad si-rev">
    <div class="si-ad-topo"><b class="si-ad-titulo">❌ Antes: dados brutos</b><button class="si-btn" type="button">✨ Higienizar</button></div>
    <div class="si-rolagem"><table class="si-tabela">
      <thead><tr><th>Produto</th><th>Fornecedor</th><th>Preço</th><th>Estoque</th><th>Categoria</th></tr></thead>
      <tbody></tbody>
    </table></div>
    <div class="si-rel"></div>
  </div>
</section>

<section>
  <div class="si-rev">
    <span class="si-tag">O que você recebe</span>
    <h2>Um painel completo de <span class="si-grad">inteligência de compras</span></h2>
  </div>
  <div class="si-recursos">
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(57,135,229,.18)">📦</div><h3>Visão do estoque</h3>
      <p>Cada item classificado como crítico, alerta, normal ou excesso, com os limites do seu negócio. Veja onde está o capital parado.</p></div>
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(144,133,233,.18)">🛡️</div><h3>Ranking & Risco</h3>
      <p>Nota de 0 a 100 por fornecedor: preço, prazo, lote mínimo e histórico de problemas. Alertas de fornecedor perigoso.</p></div>
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(25,158,112,.18)">🛒</div><h3>Simulador de compras</h3>
      <p>A melhor opção de cada produto lado a lado com a mais barata e a mais rápida, explicando por que cada uma perdeu.</p></div>
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(224,160,32,.18)">📈</div><h3>Previsão de demanda <span class="si-emb">EM BREVE</span></h3>
      <p>Quando o produto vai acabar e quanto comprar, respeitando o prazo do fornecedor e o lote mínimo.</p></div>
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(213,81,129,.18)">🤖</div><h3>Assistente de IA</h3>
      <p>Pergunte em português. A IA conhece todo o estoque e nunca recomenda um fornecedor perigoso como opção principal.</p></div>
    <div class="si-card si-recurso si-tilt si-rev"><div class="si-ico" style="background:rgba(217,89,38,.18)">🧾</div><h3>Relatório de limpeza</h3>
      <p>Transparência total: cada correção feita nos dados aparece listada, com as linhas descartadas para revisão.</p></div>
  </div>
</section>

<section>
  <div class="si-rev">
    <span class="si-tag">O que sua planilha precisa ter</span>
    <h2>Quanto mais dados, <span class="si-grad">mais análises</span></h2>
    <p class="si-lead">Só o estoque já basta para começar. Clique nos tipos de dado para ver o que cada um libera.</p>
  </div>
  <div class="si-desbloq si-rev">
    <div class="si-card si-fontes" id="si-fontes"></div>
    <div class="si-card si-libera" id="si-libera"></div>
  </div>
</section>

<div class="si-cta si-rev">
  <span class="si-tag">Pronto para ver funcionando?</span>
  <h2>Explore o painel com <span class="si-grad">dados de demonstração</span></h2>
  <p class="si-lead">Estoque, fornecedores, ranking de risco e o assistente de IA, tudo com dados de exemplo.</p>
</div>
</div>
"""

RODAPE = f"""
<div class="si si-rodape">
  <div class="si-stack"><span>🐍 Python</span><span>🐼 pandas</span><span>🐘 PostgreSQL</span><span>📊 Plotly</span><span>🎈 Streamlit</span><span>✨ Gemini</span></div>
  Projeto de portfólio · Pipeline de engenharia e análise de estoque ·
  <a href="{URL_GITHUB}" target="_blank" rel="noopener">Código no GitHub</a>
</div>
"""


def renderizar() -> None:
    """Desenha a página inicial completa."""
    _html(FUNDO.replace("__CSS__", _arquivo("estilo.css")).replace("__JS__", _script(_arquivo("efeitos.js"))))

    texto, painel = st.columns([1.05, 0.95], vertical_alignment="center", gap="large")
    with texto:
        _html(HEROI_TEXTO)
        with st.container(key="si_acoes", horizontal=True, gap="small"):
            with st.container(key="si_demo", width="content"):
                st.button("🚀 Ver demonstração ao vivo", type="primary", on_click=_abrir_demonstracao)
            st.download_button(
                "📥 Baixar planilha de exemplo",
                data=_planilha_exemplo,
                file_name=NOME_ARQUIVO,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                on_click="ignore",
                help="Excel com estoque, cotações, ocorrências e vendas da demonstração, bagunçados de propósito",
            )
            st.button("📤 Analisar minha planilha", on_click=_abrir_envio,
                      help="Envie seu Excel ou CSV: nós limpamos e analisamos")
        _html(HEROI_SELOS)
    with painel:
        _html(HEROI_PAINEL)

    _html(SECOES)
    with st.container(key="si_cta", horizontal_alignment="center"):
        st.button("🚀 Abrir a demonstração", type="primary", on_click=_abrir_demonstracao, key="si_demo_final")
    _html(RODAPE)
