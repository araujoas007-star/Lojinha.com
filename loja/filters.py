from django import forms

from .models import Categoria
from .permissions import is_manager


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
    situacao = forms.ChoiceField(
        choices=(
            ("ativos", "Produtos ativos"),
            ("arquivados", "Produtos arquivados"),
            ("todos", "Todos os produtos"),
        ),
        required=False,
        label="Situação",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if is_manager(user):
            if self.is_bound and not self.data.get("situacao"):
                self.data = self.data.copy()
                self.data["situacao"] = "ativos"
            self.initial.setdefault("situacao", "ativos")
        else:
            self.fields.pop("situacao")
