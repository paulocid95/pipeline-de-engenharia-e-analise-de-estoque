from datetime import date

import pandas as pd
import pytest

from higienizacao import (
    COTACOES, ESTOQUE, OCORRENCIAS, VENDAS, EntradaTabela, ErroArquivo, higienizar, ler_arquivo, preparar, remapear,
)
from higienizacao.colunas import detectar_tipo, encontrar_cabecalho, mapear_colunas
from higienizacao.conversores import para_data, para_numero
from higienizacao.entidades import (
    categoria_padrao, chave_fornecedor, gravidade, nome_de_exibicao, parecidos, status_ocorrencia, tipo_ocorrencia,
)
from planilha_exemplo import montar_planilha_exemplo
from regras_fornecedores import calcular_penalidades, ranking_fornecedores
from tests.test_planilha_exemplo import COTACOES as COT_DEMO
from tests.test_planilha_exemplo import ESTOQUE as EST_DEMO
from tests.test_planilha_exemplo import HOJE
from tests.test_planilha_exemplo import OCORRENCIAS as OC_DEMO


def _csv(texto: str, codificacao: str = "utf-8") -> bytes:
    return texto.encode(codificacao)


def _limpar_csvs(*arquivos, **kwargs):
    tabelas = [t for nome, conteudo in arquivos for t in ler_arquivo(nome, conteudo)]
    return higienizar(preparar(tabelas), hoje=HOJE, **kwargs)


# ------------------------------------------------------------------------------
# Conversores
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("bruto, esperado", [
    ("R$ 4.299,00", 4299.0), ("R$1,234.56", 1234.56), ("1.234,56", 1234.56), ("1234.56", 1234.56),
    ("89,9", 89.9), ("4.599", 4599.0), ("0.5", 0.5), (3699.5, 3699.5), ("12 un", 12.0), ("12,0", 12.0),
    ("15 pçs", 15.0), ("7 dias", 7.0), ("5d", 5.0), ("3 dia(s)", 3.0), ("doze", 12.0), ("-3", -3.0),
    ("1.234.567", 1234567.0), ("R$ 1 299,90", 1299.9),
])
def test_para_numero(bruto, esperado):
    assert para_numero(bruto) == pytest.approx(esperado)


@pytest.mark.parametrize("bruto", [None, "", "   ", "consultar", float("nan")])
def test_para_numero_sem_numero(bruto):
    assert para_numero(bruto) is None


@pytest.mark.parametrize("bruto", [
    "05/03/2026", "05.03.2026", "2026-03-05", "05-03-2026", "05/03/26", date(2026, 3, 5),
    pd.Timestamp("2026-03-05"), "2026-03-05 00:00:00", 46086,
])
def test_para_data(bruto):
    assert para_data(bruto) == date(2026, 3, 5)


def test_para_data_invalida():
    assert para_data("ontem") is None and para_data("") is None and para_data(12) is None


# ------------------------------------------------------------------------------
# Colunas e tipos de tabela
# ------------------------------------------------------------------------------
def test_mapeia_nomes_variados_de_colunas():
    mapa = mapear_colunas(["Cód. Item", "Descrição do Produto", "Depto", "Fornec.", "Preço Unit.", "Qtd Disp.",
                           "Est. Mínimo", "Cor"], ESTOQUE)
    assert mapa == {"sku": 0, "produto": 1, "categoria": 2, "fornecedor": 3, "preco": 4, "quantidade": 5,
                    "estoque_minimo": 6}


def test_estoque_minimo_nao_e_confundido_com_quantidade():
    mapa = mapear_colunas(["Produto", "Estoque", "Estoque mínimo", "Preço"], ESTOQUE)
    assert mapa["quantidade"] == 1 and mapa["estoque_minimo"] == 2


def test_encontra_cabecalho_abaixo_de_titulo():
    bruta = pd.DataFrame([["RELATÓRIO DE ESTOQUE", None, None], [None, None, None],
                          ["Produto", "Qtd", "Preço"], ["Camiseta", 3, 49.9]])
    assert encontrar_cabecalho(bruta)[0] == 2


@pytest.mark.parametrize("cabecalhos, nome, esperado", [
    (["Produto", "Quantidade", "Preço", "Categoria"], "planilha1", ESTOQUE),
    (["SKU", "Item", "Fornecedor", "Valor Cotado", "Prazo Entrega"], "planilha2", COTACOES),
    (["Fornecedor", "Problema", "Data", "Situação"], "planilha3", OCORRENCIAS),
    (["Data", "SKU", "Qtd Vendida"], "planilha4", VENDAS),
    (["Data", "Produto", "Quantidade"], "vendas_2026", VENDAS),
])
def test_detecta_tipo_da_tabela(cabecalhos, nome, esperado):
    bruta = pd.DataFrame([cabecalhos, ["x"] * len(cabecalhos)])
    assert detectar_tipo(bruta, nome).tipo == esperado


