from functools import wraps
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .filters import ProdutoFiltroForm
from .forms import (
    AtualizarItemCarrinhoForm,
    BuscaProdutoPDVForm,
    CancelarVendaForm,
    CategoriaForm,
    FinalizarVendaForm,
    ItemCarrinhoForm,
    MovimentacaoEstoqueForm,
    ProdutoForm,
    RelatorioFiltroForm,
    RemoverItemCarrinhoForm,
    VendaFiltroForm,
)
from .models import Categoria, MovimentacaoEstoque, Pagamento, Produto, Venda
from .permissions import can_access_store, is_manager, require_manager
from .relatorio_pdf import criar_pdf_relatorio
from .relatorios import gerar_relatorio
from .services import registrar_movimentacao
from .vendas import (
    PreviaDesatualizada,
    assinar_previa,
    cancelar_venda,
    finalizar_venda,
    montar_previa_carrinho,
    normalizar_carrinho,
)


PDV_CART_KEY = "pdv_carrinho"


def _adicionar_erros_formulario(form, error):
    if hasattr(error, "error_dict"):
        for field_name, field_errors in error.error_dict.items():
            if field_name in form.fields:
                for field_error in field_errors:
                    form.add_error(field_name, field_error)
            else:
                form.add_error(None, field_errors)
    else:
        form.add_error(None, error)


def _ler_carrinho(request):
    carrinho = request.session.get(PDV_CART_KEY, {})
    if not carrinho:
        return {}
    try:
        return normalizar_carrinho(carrinho)
    except ValidationError:
        request.session[PDV_CART_KEY] = {}
        messages.error(request, "O carrinho estava inválido e foi limpo. Adicione os produtos novamente.")
        return {}


def _linhas_carrinho(carrinho):
    if not carrinho:
        return [], Decimal("0.00"), False
    produtos = {
        produto.pk: produto
        for produto in Produto.objects.filter(pk__in=carrinho).select_related("categoria")
    }
    linhas = []
    subtotal = Decimal("0.00")
    valido = True
    for produto_id, quantidade in carrinho.items():
        produto = produtos.get(produto_id)
        if produto is None:
            linhas.append({
                "produto_id": produto_id,
                "nome": f"Produto #{produto_id} indisponível",
                "quantidade": quantidade,
                "subtotal": Decimal("0.00"),
                "disponivel": False,
            })
            valido = False
            continue
        item_subtotal = produto.preco * quantidade
        subtotal += item_subtotal
        disponivel = produto.ativo and quantidade <= produto.quantidade
        linhas.append({
            "produto_id": produto_id,
            "produto": produto,
            "nome": produto.nome,
            "quantidade": quantidade,
            "preco_unitario": produto.preco,
            "subtotal": item_subtotal,
            "disponivel": disponivel,
        })
        valido = valido and disponivel
    return linhas, subtotal, valido


def _renderizar_checkout(request, form, previa, *, revisao=False):
    dados = getattr(form, "cleaned_data", {})
    desconto = dados.get("desconto") or Decimal("0.00")
    forma_pagamento = dados.get("forma_pagamento")
    valor_recebido = dados.get("valor_recebido")
    total = previa["subtotal"] - desconto
    return render(request, "loja/venda_checkout.html", {
        "form": form,
        "previa": previa,
        "total": total,
        "desconto": desconto,
        "revisao": revisao,
        "forma_pagamento_display": dict(Pagamento.FormaPagamento.choices).get(forma_pagamento, ""),
        "valor_recebido": valor_recebido,
        "troco": (valor_recebido - total) if valor_recebido is not None else Decimal("0.00"),
        "token_previa": assinar_previa(
            previa["snapshot"],
            forma_pagamento=forma_pagamento if revisao else None,
            desconto=desconto if revisao else None,
            valor_recebido=valor_recebido if revisao else None,
        ),
    })


def staff_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not can_access_store(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


@staff_required
def inicio(request):
    total_produtos = Produto.objects.filter(ativo=True).count()
    total_categorias = Categoria.objects.count()
    total_estoque_baixo = Produto.objects.filter(
        ativo=True,
        quantidade__lte=F("estoque_minimo"),
    ).count()
    itens_baixo_estoque = Produto.objects.filter(
        ativo=True,
        quantidade__lte=F("estoque_minimo"),
    ).order_by("quantidade", "nome")[:5]
    valor_total = Produto.objects.filter(ativo=True).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("preco") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )["total"] or 0
    ultimos_produtos = Produto.objects.filter(
        ativo=True,
    ).select_related("categoria").order_by("-criado_em")[:5]
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
    gerente = is_manager(request.user)
    filtro_form = ProdutoFiltroForm(request.GET, user=request.user)
    lista = Produto.objects.select_related("categoria")
    termo = ""
    categoria_selecionada = ""
    ordenacao = ""
    situacao = "ativos"
    if filtro_form.is_valid():
        termo = filtro_form.cleaned_data["q"].strip()
        categoria = filtro_form.cleaned_data["categoria"]
        ordenacao = filtro_form.cleaned_data["ordenar"]
        situacao = filtro_form.cleaned_data.get("situacao") or "ativos"
        if gerente and situacao == "arquivados":
            lista = lista.filter(ativo=False)
        elif not gerente or situacao == "ativos":
            lista = lista.filter(ativo=True)
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
        "situacao": situacao,
        "gerente": gerente,
    })


