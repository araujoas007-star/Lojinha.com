from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=80, unique=True, verbose_name="nome")),
                ("descricao", models.TextField(blank=True, verbose_name="descrição")),
            ],
            options={
                "verbose_name": "categoria",
                "verbose_name_plural": "categorias",
                "ordering": ["nome"],
            },
        ),
        migrations.CreateModel(
            name="Produto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120, verbose_name="nome")),
                ("descricao", models.TextField(blank=True, verbose_name="descrição")),
                ("preco", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="preço")),
                ("quantidade", models.PositiveIntegerField(default=0, verbose_name="quantidade em estoque")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="cadastrado em")),
                ("categoria", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="produtos", to="loja.categoria", verbose_name="categoria")),
            ],
            options={
                "verbose_name": "produto",
                "verbose_name_plural": "produtos",
                "ordering": ["nome"],
            },
        ),
    ]
