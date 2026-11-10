from django import forms

from .models import Categoria


class ProdutoFiltroForm(forms.Form):
    ordem_choices = (
        ("nome", "Nome (A-Z)"),
        ("-nome", "Nome (Z-A)"),
        ("preco", "Menor preço"),
        ("-preco", "Maior preço"),
        ("quantidade", "Menor estoque"),
        ("-quantidade", "Maior estoque"),
    )

    q = forms.CharField(
        required=False,
        label="Buscar produto",
        widget=forms.SearchInput(attrs={"placeholder": "Buscar produto..."}),
    )
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas as categorias",
        label="Categoria",
    )
    ordenar = forms.ChoiceField(
        choices=(("", "Ordenar por"),) + ordem_choices,
        required=False,
        label="Ordenação",
    )
