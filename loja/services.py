from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import MovimentacaoEstoque, Produto
from .permissions import can_access_store, is_manager


@transaction.atomic
def registrar_movimentacao(
    *,
    produto_id,
    tipo,
    quantidade,
    responsavel,
    motivo,
):
    tipos_operacionais = {
        MovimentacaoEstoque.Tipo.ENTRADA,
        MovimentacaoEstoque.Tipo.SAIDA_MANUAL,
        MovimentacaoEstoque.Tipo.PERDA,
        MovimentacaoEstoque.Tipo.AJUSTE,
    }
    if tipo not in tipos_operacionais:
        raise ValidationError("Tipo de movimentação inválido.")
    if not can_access_store(responsavel):
        raise PermissionDenied
    if tipo in {
        MovimentacaoEstoque.Tipo.SAIDA_MANUAL,
        MovimentacaoEstoque.Tipo.AJUSTE,
    } and not is_manager(responsavel):
        raise PermissionDenied
    if not motivo or not motivo.strip():
        raise ValidationError({"motivo": "Informe o motivo da movimentação."})
    if not isinstance(quantidade, int) or isinstance(quantidade, bool):
        raise ValidationError({"quantidade": "Informe uma quantidade inteira."})

    produto = Produto.objects.select_for_update().get(pk=produto_id)
    saldo_anterior = produto.quantidade

    if tipo == MovimentacaoEstoque.Tipo.AJUSTE:
        if quantidade < 0:
            raise ValidationError({"quantidade": "O saldo contado não pode ser negativo."})
        saldo_posterior = quantidade
        variacao = saldo_posterior - saldo_anterior
        if variacao == 0:
            raise ValidationError({"quantidade": "O saldo já corresponde à quantidade informada."})
    else:
        if quantidade <= 0:
            raise ValidationError({"quantidade": "Informe uma quantidade maior que zero."})
        variacao = (
            quantidade
            if tipo == MovimentacaoEstoque.Tipo.ENTRADA
            else -quantidade
        )
        saldo_posterior = saldo_anterior + variacao
        if saldo_posterior < 0:
            raise ValidationError({"quantidade": "A saída excede o estoque disponível."})

    produto.quantidade = saldo_posterior
    produto.save(update_fields=["quantidade"])

    nome_responsavel = responsavel.get_full_name().strip() or responsavel.get_username()
    movimentacao = MovimentacaoEstoque(
        produto=produto,
        tipo=tipo,
        variacao_quantidade=variacao,
        quantidade_anterior=saldo_anterior,
        quantidade_posterior=saldo_posterior,
        responsavel=responsavel,
        responsavel_nome=nome_responsavel,
        motivo=motivo.strip(),
    )
    movimentacao.full_clean()
    movimentacao.save()
    return movimentacao
