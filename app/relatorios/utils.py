"""Utilidades partilhadas: formatação, PDF (xhtml2pdf) e Excel (openpyxl)."""
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from xhtml2pdf import pisa

NUM = (int, float, Decimal)


# --------------------------------------------------------------------------
# Dados da escola (não existe model Escola -> vem de settings.ESCOLA)
# --------------------------------------------------------------------------
def escola():
    base = {
        "nome": "Escola",
        "nif": "",
        "endereco": "",
        "telefone": "",
        "email": "",
        "logo": "",            # ex.: "/static/img/logo.png" ou caminho absoluto
        "provincia": "Luanda",
        "municipio": "",
        "cabecalho": ["República de Angola", "Ministério da Educação"],
        "ciclo": "Ensino Secundário - 2.º Ciclo",
    }
    base.update(getattr(settings, "ESCOLA", {}))
    return base


def limiar(ano, classe):
    """Nota mínima positiva (RegraAvaliacao do ano/classe, senão 10)."""
    from app.db.models import RegraAvaliacao
    v = (RegraAvaliacao.objects.filter(ano_lectivo=ano, classe=classe)
         .values_list("nota_minima_positiva", flat=True).first())
    return v if v is not None else Decimal(10)


# --------------------------------------------------------------------------
# Formatação
# --------------------------------------------------------------------------
def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, Decimal)):
        return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(v, datetime):
        if timezone.is_aware(v):
            v = timezone.localtime(v)
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def cel_nota(v, lim=Decimal(10)):
    """Célula de nota para os templates PDF: (texto, classe css)."""
    if v is None:
        return ("-", "c")
    return (fmt(Decimal(v)), "neg" if Decimal(v) < lim else "c")


@dataclass
class Tabela:
    titulo: str = ""
    colunas: list = field(default_factory=list)
    linhas: list = field(default_factory=list)
    rodape: list | None = None
    notas_cols: tuple = ()        # colunas onde nota < nota_min fica a vermelho
    nota_min: float = 10
    larguras: list | None = None  # % por coluna (opcional)

    def _auto_larguras(self):
        """Larguras (%) automáticas: colunas de texto ganham mais espaço que as numéricas."""
        pesos = []
        for i, c in enumerate(self.colunas):
            amostra = [l[i] for l in self.linhas[:200] if i < len(l) and l[i] not in (None, "")]
            comp = max([len(fmt(v)) for v in amostra] + [0])
            numerica = bool(amostra) and all(isinstance(v, NUM) or isinstance(v, date) for v in amostra)
            p = max(len(str(c)) * 0.7, min(comp, 40))
            pesos.append(min(max(p, 3), 9 if numerica else 40))
        tot = sum(pesos) or 1
        return [round(p * 100 / tot, 1) for p in pesos]

    def cab(self):
        return list(zip(self.colunas, self.larguras or self._auto_larguras()))

    def _cel(self, i, v):
        classe = ""
        if (isinstance(v, NUM) and not isinstance(v, bool)) or isinstance(v, date):
            classe = "c"
        if i in self.notas_cols and isinstance(v, NUM) and not isinstance(v, bool) and v < self.nota_min:
            classe = "neg"
        return (fmt(v), classe)

    def linhas_fmt(self):
        return [[self._cel(i, v) for i, v in enumerate(l)] for l in self.linhas]

    def rodape_fmt(self):
        return [self._cel(-1, v) for v in self.rodape] if self.rodape else None


@dataclass
class Relatorio:
    titulo: str
    subtitulo: str = ""
    tabelas: list = field(default_factory=list)
    resumo: list = field(default_factory=list)   # [(rótulo, valor)]
    orientacao: str = ""                          # "", portrait, landscape
    assinaturas: bool = False
    filtros_txt: str = ""

    @property
    def orient(self):
        if self.orientacao:
            return self.orientacao
        return "landscape" if any(len(t.colunas) > 8 for t in self.tabelas) else "portrait"

    def resumo_fmt(self):
        return [(k, fmt(v)) for k, v in self.resumo]

    @property
    def max_colunas(self):
        return max([len(t.colunas) for t in self.tabelas] or [0])


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def link_callback(uri, rel):
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri
    for url, root in ((getattr(settings, "MEDIA_URL", ""), getattr(settings, "MEDIA_ROOT", "")),
                      (getattr(settings, "STATIC_URL", ""), getattr(settings, "STATIC_ROOT", ""))):
        if url and root and uri.startswith(url):
            p = os.path.join(str(root), uri[len(url):])
            if os.path.exists(p):
                return p
    su = getattr(settings, "STATIC_URL", "")
    if su and uri.startswith(su):
        from django.contrib.staticfiles import finders
        p = finders.find(uri[len(su):])
        if p:
            return p
    return uri