def test_tabela_sem_dados_reconheciveis_nao_tem_tipo():
    bruta = pd.DataFrame([["Leia-me"], ["Esta planilha serve para..."]])
    assert detectar_tipo(bruta, "Instruções").tipo is None


# ------------------------------------------------------------------------------
# Fornecedores, categorias e ocorrências
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("variante", ["Fornecedor A", "FORNECEDOR A LTDA", "forn. a", "Fornecedor_A", " fornecedor a "])
def test_grafias_do_mesmo_fornecedor_viram_uma_chave(variante):
    assert chave_fornecedor(variante) == "fornecedor a"


def test_nome_de_exibicao_prefere_grafia_bem_escrita():
    assert nome_de_exibicao("fornecedor a", ["FORNECEDOR A LTDA", "forn. a", "Fornecedor A"]) == "Fornecedor A"
    assert nome_de_exibicao("fornecedor a", ["FORNECEDOR A LTDA", "forn. a"]) == "Fornecedor A"


def test_fornecedores_parecidos_viram_duvida_mas_letras_diferentes_nao():
    assert parecidos("distribuidora paulista", "distribuidora paulsta")
    assert parecidos("fornecedor a", "fornecedor b") is None
    assert parecidos("malharia sul", "eletronicos norte") is None


@pytest.mark.parametrize("texto, codigo", [
    ("Atraso na entrega", "ATRASO"), ("Entregou atrasado", "ATRASO"), ("produto quebrado", "DEFEITO"),
    ("Veio faltando 2 peças", "ITEM_ERRADO_FALTANDO"), ("Processo no PROCON", "JUDICIAL"),
    ("Divergência de preço na NF", "DIVERGENCIA_PRECO_NF"), ("Caixa amassada no transporte", "AVARIA_TRANSPORTE"),
    ("Sem retorno do SAC", "FALHA_ATENDIMENTO"), ("Problema com etiqueta", "OUTROS"), ("", "OUTROS"),
])
def test_tipo_de_ocorrencia_por_palavras(texto, codigo):
    assert tipo_ocorrencia(texto) == codigo


@pytest.mark.parametrize("texto, codigo", [
    ("Alta", "ALTA"), ("MÉDIA", "MEDIA"), ("leve", "BAIXA"), ("Crítica", "CRITICA"), ("muito alta", "CRITICA"),
    ("3", "ALTA"), ("", None),
])
def test_gravidade(texto, codigo):
    assert gravidade(texto) == codigo


@pytest.mark.parametrize("texto, codigo", [
    ("Resolvido", "RESOLVIDO"), ("EM ABERTO", "ABERTO"), ("em andamento", "EM_ANDAMENTO"),
    ("Não resolvido", "ABERTO"), ("concluído", "RESOLVIDO"), ("aguardando fornecedor", "EM_ANDAMENTO"),
])
def test_status(texto, codigo):
    assert status_ocorrencia(texto) == codigo


def test_categorias_do_ramo_e_categorias_proprias():
    assert categoria_padrao("celular", "Galaxy") == ("Smartphones", False)
    assert categoria_padrao("", "Fone JBL Tune") == ("Fones de Ouvido", True)
    assert categoria_padrao("vestuário", "Camiseta") == ("Vestuário", False)


