
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import ListView, TemplateView

from app.db.models import (
    Aluno,
    AnoLectivo,
    AtribuicaoDocente,
    AvaliacaoContinua,
    Disciplina,
    Exame,
    Falta,
    Funcionario,
    HorarioAula,
    Matricula,
    PlanoCurricular,
    RegraAvaliacao,
    ResultadoAnual,
    ResultadoTrimestral,
    TenantConfiguracao,
    Trimestre,
    Turma,
)

try:
    from app.db.models import Comunicado
except ImportError:
    Comunicado = None


NOTA_MAXIMA = Decimal("20")
NOTA_POSITIVA = Decimal("10")          
NOTA_ADMISSAO_EXAME = Decimal("7")

TIPOS_PROVA = {"PP": "Prova do Professor", "PT": "Prova Trimestral"}

SITUACOES_APROVADO = (
    ResultadoAnual.Situacao.APROVADO,
    ResultadoAnual.Situacao.APROVADO_EXAME,
)
SITUACOES_REPROVADO = (
    ResultadoAnual.Situacao.REPROVADO,
    ResultadoAnual.Situacao.REPROVADO_EXAME,
)
SITUACOES_EXAME = (
    ResultadoAnual.Situacao.ADMITIDO_EXAME,
    ResultadoAnual.Situacao.AGUARDAR_EXAME,
    ResultadoAnual.Situacao.APROVADO_EXAME,
    ResultadoAnual.Situacao.REPROVADO_EXAME,
)

DIAS_SEMANA = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado"}


def _uuid_ou_none(valor):
    """Converte para UUID; devolve None se inválido (evita ValidationError/500)."""
    if not valor:
        return None
    try:
        return UUID(str(valor))
    except (ValueError, AttributeError, TypeError):
        return None


def _int_ou_none(valor):
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def _parse_data(valor, default=None):
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        return default


def _parse_nota(valor, maximo=NOTA_MAXIMA):
    """Valida e normaliza uma nota. Lança ValueError com mensagem legível."""
    texto = str(valor).strip().replace(",", ".")
    try:
        nota = Decimal(texto)
    except InvalidOperation:
        raise ValueError("Nota inválida.")
    if not nota.is_finite():
        raise ValueError("Nota inválida.")
    if nota < 0 or nota > maximo:
        raise ValueError(f"Nota fora do intervalo [0, {maximo}].")
    return nota.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _tipos_lancamento():
    """Tipos aceites no lançamento: avaliações contínuas + PP + PT."""
    return list(AvaliacaoContinua.Tipo.choices) + list(TIPOS_PROVA.items())


def _rotulo_tipo(tipo):
    return dict(_tipos_lancamento()).get(tipo, tipo)


def _get_ano_atual():
    """Ano lectivo activo: o da configuração da escola ou, em alternativa, e_atual=True."""
    config = TenantConfiguracao.objects.select_related("ano_lectivo_activo").first()
    if config and config.ano_lectivo_activo_id:
        return config.ano_lectivo_activo
    return AnoLectivo.objects.filter(e_atual=True).first()


def _ano_lectivo_activo():
    return _get_ano_atual()


def _trimestre_activo(ano_lectivo=None):
    """Trimestre activo (do ano lectivo indicado, se fornecido) ou None."""
    qs = Trimestre.objects.filter(activo=True)
    if ano_lectivo:
        qs = qs.filter(ano_lectivo=ano_lectivo)
    return qs.order_by("designacao").first()


def _trimestres_do_ano(ano_lectivo):
    qs = Trimestre.objects.all()
    if ano_lectivo:
        qs = qs.filter(ano_lectivo=ano_lectivo)
    return qs.order_by("designacao")


def _nota_minima_turma(turma):
    """Nota mínima positiva definida em RegraAvaliacao (ano + classe); default 10."""
    regra = RegraAvaliacao.objects.filter(
        ano_lectivo_id=turma.ano_lectivo_id, classe_id=turma.classe_id
    ).first()
    return regra.nota_minima_positiva if regra else NOTA_POSITIVA


def _semanas_decorridas(ano_lectivo):
    hoje = timezone.localdate()
    if hoje < ano_lectivo.data_inicio:
        return 0
    semanas = (min(hoje, ano_lectivo.data_fim) - ano_lectivo.data_inicio).days // 7 + 1
    return min(semanas, ano_lectivo.semanas_lectivas)


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSÕES
# ─────────────────────────────────────────────────────────────────────────────

def _obter_professor(user):
    """Devolve o Funcionário-professor activo associado ao utilizador, ou None."""
    if not user.is_authenticated:
        return None
    try:
        funcionario = user.funcionario
    except ObjectDoesNotExist:
        return None
    if funcionario.tipo_funcionario == Funcionario.TipoFuncionario.ADMINISTRATIVO:
        return None
    if funcionario.status in (Funcionario.Status.DEMITIDO, Funcionario.Status.INACTIVO):
        return None
    return funcionario


def _get_professor_or_403(request):
    """Devolve o Funcionário do utilizador ou lança PermissionDenied (403)."""
    professor = getattr(request, "professor", None) or _obter_professor(request.user)
    if professor is None:
        raise PermissionDenied("Acesso reservado a professores.")
    return professor


