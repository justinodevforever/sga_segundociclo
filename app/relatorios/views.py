from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.contrib import messages
from collections import OrderedDict
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import slugify

from app.db.models import Aluno, AnoLectivo, Diretor, LogAuditoria
import csv
from collections import defaultdict
from django.apps import apps
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.urls import reverse
from django.utils.dateparse import parse_date

from app.financa.models import (
    MESES, STATUS_CONTA, STATUS_PROPINA,
    ConfiguracaoFinanceira, ContaAluno, LogFinanceiro, Pagamento, PropinaMensal,
)

from .documentos import DOCUMENTOS, DocumentoErro
from .forms import FiltroRelatorioForm
from .reports import REGISTO
from .utils import escola, exportar_xlsx, render_pdf
 
from .services import pauta_final as svc
 

from app.db.models import (  # <- ajustar (ex.: from app.core.models import ...)
    AnoLectivo, AtribuicaoDocente, Diretor, Disciplina, Matricula,
    PlanoCurricular, RegraAvaliacao, ResultadoAnual, ResultadoTrimestral,
    Role, Trimestre, Turma, UsuarioRole, Classe,Curso
)

ROMANOS = {1: "I", 2: "II", 3: "III"}
D = Decimal

# Regra usada quando a escola ainda não configurou RegraAvaliacao para a classe.
REGRA_PADRAO = SimpleNamespace(
    nota_minima_positiva=D("10"), nota_maxima=D("20"),
    peso_mac=D("1"), peso_pp=D("1"), peso_pt=D("1"),
    arredondar_unidades=True,
    peso_exame_na_nota_final=D("0.50"), nota_minima_exame=D("10"),
    max_negativas_transicao=2, classe_exame_exige_todas_positivas=True,
    limite_faltas_injustificadas_pct=D("30"),
)

TITULO_CICLO = {
    "GERAL": "IIº Ciclo do Ensino Secundário Geral",
    "TECNICO": "IIº Ciclo do Ensino Secundário Técnico-Profissional",
    "PEDAGOGICO": "IIº Ciclo do Ensino Secundário – Formação de Professores",
}

PAPEIS_GESTAO = {Role.NomeRole.ADMIN, Role.NomeRole.DIRECTOR, Role.NomeRole.SECRETARIO}


# ---------------------------------------------------------------- permissões
def _papeis(user):
    return set(
        UsuarioRole.objects.filter(utilizador=user, role__is_active=True)
        .values_list("role__nome", flat=True)
    )


def _escopo(user):
    """('total', None) para gestão; ('professor', Funcionario) para docentes."""
    if user.is_superuser:
        return "total", None
    papeis = _papeis(user)
    if papeis & PAPEIS_GESTAO:
        return "total", None
    if Role.NomeRole.PROFESSOR in papeis:
        func = getattr(user, "funcionario", None)
        if func:
            return "professor", func
    raise PermissionDenied


def _autorizar(user, turma, disciplina):
    tipo, func = _escopo(user)
    if tipo == "total":
        return
    if not AtribuicaoDocente.objects.filter(
        professor=func, turma=turma, disciplina=disciplina
    ).exists():
        raise PermissionDenied


# ---------------------------------------------------------------- formatação
def _arredondar(v, regra):
    if v is None:
        return None
    v = D(v)
    if regra.arredondar_unidades:
        return v.quantize(D("1"), rounding=ROUND_HALF_UP)  # 0,5 sobe
    return v.quantize(D("0.01"))


def _txt(v):
    if v is None:
        return ""
    if v == v.to_integral_value():
        return f"{v:.0f}"
    return f"{v:.2f}".replace(".", ",")


def _cel(valor, regra, media=True):
    """Prepara uma célula: texto, valor numérico e flag de negativa."""
    q = _arredondar(valor, regra) if media else (D(valor) if valor is not None else None)
    return {
        "v": q,
        "txt": _txt(q),
        "neg": q is not None and q < regra.nota_minima_positiva,
    }


def _media(valores):
    valores = [v for v in valores if v is not None]
    return sum(valores) / len(valores) if valores else None


# ---------------------------------------------------------------- estatística
def _estatistica(pares, minimo):
    """pares = [(valor|None, genero)] -> contagens HM / F."""
    av = [(v, g) for v, g in pares if v is not None]
    pos = [(v, g) for v, g in av if v >= minimo]
    neg = [(v, g) for v, g in av if v < minimo]
    f = lambda lst: sum(1 for _, g in lst if g == "F")
    media = _media([v for v, _ in av])
    return {
        "aval": len(av), "aval_f": f(av),
        "pos": len(pos), "pos_f": f(pos),
        "neg": len(neg), "neg_f": f(neg),
        "pct": f"{len(pos) / len(av) * 100:.1f}".replace(".", ",") if av else "—",
        "media": f"{media:.1f}".replace(".", ",") if media is not None else "—",
    }


# ---------------------------------------------------------------- selecção

ROLES_PERMITIDAS = {"admin", "director", "secretario"}


def acesso_relatorios(view):
    @wraps(view)
    def _w(request, *a, **kw):
        u = request.user
        if not (u.is_superuser or u.usuario_roles.filter(
                role__nome__in=ROLES_PERMITIDAS, role__is_active=True).exists()):
            raise PermissionDenied
        return view(request, *a, **kw)
    return login_required(_w)


def _log(request, accao, descricao):
    """Regista a emissão/exportação no LogAuditoria (nunca bloqueia o relatório)."""
    try:
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR") or "0.0.0.0")
        LogAuditoria.objects.create(
            utilizador=request.user, accao=accao, modulo=LogAuditoria.Modulo.SISTEMA, descricao=descricao,
            ip_address=ip, user_agent=request.META.get("HTTP_USER_AGENT", "")[:500], objeto_tipo="relatorio")
    except Exception:
        pass


def _ctx_pdf(request, titulo, orientacao):
    return {"escola": escola(), "orientacao": orientacao, "titulo": titulo, "utilizador": request.user,
            "emitido_em": timezone.localtime(), "diretor": Diretor.objects.filter(status="Activo").first()}


# --------------------------------------------------------------------------
@acesso_relatorios
def index(request):
    grupos = OrderedDict()
    for m in REGISTO.values():
        grupos.setdefault(m.grupo, []).append(m)
    docs = [dict(slug=k, **{x: v[x] for x in ("titulo", "icone", "desc")}) for k, v in DOCUMENTOS.items()]
    return render(request, "relatorios/index.html", {"grupos": grupos, "documentos": docs, "secao": "relatorios",
                                                      "total": len(REGISTO) + len(DOCUMENTOS)})


