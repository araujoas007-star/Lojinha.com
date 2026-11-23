from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.urls import reverse


VALOR_ZERO = "0.00"
PERCENTUAL_DESCONTO_MAXIMO = Decimal("0.10")


class Categoria(models.Model):
    nome = models.CharField("nome", max_length=80, unique=True)
    descricao = models.TextField("descrição", blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse("loja:categorias")


class Produto(models.Model):
    nome = models.CharField("nome", max_length=120)
    descricao = models.TextField("descrição", blank=True)
    preco = models.DecimalField("preço", max_digits=10, decimal_places=2)
    custo_aquisicao = models.DecimalField(
        "custo de aquisição",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
    )
    quantidade = models.PositiveIntegerField("quantidade em estoque", default=0)
    estoque_minimo = models.PositiveIntegerField("estoque mínimo", default=5)
    codigo_barras = models.CharField(
        "código de barras",
        max_length=64,
        unique=True,
        blank=True,
        null=True,
    )
    ativo = models.BooleanField("ativo no catálogo", default=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="produtos",
        verbose_name="categoria",
    )
    criado_em = models.DateTimeField("cadastrado em", auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "produto"
        verbose_name_plural = "produtos"

    def __str__(self):
        return self.nome

    @property
    def estoque_baixo(self):
        return self.quantidade <= self.estoque_minimo

    @property
    def valor_em_estoque(self):
        return self.preco * self.quantidade


class MovimentacaoEstoque(models.Model):
    class Tipo(models.TextChoices):
        SALDO_INICIAL = "saldo_inicial", "Saldo inicial"
        ENTRADA = "entrada", "Entrada"
        VENDA = "venda", "Venda"
        SAIDA_MANUAL = "saida_manual", "Saída manual"
        PERDA = "perda", "Perda"
        AJUSTE = "ajuste", "Ajuste"
        ESTORNO_VENDA = "estorno_venda", "Estorno de venda"

    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        verbose_name="produto",
    )
    item_venda = models.ForeignKey(
        "ItemVenda",
        on_delete=models.PROTECT,
        related_name="movimentacoes_estoque",
        verbose_name="item da venda",
        null=True,
        blank=True,
    )
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices)
    variacao_quantidade = models.IntegerField("variação de quantidade")
    quantidade_anterior = models.PositiveIntegerField("quantidade anterior")
    quantidade_posterior = models.PositiveIntegerField("quantidade posterior")
    data_movimentacao = models.DateTimeField("data da movimentação", auto_now_add=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="movimentacoes_estoque",
        verbose_name="responsável",
        null=True,
        blank=True,
    )
    responsavel_nome = models.CharField("nome do responsável", max_length=150)
    motivo = models.TextField("motivo", blank=True)
    movimento_estornado = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="estorno",
        verbose_name="movimentação estornada",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-data_movimentacao", "-pk"]
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    quantidade_posterior=F("quantidade_anterior") + F("variacao_quantidade")
                ),
                name="loja_movimentacao_saldo_coerente",
            ),
            models.CheckConstraint(
                condition=~Q(variacao_quantidade=0),
                name="loja_movimentacao_variacao_nao_zero",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(tipo__in=[
                        "saldo_inicial",
                        "entrada",
                        "saida_manual",
                        "perda",
                        "ajuste",
                        "estorno_venda",
                    ])
                    | ~Q(motivo="")
                ),
                name="loja_movimentacao_motivo_obrigatorio",
            ),
        ]
        indexes = [
            models.Index(
                fields=["produto", "-data_movimentacao"],
                name="loja_mov_prod_data_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.variacao_quantidade == 0:
            errors["variacao_quantidade"] = "A movimentação precisa alterar o saldo."
        if (
            self.quantidade_anterior is not None
            and self.variacao_quantidade is not None
            and self.quantidade_posterior is not None
            and self.quantidade_anterior + self.variacao_quantidade != self.quantidade_posterior
        ):
            errors["quantidade_posterior"] = "O saldo posterior deve corresponder à variação."
        if self.quantidade_posterior is not None and self.quantidade_posterior < 0:
            errors["quantidade_posterior"] = "O estoque não pode ficar negativo."
        if self.tipo != self.Tipo.SALDO_INICIAL and not self.responsavel_id:
            errors["responsavel"] = "Informe o usuário responsável pela movimentação."
        if self.tipo in {
            self.Tipo.SALDO_INICIAL,
            self.Tipo.ENTRADA,
            self.Tipo.SAIDA_MANUAL,
            self.Tipo.PERDA,
            self.Tipo.AJUSTE,
            self.Tipo.ESTORNO_VENDA,
        } and not (self.motivo or "").strip():
            errors["motivo"] = "Informe o motivo da movimentação."
        if self.tipo in {self.Tipo.VENDA, self.Tipo.ESTORNO_VENDA} and not self.item_venda_id:
            errors["item_venda"] = "Associe a movimentação ao item da venda."
        if self.tipo == self.Tipo.ESTORNO_VENDA and not self.movimento_estornado_id:
            errors["movimento_estornado"] = "Associe o estorno à movimentação original."
        if self.tipo != self.Tipo.ESTORNO_VENDA and self.movimento_estornado_id:
            errors["movimento_estornado"] = "A referência de estorno só pode ser usada em estornos."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.produto}"


class Venda(models.Model):
    class Status(models.TextChoices):
        FINALIZADA = "finalizada", "Finalizada"
        CANCELADA = "cancelada", "Cancelada"

    data_venda = models.DateTimeField("data da venda", auto_now_add=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="vendas_realizadas",
        verbose_name="responsável pela venda",
        null=True,
        blank=True,
    )
    usuario_nome = models.CharField("nome do responsável", max_length=150)
    status = models.CharField(
        "status",
        max_length=12,
        choices=Status.choices,
        default=Status.FINALIZADA,
    )
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2)
    desconto = models.DecimalField(
        "desconto",
        max_digits=12,
        decimal_places=2,
        default=VALOR_ZERO,
    )
    total = models.DecimalField("total", max_digits=12, decimal_places=2)
    gerente_autorizador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="descontos_autorizados",
        verbose_name="gerente autorizador",
        null=True,
        blank=True,
    )
    gerente_autorizador_nome = models.CharField(
        "nome do gerente autorizador",
        max_length=150,
        blank=True,
    )
    data_cancelamento = models.DateTimeField("data do cancelamento", null=True, blank=True)
    usuario_cancelamento = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="vendas_canceladas",
        verbose_name="responsável pelo cancelamento",
        null=True,
        blank=True,
    )
    usuario_cancelamento_nome = models.CharField(
        "nome do responsável pelo cancelamento",
        max_length=150,
        blank=True,
    )
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ["-data_venda", "-pk"]
        verbose_name = "venda"
        verbose_name_plural = "vendas"
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal__gte=0) & Q(desconto__gte=0) & Q(total__gte=0),
                name="loja_venda_valores_nao_negativos",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("desconto")),
                name="loja_venda_total_coerente",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="finalizada", data_cancelamento__isnull=True)
                    | Q(status="cancelada", data_cancelamento__isnull=False)
                ),
                name="loja_venda_cancelamento_coerente",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.subtotal is not None and self.desconto is not None:
            limite = self.subtotal * PERCENTUAL_DESCONTO_MAXIMO
            if self.desconto < 0 or self.desconto > limite:
                errors["desconto"] = "O desconto não pode ultrapassar 10% do subtotal."
            if self.total is not None and self.subtotal - self.desconto != self.total:
                errors["total"] = "O total deve corresponder ao subtotal menos o desconto."
            if self.desconto > 0 and not (self.gerente_autorizador_nome or "").strip():
                errors["gerente_autorizador_nome"] = "Identifique o gerente que aplicou o desconto."
            if (
                self.desconto > 0
                and self.usuario_id
                and self.gerente_autorizador_id
                and self.usuario_id != self.gerente_autorizador_id
            ):
                errors["gerente_autorizador"] = "O gerente autorizador deve ser quem realizou a venda."
        if self.status == self.Status.CANCELADA:
            if not (self.motivo_cancelamento or "").strip():
                errors["motivo_cancelamento"] = "Informe o motivo do cancelamento."
            if not (self.usuario_cancelamento_nome or "").strip():
                errors["usuario_cancelamento_nome"] = "Informe quem realizou o cancelamento."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Venda #{self.pk} — {self.get_status_display()}"


