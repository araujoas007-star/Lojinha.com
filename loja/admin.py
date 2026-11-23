from django.contrib import admin

from .forms import ProdutoForm
from .models import (
    Categoria,
    ItemVenda,
    MovimentacaoEstoque,
    Pagamento,
    Produto,
    Venda,
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "descricao")
    search_fields = ("nome",)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    form = ProdutoForm
    list_display = ("nome", "categoria", "preco", "quantidade", "estoque_minimo", "ativo")
    list_filter = ("categoria", "ativo")
    search_fields = ("nome", "codigo_barras")
    readonly_fields = ("quantidade", "ativo")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "data_movimentacao",
        "produto",
        "tipo",
        "variacao_quantidade",
        "quantidade_anterior",
        "quantidade_posterior",
        "responsavel_nome",
    )
    list_filter = ("tipo", "data_movimentacao")
    search_fields = ("produto__nome", "responsavel_nome", "motivo")
    readonly_fields = tuple(field.name for field in MovimentacaoEstoque._meta.fields)
    ordering = ("-data_movimentacao", "-pk")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ("id", "data_venda", "status", "usuario_nome", "subtotal", "desconto", "total")
    list_filter = ("status", "data_venda")
    search_fields = ("id", "usuario_nome", "usuario_cancelamento_nome")
    readonly_fields = tuple(field.name for field in Venda._meta.fields)
    ordering = ("-data_venda", "-pk")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemVenda)
class ItemVendaAdmin(admin.ModelAdmin):
    list_display = ("venda", "nome_produto", "codigo_barras", "preco_unitario", "quantidade", "subtotal")
    search_fields = ("venda__id", "nome_produto", "codigo_barras")
    readonly_fields = tuple(field.name for field in ItemVenda._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ("venda", "forma_pagamento", "valor_pago", "valor_recebido", "troco", "data_pagamento")
    list_filter = ("forma_pagamento", "data_pagamento")
    readonly_fields = tuple(field.name for field in Pagamento._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
