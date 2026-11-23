from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from .models import MovimentacaoEstoque, Produto, Venda


ZERO = Decimal("0.00")


def _metricas(vendas):
    totais = vendas.aggregate(
        subtotal=Sum("subtotal"),
        descontos=Sum("desconto"),
        faturamento=Sum("total"),
    )
    return {
        "quantidade": vendas.count(),
        "subtotal": totais["subtotal"] or ZERO,
        "descontos": totais["descontos"] or ZERO,
        "faturamento": totais["faturamento"] or ZERO,
    }


def _variacao_percentual(atual, anterior):
    if anterior == 0:
        return Decimal("0.0") if atual == 0 else None
    return ((Decimal(atual) - Decimal(anterior)) / Decimal(anterior) * 100).quantize(
        Decimal("0.1")
    )


def _normalizar_periodo(valor):
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.date()
    return valor


def _intervalos(data_inicio, data_fim, agrupamento):
    if agrupamento == "dia":
        cursor = data_inicio
        while cursor <= data_fim:
            yield cursor
            if cursor == data_fim:
                break
            cursor += timedelta(days=1)
    elif agrupamento == "semana":
        cursor = data_inicio - timedelta(days=data_inicio.weekday())
        ultimo = data_fim - timedelta(days=data_fim.weekday())
        while cursor <= ultimo:
            yield cursor
            if cursor == ultimo:
                break
            cursor += timedelta(days=7)
    else:
        cursor = data_inicio.replace(day=1)
        ultimo = data_fim.replace(day=1)
        while cursor <= ultimo:
            yield cursor
            if cursor == ultimo:
                break
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)


def _rotulo_periodo(periodo, agrupamento):
    if agrupamento == "semana":
        return f"Semana de {periodo:%d/%m/%Y}"
    if agrupamento == "mes":
        return periodo.strftime("%m/%Y")
    return periodo.strftime("%d/%m/%Y")


def _serie_faturamento(vendas, data_inicio, data_fim, agrupamento):
    truncadores = {
        "dia": TruncDate,
        "semana": TruncWeek,
        "mes": TruncMonth,
    }
    agrupamento_db = truncadores[agrupamento]("data_venda")
    agregados = {}
    registros = (
        vendas.order_by()
        .annotate(periodo=agrupamento_db)
        .values("periodo")
        .annotate(faturamento=Sum("total"), quantidade=Count("pk"))
        .order_by("periodo")
    )
    for registro in registros:
        agregados[_normalizar_periodo(registro["periodo"])] = registro

    serie = []
    maior_faturamento = max(
        (registro["faturamento"] for registro in agregados.values()),
        default=ZERO,
    )
    for periodo in _intervalos(data_inicio, data_fim, agrupamento):
        registro = agregados.get(periodo, {})
        faturamento = registro.get("faturamento") or ZERO
        percentual = (
            int(faturamento * 100 / maior_faturamento)
            if maior_faturamento
            else 0
        )
        serie.append({
            "periodo": periodo,
            "rotulo": _rotulo_periodo(periodo, agrupamento),
            "quantidade": registro.get("quantidade", 0),
            "faturamento": faturamento,
            "percentual_barra": percentual,
        })
    return serie


def _produtos_vendidos(data_inicio, data_fim):
    vendas_no_periodo = Q(
        itens_venda__venda__status=Venda.Status.FINALIZADA,
        itens_venda__venda__data_venda__date__gte=data_inicio,
        itens_venda__venda__data_venda__date__lte=data_fim,
    )
    produtos = Produto.objects.annotate(
        quantidade_vendida=Coalesce(
            Sum("itens_venda__quantidade", filter=vendas_no_periodo),
            Value(0),
            output_field=IntegerField(),
        )
    ).filter(Q(ativo=True) | Q(quantidade_vendida__gt=0))
    mais_vendidos = list(produtos.filter(
        quantidade_vendida__gt=0,
    ).order_by("-quantidade_vendida", "nome")[:10])
    menos_vendidos = list(produtos.order_by("quantidade_vendida", "nome")[:10])
    maior_quantidade = mais_vendidos[0].quantidade_vendida if mais_vendidos else 0
    for produto in mais_vendidos:
        produto.percentual_barra = int(produto.quantidade_vendida * 100 / maior_quantidade)
    for produto in menos_vendidos:
        produto.percentual_barra = (
            int(produto.quantidade_vendida * 100 / maior_quantidade)
            if maior_quantidade
            else 0
        )
    return mais_vendidos, menos_vendidos