@acesso_relatorios
def relatorio(request, slug):
    meta = REGISTO.get(slug)
    if not meta:
        raise Http404
    formato = request.GET.get("formato", "html")
    ano_atual = AnoLectivo.objects.filter(e_atual=True).first()
    dados = request.GET.copy()
    if ano_atual and "ano_lectivo" in meta.filtros and not dados.get("ano_lectivo"):
        dados["ano_lectivo"] = str(ano_atual.pk)
    tem_consulta = any(k not in ("formato", "ano_lectivo") and v for k, v in request.GET.items())
    kw = dict(campos=meta.filtros, obrigatorios=meta.obrigatorios, rotulos=meta.rotulos)

    form, rel = FiltroRelatorioForm(dados, **kw), None
    if form.is_valid():
        f = dict(form.cleaned_data)
        if f.get("turma"):
            f["ano_lectivo"] = f["turma"].ano_lectivo
        rel = meta.fn(f)
        rel.filtros_txt = form.resumo()
    elif not tem_consulta:
        form = FiltroRelatorioForm(initial={"ano_lectivo": ano_atual}, **kw)

    if rel and formato in ("pdf", "xlsx"):
        nome = f"{slug}-{timezone.localdate():%Y%m%d}"
        if formato == "xlsx":
            if not meta.excel:
                raise Http404
            _log(request, LogAuditoria.Accao.EXPORTAR, f"Exportou Excel: {meta.titulo}. {rel.filtros_txt}")
            return exportar_xlsx(rel, escola(), nome)
        _log(request, LogAuditoria.Accao.IMPRIMIR, f"Gerou PDF: {meta.titulo}. {rel.filtros_txt}")
        ctx = _ctx_pdf(request, rel.titulo, rel.orient)
        ctx.update(rel=rel, subtitulo=rel.subtitulo, filtros=rel.filtros_txt, fonte=7 if rel.max_colunas > 14 else 8)
        return render_pdf(request, "relatorios/pdf/tabular.html", ctx, nome, inline=not request.GET.get("download"))

    qs = dados.copy()
    qs.pop("formato", None)
    return render(request, "relatorios/report.html", {"meta": meta, "form": form, "rel": rel, "qs": qs.urlencode(),
                                                       "secao": "relatorios", "tem_consulta": tem_consulta})


@acesso_relatorios
def documento(request, tipo):
    doc = DOCUMENTOS.get(tipo)
    if not doc:
        raise Http404
    ano_atual = AnoLectivo.objects.filter(e_atual=True).first()
    dados = request.GET.copy()
    if ano_atual and "ano_lectivo" in doc["campos"] and not dados.get("ano_lectivo"):
        dados["ano_lectivo"] = str(ano_atual.pk)
    tem = any(k not in ("ano_lectivo", "download") and v for k, v in request.GET.items())
    kw = dict(campos=doc["campos"], obrigatorios=doc["obrigatorios"])
    form, erro, aluno_nome = FiltroRelatorioForm(dados, **kw), None, ""

    if tem and form.is_valid():
        f = dict(form.cleaned_data)
        if f.get("aluno"):
            aluno_nome = f["aluno"].nome_completo
        if f.get("turma"):
            f["ano_lectivo"] = f["turma"].ano_lectivo
        try:
            template, ctx, orient = doc["fn"](f)
        except DocumentoErro as e:
            erro = str(e)
        else:
            ctx.update(_ctx_pdf(request, doc["titulo"], orient))
            nome = slugify(f"{tipo}-{aluno_nome or ''}") or tipo
            _log(request, LogAuditoria.Accao.IMPRIMIR, f"Gerou PDF: {doc['titulo']} {aluno_nome}".strip())
            return render_pdf(request, template, ctx, nome, inline=not request.GET.get("download"))
    elif not tem:
        form = FiltroRelatorioForm(initial={"ano_lectivo": ano_atual}, **kw)
    return render(request, "relatorios/documento.html", {"doc": doc, "tipo": tipo, "form": form, "erro": erro,
                                                          "aluno_nome": aluno_nome, "secao": "relatorios"})


@acesso_relatorios
def api_alunos(request):
    termo = request.GET.get("term", "").strip()
    qs = Aluno.objects.none()
    if len(termo) >= 2:
        qs = Aluno.objects.filter(
            Q(nome_completo__icontains=termo) | Q(numero_processo__icontains=termo) |
            Q(numero_estudante__icontains=termo) | Q(bi__icontains=termo)).order_by("nome_completo")[:15]
    return JsonResponse([{"id": str(a.pk), "value": a.nome_completo,
                          "label": f"{a.nome_completo} - Proc. {a.numero_processo or '-'}"} for a in qs], safe=False)
    
@login_required
@require_GET
def mini_pauta_selecao(request):
    """Passo 1: escolher ano lectivo/turma; Passo 2: escolher disciplina."""
    tipo, func = _escopo(request.user)

    anos = AnoLectivo.objects.order_by("-data_inicio")
    ano_id = request.GET.get("ano")
    ano = (
        anos.filter(pk=ano_id).first() if ano_id
        else anos.filter(e_atual=True).first() or anos.first()
    )

    turmas = Turma.objects.filter(ano_lectivo=ano, activo=True).select_related("curso", "classe")
    if tipo == "professor":
        turmas = turmas.filter(atribuicaodocente__professor=func).distinct()
    turmas = turmas.order_by("classe__designacao", "curso__nome", "designacao")

    turma, disciplinas = None, []
    turma_id = request.GET.get("turma")
    if turma_id:
        turma = get_object_or_404(turmas, pk=turma_id)
        if tipo == "professor":
            disciplinas = Disciplina.objects.filter(
                atribuicaodocente__professor=func, atribuicaodocente__turma=turma
            ).distinct()
        else:
            disciplinas = Disciplina.objects.filter(
                pk__in=PlanoCurricular.objects.filter(
                    curso=turma.curso, classe=turma.classe
                ).values("disciplina")
            )
        disciplinas = disciplinas.order_by("nome")

    return render(request, "relatorios/mini_pauta_selecao.html", {
        "anos": anos, "ano": ano, "turmas": turmas,'secao': 'mini_pauta',
        "turma": turma, "disciplinas": disciplinas,
    })


