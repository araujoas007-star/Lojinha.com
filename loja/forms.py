from django import forms
from .models import Categoria, Produto


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "descricao"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Bebidas"}),
            "descricao": forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva a categoria (opcional)"}),
        }


class ProdutoForm(forms.ModelForm):
    def clean_quantidade(self):
        quantidade = self.cleaned_data["quantidade"]

        if quantidade < 0:
            raise forms.ValidationError(
                "A quantidade não pode ser negativa."
            )

        return quantidade

    def clean_preco(self):
        preco = self.cleaned_data["preco"]

        if preco <= 0:
            raise forms.ValidationError("O preço deve ser maior que zero.")

        return preco

    class Meta:
        model = Produto
        fields = ["nome", "descricao", "preco", "quantidade", "categoria"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Refrigerante 2 L"}),
            "descricao": forms.Textarea(attrs={"rows": 3, "placeholder": "Detalhes do produto (opcional)"}),
            "preco": forms.NumberInput(attrs={"min": "0.01", "step": "0.01", "placeholder": "0,00"}),
            "quantidade": forms.NumberInput(attrs={"min": "0", "step": "1", "placeholder": "0"}),
        }
        help_texts = {
            "quantidade": "Use 0 se o produto estiver sem estoque.",
            "categoria": "Cadastre uma categoria antes de cadastrar o produto.",
        }
