from decimal import Decimal

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    PERCENTUAL_DESCONTO_MAXIMO,
    ItemVenda,
    MovimentacaoEstoque,
    Pagamento,
    Produto,
    Venda,
)
from .permissions import can_access_store, is_manager


ZERO = Decimal("0.00")
ASSINATURA_PREVIA_SALT = "loja.pdv.previa-venda"


class PreviaDesatualizada(Exception):
    pass


def normalizar_carrinho(carrinho):
    if not isinstance(carrinho, dict) or not carrinho:
        raise ValidationError("O carrinho está vazio.")

    itens = {}
    for produto_id, quantidade in carrinho.items():
        try:
            produto_id = int(produto_id)
            quantidade = int(quantidade)
        except (TypeError, ValueError):
            raise ValidationError("O carrinho contém um produto ou quantidade inválida.")
        if produto_id <= 0 or quantidade <= 0 or produto_id in itens:
            raise ValidationError("O carrinho contém um produto ou quantidade inválida.")
        itens[produto_id] = quantidade
    return itens


def _carregar_produtos(carrinho, *, bloquear=False):
    ids = sorted(carrinho)
    queryset = Produto.objects.filter(pk__in=ids, ativo=True).order_by("pk")
    if bloquear:
        queryset = queryset.select_for_update()
    produtos = list(queryset)
    if len(produtos) != len(ids):
        raise ValidationError("Um produto do carrinho foi removido ou arquivado.")
    return produtos


def _montar_itens(carrinho, produtos):
    itens = []
    snapshot = []
    subtotal = ZERO
    for produto in produtos:
        quantidade = carrinho[produto.pk]
        if quantidade > produto.quantidade:
            raise ValidationError(
                f"Estoque insuficiente para {produto.nome}. Disponível: {produto.quantidade}."
            )
        item_subtotal = produto.preco * quantidade
        subtotal += item_subtotal
        itens.append({
            "produto": produto,
            "quantidade": quantidade,
            "preco_unitario": produto.preco,
            "subtotal": item_subtotal,
        })
        snapshot.append([
            produto.pk,
            quantidade,
            str(produto.preco),
            produto.nome,
            produto.codigo_barras or "",
        ])
    return itens, subtotal, snapshot


def montar_previa_carrinho(carrinho):
    carrinho = normalizar_carrinho(carrinho)
    produtos = _carregar_produtos(carrinho)
    itens, subtotal, snapshot = _montar_itens(carrinho, produtos)
    return {
        "itens": itens,
        "subtotal": subtotal,
        "snapshot": snapshot,
    }


def assinar_previa(
    snapshot,
    *,
    forma_pagamento=None,
    desconto=None,
    valor_recebido=None,
):
    payload = snapshot
    if forma_pagamento is not None:
        payload = {
            "snapshot": snapshot,
            "forma_pagamento": forma_pagamento,
            "desconto": str(Decimal(desconto or ZERO)),
            "valor_recebido": str(valor_recebido) if valor_recebido is not None else None,
        }
    return signing.dumps(payload, salt=ASSINATURA_PREVIA_SALT)


def _nome_usuario(usuario):
    return usuario.get_full_name().strip() or usuario.get_username()