@login_required
@require_GET
def mini_pauta(request, turma_id, disciplina_id):
    turma = get_object_or_404(
        Turma.objects.select_related("ano_lectivo", "curso", "classe"), pk=turma_id
    )
    disciplina = get_object_or_404(Disciplina, pk=disciplina_id)
    _autorizar(request.user, turma, disciplina)

    # --- filtro de trimestre (?t=1|2|3|todos)
    sel = request.GET.get("t", "todos")
    if sel not in {"1", "2", "3"}:
        sel = "todos"
    visiveis = [int(sel)] if sel != "todos" else [1, 2, 3]

    # --- regras e plano curricular
    regra = (
        RegraAvaliacao.objects.filter(ano_lectivo=turma.ano_lectivo, classe=turma.classe).first()
        or REGRA_PADRAO
    )
    plano = PlanoCurricular.objects.filter(
        curso=turma.curso, classe=turma.classe, disciplina=disciplina
    ).first()
    tem_exame = bool(plano and plano.tem_exame_nacional)
    usa_pp = regra.peso_pp > 0
    minimo = regra.nota_minima_positiva

    # --- alunos
    matriculas = list(
        Matricula.objects.filter(turma=turma, ano_lectivo=turma.ano_lectivo)
        .exclude(status=Matricula.Status.CANCELADA)
        .select_related("aluno")
        .order_by("aluno__nome_completo")
    )
    ids = [m.pk for m in matriculas]

    # --- trimestres e notas (3 consultas no total)
    tri_map = {t.designacao: t for t in Trimestre.objects.filter(ano_lectivo=turma.ano_lectivo)}
    trim = {
        (r.matricula_id, r.trimestre.designacao): r
        for r in ResultadoTrimestral.objects.filter(
            matricula_id__in=ids, disciplina=disciplina
        ).select_related("trimestre")
    }
    anual = {
        r.matricula_id: r
        for r in ResultadoAnual.objects.filter(matricula_id__in=ids, disciplina=disciplina)
    }

    # --- construção das linhas
    linhas = []
    colunas_stats = {f"mt{d}": [] for d in visiveis}
    colunas_stats["cf"], colunas_stats["mf"] = [], []

    for n, m in enumerate(matriculas, start=1):
        genero = m.aluno.genero
        ra = anual.get(m.pk)

        slots, mts = [], {}
        for d in (1, 2, 3):
            r = trim.get((m.pk, d))
            mts[d] = r.mt if r else None
            if d in visiveis:
                slots.append({
                    "mac": _cel(r.mac if r else None, regra),
                    "pp": _cel(r.pp if r else None, regra, media=False),
                    "pt": _cel(r.pt if r else None, regra, media=False),
                    "mt": _cel(r.mt if r else None, regra),
                })
                colunas_stats[f"mt{d}"].append((slots[-1]["mt"]["v"], genero))

        # CF
        cf = ra.mfd if ra and ra.mfd is not None else (
            _media(list(mts.values())) if all(v is not None for v in mts.values()) else None
        )
        cf_cel = _cel(cf, regra)

        # EE e MF
        ee = ra.nota_exame if ra else None
        ee_cel = _cel(ee, regra, media=False)
        if ra and ra.nota_final is not None:
            mf = ra.nota_final
        elif not tem_exame:
            mf = cf
        elif cf is not None and ee is not None:
            p = D(regra.peso_exame_na_nota_final)
            mf = D(cf) * (1 - p) + D(ee) * p
        else:
            mf = None
        mf_cel = _cel(mf, regra)

        # Observação
        st = m.status
        if st == Matricula.Status.TRANSFERIDA:
            obs = "Transferido"
        elif st == Matricula.Status.DESISTENTE:
            obs = "Desistente"
        elif st == Matricula.Status.TRANCAMENTO:
            obs = "Trancado"
        elif ra and ra.situacao != ResultadoAnual.Situacao.PENDENTE:
            obs = ra.get_situacao_display()
        elif mf_cel["v"] is not None:
            obs = "Apto" if not mf_cel["neg"] else "N/Apto"
        elif tem_exame and cf_cel["v"] is not None and not cf_cel["neg"]:
            obs = "Admitido a exame"
        else:
            obs = ""

        colunas_stats["cf"].append((cf_cel["v"], genero))
        colunas_stats["mf"].append((mf_cel["v"], genero))

        linhas.append({
            "n": n, "matricula": m, "aluno": m.aluno,
            "inactivo": st != Matricula.Status.ACTIVA,
            "slots": slots, "cf": cf_cel, "ee": ee_cel, "mf": mf_cel, "obs": obs,
        })

    # --- cabeçalhos dinâmicos dos trimestres
    cab_trim = []
    for d in visiveis:
        t = tri_map.get(d)
        cab_trim.append({
            "rotulo": f"{ROMANOS[d]} Trimestre",
            "aberto": bool(t and t.lancamento_aberto),
            "existe": t is not None,
        })
    provisoria = any(c["aberto"] or not c["existe"] for c in cab_trim)

    # --- estatísticas por coluna
    estat_cols = [
        {"rotulo": f"MT{d}", "s": _estatistica(colunas_stats[f"mt{d}"], minimo)} for d in visiveis
    ]
    if sel == "todos":
        estat_cols.append({"rotulo": "CF", "s": _estatistica(colunas_stats["cf"], minimo)})
        estat_cols.append({"rotulo": "MF", "s": _estatistica(colunas_stats["mf"], minimo)})

    # --- docente, director, escola
    atrib = (
        AtribuicaoDocente.objects.filter(turma=turma, disciplina=disciplina)
        .select_related("professor").first()
    )
    director = Diretor.objects.filter(status=Diretor.Status.ACTIVO).first()

    total_f = sum(1 for l in linhas if l["aluno"].genero == "F")

    ctx = {
        "turma": turma, "disciplina": disciplina, "regra": regra, "plano": plano,
        "tem_exame": tem_exame, "usa_pp": usa_pp,
        "colspan_tri": 3 + (1 if usa_pp else 0),
        "titulo_ciclo": TITULO_CICLO.get(turma.curso.tipo, TITULO_CICLO["GERAL"]),
        "classe_txt": f"{turma.classe.designacao}.ª",
        "professor": atrib.professor.nome_completo if atrib else "",
        "director": director.nome_completo if director else "",
        "escola": getattr(settings, "ESCOLA_NOME", ""),
        "escola_local": getattr(settings, "ESCOLA_LOCALIDADE", "Luanda"),
        "cab_trim": cab_trim, "linhas": linhas, "sel": sel,
        "mostrar_final": sel == "todos",
        "provisoria": provisoria,
        "estat_cols": estat_cols,
        "total_alunos": len(linhas), "total_f": total_f,
        "emitido_em": timezone.localtime(),
        "utilizador": request.user.nome_completo or request.user.username,
    }
    return render(request, "relatorios/mini_pauta.html", ctx)


@login_required
def pauta_final_lista(request):
    """Lista de turmas do ano lectivo, filtráveis por curso e classe."""
    ano_id = request.GET.get("ano")
    ano = (AnoLectivo.objects.filter(pk=ano_id).first() if ano_id
           else AnoLectivo.objects.filter(e_atual=True).first() or AnoLectivo.objects.order_by("-data_inicio").first())
 
    turmas = Turma.objects.none()
    if ano:
        turmas = (Turma.objects.filter(ano_lectivo=ano, activo=True)
                  .select_related("curso", "classe", "ano_lectivo")
                  .order_by("classe__ordem", "curso__nome", "designacao"))
        if request.GET.get("curso"):
            turmas = turmas.filter(curso_id=request.GET["curso"])
        if request.GET.get("classe"):
            turmas = turmas.filter(classe_id=request.GET["classe"])
 
    return render(request, "relatorios/pauta_final_lista.html", {
        "ano": ano,
        'secao': 'pauta_final',
        "anos": AnoLectivo.objects.order_by("-data_inicio"),
        "cursos": Curso.objects.filter(activo=True).order_by("nome"),
        "classes": Classe.objects.order_by("ordem"),
        "turmas": turmas,
        "publicada": svc.pauta_publicada(ano) if ano else False,
    })
 
 
