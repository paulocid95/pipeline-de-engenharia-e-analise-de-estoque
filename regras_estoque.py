"""Regras de negócio de status de reposição do estoque (fonte única para todo o projeto)."""

LIMITE_ALERTA = 15    # até 15 unidades: baixa cobertura
LIMITE_EXCESSO = 100  # acima de 100 unidades: capital imobilizado em excesso


def classificar_status(
    quantidade: int, limite_alerta: int = LIMITE_ALERTA, limite_excesso: int = LIMITE_EXCESSO,
) -> str:
    """Classifica a quantidade em estoque em CRITICO, ALERTA, NORMAL ou EXCESSO.

    Os limites podem ser os do negócio do usuário; sem informar, valem os padrões acima.
    """
    if quantidade <= 0:
        return "CRITICO"
    if quantidade <= limite_alerta:
        return "ALERTA"
    if quantidade > limite_excesso:
        return "EXCESSO"
    return "NORMAL"
