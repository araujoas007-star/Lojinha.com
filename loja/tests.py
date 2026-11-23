from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    Categoria,
    ItemVenda,
    MovimentacaoEstoque,
    Pagamento,
    Produto,
    Venda,
)
from .permissions import ATENDENTE_GROUP, GERENTE_GROUP
from .services import registrar_movimentacao
from .vendas import (
    assinar_previa,
    cancelar_venda,
    finalizar_venda,
    montar_previa_carrinho,
)


class LojaViewsTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Bebidas")
        self.gerente_group, _ = Group.objects.get_or_create(name=GERENTE_GROUP)
        self.atendente_group, _ = Group.objects.get_or_create(name=ATENDENTE_GROUP)
        self.user = get_user_model().objects.create_user(
            username="gerente",
            password="Senha-segura-123",
            is_staff=True,
        )
        self.user.groups.add(self.gerente_group)
        self.client.force_login(self.user)

    def criar_produto(self, nome="Refrigerante", quantidade=10, categoria=None, preco="8.50"):
        return Produto.objects.create(
            nome=nome,
            descricao="",
            preco=preco,
            quantidade=quantidade,
            categoria=categoria or self.categoria,
        )

    def criar_venda(self, produto, quantidade=1):
        carrinho = {produto.pk: quantidade}
        previa = montar_previa_carrinho(carrinho)
        return finalizar_venda(
            carrinho=carrinho,
            usuario=self.user,
            forma_pagamento=Pagamento.FormaPagamento.PIX,
            token_previa=assinar_previa(previa["snapshot"]),
        )

    def test_dashboard_shows_real_low_stock_total(self):
        for indice in range(6):
            self.criar_produto(nome=f"Produto {indice}", quantidade=indice)

        response = self.client.get(reverse("loja:inicio"))

        self.assertEqual(response.context["total_estoque_baixo"], 6)
        self.assertEqual(len(response.context["itens_baixo_estoque"]), 5)
        self.assertContains(response, ">6</div>")

    def test_dashboard_uses_individual_minimum_and_excludes_archived_products(self):
        produto_baixo = self.criar_produto(nome="Abaixo do mínimo", quantidade=2)
        produto_baixo.estoque_minimo = 3
        produto_baixo.save(update_fields=["estoque_minimo"])
        produto_normal = self.criar_produto(nome="No limite", quantidade=2)
        produto_normal.estoque_minimo = 2
        produto_normal.save(update_fields=["estoque_minimo"])
        produto_arquivado = self.criar_produto(nome="Arquivado", quantidade=0)
        produto_arquivado.ativo = False
        produto_arquivado.save(update_fields=["ativo"])

        response = self.client.get(reverse("loja:inicio"))

        self.assertEqual(response.context["total_estoque_baixo"], 2)
        self.assertContains(response, "Abaixo do mínimo")
        self.assertContains(response, "No limite")
        self.assertNotContains(response, "Arquivado")

    def test_product_list_shows_products_without_filters(self):
        self.criar_produto()

        response = self.client.get(reverse("loja:produtos"))

        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertContains(response, "Refrigerante")
        self.assertNotContains(response, "Nenhum produto cadastrado")

    def test_staff_user_without_a_store_group_is_denied(self):
        user = get_user_model().objects.create_user(
            username="sem-grupo",
            password="Senha-segura-123",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("loja:inicio"))

        self.assertEqual(response.status_code, 403)

    def test_product_list_is_paginated_and_keeps_search_term(self):
        for indice in range(21):
            self.criar_produto(nome=f"Produto {indice:02}")

        response = self.client.get(reverse("loja:produtos"), {"page": 2, "q": "Produto"})

        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(response.context["produtos"]), 1)
        self.assertContains(response, "q=Produto&amp;situacao=ativos&amp;page=1")

    def test_category_product_counts_use_single_query(self):
        self.criar_produto()

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("loja:categorias"))
            self.assertContains(response, "1 produto(s)")
        category_queries = [
            query for query in queries
            if 'FROM "loja_categoria"' in query["sql"]
        ]
        self.assertEqual(len(category_queries), 1)

    def test_product_form_rejects_non_positive_price(self):
        response = self.client.post(reverse("loja:produto_criar"), {
            "nome": "Produto inválido",
            "descricao": "",
            "preco": "0",
            "quantidade": "1",
            "categoria": self.categoria.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="Produto inválido").exists())
        self.assertContains(response, "O preço deve ser maior que zero.")

    def test_admin_rejects_non_positive_product_price(self):
        admin_user = get_user_model().objects.create_superuser(
            username="admin_teste",
            password="Senha-segura-123",
        )
        self.client.force_login(admin_user)

        for preco in ("0", "-1.00"):
            with self.subTest(preco=preco):
                response = self.client.post(reverse("admin:loja_produto_add"), {
                    "nome": "Produto inválido",
                    "descricao": "",
                    "preco": preco,
                    "quantidade": "1",
                    "categoria": self.categoria.pk,
                })

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "O preço deve ser maior que zero.")
                self.assertFalse(Produto.objects.filter(nome="Produto inválido").exists())

    def test_category_with_products_cannot_be_deleted(self):
        self.criar_produto()

        response = self.client.post(
            reverse("loja:categoria_excluir", args=[self.categoria.pk]),
            follow=True,
        )

        self.assertTrue(Categoria.objects.filter(pk=self.categoria.pk).exists())
        self.assertContains(response, "Não é possível excluir uma categoria que possui produtos.")

    def test_staff_pages_redirect_anonymous_users_to_login(self):
        self.client.logout()

        response = self.client.get(reverse("loja:inicio"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('loja:inicio')}",
        )

    def test_non_staff_users_cannot_access_the_management_panel(self):
        user = get_user_model().objects.create_user(
            username="visitante",
            password="Senha-segura-123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("loja:inicio"))

        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_log_in_and_log_out(self):
        self.client.logout()

        login_response = self.client.post(reverse("login"), {
            "username": "gerente",
            "password": "Senha-segura-123",
        })
        self.assertRedirects(login_response, reverse("loja:inicio"))

        logout_response = self.client.post(reverse("logout"))
        self.assertRedirects(logout_response, reverse("login"))

    def test_product_filters_by_category_and_order(self):
        outra_categoria = Categoria.objects.create(nome="Lanches")
        self.criar_produto(nome="Refrigerante caro", quantidade=3, preco="12.50")
        self.criar_produto(nome="Refrigerante barato", quantidade=8, preco="4.50")
        self.criar_produto(
            nome="Salgadinho",
            quantidade=2,
            categoria=outra_categoria,
        )

        response = self.client.get(reverse("loja:produtos"), {
            "categoria": self.categoria.pk,
            "ordenar": "preco",
        })

        nomes = [produto.nome for produto in response.context["produtos"]]
        self.assertEqual(nomes, ["Refrigerante barato", "Refrigerante caro"])
        self.assertNotIn("Salgadinho", nomes)

    def test_invalid_product_filter_is_reported_without_showing_unfiltered_results(self):
        self.criar_produto()

        response = self.client.get(reverse("loja:produtos"), {"ordenar": "campo-invalido"})

        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.assertContains(response, "Faça uma escolha válida")

    def test_staff_user_can_create_edit_and_archive_product(self):
        create_response = self.client.post(reverse("loja:produto_criar"), {
            "nome": "Suco",
            "descricao": "",
            "preco": "5.25",
            "custo_aquisicao": "",
            "estoque_minimo": "4",
            "codigo_barras": "",
            "categoria": self.categoria.pk,
        })
        produto = Produto.objects.get(nome="Suco")
        self.assertEqual(produto.quantidade, 0)
        self.assertEqual(produto.estoque_minimo, 4)
        self.assertRedirects(create_response, reverse("loja:produtos"))

        edit_response = self.client.post(
            reverse("loja:produto_editar", args=[produto.pk]),
            {
                "nome": "Suco natural",
                "descricao": "",
                "preco": "6.00",
                "custo_aquisicao": "",
                "estoque_minimo": "7",
                "codigo_barras": "7890001",
                "categoria": self.categoria.pk,
            },
        )
        produto.refresh_from_db()
        self.assertEqual(produto.nome, "Suco natural")
        self.assertEqual(produto.quantidade, 0)
        self.assertEqual(produto.estoque_minimo, 7)
        self.assertEqual(produto.codigo_barras, "7890001")
        self.assertRedirects(edit_response, reverse("loja:produtos"))

        registrar_movimentacao(
            produto_id=produto.pk,
            tipo=MovimentacaoEstoque.Tipo.ENTRADA,
            quantidade=5,
            responsavel=self.user,
            motivo="Estoque inicial do produto",
        )
        delete_response = self.client.post(
            reverse("loja:produto_excluir", args=[produto.pk]),
        )
        produto.refresh_from_db()
        self.assertFalse(produto.ativo)
        self.assertTrue(Produto.objects.filter(pk=produto.pk).exists())
        self.assertTrue(MovimentacaoEstoque.objects.filter(produto=produto).exists())
        self.assertEqual(produto.quantidade, 5)
        self.assertRedirects(delete_response, reverse("loja:produtos"))

    def test_attendant_can_record_entry_and_loss_with_history(self):
        atendente = get_user_model().objects.create_user(
            username="atendente",
            password="Senha-segura-123",
        )
        atendente.groups.add(self.atendente_group)
        produto = self.criar_produto(quantidade=0)
        self.client.force_login(atendente)

        entrada_response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.ENTRADA,
            "quantidade": 10,
            "motivo": "Reposição semanal",
        })

        self.assertRedirects(entrada_response, reverse("loja:estoque"))
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 10)
        entrada = MovimentacaoEstoque.objects.get(tipo=MovimentacaoEstoque.Tipo.ENTRADA)
        self.assertEqual(entrada.quantidade_anterior, 0)
        self.assertEqual(entrada.quantidade_posterior, 10)
        self.assertEqual(entrada.responsavel, atendente)

        perda_response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.PERDA,
            "quantidade": 3,
            "motivo": "Produto danificado",
        })

        self.assertRedirects(perda_response, reverse("loja:estoque"))
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 7)
        self.assertEqual(
            MovimentacaoEstoque.objects.get(tipo=MovimentacaoEstoque.Tipo.PERDA).variacao_quantidade,
            -3,
        )

    def test_attendant_cannot_use_manager_only_stock_operations(self):
        atendente = get_user_model().objects.create_user(
            username="atendente",
            password="Senha-segura-123",
        )
        atendente.groups.add(self.atendente_group)
        produto = self.criar_produto(quantidade=5)

        with self.assertRaises(PermissionDenied):
            registrar_movimentacao(
                produto_id=produto.pk,
                tipo=MovimentacaoEstoque.Tipo.AJUSTE,
                quantidade=2,
                responsavel=atendente,
                motivo="Contagem",
            )

        self.client.force_login(atendente)
        response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.SAIDA_MANUAL,
            "quantidade": 1,
            "motivo": "Retirada",
        })

        self.assertEqual(response.status_code, 200)
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 5)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_manager_can_adjust_to_zero_and_cannot_create_negative_stock(self):
        produto = self.criar_produto(quantidade=4)

        ajuste_response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.AJUSTE,
            "quantidade": 0,
            "motivo": "Contagem física",
        })

        self.assertRedirects(ajuste_response, reverse("loja:estoque"))
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 0)
        ajuste = MovimentacaoEstoque.objects.get()
        self.assertEqual(ajuste.variacao_quantidade, -4)
        self.assertEqual(ajuste.quantidade_anterior, 4)
        self.assertEqual(ajuste.quantidade_posterior, 0)

        response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.PERDA,
            "quantidade": 1,
            "motivo": "Produto vencido",
        })

        self.assertEqual(response.status_code, 200)
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 1)
        self.assertContains(response, "A saída excede o estoque disponível.")

    def test_stock_movement_requires_a_reason(self):
        produto = self.criar_produto(quantidade=0)

        response = self.client.post(reverse("loja:estoque_movimentar"), {
            "produto": produto.pk,
            "tipo": MovimentacaoEstoque.Tipo.ENTRADA,
            "quantidade": 2,
            "motivo": "   ",
        })

        self.assertEqual(response.status_code, 200)
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 0)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_pdv_requires_review_then_records_cash_sale_and_stock_movement(self):
        produto = self.criar_produto(quantidade=8, preco="8.50")
        produto.custo_aquisicao = Decimal("3.25")
        produto.codigo_barras = "7890002"
        produto.save(update_fields=["custo_aquisicao", "codigo_barras"])
        self.client.post(reverse("loja:carrinho_adicionar"), {
            "produto_id": produto.pk,
            "quantidade": 2,
        })
        carrinho_response = self.client.get(reverse("loja:pdv"))
        self.assertContains(carrinho_response, "Carrinho")
        self.assertContains(carrinho_response, "Refrigerante")

        dados_venda = {
            "forma_pagamento": Pagamento.FormaPagamento.DINHEIRO,
            "valor_recebido": "20.00",
            "desconto": "",
        }
        revisao = self.client.post(
            reverse("loja:venda_checkout"),
            {**dados_venda, "acao": "revisar"},
        )

        self.assertEqual(revisao.status_code, 200)
        self.assertTrue(revisao.context["revisao"])
        self.assertEqual(revisao.context["total"], Decimal("17.00"))
        self.assertEqual(revisao.context["troco"], Decimal("3.00"))
        self.assertFalse(Venda.objects.exists())
        token = revisao.context["token_previa"]

        resposta = self.client.post(
            reverse("loja:venda_checkout"),
            {
                **dados_venda,
                "acao": "finalizar",
                "token_previa": token,
            },
        )

        venda = Venda.objects.get()
        item = ItemVenda.objects.get(venda=venda)
        pagamento = Pagamento.objects.get(venda=venda)
        produto.refresh_from_db()
        self.assertRedirects(resposta, reverse("loja:venda_detalhe", args=[venda.pk]))
        self.assertEqual(produto.quantidade, 6)
        self.assertEqual(item.nome_produto, "Refrigerante")
        self.assertEqual(item.codigo_barras, "7890002")
        self.assertEqual(item.custo_unitario, Decimal("3.25"))
        self.assertEqual(item.preco_unitario, Decimal("8.50"))
        self.assertEqual(item.subtotal, Decimal("17.00"))
        self.assertEqual(pagamento.valor_pago, Decimal("17.00"))
        self.assertEqual(pagamento.valor_recebido, Decimal("20.00"))
        self.assertEqual(pagamento.troco, Decimal("3.00"))
        movimento = MovimentacaoEstoque.objects.get(tipo=MovimentacaoEstoque.Tipo.VENDA)
        self.assertEqual(movimento.item_venda, item)
        self.assertEqual(movimento.variacao_quantidade, -2)
        self.assertEqual(movimento.responsavel, self.user)
        self.assertEqual(self.client.session.get("pdv_carrinho"), {})
        self.assertContains(self.client.get(resposta.url), "Itens da venda")
        self.assertContains(
            self.client.get(reverse("loja:venda_comprovante", args=[venda.pk])),
            "Comprovante não fiscal",
        )
        self.assertContains(self.client.get(reverse("loja:vendas")), "Venda")

    def test_price_change_after_review_requires_a_new_confirmation(self):
        produto = self.criar_produto(quantidade=8, preco="8.50")
        self.client.post(reverse("loja:carrinho_adicionar"), {
            "produto_id": produto.pk,
            "quantidade": 2,
        })
        dados = {
            "forma_pagamento": Pagamento.FormaPagamento.PIX,
            "valor_recebido": "",
            "desconto": "",
        }
        revisao = self.client.post(
            reverse("loja:venda_checkout"),
            {**dados, "acao": "revisar"},
        )
        produto.preco = Decimal("9.00")
        produto.save(update_fields=["preco"])

        resposta = self.client.post(
            reverse("loja:venda_checkout"),
            {
                **dados,
                "acao": "finalizar",
                "token_previa": revisao.context["token_previa"],
            },
        )

        produto.refresh_from_db()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O preço, o estoque ou os dados da venda mudaram desde a revisão.")
        self.assertEqual(resposta.context["total"], Decimal("18.00"))
        self.assertFalse(Venda.objects.exists())
        self.assertEqual(produto.quantidade, 8)

    def test_cash_checkout_rejects_received_amount_below_total(self):
        produto = self.criar_produto(quantidade=3, preco="8.50")
        self.client.post(reverse("loja:carrinho_adicionar"), {
            "produto_id": produto.pk,
            "quantidade": 1,
        })

        resposta = self.client.post(
            reverse("loja:venda_checkout"),
            {
                "acao": "revisar",
                "forma_pagamento": Pagamento.FormaPagamento.DINHEIRO,
                "valor_recebido": "8.00",
                "desconto": "",
            },
        )

        produto.refresh_from_db()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O valor recebido não cobre o total da venda.")
        self.assertFalse(Venda.objects.exists())
        self.assertEqual(produto.quantidade, 3)

    def test_changing_checkout_values_after_review_requires_another_review(self):
        produto = self.criar_produto(quantidade=3, preco="10.00")
        self.client.post(reverse("loja:carrinho_adicionar"), {
            "produto_id": produto.pk,
            "quantidade": 1,
        })
        revisao = self.client.post(
            reverse("loja:venda_checkout"),
            {
                "acao": "revisar",
                "forma_pagamento": Pagamento.FormaPagamento.PIX,
                "valor_recebido": "",
                "desconto": "",
            },
        )

        resposta = self.client.post(
            reverse("loja:venda_checkout"),
            {
                "acao": "finalizar",
                "forma_pagamento": Pagamento.FormaPagamento.PIX,
                "valor_recebido": "",
                "desconto": "0.50",
                "token_previa": revisao.context["token_previa"],
            },
        )

        produto.refresh_from_db()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O preço, o estoque ou os dados da venda mudaram desde a revisão.")
        self.assertFalse(Venda.objects.exists())
        self.assertEqual(produto.quantidade, 3)

    def test_manager_discount_is_limited_and_attendants_cannot_apply_it(self):
        produto = self.criar_produto(quantidade=5, preco="10.00")
        previa = montar_previa_carrinho({produto.pk: 1})
        token = assinar_previa(previa["snapshot"])

        with self.assertRaises(ValidationError):
            finalizar_venda(
                carrinho={produto.pk: 1},
                usuario=self.user,
                forma_pagamento=Pagamento.FormaPagamento.PIX,
                desconto=Decimal("1.01"),
                token_previa=token,
            )
        self.assertFalse(Venda.objects.exists())

        atendente = get_user_model().objects.create_user(username="atendente-venda")
        atendente.groups.add(self.atendente_group)
        with self.assertRaises(PermissionDenied):
            finalizar_venda(
                carrinho={produto.pk: 1},
                usuario=atendente,
                forma_pagamento=Pagamento.FormaPagamento.PIX,
                desconto=Decimal("0.50"),
                token_previa=token,
            )
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 5)
        self.assertFalse(Venda.objects.exists())

    def test_manager_discount_is_recorded_with_authorizer(self):
        produto = self.criar_produto(quantidade=5, preco="10.00")
        previa = montar_previa_carrinho({produto.pk: 2})

        venda = finalizar_venda(
            carrinho={produto.pk: 2},
            usuario=self.user,
            forma_pagamento=Pagamento.FormaPagamento.PIX,
            desconto=Decimal("2.00"),
            token_previa=assinar_previa(previa["snapshot"]),
        )

        self.assertEqual(venda.subtotal, Decimal("20.00"))
        self.assertEqual(venda.desconto, Decimal("2.00"))
        self.assertEqual(venda.total, Decimal("18.00"))
        self.assertEqual(venda.gerente_autorizador, self.user)
        self.assertEqual(venda.gerente_autorizador_nome, self.user.username)

    def test_sale_finalization_is_atomic_when_stock_changes(self):
        primeiro = self.criar_produto(nome="Primeiro", quantidade=5)
        segundo = self.criar_produto(nome="Segundo", quantidade=5)
        carrinho = {primeiro.pk: 2, segundo.pk: 2}
        previa = montar_previa_carrinho(carrinho)
        segundo.quantidade = 1
        segundo.save(update_fields=["quantidade"])

        with self.assertRaises(ValidationError):
            finalizar_venda(
                carrinho=carrinho,
                usuario=self.user,
                forma_pagamento=Pagamento.FormaPagamento.PIX,
                token_previa=assinar_previa(previa["snapshot"]),
            )

        primeiro.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual(primeiro.quantidade, 5)
        self.assertEqual(segundo.quantidade, 1)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(MovimentacaoEstoque.objects.filter(tipo=MovimentacaoEstoque.Tipo.VENDA).exists())

    def test_cancelling_sale_restores_stock_and_cannot_repeat(self):
        produto = self.criar_produto(quantidade=8)
        previa = montar_previa_carrinho({produto.pk: 3})
        venda = finalizar_venda(
            carrinho={produto.pk: 3},
            usuario=self.user,
            forma_pagamento=Pagamento.FormaPagamento.PIX,
            token_previa=assinar_previa(previa["snapshot"]),
        )
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 5)

        cancelada = cancelar_venda(
            venda_id=venda.pk,
            usuario=self.user,
            motivo="Venda lançada em duplicidade",
        )

        produto.refresh_from_db()
        venda.refresh_from_db()
        self.assertEqual(produto.quantidade, 8)
        self.assertEqual(cancelada.status, Venda.Status.CANCELADA)
        self.assertEqual(venda.usuario_cancelamento, self.user)
        self.assertEqual(venda.motivo_cancelamento, "Venda lançada em duplicidade")
        estorno = MovimentacaoEstoque.objects.get(tipo=MovimentacaoEstoque.Tipo.ESTORNO_VENDA)
        movimento_venda = MovimentacaoEstoque.objects.get(tipo=MovimentacaoEstoque.Tipo.VENDA)
        self.assertEqual(estorno.movimento_estornado, movimento_venda)
        self.assertEqual(estorno.variacao_quantidade, 3)
        self.assertEqual(estorno.motivo, "Venda lançada em duplicidade")

        with self.assertRaises(ValidationError):
            cancelar_venda(
                venda_id=venda.pk,
                usuario=self.user,
                motivo="Tentativa duplicada",
            )
        self.assertEqual(MovimentacaoEstoque.objects.count(), 2)

    def test_cancel_view_requires_reason_and_records_the_operator(self):
        produto = self.criar_produto(quantidade=4)
        previa = montar_previa_carrinho({produto.pk: 1})
        venda = finalizar_venda(
            carrinho={produto.pk: 1},
            usuario=self.user,
            forma_pagamento=Pagamento.FormaPagamento.CARTAO,
            token_previa=assinar_previa(previa["snapshot"]),
        )
        url_cancelar = reverse("loja:venda_cancelar", args=[venda.pk])
        self.assertContains(self.client.get(url_cancelar), "cancelamento integral")

        resposta_invalida = self.client.post(url_cancelar, {"motivo": "   "})
        venda.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(resposta_invalida.status_code, 200)
        self.assertEqual(venda.status, Venda.Status.FINALIZADA)
        self.assertEqual(produto.quantidade, 3)

        resposta = self.client.post(url_cancelar, {"motivo": "Compra duplicada"})

        self.assertRedirects(resposta, reverse("loja:venda_detalhe", args=[venda.pk]))
        venda.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.CANCELADA)
        self.assertEqual(venda.usuario_cancelamento, self.user)
        self.assertEqual(produto.quantidade, 4)
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo=MovimentacaoEstoque.Tipo.ESTORNO_VENDA).count(), 1)

    def test_staff_user_can_create_edit_and_delete_category(self):
        create_response = self.client.post(reverse("loja:categoria_criar"), {
            "nome": "Padaria",
            "descricao": "",
        })
        categoria = Categoria.objects.get(nome="Padaria")
        self.assertRedirects(create_response, reverse("loja:categorias"))

        edit_response = self.client.post(
            reverse("loja:categoria_editar", args=[categoria.pk]),
            {"nome": "Panificação", "descricao": "Pães e massas"},
        )
        categoria.refresh_from_db()
        self.assertEqual(categoria.nome, "Panificação")
        self.assertRedirects(edit_response, reverse("loja:categorias"))

        delete_response = self.client.post(
            reverse("loja:categoria_excluir", args=[categoria.pk]),
        )
        self.assertFalse(Categoria.objects.filter(pk=categoria.pk).exists())
        self.assertRedirects(delete_response, reverse("loja:categorias"))

    def test_reports_ignore_cancelled_sales_and_include_active_zero_sales_products(self):
        vendido = self.criar_produto(nome="Produto vendido")
        sem_vendas = self.criar_produto(nome="Sem vendas", quantidade=2)
        sem_vendas.estoque_minimo = 3
        sem_vendas.save(update_fields=["estoque_minimo"])
        cancelado = self.criar_produto(nome="Produto de venda cancelada")
        arquivado = self.criar_produto(nome="Produto arquivado sem histórico")
        vendido_arquivado = self.criar_produto(nome="Produto vendido arquivado")

        self.criar_venda(vendido, quantidade=2)
        venda_cancelada = self.criar_venda(cancelado)
        cancelar_venda(
            venda_id=venda_cancelada.pk,
            usuario=self.user,
            motivo="Venda de teste cancelada",
        )
        self.criar_venda(vendido_arquivado)
        vendido_arquivado.ativo = False
        vendido_arquivado.save(update_fields=["ativo"])
        arquivado.ativo = False
        arquivado.save(update_fields=["ativo"])
        hoje = timezone.localdate()

        response = self.client.get(reverse("loja:relatorios"), {
            "data_inicio": hoje.isoformat(),
            "data_fim": hoje.isoformat(),
            "agrupamento": "dia",
        })

        relatorio = response.context["relatorio"]
        self.assertEqual(relatorio["metricas"]["quantidade"], 2)
        self.assertEqual(relatorio["metricas"]["faturamento"], Decimal("25.50"))
        self.assertEqual(relatorio["vendas_canceladas"], 1)
        produtos_mais_vendidos = {
            produto.nome: produto.quantidade_vendida
            for produto in relatorio["mais_vendidos"]
        }
        self.assertEqual(produtos_mais_vendidos["Produto vendido"], 2)
        self.assertEqual(produtos_mais_vendidos["Produto vendido arquivado"], 1)
        menos_vendidos = {
            produto.nome: produto.quantidade_vendida
            for produto in relatorio["menos_vendidos"]
        }
        self.assertEqual(menos_vendidos["Sem vendas"], 0)
        self.assertEqual(menos_vendidos["Produto de venda cancelada"], 0)
        self.assertEqual(menos_vendidos["Produto vendido arquivado"], 1)
        self.assertNotIn("Produto arquivado sem histórico", menos_vendidos)
        self.assertEqual(
            [produto.nome for produto in relatorio["estoque_baixo"]],
            ["Sem vendas"],
        )

    def test_reports_compare_equal_length_previous_period(self):
        produto = self.criar_produto()
        venda_anterior = self.criar_venda(produto)
        ontem = timezone.localdate() - timedelta(days=1)
        data_anterior = timezone.localtime(timezone.now()).replace(
            year=ontem.year,
            month=ontem.month,
            day=ontem.day,
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )
        Venda.objects.filter(pk=venda_anterior.pk).update(data_venda=data_anterior)
        self.criar_venda(produto, quantidade=2)
        hoje = timezone.localdate()

        response = self.client.get(reverse("loja:relatorios"), {
            "data_inicio": hoje.isoformat(),
            "data_fim": hoje.isoformat(),
            "agrupamento": "dia",
        })

        comparacao = response.context["relatorio"]["comparacao"]
        self.assertEqual(comparacao["vendas_anterior"], 1)
        self.assertEqual(comparacao["faturamento_anterior"], Decimal("8.50"))
        self.assertEqual(comparacao["variacao_faturamento"], Decimal("100.0"))
        self.assertEqual(response.context["relatorio"]["serie"][0]["quantidade"], 1)

    def test_reports_reject_reversed_date_range(self):
        hoje = timezone.localdate()
        response = self.client.get(reverse("loja:relatorios"), {
            "data_inicio": hoje.isoformat(),
            "data_fim": (hoje - timedelta(days=1)).isoformat(),
            "agrupamento": "dia",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["relatorio"])
        self.assertContains(response, "A data final deve ser igual ou posterior à inicial.")

    def test_reports_default_to_current_month_through_today(self):
        response = self.client.get(reverse("loja:relatorios"))
        hoje = timezone.localdate()
        relatorio = response.context["relatorio"]

        self.assertEqual(relatorio["data_inicio"], hoje.replace(day=1))
        self.assertEqual(relatorio["data_fim"], hoje)
        self.assertEqual(relatorio["agrupamento"], "dia")

    def test_report_period_limit_includes_both_dates_and_rejects_longer_ranges(self):
        hoje = timezone.localdate()
        dados = {
            "data_inicio": (hoje - timedelta(days=364)).isoformat(),
            "data_fim": hoje.isoformat(),
            "agrupamento": "dia",
        }
        response = self.client.get(reverse("loja:relatorios"), dados)
        self.assertEqual(len(response.context["relatorio"]["serie"]), 365)

        dados["data_inicio"] = (hoje - timedelta(days=365)).isoformat()
        response = self.client.get(reverse("loja:relatorios"), dados)
        self.assertIsNone(response.context["relatorio"])
        self.assertContains(response, "O período não pode ultrapassar 365 dias.")
        self.assertEqual(self.client.get(reverse("loja:relatorios_pdf"), dados).status_code, 400)

    def test_report_year_is_in_daily_and_weekly_labels(self):
        dados = {
            "data_inicio": "2025-12-31",
            "data_fim": "2026-01-02",
            "agrupamento": "dia",
        }
        response = self.client.get(reverse("loja:relatorios"), dados)
        self.assertEqual(
            [ponto["rotulo"] for ponto in response.context["relatorio"]["serie"]],
            ["31/12/2025", "01/01/2026", "02/01/2026"],
        )
        dados["agrupamento"] = "semana"
        response = self.client.get(reverse("loja:relatorios"), dados)
        self.assertEqual(response.context["relatorio"]["serie"][0]["rotulo"], "Semana de 29/12/2025")

    def test_reports_reject_dates_without_a_representable_previous_period(self):
        response = self.client.get(reverse("loja:relatorios"), {
            "data_inicio": date.min.isoformat(),
            "data_fim": date.min.isoformat(),
            "agrupamento": "dia",
        })
        self.assertContains(response, "Não é possível comparar esse período com o anterior.")

    def test_report_shows_recent_movements_and_pdf_includes_all(self):
        produto = self.criar_produto(nome="Produto & especial", quantidade=0)
        MovimentacaoEstoque.objects.bulk_create([
            MovimentacaoEstoque(
                produto=produto,
                tipo=MovimentacaoEstoque.Tipo.ENTRADA,
                variacao_quantidade=1,
                quantidade_anterior=0,
                quantidade_posterior=1,
                responsavel=self.user,
                responsavel_nome=self.user.username,
                motivo=f"marcador-{indice:02}",
            )
            for indice in range(31)
        ])
        hoje = timezone.localdate()
        dados = {
            "data_inicio": hoje.isoformat(),
            "data_fim": hoje.isoformat(),
            "agrupamento": "dia",
        }
        response = self.client.get(reverse("loja:relatorios"), dados)
        self.assertContains(response, "marcador-30")
        self.assertNotContains(response, "marcador-00")
        self.assertEqual(len(response.context["movimentacoes_recentes"]), 30)

        with patch("reportlab.rl_config.pageCompression", 0):
            response = self.client.get(reverse("loja:relatorios_pdf"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", response.content)
        self.assertIn(b"marcador-00", response.content)
        self.assertIn(b"marcador-30", response.content)
        self.assertGreater(response.content.count(b"/Type /Page\n"), 1)

    def test_pdf_export_respects_access_control_and_includes_sales_values(self):
        produto = self.criar_produto(nome="Cafe & cha")
        self.criar_venda(produto, quantidade=2)
        hoje = timezone.localdate()
        dados = {
            "data_inicio": hoje.isoformat(),
            "data_fim": hoje.isoformat(),
            "agrupamento": "dia",
        }
        with patch("reportlab.rl_config.pageCompression", 0):
            response = self.client.get(reverse("loja:relatorios_pdf"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"R$ 17,00", response.content)
        self.assertIn(b"Cafe & cha", response.content)

        self.client.logout()
        response = self.client.get(reverse("loja:relatorios_pdf"), dados)
        self.assertEqual(response.status_code, 302)
        usuario = get_user_model().objects.create_user(username="sem-acesso")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("loja:relatorios_pdf"), dados).status_code, 403)