@login_required
def pauta_final_turma(request, turma_id):
    """Pauta final de uma turma: nota por disciplina, Apto/N-Apto e situação do aluno."""
    turma = get_object_or_404(
        Turma.objects.select_related("curso", "classe", "ano_lectivo"), pk=turma_id)
 
    if not svc.pauta_publicada(turma.ano_lectivo):
        messages.warning(
            request,
            "A pauta final ainda não foi publicada: o lançamento do 3.º trimestre continua aberto.")
        return redirect("pauta_final_lista")
 
    disciplinas, resultados, regra = svc.gerar_pauta(turma)
 
    filtro = request.GET.get("situacao")
    if filtro:
        resultados = [r for r in resultados if r.situacao == filtro]
    pesquisa = (request.GET.get("q") or "").strip().lower()
    if pesquisa:
        resultados = [r for r in resultados
                      if pesquisa in r.matricula.aluno.nome_completo.lower()]
 
    return render(request, "relatorios/pauta_final_turma.html", {
        "turma": turma,
        "disciplinas": disciplinas,
        "resultados": resultados,
        "regra": regra,
        'secao': 'pauta_final',
        "resumo": svc.resumo(resultados),
        "terminal": int(turma.classe.designacao) >= svc.classe_terminal(turma),
        "situacoes": [(k, svc.ROTULOS[k]) for k in (
            svc.TRANSITA, svc.CONCLUIU, svc.APROVADO, svc.ADMITIDO_EXAME,
            svc.ADMITIDO_RECURSO, svc.NAO_TRANSITA, svc.REPROVADO, svc.REPROVADO_FALTAS)],
        "filtro": filtro or "",
        "q": request.GET.get("q", ""),
    })
    

ZERO = Decimal('0')
METODOS = [
    ('dinheiro', 'Dinheiro'), ('transferencia', 'Transferência Bancária'),
    ('multicaixa', 'Multicaixa'), ('cheque', 'Cheque'),
]
NOME_MES = dict(MESES)
TAG_PROPINA = {'pago': 'tag-green', 'pendente': 'tag-yellow', 'atrasado': 'tag-red'}
LABEL_PROPINA = dict(STATUS_PROPINA)


# ───────────────────────── helpers ─────────────────────────
def _soma(qs, campo='valor'):
    return qs.aggregate(t=Sum(campo))['t'] or ZERO


def _ano(request):
    """Devolve (ano_seleccionado|None=todos, queryset de anos)."""
    #AnoLectivo = apps.get_model('db', 'AnoLectivo')
    anos = AnoLectivo.objects.order_by('-data_inicio')
    pk = request.GET.get('ano')
    if pk == 'todos':
        return None, anos
    ano = anos.filter(pk=pk).first() if pk  else None
    return (ano or anos.first()), anos


def _data(request, chave):
    v = request.GET.get(chave)
    return parse_date(v) if v else None


def _contas(request):
    """Contas filtradas por ano lectivo, pesquisa e status."""
    ano, anos = _ano(request)
    qs = ContaAluno.objects.select_related('aluno', 'ano_lectivo')
    if ano:
        qs = qs.filter(ano_lectivo=ano)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(aluno__nome_completo__icontains=q)
    st = request.GET.get('status')
    if st in dict(STATUS_CONTA):
        qs = qs.filter(status=st)
    return qs, ano, anos


def _pagamentos(request):
    ano, anos = _ano(request)
    qs = Pagamento.objects.select_related('conta_aluno__aluno', 'registado_por')
    for  q in qs:
        print(q.conta_aluno.ano_lectivo, ano)
    if ano:
        qs = qs.filter(conta_aluno__ano_lectivo=ano)
        
    ini, fim = _data(request, 'inicio'), _data(request, 'fim')
    if ini:
        qs = qs.filter(data_pagamento__gte=ini)
    if fim:
        qs = qs.filter(data_pagamento__lte=fim)
    m = request.GET.get('metodo')
    if m in dict(METODOS):
        qs = qs.filter(metodo_pagamento=m)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(numero_recibo__icontains=q) | Q(referencia__icontains=q) |
            Q(conta_aluno__aluno__nome_completo__icontains=q))
    return qs, ano, anos


def _plain(v, t):
    if v is None:
        return ''
    if t in ('tag', 'link'):
        return v[0]
    if t == 'data':
        return v.strftime('%d/%m/%Y')
    if t == 'kz':
        return f'{v:.2f}'.replace('.', ',')
    return v


def _csv(nome, colunas, linhas, tipos):
    r = HttpResponse(content_type='text/csv; charset=utf-8')
    r['Content-Disposition'] = f'attachment; filename="{nome}_{timezone.localdate():%Y%m%d}.csv"'
    r.write('\ufeff')
    w = csv.writer(r, delimiter=';')
    w.writerow(colunas)
    for l in linhas:
        w.writerow([_plain(v, t) for v, t in zip(l, tipos)])
    return r


def _grafico(gid, tipo, titulo, labels, datasets):
    return {'id': gid, 'tipo': tipo, 'titulo': titulo, 'labels': labels,
            'datasets': [{'label': l, 'data': [float(x) for x in d]} for l, d in datasets]}


def _render(request, *, titulo, sub, icone, nome, colunas=None, tipos=None,
            linhas=None, rodape=None, cards=None, graficos=None, filtros=(),
            tabela_titulo=None, extra=None):
    if request.GET.get('export') == 'csv' and linhas is not None:
        return _csv(nome, colunas, linhas, tipos)
    ano, anos = _ano(request)
    params = request.GET.copy()
    params.pop('export', None)
    ctx = {
        'secao': 'relatorios_financa', 'titulo': titulo, 'subtitulo': sub, 'icone': icone,
        'colunas': colunas, 'cards': cards or [], 'graficos': graficos or [],
        'filtros': filtros, 'tabela_titulo': tabela_titulo,
        'ano': ano, 'anos': anos, 'qs': params.urlencode(),
        'METODOS': METODOS, 'STATUS_CONTA': STATUS_CONTA,
        'STATUS_PROPINA': STATUS_PROPINA, 'MESES': MESES,
        'ACOES': LogFinanceiro.ACOES, 'hoje': timezone.localdate(),
    }
    if linhas is not None:
        ctx['linhas'] = [list(zip(l, tipos)) for l in linhas]
        ctx['total_linhas'] = len(linhas)
        if rodape:
            ctx['rodape'] = list(zip(rodape, tipos))
    if extra:
        ctx.update(extra)
    return render(request, 'financeiro/relatorios/relatorio.html', ctx)


def _tag_conta(c):
    return (c.get_status_display(), c.status_display_class)


def _tag_propina(p):
    return (LABEL_PROPINA.get(p.status, p.status), TAG_PROPINA.get(p.status, 'tag-gray'))


