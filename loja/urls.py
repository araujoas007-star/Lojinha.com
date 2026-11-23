from django.urls import path
from . import views

app_name = "loja"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("produtos/", views.produtos, name="produtos"),
    path("produtos/novo/", views.produto_criar, name="produto_criar"),
    path("produtos/<int:pk>/editar/", views.produto_editar, name="produto_editar"),
    path("produtos/<int:pk>/excluir/", views.produto_excluir, name="produto_excluir"),
    path("produtos/<int:pk>/reativar/", views.produto_reativar, name="produto_reativar"),
    path("estoque/", views.estoque, name="estoque"),
    path("estoque/movimentar/", views.estoque_movimentar, name="estoque_movimentar"),
    path("pdv/", views.pdv, name="pdv"),
    path("pdv/carrinho/adicionar/", views.carrinho_adicionar, name="carrinho_adicionar"),
    path("pdv/carrinho/atualizar/", views.carrinho_atualizar, name="carrinho_atualizar"),
    path("pdv/carrinho/remover/", views.carrinho_remover, name="carrinho_remover"),
    path("pdv/carrinho/limpar/", views.carrinho_limpar, name="carrinho_limpar"),
    path("pdv/confirmar/", views.venda_checkout, name="venda_checkout"),
    path("vendas/", views.vendas, name="vendas"),
    path("vendas/<int:pk>/", views.venda_detalhe, name="venda_detalhe"),
    path("vendas/<int:pk>/comprovante/", views.venda_comprovante, name="venda_comprovante"),
    path("vendas/<int:pk>/cancelar/", views.venda_cancelar, name="venda_cancelar"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("relatorios/pdf/", views.relatorios_pdf, name="relatorios_pdf"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nova/", views.categoria_criar, name="categoria_criar"),
    path("categorias/<int:pk>/editar/", views.categoria_editar, name="categoria_editar"),
    path("categorias/<int:pk>/excluir/", views.categoria_excluir, name="categoria_excluir"),
]
