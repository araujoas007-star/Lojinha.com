from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from .models import Categoria, MovimentacaoEstoque, Pagamento, Produto, Venda
from .permissions import ATENDENTE_GROUP
from .vendas import assinar_previa, finalizar_venda, montar_previa_carrinho


class VendaConcorrenteTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_sale_succeeds_when_both_need_the_last_unit(self):
        grupo, _ = Group.objects.get_or_create(name=ATENDENTE_GROUP)
        usuario = get_user_model().objects.create_user(username="caixa")
        usuario.groups.add(grupo)
        categoria = Categoria.objects.create(nome="Concorrência")
        produto = Produto.objects.create(
            nome="Última unidade", preco="10.00", quantidade=1, categoria=categoria
        )
        carrinho = {produto.pk: 1}
        token = assinar_previa(montar_previa_carrinho(carrinho)["snapshot"])
        barreira = Barrier(2, timeout=15)

        def vender():
            close_old_connections()
            try:
                operador = get_user_model().objects.get(pk=usuario.pk)
                barreira.wait()
                try:
                    finalizar_venda(
                        carrinho=carrinho,
                        usuario=operador,
                        forma_pagamento=Pagamento.FormaPagamento.PIX,
                        token_previa=token,
                    )
                except ValidationError:
                    return "sem estoque"
                return "vendida"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            tarefas = [executor.submit(vender) for _ in range(2)]
            resultados = [tarefa.result(timeout=30) for tarefa in tarefas]

        produto.refresh_from_db()
        self.assertCountEqual(resultados, ["vendida", "sem estoque"])
        self.assertEqual(produto.quantidade, 0)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(
            MovimentacaoEstoque.objects.filter(tipo=MovimentacaoEstoque.Tipo.VENDA).count(),
            1,
        )
