import json

import httpx
import pandas as pd

import assistente_estoque as ae
from tests.test_planilha_exemplo import HOJE

RESPOSTA_LONGA = "Recomendo comprar do Fornecedor B, que tem a melhor nota geral e entrega em 4 dias úteis."


def _cliente(respostas: dict, chamadas: list) -> httpx.Client:
    """Simula a API do Groq: `respostas` = modelo -> (status, conteúdo)."""
    def tratar(request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        chamadas.append(corpo)
        status, conteudo = respostas.get(corpo["model"], (404, ""))
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "x"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": conteudo}}]})
    return httpx.Client(transport=httpx.MockTransport(tratar))


MENSAGENS = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(9)]


def test_groq_assume_quando_o_gemini_falha(monkeypatch):
    monkeypatch.setattr(ae, "_tentar_gemini", lambda *a, **k: (None, "503"))
    chamadas = []
    cliente = _cliente({"openai/gpt-oss-20b": (200, "<think>pensando...</think>" + RESPOSTA_LONGA)}, chamadas)
    r = ae.obter_resposta(MENSAGENS, "CONTEXTO COMPLETO", "chave-gemini", chave_groq="chave-groq",
                          contexto_enxuto="CONTEXTO ENXUTO", cliente_groq=cliente)
    assert r.texto == RESPOSTA_LONGA and r.origem == "Groq (gpt-oss-20b)"
    assert [c["model"] for c in chamadas] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    enviado = chamadas[-1]["messages"]
    assert "CONTEXTO ENXUTO" in enviado[0]["content"] and "CONTEXTO COMPLETO" not in enviado[0]["content"]
    assert len(enviado) == 1 + ae.MENSAGENS_GROQ and enviado[-1]["content"] == "msg 8"


def test_gemini_responde_e_groq_nem_e_chamado(monkeypatch):
    monkeypatch.setattr(ae, "_tentar_gemini", lambda *a, **k: (RESPOSTA_LONGA, "gemini-3.5-flash"))
    chamadas = []
    r = ae.obter_resposta(MENSAGENS, "C", "chave-gemini", chave_groq="chave-groq", cliente_groq=_cliente({}, chamadas))
    assert r.origem == "Google Gemini (gemini-3.5-flash)" and chamadas == []


def test_todos_falham_mostra_aviso_sem_origem(monkeypatch):
    monkeypatch.setattr(ae, "_tentar_gemini", lambda *a, **k: (None, "429"))
    chamadas = []
    cliente = _cliente({m: (429, "") for m in ae.MODELOS_GROQ}, chamadas)
    r = ae.obter_resposta(MENSAGENS, "C", "chave-gemini", chave_groq="chave-groq", cliente_groq=cliente)
    assert r.texto == ae.MSG_INDISPONIVEL and r.origem is None and len(chamadas) == len(ae.MODELOS_GROQ)


def test_sem_nenhuma_chave():
    r = ae.obter_resposta(MENSAGENS, "C", "", chave_groq="")
    assert r.texto == ae.MSG_SEM_CHAVE and r.origem is None


def test_so_groq_configurado(monkeypatch):
    monkeypatch.setattr(ae, "_tentar_gemini", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria")))
    cliente = _cliente({"openai/gpt-oss-120b": (200, RESPOSTA_LONGA)}, [])
    r = ae.obter_resposta(MENSAGENS, "C", "", chave_groq="chave-groq", cliente_groq=cliente)
    assert r.origem == "Groq (gpt-oss-120b)"


def test_provedores_citados_no_aviso():
    assert ae.provedores_ativos("g", "q") == ["Google Gemini", "Groq"]
    assert ae.provedores_ativos("g", "") == ["Google Gemini"]


def test_contexto_enxuto_resume_listas_grandes():
    estoque = pd.DataFrame({
        "sku": [f"P{i:02d}" for i in range(30)], "nome_produto": [f"Produto {i}" for i in range(30)],
        "nome_categoria": "Geral", "preco_unitario": 10.0, "estoque_minimo": None,
        "quantidade_disponivel": [0] * 25 + [50] * 5, "valor_total_estoque": 0.0,
        "status_reposicao": ["CRITICO"] * 25 + ["NORMAL"] * 5,
    })
    cot = pd.DataFrame({"sku": estoque["sku"], "nome_produto": estoque["nome_produto"], "fornecedor": "Loja X",
                        "preco_cotado": 9.0, "lote_minimo": 1, "prazo_dias": 3})
    oc = pd.DataFrame(columns=["fornecedor", "tipo", "gravidade", "data_ocorrencia", "status", "data_resolucao"])
    completo = ae.montar_contexto(estoque, cot, oc, HOJE)
    enxuto = ae.montar_contexto(estoque, cot, oc, HOJE, enxuto=True)
    assert len(enxuto) < len(completo) / 2
    assert "DEMAIS PRODUTOS" in completo and "DEMAIS PRODUTOS" not in enxuto
    assert "[P09]" in enxuto and "[P10]" not in enxuto and "mais 15 itens" in enxuto
