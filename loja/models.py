from django.db import models
from django.urls import reverse


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
    quantidade = models.PositiveIntegerField("quantidade em estoque", default=0)
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
        return self.quantidade <= 5

    @property
    def valor_em_estoque(self):
        return self.preco * self.quantidade