# ------------------------------------------------------------------------------
# Ida e volta: a planilha de exemplo bagunçada volta a ser a demonstração
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [42, 1, 7, 99])
def test_planilha_de_exemplo_volta_aos_dados_originais(seed):
    arquivo = montar_planilha_exemplo(EST_DEMO, COT_DEMO, OC_DEMO, HOJE, seed=seed)
    r = higienizar(preparar(ler_arquivo("exemplo.xlsx", arquivo)), hoje=HOJE)
    assert r.ok and not r.pendencias and not r.descartes and not r.duvidas

    est = r.estoque.set_index("sku").sort_index()
    orig = EST_DEMO.set_index("sku").sort_index()
    assert est["nome_produto"].tolist() == orig["nome_produto"].tolist()
    assert est["nome_categoria"].tolist() == orig["nome_categoria"].tolist()
    assert est["fornecedor"].tolist() == orig["fornecedor"].tolist()
    assert est["preco_unitario"].tolist() == pytest.approx(orig["preco_unitario"].tolist())
    assert est["quantidade_disponivel"].tolist() == orig["quantidade_disponivel"].tolist()

    cot = r.cotacoes.sort_values("fornecedor_cotacao", ignore_index=True)
    assert cot["fornecedor_cotacao"].tolist() == ["Fornecedor B", "Fornecedor D"]
    assert cot["preco_cotado"].tolist() == pytest.approx([4100.5, 3899.0])
    assert cot["prazo_dias"].tolist() == [4, 9] and cot["lote_minimo"].tolist() == [5, 20]

    oc = r.ocorrencias.iloc[0]
    assert (oc["fornecedor"], oc["tipo"], oc["gravidade"], oc["status"]) == ("Fornecedor D", "JUDICIAL", "ALTA", "ABERTO")
    assert oc["data_ocorrencia"] == date(2026, 10, 5)

    assert len(r.vendas) == 90 * len(EST_DEMO)
    assert r.vendas["quantidade_vendida"].dtype.kind == "i"


def test_relatorio_lista_as_correcoes():
    arquivo = montar_planilha_exemplo(EST_DEMO, COT_DEMO, OC_DEMO, HOJE)
    r = higienizar(preparar(ler_arquivo("exemplo.xlsx", arquivo)), hoje=HOJE)
    mensagens = " ".join(i.mensagem for i in r.relatorio)
    assert "TOTAL" in mensagens and "título" in mensagens and "unificadas" in mensagens


# ------------------------------------------------------------------------------
# Planilhas de outros ramos, CSV, dúvidas e pendências
# ------------------------------------------------------------------------------
LOJA_ROUPAS = """Relatório da loja;;;;
Código;Peça;Seção;Saldo;Valor unitário;Estoque mínimo
C01;Camiseta Básica P;vestuário;"30 un";R$ 49,90;40
C02;Calça Jeans 42;Vestuário;8;R$ 159,90;
C01;Camiseta Básica P;vestuário;10;R$ 49,90;40
B01;Boneco Articulado;Brinquedos;0;89,9;
TOTAL;;;48;;
"""


def test_csv_de_outro_ramo_com_limites_proprios():
    r = _limpar_csvs(("estoque_loja.csv", _csv(LOJA_ROUPAS, "cp1252")), limite_alerta=5, limite_excesso=50)
    est = r.estoque.set_index("sku")
    assert sorted(est.index) == ["B01", "C01", "C02"]
    assert est.loc["C01", "quantidade_disponivel"] == 40                 # duplicado somado
    assert est.loc["C01", "status_reposicao"] == "ALERTA"                # 40 <= estoque mínimo próprio (40)
    assert est.loc["C02", "status_reposicao"] == "NORMAL"                # 8 > limite informado (5)
    assert est.loc["B01", "status_reposicao"] == "CRITICO"
    assert set(est["nome_categoria"]) == {"Vestuário", "Brinquedos"}
    assert est.loc["C02", "preco_unitario"] == pytest.approx(159.9)


def test_produto_parecido_vira_duvida_e_decisao_liga_a_cotacao():
    estoque = _csv("Produto;Qtd;Preço\nGalaxy S23 128GB;5;4299\n")
    cotacoes = _csv("Produto;Fornecedor;Valor;Prazo\nGalaxy S23 128 GB;Distribuidora Alfa;4100;5\n")
    sem_decisao = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes))
    assert [d.tipo for d in sem_decisao.duvidas] == ["produto"]
    assert sem_decisao.cotacoes.empty and sem_decisao.descartes

    duvida = sem_decisao.duvidas[0]
    com_decisao = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes), decisoes={duvida.chave: True})
    assert len(com_decisao.cotacoes) == 1
    assert com_decisao.cotacoes.loc[0, "nome_produto"] == "Galaxy S23 128GB"


def test_fornecedores_parecidos_so_sao_unidos_com_confirmacao():
    estoque = _csv("Produto;Qtd;Preço\nCamiseta;5;50\n")
    cotacoes = _csv("Produto;Fornecedor;Valor\nCamiseta;Malharia Esperanca;40\nCamiseta;Malharia Esperana;42\n")
    r = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes))
    assert len(r.duvidas) == 1 and r.duvidas[0].tipo == "fornecedor"
    assert r.cotacoes["fornecedor_cotacao"].nunique() == 2
    r2 = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes), decisoes={r.duvidas[0].chave: True})
    assert r2.cotacoes["fornecedor_cotacao"].nunique() == 1