# ───────────────────────── índice ─────────────────────────
@login_required
def index_financa(request):
    grupos = [
        ('Visão Geral', 'bi-speedometer2', [
            ('Resumo Financeiro', 'rel_resumo', 'Indicadores gerais, gráficos e maiores devedores.', 'bi-graph-up-arrow'),
            ('Comparativo entre Anos Lectivos', 'rel_comparativo', 'Evolução de valores devidos, cobrados e taxa de cobrança.', 'bi-bar-chart-steps'),
        ]),
        ('Receitas e Caixa', 'bi-cash-stack', [
            ('Pagamentos Recebidos', 'rel_pagamentos', 'Listagem de recibos com filtros por período e método.', 'bi-receipt'),
            ('Caixa Diário', 'rel_caixa', 'Fecho de caixa de um dia, por método de pagamento.', 'bi-safe2'),
            ('Receita Mensal', 'rel_receita_mensal', 'Total arrecadado mês a mês, com acumulado.', 'bi-calendar-month'),
            ('Receita por Método', 'rel_por_metodo', 'Distribuição entre dinheiro, multicaixa, transferência e cheque.', 'bi-credit-card-2-front'),
            ('Pagamentos por Funcionário', 'rel_por_funcionario', 'Quem registou quantos pagamentos e que valor.', 'bi-person-workspace'),
        ]),
        ('Dívidas e Cobrança', 'bi-exclamation-triangle', [
            ('Alunos Devedores', 'rel_devedores', 'Todas as contas com saldo em dívida.', 'bi-person-x'),
            ('Maiores Devedores', 'rel_top_devedores', 'Os 20 maiores saldos devedores.', 'bi-sort-numeric-down-alt'),
            ('Contas Bloqueadas', 'rel_bloqueados', 'Alunos bloqueados (sem exames/matrícula).', 'bi-lock-fill'),
            ('Contas por Estado', 'rel_por_status', 'Quantidade e valores por estado da conta.', 'bi-pie-chart'),
            ('Antiguidade da Dívida', 'rel_aging', 'Dívida vencida por faixas: 0-30, 31-60, 61-90 e +90 dias.', 'bi-hourglass-split'),
        ]),
        ('Propinas', 'bi-calendar-check', [
            ('Propinas em Atraso', 'rel_propinas_atraso', 'Propinas vencidas e não pagas, com dias de atraso.', 'bi-clock-history'),
            ('Mapa de Propinas por Mês', 'rel_mapa_propinas', 'Previsto vs. cobrado em cada mês.', 'bi-table'),
            ('Matriz de Propinas por Aluno', 'rel_matriz_propinas', 'Grelha aluno × mês com o estado de cada propina.', 'bi-grid-3x3-gap'),
            ('Previsão de Receita', 'rel_previsao', 'Valores a receber nos próximos meses.', 'bi-bullseye'),
        ]),
        ('Aluno e Auditoria', 'bi-shield-check', [
            ('Extrato do Aluno', 'rel_extrato_lista', 'Extrato completo (propinas + pagamentos) de um aluno.', 'bi-file-earmark-person'),
            ('Log Financeiro', 'rel_log', 'Histórico de acções registadas no módulo.', 'bi-journal-text'),
            ('Auditoria de Consistência', 'rel_auditoria', 'Detecta contas com valores incoerentes ou sem propinas.', 'bi-clipboard2-check'),
        ]),
    ]
    return render(request, 'financeiro/relatorios/index.html',
                  {'secao': 'relatorios_financa', 'grupos': grupos})


# ───────────────────────── visão geral ─────────────────────────
@login_required
def resumo(request):
    contas, ano, _ = _contas(request)
    hoje = timezone.localdate()
    devido, pago = _soma(contas, 'total_devido'), _soma(contas, 'total_pago')
    saldo = _soma(contas, 'saldo_devedor')
    taxa = int(pago / devido * 100) if devido else 0
    pags, _, _ = _pagamentos(request)
    props = PropinaMensal.objects.filter(conta_aluno__in=contas)
    atrasadas = props.filter(Q(status='atrasado') | Q(status='pendente', data_vencimento__lt=hoje))
    valor_atraso = _soma(atrasadas.annotate(
        s=F('valor') - F('valor_pago')), 's') if atrasadas.exists() else ZERO
    cards = [
        ('Total Esperado', devido, 'kz', 'blue', 'bi-bullseye'),
        ('Total Cobrado', pago, 'kz', 'green', 'bi-cash-coin'),
        ('Saldo Devedor', saldo, 'kz', 'warn', 'bi-exclamation-circle'),
        ('Taxa de Cobrança', taxa, 'pct', 'purple', 'bi-percent'),
        ('Contas', contas.count(), 'num', 'cyan', 'bi-people'),
        ('Em Atraso / Bloqueadas', contas.filter(status__in=['atrasado', 'bloqueado']).count(), 'num', 'warn', 'bi-flag'),
        ('Propinas Vencidas (Kz)', valor_atraso, 'kz', 'warn', 'bi-clock-history'),
        ('Recebido Hoje', _soma(Pagamento.objects.filter(data_pagamento=hoje)), 'kz', 'green', 'bi-calendar-day'),
        ('Recebido este Mês', _soma(Pagamento.objects.filter(
            data_pagamento__year=hoje.year, data_pagamento__month=hoje.month)), 'kz', 'cyan', 'bi-calendar-month'),
    ]
    mensal = (pags.annotate(m=TruncMonth('data_pagamento')).values('m')
              .annotate(t=Sum('valor')).order_by('m'))
    por_status = contas.values('status').annotate(n=Count('id'))
    nomes_status = dict(STATUS_CONTA)
    por_metodo = pags.values('metodo_pagamento').annotate(t=Sum('valor'))
    nomes_metodo = dict(METODOS)
    graficos = [
        _grafico('g-mensal', 'bar', 'Receita mensal (Kz)',
                 [m['m'].strftime('%m/%Y') for m in mensal], [('Receita', [m['t'] for m in mensal])]),
        _grafico('g-status', 'doughnut', 'Contas por estado',
                 [nomes_status[s['status']] for s in por_status], [('Contas', [s['n'] for s in por_status])]),
        _grafico('g-metodo', 'pie', 'Receita por método',
                 [nomes_metodo.get(m['metodo_pagamento'], m['metodo_pagamento']) for m in por_metodo],
                 [('Kz', [m['t'] for m in por_metodo])]),
    ]
    top = contas.filter(saldo_devedor__gt=0).order_by('-saldo_devedor')[:10]
    tipos = ['txt', 'kz', 'kz', 'kz', 'tag']
    linhas = [[c.aluno.nome_completo, c.total_devido, c.total_pago, c.saldo_devedor, _tag_conta(c)] for c in top]
    return _render(request, titulo='Resumo Financeiro', sub='Indicadores gerais do ano lectivo',
                   icone='bi-graph-up-arrow', nome='resumo_financeiro',
                   colunas=['Aluno', 'Devido', 'Pago', 'Saldo', 'Estado'], tipos=tipos, linhas=linhas,
                   cards=cards, graficos=graficos, filtros=('ano',), tabela_titulo='Top 10 devedores')


@login_required
def comparativo(request):
    AnoLectivo = apps.get_model('db', 'AnoLectivo')
    linhas, labels, d_dev, d_pag = [], [], [], []
    for a in AnoLectivo.objects.order_by('data_inicio'):
        c = ContaAluno.objects.filter(ano_lectivo=a)
        dev, pag, sal = _soma(c, 'total_devido'), _soma(c, 'total_pago'), _soma(c, 'saldo_devedor')
        linhas.append([str(a), c.count(), dev, pag, sal, int(pag / dev * 100) if dev else 0,
                       c.filter(status='bloqueado').count()])
        labels.append(str(a)); d_dev.append(dev); d_pag.append(pag)
    return _render(request, titulo='Comparativo entre Anos Lectivos', sub='Devido vs. cobrado por ano',
                   icone='bi-bar-chart-steps', nome='comparativo_anos',
                   colunas=['Ano Lectivo', 'Contas', 'Devido', 'Pago', 'Saldo', 'Taxa Cobrança', 'Bloqueadas'],
                   tipos=['txt', 'num', 'kz', 'kz', 'kz', 'pct', 'num'], linhas=linhas,
                   graficos=[_grafico('g-comp', 'bar', 'Devido vs. Pago', labels,
                                      [('Devido', d_dev), ('Pago', d_pag)])])


