"""Views do processo de avaliação - II Ciclo (Angola)."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from app.db.models import (AvaliacaoContinua, Disciplina, Exame, HistoricoNota, Matricula,
                     PlanoCurricular, ResultadoAnual, ResultadoTrimestral, Trimestre, Turma,
                     AtribuicaoDocente)
from app.avaliacao.services.regras_avaliacao import decidir_situacao_final, obter_regra, percentagem_faltas_injustificadas, recalcular_anual
from ..db.decorators import role_required


# ---------------------------------------------------------------- helpers

def _turmas_permitidas(user):
    if user.is_staff:
        return Turma.objects.select_related("curso", "ano_lectivo")
    return (Turma.objects.filter(atribuicaodocente__professor__utilizador=user)
            .select_related("curso", "ano_lectivo").distinct())


def _turma_ou_403(user, turma_id):
    return get_object_or_404(_turmas_permitidas(user), pk=turma_id)


def _disciplinas_permitidas(user, turma):
    if user.is_staff:
        ids = PlanoCurricular.objects.filter(curso=turma.curso, classe=turma.classe).values("disciplina")
        return AtribuicaoDocente.objects.filter(disciplina_id__in=ids).order_by("disciplina__nome")
    return AtribuicaoDocente.objects.filter(professor__utilizador=user,
                                            turma=turma).order_by("disciplina__nome")


def _disciplina_ou_403(user, turma, disciplina_id):
    
    return get_object_or_404(_disciplinas_permitidas(user, turma), disciplina_id=disciplina_id)


def _matriculas_activas(turma):
    return (Matricula.objects.filter(turma=turma, status=Matricula.Status.ACTIVA)
            .select_related("aluno").order_by( "aluno__nome_completo"))


def _parse_nota(valor):
    valor = (valor or "").strip().replace(",", ".")
    if valor == "":
        return None
    try:
        n = Decimal(valor)
    except InvalidOperation:
        raise ValueError(f"valor inválido '{valor}'")
    if not (0 <= n <= 20):
        raise ValueError("a nota deve estar entre 0 e 20")
    return n


def _historico(user, obj, campo, antes, depois, motivo=""):
    if antes != depois:
        HistoricoNota.objects.create(
            modelo=obj.__class__.__name__, objecto_id=obj.pk, campo=campo,
            valor_anterior="" if antes is None else str(antes),
            valor_novo="" if depois is None else str(depois),
            motivo=motivo, utilizador=user)


def _verificar_trimestre_aberto(request, trimestre):
    if not trimestre.lancamento_aberto and not request.user.is_superuser:
        raise PermissionDenied("O lançamento de notas está fechado para este trimestre.")


# ---------------------------------------------------------------- páginas
@login_required
@role_required('professord')
def turmas(request):
    return render(request, "avaliacao/turmas.html", {"turmas": _turmas_permitidas(request.user)})


@login_required
def turma_detalhe(request, turma_id):
    turma = _turma_ou_403(request.user, turma_id)
    return render(request, "avaliacao/turma_detalhe.html", {
        "turma": turma,
        "disciplinas": _disciplinas_permitidas(request.user, turma),
        "trimestres": Trimestre.objects.filter(ano_lectivo=turma.ano_lectivo),
        "n_alunos": _matriculas_activas(turma).count(),
    })


@login_required
def lancar_notas(request, turma_id, disciplina_id, trimestre_id):
    """Lançamento de PP e PT (o MAC vem das avaliações contínuas; a MT é automática)."""
    turma = _turma_ou_403(request.user, turma_id)
   
    disciplina = _disciplina_ou_403(request.user, turma, disciplina_id)
    trimestre = get_object_or_404(Trimestre, pk=trimestre_id, ano_lectivo=turma.ano_lectivo)
    matriculas = list(_matriculas_activas(turma))
    existentes = {r.matricula_id: r for r in ResultadoTrimestral.objects.filter(
        matricula__in=matriculas, disciplina=disciplina.disciplina, trimestre=trimestre)}
    erros = []

    if request.method == "POST":
        _verificar_trimestre_aberto(request, trimestre)
        dados = []
        for m in matriculas:
            try:
                dados.append((m, _parse_nota(request.POST.get(f"pp_{m.id}")),
                              _parse_nota(request.POST.get(f"pt_{m.id}"))))
            except ValueError as e:
                erros.append(f"{m.aluno.nome_completo}: {e}")
        if not erros:
            with transaction.atomic():
                for m, pp, pt in dados:
                    r, _ = ResultadoTrimestral.objects.get_or_create(
                        matricula=m, disciplina=disciplina.disciplina, trimestre=trimestre)
                    _historico(request.user, r, "pp", r.pp, pp)
                    _historico(request.user, r, "pt", r.pt, pt)
                    r.pp, r.pt, r.lancado_por = pp, pt, request.user
                    r.save()
            messages.success(request, "Notas guardadas e médias recalculadas.")
            return redirect(request.path)
        for e in erros:
            messages.error(request, e)

    linhas = [{"m": m, "r": existentes.get(m.id)} for m in matriculas]
    return render(request, "avaliacao/lancar_notas.html", {
        "turma": turma, "disciplina": disciplina.disciplina, "trimestre": trimestre, "linhas": linhas})


@login_required
def lancar_continua(request, turma_id, disciplina_id, trimestre_id):
    """Cria uma avaliação contínua (teste/trabalho/...) para toda a turma de uma só vez."""
    turma = _turma_ou_403(request.user, turma_id)
    disciplina = _disciplina_ou_403(request.user, turma, disciplina_id)
    trimestre = get_object_or_404(Trimestre, pk=trimestre_id, ano_lectivo=turma.ano_lectivo)
    matriculas = list(_matriculas_activas(turma))

    if request.method == "POST":
        _verificar_trimestre_aberto(request, trimestre)
        tipo = request.POST.get("tipo", AvaliacaoContinua.Tipo.TESTE)
        if tipo not in AvaliacaoContinua.Tipo.values:
            tipo = AvaliacaoContinua.Tipo.OUTRO
        data = request.POST.get("data") or timezone.localdate().isoformat()
        descricao = request.POST.get("descricao", "")[:150]
        novos, erros = [], []
        for m in matriculas:
            try:
                n = _parse_nota(request.POST.get(f"nota_{m.id}"))
            except ValueError as e:
                erros.append(f"{m.aluno.nome_completo}: {e}")
                continue
            if n is not None:
                novos.append(AvaliacaoContinua(matricula=m, disciplina=disciplina.disciplina, trimestre=trimestre,
                                               tipo=tipo, descricao=descricao, data=data, valor=n,
                                               lancado_por=request.user))
        if erros:
            for e in erros:
                messages.error(request, e)
        else:
            with transaction.atomic():
                for a in novos:
                    a.save()  # o sinal recalcula MAC, MT, MFD
            messages.success(request, f"{len(novos)} notas de avaliação contínua lançadas.")
            return redirect("avaliacao:lancar_notas", turma.id, disciplina.disciplina.id, trimestre.id)

    return render(request, "avaliacao/lancar_continua.html", {
        "turma": turma, "disciplina": disciplina.disciplina, "trimestre": trimestre,
        "matriculas": matriculas, "tipos": AvaliacaoContinua.Tipo.choices,
        "hoje": timezone.localdate().isoformat()})


@login_required
def lancar_exame(request, turma_id, disciplina_id):
    turma = _turma_ou_403(request.user, turma_id)
    disciplina = _disciplina_ou_403(request.user, turma, disciplina_id)
    if not PlanoCurricular.objects.filter(curso=turma.curso, classe=turma.classe, disciplina=disciplina.disciplina,
                                          tem_exame_nacional=True).exists():
        raise PermissionDenied("Esta disciplina não tem exame nacional nesta classe.")
    matriculas = list(_matriculas_activas(turma))

    if request.method == "POST":
        tipo = request.POST.get("tipo", Exame.Tipo.NACIONAL)
        if tipo not in Exame.Tipo.values:
            tipo = Exame.Tipo.NACIONAL
        data = request.POST.get("data") or None
        dados, erros = [], []
        for m in matriculas:
            try:
                n = _parse_nota(request.POST.get(f"nota_{m.id}"))
            except ValueError as e:
                erros.append(f"{m.aluno.nome_completo}: {e}")
                continue
            if n is not None:
                dados.append((m, n))
        if erros:
            for e in erros:
                messages.error(request, e)
        else:
            with transaction.atomic():
                for m, n in dados:
                    ex, _ = Exame.objects.get_or_create(matricula=m, disciplina=disciplina.disciplina, tipo=tipo,
                                                        defaults={"data": data})
                    _historico(request.user, ex, "nota", ex.nota, n)
                    ex.nota, ex.data = n, data or ex.data
                    ex.save()
            messages.success(request, "Notas de exame guardadas.")
            return redirect("avaliacao:turma_detalhe", turma.id)

    return render(request, "avaliacao/lancar_exame.html", {
        "turma": turma, "disciplina": disciplina.disciplina, "matriculas": matriculas,
        "tipos": Exame.Tipo.choices})


@login_required
def pauta_trimestral(request, turma_id, trimestre_id):
    turma = _turma_ou_403(request.user, turma_id)
    trimestre = get_object_or_404(Trimestre, pk=trimestre_id, ano_lectivo=turma.ano_lectivo)
    disciplinas = list(Disciplina.objects.filter(
        planocurricular__curso=turma.curso, planocurricular__classe=turma.classe).order_by("nome"))
    regra = obter_regra(turma.ano_lectivo, turma.classe)
    res = {(r.matricula_id, r.disciplina_id): r for r in ResultadoTrimestral.objects.filter(
        matricula__turma=turma, trimestre=trimestre)}
    linhas = []
    for m in _matriculas_activas(turma):
        notas = [res.get((m.id, d.id)) for d in disciplinas]
        negativas = sum(1 for r in notas if r and r.mt is not None and r.mt < regra.nota_minima_positiva)
        linhas.append({"m": m, "notas": notas, "negativas": negativas})
    return render(request, "avaliacao/pauta_trimestral.html", {
        "turma": turma, "trimestre": trimestre, "disciplinas": disciplinas, "linhas": linhas})


@login_required
def pauta_final(request, turma_id):
    turma = _turma_ou_403(request.user, turma_id)
    disciplinas = list(Disciplina.objects.filter(
        planocurricular__curso=turma.curso, planocurricular__classe=turma.classe).order_by("nome"))
    res = {(r.matricula_id, r.disciplina_id): r for r in ResultadoAnual.objects.filter(
        matricula__turma=turma)}
    linhas = [{"m": m, "notas": [res.get((m.id, d.id)) for d in disciplinas]}
              for m in _matriculas_activas(turma)]
    return render(request, "avaliacao/pauta_final.html", {
        "turma": turma, "disciplinas": disciplinas, "linhas": linhas})


@login_required
@require_POST
def calcular_resultados(request, turma_id):
    """Recalcula notas finais e decide aprovado/reprovado (apenas coordenação/secretaria)."""
    if not request.user.is_staff:
        raise PermissionDenied
    turma = get_object_or_404(Turma, pk=turma_id)
    disciplinas = Disciplina.objects.filter(planocurricular__curso=turma.curso,
                                            planocurricular__classe=turma.classe)
    with transaction.atomic():
        for m in _matriculas_activas(turma):
            for d in disciplinas:
                recalcular_anual(m, d)
            decidir_situacao_final(m)
    messages.success(request, "Resultados finais calculados.")
    return redirect("avaliacao:pauta_final", turma.id)


@login_required
def boletim(request, matricula_id):
    matricula = get_object_or_404(Matricula.objects.select_related("aluno", "turma__curso", "ano_lectivo"),
                                  pk=matricula_id)
    _turma_ou_403(request.user, matricula.turma_id)
    disciplinas = Disciplina.objects.filter(planocurricular__curso=matricula.turma.curso,
                                            planocurricular__classe=matricula.turma.classe).order_by("nome")
    rt = {(r.disciplina_id, r.trimestre.designacao): r for r in matricula.resultados_trimestrais.select_related("trimestre")}
    ra = {r.disciplina_id: r for r in matricula.resultados_anuais.all()}
    linhas = [{"d": d, "t1": rt.get((d.id, 1)), "t2": rt.get((d.id, 2)), "t3": rt.get((d.id, 3)),
               "anual": ra.get(d.id)} for d in disciplinas]
    return render(request, "avaliacao/boletim.html", {
        "m": matricula, "linhas": linhas,
        "faltas_pct": round(percentagem_faltas_injustificadas(matricula), 1)})