import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import TemplateView

from app.db.models import (
    Aluno, AvaliacaoContinua, Falta, HorarioAula, LogAuditoria, PlanoCurricular,
    Reclamacao, RegraAvaliacao, ResultadoAnual, ResultadoTrimestral, TenantConfiguracao,
)
from app.financa.models import ContaAluno, Pagamento 
from .forms import AlunoPerfilForm, DocumentoForm, ReclamacaoForm

logger = logging.getLogger(__name__)
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]


# ───────────────────────── helpers ─────────────────────────
def registar_log(request, accao, modulo, descricao, obj=None):
    """Auditoria — nunca deve quebrar a página."""
    try:
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR") or "0.0.0.0")
        LogAuditoria.objects.create(
            utilizador=request.user, accao=accao, modulo=modulo, descricao=descricao,
            objeto_id=str(obj.pk) if obj else None,
            objeto_tipo=obj.__class__.__name__ if obj else None,
            ip_address=ip, user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
    except Exception:
        logger.exception("Falha ao registar log de auditoria")


def regra_da(matricula):
    if not matricula or not matricula.turma:
        return None
    return RegraAvaliacao.objects.filter(
        ano_lectivo=matricula.ano_lectivo, classe=matricula.turma.classe
    ).first()


def nota_minima(matricula):
    r = regra_da(matricula)
    return r.nota_minima_positiva if r else Decimal("10")


def media_geral(matricula):
    return ResultadoAnual.objects.filter(matricula=matricula, mfd__isnull=False).aggregate(m=Avg("mfd"))["m"]


def ordem_lectiva(propina):
    """Ano lectivo: Setembro→Dezembro, depois Janeiro→Junho."""
    return (propina.mes < 9, propina.mes)


# ───────────────────────── base ─────────────────────────
class AlunoPortalMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        aluno = Aluno.objects.filter(utilizador=request.user).first()
        if not aluno:
            return render(request, "portal/sem_acesso.html", status=403)
        request.aluno = aluno
        self.matriculas, self.matricula = self._resolver_matricula(request)
        return super().dispatch(request, *args, **kwargs)

    def _resolver_matricula(self, request):
        lista = list(request.aluno.matriculas.select_related(
            "ano_lectivo", "turma", "turma__curso", "turma__classe"
        ).order_by("-ano_lectivo__data_inicio"))
        ano = request.GET.get("ano")
        escolhida = next((m for m in lista if str(m.ano_lectivo_id) == ano), None) if ano else None
        if not escolhida:
            escolhida = next((m for m in lista if m.ano_lectivo.e_atual), lista[0] if lista else None)
        return lista, escolhida


class PortalBase(AlunoPortalMixin, TemplateView):
    secao = ""

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(
            aluno=self.request.aluno, matriculas=self.matriculas, matricula=self.matricula,
            secao=self.secao, escola=TenantConfiguracao.objects.first(),
            minimo=nota_minima(self.matricula),
        )
        return ctx

    def conta(self):
        if not self.matricula:
            return None
        return ContaAluno.objects.filter(aluno=self.request.aluno, ano_lectivo=self.matricula.ano_lectivo).first()


# ───────────────────────── páginas ─────────────────────────
class DashboardView(PortalBase):
    template_name = "portal/dashboard.html"
    secao = "dashboard"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        m = self.matricula
        if not m:
            return ctx
        conta = self.conta()
        faltas = Falta.objects.filter(matricula=m).aggregate(
            total=Sum("tempos"), injust=Sum("tempos", filter=Q(justificada=False)))
        hoje = timezone.localdate()
        aulas_hoje = []
        if m.turma and hoje.weekday() < 5:
            aulas_hoje = HorarioAula.objects.filter(
                atribuicao__turma=m.turma, dia_semana=DIAS[hoje.weekday()]
            ).select_related("atribuicao__disciplina", "atribuicao__professor").order_by("hora_inicio")
        ctx.update(
            conta=conta,
            media=media_geral(m),
            faltas=faltas,
            aulas_hoje=aulas_hoje,
            dia_hoje=DIAS[hoje.weekday()] if hoje.weekday() < 5 else None,
            ultimas_notas=ResultadoTrimestral.objects.filter(matricula=m, mt__isnull=False)
            .select_related("disciplina", "trimestre").order_by("-actualizado_em")[:6],
            propinas_abertas=sorted(conta.propinas.exclude(status="pago"), key=ordem_lectiva)[:3] if conta else [],
            reclamacoes_pendentes=Reclamacao.objects.filter(
                matricula__aluno=self.request.aluno, estado=Reclamacao.Estado.PENDENTE).count(),
        )
        return ctx


class NotasView(PortalBase):
    template_name = "portal/notas.html"
    secao = "notas"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        m = self.matricula
        if not m:
            return ctx
        conta = self.conta()
        if getattr(settings, "PORTAL_BLOQUEAR_NOTAS_DIVIDA", False) and conta and not conta.pode_ver_notas():
            ctx.update(bloqueado=True, conta=conta)
            return ctx

        anuais = {a.disciplina_id: a for a in ResultadoAnual.objects.filter(matricula=m)}
        linhas = {}
        for r in ResultadoTrimestral.objects.filter(matricula=m).select_related("disciplina", "trimestre"):
            l = linhas.setdefault(r.disciplina_id, {"disciplina": r.disciplina, "t1": None, "t2": None, "t3": None})
            l[f"t{r.trimestre.designacao}"] = r
        for disc_id, a in anuais.items():
            linhas.setdefault(disc_id, {"disciplina": a.disciplina, "t1": None, "t2": None, "t3": None})
        for disc_id, l in linhas.items():
            l["anual"] = anuais.get(disc_id)
        linhas = sorted(linhas.values(), key=lambda l: l["disciplina"].nome)

        minimo = ctx["minimo"]
        finais = [l["anual"].nota_final or l["anual"].mfd for l in linhas if l["anual"] and (l["anual"].nota_final or l["anual"].mfd) is not None]
        ctx.update(
            linhas=linhas,
            media=media_geral(m),
            positivas=sum(1 for n in finais if n >= minimo),
            negativas=sum(1 for n in finais if n < minimo),
            exames=m.exames.select_related("disciplina").order_by("-data"),
            avaliacoes=AvaliacaoContinua.objects.filter(matricula=m)
            .select_related("disciplina", "trimestre").order_by("-data")[:40],
        )
        registar_log(self.request, LogAuditoria.Accao.OUTRO, LogAuditoria.Modulo.NOTA,
                     f"Estudante consultou notas de {m.ano_lectivo}", m)
        return ctx


class HistoricoView(PortalBase):
    template_name = "portal/historico.html"
    secao = "historico"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["percurso"] = self.request.aluno.matriculas.select_related(
            "ano_lectivo", "turma", "turma__curso", "turma__classe"
        ).annotate(media=Avg("resultados_anuais__mfd")).order_by("ano_lectivo__data_inicio")
        ctx["media_global"] = ResultadoAnual.objects.filter(
            matricula__aluno=self.request.aluno, mfd__isnull=False).aggregate(m=Avg("mfd"))["m"]
        return ctx


class FinanceiroView(PortalBase):
    template_name = "portal/financeiro.html"
    secao = "financeiro"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        conta = self.conta()
        todas = ContaAluno.objects.filter(aluno=self.request.aluno)
        ctx.update(
            conta=conta,
            divida_total=todas.aggregate(s=Sum("saldo_devedor"))["s"] or 0,
            propinas=sorted(conta.propinas.all(), key=ordem_lectiva) if conta else [],
            pagamentos=conta.pagamentos.select_related("registado_por") if conta else [],
        )
        return ctx


class ReciboView(PortalBase):
    template_name = "portal/recibo.html"
    secao = "financeiro"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        p = get_object_or_404(
            Pagamento.objects.select_related("conta_aluno__ano_lectivo", "registado_por"),
            pk=self.kwargs["pk"], conta_aluno__aluno=self.request.aluno,  # só os seus recibos
        )
        ctx.update(pagamento=p, qr=p.gerar_qr_code())
        registar_log(self.request, LogAuditoria.Accao.IMPRIMIR, LogAuditoria.Modulo.FINANCEIRO,
                     f"Recibo {p.numero_recibo} consultado", p)
        return ctx


class FaltasView(PortalBase):
    template_name = "portal/faltas.html"
    secao = "faltas"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        m = self.matricula
        if not m:
            return ctx
        regra = regra_da(m)
        limite = regra.limite_faltas_injustificadas_pct if regra else Decimal("30")
        previsto = {}
        if m.turma:
            semanas = m.ano_lectivo.semanas_lectivas
            previsto = {p.disciplina_id: p.carga_horaria_semanal * semanas for p in PlanoCurricular.objects.filter(
                ano_lectivo=m.ano_lectivo, curso=m.turma.curso, classe=m.turma.classe)}
        faltas = Falta.objects.filter(matricula=m).select_related("disciplina").order_by("-data")
        resumo = {}
        for f in faltas:
            d = resumo.setdefault(f.disciplina_id, {"disciplina": f.disciplina, "just": 0, "injust": 0})
            d["just" if f.justificada else "injust"] += f.tempos
        for disc_id, d in resumo.items():
            total = previsto.get(disc_id)
            d["pct"] = round(d["injust"] * 100 / total, 1) if total else None
            d["excedeu"] = bool(d["pct"] is not None and d["pct"] >= limite)
            d["alerta"] = bool(d["pct"] is not None and d["pct"] >= float(limite) * 0.7)
        ctx.update(resumo=sorted(resumo.values(), key=lambda d: d["disciplina"].nome), faltas=faltas[:60], limite=limite)
        return ctx


class HorarioView(PortalBase):
    template_name = "portal/horario.html"
    secao = "horario"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        m = self.matricula
        if not m or not m.turma:
            return ctx
        aulas = HorarioAula.objects.filter(atribuicao__turma=m.turma).select_related(
            "atribuicao__disciplina", "atribuicao__professor").order_by("hora_inicio")
        ctx["semana"] = [(label, [a for a in aulas if a.dia_semana == valor])
                         for valor, label in HorarioAula.DiaSemana.choices]
        ctx["hoje"] = DIAS[timezone.localdate().weekday()] if timezone.localdate().weekday() < 5 else None
        return ctx


class ReclamacoesView(PortalBase):
    template_name = "portal/reclamacoes.html"
    secao = "reclamacoes"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["lista"] = Reclamacao.objects.filter(matricula__aluno=self.request.aluno).select_related(
            "disciplina", "trimestre", "matricula__ano_lectivo").order_by("-criada_em")
        if self.matricula and "form" not in ctx:
            ctx["form"] = ReclamacaoForm(matricula=self.matricula)
        return ctx

    def post(self, request, *a, **kw):
        if not self.matricula:
            return redirect("portal:reclamacoes")
        form = ReclamacaoForm(request.POST, matricula=self.matricula)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.matricula = self.matricula
            rec.nota_original = ResultadoTrimestral.objects.filter(
                matricula=self.matricula, disciplina=rec.disciplina, trimestre=rec.trimestre
            ).values_list("mt", flat=True).first()
            rec.save()
            registar_log(request, LogAuditoria.Accao.CRIAR, LogAuditoria.Modulo.NOTA,
                         f"Reclamação de nota — {rec.disciplina}", rec)
            messages.success(request, "Reclamação enviada. Será notificado da decisão.")
            return redirect("portal:reclamacoes")
        return self.render_to_response(self.get_context_data(form=form))


class PerfilView(PortalBase):
    template_name = "portal/perfil.html"
    secao = "perfil"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["form_dados"] = ctx.get("form_dados") or AlunoPerfilForm(instance=self.request.aluno)
        ctx["form_doc"] = ctx.get("form_doc") or DocumentoForm()
        ctx["documentos"] = self.request.aluno.documentos.all()
        return ctx

    def post(self, request, *a, **kw):
        acao = request.POST.get("acao")
        if acao == "dados":
            form = AlunoPerfilForm(request.POST, request.FILES, instance=request.aluno)
            if form.is_valid():
                form.save()
                registar_log(request, LogAuditoria.Accao.ACTUALIZAR, LogAuditoria.Modulo.ALUNO,
                             "Estudante actualizou os seus dados de contacto", request.aluno)
                messages.success(request, "Dados actualizados.")
                return redirect("portal:perfil")
            return self.render_to_response(self.get_context_data(form_dados=form))
        if acao == "documento":
            form = DocumentoForm(request.POST, request.FILES)
            if form.is_valid():
                doc = form.save(commit=False)
                doc.aluno, doc.uploaded_por = request.aluno, request.user
                doc.save()
                registar_log(request, LogAuditoria.Accao.CRIAR, LogAuditoria.Modulo.ALUNO,
                             f"Documento carregado: {doc.titulo}", doc)
                messages.success(request, "Documento carregado.")
                return redirect("portal:perfil")
            return self.render_to_response(self.get_context_data(form_doc=form))
        return redirect("portal:perfil")