class ItemVenda(models.Model):
    venda = models.ForeignKey(
        Venda,
        on_delete=models.PROTECT,
        related_name="itens",
        verbose_name="venda",
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="itens_venda",
        verbose_name="produto",
    )
    nome_produto = models.CharField("nome do produto", max_length=120)
    codigo_barras = models.CharField("código de barras", max_length=64, blank=True)
    preco_unitario = models.DecimalField("preço unitário", max_digits=10, decimal_places=2)
    custo_unitario = models.DecimalField(
        "custo unitário",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    quantidade = models.PositiveIntegerField("quantidade")
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["pk"]
        verbose_name = "item da venda"
        verbose_name_plural = "itens da venda"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantidade__gt=0),
                name="loja_item_venda_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=Q(preco_unitario__gt=0) & Q(subtotal__gt=0),
                name="loja_item_venda_valores_positivos",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.preco_unitario is not None
            and self.quantidade is not None
            and self.subtotal is not None
            and self.preco_unitario * self.quantidade != self.subtotal
        ):
            raise ValidationError({"subtotal": "O subtotal deve corresponder ao preço vezes a quantidade."})

    def __str__(self):
        return f"{self.nome_produto} — {self.quantidade} un."


class Pagamento(models.Model):
    class FormaPagamento(models.TextChoices):
        DINHEIRO = "dinheiro", "Dinheiro"
        PIX = "pix", "Pix"
        CARTAO = "cartao", "Cartão"

    venda = models.OneToOneField(
        Venda,
        on_delete=models.PROTECT,
        related_name="pagamento",
        verbose_name="venda",
    )
    forma_pagamento = models.CharField(
        "forma de pagamento",
        max_length=10,
        choices=FormaPagamento.choices,
    )
    valor_pago = models.DecimalField("valor pago", max_digits=12, decimal_places=2)
    valor_recebido = models.DecimalField(
        "valor recebido",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    troco = models.DecimalField(
        "troco",
        max_digits=12,
        decimal_places=2,
        default=VALOR_ZERO,
    )
    data_pagamento = models.DateTimeField("data do pagamento", auto_now_add=True)

    class Meta:
        ordering = ["-data_pagamento", "-pk"]
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_pago__gt=0) & Q(troco__gte=0),
                name="loja_pagamento_valores_validos",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        forma_pagamento="dinheiro",
                        valor_recebido__gte=F("valor_pago"),
                        troco=F("valor_recebido") - F("valor_pago"),
                    )
                    | Q(
                        forma_pagamento__in=[
                            "pix",
                            "cartao",
                        ],
                        valor_recebido__isnull=True,
                        troco=VALOR_ZERO,
                    )
                ),
                name="loja_pagamento_troco_coerente",
            ),
        ]

    def clean(self):
        super().clean()
        if self.venda_id and self.valor_pago != self.venda.total:
            raise ValidationError({"valor_pago": "O pagamento deve corresponder ao total da venda."})

    def __str__(self):
        return f"{self.get_forma_pagamento_display()} — R$ {self.valor_pago}"