# ───────────────────────── receitas e caixa ─────────────────────────
@login_required
def pagamentos(request):
    qs, _, _ = _pagamentos(request)
    linhas = [[p.numero_recibo, p.data_pagamento, p.conta_aluno.aluno.nome_completo,
               p.get_metodo_pagamento_display(), p.referencia or '—',
               getattr(p.registado_por, 'nome_completo', '—'), p.valor,
               ('Recibo', reverse('rel_recibo', args=[p.pk]))] for p in qs]
    total = _soma(qs)
    return _render(request, titulo='Pagamentos Recebidos', sub='Recibos emitidos no período',
                   icone='bi-receipt', nome='pagamentos',
                   colunas=['Recibo', 'Data', 'Aluno', 'Método', 'Referência', 'Registado por', 'Valor', ''],
                   tipos=['txt', 'data', 'txt', 'txt', 'txt', 'txt', 'kz', 'link'],
                   linhas=linhas, rodape=['Total', '', '', '', '', '', total, ''],
                   cards=[('Total Recebido', total, 'kz', 'green', 'bi-cash-coin'),
                          ('Nº de Pagamentos', len(linhas), 'num', 'blue', 'bi-receipt')],
                   filtros=('ano', 'periodo', 'metodo', 'q'))


@login_required
def caixa_diario(request):
    dia = _data(request, 'dia') or timezone.localdate()
    qs = Pagamento.objects.filter(data_pagamento=dia).select_related('conta_aluno__aluno', 'registado_por')
    linhas = [[p.numero_recibo, p.conta_aluno.aluno.nome_completo, p.get_metodo_pagamento_display(),
               getattr(p.registado_por, 'nome_completo', '—'), p.valor] for p in qs.order_by('data_criacao')]
    por_m = {m: _soma(qs.filter(metodo_pagamento=m)) for m, _ in METODOS}
    cards = [('Total do Dia', _soma(qs), 'kz', 'green', 'bi-safe2'), ('Recibos', len(linhas), 'num', 'blue', 'bi-receipt')]
    cores = ['cyan', 'purple', 'warn', 'blue']
    cards += [(n, por_m[m], 'kz', cores[i], 'bi-wallet2') for i, (m, n) in enumerate(METODOS)]
    return _render(request, titulo='Caixa Diário', sub=f'Fecho de caixa — {dia:%d/%m/%Y}',
                   icone='bi-safe2', nome=f'caixa_{dia:%Y%m%d}',
                   colunas=['Recibo', 'Aluno', 'Método', 'Registado por', 'Valor'],
                   tipos=['txt', 'txt', 'txt', 'txt', 'kz'], linhas=linhas,
                   rodape=['Total', '', '', '', _soma(qs)], cards=cards, filtros=('dia',),
                   extra={'dia': dia})


@login_required
def receita_mensal(request):
    qs, _, _ = _pagamentos(request)
    dados = qs.annotate(m=TruncMonth('data_pagamento')).values('m').annotate(
        t=Sum('valor'), n=Count('id')).order_by('m')
    linhas, acum = [], ZERO
    for d in dados:
        acum += d['t']
        linhas.append([d['m'].strftime('%m/%Y'), d['n'], d['t'], acum])
        print(dados, linhas)
    return _render(request, titulo='Receita Mensal', sub='Total arrecadado por mês',
                   icone='bi-calendar-month', nome='receita_mensal',
                   colunas=['Mês', 'Nº Pagamentos', 'Total', 'Acumulado'],
                   tipos=['txt', 'num', 'kz', 'kz'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), acum, ''],
                   graficos=[_grafico('g-rm', 'line', 'Receita mensal (Kz)',
                                      [l[0] for l in linhas], [('Receita', [l[2] for l in linhas])])],
                   filtros=('ano',))


@login_required
def por_metodo(request):
    qs, _, _ = _pagamentos(request)
    total = _soma(qs)
    nomes = dict(METODOS)
    dados = qs.values('metodo_pagamento').annotate(t=Sum('valor'), n=Count('id')).order_by('-t')
    linhas = [[nomes.get(d['metodo_pagamento'], d['metodo_pagamento']), d['n'], d['t'],
               int(d['t'] / total * 100) if total else 0] for d in dados]
    return _render(request, titulo='Receita por Método de Pagamento', sub='Distribuição das receitas',
                   icone='bi-credit-card-2-front', nome='receita_por_metodo',
                   colunas=['Método', 'Nº Pagamentos', 'Total', '% do Total'],
                   tipos=['txt', 'num', 'kz', 'pct'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), total, ''],
                   graficos=[_grafico('g-met', 'doughnut', 'Por método',
                                      [l[0] for l in linhas], [('Kz', [l[2] for l in linhas])])],
                   filtros=('ano', 'periodo'))


@login_required
def por_funcionario(request):
    qs, _, _ = _pagamentos(request)
    dados = qs.values('registado_por__nome_completo').annotate(t=Sum('valor'), n=Count('id')).order_by('-t')
    linhas = [[d['registado_por__nome_completo'] or '— (removido/sistema)', d['n'], d['t'],
               d['t'] / d['n'] if d['n'] else ZERO] for d in dados]
    return _render(request, titulo='Pagamentos por Funcionário', sub='Produtividade do registo de pagamentos',
                   icone='bi-person-workspace', nome='pagamentos_por_funcionario',
                   colunas=['Funcionário', 'Nº Pagamentos', 'Total Registado', 'Média por Pagamento'],
                   tipos=['txt', 'num', 'kz', 'kz'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), sum((l[2] for l in linhas), ZERO), ''],
                   filtros=('ano', 'periodo'))


# ───────────────────────── dívidas ─────────────────────────
def _linhas_contas(qs):
    return [[c.aluno.nome_completo, str(c.ano_lectivo), c.total_devido, c.total_pago, c.saldo_devedor,
             c.percentagem_pago, _tag_conta(c), ('Extrato', reverse('rel_extrato', args=[c.pk]))] for c in qs]


COLS_CONTAS = ['Aluno', 'Ano Lectivo', 'Devido', 'Pago', 'Saldo', '% Pago', 'Estado', '']
TIPOS_CONTAS = ['txt', 'txt', 'kz', 'kz', 'kz', 'pct', 'tag', 'link']


@login_required
def devedores(request):
    qs, _, _ = _contas(request)
    qs = qs.filter(saldo_devedor__gt=0).order_by('-saldo_devedor')
    total = _soma(qs, 'saldo_devedor')
    return _render(request, titulo='Alunos Devedores', sub='Contas com saldo em dívida',
                   icone='bi-person-x', nome='devedores', colunas=COLS_CONTAS, tipos=TIPOS_CONTAS,
                   linhas=_linhas_contas(qs), rodape=['Total', '', _soma(qs, 'total_devido'),
                                                      _soma(qs, 'total_pago'), total, '', '', ''],
                   cards=[('Dívida Total', total, 'kz', 'warn', 'bi-exclamation-circle'),
                          ('Alunos Devedores', qs.count(), 'num', 'blue', 'bi-people')],
                   filtros=('ano', 'status', 'q'))


