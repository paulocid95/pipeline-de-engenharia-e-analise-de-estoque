"""Tela de envio: o usuário manda a planilha, confere o que foi reconhecido, define limites e revisa a limpeza.

Tudo fica só na sessão (st.session_state): nada é gravado no banco.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from dashboard.componentes import cabecalho
from dashboard.estilo import aplicar_estilo
from higienizacao import (
    ESTOQUE, LINHAS_MAXIMAS, NOMES_TIPO, ROTULOS_COLUNA, TAMANHO_MAXIMO_MB, TIPOS, ErroArquivo, higienizar,
    ler_arquivo, preparar, remapear,
)
from higienizacao.colunas import ESQUEMAS, OBRIGATORIAS, faltando
from higienizacao.exportacao import NOME_ARQUIVO_LIMPO, planilha_higienizada
from planilha_exemplo import NOME_ARQUIVO
from regras_estoque import LIMITE_ALERTA, LIMITE_EXCESSO

IGNORAR = "ignorar"
ROTULO_TIPO = {**{t: f"{NOMES_TIPO[t]}" for t in TIPOS}, IGNORAR: "Ignorar esta tabela"}
ICONE_TIPO = {"estoque": "📦", "cotacoes": "💰", "ocorrencias": "⚠️", "vendas": "📈", IGNORAR: "🚫"}
ICONE_NIVEL = {"ok": "✅", "aviso": "⚠️", "erro": "❌"}
LIBERA = {
    "estoque": "Visão geral, alertas de ruptura, tabela e assistente de IA",
    "cotacoes": "Fornecedores e simulador de compras",
    "ocorrencias": "Ranking & Risco com a nota de confiabilidade",
    "vendas": "Previsão de demanda e sugestão de compra",
}

# Chaves do st.session_state
K_ASSINATURA, K_ENTRADAS, K_ERROS = "envio_assinatura", "envio_entradas", "envio_erros"
K_RESULTADO, K_DECISOES, K_UPLOADER = "envio_resultado", "envio_decisoes", "envio_uploader"
# Dados que alimentam o painel: guardados à parte para sobreviver à troca de tela
K_MEUS_DADOS = "meus_dados"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ------------------------------------------------------------------------------
# Estado
# ------------------------------------------------------------------------------
def _invalidar_resultado() -> None:
    st.session_state.pop(K_RESULTADO, None)


def _limpar_widgets() -> None:
    """Esquece as escolhas feitas para os arquivos anteriores (tipo de tabela, colunas, dúvidas)."""
    for chave in [k for k in st.session_state if str(k).startswith(("envio_tipo_", "envio_col_", "envio_duvida_"))]:
        del st.session_state[chave]


def _recomecar() -> None:
    proximo = st.session_state.get(K_UPLOADER, 0) + 1     # nova chave = campo de envio vazio
    for chave in [k for k in st.session_state if str(k).startswith("envio_")]:
        del st.session_state[chave]
    st.session_state[K_UPLOADER] = proximo


def _voltar_ao_inicio() -> None:
    st.query_params.pop("tela", None)


def enviar_outra_planilha() -> None:
    """Descarta os dados atuais e abre a tela de envio vazia."""
    _recomecar()
    st.session_state.pop(K_MEUS_DADOS, None)
    st.session_state.pop("messages_planilha", None)
    st.query_params["tela"] = "envio"


def _abrir_analise(alerta: int) -> None:
    st.session_state[K_MEUS_DADOS] = {
        "resultado": st.session_state[K_RESULTADO], "alerta": alerta, "enviado_em": datetime.now(),
    }
    st.session_state.pop("messages_planilha", None)     # dados novos, conversa nova
    st.query_params["tela"] = "meus_dados"


def _ler_envio(arquivos) -> None:
    """Lê os arquivos só quando o conjunto enviado muda."""
    assinatura = tuple((a.name, a.size) for a in arquivos)
    if st.session_state.get(K_ASSINATURA) == assinatura:
        return
    tabelas, erros = [], []
    for arquivo in arquivos:
        try:
            tabelas.extend(ler_arquivo(arquivo.name, arquivo.getvalue()))
        except ErroArquivo as erro:
            erros.append(str(erro))
    _limpar_widgets()
    st.session_state[K_ASSINATURA] = assinatura
    st.session_state[K_ENTRADAS] = preparar(tabelas)
    st.session_state[K_ERROS] = erros
    st.session_state[K_DECISOES] = {}
    _invalidar_resultado()


# ------------------------------------------------------------------------------
# Passo 1: o que a planilha precisa ter + envio
# ------------------------------------------------------------------------------
def _guia() -> None:
    with st.expander("📋 O que a sua planilha precisa ter", expanded=K_ENTRADAS not in st.session_state):
        st.markdown(
            f"Aceitamos **Excel (.xlsx)** com abas ou **arquivos CSV** separados, até **{TAMANHO_MAXIMO_MB} MB** e "
            f"**{LINHAS_MAXIMAS:,} linhas** por arquivo. ".replace(",", ".")
            + "Os nomes das colunas não precisam ser iguais aos daqui: "
            "nós reconhecemos variações, cabeçalhos fora do lugar e linhas de total."
        )
        st.markdown(
            "| Dado | Colunas obrigatórias | Opcionais | O que libera |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| 📦 **Estoque** (obrigatório) | produto, quantidade, preço | código/SKU, categoria, fornecedor, estoque mínimo | "
            f"{LIBERA['estoque']} |\n"
            f"| 💰 **Cotações** | produto (ou SKU), fornecedor, preço | prazo de entrega, lote mínimo | {LIBERA['cotacoes']} |\n"
            f"| ⚠️ **Ocorrências** | fornecedor, tipo, data | gravidade, situação, data de resolução | {LIBERA['ocorrencias']} |\n"
            f"| 📈 **Vendas** | data, produto (ou SKU), quantidade vendida | — | {LIBERA['vendas']} |"
        )
        from dashboard.pagina_inicial import _planilha_exemplo
        st.download_button(
            "📥 Baixar planilha de exemplo para usar como base", data=_planilha_exemplo, file_name=NOME_ARQUIVO,
            mime=MIME_XLSX, on_click="ignore",
        )


def _envio() -> None:
    st.subheader("1️⃣ Envie seus arquivos")
    arquivos = st.file_uploader(
        "Arraste o Excel ou os CSVs aqui",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        max_upload_size=TAMANHO_MAXIMO_MB,
        key=f"{K_UPLOADER}_{st.session_state.get(K_UPLOADER, 0)}",
        help="Seus dados ficam só nesta sessão e somem quando você fecha a página.",
    )
    if arquivos:
        _ler_envio(arquivos)
    elif K_ENTRADAS in st.session_state:
        for chave in (K_ASSINATURA, K_ENTRADAS, K_ERROS, K_RESULTADO, K_DECISOES):
            st.session_state.pop(chave, None)
    for erro in st.session_state.get(K_ERROS, []):
        st.error(f"❌ {erro}")


# ------------------------------------------------------------------------------
# Passo 2: conferir abas e colunas
# ------------------------------------------------------------------------------
def _trocar_tipo(i: int) -> None:
    entradas = st.session_state[K_ENTRADAS]
    novo = st.session_state[f"envio_tipo_{i}"]
    entradas[i] = remapear(entradas[i], novo) if novo != IGNORAR else _ignorada(entradas[i])
    _invalidar_resultado()


def _ignorada(entrada):
    entrada.tipo = None
    return entrada


def _definir_coluna(i: int, canonica: str) -> None:
    entrada = st.session_state[K_ENTRADAS][i]
    escolha = st.session_state[f"envio_col_{i}_{canonica}"]
    if escolha is None:
        entrada.mapa.pop(canonica, None)
    else:
        for c, idx in list(entrada.mapa.items()):     # uma coluna da planilha só pode ter um papel
            if idx == escolha:
                del entrada.mapa[c]
        entrada.mapa[canonica] = escolha
    _invalidar_resultado()


def _nome_coluna(entrada, idx: int) -> str:
    valor = entrada.cabecalhos[idx] if idx < len(entrada.cabecalhos) else None
    return str(valor).strip() if valor is not None and str(valor).strip() else f"Coluna {idx + 1}"


def _cartao_tabela(i: int, entrada) -> None:
    tipo = entrada.tipo or IGNORAR
    with st.container(border=True):
        topo, seletor = st.columns([3, 2], vertical_alignment="center")
        topo.markdown(f"**{ICONE_TIPO[tipo]} {entrada.origem}**  \n"
                      f"<small>{max(len(entrada.bruta) - entrada.linha_cabecalho - 1, 0)} linhas · "
                      f"cabeçalho na linha {entrada.linha_cabecalho + 1}</small>", unsafe_allow_html=True)
        seletor.selectbox(
            "Esta tabela é:", options=[*TIPOS, IGNORAR], index=[*TIPOS, IGNORAR].index(tipo),
            format_func=lambda t: f"{ICONE_TIPO[t]} {ROTULO_TIPO[t]}", key=f"envio_tipo_{i}",
            on_change=_trocar_tipo, args=(i,),
        )
        if entrada.tipo is None:
            st.caption("Esta tabela não será usada. Se ela tiver dados, escolha o tipo acima.")
            return

        reconhecidas = [f"`{_nome_coluna(entrada, entrada.mapa[c])}` → **{ROTULOS_COLUNA[c]}**"
                        for c in ESQUEMAS[entrada.tipo] if c in entrada.mapa]
        st.markdown("Colunas reconhecidas: " + (" · ".join(reconhecidas) if reconhecidas else "nenhuma"))

        pendentes = faltando(entrada.mapa, entrada.tipo)
        opcoes = list(range(len(entrada.cabecalhos)))
        if pendentes:
            st.warning("Não encontramos algumas colunas obrigatórias. Aponte qual coluna da planilha corresponde a cada uma:")
            for grupo in pendentes:
                canonica = grupo[0]
                rotulo = " ou ".join(ROTULOS_COLUNA[c] for c in grupo)
                st.selectbox(f"Qual coluna é **{rotulo}**?", options=opcoes, index=None,
                             format_func=lambda idx: _nome_coluna(entrada, idx), placeholder="Escolha a coluna",
                             key=f"envio_col_{i}_{canonica}", on_change=_definir_coluna, args=(i, canonica))

        opcionais = [c for c in ESQUEMAS[entrada.tipo] if c not in entrada.mapa
                     and not any(c in g for g in pendentes)]
        with st.expander("Ajustar colunas e ver as primeiras linhas"):
            for canonica in opcionais:
                st.selectbox(f"{ROTULOS_COLUNA[canonica]} (opcional)", options=opcoes, index=None,
                             format_func=lambda idx: _nome_coluna(entrada, idx), placeholder="Não tenho esta coluna",
                             key=f"envio_col_{i}_{canonica}", on_change=_definir_coluna, args=(i, canonica))
            previa = entrada.bruta.iloc[entrada.linha_cabecalho + 1: entrada.linha_cabecalho + 6].copy()
            previa.columns = [_nome_coluna(entrada, j) for j in range(previa.shape[1])]
            st.dataframe(previa.astype(str).replace({"None": "", "nan": ""}), hide_index=True, width="stretch")


def _conferencia() -> bool:
    """Mostra o que foi reconhecido. Retorna True se dá para higienizar."""
    entradas = st.session_state.get(K_ENTRADAS) or []
    if not entradas:
        if st.session_state.get(K_ASSINATURA):
            st.warning("Não encontramos tabelas com dados nos arquivos enviados.")
        return False
    st.subheader("2️⃣ Confira o que reconhecemos")
    st.caption("Identificamos cada aba/arquivo e suas colunas automaticamente. Corrija se algo estiver errado.")
    for i, entrada in enumerate(entradas):
        _cartao_tabela(i, entrada)

    tipos = {e.tipo for e in entradas if e.tipo}
    if ESTOQUE not in tipos:
        st.error("❌ Precisamos de pelo menos uma tabela de **Estoque** (produto, quantidade e preço).")
        return False
    if any(faltando(e.mapa, e.tipo) for e in entradas if e.tipo):
        st.info("👆 Aponte as colunas obrigatórias que faltam para continuar.")
        return False
    nao_enviados = [t for t in TIPOS if t not in tipos]
    if nao_enviados:
        st.caption("Não enviados (opcionais): " + " · ".join(
            f"{ICONE_TIPO[t]} {NOMES_TIPO[t]} libera {LIBERA[t].lower()}" for t in nao_enviados))
    return True


# ------------------------------------------------------------------------------
# Passo 3: limites e higienização
# ------------------------------------------------------------------------------
def _limites() -> tuple[int, int]:
    st.subheader("3️⃣ Limites de estoque do seu negócio")
    st.markdown(
        f"Informe a partir de quantas unidades um item entra em **alerta** (estoque baixo) e em **excesso**. "
        f"**Se não alterar, usaremos o nosso padrão: alerta até {LIMITE_ALERTA} unidades e excesso acima de "
        f"{LIMITE_EXCESSO}.** Produtos com uma coluna de *estoque mínimo* na planilha usam o próprio valor no alerta."
    )
    c1, c2 = st.columns(2)
    alerta = c1.number_input("⚠️ Alerta: até quantas unidades?", min_value=1, value=LIMITE_ALERTA, step=1,
                             key="envio_alerta", on_change=_invalidar_resultado)
    excesso = c2.number_input("📦 Excesso: acima de quantas unidades?", min_value=2, value=LIMITE_EXCESSO, step=1,
                              key="envio_excesso", on_change=_invalidar_resultado)
    if excesso <= alerta:
        st.error("O limite de excesso precisa ser maior que o de alerta.")
    elif (alerta, excesso) == (LIMITE_ALERTA, LIMITE_EXCESSO):
        st.caption(f"ℹ️ Usando o padrão do sistema ({LIMITE_ALERTA} / {LIMITE_EXCESSO}).")
    return int(alerta), int(excesso)


def _executar(alerta: int, excesso: int) -> None:
    entradas = [e for e in st.session_state[K_ENTRADAS] if e.tipo]
    with st.spinner("🧹 Higienizando seus dados..."):
        st.session_state[K_RESULTADO] = higienizar(
            entradas, limite_alerta=alerta, limite_excesso=excesso, decisoes=st.session_state.get(K_DECISOES, {}),
        )


# ------------------------------------------------------------------------------
# Passo 4: revisão
# ------------------------------------------------------------------------------
def _resumo(resultado) -> None:
    descartes = pd.DataFrame(resultado.descartes)
    def qtd(df):
        return 0 if df is None else len(df)
    with st.container(horizontal=True, wrap=True, gap="small"):
        for rotulo, valor in [
            ("📦 Produtos", qtd(resultado.estoque)),
            ("💰 Cotações", qtd(resultado.cotacoes)),
            ("⚠️ Ocorrências", qtd(resultado.ocorrencias)),
            ("📈 Dias de vendas", 0 if resultado.vendas is None else resultado.vendas["data"].nunique()),
            ("🗑️ Descartadas", len(descartes)),
        ]:
            st.metric(rotulo, valor, border=True, width=190)


def _duvidas(resultado, alerta, excesso) -> None:
    if not resultado.duvidas:
        return
    st.warning(f"🤔 Encontramos **{len(resultado.duvidas)}** caso(s) que parecem ser a mesma coisa escrita de "
               "jeitos diferentes. Confirme para unirmos; sem confirmação, eles ficam separados.")
    decisoes = st.session_state.setdefault(K_DECISOES, {})
    with st.form("envio_form_duvidas", border=True):
        escolhas = {}
        for i, d in enumerate(resultado.duvidas):
            tipo = "Fornecedor" if d.tipo == "fornecedor" else "Produto"
            escolhas[d.chave] = st.segmented_control(
                f"{tipo}: **{d.a}** parece ser **{d.b}**? ({d.similaridade:.0%} parecidos)",
                options=["Unir", "Manter separados"],
                default="Unir" if decisoes.get(d.chave) else "Manter separados",
                key=f"envio_duvida_{i}",
            )
        if st.form_submit_button("✔️ Aplicar decisões", type="primary"):
            st.session_state[K_DECISOES] = {k: v == "Unir" for k, v in escolhas.items()}
            _executar(alerta, excesso)
            st.rerun()


def _relatorio(resultado) -> None:
    st.markdown("#### 🧾 Relatório da higienização")
    por_aba: dict[str, list] = {}
    for item in resultado.relatorio:
        por_aba.setdefault(item.aba, []).append(item)
    if not por_aba:
        st.success("✨ Seus dados já estavam limpos: nenhuma correção foi necessária.")
    for aba, itens in por_aba.items():
        with st.container(border=True):
            st.markdown(f"**{aba}**")
            for item in itens:
                linha = f"{ICONE_NIVEL[item.nivel]} {item.mensagem}"
                if item.quantidade:
                    linha += f": **{item.quantidade}**"
                st.markdown(linha)
                if item.exemplos:
                    st.caption("  ·  ".join(f"“{a}” → “{b}”" for a, b in item.exemplos))

    if resultado.descartes:
        with st.expander(f"🗑️ Ver as {len(resultado.descartes)} linha(s) descartadas e o motivo"):
            st.dataframe(pd.DataFrame(resultado.descartes).rename(columns={
                "aba": "Tabela", "linha": "Linha", "motivo": "Motivo", "conteudo": "Conteúdo original"}),
                hide_index=True, width="stretch")
    if resultado.colunas_ignoradas:
        st.caption("Colunas não utilizadas nas análises: " + " · ".join(
            f"{aba}: {', '.join(cols)}" for aba, cols in resultado.colunas_ignoradas.items()))


def _revisao(alerta: int, excesso: int) -> None:
    resultado = st.session_state.get(K_RESULTADO)
    if resultado is None:
        return
    st.divider()
    st.subheader("4️⃣ Revise a higienização")
    if not resultado.ok:
        st.error("❌ Nenhum produto válido foi encontrado no estoque. Confira as colunas de quantidade e preço.")
        _relatorio(resultado)
        return
    _resumo(resultado)
    _duvidas(resultado, alerta, excesso)
    _relatorio(resultado)
    st.divider()
    st.button("📊 Ver a análise dos meus dados", type="primary", width="stretch",
              on_click=_abrir_analise, args=(alerta,))
    st.download_button(
        "📥 Baixar meus dados higienizados (Excel)", data=lambda: planilha_higienizada(resultado),
        file_name=NOME_ARQUIVO_LIMPO, mime=MIME_XLSX, on_click="ignore", width="stretch",
        help="Uma aba por tabela, já padronizada. Você pode enviar este arquivo de novo depois.",
    )


# ------------------------------------------------------------------------------
# Página
# ------------------------------------------------------------------------------
def renderizar() -> None:
    aplicar_estilo()
    topo1, topo2 = st.columns([1, 1])
    topo1.button("← Voltar ao início", type="tertiary", on_click=_voltar_ao_inicio)
    if K_ENTRADAS in st.session_state:
        with topo2:
            st.button("↺ Recomeçar com outros arquivos", type="tertiary", on_click=_recomecar, key="envio_recomecar")
    cabecalho(
        titulo="Analise a sua planilha",
        texto="Envie o arquivo do jeito que ele sai do seu sistema. Nós reconhecemos as colunas, limpamos os dados "
              "e mostramos tudo o que foi corrigido antes da análise.",
        conectado=None,
        chips=["🔒 Dados só nesta sessão", f"📄 Excel ou CSV até {TAMANHO_MAXIMO_MB} MB"],
    )
    _guia()
    _envio()
    if not _conferencia():
        return
    alerta, excesso = _limites()
    pode = excesso > alerta
    rotulo = "🧹 Higienizar novamente" if K_RESULTADO in st.session_state else "🧹 Higienizar meus dados"
    if st.button(rotulo, type="primary", disabled=not pode, width="stretch"):
        _executar(alerta, excesso)
    _revisao(alerta, excesso)


# ------------------------------------------------------------------------------
# Painel com os dados enviados
# ------------------------------------------------------------------------------
def renderizar_meus_dados() -> None:
    from dashboard.painel import Fonte, renderizar as renderizar_painel

    dados = st.session_state.get(K_MEUS_DADOS)
    if dados is None:
        # Página recarregada ou link aberto em outra aba: os dados ficam só na sessão em que foram enviados
        aplicar_estilo()
        st.button("← Voltar ao início", type="tertiary", on_click=_voltar_ao_inicio)
        cabecalho(
            titulo="Seus dados não estão mais aqui",
            texto="Por segurança, a planilha fica só na sessão em que foi enviada e some quando a página é "
                  "recarregada ou fechada. Envie de novo para ver a análise.",
            conectado=None, chips=["🔒 Nada é guardado"],
        )
        st.button("📤 Enviar minha planilha", type="primary", on_click=enviar_outra_planilha, key="meus_dados_enviar")
        return
    resultado = dados["resultado"]
    renderizar_painel(Fonte.da_planilha(
        resultado, limite_alerta=dados["alerta"], enviado_em=dados["enviado_em"],
        planilha_limpa=lambda: planilha_higienizada(resultado),
    ))