@staff_required
def produto_criar(request):
    if request.method == "POST":
        form = ProdutoForm(request.POST)
        if form.is_valid():
            produto = form.save()
            messages.success(
                request,
                f'Produto "{produto.nome}" cadastrado. Registre a entrada de estoque no módulo Estoque.',
            )
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
    require_manager(request.user)
    produto = get_object_or_404(Produto, pk=pk, ativo=True)
    if request.method == "POST":
        produto.ativo = False
        produto.save(update_fields=["ativo"])
        messages.success(request, f'Produto "{produto.nome}" arquivado. O histórico foi preservado.')
        return redirect("loja:produtos")
    return render(request, "loja/confirmar_exclusao.html", {
        "objeto": produto,
        "tipo": "produto",
        "acao": "arquivar",
        "voltar_url": "loja:produtos",
    })


@staff_required
def produto_reativar(request, pk):
    require_manager(request.user)
    produto = get_object_or_404(Produto, pk=pk, ativo=False)
    if request.method == "POST":
        produto.ativo = True
        produto.save(update_fields=["ativo"])
        messages.success(request, f'Produto "{produto.nome}" reativado.')
    return redirect(f"{reverse('loja:produtos')}?situacao=arquivados")


@staff_required
def estoque(request):
    produtos_ativos = Produto.objects.filter(ativo=True)
    movimentacoes = MovimentacaoEstoque.objects.select_related(
        "produto",
        "responsavel",
    )[:30]
    return render(request, "loja/estoque.html", {
        "form": MovimentacaoEstoqueForm(user=request.user),
        "total_produtos": produtos_ativos.count(),
        "total_estoque_baixo": produtos_ativos.filter(
            quantidade__lte=F("estoque_minimo"),
        ).count(),
        "total_sem_estoque": produtos_ativos.filter(quantidade=0).count(),
        "movimentacoes": movimentacoes,
        "gerente": is_manager(request.user),
    })


@staff_required
def estoque_movimentar(request):
    if request.method != "POST":
        return redirect("loja:estoque")

    form = MovimentacaoEstoqueForm(request.POST, user=request.user)
    if form.is_valid():
        try:
            movimentacao = registrar_movimentacao(
                produto_id=form.cleaned_data["produto"].pk,
                tipo=form.cleaned_data["tipo"],
                quantidade=form.cleaned_data["quantidade"],
                responsavel=request.user,
                motivo=form.cleaned_data["motivo"],
            )
        except ValidationError as error:
            _adicionar_erros_formulario(form, error)
        else:
            messages.success(
                request,
                f"Estoque de {movimentacao.produto.nome} atualizado para "
                f"{movimentacao.quantidade_posterior} unidade(s).",
            )
            return redirect("loja:estoque")

    produtos_ativos = Produto.objects.filter(ativo=True)
    return render(request, "loja/estoque.html", {
        "form": form,
        "total_produtos": produtos_ativos.count(),
        "total_estoque_baixo": produtos_ativos.filter(
            quantidade__lte=F("estoque_minimo"),
        ).count(),
        "total_sem_estoque": produtos_ativos.filter(quantidade=0).count(),
        "movimentacoes": MovimentacaoEstoque.objects.select_related(
            "produto",
            "responsavel",
        )[:30],
        "gerente": is_manager(request.user),
    })


@staff_required
def pdv(request):
    formulario_busca = BuscaProdutoPDVForm(request.GET)
    termo = ""
    produtos = Produto.objects.filter(ativo=True).select_related("categoria")
    if formulario_busca.is_valid():
        termo = formulario_busca.cleaned_data["q"].strip()
        if termo:
            produtos = produtos.filter(
                Q(nome__icontains=termo) | Q(codigo_barras__icontains=termo)
            )
    produtos = produtos.order_by("nome")[:30]
    carrinho = _ler_carrinho(request)
    linhas, subtotal, carrinho_valido = _linhas_carrinho(carrinho)
    return render(request, "loja/pdv.html", {
        "produtos": produtos,
        "formulario_busca": formulario_busca,
        "termo": termo,
        "linhas_carrinho": linhas,
        "subtotal_carrinho": subtotal,
        "carrinho_valido": carrinho_valido,
    })