@login_required
def top_devedores(request):
    qs, _, _ = _contas(request)
    qs = qs.filter(saldo_devedor__gt=0).order_by('-saldo_devedor')[:20]
    linhas = _linhas_contas(qs)
    return _render(request, titulo='Maiores Devedores', sub='Top 20 por saldo em dívida',
                   icone='bi-sort-numeric-down-alt', nome='top_devedores',
                   colunas=COLS_CONTAS, tipos=TIPOS_CONTAS, linhas=linhas,
                   graficos=[_grafico('g-top', 'bar', 'Saldo devedor (Kz)',
                                      [l[0][:22] for l in linhas], [('Saldo', [l[4] for l in linhas])])],
                   filtros=('ano',))


@login_required
def bloqueados(request):
    qs, _, _ = _contas(request)
    qs = qs.filter(status='bloqueado').order_by('-saldo_devedor')
    return _render(request, titulo='Contas Bloqueadas', sub='Sem direito a exames nem matrícula',
                   icone='bi-lock-fill', nome='contas_bloqueadas',
                   colunas=COLS_CONTAS, tipos=TIPOS_CONTAS, linhas=_linhas_contas(qs),
                   rodape=['Total', '', _soma(qs, 'total_devido'), _soma(qs, 'total_pago'),
                           _soma(qs, 'saldo_devedor'), '', '', ''],
                   filtros=('ano', 'q'))


@login_required
def por_status(request):
    ano, _ = _ano(request)
    qs = ContaAluno.objects.all()
    if ano:
        qs = qs.filter(ano_lectivo=ano)
    linhas = []
    for cod, nome in STATUS_CONTA:
        c = qs.filter(status=cod)
        linhas.append([(nome, {'em_dia': 'tag-green', 'pendente': 'tag-yellow',
                               'atrasado': 'tag-red', 'bloqueado': 'tag-red'}[cod]),
                       c.count(), _soma(c, 'total_devido'), _soma(c, 'total_pago'), _soma(c, 'saldo_devedor')])
    return _render(request, titulo='Contas por Estado', sub='Situação financeira dos alunos',
                   icone='bi-pie-chart', nome='contas_por_estado',
                   colunas=['Estado', 'Nº Contas', 'Devido', 'Pago', 'Saldo'],
                   tipos=['tag', 'num', 'kz', 'kz', 'kz'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), sum((l[2] for l in linhas), ZERO),
                           sum((l[3] for l in linhas), ZERO), sum((l[4] for l in linhas), ZERO)],
                   graficos=[_grafico('g-st', 'doughnut', 'Contas por estado',
                                      [l[0][0] for l in linhas], [('Contas', [l[1] for l in linhas])])],
                   filtros=('ano',))


@login_required
def aging(request):
    contas, _, _ = _contas(request)
    hoje = timezone.localdate()
    props = (PropinaMensal.objects.filter(conta_aluno__in=contas, data_vencimento__lt=hoje)
             .exclude(status='pago').select_related('conta_aluno__aluno'))
    faixas = ['0-30 dias', '31-60 dias', '61-90 dias', '+90 dias']
    por_aluno, totais = defaultdict(lambda: [ZERO] * 4), [ZERO] * 4
    for p in props:
        dias = (hoje - p.data_vencimento).days
        i = 0 if dias <= 30 else 1 if dias <= 60 else 2 if dias <= 90 else 3
        s = p.saldo_propina
        if s > 0:
            por_aluno[p.conta_aluno.aluno.nome_completo][i] += s
            totais[i] += s
    linhas = sorted(([n, *v, sum(v, ZERO)] for n, v in por_aluno.items()), key=lambda l: -l[5])
    cores = ['green', 'cyan', 'warn', 'purple']
    return _render(request, titulo='Antiguidade da Dívida', sub='Propinas vencidas por faixa de atraso',
                   icone='bi-hourglass-split', nome='antiguidade_divida',
                   colunas=['Aluno', *faixas, 'Total'], tipos=['txt'] + ['kz'] * 5, linhas=linhas,
                   rodape=['Total', *totais, sum(totais, ZERO)],
                   cards=[(f, totais[i], 'kz', cores[i], 'bi-clock') for i, f in enumerate(faixas)],
                   graficos=[_grafico('g-ag', 'bar', 'Dívida por faixa (Kz)', faixas, [('Valor', totais)])],
                   filtros=('ano', 'q'))


# ───────────────────────── propinas ─────────────────────────
@login_required
def propinas_atraso(request):
    contas, _, _ = _contas(request)
    hoje = timezone.localdate()
    qs = (PropinaMensal.objects.filter(conta_aluno__in=contas)
          .filter(Q(status='atrasado') | Q(status='pendente', data_vencimento__lt=hoje))
          .select_related('conta_aluno__aluno').order_by('data_vencimento'))
    mes = request.GET.get('mes')
    if mes and mes.isdigit():
        qs = qs.filter(mes=int(mes))
    linhas = [[p.conta_aluno.aluno.nome_completo, NOME_MES.get(p.mes), p.data_vencimento, p.valor,
               p.valor_pago, p.saldo_propina, (hoje - p.data_vencimento).days, _tag_propina(p)] for p in qs]
    return _render(request, titulo='Propinas em Atraso', sub='Propinas vencidas e não liquidadas',
                   icone='bi-clock-history', nome='propinas_atraso',
                   colunas=['Aluno', 'Mês', 'Vencimento', 'Valor', 'Pago', 'Em Falta', 'Dias de Atraso', 'Estado'],
                   tipos=['txt', 'txt', 'data', 'kz', 'kz', 'kz', 'num', 'tag'], linhas=linhas,
                   rodape=['Total', '', '', sum((l[3] for l in linhas), ZERO), sum((l[4] for l in linhas), ZERO),
                           sum((l[5] for l in linhas), ZERO), '', ''],
                   filtros=('ano', 'mes', 'q'))


@login_required
def mapa_propinas(request):
    contas, _, _ = _contas(request)
    dados = (PropinaMensal.objects.filter(conta_aluno__in=contas).values('mes')
             .annotate(prev=Sum('valor'), cob=Sum('valor_pago'), n=Count('id'),
                       pagas=Count('id', filter=Q(status='pago')),
                       pend=Count('id', filter=Q(status='pendente')),
                       atr=Count('id', filter=Q(status='atrasado'))).order_by('mes'))
    linhas = [[NOME_MES.get(d['mes']), d['n'], d['pagas'], d['pend'], d['atr'], d['prev'], d['cob'],
               d['prev'] - d['cob'], int(d['cob'] / d['prev'] * 100) if d['prev'] else 0] for d in dados]
    return _render(request, titulo='Mapa de Propinas por Mês', sub='Previsto vs. cobrado',
                   icone='bi-table', nome='mapa_propinas',
                   colunas=['Mês', 'Propinas', 'Pagas', 'Pendentes', 'Atrasadas', 'Previsto', 'Cobrado', 'Em Falta', '% Cobrança'],
                   tipos=['txt', 'num', 'num', 'num', 'num', 'kz', 'kz', 'kz', 'pct'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), sum(l[2] for l in linhas), sum(l[3] for l in linhas),
                           sum(l[4] for l in linhas), sum((l[5] for l in linhas), ZERO),
                           sum((l[6] for l in linhas), ZERO), sum((l[7] for l in linhas), ZERO), ''],
                   graficos=[_grafico('g-mp', 'bar', 'Previsto vs. Cobrado (Kz)', [l[0] for l in linhas],
                                      [('Previsto', [l[5] for l in linhas]), ('Cobrado', [l[6] for l in linhas])])],
                   filtros=('ano',))