def gerar_relatorio(*, data_inicio, data_fim, agrupamento):
    if data_inicio > data_fim:
        raise ValueError("A data inicial não pode ser posterior à data final.")

    vendas_periodo = Venda.objects.filter(
        status=Venda.Status.FINALIZADA,
        data_venda__date__gte=data_inicio,
        data_venda__date__lte=data_fim,
    )
    canceladas = Venda.objects.filter(
        status=Venda.Status.CANCELADA,
        data_venda__date__gte=data_inicio,
        data_venda__date__lte=data_fim,
    ).count()

    dias = (data_fim - data_inicio).days + 1
    periodo_anterior_fim = data_inicio - timedelta(days=1)
    periodo_anterior_inicio = periodo_anterior_fim - timedelta(days=dias - 1)
    vendas_periodo_anterior = Venda.objects.filter(
        status=Venda.Status.FINALIZADA,
        data_venda__date__gte=periodo_anterior_inicio,
        data_venda__date__lte=periodo_anterior_fim,
    )
    metricas = _metricas(vendas_periodo)
    metricas_anteriores = _metricas(vendas_periodo_anterior)
    comparacao = {
        "inicio_anterior": periodo_anterior_inicio,
        "fim_anterior": periodo_anterior_fim,
        "vendas_anterior": metricas_anteriores["quantidade"],
        "faturamento_anterior": metricas_anteriores["faturamento"],
        "variacao_vendas": _variacao_percentual(
            metricas["quantidade"],
            metricas_anteriores["quantidade"],
        ),
        "variacao_faturamento": _variacao_percentual(
            metricas["faturamento"],
            metricas_anteriores["faturamento"],
        ),
    }
    comparacao["sem_base_faturamento"] = (
        metricas_anteriores["faturamento"] == 0 and metricas["faturamento"] > 0
    )
    comparacao["tem_variacao_faturamento"] = (
        comparacao["variacao_faturamento"] is not None
    )
    comparacao["faturamento_caiu"] = (
        comparacao["variacao_faturamento"] is not None
        and comparacao["variacao_faturamento"] < 0
    )
    comparacao["faturamento_subiu"] = (
        comparacao["variacao_faturamento"] is not None
        and comparacao["variacao_faturamento"] > 0
    )

    mais_vendidos, menos_vendidos = _produtos_vendidos(data_inicio, data_fim)
    estoque_baixo = Produto.objects.filter(
        ativo=True,
        quantidade__lte=F("estoque_minimo"),
    ).select_related("categoria").order_by("quantidade", "nome")
    movimentacoes = MovimentacaoEstoque.objects.filter(
        data_movimentacao__date__gte=data_inicio,
        data_movimentacao__date__lte=data_fim,
    ).select_related("produto", "responsavel").order_by("-data_movimentacao", "-pk")

    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "agrupamento": agrupamento,
        "metricas": metricas,
        "vendas_canceladas": canceladas,
        "comparacao": comparacao,
        "serie": _serie_faturamento(vendas_periodo, data_inicio, data_fim, agrupamento),
        "mais_vendidos": mais_vendidos,
        "menos_vendidos": menos_vendidos,
        "estoque_baixo": estoque_baixo,
        "movimentacoes": movimentacoes,
    }