def render_pdf(request, template, ctx, filename, inline=True):
    html = render_to_string(template, ctx, request=request)
    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}.pdf"'
    status = pisa.CreatePDF(src=html, dest=resp, encoding="utf-8", link_callback=link_callback)
    if status.err:
        return HttpResponse("Erro ao gerar o PDF.", status=500)
    return resp


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------
def _xl(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, datetime) and timezone.is_aware(v):
        return timezone.localtime(v).replace(tzinfo=None)
    return v


def exportar_xlsx(rel, esc, filename):
    wb = Workbook()
    wb.remove(wb.active)
    azul = PatternFill("solid", fgColor="1D4ED8")
    cinza = PatternFill("solid", fgColor="E5E7EB")
    lado = Side(style="thin", color="CBD5E1")
    borda = Border(left=lado, right=lado, top=lado, bottom=lado)
    usados = set()

    for i, t in enumerate(rel.tabelas, 1):
        base = re.sub(r"[\[\]\*\?/\\:]", "", t.titulo or rel.titulo)[:28] or f"Folha {i}"
        nome, n = base, 1
        while nome in usados:
            n += 1
            nome = f"{base[:26]} {n}"
        usados.add(nome)
        ws = wb.create_sheet(nome)
        ncol = max(len(t.colunas), 4)
        larg = {}

        def medir(col, v):
            larg[col] = max(larg.get(col, 8), min(len(str(fmt(v))) + 2, 45))

        r = 1
        for txt, size, bold in ((esc["nome"], 13, True), (rel.titulo, 12, True),
                                (rel.subtitulo, 10, False), (rel.filtros_txt, 9, False)):
            if not txt:
                continue
            ws.cell(row=r, column=1, value=txt).font = Font(size=size, bold=bold)
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
            r += 1
        if i == 1 and rel.resumo:
            r += 1
            for k, v in rel.resumo:
                ws.cell(row=r, column=1, value=k).font = Font(bold=True)
                ws.cell(row=r, column=2, value=_xl(v))
                medir(1, k)
                r += 1
        r += 1
        if t.titulo and len(rel.tabelas) > 1:
            ws.cell(row=r, column=1, value=t.titulo).font = Font(size=11, bold=True)
            r += 1
        cab = r
        for c, h in enumerate(t.colunas, 1):
            x = ws.cell(row=cab, column=c, value=h)
            x.font = Font(bold=True, color="FFFFFF")
            x.fill = azul
            x.border = borda
            x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            medir(c, h)
        ws.freeze_panes = ws.cell(row=cab + 1, column=1)

        for l in t.linhas + ([t.rodape] if t.rodape else []):
            r += 1
            eh_rodape = t.rodape is not None and l is t.rodape
            for c, v in enumerate(l, 1):
                v = _xl(v)
                x = ws.cell(row=r, column=c, value=v)
                x.border = borda
                if isinstance(v, datetime):
                    x.number_format = "DD/MM/YYYY HH:MM"
                elif isinstance(v, date):
                    x.number_format = "DD/MM/YYYY"
                elif isinstance(v, float):
                    x.number_format = "0.00"
                if isinstance(v, (int, float, date)):
                    x.alignment = Alignment(horizontal="center")
                if (c - 1) in t.notas_cols and isinstance(v, (int, float)) and v < t.nota_min:
                    x.font = Font(color="DC2626", bold=True)
                if eh_rodape:
                    x.font = Font(bold=True)
                    x.fill = cinza
                medir(c, v)
        for c, w in larg.items():
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape" if len(t.colunas) > 8 else "portrait"
        ws.page_setup.fitToWidth = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToHeight = 0

    resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    wb.save(resp)
    return resp