@login_required
def matriz_propinas(request):
    contas, _, _ = _contas(request)
    contas = contas.prefetch_related('propinas').order_by('aluno__nome_completo')
    linhas = []
    for c in contas:
        por_mes = {p.mes: p for p in c.propinas.all()}
        linha = [c.aluno.nome_completo]
        for cod, _ in MESES:
            p = por_mes.get(cod)
            linha.append(_tag_propina(p) if p else ('—', 'tag-gray'))
        linhas.append(linha)
    return _render(request, titulo='Matriz de Propinas por Aluno', sub='Estado de cada propina, mês a mês',
                   icone='bi-grid-3x3-gap', nome='matriz_propinas',
                   colunas=['Aluno', *[n[:3] for _, n in MESES]], tipos=['txt'] + ['tag'] * len(MESES),
                   linhas=linhas, filtros=('ano', 'q'))


@login_required
def previsao(request):
    contas, _, _ = _contas(request)
    hoje = timezone.localdate()
    abertas = PropinaMensal.objects.filter(conta_aluno__in=contas).exclude(status='pago')
    falta = F('valor') - F('valor_pago')
    vencidas = abertas.filter(data_vencimento__lt=hoje)
    linhas = [['Já vencido (em atraso)', vencidas.count(),
               vencidas.aggregate(t=Sum(falta, output_field=DecimalField()))['t'] or ZERO]]
    futuras = (abertas.filter(data_vencimento__gte=hoje).annotate(m=TruncMonth('data_vencimento'))
               .values('m').annotate(n=Count('id'), t=Sum(falta, output_field=DecimalField())).order_by('m'))
    linhas += [[d['m'].strftime('%m/%Y'), d['n'], d['t']] for d in futuras]
    return _render(request, titulo='Previsão de Receita', sub='Valores a receber por mês de vencimento',
                   icone='bi-bullseye', nome='previsao_receita',
                   colunas=['Período', 'Nº Propinas', 'Valor a Receber'], tipos=['txt', 'num', 'kz'], linhas=linhas,
                   rodape=['Total', sum(l[1] for l in linhas), sum((l[2] for l in linhas), ZERO)],
                   graficos=[_grafico('g-pv', 'bar', 'A receber (Kz)', [l[0] for l in linhas],
                                      [('Valor', [l[2] for l in linhas])])],
                   filtros=('ano',))


@login_required
def extrato_lista(request):
    qs, _, _ = _contas(request)
    return _render(request, titulo='Extrato do Aluno', sub='Procura um aluno e abre o extrato completo',
                   icone='bi-file-earmark-person', nome='contas',
                   colunas=COLS_CONTAS, tipos=TIPOS_CONTAS,
                   linhas=_linhas_contas(qs.order_by('aluno__nome_completo')[:300]),
                   filtros=('ano', 'status', 'q'))

@login_required
def extrato(request, conta_id):
    conta = get_object_or_404(ContaAluno.objects.select_related('aluno', 'ano_lectivo'), pk=conta_id)
    props = conta.propinas.all().order_by('mes')
    pags = conta.pagamentos.select_related('registado_por').order_by('data_pagamento')
    return render(request, 'financeiro/relatorios/extrato.html', {
        'secao': 'relatorios_financa', 'conta': conta, 'hoje': timezone.localdate(),
        'propinas': [(p, _tag_propina(p)) for p in props], 'pagamentos': pags,
        'tag_conta': _tag_conta(conta), 'nome_mes': NOME_MES,
    })


@login_required
def recibo(request, pk):
    p = get_object_or_404(Pagamento.objects.select_related('conta_aluno__aluno', 'conta_aluno__ano_lectivo',
                                                           'registado_por'), pk=pk)
    return render(request, 'financeiro/relatorios/recibo.html',
                  {'p': p, 'qr': p.gerar_qr_code(), 'conta': p.conta_aluno})


@login_required
def log_financeiro(request):
    qs = LogFinanceiro.objects.select_related('conta_aluno__aluno', 'usuario')
    ini, fim = _data(request, 'inicio'), _data(request, 'fim')
    if ini:
        qs = qs.filter(data__date__gte=ini)
    if fim:
        qs = qs.filter(data__date__lte=fim)
    ac = request.GET.get('acao')
    if ac in dict(LogFinanceiro.ACOES):
        qs = qs.filter(acao=ac)
    linhas = [[timezone.localtime(l.data).strftime('%d/%m/%Y %H:%M'), l.get_acao_display(),
               l.conta_aluno.aluno.nome_completo, l.descricao,
               getattr(l.usuario, 'nome_completo', '—')] for l in qs[:500]]
    return _render(request, titulo='Log Financeiro', sub='Últimas 500 acções registadas',
                   icone='bi-journal-text', nome='log_financeiro',
                   colunas=['Data/Hora', 'Acção', 'Aluno', 'Descrição', 'Utilizador'],
                   tipos=['txt'] * 5, linhas=linhas, filtros=('periodo', 'acao'))


@login_required
def auditoria(request):
    contas, _, _ = _contas(request)
    contas = contas.prefetch_related('propinas')
    linhas = []
    for c in contas:
        nome = c.aluno.nome_completo
        real = _soma(c.pagamentos)
        if real != c.total_pago:
            linhas.append([('Total pago incoerente', 'tag-red'), nome,
                           f'Conta: {c.total_pago} Kz · Soma dos recibos: {real} Kz',
                           ('Extrato', reverse('rel_extrato', args=[c.pk]))])
        if not c.propinas.all():
            linhas.append([('Sem propinas geradas', 'tag-yellow'), nome,
                           'Conta sem nenhuma propina mensal.', ('Extrato', reverse('rel_extrato', args=[c.pk]))])
        if c.valor_propina_mensal == 0:
            linhas.append([('Propina mensal = 0', 'tag-yellow'), nome,
                           'Valor mensal não definido.', ('Extrato', reverse('rel_extrato', args=[c.pk]))])
        for p in c.propinas.all():
            if p.valor_pago > p.valor:
                linhas.append([('Propina paga a mais', 'tag-red'), nome,
                               f'{NOME_MES.get(p.mes)}: pago {p.valor_pago} > valor {p.valor}',
                               ('Extrato', reverse('rel_extrato', args=[c.pk]))])
    return _render(request, titulo='Auditoria de Consistência', sub='Contas com valores incoerentes',
                   icone='bi-clipboard2-check', nome='auditoria',
                   colunas=['Problema', 'Aluno', 'Detalhe', ''], tipos=['tag', 'txt', 'txt', 'link'],
                   linhas=linhas, cards=[('Ocorrências', len(linhas), 'num', 'warn', 'bi-flag')],
                   filtros=('ano', 'q'))
