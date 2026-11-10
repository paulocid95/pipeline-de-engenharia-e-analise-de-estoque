from assistente_estoque import verificar_limite_perguntas


def test_libera_primeira_pergunta():
    assert verificar_limite_perguntas(0, None, agora=1000.0, limite=10, intervalo_minimo=5) is None


def test_libera_apos_intervalo_minimo():
    assert verificar_limite_perguntas(3, 1000.0, agora=1005.0, limite=10, intervalo_minimo=5) is None


def test_bloqueia_perguntas_em_sequencia_rapida():
    mensagem = verificar_limite_perguntas(3, 1000.0, agora=1002.0, limite=10, intervalo_minimo=5)
    assert mensagem is not None and "Aguarde" in mensagem


def test_bloqueia_ao_atingir_limite_da_sessao():
    mensagem = verificar_limite_perguntas(10, None, agora=1000.0, limite=10, intervalo_minimo=5)
    assert mensagem is not None and "limite de 10" in mensagem
