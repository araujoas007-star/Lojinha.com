from decimal import Decimal

from django import forms

from .models import (
    PERCENTUAL_DESCONTO_MAXIMO,
    Categoria,
    MovimentacaoEstoque,
    Pagamento,
    Produto,
    Venda,
)
from .permissions import is_manager


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "descricao"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Bebidas"}),
            "descricao": forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva a categoria (opcional)"}),
        }


class ProdutoForm(forms.ModelForm):
    def clean_preco(self):
        preco = self.cleaned_data["preco"]

        if preco <= 0:
            raise forms.ValidationError("O preço deve ser maior que zero.")

        return preco

    class Meta:
        model = Produto
        fields = [
            "nome",
            "descricao",
            "preco",
            "custo_aquisicao",
            "estoque_minimo",
            "codigo_barras",
            "categoria",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Refrigerante 2 L"}),
            "descricao": forms.Textarea(attrs={"rows": 3, "placeholder": "Detalhes do produto (opcional)"}),
            "preco": forms.NumberInput(attrs={"min": "0.01", "step": "0.01", "placeholder": "0,00"}),
            "custo_aquisicao": forms.NumberInput(attrs={"min": "0", "step": "0.01", "placeholder": "Opcional"}),
            "estoque_minimo": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "codigo_barras": forms.TextInput(attrs={"placeholder": "Opcional"}),
        }
        help_texts = {
            "custo_aquisicao": "Deixe em branco até o custo ser conferido.",
            "estoque_minimo": "O alerta de estoque baixo usa este limite.",
            "codigo_barras": "O código deve ser único quando informado.",
            "categoria": "Cadastre uma categoria antes de cadastrar o produto.",
        }


class MovimentacaoEstoqueForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.all(),
        label="Produto",
    )
    tipo = forms.ChoiceField(label="Operação")
    quantidade = forms.IntegerField(
        min_value=0,
        label="Quantidade",
        help_text="Em ajuste, informe o saldo contado. Nas demais operações, informe as unidades.",
    )
    motivo = forms.CharField(
        label="Motivo",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva o motivo da movimentação"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        tipos = [
            MovimentacaoEstoque.Tipo.ENTRADA,
            MovimentacaoEstoque.Tipo.PERDA,
        ]
        if is_manager(user):
            tipos.extend([
                MovimentacaoEstoque.Tipo.SAIDA_MANUAL,
                MovimentacaoEstoque.Tipo.AJUSTE,
            ])
        self.fields["tipo"].choices = [
            (tipo.value, tipo.label)
            for tipo in MovimentacaoEstoque.Tipo
            if tipo in tipos
        ]

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo")
        quantidade = cleaned_data.get("quantidade")
        if (
            tipo != MovimentacaoEstoque.Tipo.AJUSTE
            and quantidade is not None
            and quantidade == 0
        ):
            self.add_error("quantidade", "Informe uma quantidade maior que zero.")
        return cleaned_data


class BuscaProdutoPDVForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Buscar produto",
        widget=forms.SearchInput(attrs={"placeholder": "Nome ou código de barras"}),
    )


class ItemCarrinhoForm(forms.Form):
    produto_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    quantidade = forms.IntegerField(min_value=1, initial=1, label="Quantidade")


class AtualizarItemCarrinhoForm(forms.Form):
    produto_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    quantidade = forms.IntegerField(min_value=0, label="Quantidade")


class RemoverItemCarrinhoForm(forms.Form):
    produto_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class FinalizarVendaForm(forms.Form):
    forma_pagamento = forms.ChoiceField(
        choices=(("", "Selecione a forma de pagamento"),) + tuple(Pagamento.FormaPagamento.choices),
        label="Forma de pagamento",
    )
    valor_recebido = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        label="Valor recebido em dinheiro",
    )

    def __init__(self, *args, user, subtotal, **kwargs):
        self.user = user
        self.subtotal = subtotal
        super().__init__(*args, **kwargs)
        if is_manager(user):
            self.fields["desconto"] = forms.DecimalField(
                required=False,
                min_value=Decimal("0.00"),
                max_digits=12,
                decimal_places=2,
                label="Desconto (R$)",
                help_text="Exclusivo do Gerente; limite de 10% do subtotal.",
            )

    def clean(self):
        cleaned_data = super().clean()
        desconto = cleaned_data.get("desconto") or Decimal("0.00")
        forma_pagamento = cleaned_data.get("forma_pagamento")
        valor_recebido = cleaned_data.get("valor_recebido")
        total = self.subtotal - desconto

        if desconto > self.subtotal * PERCENTUAL_DESCONTO_MAXIMO:
            self.add_error("desconto", "O desconto máximo é 10% do subtotal.")
        if total <= 0:
            self.add_error("desconto", "O total da venda deve ser maior que zero.")

        if forma_pagamento == Pagamento.FormaPagamento.DINHEIRO:
            if valor_recebido is None:
                self.add_error("valor_recebido", "Informe quanto o cliente entregou.")
            elif valor_recebido < total:
                self.add_error("valor_recebido", "O valor recebido não cobre o total da venda.")
        elif forma_pagamento:
            cleaned_data["valor_recebido"] = None
        return cleaned_data


class CancelarVendaForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo do cancelamento",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Informe por que a venda será cancelada"}),
    )


class VendaFiltroForm(forms.Form):
    data_inicio = forms.DateField(
        required=False,
        label="De",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    data_fim = forms.DateField(
        required=False,
        label="Até",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "Todos os status"),) + tuple(Venda.Status.choices),
        label="Status",
    )

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get("data_inicio")
        fim = cleaned_data.get("data_fim")
        if inicio and fim and inicio > fim:
            self.add_error("data_fim", "A data final deve ser igual ou posterior à inicial.")
        return cleaned_data


class RelatorioFiltroForm(forms.Form):
    AGRUPAMENTOS = (
        ("dia", "Diário"),
        ("semana", "Semanal"),
        ("mes", "Mensal"),
    )

    data_inicio = forms.DateField(
        label="De",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    data_fim = forms.DateField(
        label="Até",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    agrupamento = forms.ChoiceField(
        choices=AGRUPAMENTOS,
        label="Agrupar faturamento",
    )

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get("data_inicio")
        fim = cleaned_data.get("data_fim")
        if inicio and fim:
            if inicio > fim:
                self.add_error("data_fim", "A data final deve ser igual ou posterior à inicial.")
            elif (fim - inicio).days + 1 > 365:
                self.add_error("data_fim", "O período não pode ultrapassar 365 dias.")
            elif inicio.toordinal() <= (fim - inicio).days + 1:
                self.add_error("data_inicio", "Não é possível comparar esse período com o anterior.")
        return cleaned_data
