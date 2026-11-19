"""Dashboard Executivo de Estoque (Streamlit).

Este arquivo escolhe a tela: página inicial, envio de planilha, painel com os dados
do usuário ou a demonstração. O painel fica em dashboard/painel.py.
"""

import streamlit as st

from dashboard import pagina_envio, pagina_inicial, painel
from dashboard.dados import (
    carregar_dados_analiticos,
    carregar_dados_cotacoes,
    carregar_ocorrencias,
    obter_conexao,
)

st.set_page_config(
    page_title="Dashboard Executivo de Estoque",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="auto",
)

tela = st.query_params.get("tela")
if tela == "envio":
    pagina_envio.renderizar()
elif tela == "meus_dados":
    pagina_envio.renderizar_meus_dados()
elif tela == "painel":
    painel.renderizar(painel.Fonte(
        estoque=carregar_dados_analiticos(),
        cotacoes=carregar_dados_cotacoes(),
        ocorrencias=carregar_ocorrencias(),
        engine=obter_conexao(),
    ))
else:
    pagina_inicial.renderizar()
