from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _texto(valor):
    return escape(str(valor)).replace("\n", "<br/>")


def _dinheiro(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _variacao(valor):
    return "Sem base de comparação" if valor is None else f"{valor:.1f}%".replace(".", ",")


def criar_pdf_relatorio(relatorio):
    arquivo = BytesIO()
    documento = SimpleDocTemplate(
        arquivo,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Relatório Lojinha.com",
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "RelatorioTitulo", parent=estilos["Title"], textColor=colors.HexColor("#173b37")
    )
    secao = ParagraphStyle(
        "RelatorioSecao", parent=estilos["Heading2"], textColor=colors.HexColor("#173b37"),
        spaceBefore=12, spaceAfter=6, keepWithNext=True,
    )
    corpo = ParagraphStyle(
        "RelatorioCorpo", parent=estilos["BodyText"], fontSize=9, leading=13, spaceAfter=4,
    )
    rodape = ParagraphStyle(
        "RelatorioRodape", parent=corpo, fontSize=8, alignment=TA_CENTER
    )
    conteudo = [
        Paragraph("Lojinha.com — Relatório", titulo),
        Paragraph(
            f'{relatorio["data_inicio"]:%d/%m/%Y} a {relatorio["data_fim"]:%d/%m/%Y}',
            rodape,
        ),
    ]

    def adicionar_secao(nome):
        conteudo.append(Paragraph(_texto(nome), secao))

    def adicionar_linha(rotulo, valor):
        conteudo.append(Paragraph(f"<b>{_texto(rotulo)}:</b> {_texto(valor)}", corpo))

    metricas = relatorio["metricas"]
    comparacao = relatorio["comparacao"]
    adicionar_secao("Resumo")
    adicionar_linha("Vendas finalizadas", metricas["quantidade"])
    adicionar_linha("Vendas canceladas", relatorio["vendas_canceladas"])
    adicionar_linha("Subtotal vendido", _dinheiro(metricas["subtotal"]))
    adicionar_linha("Descontos", _dinheiro(metricas["descontos"]))
    adicionar_linha("Faturamento das vendas finalizadas", _dinheiro(metricas["faturamento"]))

    adicionar_secao("Comparação com o período anterior")
    adicionar_linha(
        "Período",
        f'{comparacao["inicio_anterior"]:%d/%m/%Y} a {comparacao["fim_anterior"]:%d/%m/%Y}',
    )
    adicionar_linha("Vendas anteriores", comparacao["vendas_anterior"])
    adicionar_linha("Faturamento anterior", _dinheiro(comparacao["faturamento_anterior"]))
    adicionar_linha("Variação de vendas", _variacao(comparacao["variacao_vendas"]))
    adicionar_linha("Variação de faturamento", _variacao(comparacao["variacao_faturamento"]))

    agrupamento = {"dia": "diário", "semana": "semanal", "mes": "mensal"}
    adicionar_secao(f'Faturamento {agrupamento[relatorio["agrupamento"]]}')
    for ponto in relatorio["serie"]:
        adicionar_linha(
            ponto["rotulo"],
            f'{ponto["quantidade"]} venda(s) — {_dinheiro(ponto["faturamento"])}',
        )

    for nome, chave in (("Mais vendidos", "mais_vendidos"), ("Menos vendidos", "menos_vendidos")):
        adicionar_secao(nome)
        if not relatorio[chave]:
            conteudo.append(Paragraph("Nenhum produto neste período.", corpo))
        for produto in relatorio[chave]:
            codigo = f" — Código: {produto.codigo_barras}" if produto.codigo_barras else ""
            adicionar_linha(produto.nome, f"{produto.quantidade_vendida} unidade(s){codigo}")

    adicionar_secao("Estoque baixo — saldo atual")
    encontrou_produto = False
    for produto in relatorio["estoque_baixo"].iterator():
        encontrou_produto = True
        adicionar_linha(
            produto.nome,
            f"{produto.categoria.nome} — saldo: {produto.quantidade} — mínimo: {produto.estoque_minimo}",
        )
    if not encontrou_produto:
        conteudo.append(Paragraph("Nenhum produto com estoque baixo.", corpo))

    adicionar_secao("Movimentações de estoque")
    encontrou_movimento = False
    for movimento in relatorio["movimentacoes"].iterator():
        encontrou_movimento = True
        data = timezone.localtime(movimento.data_movimentacao).strftime("%d/%m/%Y %H:%M")
        adicionar_linha(
            f"{data} — {movimento.produto.nome}",
            f"{movimento.get_tipo_display()} — variação: {movimento.variacao_quantidade:+d} "
            f"— saldo: {movimento.quantidade_anterior} para {movimento.quantidade_posterior} "
            f"— responsável: {movimento.responsavel_nome} — motivo: {movimento.motivo or '—'}",
        )
    if not encontrou_movimento:
        conteudo.append(Paragraph("Nenhuma movimentação neste período.", corpo))

    conteudo.append(Spacer(1, 5 * mm))
    conteudo.append(Paragraph("Faturamento considera apenas vendas finalizadas.", rodape))
    documento.build(conteudo)
    arquivo.seek(0)
    return arquivo