@staff_required
def carrinho_adicionar(request):
    if request.method != "POST":
        return redirect("loja:pdv")
    form = ItemCarrinhoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe um produto e uma quantidade válida.")
        return redirect("loja:pdv")

    produto = get_object_or_404(
        Produto,
        pk=form.cleaned_data["produto_id"],
        ativo=True,
    )
    carrinho = _ler_carrinho(request)
    produto_id = str(produto.pk)
    quantidade = carrinho.get(produto.pk, carrinho.get(produto_id, 0))
    nova_quantidade = quantidade + form.cleaned_data["quantidade"]
    if nova_quantidade > produto.quantidade:
        messages.error(
            request,
            f"Estoque insuficiente para {produto.nome}. Disponível: {produto.quantidade}.",
        )
    else:
        carrinho.pop(produto.pk, None)
        carrinho[produto_id] = nova_quantidade
        request.session[PDV_CART_KEY] = carrinho
        messages.success(request, f"{produto.nome} adicionado ao carrinho.")
    return redirect("loja:pdv")


@staff_required
def carrinho_atualizar(request):
    if request.method != "POST":
        return redirect("loja:pdv")
    form = AtualizarItemCarrinhoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe uma quantidade válida.")
        return redirect("loja:pdv")

    produto_id = form.cleaned_data["produto_id"]
    carrinho = _ler_carrinho(request)
    quantidade = form.cleaned_data["quantidade"]
    if produto_id not in carrinho:
        messages.error(request, "Esse produto não está no carrinho.")
    elif quantidade == 0:
        carrinho.pop(produto_id)
        request.session[PDV_CART_KEY] = carrinho
        messages.success(request, "Produto removido do carrinho.")
    else:
        produto = get_object_or_404(Produto, pk=produto_id, ativo=True)
        if quantidade > produto.quantidade:
            messages.error(
                request,
                f"Estoque insuficiente para {produto.nome}. Disponível: {produto.quantidade}.",
            )
        else:
            carrinho[produto_id] = quantidade
            request.session[PDV_CART_KEY] = carrinho
            messages.success(request, "Quantidade do carrinho atualizada.")
    return redirect("loja:pdv")


@staff_required
def carrinho_remover(request):
    if request.method != "POST":
        return redirect("loja:pdv")
    form = RemoverItemCarrinhoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Não foi possível identificar o produto.")
        return redirect("loja:pdv")
    carrinho = _ler_carrinho(request)
    carrinho.pop(form.cleaned_data["produto_id"], None)
    request.session[PDV_CART_KEY] = carrinho
    messages.success(request, "Produto removido do carrinho.")
    return redirect("loja:pdv")


@staff_required
def carrinho_limpar(request):
    if request.method == "POST":
        request.session[PDV_CART_KEY] = {}
        messages.success(request, "Carrinho limpo.")
    return redirect("loja:pdv")


@staff_required
def venda_checkout(request):
    carrinho = _ler_carrinho(request)
    try:
        previa = montar_previa_carrinho(carrinho)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("loja:pdv")

    form = FinalizarVendaForm(
        request.POST if request.method == "POST" else None,
        user=request.user,
        subtotal=previa["subtotal"],
    )
    if request.method == "POST" and form.is_valid():
        if request.POST.get("acao") == "revisar":
            return _renderizar_checkout(request, form, previa, revisao=True)
        if request.POST.get("acao") != "finalizar":
            return _renderizar_checkout(request, form, previa)
        try:
            venda = finalizar_venda(
                carrinho=carrinho,
                usuario=request.user,
                forma_pagamento=form.cleaned_data["forma_pagamento"],
                desconto=form.cleaned_data.get("desconto") or Decimal("0.00"),
                valor_recebido=form.cleaned_data.get("valor_recebido"),
                token_previa=request.POST.get("token_previa", ""),
            )
        except PreviaDesatualizada:
            form.add_error(
                None,
                "O preço, o estoque ou os dados da venda mudaram desde a revisão. Confira os valores e revise novamente.",
            )
            try:
                previa = montar_previa_carrinho(carrinho)
            except ValidationError as error:
                messages.error(request, error.messages[0])
                return redirect("loja:pdv")
        except ValidationError as error:
            _adicionar_erros_formulario(form, error)
            try:
                previa = montar_previa_carrinho(carrinho)
            except ValidationError as preview_error:
                messages.error(request, preview_error.messages[0])
                return redirect("loja:pdv")
        else:
            request.session[PDV_CART_KEY] = {}
            messages.success(request, f"Venda #{venda.pk} finalizada com sucesso.")
            return redirect("loja:venda_detalhe", pk=venda.pk)

    return _renderizar_checkout(request, form, previa)


