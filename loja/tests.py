from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Categoria, Produto


class LojaViewsTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Bebidas")
        self.user = get_user_model().objects.create_user(
            username="gerente",
            password="Senha-segura-123",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def criar_produto(self, nome="Refrigerante", quantidade=10, categoria=None, preco="8.50"):
        return Produto.objects.create(
            nome=nome,
            descricao="",
            preco=preco,
            quantidade=quantidade,
            categoria=categoria or self.categoria,
        )

    def test_dashboard_shows_real_low_stock_total(self):
        for indice in range(6):
            self.criar_produto(nome=f"Produto {indice}", quantidade=indice)

        response = self.client.get(reverse("loja:inicio"))

        self.assertEqual(response.context["total_estoque_baixo"], 6)
        self.assertEqual(len(response.context["itens_baixo_estoque"]), 5)
        self.assertContains(response, ">6</div>")

    def test_product_list_is_paginated_and_keeps_search_term(self):
        for indice in range(21):
            self.criar_produto(nome=f"Produto {indice:02}")

        response = self.client.get(reverse("loja:produtos"), {"page": 2, "q": "Produto"})

        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(response.context["produtos"]), 1)
        self.assertContains(response, "q=Produto&amp;page=1")

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

    def test_staff_user_can_create_edit_and_delete_product(self):
        create_response = self.client.post(reverse("loja:produto_criar"), {
            "nome": "Suco",
            "descricao": "",
            "preco": "5.25",
            "quantidade": "12",
            "categoria": self.categoria.pk,
        })
        produto = Produto.objects.get(nome="Suco")
        self.assertRedirects(create_response, reverse("loja:produtos"))

        edit_response = self.client.post(
            reverse("loja:produto_editar", args=[produto.pk]),
            {
                "nome": "Suco natural",
                "descricao": "",
                "preco": "6.00",
                "quantidade": "10",
                "categoria": self.categoria.pk,
            },
        )
        produto.refresh_from_db()
        self.assertEqual(produto.nome, "Suco natural")
        self.assertRedirects(edit_response, reverse("loja:produtos"))

        delete_response = self.client.post(
            reverse("loja:produto_excluir", args=[produto.pk]),
        )
        self.assertFalse(Produto.objects.filter(pk=produto.pk).exists())
        self.assertRedirects(delete_response, reverse("loja:produtos"))

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
