from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ConsultaForm, PreInscricaoForm
from app.db.models import AnoLectivo, Candidato, Inscricao, TenantConfiguracao

SESSION_CANDIDATO = "portal_candidato_id"
SESSION_TENTATIVAS = "portal_tentativas"
MAX_TENTATIVAS = 5

ETAPAS = ["Pré-inscrição recebida", "Em análise", "Resultado"]
PASSO_POR_STATUS = {
    Inscricao.Status.ATIVA: 1,
    Inscricao.Status.APROVADA: 3,
    Inscricao.Status.REPROVADA: 3,
}


def _config():
    return TenantConfiguracao.objects.first()


def _inscricao_aberta(config, ano):
    return bool(config and config.periodo_inscricao and ano)


def _serializar(insc):
    passo = PASSO_POR_STATUS.get(insc.status, 2)
    nota = None
    if passo == 3:
        n = insc.nota_admissao.first()
        nota = str(n.nota) if n else None
    return {
        "id": str(insc.id),
        "protocolo": insc.id.hex[:8].upper(),
        "curso": insc.curso.nome,
        "periodo": insc.periodo.get_designacao_display(),
        "ano_lectivo": str(insc.ano_lectivo),
        "data": insc.data_inscricao.strftime("%d/%m/%Y"),
        "status": insc.status,
        "status_label": insc.get_status_display(),
        "passo": passo,
        "nota": nota,
    }


def home(request):
    config = _config()
    ano = AnoLectivo.objects.filter(e_atual=True).first()
    return render(request, "portal_candidato/home.html", {
        "config": config, "ano": ano,
        "aberta": _inscricao_aberta(config, ano),
        "form": ConsultaForm(),
    })


@require_http_methods(["GET", "POST"])
def pre_inscricao(request):
    config = _config()
    ano = AnoLectivo.objects.filter(e_atual=True).first()
    if not _inscricao_aberta(config, ano):
        return render(request, "portal_candidato/fechado.html", {"config": config})

    form = PreInscricaoForm(request.POST or None, ano_lectivo=ano)
    if request.method == "POST" and form.is_valid():
        insc = form.save()
        request.session[SESSION_CANDIDATO] = str(insc.candidato_id)
        return redirect("candidato:sucesso", pk=insc.pk)
    return render(request, "portal_candidato/pre_inscricao.html", {"config": config, "ano": ano, "form": form})


def sucesso(request, pk):
    insc = get_object_or_404(Inscricao.objects.select_related("candidato", "curso", "periodo"), pk=pk)
    if request.session.get(SESSION_CANDIDATO) != str(insc.candidato_id):
        return redirect("candidato:home")
    return render(request, "portal_candidato/sucesso.html", {"config": _config(), "insc": _serializar(insc),
                                                   "candidato": insc.candidato})


@require_http_methods(["GET", "POST"])
def consultar(request):
    config = _config()
    form = ConsultaForm(request.POST or None)
    erro = None
    if request.method == "POST":
        if request.session.get(SESSION_TENTATIVAS, 0) >= MAX_TENTATIVAS:
            erro = "Demasiadas tentativas. Tente novamente mais tarde ou contacte a secretaria."
        elif form.is_valid():
            cand = Candidato.objects.filter(
                bi=form.cleaned_data["bi"], data_nascimento=form.cleaned_data["data_nascimento"]
            ).first()
            if cand and cand.inscricoes.exists():
                request.session[SESSION_CANDIDATO] = str(cand.pk)
                request.session[SESSION_TENTATIVAS] = 0
                return redirect("candidato:acompanhar")
            request.session[SESSION_TENTATIVAS] = request.session.get(SESSION_TENTATIVAS, 0) + 1
            erro = "Não encontrámos nenhuma candidatura com estes dados. Verifique o BI e a data de nascimento."
    return render(request, "portal_candidato/consultar.html", {"config": config, "form": form, "erro": erro})


def _candidato_da_sessao(request):
    pk = request.session.get(SESSION_CANDIDATO)
    return Candidato.objects.filter(pk=pk).first() if pk else None


def acompanhar(request):
    cand = _candidato_da_sessao(request)
    if not cand:
        return redirect("candidato:consultar")
    inscricoes = cand.inscricoes.select_related("curso", "periodo", "ano_lectivo").order_by("-data_inscricao")
    return render(request, "portal_candidato/acompanhar.html", {
        "config": _config(), "candidato": cand, "etapas": ETAPAS,
        "inscricoes": [_serializar(i) for i in inscricoes],
    })


@require_GET
def api_progresso(request):
    cand = _candidato_da_sessao(request)
    if not cand:
        return JsonResponse({"erro": "sessão expirada"}, status=403)
    qs = cand.inscricoes.select_related("curso", "periodo", "ano_lectivo")
    return JsonResponse({"inscricoes": [_serializar(i) for i in qs]})


def sair(request):
    request.session.pop(SESSION_CANDIDATO, None)
    return redirect("candidato:home")
