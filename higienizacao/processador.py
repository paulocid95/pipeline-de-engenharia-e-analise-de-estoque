"""Orquestra a higienização: das tabelas brutas aos DataFrames no formato do painel, com relatório."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from regras_estoque import LIMITE_ALERTA, LIMITE_EXCESSO, classificar_status
from regras_fornecedores import ROTULOS_TIPO

from . import entidades as ent
from .colunas import COTACOES, ESTOQUE, NOMES_TIPO, OCORRENCIAS, VENDAS, detectar_tipo, faltando, mapear_colunas
from .conversores import para_data, para_numero
from .leitura import TabelaBruta
from .texto import limpar_texto, melhor_variante, normalizar, vazio

NAO_INFORMADO = "Não informado"
PRAZO_PADRAO = 7
SIMILARIDADE_PRODUTO = 0.85


# ------------------------------------------------------------------------------
# Estruturas de entrada e saída
# ------------------------------------------------------------------------------
@dataclass
class EntradaTabela:
    """Uma tabela já identificada (tipo e colunas). A tela de envio pode corrigir `tipo` e `mapa`."""
    origem: str
    tipo: str | None
    bruta: pd.DataFrame
    linha_cabecalho: int = 0
    mapa: dict = field(default_factory=dict)        # coluna canônica -> índice na tabela
    cabecalhos: list = field(default_factory=list)


@dataclass
class ItemRelatorio:
    aba: str
    mensagem: str
    quantidade: int = 0
    nivel: str = "ok"                                  # ok | aviso | erro
    exemplos: list = field(default_factory=list)     # [(antes, depois)]


@dataclass
class Duvida:
    tipo: str            # "fornecedor" ou "produto"
    a: str               # como aparece na planilha
    b: str               # com quem parece ser o mesmo
    similaridade: float
    sugerida: bool = False   # um nome contém o outro: já vem unido, e o usuário pode separar

    @property
    def chave(self) -> tuple:
        return (self.tipo, self.a, self.b)


@dataclass
class Resultado:
    estoque: pd.DataFrame | None = None
    cotacoes: pd.DataFrame | None = None
    ocorrencias: pd.DataFrame | None = None
    vendas: pd.DataFrame | None = None
    relatorio: list = field(default_factory=list)
    descartes: list = field(default_factory=list)          # {aba, linha, motivo, conteudo}
    duvidas: list = field(default_factory=list)
    colunas_ignoradas: dict = field(default_factory=dict)  # aba -> [nomes]
    pendencias: dict = field(default_factory=dict)         # aba -> [grupos de colunas obrigatórias faltando]

    @property
    def ok(self) -> bool:
        return self.estoque is not None and not self.estoque.empty


def preparar(tabelas: list[TabelaBruta]) -> list[EntradaTabela]:
    """Identifica o tipo e as colunas de cada tabela lida (o usuário pode corrigir depois)."""
    entradas = []
    for t in tabelas:
        d = detectar_tipo(t.dados, t.nome)
        entradas.append(EntradaTabela(t.origem, d.tipo, t.dados, d.linha_cabecalho, d.mapa, d.cabecalhos))
    return entradas


def remapear(entrada: EntradaTabela, tipo: str) -> EntradaTabela:
    """Reaplica o reconhecimento de colunas quando o usuário troca o tipo da tabela."""
    from .colunas import encontrar_cabecalho
    linha, _ = encontrar_cabecalho(entrada.bruta, tipo)
    cabecalhos = list(entrada.bruta.iloc[linha])
    return EntradaTabela(entrada.origem, tipo, entrada.bruta, linha, mapear_colunas(cabecalhos, tipo), cabecalhos)


# ------------------------------------------------------------------------------
# Auxiliares
# ------------------------------------------------------------------------------
class _Coletor:
    def __init__(self, resultado: Resultado):
        self.r = resultado

    def info(self, aba, mensagem, quantidade=0, exemplos=None, nivel="ok"):
        if quantidade or nivel != "ok" or exemplos:
            self.r.relatorio.append(ItemRelatorio(NOMES_TIPO.get(aba, aba), mensagem, quantidade, nivel,
                                                  list(dict.fromkeys(exemplos or []))[:4]))

    def descarte(self, aba, linha, motivo, conteudo):
        self.r.descartes.append({"aba": NOMES_TIPO.get(aba, aba), "linha": linha, "motivo": motivo,
                                 "conteudo": " | ".join(limpar_texto(v) for v in conteudo if not vazio(v))})


def _txt(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return limpar_texto(valor)


def _extrair(entradas: list[EntradaTabela], tipo: str, col: _Coletor, res: Resultado) -> pd.DataFrame | None:
    """Junta as tabelas de um tipo em um DataFrame com as colunas canônicas (valores ainda brutos)."""
    partes = []
    for e in (x for x in entradas if x.tipo == tipo):
        falta = faltando(e.mapa, tipo)
        if falta:
            res.pendencias.setdefault(NOMES_TIPO[tipo], []).extend(falta)
            continue
        dados = e.bruta.iloc[e.linha_cabecalho + 1:]
        if e.linha_cabecalho > 0:
            col.info(tipo, "Linhas de título acima do cabeçalho ignoradas", e.linha_cabecalho)
        # Linhas de total/subtotal no fim de relatórios
        primeiras = dados.iloc[:, : min(3, dados.shape[1])].map(normalizar)
        eh_total = primeiras.apply(lambda l: any(v.startswith(("total", "subtotal")) for v in l), axis=1)
        if eh_total.any():
            col.info(tipo, "Linhas de TOTAL/subtotal removidas", int(eh_total.sum()))
        dados = dados[~eh_total]
        df = pd.DataFrame({canon: dados.iloc[:, i].tolist() for canon, i in e.mapa.items()})
        df["_linha"] = [e.linha_cabecalho + 2 + k for k in range(len(dados))]
        df["_bruto"] = [list(l) for l in dados.itertuples(index=False)]
        partes.append(df)
        usados = set(e.mapa.values())
        ignoradas = [_txt(c) for i, c in enumerate(e.cabecalhos) if i not in usados and not vazio(c)]
        if ignoradas:
            res.colunas_ignoradas.setdefault(NOMES_TIPO[tipo], []).extend(ignoradas)
    if not partes:
        return None
    df = pd.concat(partes, ignore_index=True)
    for canon in ("sku", "produto", "fornecedor"):
        if canon not in df.columns:
            df[canon] = None
    return df


def _contar_texto(serie: pd.Series) -> int:
    return int(sum(isinstance(v, str) and not vazio(v) for v in serie))


def _uniao(pares: list[tuple[str, str]]) -> dict[str, str]:
    """Agrupa chaves ligadas (a~b, b~c) e aponta todas para a primeira do grupo."""
    pai: dict[str, str] = {}

    def raiz(x):
        while pai.get(x, x) != x:
            x = pai[x]
        return x

    for a, b in pares:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[rb] = ra
    return {x: raiz(x) for x in pai}


# ------------------------------------------------------------------------------
# Orquestração
# ------------------------------------------------------------------------------
def higienizar(
    entradas: list[EntradaTabela],
    limite_alerta: int = LIMITE_ALERTA,
    limite_excesso: int = LIMITE_EXCESSO,
    decisoes: dict | None = None,
    hoje: date | None = None,
) -> Resultado:
    """Limpa e padroniza todas as tabelas enviadas.

    `decisoes`: respostas do usuário aos casos duvidosos, {Duvida.chave: True (unir) / False (manter separado)}.
    Casos sem resposta ficam separados.
    """
    hoje = hoje or date.today()
    decisoes = decisoes or {}
    res = Resultado()
    col = _Coletor(res)

    brutos = {t: _extrair(entradas, t, col, res) for t in (ESTOQUE, COTACOES, OCORRENCIAS, VENDAS)}
    if brutos[ESTOQUE] is None:
        if NOMES_TIPO[ESTOQUE] not in res.pendencias:
            res.pendencias[NOMES_TIPO[ESTOQUE]] = [("produto",), ("quantidade",), ("preco",)]
        return res

    # ---------------- Fornecedores (todas as tabelas) ----------------
    variantes = [v for t in brutos.values() if t is not None for v in t["fornecedor"] if not vazio(v)]
    chaves = sorted({ent.chave_fornecedor(v) for v in variantes} - {""})
    exibicao = {k: ent.nome_de_exibicao(k, variantes) for k in chaves}
    uso = {k: 0 for k in chaves}
    for v in variantes:
        uso[ent.chave_fornecedor(v)] = uso.get(ent.chave_fornecedor(v), 0) + 1
    def principal(nomes) -> str:
        # O nome mais usado (e, no empate, o mais completo) é o que fica
        return max(nomes, key=lambda k: (uso[k], len(k)))

    pares_unidos, contidos = [], []
    for i, a in enumerate(chaves):
        for b in chaves[i + 1:]:
            if ent.contido(a, b):
                contidos.append((a, b))
            elif sim := ent.parecidos(a, b):
                fica = principal((a, b))
                sai = b if fica == a else a
                duvida = Duvida("fornecedor", exibicao[sai], exibicao[fica], round(sim, 2))
                res.duvidas.append(duvida)
                if decisoes.get(duvida.chave):
                    pares_unidos.append((fica, sai))
    # Nomes contidos um no outro formam grupos ("Vetfarma" ⊂ "Vetfarma Distribuidora" ⊂ ...): cada nome
    # vira uma única pergunta, já marcada para unir ao nome principal do grupo.
    grupos: dict[str, list] = {}
    for nome, raiz in _uniao(contidos).items():
        grupos.setdefault(raiz, [raiz]).append(nome)
    for membros in grupos.values():
        fica = principal(membros)
        for sai in sorted(m for m in membros if m != fica):
            razao = ent.SequenceMatcher(None, sai, fica).ratio()
            duvida = Duvida("fornecedor", exibicao[sai], exibicao[fica], round(razao, 2), sugerida=True)
            res.duvidas.append(duvida)
            if decisoes.get(duvida.chave, True):
                pares_unidos.append((fica, sai))
    destino = _uniao(pares_unidos)

    def fornecedor(valor) -> str:
        if vazio(valor):
            return NAO_INFORMADO
        k = ent.chave_fornecedor(valor)
        return exibicao.get(destino.get(k, k), limpar_texto(valor)) if k else NAO_INFORMADO

    mudancas = [(limpar_texto(v), fornecedor(v)) for v in variantes if limpar_texto(v) != fornecedor(v)]
    col.info("Fornecedores", f"Grafias diferentes unificadas em {len(set(fornecedor(v) for v in variantes))} fornecedores",
             len({a for a, _ in mudancas}), exemplos=mudancas)

    # ---------------- Nomes de produto por SKU (todas as tabelas) ----------------
    nomes_por_sku: dict[str, list] = {}
    for t in brutos.values():
        if t is not None:
            for sku, prod in zip(t["sku"], t["produto"]):
                if not vazio(sku) and not vazio(prod):
                    nomes_por_sku.setdefault(_txt(sku).upper(), []).append(prod)

    estoque = _estoque(brutos[ESTOQUE], col, fornecedor, nomes_por_sku, limite_alerta, limite_excesso)
    res.estoque = estoque

    # Índices para ligar as outras tabelas ao estoque
    por_sku = {s.upper(): s for s in estoque["sku"]}
    por_nome = {normalizar(n): s for s, n in zip(estoque["sku"], estoque["nome_produto"])}
    nome_do_sku = dict(zip(estoque["sku"], estoque["nome_produto"]))

    def ligar(sku_bruto, prod_bruto, perguntar: bool) -> str | None:
        if not vazio(sku_bruto) and _txt(sku_bruto).upper() in por_sku:
            return por_sku[_txt(sku_bruto).upper()]
        chave = normalizar(prod_bruto)
        if chave in por_nome:
            return por_nome[chave]
        if not chave or not perguntar:
            return None
        melhor, sim = None, 0.0
        for nome_est, sku in por_nome.items():
            s = ent.SequenceMatcher(None, chave, nome_est).ratio()
            if s > sim:
                melhor, sim = sku, s
        if melhor and sim >= SIMILARIDADE_PRODUTO:
            duvida = Duvida("produto", limpar_texto(prod_bruto), nome_do_sku[melhor], round(sim, 2))
            if duvida.chave not in {d.chave for d in res.duvidas}:
                res.duvidas.append(duvida)
            if decisoes.get(duvida.chave):
                return melhor
        return None

    if brutos[COTACOES] is not None:
        res.cotacoes = _cotacoes(brutos[COTACOES], col, fornecedor, ligar, estoque, hoje)
    if brutos[OCORRENCIAS] is not None:
        res.ocorrencias = _ocorrencias(brutos[OCORRENCIAS], col, fornecedor, ligar, nome_do_sku, hoje)
    if brutos[VENDAS] is not None:
        res.vendas = _vendas(brutos[VENDAS], col, ligar, nome_do_sku, hoje)
    return res


# ------------------------------------------------------------------------------
# Estoque
# ------------------------------------------------------------------------------
def _categorias_da_planilha(linhas: list[dict]) -> tuple[int, int, list]:
    """Lojas que não são de eletrônicos: mantém as categorias do usuário, só unificando a grafia
    ('RACOES' e 'Racoes' viram 'Racoes'), e deduz as vazias por produtos que começam com a mesma palavra."""
    grafias: dict[str, list] = {}
    for l in linhas:
        if l["categoria"]:
            grafias.setdefault(normalizar(l["categoria"]), []).append(l["categoria"])
    nomes = {k: ent.nome_de_categoria(v) for k, v in grafias.items()}

    contagem: dict[str, Counter] = {}
    for l in linhas:
        palavras = normalizar(l["produto"]).split()
        if l["categoria"] and palavras:
            contagem.setdefault(palavras[0], Counter())[nomes[normalizar(l["categoria"])]] += 1
    por_palavra = {p: c.most_common(1)[0][0] for p, c in contagem.items()}

    deduzidas = padronizadas = 0
    exemplos = []
    for l in linhas:
        bruta = l["categoria"]
        if not bruta:
            l["categoria"] = ent.deduzir_pela_planilha(l["produto"], por_palavra)
            deduzidas += 1
            continue
        l["categoria"] = nomes[normalizar(bruta)]
        if l["categoria"] != bruta:
            padronizadas += 1
            exemplos.append((bruta, l["categoria"]))
    return deduzidas, padronizadas, exemplos


def _estoque(df, col, fornecedor, nomes_por_sku, limite_alerta, limite_excesso) -> pd.DataFrame:
    linhas = []
    precos_texto = _contar_texto(df["preco"])
    qtd_texto = sum(isinstance(v, str) and not vazio(v) and para_numero(v) is not None
                    and str(para_numero(v)).rstrip("0").rstrip(".") != v.strip() for v in df["quantidade"])
    vazias = negativas = deduzidas = sinonimos = 0
    ex_cat, ex_preco = [], []
    eletronicos = ent.loja_de_eletronicos(df["produto"].map(limpar_texto))
    for r in df.to_dict("records"):
        preco = para_numero(r["preco"])
        if preco is None or preco <= 0:
            col.descarte(ESTOQUE, r["_linha"], f"Preço inválido: “{_txt(r['preco']) or 'vazio'}”", r["_bruto"])
            continue
        if isinstance(r["preco"], str):
            ex_preco.append((limpar_texto(r["preco"]), f"{preco:.2f}"))
        bruta_qtd = r["quantidade"]
        qtd = para_numero(bruta_qtd)
        if qtd is None:
            if vazio(bruta_qtd):
                vazias += 1
                qtd = 0
            else:
                col.descarte(ESTOQUE, r["_linha"], f"Quantidade ilegível: “{_txt(bruta_qtd)}”", r["_bruto"])
                continue
        if qtd < 0:
            negativas += 1
            qtd = 0
        produto = limpar_texto(r["produto"]) or _txt(r["sku"])
        sku = _txt(r["sku"]) or None
        cat_bruta = limpar_texto(r.get("categoria"))
        if eletronicos:
            categoria, deduzida = ent.categoria_padrao(cat_bruta, produto)
            if deduzida:
                deduzidas += 1
            elif cat_bruta != categoria:
                sinonimos += 1
                ex_cat.append((cat_bruta, categoria))
        else:
            categoria = cat_bruta            # padronizada depois, olhando a planilha inteira
        minimo = para_numero(r.get("estoque_minimo"))
        linhas.append({
            "sku": sku, "produto": produto, "categoria": categoria, "fornecedor": fornecedor(r["fornecedor"]),
            "preco": round(preco, 2), "quantidade": int(round(qtd)),
            "estoque_minimo": int(minimo) if minimo is not None and minimo > 0 else None,
        })

    if not eletronicos:
        d, s, ex = _categorias_da_planilha(linhas)
        deduzidas, sinonimos, ex_cat = d, s, ex

    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=["sku", "nome_produto", "nome_categoria", "fornecedor", "preco_unitario",
                                     "quantidade_disponivel", "valor_total_estoque", "status_reposicao", "data_carga"])

    # Sem código: cria um a partir do nome (o mesmo nome vira o mesmo código)
    sem_sku = df["sku"].isna()
    if sem_sku.any():
        codigos = {k: f"P{i + 1:04d}" for i, k in enumerate(dict.fromkeys(df.loc[sem_sku, "produto"].map(normalizar)))}
        df.loc[sem_sku, "sku"] = df.loc[sem_sku, "produto"].map(lambda p: codigos[normalizar(p)])
        col.info(ESTOQUE, "Produtos sem código receberam um código automático (P0001, P0002...)", int(sem_sku.sum()))
    df["chave"] = df["sku"].str.upper()

    # SKUs repetidos: soma as quantidades
    repetidos = df["chave"].duplicated(keep=False)
    if repetidos.any():
        exemplos = [(f"{k}: {' + '.join(map(str, g['quantidade']))}", f"{g['quantidade'].sum()} un")
                    for k, g in df[repetidos].groupby("chave")]
        col.info(ESTOQUE, "Produtos repetidos somados em uma linha só", df.loc[repetidos, "chave"].nunique(), exemplos)
        conflito = df[repetidos].groupby("chave")["preco"].nunique()
        if (conflito > 1).any():
            col.info(ESTOQUE, "Produtos repetidos com preços diferentes (usado o primeiro)", int((conflito > 1).sum()),
                     nivel="aviso")
    agrupado = df.groupby("chave", sort=False).agg(
        sku=("sku", "first"), preco=("preco", "first"), quantidade=("quantidade", "sum"),
        categoria=("categoria", "first"), fornecedor=("fornecedor", "first"),
        estoque_minimo=("estoque_minimo", "first"), produtos=("produto", list),
    ).reset_index(drop=True)
    agrupado["nome_produto"] = [
        melhor_variante(prods + nomes_por_sku.get(s.upper(), [])) for s, prods in zip(agrupado["sku"], agrupado["produtos"])
    ]
    nomes_mudados = sum(limpar_texto(p) != n for ps, n in zip(agrupado["produtos"], agrupado["nome_produto"]) for p in ps)

    col.info(ESTOQUE, "Preços convertidos para número (R$, milhar, vírgula decimal)", precos_texto, ex_preco)
    col.info(ESTOQUE, "Quantidades com texto corrigidas (ex.: “12 un”, “12,0”)", int(qtd_texto))
    col.info(ESTOQUE, "Quantidades vazias consideradas 0", vazias)
    col.info(ESTOQUE, "Quantidades negativas ajustadas para 0", negativas, nivel="aviso" if negativas else "ok")
    col.info(ESTOQUE, "Categorias deduzidas pelo nome do produto (estavam vazias)", deduzidas)
    col.info(ESTOQUE, "Categorias padronizadas (sinônimos e maiúsculas)", sinonimos, ex_cat)
    col.info(ESTOQUE, "Nomes de produto padronizados (espaços e maiúsculas)", nomes_mudados)

    usa_minimo = agrupado["estoque_minimo"].notna()
    if usa_minimo.any():
        col.info(ESTOQUE, "Produtos com estoque mínimo próprio (usado no lugar do limite de alerta)", int(usa_minimo.sum()))
    limites = [int(m) if pd.notna(m) else limite_alerta for m in agrupado["estoque_minimo"]]
    return pd.DataFrame({
        "sku": agrupado["sku"],
        "nome_produto": agrupado["nome_produto"],
        "nome_categoria": agrupado["categoria"],
        "fornecedor": agrupado["fornecedor"],
        "preco_unitario": agrupado["preco"],
        "quantidade_disponivel": agrupado["quantidade"].astype(int),
        "valor_total_estoque": (agrupado["preco"] * agrupado["quantidade"]).round(2),
        "status_reposicao": [classificar_status(q, lim, limite_excesso) for q, lim in zip(agrupado["quantidade"], limites)],
        "estoque_minimo": agrupado["estoque_minimo"],
        "data_carga": pd.Timestamp(datetime.now()),
    }).sort_values("valor_total_estoque", ascending=False, ignore_index=True)


# ------------------------------------------------------------------------------
# Cotações
# ------------------------------------------------------------------------------
def _cotacoes(df, col, fornecedor, ligar, estoque, hoje) -> pd.DataFrame:
    info_est = estoque.set_index("sku")
    linhas, sem_prazo, sem_lote, sem_produto = [], 0, 0, 0
    for r in df.to_dict("records"):
        sku = ligar(r["sku"], r["produto"], perguntar=True)
        if sku is None:
            sem_produto += 1
            col.descarte(COTACOES, r["_linha"], "Produto não encontrado no estoque", r["_bruto"])
            continue
        if vazio(r["fornecedor"]):
            col.descarte(COTACOES, r["_linha"], "Cotação sem fornecedor", r["_bruto"])
            continue
        preco = para_numero(r["preco"])
        if preco is None or preco <= 0:
            col.descarte(COTACOES, r["_linha"], f"Preço inválido: “{_txt(r['preco']) or 'vazio'}”", r["_bruto"])
            continue
        prazo = para_numero(r.get("prazo_dias"))
        lote = para_numero(r.get("lote_minimo"))
        linhas.append({
            "sku": sku, "fornecedor_cotacao": fornecedor(r["fornecedor"]), "preco_cotado": round(preco, 2),
            "prazo_dias": None if prazo is None or prazo < 0 else int(round(prazo)),
            "lote_minimo": None if lote is None or lote <= 0 else int(round(lote)),
            "data_cotacao": para_data(r.get("data")) or hoje,
        })
    colunas = ["id_cotacao", "sku", "nome_produto", "nome_categoria", "preco_referencia", "fornecedor_cotacao",
               "preco_cotado", "lote_minimo", "prazo_dias", "data_cotacao", "status_reposicao", "quantidade_disponivel"]
    if not linhas:
        return pd.DataFrame(columns=colunas)
    cot = pd.DataFrame(linhas)

    sem_prazo = int(cot["prazo_dias"].isna().sum())
    if sem_prazo:
        mediana = int(cot["prazo_dias"].median()) if cot["prazo_dias"].notna().any() else PRAZO_PADRAO
        cot["prazo_dias"] = cot["prazo_dias"].fillna(mediana)
        col.info(COTACOES, f"Cotações sem prazo: usado o prazo típico das demais ({mediana} dias)", sem_prazo, nivel="aviso")
    sem_lote = int(cot["lote_minimo"].isna().sum())
    if sem_lote:
        cot["lote_minimo"] = cot["lote_minimo"].fillna(1)
        col.info(COTACOES, "Cotações sem lote mínimo: considerado 1 unidade", sem_lote, nivel="aviso")

    # Mesma combinação produto + fornecedor repetida: fica a cotação mais recente
    antes = len(cot)
    cot = cot.sort_values("data_cotacao").drop_duplicates(["sku", "fornecedor_cotacao"], keep="last")
    col.info(COTACOES, "Cotações repetidas (mesmo produto e fornecedor): mantida a mais recente", antes - len(cot))
    col.info(COTACOES, "Preços, prazos e lotes convertidos para número",
             _contar_texto(df["preco"]) + _contar_texto(df.get("prazo_dias", pd.Series(dtype=object)))
             + _contar_texto(df.get("lote_minimo", pd.Series(dtype=object))))
    if sem_produto:
        col.info(COTACOES, "Cotações de produtos que não estão no estoque (descartadas)", sem_produto, nivel="aviso")

    cot = cot.sort_values(["sku", "preco_cotado"], ignore_index=True)
    cot["id_cotacao"] = range(1, len(cot) + 1)
    cot["nome_produto"] = cot["sku"].map(info_est["nome_produto"])
    cot["nome_categoria"] = cot["sku"].map(info_est["nome_categoria"])
    cot["preco_referencia"] = cot["sku"].map(info_est["preco_unitario"])
    cot["status_reposicao"] = cot["sku"].map(info_est["status_reposicao"])
    cot["quantidade_disponivel"] = cot["sku"].map(info_est["quantidade_disponivel"])
    cot["prazo_dias"] = cot["prazo_dias"].astype(int)
    cot["lote_minimo"] = cot["lote_minimo"].astype(int)
    cot["data_cotacao"] = pd.to_datetime(cot["data_cotacao"])
    return cot[colunas]


# ------------------------------------------------------------------------------
# Ocorrências
# ------------------------------------------------------------------------------
def _ocorrencias(df, col, fornecedor, ligar, nome_do_sku, hoje) -> pd.DataFrame:
    linhas, outros, sem_gravidade, sem_status, res_sem_data, datas_invertidas = [], [], 0, 0, 0, 0
    datas_texto = _contar_texto(df["data"])
    for r in df.to_dict("records"):
        if vazio(r["fornecedor"]):
            col.descarte(OCORRENCIAS, r["_linha"], "Ocorrência sem fornecedor", r["_bruto"])
            continue
        data_oc = para_data(r["data"])
        if data_oc is None:
            col.descarte(OCORRENCIAS, r["_linha"], f"Data ilegível: “{_txt(r['data']) or 'vazia'}”", r["_bruto"])
            continue
        if data_oc > hoje:
            col.descarte(OCORRENCIAS, r["_linha"], f"Data no futuro: {data_oc:%d/%m/%Y}", r["_bruto"])
            continue
        tipo = ent.tipo_ocorrencia(r["tipo"])
        if tipo == ent.TIPO_OUTROS:
            outros.append((limpar_texto(r["tipo"]) or "(vazio)", ROTULOS_TIPO[ent.TIPO_OUTROS]))
        grav = ent.gravidade(r.get("gravidade"))
        if grav is None:
            sem_gravidade += 1
            grav = "MEDIA"
        data_res = para_data(r.get("data_resolucao"))
        if data_res is not None and data_res < data_oc:
            datas_invertidas += 1
            data_res = None
        status = ent.status_ocorrencia(r.get("status"))
        if status is None:
            sem_status += 1
            status = "RESOLVIDO" if data_res else "ABERTO"
        if status != "RESOLVIDO" and data_res is not None:
            status = "RESOLVIDO"                     # tem data de resolução: foi resolvida
        if status == "RESOLVIDO" and data_res is None:
            res_sem_data += 1
        sku = ligar(None, r.get("produto"), perguntar=False)
        linhas.append({
            "fornecedor": fornecedor(r["fornecedor"]),
            "nome_produto": nome_do_sku.get(sku) if sku else (limpar_texto(r.get("produto")) or None),
            "tipo": tipo, "gravidade": grav, "data_ocorrencia": data_oc, "status": status,
            "data_resolucao": data_res, "descricao": limpar_texto(r.get("descricao")) or None,
        })
    col.info(OCORRENCIAS, "Datas em formatos diferentes padronizadas", datas_texto)
    col.info(OCORRENCIAS, "Tipos não reconhecidos classificados como “Outros problemas” (peso médio)", len(outros),
             outros, nivel="aviso" if outros else "ok")
    col.info(OCORRENCIAS, "Ocorrências sem gravidade: considerada média", sem_gravidade, nivel="aviso" if sem_gravidade else "ok")
    col.info(OCORRENCIAS, "Ocorrências sem situação: deduzida pela data de resolução", sem_status)
    col.info(OCORRENCIAS, "Resolvidas sem data de resolução: considerado tempo médio de 30 dias", res_sem_data,
             nivel="aviso" if res_sem_data else "ok")
    col.info(OCORRENCIAS, "Datas de resolução anteriores à ocorrência ignoradas", datas_invertidas,
             nivel="aviso" if datas_invertidas else "ok")
    colunas = ["id_ocorrencia", "fornecedor", "nome_produto", "tipo", "gravidade", "data_ocorrencia", "status",
               "data_resolucao", "descricao"]
    if not linhas:
        return pd.DataFrame(columns=colunas)
    oc = pd.DataFrame(linhas).sort_values("data_ocorrencia", ascending=False, ignore_index=True)
    oc["id_ocorrencia"] = range(len(oc), 0, -1)
    return oc[colunas]


# ------------------------------------------------------------------------------
# Vendas
# ------------------------------------------------------------------------------
def _vendas(df, col, ligar, nome_do_sku, hoje) -> pd.DataFrame:
    linhas, fora, negativas = [], {}, 0
    for r in df.to_dict("records"):
        data_v = para_data(r["data"])
        if data_v is None or data_v > hoje:
            col.descarte(VENDAS, r["_linha"], f"Data inválida: “{_txt(r['data']) or 'vazia'}”", r["_bruto"])
            continue
        sku = ligar(r["sku"], r["produto"], perguntar=False)
        if sku is None:
            nome = limpar_texto(r["produto"]) or _txt(r["sku"]) or "(sem produto)"
            fora[nome] = fora.get(nome, 0) + 1
            continue
        qtd = para_numero(r["quantidade"])
        if qtd is None:
            col.descarte(VENDAS, r["_linha"], f"Quantidade ilegível: “{_txt(r['quantidade']) or 'vazia'}”", r["_bruto"])
            continue
        if qtd < 0:
            negativas += 1
            qtd = 0
        linhas.append({"data": data_v, "sku": sku, "quantidade_vendida": int(round(qtd))})
    col.info(VENDAS, "Quantidades com texto corrigidas", sum(
        isinstance(v, str) and not vazio(v) and not v.strip().lstrip("-").isdigit() for v in df["quantidade"]))
    col.info(VENDAS, "Quantidades negativas (devoluções) ajustadas para 0", negativas, nivel="aviso" if negativas else "ok")
    if fora:
        col.info(VENDAS, "Linhas de produtos que não estão no estoque (ignoradas)", sum(fora.values()),
                 [(n, f"{q} linha(s)") for n, q in fora.items()], nivel="aviso")
    colunas = ["data", "sku", "nome_produto", "quantidade_vendida"]
    if not linhas:
        return pd.DataFrame(columns=colunas)
    v = pd.DataFrame(linhas)
    antes = len(v)
    v = v.groupby(["data", "sku"], as_index=False)["quantidade_vendida"].sum()
    col.info(VENDAS, "Vendas do mesmo produto no mesmo dia somadas", antes - len(v))
    v["nome_produto"] = v["sku"].map(nome_do_sku)
    return v.sort_values(["sku", "data"], ignore_index=True)[colunas]