def _e_pessoal_escola(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return (
        getattr(user, "funcionario", None) is not None
        or getattr(user, "director", None) is not None
    )


def professor_required(view_func):
    """Exige login + utilizador com perfil de professor. Define `request.professor`."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        professor = _obter_professor(request.user)
        if professor is None:
            raise PermissionDenied("Acesso reservado a professores.")
        request.professor = professor
        return view_func(request, *args, **kwargs)
    return login_required(_wrapped)


def pessoal_required(view_func):
    """Exige login + pessoal da escola (funcionário, director ou administrador)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _e_pessoal_escola(request.user):
            raise PermissionDenied("Acesso reservado ao pessoal da escola.")
        return view_func(request, *args, **kwargs)
    return login_required(_wrapped)


def api_professor_required(view_func):
    """Versão JSON de professor_required (401/403 em JSON em vez de redirect)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"erro": "Autenticação necessária."}, status=401)
        professor = _obter_professor(request.user)
        if professor is None:
            return JsonResponse({"erro": "Acesso reservado a professores."}, status=403)
        request.professor = professor
        return view_func(request, *args, **kwargs)
    return _wrapped


class ProfessorRequiredMixin(LoginRequiredMixin):

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.professor = _obter_professor(request.user)
        if self.professor is None:
            return HttpResponseForbidden("Acesso reservado a professores.")
        return super().dispatch(request, *args, **kwargs)

    def get_professor(self):
        return self.professor


def _get_iniciais(request) -> str:
    """Iniciais do utilizador (funcionário, ou nome do utilizador como alternativa)."""
    user = request.user
    funcionario = getattr(user, "funcionario", None)
    nome = (
        getattr(funcionario, "nome_completo", None)
        or getattr(user, "nome_completo", None)
        or user.get_username()
        or ""
    )
    partes = nome.split()
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return f"{partes[0][0]}{partes[-1][0]}".upper()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE CONSULTA
# ─────────────────────────────────────────────────────────────────────────────

def _turmas_do_professor(professor, ano_lectivo=None):
    """AtribuicaoDocente do professor (filtradas por ano lectivo e turmas activas)."""
    qs = AtribuicaoDocente.objects.filter(professor=professor)
    if ano_lectivo:
        qs = qs.filter(turma__ano_lectivo=ano_lectivo, turma__activo=True)
    return (
        qs.select_related("turma", "disciplina", "turma__classe", "turma__curso", "turma__ano_lectivo")
        .order_by("turma__designacao", "disciplina__nome")
    )


def _turmas_distintas(atribuicoes):
    """Turmas (sem repetição, ordem preservada) de um conjunto de atribuições."""
    vistas, turmas = set(), []
    for atr in atribuicoes:
        if atr.turma_id not in vistas:
            vistas.add(atr.turma_id)
            turmas.append(atr.turma)
    return turmas


def _restringir_atribuicoes(qs, atribuicoes, campo_turma, campo_disciplina):
    """
    Limita `qs` aos pares (turma, disciplina) leccionados pelo professor.
    Sem atribuições devolve qs vazio (um Q() vazio devolveria TUDO).
    """
    filtro = Q()
    tem_pares = False
    for turma_id, disciplina_id in atribuicoes.values_list("turma_id", "disciplina_id"):
        filtro |= Q(**{campo_turma: turma_id, campo_disciplina: disciplina_id})
        tem_pares = True
    return qs.filter(filtro) if tem_pares else qs.none()


def _matriculas_activas(turma, ano_lectivo=None):
    return (
        Matricula.objects
        .filter(
            turma=turma,
            ano_lectivo=ano_lectivo or turma.ano_lectivo,
            status=Matricula.Status.ACTIVA,
        )
        .select_related("aluno")
        .order_by("aluno__nome_completo")
    )


def _gravar_nota(*, utilizador, matricula, disciplina, trimestre, tipo, data, descricao, valor):
    """
    Grava uma nota no sítio certo:
      - PP / PT  -> ResultadoTrimestral (o save() recalcula MAC/MT e o anual)
      - restantes -> AvaliacaoContinua  (o signal actualiza o MAC)
    Devolve (objecto, criado).
    """
    if tipo in TIPOS_PROVA:
        rt, criado = ResultadoTrimestral.objects.get_or_create(
            matricula=matricula,
            disciplina=disciplina,
            trimestre=trimestre,
            defaults={"ano_lectivo_id": matricula.ano_lectivo_id, "lancado_por": utilizador},
        )
        setattr(rt, tipo.lower(), valor)
        rt.lancado_por = utilizador
        if rt.ano_lectivo_id is None:
            rt.ano_lectivo_id = matricula.ano_lectivo_id
        rt.save()
        return rt, criado

    return AvaliacaoContinua.objects.update_or_create(
        matricula=matricula,
        disciplina=disciplina,
        trimestre=trimestre,
        tipo=tipo,
        data=data,
        descricao=descricao,
        defaults={
            "valor": valor,
            "lancado_por": utilizador,
            "ano_lectivo_id": matricula.ano_lectivo_id,
        },
    )


def _notas_trimestrais(rt):
    """Dicionário de notas de um ResultadoTrimestral (ou tudo None). npt == pt."""
    if rt is None:
        return {"mac": None, "pp": None, "pt": None, "npt": None, "mt": None}
    return {"mac": rt.mac, "pp": rt.pp, "pt": rt.pt, "npt": rt.pt, "mt": rt.mt}



@professor_required
def dashboard_professor(request):
    professor = request.professor
    ano_lectivo = _get_ano_atual()
    trimestre = _trimestre_activo(ano_lectivo)
    iniciais = _get_iniciais(request)

    atribuicoes = _turmas_do_professor(professor, ano_lectivo)
    turma_ids = set(atribuicoes.values_list("turma_id", flat=True))

    total_alunos = Matricula.objects.filter(
        turma_id__in=turma_ids,
        ano_lectivo=ano_lectivo,
        status=Matricula.Status.ACTIVA,
    ).count()

    # Taxa de aprovação: só resultados das turmas/disciplinas do professor
    resultados = _restringir_atribuicoes(
        ResultadoAnual.objects.filter(matricula__ano_lectivo=ano_lectivo),
        atribuicoes, "matricula__turma_id", "disciplina_id",
    )
    total_resultados = resultados.count()
    aprovados = resultados.filter(situacao__in=SITUACOES_APROVADO).count()
    taxa_aprovacao = round(aprovados / total_resultados * 100) if total_resultados else 0

    # Avaliações contínuas só das turmas/disciplinas do professor
    avaliacoes_do_prof = _restringir_atribuicoes(
        AvaliacaoContinua.objects.filter(matricula__ano_lectivo=ano_lectivo),
        atribuicoes, "matricula__turma_id", "disciplina_id",
    )
    avaliacoes_lancadas = (
        avaliacoes_do_prof.filter(trimestre=trimestre)
        .values("matricula__turma_id", "disciplina_id", "tipo", "data", "descricao")
        .distinct()
        .count()
        if trimestre else 0
    )

    total_disciplinas = atribuicoes.count()
    total_turmas = len(turma_ids)
    notas_pendentes = _calcular_notas_pendentes(atribuicoes, trimestre)
    alertas = _construir_alertas(trimestre, notas_pendentes)
    turmas_activas = _turmas_com_estatisticas(atribuicoes, trimestre)

    # Próximas avaliações (agrupadas: uma linha por avaliação, não por aluno)
    proximas_avaliacoes = list(
        avaliacoes_do_prof
        .filter(data__gte=timezone.localdate())
        .values("data", "tipo", "descricao", "disciplina__nome", "matricula__turma__designacao")
        .annotate(total=Count("id"))
        .order_by("data")[:6]
    )

    return render(request, "dashboard_prof.html", {
        "professor": professor,
        "ano_lectivo": ano_lectivo,
        "trimestre": trimestre,
        "total_turmas": total_turmas,
        "total_alunos": total_alunos,
        "total_disciplinas": total_disciplinas,
        "taxa_aprovacao": taxa_aprovacao,
        "avaliacoes_lancadas": avaliacoes_lancadas,
        "notas_pendentes": notas_pendentes,
        "alertas": alertas,
        "turmas_activas": turmas_activas,
        "proximas_avaliacoes": proximas_avaliacoes,
        "secao": "dashboard",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. MINHAS TURMAS
# ─────────────────────────────────────────────────────────────────────────────

class MinhasTurmasView(ProfessorRequiredMixin, TemplateView):
    """Lista todas as turmas-disciplina atribuídas ao professor no ano lectivo."""
    template_name = "professor/minhas_turmas.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()
        trimestre = _trimestre_activo(ano_lectivo)

        turma_disciplinas = _turmas_do_professor(professor, ano_lectivo)
        avaliacoes = _restringir_atribuicoes(
            AvaliacaoContinua.objects.filter(matricula__ano_lectivo=ano_lectivo),
            turma_disciplinas, "matricula__turma_id", "disciplina_id",
        ).select_related("trimestre", "disciplina", "matricula__aluno")

        ctx.update({
            "professor": professor,
            "avaliacoes": avaliacoes,
            "trimestres": _trimestres_do_ano(ano_lectivo),
            "ano_lectivo": ano_lectivo,
            "trimestre": trimestre,
            "turmas": _turmas_com_estatisticas(turma_disciplinas, trimestre),
            "turma_disciplinas": turma_disciplinas,
            "secao": "minhas_turmas",
            "iniciais": _get_iniciais(self.request),
        })
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 3. AVALIAÇÕES (lista agrupada)
# ─────────────────────────────────────────────────────────────────────────────

class AvaliacoesView(ProfessorRequiredMixin, TemplateView):
    """
    Lista as avaliações lançadas pelo professor. Como AvaliacaoContinua guarda
    uma linha por aluno, as avaliações são agrupadas por
    (turma, disciplina, trimestre, tipo, data, descrição).
    """
    template_name = "professor/avaliacoes.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()
        trimestre_activo = _trimestre_activo(ano_lectivo)

        atribuicoes = _turmas_do_professor(professor, ano_lectivo)
        atribuicao_por_par = {(a.turma_id, a.disciplina_id): a for a in atribuicoes}

        trimestre_id = _uuid_ou_none(self.request.GET.get("trimestre"))
        tipo = self.request.GET.get("tipo")
        if tipo not in AvaliacaoContinua.Tipo.values:
            tipo = None

        qs = _restringir_atribuicoes(
            AvaliacaoContinua.objects.filter(matricula__ano_lectivo=ano_lectivo),
            atribuicoes, "matricula__turma_id", "disciplina_id",
        )
        if trimestre_id:
            qs = qs.filter(trimestre_id=trimestre_id)
        if tipo:
            qs = qs.filter(tipo=tipo)

        grupos = list(
            qs.values("matricula__turma_id", "disciplina_id", "trimestre_id", "tipo", "data", "descricao")
            .annotate(
                notas_lancadas=Count("id"),
                media=Avg("valor"),
                aprovados=Count("id", filter=Q(valor__gte=NOTA_POSITIVA)),
                reprovados=Count("id", filter=Q(valor__lt=NOTA_POSITIVA)),
            )
            .order_by("-data", "disciplina_id")
        )

        turmas = Turma.objects.in_bulk({g["matricula__turma_id"] for g in grupos})
        disciplinas = Disciplina.objects.in_bulk({g["disciplina_id"] for g in grupos})
        trimestres_map = Trimestre.objects.in_bulk({g["trimestre_id"] for g in grupos})
        alunos_por_turma = dict(
            Matricula.objects
            .filter(turma_id__in=turmas.keys(), ano_lectivo=ano_lectivo, status=Matricula.Status.ACTIVA)
            .values_list("turma_id")
            .annotate(total=Count("id"))
        )

        avaliacoes = []
        for g in grupos:
            turma_id = g["matricula__turma_id"]
            total_alunos = alunos_por_turma.get(turma_id, 0)
            lancadas = g["notas_lancadas"]
            atr = atribuicao_por_par.get((turma_id, g["disciplina_id"]))
            stats = {
                "media": round(g["media"] or 0, 1),
                "aprovados": g["aprovados"],
                "reprovados": g["reprovados"],
            } if lancadas else {}

            avaliacoes.append({
                "avaliacao": {
                    "designacao": g["descricao"] or _rotulo_tipo(g["tipo"]),
                    "descricao": g["descricao"],
                    "tipo": g["tipo"],
                    "tipo_display": _rotulo_tipo(g["tipo"]),
                    "data_realizacao": g["data"],
                    "trimestre": trimestres_map.get(g["trimestre_id"]),
                    "turma": turmas.get(turma_id),
                    "disciplina": disciplinas.get(g["disciplina_id"]),
                    "turma_disciplina_id": atr.pk if atr else None,
                    "query": urlencode({
                        "trimestre": g["trimestre_id"], "tipo": g["tipo"],
                        "data": g["data"].isoformat(), "descricao": g["descricao"],
                    }),
                },
                "total_alunos": total_alunos,
                "notas_lancadas": lancadas,
                "progresso": round(lancadas / total_alunos * 100) if total_alunos else 0,
                "status": _status_avaliacao(lancadas, total_alunos, g["data"]),
                "stats": stats,
            })

        ctx.update({
            "professor": professor,
            "ano_lectivo": ano_lectivo,
            "trimestre_activo": trimestre_activo,
            "avaliacoes": avaliacoes,
            "trimestres": _trimestres_do_ano(ano_lectivo),
            "tipos": AvaliacaoContinua.Tipo.choices,
            "filtro_trimestre": str(trimestre_id) if trimestre_id else None,
            "filtro_tipo": tipo,
            "secao": "avaliacoes",
            "iniciais": _get_iniciais(self.request),
        })
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 4. LANÇAMENTO DE NOTAS
# ─────────────────────────────────────────────────────────────────────────────

@professor_required
def avaliacao_lancar_notas(request, turma_disciplina_id):
    """
    Lança notas de uma turma/disciplina para um trimestre.

    Parâmetros (GET ou POST): trimestre, tipo, data, descricao.
      tipo = TESTE | TRAB | PART | PRAT | OUTRO  -> AvaliacaoContinua
      tipo = PP | PT                              -> ResultadoTrimestral
    Campos do formulário por aluno: nota_<matricula_id> e faltou_<matricula_id>.
    """
    professor = request.professor
    iniciais = _get_iniciais(request)

    # Só o professor titular da turma/disciplina pode lançar
    atribuicao = get_object_or_404(
        AtribuicaoDocente.objects.select_related("turma", "turma__ano_lectivo", "turma__classe", "disciplina"),
        pk=turma_disciplina_id, professor=professor,
    )
    turma, disciplina = atribuicao.turma, atribuicao.disciplina
    ano_lectivo = turma.ano_lectivo
    nota_maxima = min(Decimal(turma.valor_maximo or NOTA_MAXIMA), NOTA_MAXIMA)

    def _param(nome, default=""):
        return request.POST.get(nome) or request.GET.get(nome) or default

    trimestres = _trimestres_do_ano(ano_lectivo)
    trimestre = (
        trimestres.filter(pk=_uuid_ou_none(_param("trimestre"))).first()
        or _trimestre_activo(ano_lectivo)
        or trimestres.first()
    )

    tipo = _param("tipo", AvaliacaoContinua.Tipo.TESTE)
    if tipo not in dict(_tipos_lancamento()):
        tipo = AvaliacaoContinua.Tipo.TESTE
    data = _parse_data(_param("data"), timezone.localdate())
    descricao = _param("descricao").strip()[:150]
    if tipo in TIPOS_PROVA:          # provas não têm data/descrição próprias
        descricao = ""

    matriculas = list(_matriculas_activas(turma, ano_lectivo))

    # ── POST: gravar ─────────────────────────────────────────────────────────
    if request.method == "POST":
        if trimestre is None:
            messages.error(request, "Não existe nenhum trimestre configurado para este ano lectivo.")
        elif not trimestre.lancamento_aberto:
            messages.error(request, "O lançamento de notas está fechado para este trimestre.")
        else:
            salvos, erros = 0, []
            with transaction.atomic():
                for m in matriculas:
                    faltou = request.POST.get(f"faltou_{m.pk}") == "on"
                    bruto = request.POST.get(f"nota_{m.pk}", "").strip()

                    if faltou:
                        valor = Decimal("0.00")
                    elif bruto == "":
                        continue                      # campo vazio = não lançar
                    else:
                        try:
                            valor = _parse_nota(bruto, nota_maxima)
                        except ValueError as exc:
                            erros.append(f"{m.aluno.nome_completo}: {exc}")
                            continue

                    _gravar_nota(
                        utilizador=request.user, matricula=m, disciplina=disciplina,
                        trimestre=trimestre, tipo=tipo, data=data,
                        descricao=descricao, valor=valor,
                    )
                    salvos += 1

            if salvos:
                messages.success(request, f"{salvos} notas lançadas/actualizadas com sucesso.")
            for erro in erros:
                messages.warning(request, erro)

        query = urlencode({
            "trimestre": trimestre.pk if trimestre else "", "tipo": tipo,
            "data": data.isoformat(), "descricao": descricao,
        })
        return redirect(f"{request.path}?{query}")

    # ── GET: notas já lançadas ───────────────────────────────────────────────
    if trimestre is None:
        existentes = {}
        messages.warning(request, "Não existe nenhum trimestre configurado para este ano lectivo.")
    elif tipo in TIPOS_PROVA:
        campo = tipo.lower()
        existentes = {
            str(rt.matricula_id): getattr(rt, campo)
            for rt in ResultadoTrimestral.objects.filter(
                matricula__in=matriculas, disciplina=disciplina, trimestre=trimestre
            )
        }
    else:
        existentes = {
            str(av.matricula_id): av.valor
            for av in AvaliacaoContinua.objects.filter(
                matricula__in=matriculas, disciplina=disciplina, trimestre=trimestre,
                tipo=tipo, data=data, descricao=descricao,
            )
        }

    alunos_data = [{"matricula": m, "nota": existentes.get(str(m.pk))} for m in matriculas]

    valores = [v for v in existentes.values() if v is not None]
    total_alunos = len(matriculas)
    total_lancadas = len(valores)
    percentagem = int(total_lancadas / total_alunos * 100) if total_alunos else 0

    stats = {}
    if valores:
        stats = {
            "media": (sum(valores) / len(valores)).quantize(Decimal("0.01")),
            "max": max(valores),
            "min": min(valores),
            "aprovados": sum(1 for v in valores if v >= NOTA_POSITIVA),
            "reprovados": sum(1 for v in valores if v < NOTA_POSITIVA),
        }

    return render(request, "professor/lancar_notas.html", {
        "avaliacao": {
            "designacao": descricao or _rotulo_tipo(tipo),
            "tipo": tipo,
            "tipo_display": _rotulo_tipo(tipo),
            "trimestre": trimestre,
            "data_realizacao": data,
            "descricao": descricao,
            "nota_maxima": nota_maxima,
        },
        "tipos": _tipos_lancamento(),
        "trimestres": trimestres,
        "trimestre": trimestre,
        "tipo": tipo,
        "data": data,
        "descricao": descricao,
        "nota_maxima": nota_maxima,
        "lancamento_aberto": bool(trimestre and trimestre.lancamento_aberto),
        "alunos_data": alunos_data,
        "total_lancadas": total_lancadas,
        "total_alunos": total_alunos,
        "percentagem": percentagem,
        "stats": stats,
        "turma_disciplina": atribuicao,
        "secao": "minhas_turmas",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 5. PAUTA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

@professor_required
def pauta_trimestral(request):
    """Pauta trimestral (só leitura): avaliações contínuas, MAC, PP, PT e MT."""
    professor = request.professor
    ano_lectivo = _get_ano_atual()
    iniciais = _get_iniciais(request)

    atribuicoes = _turmas_do_professor(professor, ano_lectivo)
    turmas = _turmas_distintas(atribuicoes)
    trimestres = _trimestres_do_ano(ano_lectivo).order_by("-designacao")

    turma_id = _uuid_ou_none(request.GET.get("turma"))
    trimestre_id = _uuid_ou_none(request.GET.get("trimestre"))
    disciplina_id = _uuid_ou_none(request.GET.get("disciplina"))

    pauta, avaliacoes = [], []
    turma = trimestre = disciplina = None

    if turma_id and trimestre_id and disciplina_id:
        atribuicao = get_object_or_404(atribuicoes, turma_id=turma_id, disciplina_id=disciplina_id)
        turma, disciplina = atribuicao.turma, atribuicao.disciplina
        trimestre = get_object_or_404(trimestres, pk=trimestre_id)
        minimo = _nota_minima_turma(turma)

        matriculas = list(_matriculas_activas(turma))

        # colunas = avaliações distintas do trimestre
        registos = list(
            AvaliacaoContinua.objects
            .filter(matricula__in=matriculas, disciplina=disciplina, trimestre=trimestre)
            .order_by("data", "tipo", "descricao")
        )
        colunas = []
        for r in registos:
            chave = (r.data, r.tipo, r.descricao)
            if chave not in colunas:
                colunas.append(chave)
        avaliacoes = [
            {"data": d, "tipo": t, "tipo_display": _rotulo_tipo(t), "descricao": desc,
             "designacao": desc or _rotulo_tipo(t)}
            for d, t, desc in colunas
        ]
        valores = {(r.matricula_id, r.data, r.tipo, r.descricao): r.valor for r in registos}

        resultados = {
            rt.matricula_id: rt
            for rt in ResultadoTrimestral.objects.filter(
                matricula__in=matriculas, disciplina=disciplina, trimestre=trimestre
            )
        }

        for idx, m in enumerate(matriculas, 1):
            rt = resultados.get(m.pk)
            notas = _notas_trimestrais(rt)
            mt = notas["mt"]
            pauta.append({
                "numero": idx,
                "matricula": m,
                # lista alinhada com `avaliacoes` (uma célula por coluna)
                "notas": [valores.get((m.pk, d, t, desc)) for d, t, desc in colunas],
                "mac": notas["mac"],
                "pp": notas["pp"],
                "pt": notas["pt"],
                "mt": mt,
                "situacao": "" if mt is None else ("Aprovado" if mt >= minimo else "Reprovado"),
            })

    return render(request, "professor/pauta_trimestral.html", {
        "turmas": turmas,
        "trimestres": trimestres,
        "disciplinas": atribuicoes,
        "turma_sel": turma_id,
        "trimestre_sel": trimestre_id,
        "disciplina_sel": disciplina_id,
        "turma": turma,
        "trimestre": trimestre,
        "disciplina": disciplina,
        "pauta": pauta,
        "avaliacoes": avaliacoes,
        "secao": "resultado_semestral",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 6. RESULTADOS ANUAIS
# ─────────────────────────────────────────────────────────────────────────────

@professor_required
def resultados_anuais(request):
    """Resultados anuais por turma/disciplina. POST recalcula os resultados."""
    professor = request.professor
    ano_lectivo = _get_ano_atual()
    iniciais = _get_iniciais(request)

    atribuicoes = _turmas_do_professor(professor, ano_lectivo)
    turmas = _turmas_distintas(atribuicoes)
    trimestres = _trimestres_do_ano(ano_lectivo)          # ordem crescente: 1.º, 2.º, 3.º

    turma_id = _uuid_ou_none(request.GET.get("turma"))
    disciplina_id = _uuid_ou_none(request.GET.get("disciplina"))

    pauta = []
    turma = disciplina = atribuicao = None

    if turma_id and disciplina_id:
        atribuicao = get_object_or_404(atribuicoes, turma_id=turma_id, disciplina_id=disciplina_id)
        turma, disciplina = atribuicao.turma, atribuicao.disciplina
        matriculas = list(_matriculas_activas(turma))

        if request.method == "POST":
            from app.avaliacao.services.regras_avaliacao import recalcular_anual
            with transaction.atomic():
                for m in matriculas:
                    recalcular_anual(m, disciplina)
            messages.success(request, "Resultados anuais recalculados.")
            return redirect(f"{request.path}?{urlencode({'turma': turma_id, 'disciplina': disciplina_id})}")

        trimestrais = {
            (rt.matricula_id, rt.trimestre_id): rt
            for rt in ResultadoTrimestral.objects.filter(matricula__in=matriculas, disciplina=disciplina)
        }
        anuais = {
            ra.matricula_id: ra
            for ra in ResultadoAnual.objects.filter(matricula__in=matriculas, disciplina=disciplina)
        }

        for idx, m in enumerate(matriculas, 1):
            pauta.append({
                "numero": idx,
                "matricula": m,
                "resultados_trim": {str(t.pk): trimestrais.get((m.pk, t.pk)) for t in trimestres},
                "trimestres": trimestres,
                "resultado_anual": anuais.get(m.pk),
            })

    return render(request, "professor/resultados_anuais.html", {
        "turmas": turmas,
        "disciplinas": atribuicoes,
        "turma_sel": turma_id,
        "disciplina_sel": disciplina_id,
        "turma": turma,
        "disciplina": disciplina,
        "turma_disciplina": atribuicao,
        "pauta": pauta,
        "trimestres": trimestres if turma_id else [],
        "secao": "resultados_anual",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 7. EXAMES
# ─────────────────────────────────────────────────────────────────────────────

@professor_required
def lancar_nota_exame(request):
    """Lança notas de exame (Nacional / Recurso / Especial) dos alunos admitidos."""
    professor = request.professor
    ano_lectivo = _get_ano_atual()
    iniciais = _get_iniciais(request)

    atribuicoes = _turmas_do_professor(professor, ano_lectivo)
    turmas = _turmas_distintas(atribuicoes)
    disciplinas = list({a.disciplina_id: a.disciplina for a in atribuicoes}.values())

    turma_id = _uuid_ou_none(request.GET.get("turma"))
    disciplina_id = _uuid_ou_none(request.GET.get("disciplina"))
    tipo = request.GET.get("tipo") or Exame.Tipo.NACIONAL
    if tipo not in Exame.Tipo.values:
        tipo = Exame.Tipo.NACIONAL

    admitidos = []
    turma = atribuicao = None

    if turma_id and disciplina_id:
        atribuicao = get_object_or_404(atribuicoes, turma_id=turma_id, disciplina_id=disciplina_id)
        turma = atribuicao.turma
        disciplina = atribuicao.disciplina

        admitidos = list(
            ResultadoAnual.objects
            .filter(
                matricula__turma=turma,
                matricula__ano_lectivo=turma.ano_lectivo,
                disciplina=disciplina,
                situacao__in=SITUACOES_EXAME,
            )
            .select_related("matricula__aluno")
            .order_by("matricula__aluno__nome_completo")
        )
        exames = {
            e.matricula_id: e
            for e in Exame.objects.filter(
                matricula__in=[ra.matricula_id for ra in admitidos], disciplina=disciplina, tipo=tipo
            )
        }
        for ra in admitidos:
            ra.exame_lancado = exames.get(ra.matricula_id)       # para pré-preencher o formulário

        if request.method == "POST":
            data_exame = _parse_data(request.POST.get("data"))
            salvos, erros = 0, []
            with transaction.atomic():
                for ra in admitidos:
                    bruto = request.POST.get(f"exame_{ra.pk}", "").strip()
                    if not bruto:
                        continue
                    try:
                        nota = _parse_nota(bruto)
                    except ValueError as exc:
                        erros.append(f"{ra.matricula.aluno.nome_completo}: {exc}")
                        continue
                    defaults = {"nota": nota, "ano_lectivo": turma.ano_lectivo}
                    if data_exame:
                        defaults["data"] = data_exame
                    # o signal de Exame recalcula o ResultadoAnual
                    Exame.objects.update_or_create(
                        matricula=ra.matricula, disciplina=disciplina, tipo=tipo, defaults=defaults,
                    )
                    salvos += 1

            if salvos:
                messages.success(request, "Notas de exame lançadas e resultados actualizados.")
            for erro in erros:
                messages.warning(request, erro)
            query = urlencode({"turma": turma_id, "disciplina": disciplina_id, "tipo": tipo})
            return redirect(f"{request.path}?{query}")

    return render(request, "professor/lancar_exame.html", {
        "turmas": turmas,
        "disciplinas": disciplinas,
        "turma_sel": turma_id,
        "disciplina_sel": disciplina_id,
        "tipo": tipo,
        "tipos_exame": Exame.Tipo.choices,
        "turma": turma,
        "turma_disciplina": atribuicao,
        "admitidos": admitidos,
        "secao": "resultados_anual",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 8. BOLETIM DO ALUNO
# ─────────────────────────────────────────────────────────────────────────────

def _pode_ver_matricula(user, matricula):
    """Quem pode consultar o boletim: o próprio aluno, direcção/administração,
    funcionários não-professores e professores da turma."""
    if user.is_superuser or user.is_staff:
        return True
    if getattr(user, "director", None) is not None:
        return True
    if matricula.aluno.utilizador_id == user.pk:
        return True
    funcionario = getattr(user, "funcionario", None)
    if funcionario is None:
        return False
    if funcionario.tipo_funcionario == Funcionario.TipoFuncionario.PROFESSOR:
        return AtribuicaoDocente.objects.filter(professor=funcionario, turma_id=matricula.turma_id).exists()
    return True


@login_required
def boletim_aluno(request, matricula_pk):
    matricula = get_object_or_404(
        Matricula.objects.select_related("aluno", "turma", "turma__curso", "turma__classe", "ano_lectivo"),
        pk=matricula_pk,
    )
    if not _pode_ver_matricula(request.user, matricula):
        raise PermissionDenied("Sem permissão para consultar este boletim.")

    iniciais = _get_iniciais(request)
    ano_lectivo = matricula.ano_lectivo
    trimestres = _trimestres_do_ano(ano_lectivo)
    turma = matricula.turma

    # Disciplinas: plano curricular do curso/classe + as atribuídas à turma
    disciplinas = Disciplina.objects.none()
    if turma:
        disciplinas = (
            Disciplina.objects
            .filter(
                Q(atribuicao__turma=turma)
                | Q(planocurricular__curso_id=turma.curso_id, planocurricular__classe_id=turma.classe_id)
            )
            .distinct()
            .order_by("nome")
        )

    trimestrais = {
        (rt.disciplina_id, rt.trimestre_id): rt
        for rt in ResultadoTrimestral.objects.filter(matricula=matricula)
    }
    anuais = {ra.disciplina_id: ra for ra in ResultadoAnual.objects.filter(matricula=matricula)}

    boletim = [
        {
            "disciplina": disciplina,
            "trimestrais": {str(t.pk): trimestrais.get((disciplina.pk, t.pk)) for t in trimestres},
            "resultado_anual": anuais.get(disciplina.pk),
        }
        for disciplina in disciplinas
    ]

    return render(request, "professor/boletim_aluno.html", {
        "matricula": matricula,
        "boletim": boletim,
        "trimestres": trimestres,
        "ano_lectivo": ano_lectivo,
        "agora": timezone.localtime(),
        "secao": "avaliacoes",
        "iniciais": iniciais,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 9. HORÁRIO
# ─────────────────────────────────────────────────────────────────────────────

class HorarioView(ProfessorRequiredMixin, TemplateView):
    """Horário semanal do professor organizado por dia e bloco horário."""
    template_name = "professor/horario.html"

    DIAS_ORDEM = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()

        horarios_qs = HorarioAula.objects.filter(professor=professor)
        if ano_lectivo:
            horarios_qs = horarios_qs.filter(turma__ano_lectivo=ano_lectivo)
        horarios = list(
            horarios_qs
            .select_related("turma", "disciplina", "turma__classe")   # `periodo` é CharField: não entra em select_related
            .order_by("hora_inicio", "dia_semana")
        )

        blocos = sorted({(h.hora_inicio, h.hora_fim) for h in horarios}, key=lambda b: b[0])
        grade = {bloco: {dia: None for dia in self.DIAS_ORDEM} for bloco in blocos}
        for h in horarios:
            if h.dia_semana in self.DIAS_ORDEM:
                grade[(h.hora_inicio, h.hora_fim)][h.dia_semana] = h

        linhas = [
            {"inicio": b[0], "fim": b[1], "celulas": [grade[b][d] for d in self.DIAS_ORDEM]}
            for b in blocos
        ]

        ctx.update({
            "professor": professor,
            "dias": self.DIAS_ORDEM,
            "grade": grade,
            "blocos": blocos,
            "linhas": linhas,
            "total_aulas": len(horarios),
            "disciplinas_count": len({h.disciplina_id for h in horarios}),
            "turmas_count": len({h.turma_id for h in horarios}),
            "carga_horaria": professor.carga_horaria_semanal or 0,
            "secao": "meu_horario",
            "iniciais": _get_iniciais(self.request),
        })
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 10. OS MEUS ALUNOS
# ─────────────────────────────────────────────────────────────────────────────

class MeusAlunosView(ProfessorRequiredMixin, TemplateView):
    """Alunos das turmas do professor, com pesquisa, filtros e MAC por trimestre."""
    template_name = "professor/meus_alunos.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()

        atribuicoes = _turmas_do_professor(professor, ano_lectivo)
        turma_ids = set(atribuicoes.values_list("turma_id", flat=True))
        pares = set(atribuicoes.values_list("turma_id", "disciplina_id"))

        turma_id = _uuid_ou_none(self.request.GET.get("turma"))
        pesquisa = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado")
        if estado not in Matricula.Status.values:
            estado = None

        matriculas_qs = (
            Matricula.objects
            .filter(turma_id__in=turma_ids, ano_lectivo=ano_lectivo)
            .select_related("aluno", "turma", "turma__classe")
            .order_by("aluno__nome_completo")
        )
        if turma_id:
            matriculas_qs = matriculas_qs.filter(turma_id=turma_id)
        if pesquisa:
            matriculas_qs = matriculas_qs.filter(
                Q(aluno__nome_completo__icontains=pesquisa)
                | Q(aluno__numero_processo__icontains=pesquisa)
                | Q(aluno__bi__icontains=pesquisa)
            )
        if estado:
            matriculas_qs = matriculas_qs.filter(status=estado)

        # Paginar ANTES de calcular (só se enriquece a página corrente)
        paginator = Paginator(matriculas_qs, 25)
        page_obj = paginator.get_page(self.request.GET.get("page", 1))
        matriculas_pagina = list(page_obj.object_list)

        trimestres = _trimestres_do_ano(ano_lectivo)

        # Uma única query com todos os MAC da página
        acumulado = {}
        mapa_turma = {m.pk: m.turma_id for m in matriculas_pagina}
        for mat_id, disc_id, trim_id, mac in (
            ResultadoTrimestral.objects
            .filter(matricula__in=matriculas_pagina, mac__isnull=False)
            .values_list("matricula_id", "disciplina_id", "trimestre_id", "mac")
        ):
            if (mapa_turma[mat_id], disc_id) in pares:     # só disciplinas do professor
                acumulado.setdefault((mat_id, trim_id), []).append(mac)

        lista_alunos = []
        for m in matriculas_pagina:
            macs = {}
            for t in trimestres:
                valores = acumulado.get((m.pk, t.pk))
                macs[t.designacao] = (sum(valores) / len(valores)) if valores else None
            lista_alunos.append({"matricula": m, "aluno": m.aluno, "macs": macs})

        page_obj.object_list = lista_alunos

        ctx.update({
            "professor": professor,
            "ano_lectivo": ano_lectivo,
            "trimestres": trimestres,
            "lista_alunos": page_obj,
            "paginator": paginator,
            "page_obj": page_obj,
            "turmas_do_prof": (
                Turma.objects.filter(id__in=turma_ids).select_related("classe").order_by("designacao")
            ),
            "filtro_turma": str(turma_id) if turma_id else None,
            "pesquisa": pesquisa,
            "filtro_estado": estado,
            "total_alunos": paginator.count,
            "iniciais": _get_iniciais(self.request),
            "secao": "meus_alunos",
        })
        return ctx


class DetalheAlunoView(ProfessorRequiredMixin, TemplateView):
    """Ficha detalhada de um aluno — notas, resultados e faltas (disciplinas do professor)."""
    template_name = "professor/detalhe_aluno.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()

        aluno = get_object_or_404(Aluno, pk=self.kwargs.get("aluno_id"))

        # O professor só vê alunos das turmas onde lecciona
        matriculas = Matricula.objects.filter(aluno=aluno, turma__atribuicaodocente__professor=professor)
        if ano_lectivo:
            matriculas = matriculas.filter(ano_lectivo=ano_lectivo)
        matricula = (
            matriculas.select_related("turma", "turma__classe", "turma__curso")
            .distinct().order_by("-ano_lectivo__data_inicio").first()
        )
        if matricula is None:
            raise PermissionDenied("Este aluno não pertence a nenhuma das suas turmas.")

        disciplina_ids = list(
            AtribuicaoDocente.objects
            .filter(professor=professor, turma_id=matricula.turma_id)
            .values_list("disciplina_id", flat=True)
        )

        notas = (
            AvaliacaoContinua.objects
            .filter(matricula=matricula, disciplina_id__in=disciplina_ids)
            .select_related("trimestre", "disciplina")
            .order_by("trimestre__designacao", "data")
        )
        resultados_trim = (
            ResultadoTrimestral.objects
            .filter(matricula=matricula, disciplina_id__in=disciplina_ids)
            .select_related("trimestre", "disciplina")
            .order_by("disciplina__nome", "trimestre__designacao")
        )
        resultados_anuais = (
            ResultadoAnual.objects
            .filter(matricula=matricula, disciplina_id__in=disciplina_ids)
            .select_related("disciplina")
            .order_by("disciplina__nome")
        )
        faltas = (
            Falta.objects
            .filter(matricula=matricula, disciplina_id__in=disciplina_ids)
            .select_related("disciplina")
            .order_by("-data")
        )
        resumo_faltas = faltas.aggregate(
            total=Coalesce(Sum("tempos"), 0),
            injustificadas=Coalesce(Sum("tempos", filter=Q(justificada=False)), 0),
        )

        ctx.update({
            "professor": professor,
            "aluno": aluno,
            "matricula": matricula,
            "ano_lectivo": matricula.ano_lectivo,
            "notas": notas,
            "resultados_trim": resultados_trim,
            "resultados_anuais": resultados_anuais,
            "faltas": faltas,
            "total_faltas": resumo_faltas["total"],
            "faltas_injustificadas": resumo_faltas["injustificadas"],
            "iniciais": _get_iniciais(self.request),
            "secao": "meus_alunos",
        })
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 11. FREQUÊNCIA & FALTAS
# ─────────────────────────────────────────────────────────────────────────────

class FrequenciaView(ProfessorRequiredMixin, TemplateView):
    """
    Consulta (GET) e registo (POST) de faltas por turma/disciplina/data.
    POST: campos `turma`, `disciplina`, `data`, `tempos` e, por aluno,
    `faltou_<matricula_id>`, `justificada_<matricula_id>`, `motivo_<matricula_id>`.
    Alunos sem `faltou_` marcado ficam sem falta nessa data/disciplina.
    """
    template_name = "professor/frequencia.html"

    def post(self, request, *args, **kwargs):
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()
        atribuicao = get_object_or_404(
            _turmas_do_professor(professor, ano_lectivo),
            turma_id=_uuid_ou_none(request.POST.get("turma")),
            disciplina_id=_uuid_ou_none(request.POST.get("disciplina")),
        )
        data_aula = _parse_data(request.POST.get("data"), timezone.localdate())
        tempos = min(max(_int_ou_none(request.POST.get("tempos")) or 1, 1), 10)

        with transaction.atomic():
            for m in _matriculas_activas(atribuicao.turma):
                filtro = {"matricula": m, "disciplina": atribuicao.disciplina, "data": data_aula}
                if request.POST.get(f"faltou_{m.pk}") == "on":
                    Falta.objects.update_or_create(
                        **filtro,
                        defaults={
                            "tempos": tempos,
                            "justificada": request.POST.get(f"justificada_{m.pk}") == "on",
                            "motivo": request.POST.get(f"motivo_{m.pk}", "").strip()[:200],
                        },
                    )
                else:
                    Falta.objects.filter(**filtro).delete()

        messages.success(request, "Faltas registadas com sucesso.")
        query = urlencode({
            "turma": atribuicao.turma_id, "disciplina": atribuicao.disciplina_id,
            "data": data_aula.isoformat(),
        })
        return redirect(f"{request.path}?{query}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ano_lectivo = _get_ano_atual()
        hoje = timezone.localdate()

        atribuicoes = list(_turmas_do_professor(professor, ano_lectivo))
        turmas_do_prof = _turmas_distintas(atribuicoes)

        turma_id = _uuid_ou_none(self.request.GET.get("turma"))
        disciplina_id = _uuid_ou_none(self.request.GET.get("disciplina"))
        data_aula = _parse_data(self.request.GET.get("data"), hoje)
        dia_semana = DIAS_SEMANA.get(data_aula.weekday(), "")

        # Só turmas do professor (padrão: a primeira)
        turma_actual = next((t for t in turmas_do_prof if t.pk == turma_id), None) \
            or (turmas_do_prof[0] if turmas_do_prof else None)

        lista_alunos, horario_aula = [], None
        disciplinas_turma, atribuicao_actual = [], None

        if turma_actual:
            disciplinas_turma = [a for a in atribuicoes if a.turma_id == turma_actual.pk]
            atribuicao_actual = next((a for a in disciplinas_turma if a.disciplina_id == disciplina_id), None) \
                or disciplinas_turma[0]
            disc_ids = [a.disciplina_id for a in disciplinas_turma]

            horario_aula = HorarioAula.objects.filter(
                professor=professor, turma=turma_actual, dia_semana=dia_semana
            ).first()

            matriculas = list(_matriculas_activas(turma_actual, ano_lectivo))

            faltas_qs = Falta.objects.filter(matricula__in=matriculas, disciplina_id__in=disc_ids)
            resumo = {
                r["matricula_id"]: r
                for r in faltas_qs.values("matricula_id").annotate(
                    total=Sum("tempos"),
                    injustificadas=Sum("tempos", filter=Q(justificada=False)),
                )
            }
            faltas_dia = {
                f.matricula_id: f
                for f in faltas_qs.filter(data=data_aula, disciplina=atribuicao_actual.disciplina)
            }

            # Tempos previstos até hoje = carga semanal (plano) x semanas decorridas
            carga = PlanoCurricular.objects.filter(
                curso_id=turma_actual.curso_id, classe_id=turma_actual.classe_id, disciplina_id__in=disc_ids,
            ).aggregate(t=Sum("carga_horaria_semanal"))["t"] or 0
            previstos = carga * _semanas_decorridas(turma_actual.ano_lectivo)

            regra = RegraAvaliacao.objects.filter(
                ano_lectivo_id=turma_actual.ano_lectivo_id, classe_id=turma_actual.classe_id
            ).first()
            limite = regra.limite_faltas_injustificadas_pct if regra else Decimal("30")

            for i, m in enumerate(matriculas, start=1):
                r = resumo.get(m.pk, {})
                total_faltas = r.get("total") or 0
                injustificadas = r.get("injustificadas") or 0
                perc_faltas = (Decimal(injustificadas) / previstos * 100) if previstos else Decimal("0")
                lista_alunos.append({
                    "ordem": i,
                    "matricula": m,
                    "aluno": m.aluno,
                    "total_faltas": total_faltas,
                    "faltas_injustificadas": injustificadas,
                    "falta_hoje": faltas_dia.get(m.pk),
                    "perc_presenca": max(0, min(100, round(100 - (total_faltas / previstos * 100)))) if previstos else 100,
                    "em_risco": perc_faltas >= limite,
                })

        ctx.update({
            "professor": professor,
            "ano_lectivo": ano_lectivo,
            "turmas_do_prof": turmas_do_prof,
            "turma_actual": turma_actual,
            "disciplinas_turma": disciplinas_turma,
            "atribuicao_actual": atribuicao_actual,
            "data_aula": data_aula,
            "horario_aula": horario_aula,
            "lista_alunos": lista_alunos,
            "secao": "frequencia",
            "iniciais": _get_iniciais(self.request),
        })
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 12. COMUNICADOS
# ─────────────────────────────────────────────────────────────────────────────

class ComunicadosView(ProfessorRequiredMixin, ListView):
    """
    Comunicados dirigidos ao professor ou a todos.
    NOTA: o modelo `Comunicado` não existe em models.py; enquanto não for criado
    a lista aparece vazia (em vez de a view rebentar com NameError).
    """
    template_name = "professor/comunicados.html"
    context_object_name = "comunicados"
    paginate_by = 10

    def get_queryset(self):
        if Comunicado is None:
            return []
        return (
            Comunicado.objects
            .filter(activo=True)
            .filter(Q(destinatario_tipo="Todos") | Q(destinatario_tipo="Professores"))
            .filter(Q(data_expiracao__isnull=True) | Q(data_expiracao__gte=timezone.now()))
            .order_by("-data_publicacao")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["professor"] = self.get_professor()
        ctx["iniciais"] = _get_iniciais(self.request)
        ctx["secao"] = "comunicados"
        ctx["urgentes"] = [] if Comunicado is None else self.get_queryset().filter(tipo="Urgente")
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 13. MINI-PAUTA GERAL + PDF
# ─────────────────────────────────────────────────────────────────────────────

def _montar_pauta(turma, trimestre, termo=""):
    """Constrói a mini-pauta (MAC/PT/MT por disciplina) de uma turma num trimestre."""
    disciplinas = list(
        AtribuicaoDocente.objects.filter(turma=turma)
        .select_related("disciplina").order_by("disciplina__nome")
    )
    matriculas_qs = _matriculas_activas(turma)
    if termo:
        matriculas_qs = matriculas_qs.filter(aluno__nome_completo__icontains=termo)
    matriculas = list(matriculas_qs)

    resultados = {
        (rt.matricula_id, rt.disciplina_id): rt
        for rt in ResultadoTrimestral.objects.filter(matricula__in=matriculas, trimestre=trimestre)
    }
    minimo = _nota_minima_turma(turma)

    soma = {d.disciplina_id: Decimal("0") for d in disciplinas}
    cont = {d.disciplina_id: 0 for d in disciplinas}
    dados, positivos, negativos = [], 0, 0

    for m in matriculas:
        linha, tem_nota, tem_negativa = [], False, False
        for d in disciplinas:
            notas = _notas_trimestrais(resultados.get((m.pk, d.disciplina_id)))
            linha.append(notas)
            if notas["mt"] is not None:
                tem_nota = True
                soma[d.disciplina_id] += notas["mt"]
                cont[d.disciplina_id] += 1
                if notas["mt"] < minimo:
                    tem_negativa = True
        if tem_negativa:
            negativos += 1
        elif tem_nota:
            positivos += 1
        dados.append({"aluno": m.aluno, "matricula": m, "notas": linha})

    medias_turma = [
        {"mt": (soma[d.disciplina_id] / cont[d.disciplina_id]).quantize(Decimal("0.1"))
         if cont[d.disciplina_id] else None}
        for d in disciplinas
    ]
    return {
        "dados": dados,
        "disciplinas": disciplinas,
        "medias_turma": medias_turma,
        "total_alunos": len(matriculas),
        "total_positivos": positivos,
        "total_negativos": negativos,
        "num_colunas": 2 + len(disciplinas) * 3,
    }


@pessoal_required
def mini_pauta(request):
    ano_lectivo_id = _uuid_ou_none(request.GET.get("ano_lectivo"))
    turma_id = _uuid_ou_none(request.GET.get("turma"))
    trimestre_id = _uuid_ou_none(request.GET.get("trimestre"))
    q = request.GET.get("q", "").strip()

    anos_lectivos = AnoLectivo.objects.all().order_by("-data_inicio")
    ano_lectivo_obj = (
        anos_lectivos.filter(pk=ano_lectivo_id).first() if ano_lectivo_id else _get_ano_atual()
    )

    turmas_qs = Turma.objects.select_related("classe", "curso", "ano_lectivo")
    trimestres_qs = Trimestre.objects.all().order_by("designacao")
    if ano_lectivo_obj:
        turmas_qs = turmas_qs.filter(ano_lectivo=ano_lectivo_obj)
        trimestres_qs = trimestres_qs.filter(ano_lectivo=ano_lectivo_obj)

    turma_obj = turmas_qs.filter(pk=turma_id).first() if turma_id else None
    trimestre_obj = trimestres_qs.filter(pk=trimestre_id).first() if trimestre_id else None

    pauta = {
        "dados": [], "disciplinas": [], "medias_turma": [], "total_alunos": 0,
        "total_positivos": 0, "total_negativos": 0, "num_colunas": 2,
    }
    if turma_obj and trimestre_obj:
        pauta = _montar_pauta(turma_obj, trimestre_obj, q)

    agora = timezone.localtime(timezone.now())
    return render(request, "professor/mini_pauta_geral.html", {
        "anos_lectivos": anos_lectivos,
        "turmas": turmas_qs,
        "trimestres": trimestres_qs,
        "ano_lectivo": ano_lectivo_obj,
        "turma": turma_obj,
        "trimestre": trimestre_obj,
        "trimestre_id": request.GET.get("trimestre"),
        "turma_id": request.GET.get("turma"),
        "hoje": agora.strftime("%d/%m/%Y"),
        "agora": agora.strftime("%H:%M"),
        **pauta,
    })


def gerar_contexto_pauta(request, trimestre_id, turma_id):
    """Contexto da pauta para exportação (mesma lógica da mini-pauta)."""
    turma_obj = Turma.objects.select_related("classe", "curso", "ano_lectivo").filter(
        pk=_uuid_ou_none(turma_id)
    ).first()
    trimestre_obj = Trimestre.objects.filter(pk=_uuid_ou_none(trimestre_id)).first()
    if not turma_obj or not trimestre_obj:
        return None

    return {
        "turma": turma_obj,
        "trimestre": trimestre_obj,
        "classe": turma_obj.classe,
        "curso": turma_obj.curso,
        "sala": turma_obj.sala or "—",
        "hoje": timezone.now(),
        **_montar_pauta(turma_obj, trimestre_obj),
    }


@pessoal_required
def exportar_pauta_pdf(request, trimestre_id, turma_id):
    context = gerar_contexto_pauta(request, trimestre_id, turma_id)
    if context is None:
        return HttpResponse("Turma ou trimestre não encontrado.", status=404)

    from xhtml2pdf import pisa      # import local: não quebra o módulo se não estiver instalado

    html_string = render_to_string("professor/pdf_mini_pauta.html", context, request=request)
    nome_ficheiro = slugify(f"pauta-{context['turma'].designacao}-{context['trimestre'].designacao}-trimestre")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nome_ficheiro}.pdf"'

    pisa_status = pisa.CreatePDF(io.BytesIO(html_string.encode("UTF-8")), dest=response)
    if pisa_status.err:
        return HttpResponse("Erro ao gerar PDF", status=500)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# VIEWS AJAX / API INTERNA
# ─────────────────────────────────────────────────────────────────────────────

@api_professor_required
def api_turma_alunos(request, turma_id):
    """JSON: lista de {id, nome, numero_processo} dos alunos de uma turma."""
    atribuicao = (
        AtribuicaoDocente.objects
        .filter(professor=request.professor, turma_id=_uuid_ou_none(turma_id))
        .select_related("turma")
        .first()
    )
    if atribuicao is None:
        return JsonResponse({"erro": "Sem acesso."}, status=403)

    matriculas = _matriculas_activas(atribuicao.turma)
    data = [
        {
            "id": str(m.id),
            "nome": m.aluno.nome_completo,
            "numero_processo": m.aluno.numero_processo or "—",
        }
        for m in matriculas
    ]
    return JsonResponse({"alunos": data, "total": len(data)})


@api_professor_required
def api_estatisticas_turma(request, turma_id):
    """JSON: estatísticas de uma turma (média, aprovados, reprovados) nas disciplinas do professor."""
    atribuicoes = AtribuicaoDocente.objects.filter(
        professor=request.professor, turma_id=_uuid_ou_none(turma_id)
    ).select_related("turma")
    atribuicao = atribuicoes.first()
    if atribuicao is None:
        return JsonResponse({"erro": "Sem acesso."}, status=403)

    resultados = ResultadoAnual.objects.filter(
        matricula__turma_id=atribuicao.turma_id,
        matricula__ano_lectivo_id=atribuicao.turma.ano_lectivo_id,
        disciplina_id__in=atribuicoes.values_list("disciplina_id", flat=True),
    )
    agg = resultados.aggregate(
        media=Avg(Coalesce("nota_final", "mfd")),
        aprovados=Count("id", filter=Q(situacao__in=SITUACOES_APROVADO)),
        admitidos_exame=Count("id", filter=Q(situacao=ResultadoAnual.Situacao.ADMITIDO_EXAME)),
        reprovados=Count("id", filter=Q(situacao__in=SITUACOES_REPROVADO)),
        total=Count("id"),
    )
    return JsonResponse({
        "media": float(agg["media"] or 0),
        "aprovados": agg["aprovados"],
        "admitidos_exame": agg["admitidos_exame"],
        "reprovados": agg["reprovados"],
        "total": agg["total"],
    })


@api_professor_required
def api_guardar_nota_rapida(request):
    """
    JSON POST: guarda/actualiza a nota de UM aluno.
    Body: {matricula_id, turma_disciplina_id, trimestre_id, nota, faltou?,
           tipo? (default TESTE; também PP/PT), data? (YYYY-MM-DD), descricao?}
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    professor = request.professor
    atribuicao = (
        AtribuicaoDocente.objects
        .filter(pk=_int_ou_none(body.get("turma_disciplina_id")), professor=professor)
        .select_related("turma", "disciplina")
        .first()
    )
    if atribuicao is None:
        return JsonResponse({"erro": "Atribuição não encontrada."}, status=404)

    matricula = Matricula.objects.filter(
        pk=_uuid_ou_none(body.get("matricula_id")),
        turma_id=atribuicao.turma_id,
        status=Matricula.Status.ACTIVA,
    ).select_related("aluno").first()
    if matricula is None:
        return JsonResponse({"erro": "Matrícula não encontrada nesta turma."}, status=404)

    trimestre = Trimestre.objects.filter(
        pk=_uuid_ou_none(body.get("trimestre_id")),
        ano_lectivo_id=atribuicao.turma.ano_lectivo_id,
    ).first()
    if trimestre is None:
        return JsonResponse({"erro": "Trimestre inválido."}, status=400)
    if not trimestre.lancamento_aberto:
        return JsonResponse({"erro": "Lançamento fechado para este trimestre."}, status=403)

    tipo = body.get("tipo") or AvaliacaoContinua.Tipo.TESTE
    if tipo not in dict(_tipos_lancamento()):
        return JsonResponse({"erro": "Tipo de avaliação inválido."}, status=400)

    faltou = bool(body.get("faltou", False))
    if faltou:
        nota_val = Decimal("0.00")
    else:
        try:
            nota_val = _parse_nota(body.get("nota"), min(Decimal(atribuicao.turma.valor_maximo or 20), NOTA_MAXIMA))
        except ValueError as exc:
            return JsonResponse({"erro": str(exc)}, status=400)

    data = _parse_data(body.get("data"), timezone.localdate())
    descricao = "" if tipo in TIPOS_PROVA else str(body.get("descricao") or "").strip()[:150]

    obj, criado = _gravar_nota(
        utilizador=request.user, matricula=matricula, disciplina=atribuicao.disciplina,
        trimestre=trimestre, tipo=tipo, data=data, descricao=descricao, valor=nota_val,
    )
    valor_gravado = getattr(obj, tipo.lower()) if tipo in TIPOS_PROVA else obj.valor

    return JsonResponse({
        "ok": True,
        "criado": criado,
        "nota": float(valor_gravado),
        "faltou": faltou,
        "situacao": _situacao_nota(valor_gravado, faltou)["codigo"],
    })


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES INTERNAS
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_notas_pendentes(atribuicoes, trimestre):
    """
    Nº de turmas/disciplinas do professor com lançamento incompleto no trimestre
    activo (há alunos activos sem PP e PT lançadas).
    """
    if not trimestre:
        return 0

    pendentes = 0
    for atr in atribuicoes:
        ano_id = atr.turma.ano_lectivo_id
        total_alunos = Matricula.objects.filter(
            turma_id=atr.turma_id, ano_lectivo_id=ano_id, status=Matricula.Status.ACTIVA
        ).count()
        if total_alunos == 0:
            continue
        completos = ResultadoTrimestral.objects.filter(
            matricula__turma_id=atr.turma_id,
            matricula__ano_lectivo_id=ano_id,
            matricula__status=Matricula.Status.ACTIVA,
            disciplina_id=atr.disciplina_id,
            trimestre=trimestre,
            pp__isnull=False,
            pt__isnull=False,
        ).count()
        if completos < total_alunos:
            pendentes += 1
    return pendentes


def _construir_alertas(trimestre, notas_pendentes):
    """Constrói a lista de alertas para o dashboard."""
    alertas = []

    if notas_pendentes > 0:
        alertas.append({
            "tipo": "warn",
            "icone": "bi-exclamation-triangle-fill",
            "titulo": f"{notas_pendentes} turma(s)/disciplina(s) com notas por lançar",
            "subtitulo": "Clique em 'Lançamento de Notas' para proceder.",
        })

    if trimestre:
        subtitulo = "Trimestre em curso."
        if trimestre.data_fim:
            subtitulo += f" Termina a {trimestre.data_fim.strftime('%d/%m/%Y')}."
        alertas.append({
            "tipo": "info",
            "icone": "bi-info-circle-fill",
            "titulo": f"Período de avaliações activo — {trimestre.designacao}.º Trimestre",
            "subtitulo": subtitulo,
        })

    return alertas


def _turmas_com_estatisticas(atribuicoes, trimestre):
    """
    Enriquece cada AtribuicaoDocente com: total de alunos, média MAC do
    trimestre activo, taxa de aprovação e nº de alunos sem MT.
    Tudo filtrado pela turma da atribuição (e não pela disciplina em geral).
    """
    resultado = []
    for atr in atribuicoes:
        ano_id = atr.turma.ano_lectivo_id
        base = {"matricula__turma_id": atr.turma_id, "matricula__ano_lectivo_id": ano_id,
                "disciplina_id": atr.disciplina_id}

        total_alunos = Matricula.objects.filter(
            turma_id=atr.turma_id, ano_lectivo_id=ano_id, status=Matricula.Status.ACTIVA
        ).count()

        media_mac, sem_mt = None, total_alunos
        if trimestre:
            trimestrais = ResultadoTrimestral.objects.filter(trimestre=trimestre, **base)
            media = trimestrais.aggregate(media=Avg("mac"))["media"]
            media_mac = round(media, 1) if media is not None else None
            sem_mt = max(total_alunos - trimestrais.filter(mt__isnull=False).count(), 0)

        anuais = ResultadoAnual.objects.filter(**base)
        total_res = anuais.count()
        aprovados = anuais.filter(situacao__in=SITUACOES_APROVADO).count()

        resultado.append({
            "turma_disciplina": atr,
            "total_alunos": total_alunos,
            "media_mac": media_mac,
            "taxa_aprovacao": round(aprovados / total_res * 100) if total_res else None,
            "notas_pendentes": sem_mt,
        })
    return resultado


def _status_avaliacao(notas_lancadas, total_alunos, data_realizacao):
    """Devolve o estado legível de uma avaliação."""
    hoje = timezone.localdate()
    if notas_lancadas >= total_alunos and total_alunos > 0:
        return {"codigo": "concluida", "label": "Concluída", "tag": "tag-green"}
    if data_realizacao and data_realizacao > hoje:
        return {"codigo": "programada", "label": "Programada", "tag": "tag-blue"}
    if notas_lancadas == 0:
        return {"codigo": "pendente", "label": "Pendente", "tag": "tag-yellow"}
    return {"codigo": "parcial", "label": "Parcial", "tag": "tag-warn"}


def _situacao_nota(nota, faltou=False):
    """Classifica a situação de uma nota individual."""
    if faltou:
        return {"codigo": "faltou", "label": "Faltou", "tag": "tag-red"}
    if nota is None:
        return {"codigo": "sem_nota", "label": "—", "tag": "tag-gray"}
    if nota >= NOTA_POSITIVA:
        return {"codigo": "aprovado", "label": "Aprovado", "tag": "tag-green"}
    if nota >= NOTA_ADMISSAO_EXAME:
        return {"codigo": "exame", "label": "A Exame", "tag": "tag-yellow"}
    return {"codigo": "reprovado", "label": "Reprovado", "tag": "tag-red"}