def test_cotacoes_sem_prazo_e_lote_recebem_valores_padrao():
    estoque = _csv("Produto;Qtd;Preço\nCamiseta;5;50\nCalça;3;120\n")
    cotacoes = _csv("Produto;Fornecedor;Valor;Prazo\nCamiseta;Malharia Sul;40;10\nCalça;Malharia Sul;100;\n")
    r = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes))
    assert r.cotacoes["prazo_dias"].tolist() == [10, 10] and r.cotacoes["lote_minimo"].tolist() == [1, 1]
    assert r.ocorrencias is None                                         # aba não enviada
    sem_ocorrencias = pd.DataFrame(columns=["fornecedor", "tipo", "gravidade", "data_ocorrencia", "status", "data_resolucao"])
    ranking = ranking_fornecedores(r.cotacoes, sem_ocorrencias, HOJE, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")
    assert not ranking.empty


def test_ocorrencias_desconhecidas_e_resolvidas_sem_data_nao_quebram_o_ranking():
    estoque = _csv("Produto;Qtd;Preço\nCamiseta;5;50\n")
    cotacoes = _csv("Produto;Fornecedor;Valor\nCamiseta;Malharia Sul;40\n")
    ocorrencias = _csv("Fornecedor;Problema;Data;Situação\nMalharia Sul;Etiqueta trocada de cor;01/11/2026;Resolvido\n"
                       "malharia sul ltda;Fora do prazo;10/11/2026;\n")
    r = _limpar_csvs(("estoque.csv", estoque), ("cotacoes.csv", cotacoes), ("ocorrencias.csv", ocorrencias))
    assert sorted(r.ocorrencias["tipo"]) == ["ATRASO", "ITEM_ERRADO_FALTANDO"]   # "trocada" = item errado
    assert set(r.ocorrencias["fornecedor"]) == {"Malharia Sul"}
    assert calcular_penalidades(r.ocorrencias, HOJE)["penalidade"].notna().all()
    ranking = ranking_fornecedores(r.cotacoes, r.ocorrencias, HOJE, chave_produto="sku", coluna_fornecedor="fornecedor_cotacao")
    assert len(ranking) == 1 and ranking["nota_final"].notna().all()


def test_tipo_nao_reconhecido_vira_outros_no_relatorio():
    estoque = _csv("Produto;Qtd;Preço\nCamiseta;5;50\n")
    ocorrencias = _csv("Fornecedor;Problema;Data\nMalharia Sul;Etiqueta ilegível;01/11/2026\n")
    r = _limpar_csvs(("estoque.csv", estoque), ("ocorrencias.csv", ocorrencias))
    assert r.ocorrencias["tipo"].tolist() == ["OUTROS"]
    assert any("Outros" in i.mensagem for i in r.relatorio)


def test_linhas_invalidas_vao_para_descartes_com_motivo():
    estoque = _csv("Produto;Qtd;Preço\nCamiseta;5;consultar\nCalça;muitas;100\nBoné;2;30\n")
    r = _limpar_csvs(("estoque.csv", estoque))
    assert r.estoque["nome_produto"].tolist() == ["Boné"]
    motivos = [d["motivo"] for d in r.descartes]
    assert any("Preço inválido" in m for m in motivos) and any("Quantidade ilegível" in m for m in motivos)


def test_falta_coluna_obrigatoria_vira_pendencia():
    r = _limpar_csvs(("estoque.csv", _csv("Produto;Preço\nCamiseta;50\n")))
    assert not r.ok


def test_usuario_pode_corrigir_o_tipo_da_tabela():
    tabela = ler_arquivo("dados.csv", _csv("Data;Produto;Quantidade\n01/11/2026;Camiseta;3\n"))[0]
    entrada = preparar([tabela])[0]
    corrigida = remapear(entrada, VENDAS)
    assert isinstance(corrigida, EntradaTabela) and corrigida.tipo == VENDAS
    assert {"data", "produto", "quantidade"} <= corrigida.mapa.keys()


def test_arquivo_grande_ou_formato_errado_gera_erro_amigavel():
    with pytest.raises(ErroArquivo, match="5 MB"):
        ler_arquivo("enorme.csv", b"a" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ErroArquivo, match="Excel"):
        ler_arquivo("foto.png", b"123")
    linhas = "Produto;Qtd;Preço\n" + "x;1;1\n" * 10_100
    with pytest.raises(ErroArquivo, match="limite"):
        ler_arquivo("grande.csv", _csv(linhas))
