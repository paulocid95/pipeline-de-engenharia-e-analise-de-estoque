import pytest

from regras_estoque import classificar_status


@pytest.mark.parametrize(
    "quantidade, esperado",
    [
        (-5, "CRITICO"),
        (0, "CRITICO"),
        (1, "ALERTA"),
        (15, "ALERTA"),
        (16, "NORMAL"),
        (100, "NORMAL"),
        (101, "EXCESSO"),
    ],
)
def test_classificar_status_nos_limites_das_faixas(quantidade, esperado):
    assert classificar_status(quantidade) == esperado
