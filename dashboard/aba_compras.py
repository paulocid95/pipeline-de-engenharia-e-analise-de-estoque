"""Aba 3: Inteligência de Compras & Cotações (Procurement Analytics)."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.formatacao import formatar_moeda_brl
from dashboard.graficos import cor_fornecedor, exibir_grafico
from regras_fornecedores import ICONE_CLASSE, motivo_derrota, opcoes_por_produto


def _fmt_dias(valor) -> str:
    return f"{int(valor)} dias"


def _sem_quebra(texto: str) -> str:
    """Troca espaços por espaços não separáveis, para valores curtos não quebrarem linha."""
    return texto.replace(" ", " ")


def _linha_opcao(rotulo: str, opcao: pd.Series, diferenca: str = "", observacao: str = "—") -> str:
    classe = _sem_quebra(f"{ICONE_CLASSE[opcao['classe']]} {opcao['fornecedor_cotacao']}")
    preco = _sem_quebra(formatar_moeda_brl(float(opcao["preco_cotado"])))
    return (
        f"| {rotulo} | {classe} | {preco} | {_sem_quebra(_fmt_dias(opcao['prazo_dias']))} | "
        f"{_sem_quebra(str(int(opcao['lote_minimo'])) + ' un')} | {opcao['nota_cotacao']:.0f} | "
        f"{_sem_quebra(diferenca) if diferenca else '—'} | {observacao} |"
    )


def _detalhe_produto(opcoes: dict) -> str:
    """Tabela Markdown comparando a melhor opção com quem vence em cada critério isolado."""
    melhor = opcoes["melhor"]
    linhas = [
        "| Critério | Fornecedor | Preço | Prazo | Lote | Nota | Diferença | Por que não venceu |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |",
        _linha_opcao("✅ **Melhor opção**", melhor, observacao="Melhor equilíbrio entre preço, prazo, lote e confiabilidade"),
    ]
    rotulos = {"mais_barato": "💰 Mais barato", "mais_rapido": "⚡ Mais rápido", "menor_lote": "📦 Menor lote"}
    for criterio, rotulo in rotulos.items():
        alt = opcoes[criterio]
        if alt is None:
            linhas.append(f"| {rotulo} | *(mesmo da melhor opção)* | | | | | | |")
            continue
        if criterio == "mais_barato":
            diferenca = f"−{formatar_moeda_brl(float(melhor['preco_cotado'] - alt['preco_cotado']))}"
        elif criterio == "mais_rapido":
            diferenca = f"−{int(melhor['prazo_dias'] - alt['prazo_dias'])} dias"
        else:
            diferenca = f"−{int(melhor['lote_minimo'] - alt['lote_minimo'])} un"
        linhas.append(_linha_opcao(rotulo, alt, diferenca, motivo_derrota(alt, melhor)))
    return "\n".join(linhas)


def _simulador_recompra(df_cot_filtrado: pd.DataFrame, df_cot_avaliado: pd.DataFrame) -> None:
    st.markdown("##### 🚨 Simulador de Recompra: Melhor Opção para Itens em Ruptura ou Alerta")
    st.caption(
        "A melhor opção combina preço, prazo, lote mínimo e confiabilidade do fornecedor (aba 🛡️ Ranking & Risco). "
        "As alternativas mostram quem vence em cada critério isolado e por que não foi a escolhida: a decisão final é sua."
    )

    skus = df_cot_filtrado.loc[df_cot_filtrado["status_reposicao"].isin(["CRITICO", "ALERTA"]), "sku"].unique()
    if len(skus) == 0:
        st.success("✅ **Nenhum produto em status CRÍTICO ou ALERTA** requer recompra urgente nos filtros atuais.")
        return

    # Todas as propostas dos produtos em risco, para comparar com todos os fornecedores
    cotacoes = df_cot_avaliado[df_cot_avaliado["sku"].isin(skus)]
    opcoes = opcoes_por_produto(cotacoes, chave_produto="sku")

    linhas, com_alternativas, economia, baratos_perigosos = [], [], 0.0, 0
    for sku, op in opcoes.items():
        melhor = op["melhor"]
        qtd_alt = sum(op[c] is not None for c in ("mais_barato", "mais_rapido", "menor_lote"))
        if qtd_alt:
            com_alternativas.append((sku, op))
        barato = op["mais_barato"]
        if barato is not None:
            economia += float(melhor["preco_cotado"] - barato["preco_cotado"])
            baratos_perigosos += int(barato["classe"] == "PERIGOSO")
        linhas.append({
            "status": melhor["status_reposicao"],
            "produto": melhor["nome_produto"],
            "melhor": f"{ICONE_CLASSE[melhor['classe']]} {melhor['fornecedor_cotacao']}",
            "nota": melhor["nota_cotacao"],
            "preco": melhor["preco_cotado"],
            "prazo": melhor["prazo_dias"],
            "lote": melhor["lote_minimo"],
            "alternativas": f"⚠️ {qtd_alt}" if qtd_alt else "—",
        })

    if com_alternativas:
        resumo = f"⚠️ **{len(com_alternativas)} de {len(opcoes)} produtos** têm alternativas que vencem em algum critério."
        if economia > 0:
            resumo += (
                f" Optar sempre pelo mais barato economizaria **{formatar_moeda_brl(economia)}** "
                "(comprando uma unidade de cada produto)"
                + (f", mas em {baratos_perigosos} produto(s) ele é 🔴 Perigoso." if baratos_perigosos else ".")
            )
        st.warning(resumo)
    else:
        st.success("✅ Em todos os produtos, a melhor opção também é a mais barata, a mais rápida e a de menor lote.")

    tabela = pd.DataFrame(linhas).sort_values(["status", "produto"])
    st.dataframe(
        tabela,
        column_config={
            "status": st.column_config.TextColumn("Status"),
            "produto": st.column_config.TextColumn("Produto"),
            "melhor": st.column_config.TextColumn("Melhor opção"),
            "nota": st.column_config.NumberColumn("Nota", format="%.0f"),
            "preco": st.column_config.NumberColumn("Preço", format="R$ %.2f"),
            "prazo": st.column_config.NumberColumn("Prazo", format="%d dias"),
            "lote": st.column_config.NumberColumn("Lote mín.", format="%d un"),
            "alternativas": st.column_config.TextColumn("Alternativas"),
        },
        hide_index=True,
        width="stretch",
    )

    if com_alternativas:
        st.markdown("###### 🔍 Comparação por produto")
        for sku, op in sorted(com_alternativas, key=lambda item: str(item[1]["melhor"]["nome_produto"])):
            melhor = op["melhor"]
            qtd = sum(op[c] is not None for c in ("mais_barato", "mais_rapido", "menor_lote"))
            with st.expander(f"{melhor['nome_produto']} · {qtd} alternativa(s)"):
                st.markdown(_detalhe_produto(op))


def renderizar_cabecalho() -> None:
    st.markdown(
        '<div class="tab-banner">💡 <strong>Cenário de Procurement:</strong> Auditoria de propostas concorrentes, identificação de saving potencial e otimização da relação custo vs. prazo de entrega.</div>',
        unsafe_allow_html=True,
    )
    st.subheader("💡 Inteligência de Compras e Cotações (Procurement Analytics)")
    st.caption("Central estratégica de negociação: simulação de cenários de recompra, concorrência direta e captura de saving unitário.")


def renderizar(df_cot_filtrado: pd.DataFrame, df_cot_avaliado: pd.DataFrame) -> None:
    renderizar_cabecalho()

    if not df_cot_filtrado.empty:
        # 1. Cards / Métricas no Topo
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)

        # Cálculo do Saving por SKU comparado à melhor proposta do mercado
        idx_melhores = df_cot_filtrado.groupby("sku")["preco_cotado"].idxmin()
        df_melhores_ofertas = df_cot_filtrado.loc[idx_melhores].copy()
        df_melhores_ofertas["saving_unitario"] = df_melhores_ofertas["preco_referencia"] - df_melhores_ofertas["preco_cotado"]
        df_melhores_ofertas["saving_pct"] = (df_melhores_ofertas["saving_unitario"] / df_melhores_ofertas["preco_referencia"]) * 100

        saving_medio_pct = df_melhores_ofertas["saving_pct"].mean()
        lead_time_medio = df_cot_filtrado["prazo_dias"].mean()

        vitorias_fornecedor = df_melhores_ofertas["fornecedor_cotacao"].value_counts()
        fornecedor_competitivo = vitorias_fornecedor.index[0] if not vitorias_fornecedor.empty else "N/A"
        vitorias_qtd = int(vitorias_fornecedor.iloc[0]) if not vitorias_fornecedor.empty else 0
        vitorias_pct = (vitorias_qtd / len(df_melhores_ofertas) * 100) if len(df_melhores_ofertas) > 0 else 0

        col_m1.metric(
            label="💰 Saving Potencial Médio",
            value=f"{saving_medio_pct:.1f}%",
            delta="Economia vs Tabela",
            help="Economia percentual média obtida optando pela melhor proposta concorrente de cada SKU.",
        )
        col_m2.metric(
            label="⏱️ Lead Time Médio",
            value=f"{lead_time_medio:.1f} dias",
            help="Prazo médio de entrega considerando todas as cotações ativas no filtro atual.",
        )
        col_m3.metric(
            label="🏆 Fornecedor Mais Competitivo",
            value=fornecedor_competitivo,
            delta=f"{vitorias_qtd} ofertas vencedoras ({vitorias_pct:.0f}%)",
            help="Fornecedor que apresentou o menor preço cotado no maior número de produtos.",
        )
        col_m4.metric(
            label="📑 Cotações Analisadas",
            value=f"{len(df_cot_filtrado)} propostas",
            help=f"Volume de propostas cobrindo {len(df_melhores_ofertas)} SKUs cadastrados.",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. Módulo de Cotações Brutas (Expander de Auditoria)
        with st.expander("📥 Ver Todas as Propostas em Aberto (Cotações Recebidas)", expanded=False):
            st.caption(f"Visão analítica completa das {len(df_cot_filtrado)} propostas comerciais submetidas pelos parceiros para auditoria de preços.")
            df_cot_brutas = df_cot_filtrado[[
                "sku", "nome_produto", "fornecedor_cotacao", "preco_cotado", "lote_minimo", "prazo_dias", "data_cotacao"
            ]].copy()
            st.dataframe(
                df_cot_brutas,
                column_config={
                    "sku": st.column_config.TextColumn("SKU"),
                    "nome_produto": st.column_config.TextColumn("Produto"),
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor"),
                    "preco_cotado": st.column_config.NumberColumn("Preço Cotado", format="R$ %.2f"),
                    "lote_minimo": st.column_config.NumberColumn("Lote Mínimo", format="%d un"),
                    "prazo_dias": st.column_config.NumberColumn("Prazo de Entrega", format="%d dias"),
                    "data_cotacao": st.column_config.DatetimeColumn("Data Cotação", format="DD/MM/YYYY HH:mm"),
                },
                hide_index=True,
                width="stretch",
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. Simulador de Recompra: melhor opção geral + alternativas por critério
        _simulador_recompra(df_cot_filtrado, df_cot_avaliado)

        st.markdown("<br>", unsafe_allow_html=True)

        # 4. Painel Executivo de Trade-off Logístico vs. Financeiro
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.markdown("##### ⚖️ Matriz Comparativa de Trade-off: Custo vs. Agilidade Logística")
            st.caption("Comparativo consolidado por parceiro: contraste direto entre tempo de atendimento logístico e competitividade de preço negociado.")
        with col_t2:
            categorias_tradeoff = ["Todas as Categorias"] + sorted(df_cot_filtrado["nome_categoria"].dropna().unique().tolist())
            cat_tradeoff_selecionada = st.selectbox(
                "Filtrar Categoria na Análise:",
                categorias_tradeoff,
                key="sel_cat_tradeoff",
            )

        df_analise_tradeoff = df_cot_filtrado.copy()
        if cat_tradeoff_selecionada != "Todas as Categorias":
            df_analise_tradeoff = df_analise_tradeoff[df_analise_tradeoff["nome_categoria"] == cat_tradeoff_selecionada]

        if not df_analise_tradeoff.empty:
            # Cálculo de saving individual por cotação frente à tabela de referência
            df_analise_tradeoff["saving_pct_item"] = (
                (df_analise_tradeoff["preco_referencia"] - df_analise_tradeoff["preco_cotado"]) 
                / df_analise_tradeoff["preco_referencia"]
            ) * 100

            resumo_fornecedores = df_analise_tradeoff.groupby("fornecedor_cotacao").agg(
                prazo_medio=("prazo_dias", "mean"),
                preco_medio=("preco_cotado", "mean"),
                saving_medio=("saving_pct_item", "mean"),
                lote_medio=("lote_minimo", "mean"),
                total_itens=("id_cotacao", "count")
            ).reset_index()

            # Identificação de lideranças de trade-off
            mais_agil = resumo_fornecedores.loc[resumo_fornecedores["prazo_medio"].idxmin()]
            mais_economico = resumo_fornecedores.loc[resumo_fornecedores["saving_medio"].idxmax()]
            menor_lote = resumo_fornecedores.loc[resumo_fornecedores["lote_medio"].idxmin()]

            # 3 Cards de Síntese Executiva no Topo
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric(
                "⚡ Líder em Agilidade (Menor Prazo)",
                f"{mais_agil['fornecedor_cotacao']}",
                f"{mais_agil['prazo_medio']:.1f} dias médios",
                delta_color="normal"
            )
            kpi2.metric(
                "💰 Líder em Custo (Maior Saving)",
                f"{mais_economico['fornecedor_cotacao']}",
                f"+{mais_economico['saving_medio']:.1f}% vs tabela",
                delta_color="normal"
            )
            kpi3.metric(
                "📦 Menor Compromisso de Compra",
                f"{menor_lote['fornecedor_cotacao']}",
                f"{menor_lote['lote_medio']:.0f} un / pedido",
                delta_color="off"
            )

            st.markdown("<br>", unsafe_allow_html=True)

            # Dois Gráficos de Barras Horizontais Límpidos (Zero Sobreposição)
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                # Gráfico 1: Prazo Médio (quanto menor, mais ágil)
                df_prazo = resumo_fornecedores.sort_values(by="prazo_medio", ascending=False)
                fig_prazo = go.Figure(
                    go.Bar(
                        x=df_prazo["prazo_medio"],
                        y=df_prazo["fornecedor_cotacao"],
                        orientation="h",
                        marker=dict(
                            color=[cor_fornecedor(f) for f in df_prazo["fornecedor_cotacao"]],
                            line=dict(width=0),
                        ),
                        text=[f"<b>{p:.1f} dias úteis</b>" for p in df_prazo["prazo_medio"]],
                        textposition="auto",
                        textfont=dict(color="#ffffff", size=13),
                        hovertemplate="<b>%{y}</b><br>Prazo Médio: %{x:.1f} dias úteis<extra></extra>",
                    )
                )
                fig_prazo.update_layout(
                    title=dict(text="<b>🚚 Agilidade logística</b>", font=dict(size=14, color="#1e293b")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=260,
                    margin=dict(t=45, b=25, l=10, r=20),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        title="Dias Úteis (menor barra = mais ágil)",
                        zeroline=False,
                    ),
                    yaxis=dict(
                        showgrid=False,
                        tickfont=dict(size=12, color="#0f172a"),
                    ),
                )
                exibir_grafico(fig_prazo)

            with col_g2:
                # Gráfico 2: Saving Médio (% de Desconto frente à referência)
                df_saving = resumo_fornecedores.sort_values(by="saving_medio", ascending=True)
                fig_saving = go.Figure(
                    go.Bar(
                        x=df_saving["saving_medio"],
                        y=df_saving["fornecedor_cotacao"],
                        orientation="h",
                        marker=dict(
                            color=[cor_fornecedor(f) for f in df_saving["fornecedor_cotacao"]],
                            line=dict(width=0),
                        ),
                        text=[f"<b>+{s:.1f}% saving</b>" for s in df_saving["saving_medio"]],
                        textposition="auto",
                        textfont=dict(color="#ffffff", size=13),
                        hovertemplate="<b>%{y}</b><br>Economia Média: %{x:.2f}%<extra></extra>",
                    )
                )
                fig_saving.update_layout(
                    title=dict(text="<b>💰 Competitividade de custo</b>", font=dict(size=14, color="#1e293b")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=260,
                    margin=dict(t=45, b=25, l=10, r=20),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        title="% de Economia em Relação ao Preço Base",
                        ticksuffix="%",
                        zeroline=False,
                    ),
                    yaxis=dict(
                        showgrid=False,
                        tickfont=dict(size=12, color="#0f172a"),
                    ),
                )
                exibir_grafico(fig_saving)

            # 4. Quadro Sintético de Decisão de Compra
            st.markdown("###### 📋 Quadro Sintético de Decisão de Compra")
            
            def classificar_estrategia(row):
                if row["fornecedor_cotacao"] == mais_agil["fornecedor_cotacao"] and row["fornecedor_cotacao"] == mais_economico["fornecedor_cotacao"]:
                    return "⭐ Campeão Geral: Melhor Preço e Entrega Mais Rápida"
                elif row["fornecedor_cotacao"] == mais_agil["fornecedor_cotacao"]:
                    return "🚀 Entrega Rápida: Indicado para Reposições Urgentes e Rupturas"
                elif row["fornecedor_cotacao"] == mais_economico["fornecedor_cotacao"]:
                    return "💡 Menor Custo: Indicado para Compras Programadas de Alto Volume"
                elif row["fornecedor_cotacao"] == menor_lote["fornecedor_cotacao"]:
                    return "📦 Baixo Volume: Indicado para Testes de Demanda e Estoque Enxuto"
                else:
                    return "⚖️ Oferta Equilibrada: Alternativa Concorrencial"

            df_tabela_tradeoff = resumo_fornecedores.copy()
            df_tabela_tradeoff["recomendacao"] = df_tabela_tradeoff.apply(classificar_estrategia, axis=1)

            st.dataframe(
                df_tabela_tradeoff[[
                    "fornecedor_cotacao", "prazo_medio", "saving_medio", "preco_medio", "lote_medio", "recomendacao"
                ]],
                column_config={
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor Parceiro"),
                    "prazo_medio": st.column_config.NumberColumn("Prazo Médio", format="%.1f dias úteis"),
                    "saving_medio": st.column_config.NumberColumn("Saving Médio", format="+%.1f%%"),
                    "preco_medio": st.column_config.NumberColumn("Preço Médio Cotado", format="R$ %.2f"),
                    "lote_medio": st.column_config.NumberColumn("Lote Mínimo Médio", format="%.0f un"),
                    "recomendacao": st.column_config.TextColumn("Recomendação Estratégica"),
                },
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Nenhuma cotação encontrada para a categoria selecionada.")

        st.markdown("<br>", unsafe_allow_html=True)

        # 5. Comparador Detalhado por SKU
        st.markdown("##### 🔍 Comparador Concorrencial por Produto")
        st.caption("Selecione um produto para auditar e comparar todas as propostas ativas submetidas pelos parceiros.")

        produtos_disponiveis = sorted(df_cot_filtrado["nome_produto"].unique().tolist())
        produto_selecionado = st.selectbox(
            "Selecione o Produto para Comparação Direta:",
            options=produtos_disponiveis,
            key="select_produto_cotacao",
        )

        df_sku_cot = df_cot_filtrado[df_cot_filtrado["nome_produto"] == produto_selecionado].sort_values(by="preco_cotado", ascending=True).copy()

        if not df_sku_cot.empty:
            preco_base_prod = float(df_sku_cot["preco_referencia"].iloc[0])
            menor_oferta = float(df_sku_cot["preco_cotado"].min())
            maior_oferta = float(df_sku_cot["preco_cotado"].max())
            spread_oferta = maior_oferta - menor_oferta

            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            col_p1.metric("Preço de Tabela (Base)", formatar_moeda_brl(preco_base_prod))
            col_p2.metric(
                "Menor Oferta (Best Price)",
                formatar_moeda_brl(menor_oferta),
                delta=f"-{((preco_base_prod - menor_oferta)/preco_base_prod)*100:.1f}%" if preco_base_prod > 0 else None,
            )
            col_p3.metric("Maior Oferta", formatar_moeda_brl(maior_oferta))
            col_p4.metric("Spread Concorrencial", formatar_moeda_brl(spread_oferta))

            # Flag de classificação
            df_sku_cot["resultado"] = [
                "🏆 Vencedora (Melhor Preço)" if p == menor_oferta else "Concorrente"
                for p in df_sku_cot["preco_cotado"]
            ]
            df_sku_cot["variacao_pct"] = ((df_sku_cot["preco_cotado"] - preco_base_prod) / preco_base_prod) * 100

            st.dataframe(
                df_sku_cot[[
                    "resultado", "fornecedor_cotacao", "preco_cotado", "variacao_pct",
                    "lote_minimo", "prazo_dias", "data_cotacao"
                ]],
                column_config={
                    "resultado": st.column_config.TextColumn("Status da Oferta"),
                    "fornecedor_cotacao": st.column_config.TextColumn("Fornecedor"),
                    "preco_cotado": st.column_config.NumberColumn("Preço Cotado", format="R$ %.2f"),
                    "variacao_pct": st.column_config.NumberColumn("Variação vs Tabela", format="%+.1f%%"),
                    "lote_minimo": st.column_config.NumberColumn("Lote Mínimo", format="%d un"),
                    "prazo_dias": st.column_config.NumberColumn("Prazo de Entrega", format="%d dias"),
                    "data_cotacao": st.column_config.DatetimeColumn("Data da Cotação", format="DD/MM/YYYY HH:mm"),
                },
                hide_index=True,
                width="stretch",
            )
    else:
        st.info("ℹ️ Nenhuma cotação encontrada para os filtros selecionados.")
