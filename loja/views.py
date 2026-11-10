from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper
from django.shortcuts import get_object_or_404, redirect, render

from .filters import ProdutoFiltroForm
from .forms import CategoriaForm, ProdutoForm
from .models import Categoria, Produto


def staff_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


@staff_required
def inicio(request):
    total_produtos = Produto.objects.count()
    total_categorias = Categoria.objects.count()
    total_estoque_baixo = Produto.objects.filter(quantidade__lte=5).count()
    itens_baixo_estoque = Produto.objects.filter(quantidade__lte=5).order_by("quantidade", "nome")[:5]
    valor_total = Produto.objects.aggregate(
        total=Sum(
            ExpressionWrapper(
                F("preco") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )["total"] or 0
    ultimos_produtos = Produto.objects.select_related("categoria").order_by("-criado_em")[:5]
    return render(request, "loja/inicio.html", {
        "total_produtos": total_produtos,
        "total_categorias": total_categorias,
        "total_estoque_baixo": total_estoque_baixo,
        "itens_baixo_estoque": itens_baixo_estoque,
        "valor_total": valor_total,
        "ultimos_produtos": ultimos_produtos,
    })


@staff_required
def produtos(request):
    filtro_form = ProdutoFiltroForm(request.GET or None)
    lista = Produto.objects.select_related("categoria")
    termo = ""
    categoria_selecionada = ""
    ordenacao = ""
    if filtro_form.is_valid():
        termo = filtro_form.cleaned_data["q"].strip()
        categoria = filtro_form.cleaned_data["categoria"]
        ordenacao = filtro_form.cleaned_data["ordenar"]
        if termo:
            lista = lista.filter(nome__icontains=termo)
        if categoria:
            categoria_selecionada = categoria.pk
            lista = lista.filter(categoria=categoria)
        if ordenacao:
            lista = lista.order_by(ordenacao, "pk")
    else:
        lista = lista.none()
    page_obj = Paginator(lista, 20).get_page(request.GET.get("page"))
    return render(request, "loja/produtos.html", {
        "produtos": page_obj.object_list,
        "page_obj": page_obj,
        "termo": termo,
        "filtro_form": filtro_form,
        "categoria_selecionada": categoria_selecionada,
        "ordenacao": ordenacao,
    })


@staff_required
def produto_criar(request):
    if request.method == "POST":
        form = ProdutoForm(request.POST)
        if form.is_valid():
            produto = form.save()
            messages.success(request, f'Produto "{produto.nome}" cadastrado com sucesso.')
            return redirect("loja:produtos")
    else:
        form = ProdutoForm()
    return render(request, "loja/formulario.html", {
        "form": form, "titulo": "Cadastrar produto", "voltar_url": "loja:produtos"
    })


@staff_required
def produto_editar(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    if request.method == "POST":
        form = ProdutoForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            messages.success(request, f'Produto "{produto.nome}" atualizado com sucesso.')
            return redirect("loja:produtos")
    else:
        form = ProdutoForm(instance=produto)
    return render(request, "loja/formulario.html", {
        "form": form, "titulo": "Editar produto", "voltar_url": "loja:produtos"
    })


@staff_required
def produto_excluir(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    if request.method == "POST":
        nome = produto.nome
        produto.delete()
        messages.success(request, f'Produto "{nome}" excluído.')
        return redirect("loja:produtos")
    return render(request, "loja/confirmar_exclusao.html", {
        "objeto": produto, "tipo": "produto", "voltar_url": "loja:produtos"
    })


@staff_required
def categorias(request):
    lista = Categoria.objects.annotate(total_produtos=Count("produtos"))
    return render(request, "loja/categorias.html", {"categorias": lista})


@staff_required
def categoria_criar(request):
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, f'Categoria "{categoria.nome}" cadastrada com sucesso.')
            return redirect("loja:categorias")
    else:
        form = CategoriaForm()
    return render(request, "loja/formulario.html", {
        "form": form, "titulo": "Cadastrar categoria", "voltar_url": "loja:categorias"
    })


@staff_required
def categoria_editar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == "POST":
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoria "{categoria.nome}" atualizada com sucesso.')
            return redirect("loja:categorias")
    else:
        form = CategoriaForm(instance=categoria)
    return render(request, "loja/formulario.html", {
        "form": form, "titulo": "Editar categoria", "voltar_url": "loja:categorias"
    })


@staff_required
def categoria_excluir(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == "POST":
        if categoria.produtos.exists():
            messages.error(request, "Não é possível excluir uma categoria que possui produtos. Edite ou exclua os produtos primeiro.")
            return redirect("loja:categorias")
        nome = categoria.nome
        categoria.delete()
        messages.success(request, f'Categoria "{nome}" excluída.')
        return redirect("loja:categorias")
    return render(request, "loja/confirmar_exclusao.html", {
        "objeto": categoria, "tipo": "categoria", "voltar_url": "loja:categorias"
    })