@staff_required
def vendas(request):
    filtro = VendaFiltroForm(request.GET)
    lista = Venda.objects.select_related(
        "usuario",
        "usuario_cancelamento",
        "pagamento",
    ).prefetch_related("itens")
    if filtro.is_valid():
        if filtro.cleaned_data["data_inicio"]:
            lista = lista.filter(data_venda__date__gte=filtro.cleaned_data["data_inicio"])
        if filtro.cleaned_data["data_fim"]:
            lista = lista.filter(data_venda__date__lte=filtro.cleaned_data["data_fim"])
        if filtro.cleaned_data["status"]:
            lista = lista.filter(status=filtro.cleaned_data["status"])
    else:
        lista = lista.none()
    page_obj = Paginator(lista, 25).get_page(request.GET.get("page"))
    return render(request, "loja/vendas.html", {
        "filtro": filtro,
        "vendas": page_obj.object_list,
        "page_obj": page_obj,
    })


def _formulario_relatorios(request):
    if request.GET:
        return RelatorioFiltroForm(request.GET)

    hoje = timezone.localdate()
    dados = QueryDict(mutable=True)
    dados.update({
        "data_inicio": hoje.replace(day=1).isoformat(),
        "data_fim": hoje.isoformat(),
        "agrupamento": "dia",
    })
    return RelatorioFiltroForm(dados)


@staff_required
def relatorios(request):
    filtro = _formulario_relatorios(request)
    relatorio = None
    pdf_url = None
    movimentacoes_recentes = None
    if filtro.is_valid():
        dados = filtro.cleaned_data
        relatorio = gerar_relatorio(
            data_inicio=dados["data_inicio"],
            data_fim=dados["data_fim"],
            agrupamento=dados["agrupamento"],
        )
        query = urlencode({
            "data_inicio": dados["data_inicio"].isoformat(),
            "data_fim": dados["data_fim"].isoformat(),
            "agrupamento": dados["agrupamento"],
        })
        pdf_url = f"{reverse('loja:relatorios_pdf')}?{query}"
        movimentacoes_recentes = relatorio["movimentacoes"][:30]
    return render(request, "loja/relatorios.html", {
        "filtro": filtro,
        "relatorio": relatorio,
        "pdf_url": pdf_url,
        "movimentacoes_recentes": movimentacoes_recentes,
    })


@staff_required
def relatorios_pdf(request):
    filtro = _formulario_relatorios(request)
    if not filtro.is_valid():
        return HttpResponseBadRequest("Informe um período e um agrupamento válidos para exportar.")

    dados = filtro.cleaned_data
    relatorio = gerar_relatorio(
        data_inicio=dados["data_inicio"],
        data_fim=dados["data_fim"],
        agrupamento=dados["agrupamento"],
    )
    arquivo = criar_pdf_relatorio(relatorio)
    nome = (
        f"relatorio_{dados['data_inicio'].isoformat()}_"
        f"{dados['data_fim'].isoformat()}.pdf"
    )
    resposta = HttpResponse(
        arquivo.getvalue(),
        content_type="application/pdf",
    )
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@staff_required
def venda_detalhe(request, pk):
    venda = get_object_or_404(
        Venda.objects.select_related(
            "usuario",
            "usuario_cancelamento",
            "gerente_autorizador",
            "pagamento",
        ).prefetch_related("itens"),
        pk=pk,
    )
    return render(request, "loja/venda_detalhe.html", {
        "venda": venda,
        "pode_cancelar": venda.status == Venda.Status.FINALIZADA,
    })


@staff_required
def venda_comprovante(request, pk):
    venda = get_object_or_404(
        Venda.objects.select_related("pagamento").prefetch_related("itens"),
        pk=pk,
    )
    return render(request, "loja/venda_comprovante.html", {"venda": venda})


@staff_required
def venda_cancelar(request, pk):
    venda = get_object_or_404(Venda, pk=pk)
    if venda.status != Venda.Status.FINALIZADA:
        messages.error(request, "Esta venda já foi cancelada.")
        return redirect("loja:venda_detalhe", pk=venda.pk)
    form = CancelarVendaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            cancelar_venda(
                venda_id=venda.pk,
                usuario=request.user,
                motivo=form.cleaned_data["motivo"],
            )
        except ValidationError as error:
            _adicionar_erros_formulario(form, error)
        else:
            messages.success(request, f"Venda #{venda.pk} cancelada e estoque estornado.")
            return redirect("loja:venda_detalhe", pk=venda.pk)
    return render(request, "loja/confirmar_cancelamento.html", {
        "venda": venda,
        "form": form,
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
