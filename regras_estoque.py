"""Regras de negócio de status de reposição do estoque (fonte única para todo o projeto)."""

LIMITE_ALERTA = 15    # até 15 unidades: baixa cobertura
LIMITE_EXCESSO = 100  # acima de 100 unidades: capital imobilizado em excesso


def classificar_status(quantidade: int) -> str:
    """Classifica a quantidade em estoque em CRITICO, ALERTA, NORMAL ou EXCESSO."""
    if quantidade <= 0:
        return "CRITICO"
    if quantidade <= LIMITE_ALERTA:
        return "ALERTA"
    if quantidade > LIMITE_EXCESSO:
        return "EXCESSO"
    return "NORMAL"