@transaction.atomic
def finalizar_venda(
    *,
    carrinho,
    usuario,
    forma_pagamento,
    desconto=ZERO,
    valor_recebido=None,
    token_previa,
):
    if not can_access_store(usuario):
        raise PermissionDenied
    try:
        desconto = Decimal(desconto or ZERO)
    except (TypeError, ValueError):
        raise ValidationError({"desconto": "Informe um desconto válido."})
    if desconto < ZERO:
        raise ValidationError({"desconto": "O desconto não pode ser negativo."})
    if desconto > ZERO and not is_manager(usuario):
        raise PermissionDenied

    carrinho = normalizar_carrinho(carrinho)
    produtos = _carregar_produtos(carrinho, bloquear=True)
    itens, subtotal, snapshot = _montar_itens(carrinho, produtos)

    if desconto > subtotal * PERCENTUAL_DESCONTO_MAXIMO:
        raise ValidationError({"desconto": "O desconto máximo é 10% do subtotal."})
    total = subtotal - desconto
    if total <= ZERO:
        raise ValidationError({"desconto": "O total da venda deve ser maior que zero."})

    formas_validas = {choice for choice, _ in Pagamento.FormaPagamento.choices}
    if forma_pagamento not in formas_validas:
        raise ValidationError({"forma_pagamento": "Selecione uma forma de pagamento válida."})
    if forma_pagamento == Pagamento.FormaPagamento.DINHEIRO:
        if valor_recebido is None or valor_recebido < total:
            raise ValidationError({"valor_recebido": "O valor recebido deve cobrir o total da venda."})
        troco = valor_recebido - total
    else:
        if valor_recebido is not None:
            raise ValidationError({"valor_recebido": "Informe o valor recebido apenas para pagamentos em dinheiro."})
        troco = ZERO

    try:
        assinatura_anterior = signing.loads(
            token_previa,
            salt=ASSINATURA_PREVIA_SALT,
            max_age=1800,
        )
    except signing.BadSignature:
        raise PreviaDesatualizada
    if isinstance(assinatura_anterior, dict):
        valores_confirmados = {
            "forma_pagamento": forma_pagamento,
            "desconto": str(desconto),
            "valor_recebido": str(valor_recebido) if valor_recebido is not None else None,
        }
        if assinatura_anterior.get("snapshot") != snapshot:
            raise PreviaDesatualizada
        if any(assinatura_anterior.get(chave) != valor for chave, valor in valores_confirmados.items()):
            raise PreviaDesatualizada
    elif assinatura_anterior != snapshot:
        raise PreviaDesatualizada

    nome_responsavel = _nome_usuario(usuario)
    venda = Venda(
        usuario=usuario,
        usuario_nome=nome_responsavel,
        subtotal=subtotal,
        desconto=desconto,
        total=total,
        gerente_autorizador=usuario if desconto > ZERO else None,
        gerente_autorizador_nome=nome_responsavel if desconto > ZERO else "",
    )
    venda.full_clean()
    venda.save()

    for item_resumo in itens:
        produto = item_resumo["produto"]
        quantidade = item_resumo["quantidade"]
        item = ItemVenda(
            venda=venda,
            produto=produto,
            nome_produto=produto.nome,
            codigo_barras=produto.codigo_barras or "",
            preco_unitario=produto.preco,
            custo_unitario=produto.custo_aquisicao,
            quantidade=quantidade,
            subtotal=item_resumo["subtotal"],
        )
        item.full_clean()
        item.save()

        saldo_anterior = produto.quantidade
        produto.quantidade -= quantidade
        produto.save(update_fields=["quantidade"])

        movimento = MovimentacaoEstoque(
            produto=produto,
            item_venda=item,
            tipo=MovimentacaoEstoque.Tipo.VENDA,
            variacao_quantidade=-quantidade,
            quantidade_anterior=saldo_anterior,
            quantidade_posterior=produto.quantidade,
            responsavel=usuario,
            responsavel_nome=nome_responsavel,
        )
        movimento.full_clean()
        movimento.save()

    pagamento = Pagamento(
        venda=venda,
        forma_pagamento=forma_pagamento,
        valor_pago=total,
        valor_recebido=valor_recebido,
        troco=troco,
    )
    pagamento.full_clean()
    pagamento.save()
    return venda


@transaction.atomic
def cancelar_venda(*, venda_id, usuario, motivo):
    if not can_access_store(usuario):
        raise PermissionDenied
    if not motivo or not motivo.strip():
        raise ValidationError({"motivo_cancelamento": "Informe o motivo do cancelamento."})

    venda = Venda.objects.select_for_update().get(pk=venda_id)
    if venda.status != Venda.Status.FINALIZADA:
        raise ValidationError("Esta venda já foi cancelada.")

    itens = list(venda.itens.order_by("produto_id", "pk"))
    if not itens:
        raise ValidationError("A venda não possui itens para estornar.")
    produtos = {
        produto.pk: produto
        for produto in Produto.objects.select_for_update()
        .filter(pk__in={item.produto_id for item in itens})
        .order_by("pk")
    }
    if len(produtos) != len({item.produto_id for item in itens}):
        raise ValidationError("Um produto da venda não está disponível para estorno.")

    nome_responsavel = _nome_usuario(usuario)
    for item in itens:
        produto = produtos[item.produto_id]
        try:
            movimento_original = MovimentacaoEstoque.objects.select_for_update().get(
                item_venda=item,
                tipo=MovimentacaoEstoque.Tipo.VENDA,
                movimento_estornado__isnull=True,
            )
        except MovimentacaoEstoque.DoesNotExist:
            raise ValidationError("Não foi encontrada a baixa de estoque original desta venda.")

        saldo_anterior = produto.quantidade
        saldo_posterior = saldo_anterior + item.quantidade
        produto.quantidade = saldo_posterior
        produto.save(update_fields=["quantidade"])

        estorno = MovimentacaoEstoque(
            produto=produto,
            item_venda=item,
            tipo=MovimentacaoEstoque.Tipo.ESTORNO_VENDA,
            variacao_quantidade=item.quantidade,
            quantidade_anterior=saldo_anterior,
            quantidade_posterior=saldo_posterior,
            responsavel=usuario,
            responsavel_nome=nome_responsavel,
            motivo=motivo.strip(),
            movimento_estornado=movimento_original,
        )
        estorno.full_clean()
        estorno.save()

    venda.status = Venda.Status.CANCELADA
    venda.data_cancelamento = timezone.now()
    venda.usuario_cancelamento = usuario
    venda.usuario_cancelamento_nome = nome_responsavel
    venda.motivo_cancelamento = motivo.strip()
    venda.full_clean()
    venda.save(update_fields=[
        "status",
        "data_cancelamento",
        "usuario_cancelamento",
        "usuario_cancelamento_nome",
        "motivo_cancelamento",
    ])
    return venda
