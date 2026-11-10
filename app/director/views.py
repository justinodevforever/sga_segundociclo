from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import date, timedelta, timezone
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from app.db.decorators import *
from .forms import *
from app.db.models import *
from app.financa.models import *
import json
from django.db.utils import IntegrityError
from django.db import transaction
from django.contrib import messages
from .permissions import *

from datetime import timedelta
from django.core.validators import MaxValueValidator, MinValueValidator
from django.urls import reverse
from django.views import View

from .utils import DirectorAdminRequiredMixin, _erros, _tenant, _log

from app.db.models import (
    AnoLectivo, Classe, LogAuditoria, RegraAvaliacao,
    TenantConfiguracao, Trimestre, Turma,
)

# ──────────────────────────────────────────────────────────────
# View
# ──────────────────────────────────────────────────────────────
class ConfiguracoesEscolaView(DirectorAdminRequiredMixin, View):
    template_name = "configuracoes/configuracoes_escola.html"

    # ---------- GET ----------
    def get(self, request):
        try:
            step = min(max(int(request.GET.get("step", 1)), 1), 6)
        except ValueError:
            step = 1
        return render(request, self.template_name, self._contexto(step))

    def _contexto(self, step):
        tenant = _tenant()
        ano = AnoLectivo.objects.filter(e_atual=True).first()
        anos = AnoLectivo.objects.order_by("-data_inicio")
        trimestres = list(ano.trimestres.all()) if ano else []
        classes = list(Classe.objects.order_by("ordem", "designacao"))
        regras = {r.classe_id: r for r in RegraAvaliacao.objects.filter(ano_lectivo=ano)} if ano else {}
        cfg_fin = ConfiguracaoFinanceira.objects.filter(ano_lectivo=ano).first() if ano else None

        regras_lista = [{
            "classe": c,
            "existe": c.pk in regras,
            "form": RegraAvaliacaoForm(instance=regras.get(c.pk), prefix=f"c{c.pk.hex[:8]}"),
        } for c in classes]

        # Estado de cada passo + lista de verificação
        ok = {
            1: ano is not None,
            2: len(trimestres) == 3 and any(t.activo for t in trimestres),
            3: any(getattr(tenant, f) for f in (
                "periodo_inscricao", "periodo_matricula", "periodo_confirmacao")),
            4: bool(classes) and len(regras) >= len(classes),
            5: bool(cfg_fin and cfg_fin.valor_propina_padrao > 0),
            6: bool(tenant.email_remetente or tenant.multicaixa_entity or tenant.sms_provider),
        }
        checklist = [
            {"step": 1, "ok": ok[1], "txt": "Ano lectivo actual definido"},
            {"step": 2, "ok": len(trimestres) == 3, "txt": "3 trimestres criados"},
            {"step": 2, "ok": any(t.activo for t in trimestres), "txt": "Trimestre activo seleccionado"},
            {"step": 4, "ok": ok[4], "txt": f"Regras de avaliação ({len(regras)}/{len(classes)} classes)"},
            {"step": 5, "ok": ok[5], "txt": "Propina padrão definida"},
            {"step": 6, "ok": ok[6], "txt": "Pelo menos uma integração configurada"},
        ]
        obrigatorios = [ok[1], ok[2], ok[4], ok[5]]
        progresso = int(sum(obrigatorios) / len(obrigatorios) * 100)

        fin_initial = {}
        if cfg_fin is None:
            fin_initial = {"dia_vencimento": tenant.dia_vencimento_propina or 10,
                           "limite_bloqueio_meses": 3}

        return {
            "secao": "configuracoes",
            "step": step,
            "ano": ano,
            "anos": anos,
            "trimestres": trimestres,
            "tenant": tenant,
            "cfg_fin": cfg_fin,
            "regras_lista": regras_lista,
            "form_ano": AnoLectivoForm(prefix="ano"),
            "form_tri": TrimestreForm(prefix="tri", ano=ano),
            "form_cal": CalendarioForm(instance=tenant),
            "form_fin": FinanceiroForm(instance=cfg_fin, initial=fin_initial),
            "form_int": IntegracoesForm(instance=tenant),
            "steps_ok": ok,
            "checklist": checklist,
            "progresso": progresso,
            "n_turmas_sem_preco": Turma.objects.filter(
                ano_lectivo=ano, activo=True, preco_propina__isnull=True).count() if ano else 0,
        }

    # ---------- POST ----------
    def post(self, request):
        acoes = {
            "ano_salvar": self._ano_salvar,
            "ano_activar": self._ano_activar,
            "trimestre_salvar": self._trimestre_salvar,
            "trimestre_gerar": self._trimestre_gerar,
            "trimestre_activar": self._trimestre_activar,
            "trimestre_lancamento": self._trimestre_lancamento,
            "calendario_salvar": self._calendario_salvar,
            "regra_salvar": self._regra_salvar,
            "regra_padrao": self._regra_padrao,
            "financeiro_salvar": self._financeiro_salvar,
            "financeiro_aplicar_turmas": self._financeiro_aplicar_turmas,
            "integracoes_salvar": self._integracoes_salvar,
        }
        handler = acoes.get(request.POST.get("acao"))
        step = 1
        if handler is None:
            messages.error(request, "Acção inválida.")
        else:
            try:
                with transaction.atomic():
                    step = handler(request) or 1
            except Exception as exc:  # não expor detalhes técnicos ao utilizador
                messages.error(request, "Não foi possível concluir a operação. Tente novamente.")
                import logging
                logging.getLogger(__name__).exception("Configurações: %s", exc)
        return redirect(f"{reverse('configuracoes_escola')}?step={step}")

    # ---------- Passo 1: Ano lectivo ----------
    def _ano_salvar(self, request):
        pk = request.POST.get("ano_id")
        instancia = AnoLectivo.objects.filter(pk=pk).first() if pk else None
        form = AnoLectivoForm(request.POST, instance=instancia, prefix="ano")
        if not form.is_valid():
            messages.error(request, _erros(form))
            return 1
        ano = form.save()
        if not AnoLectivo.objects.filter(e_atual=True).exists():
            self._definir_actual(ano)
        _log(request, f"Ano lectivo {'actualizado' if instancia else 'criado'}: {ano.designacao}", ano)
        messages.success(request, f"Ano lectivo {ano.designacao} guardado.")
        return 2 if not instancia else 1

    def _definir_actual(self, ano):
        AnoLectivo.objects.exclude(pk=ano.pk).update(e_atual=False)
        ano.e_atual = True
        ano.save(update_fields=["e_atual"])
        tenant = _tenant()
        tenant.ano_lectivo_activo = ano
        tenant.save(update_fields=["ano_lectivo_activo"])

    def _ano_activar(self, request):
        ano = AnoLectivo.objects.filter(pk=request.POST.get("ano_id")).first()
        if not ano:
            messages.error(request, "Ano lectivo não encontrado.")
            return 1
        self._definir_actual(ano)
        _log(request, f"Ano lectivo actual alterado para {ano.designacao}", ano)
        messages.success(request, f"{ano.designacao} é agora o ano lectivo actual.")
        return 1

    # ---------- Passo 2: Trimestres ----------
    def _ano_actual_ou_erro(self, request):
        ano = AnoLectivo.objects.filter(e_atual=True).first()
        if not ano:
            messages.warning(request, "Defina primeiro o ano lectivo actual.")
        return ano

    def _trimestre_salvar(self, request):
        ano = self._ano_actual_ou_erro(request)
        if not ano:
            return 1
        designacao = request.POST.get("tri-designacao")
        existente = Trimestre.objects.filter(ano_lectivo=ano, designacao=designacao).first()
        form = TrimestreForm(request.POST, instance=existente, prefix="tri", ano=ano)
        if not form.is_valid():
            messages.error(request, _erros(form))
            return 2
        tri = form.save(commit=False)
        tri.ano_lectivo = ano
        tri.save()
        _log(request, f"Trimestre {tri.designacao} guardado ({ano.designacao})", tri)
        messages.success(request, f"{tri.designacao}.º trimestre guardado.")
        return 2

    def _trimestre_gerar(self, request):
        ano = self._ano_actual_ou_erro(request)
        if not ano:
            return 1
        total = (ano.data_fim - ano.data_inicio).days + 1
        parte = total // 3
        criados = 0
        for i in (1, 2, 3):
            ini = ano.data_inicio + timedelta(days=parte * (i - 1))
            fim = ano.data_fim if i == 3 else ini + timedelta(days=parte - 1)
            _, novo = Trimestre.objects.get_or_create(
                ano_lectivo=ano, designacao=i,
                defaults={"data_inicio": ini, "data_fim": fim, "lancamento_aberto": True},
            )
            criados += int(novo)
        if not Trimestre.objects.filter(ano_lectivo=ano, activo=True).exists():
            Trimestre.objects.filter(ano_lectivo=ano, designacao=1).update(activo=True)
        _log(request, f"Trimestres gerados automaticamente ({criados} novos)", ano)
        messages.success(request, f"{criados} trimestre(s) gerado(s) com datas distribuídas igualmente.")
        return 2

    def _trimestre_activar(self, request):
        ano = self._ano_actual_ou_erro(request)
        if not ano:
            return 1
        tri = Trimestre.objects.filter(pk=request.POST.get("trimestre_id"), ano_lectivo=ano).first()
        if not tri:
            messages.error(request, "Trimestre não encontrado.")
            return 2
        Trimestre.objects.filter(ano_lectivo=ano).update(activo=False)
        tri.activo = True
        tri.save(update_fields=["activo"])
        _log(request, f"Trimestre activo: {tri.designacao}.º", tri)
        messages.success(request, f"{tri.designacao}.º trimestre definido como activo.")
        return 2

    def _trimestre_lancamento(self, request):
        tri = Trimestre.objects.filter(pk=request.POST.get("trimestre_id")).first()
        if not tri:
            messages.error(request, "Trimestre não encontrado.")
            return 2
        tri.lancamento_aberto = not tri.lancamento_aberto
        tri.save(update_fields=["lancamento_aberto"])
        _log(request, f"Lançamento de notas {'aberto' if tri.lancamento_aberto else 'fechado'} — {tri.designacao}.º trimestre", tri)
        messages.success(request, f"Lançamento de notas {'aberto' if tri.lancamento_aberto else 'fechado'}.")
        return 2

    # ---------- Passo 3: Calendário ----------
    def _calendario_salvar(self, request):
        form = CalendarioForm(request.POST, instance=_tenant())
        if form.is_valid():
            form.save()
            _log(request, "Períodos do sistema actualizados", form.instance)
            messages.success(request, "Calendário do sistema actualizado.")
        else:
            messages.error(request, _erros(form))
        return 3

    # ---------- Passo 4: Avaliação ----------
    def _regra_salvar(self, request):
        ano = self._ano_actual_ou_erro(request)
        classe = Classe.objects.filter(pk=request.POST.get("classe_id")).first()
        if not ano or not classe:
            messages.error(request, "Ano lectivo ou classe inválidos.")
            return 4
        existente = RegraAvaliacao.objects.filter(ano_lectivo=ano, classe=classe).first()
        form = RegraAvaliacaoForm(request.POST, instance=existente, prefix=f"c{classe.pk.hex[:8]}")
        if not form.is_valid():
            messages.error(request, f"{classe}: {_erros(form)}")
            return 4
        regra = form.save(commit=False)
        regra.ano_lectivo, regra.classe = ano, classe
        regra.save()
        _log(request, f"Regras de avaliação guardadas — {classe}.ª classe ({ano.designacao})", regra)
        messages.success(request, f"Regras da {classe}.ª classe guardadas.")
        return 4

    def _regra_padrao(self, request):
        """Cria regras com os valores por defeito para classes ainda sem regra."""
        ano = self._ano_actual_ou_erro(request)
        if not ano:
            return 1
        n = 0
        for c in Classe.objects.all():
            _, novo = RegraAvaliacao.objects.get_or_create(ano_lectivo=ano, classe=c)
            n += int(novo)
        _log(request, f"Regras padrão criadas para {n} classe(s)", ano)
        messages.success(request, f"Regras padrão criadas para {n} classe(s). Ajuste-as conforme necessário.")
        return 4

    # ---------- Passo 5: Financeiro ----------
    def _financeiro_salvar(self, request):
        ano = self._ano_actual_ou_erro(request)
        if not ano:
            return 1
        existente = ConfiguracaoFinanceira.objects.filter(ano_lectivo=ano).first()
        form = FinanceiroForm(request.POST, instance=existente)
        if not form.is_valid():
            messages.error(request, _erros(form))
            return 5
        cfg = form.save(commit=False)
        cfg.ano_lectivo = ano
        cfg.save()
        tenant = _tenant()
        tenant.dia_vencimento_propina = cfg.dia_vencimento  # mantém as duas configs alinhadas
        tenant.save(update_fields=["dia_vencimento_propina"])
        _log(request, f"Configuração financeira guardada ({ano.designacao})", cfg)
        messages.success(request, "Configuração financeira guardada.")
        return 5

    def _financeiro_aplicar_turmas(self, request):
        ano = self._ano_actual_ou_erro(request)
        cfg = ConfiguracaoFinanceira.objects.filter(ano_lectivo=ano).first() if ano else None
        if not cfg:
            messages.warning(request, "Guarde primeiro a configuração financeira.")
            return 5
        turmas = Turma.objects.filter(ano_lectivo=ano, activo=True)
        n1 = turmas.filter(preco_propina__isnull=True).update(preco_propina=cfg.valor_propina_padrao)
        n2 = turmas.filter(preco_matricula__isnull=True).update(preco_matricula=cfg.taxa_matricula)
        _log(request, f"Preços padrão aplicados às turmas (propina: {n1}, matrícula: {n2})", cfg)
        messages.success(request, f"Preços aplicados: propina em {n1} turma(s), matrícula em {n2}. "
                                  f"Turmas com preço já definido não foram alteradas.")
        return 5

    # ---------- Passo 6: Integrações ----------
    def _integracoes_salvar(self, request):
        form = IntegracoesForm(request.POST, instance=_tenant())
        if form.is_valid():
            form.save()
            _log(request, "Integrações (SMTP/SMS/Multicaixa) actualizadas", form.instance)
            messages.success(request, "Integrações guardadas.")
        else:
            messages.error(request, _erros(form))
        return 6


configuracoes_escola = ConfiguracoesEscolaView.as_view()

@login_required
def dashboard(request):
    user = request.user
    
    if is_admin(user):
        return redirect('dashboard_diretor')
    elif is_professor(user):
        return redirect('professor:dashboard_professor')
    elif is_director(user):
        return redirect('dashboard_diretor')
    elif is_secretario(user):
        return redirect('dashboard_secretario')
    elif is_estudante(user):
        print('ols')
        return redirect('estudante:dashboard_estudante')
    elif is_candidato(user):
        return redirect('dashboard_candidato')
    else:
        messages.warning(request, 'Seu perfil não tem um dashboard específico.')
        return redirect('home')


def _get_ano_atual():

    ano = AnoLectivo.objects.filter(e_atual=True).first()

    return ano

@login_required
@role_required('director')
def dashboard_diretor(request):

    hoje = timezone.now().date()

    
    ano_lectivo = AnoLectivo.objects.filter(e_atual=True).first()

    total_alunos        = Aluno.objects.filter(status='Matriculado').count()
    total_professores   = Funcionario.objects.filter(tipo_funcionario='Professor', status='Activo').count()
    total_turmas        = Turma.objects.filter(Q(activo=True)).count()
    total_disciplinas   = Disciplina.objects.filter(Q(activo=True)).count()

    matriculas_ativas   = Matricula.objects.filter(Q(status='Activa')).count()
    inscricoes_pendentes = Inscricao.objects.filter(
        Q(ano_lectivo=ano_lectivo)
    ).count() if ano_lectivo else 0

    financeiro = ContaAluno.objects.all().aggregate(
        total_pago     = Sum('total_pago'),
        total_devido   = Sum('total_devido'),
        saldo_devedor  = Sum('saldo_devedor'),
    )
    
    contas_atrasadas  = ContaAluno.objects.filter(status='Atrasado').count()
    contas_bloqueadas = ContaAluno.objects.filter(status='Bloqueado').count()

    ultimas_matriculas = Matricula.objects.all().select_related(
        'aluno', 'turma', 'ano_lectivo'
    ).order_by('-data_matricula')[:10]

    # ── Matrículas dos últimos 6 meses (gráfico) ─
    matriculas_mensal = []
    for i in range(5, -1, -1):
        mes_ref = hoje.replace(day=1) - timedelta(days=i * 30)
        qtd = Matricula.objects.filter(
            
            data_matricula__year=mes_ref.year,
            data_matricula__month=mes_ref.month,
        ).count()
        matriculas_mensal.append({'mes': mes_ref.strftime('%b/%Y'), 'qtd': qtd})

    # ── Distribuição de alunos por curso ───────
    alunos_por_curso = (
        Matricula.objects
        .filter(status='Activa')
        .values('turma__curso__nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:6]
    )

    turmas = Turma.objects.prefetch_related('matriculas').all().order_by('designacao')
    professores = Funcionario.objects.filter(tipo_funcionario=Funcionario.TipoFuncionario.PROFESSOR).order_by('nome_completo')

    # ── Média geral de notas (ano lectivo actual) ─
    media_geral = None
    if ano_lectivo:
        media_geral = AvaliacaoContinua.objects.filter(
            trimestre__ano_lectivo=ano_lectivo,
        ).aggregate(media=Avg('valor'))['media']

    context = {
        'secao': 'dashboard',
        
        'ano_lectivo': ano_lectivo,
        'hoje': hoje,
        # KPIs
        'total_alunos': total_alunos,
        'total_professores': total_professores,
        'total_turmas': total_turmas,
        'total_disciplinas': total_disciplinas,
        'matriculas_ativas': matriculas_ativas,
        'inscricoes_pendentes': inscricoes_pendentes,
        # Financeiro
        'financeiro': financeiro,
        'contas_atrasadas': contas_atrasadas,
        'contas_bloqueadas': contas_bloqueadas,
        # Listas
        'ultimas_matriculas': ultimas_matriculas,
        'turmas': turmas,
        'professores': professores,
        # Gráficos
        'matriculas_mensal': json.dumps(matriculas_mensal),
        'alunos_por_curso': json.dumps(list(alunos_por_curso)),
        'media_geral': media_geral,
    }
    return render(request, 'director/index.html', context)


@login_required
def financeiro_dashboard(request):
  
    
    ano_lectivo_activo = _get_ano_atual()
    
    contas = ContaAluno.objects.filter(
        ano_lectivo=ano_lectivo_activo
    )
    
    total_a_receber=None
    total_recebido=None
    total_pendente=None
    
    if contas:
    
        total_a_receber = contas.aggregate(total=Sum('total_devido'))['total'] or Decimal('0')
        total_recebido = contas.aggregate(total=Sum('total_pago'))['total'] or Decimal('0')
        total_pendente = contas.aggregate(total=Sum('saldo_devedor'))['total'] or Decimal('0')
    
    contas_por_status = contas.values('status').annotate(
        total=Count('id'),
        valor=Sum('saldo_devedor')
    )
    
    hoje = timezone.now()
    meses_anteriores = []
    for i in range(6):
        mes = hoje - timedelta(days=30*i)
        meses_anteriores.append(mes.strftime('%Y-%m'))
    
    context = {
        'total_a_receber': total_a_receber,
        'total_recebido': total_recebido,
        'total_pendente': total_pendente,
        'contas_por_status': contas_por_status,
        'ano_lectivo_activo': ano_lectivo_activo,
    }
    
    return render(request, 'financeiro/dashboard.html', context)


@login_required
def financeiro_contas_list(request):
    
    
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    contas = ContaAluno.objects.filter(
        ano_lectivo=ano_lectivo_activo
    ).select_related('aluno')
    
    status = request.GET.get('status')
    if status:
        contas = contas.filter(status=status)
    
    search = request.GET.get('search')
    if search:
        contas = contas.filter(
            Q(aluno__nome_completo__icontains=search) |
            Q(aluno__numero_processo__icontains=search)
        )
    
    paginator = Paginator(contas, 20)
    page = request.GET.get('page')
    contas_page = paginator.get_page(page)
    
    context = {
        'contas': contas_page,
        'ano_lectivo_activo': ano_lectivo_activo,
    }
    
    return render(request, 'financeiro/contas_list.html', context)


@login_required
def financeiro_conta_detail(request, conta_id):
   
    conta = get_object_or_404(
        ContaAluno.objects.select_related('aluno', 'ano_lectivo'),
        id=conta_id
    )
    
    context = {
        'conta': conta,
    }
    
    return render(request, 'financeiro/conta_detail.html', context)

@login_required
def dashboard_professor(request):

    return render(request, 'director/../professores/templates/dashboard_prof.html')


 
def so_director_ou_admin(view):
    """Apenas superutilizadores, directores e administradores podem gerir utilizadores."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        u = request.user
        permitido = u.is_superuser or UsuarioRole.objects.filter(
            utilizador=u,
            role__nome__in=[Role.NomeRole.DIRECTOR, Role.NomeRole.ADMIN],
            role__is_active=True,
        ).exists()
        if not permitido:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper
 
 
@login_required
@role_required('admin')
def usuario_create(request):
    if request.method == "POST":
        form = UtilizadorCreateForm(request.POST)
        if form.is_valid():
            user = form.save(criado_por=request.user)
            messages.success(request, f"Utilizador «{user}» criado com sucesso.")
            return redirect("usuario_list")
        messages.error(request, "Corrija os erros assinalados e tente novamente.")
    else:
        form = UtilizadorCreateForm()
 
    return render(request, "gestao/usuario_form.html", {
        "form": form,
        "secao": "usuarios",   # mantém o menu "Pessoas e Acessos" aberto
    })

@login_required
@role_required('director','secretario')
def usuario_list(request) -> HttpResponse:
    
    usuarios = Utilizador.objects.all()

    context = {
        'secao': 'usuarios',
        'usuarios': usuarios
    }
    return render(request, 'usuario/list.html', context)

@login_required
@role_required('director','secretario')
def usuario_datail(request, usuario_id:str) -> HttpResponse:

    usuario = Utilizador.objects.get(id=usuario_id)

    context = {
        'secao': 'usuarios',
        'usuario': usuario
    }

    return render(request, 'usuario/detail.html', context)

@login_required
@role_required('director','secretario')
def usuario_edit(request, usuario_id:uuid):
    usuario = get_object_or_404(Utilizador, id=usuario_id)

    context = {
        'usuario': usuario,
        'erro': None,
        'sucesso': None
    }

    if request.method == 'POST':

        is_active = request.POST.get('status')

        try:

            if is_active == 'ativar':
                usuario.is_active = True
            elif is_active == 'desativar':
                usuario.is_active = False

            usuario.save()

            context.update(
                sucesso=f'O Estado do usuário foi atualizado para {is_active} !'
            )
            return render(request, 'usuario/edit.html', context)

        except Exception as e:
            context.update(
                erro='Houve erro ao atualizar o estado do usuário!'
            )
            return render(request, 'usuario/edit.html',  context)

    return render(request, 'usuario/edit.html', context)

@login_required
def lista_turmas(request):
 
    
    ano_id = request.GET.get('ano_lectivo')
    curso_id = request.GET.get('curso')

    turmas = (
        Turma.objects
        .all()
        .select_related('curso', 'classe', 'ano_lectivo', 'director_turma')
        .annotate(total_alunos=Count('matriculas', filter=Q(matriculas__status='Activa')))
        .order_by('classe__ordem', 'designacao')
    )

    if ano_id:
        turmas = turmas.filter(ano_lectivo_id=ano_id)
    if curso_id:
        turmas = turmas.filter(curso_id=curso_id)

    anos_lectivos = AnoLectivo.objects.all().order_by('-data_inicio')
    cursos = Curso.objects.filter(activo=True)

    context = {
        'secao': 'turmas',
        
        'turmas': turmas,
        'anos_lectivos': anos_lectivos,
        'cursos': cursos,
        'filtros': {'ano_id': ano_id, 'curso_id': curso_id},
    }
    return render(request, 'diretor/turmas/lista.html', context)


@login_required
def detalhe_turma(request, turma_id):
 
    
    turma = get_object_or_404(Turma, id=turma_id)

    alunos = Matricula.objects.filter(
        turma=turma, status='Activa'
    ).select_related('aluno').order_by('aluno__nome_completo')

    disciplinas = AtribuicaoDocente.objects.filter(
        turma=turma
    ).select_related('disciplina', 'professor')

    horarios = HorarioAula.objects.filter(
        turma=turma
    ).select_related('disciplina', 'professor').order_by('dia_semana', 'hora_inicio')

    # Média por disciplina na turma
    medias = (
        Nota.objects.filter(avaliacao__turma=turma)
        .values('avaliacao__disciplina__nome')
        .annotate(media=Avg('nota'))
        .order_by('-media')
    )

    context = {
        'secao': 'turmas',
        
        'turma': turma,
        'alunos': alunos,
        'disciplinas': disciplinas,
        'horarios': horarios,
        'medias': medias,
        'total_alunos': alunos.count(),
    }
    return render(request, 'diretor/turmas/detalhe.html', context)



@login_required
def turma_list(request):
  
    

    ano_lectivos = AnoLectivo.objects.all().order_by('-e_atual')
    ano_lectivo = _get_ano_atual()
    
    turmas = Turma.objects.all().select_related(
        'ano_lectivo', 'curso', 'classe'
    ).order_by('-ano_lectivo__e_atual', 'classe__ordem', 'designacao')
    
    ano_lectivo_id = request.GET.get('ano_lectivo')
    curso_id = request.GET.get('curso')
    classe_id = request.GET.get('classe')
    order_by = request.GET.get('order_by')
    
    if ano_lectivo_id:
        turmas = turmas.filter(ano_lectivo_id=ano_lectivo_id)
        ano_lectivo = AnoLectivo.objects.get(id=ano_lectivo_id)
    else:
        turmas = turmas.filter(ano_lectivo=ano_lectivo)

    if curso_id:
        turmas = turmas.filter(curso_id=curso_id)
    if classe_id:
        turmas = turmas.filter(classe_id=classe_id)
    
    if order_by:
        turmas = turmas.order_by(order_by)

    per_page = request.GET.get('per_page', 20)
    page = request.GET.get('page')

    paginator = Paginator(turmas, per_page)
    turmas_page = paginator.get_page(page)

    print(ano_lectivo_id)
    
    
    context = {
        'secao': 'turmas',
        'turmas': turmas_page,
        'ano_lectivos':ano_lectivos,
        'ano_lectivo': ano_lectivo,
        'ano_lectivo_id': ano_lectivo_id
    }
    
    return render(request, 'turmas/list.html', context)

@login_required
def turma_estudante_list(request, turma_id):
  
    
    
    turmas = Turma.objects.all().select_related(
        'ano_lectivo', 'curso', 'classe', 'director_turma'
    ).annotate(
        total_alunos=Count('matricula')
    ).order_by('-ano_lectivo__activo', 'classe__ordem', 'designacao')
    
    ano_lectivo_id = request.GET.get('ano_lectivo')
    curso_id = request.GET.get('curso')
    classe_id = request.GET.get('classe')
    turno = request.GET.get('turno')
    
    if ano_lectivo_id:
        turmas = turmas.filter(ano_lectivo_id=ano_lectivo_id)
    if curso_id:
        turmas = turmas.filter(curso_id=curso_id)
    if classe_id:
        turmas = turmas.filter(classe_id=classe_id)
    if turno:
        turmas = turmas.filter(turno=turno)
    
    anos_lectivos = AnoLectivo.objects.all()
    cursos = Curso.objects.filter(activo=True)
    classes = Classe.objects.all()
    
    context = {
        'turmas': turmas,
        'anos_lectivos': anos_lectivos,
        'cursos': cursos,
        'classes': classes,
    }
    
    return render(request, 'turmas/list.html', context)


@login_required
def turma_create(request):

    form = TurmaForm()
    
    if request.method == 'POST':
        form = TurmaForm(request.POST)
        
        if form.is_valid():
           
            turma = form.save()

            turma.save()
            
            return redirect('turma_detail', turma_id=turma.id)
            
        else:
            context = {
                'erro': 'Erro ao Criar turma, corrija os erros abaixo!',
                'secao': 'turmas',
                'form': form
            }
            
            return render(request, 'turmas/create.html', context)
    
    context = {
        'secao': 'turmas',
        'form': form
    }
    
    return render(request, 'turmas/create.html', context)

@login_required
def turma_update(request, turma_id):

    turma = Turma.objects.get(id=turma_id)

    
    
    form = TurmaEditForm(turma=turma)
    
    if request.method == 'POST':
        form = TurmaEditForm(request.POST, turma=turma)
        
        
        if form.is_valid():
           
            turma = form.save()

            turma.save()
            
            return redirect('turma_detail', turma_id=turma.id)
            
        else:
            context = {
                'erro': 'Erro ao atualizar turma, corrija os erros abaixo!',
                'form': form,
                'secao': 'turmas',
                'turma': turma
            }
            
            return render(request, 'turmas/edit.html', context)
    
    context = {

        'form': form,
        'secao': 'turmas',
        'turma': turma
    }
    
    return render(request, 'turmas/edit.html', context)

@login_required
@require_http_methods('POST')
def turma_delete(request, turma_id):

    turma = Turma.objects.get(id=turma_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao='delete',
        modulo='Turma',
        descricao=f'Turma: {turma.designacao} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    turma.delete()

    return redirect('turma_list')

@login_required
def turma_detail(request, turma_id):

    
    avaliacoes = AvaliacaoContinua.objects.all()

    turma = get_object_or_404(
        Turma.objects.select_related(
             'ano_lectivo', 'curso', 'classe'
        ),
        id=turma_id
    )
    
    total_alunos  = Matricula.objects.filter(
        turma=turma, 
        status='Activa'
    ).select_related('aluno').order_by('aluno__nome_completo').count()
    
    matriculas = Matricula.objects.filter(
        turma=turma
    ).select_related('aluno', 'turma')

    page = request.GET.get('page', 1)

    paginator = Paginator(matriculas, 20)
    matriculas = paginator.page(page)

    horarios = turma.horarios.all().select_related('disciplina', 'professor')
    
    context = {
        'turma': turma,
        'secao': 'turmas',
        'matriculas': matriculas,
        'horarios': horarios,
        'total_alunos': total_alunos,
        'avaliacoes': avaliacoes
    }
    
    return render(request, 'turmas/detail.html', context)


@login_required
def classe_list(request):
  
    
    
    classes = Classe.objects.all().order_by('designacao')
    
    designacao = request.GET.get('designacao')
    
    if designacao:
        classes = classes.filter(designacao=designacao)
    
    per_page = request.GET.get('per_page', 20)
    page = request.GET.get('page')

    paginator = Paginator(classes, per_page)
    classes_page = paginator.get_page(page)

    context = {
        'per_page': per_page,
        'secao': 'classes',
        'classes': classes_page,
        
    }
    
    return render(request, 'classes/list.html', context)

@login_required
def classe_create(request):

    form = CriarClasseForm()
    
    if request.method == 'POST':
        form = CriarClasseForm(request.POST)
        
        
        if form.is_valid():
           
            classe = form.save()

            classe.save()
            
            return redirect('classe_detail', classe_id=classe.id)
            
        else:
            context = {
                'secao': 'classes',
                'erro': 'Erro ao Criar classe, corrija os erros abaixo!',
                'form': form
            }
            
            return render(request, 'classes/create.html', context)
    
    context = {

        'secao': 'classes',
        'form': form
    }
    
    return render(request, 'classes/create.html', context)

@login_required
def classe_update(request, classe_id):

    classe = Classe.objects.get(id=classe_id)

    form = EditarClasseForm( instance=classe)
    
    if request.method == 'POST':
        form = EditarClasseForm(request.POST, instance=classe)
        
        
        if form.is_valid():
           
            classe = form.save()
            classe.save()
            
            return redirect('classe_detail', classe_id=classe.id)
            
        else:
            context = {
                'erro': 'Erro ao atualizar classe, corrija os erros abaixo!',
                'form': form,
                'secao': 'classes',
                'classe': classe
            }
            
            return render(request, 'classes/update.html', context)
    
    context = {

        'form': form,
        'secao': 'classes',
        'classe': classe
    }
    
    return render(request, 'classes/update.html', context)

@login_required
@require_http_methods('POST')
def classe_delete(request, classe_id):

    classe = Classe.objects.get(id=classe_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao='delete',
        modulo='Classe',
        descricao=f'Classe: {classe.designacao} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    classe.delete()

    return redirect('classe_list')

@login_required
def classe_detail(request, classe_id):

    classe = Classe.objects.get(id=classe_id)

    alunos = Matricula.objects.filter(turma__classe=classe)
    
    context = {
        'classe': classe,
        'secao': 'classes',
        'alunos': alunos
    }
    
    return render(request, 'classes/detail.html', context)


@login_required
def disciplina_list(request):
    
    disciplinas = Disciplina.objects.all().order_by('nome')
    
    busca = request.GET.get('busca')
    if busca:
        disciplinas = disciplinas.filter(
            Q(nome__icontains=busca) |
            Q(codigo__icontains=busca) |
            Q(nome_abreviado__icontains=busca)
        )
    
    per_page = request.GET.get('per_page', 20)
    page = request.GET.get('page')

    paginator = Paginator(disciplinas, per_page)
    disciplinas_page = paginator.get_page(page)

    context = {
        'secao': 'disciplinas',
        'disciplinas': disciplinas_page,
    }
    
    return render(request, 'disciplinas/list.html', context)

@login_required
def disciplina_create(request):

    form = CriarDisciplinaForm()

    if request.method == 'POST':

        form = CriarDisciplinaForm(request.POST)
        
        if form.is_valid():

            disciplina = form.save()

            disciplina.save()
            
            context = {
                'sucesso': 'Disciplina criada com sucesso!',
                'secao': 'disciplinas',
                'form': form
            }

            return redirect('disciplina_detail', disciplina.id)
            
        else:
            context = {
                'erro': 'Erro ao criar a Disciplina!',
                'secao': 'disciplinas',
                'form': form
            }

            return render(request, 'disciplinas/create.html', context)
    
    return render(request, 'disciplinas/create.html', {'form': form,'secao': 'disciplinas'})

@login_required
def disciplina_edit(request, disciplina_id):

    disciplina = Disciplina.objects.get(id=disciplina_id)
   
    

    form = EditarDisciplinaForm(instance=disciplina)

    if request.method == 'POST':

        form = EditarDisciplinaForm(request.POST, instance=disciplina)
        
        if form.is_valid():

            disciplina = form.save()

            disciplina.save()

            return redirect('disciplina_detail', disciplina_id=disciplina_id)
            
        else:
            context = {
                'erro': 'Erro ao atualizada a Disciplina!',
                'disciplina': disciplina,
                'secao': 'disciplinas',
                'form': form

            }

            return render(request, 'disciplinas/edit.html', context)
    
    return render(request, 'disciplinas/edit.html', {'form': form,'disciplina': disciplina,'secao': 'disciplinas',})


@login_required
def disciplina_detail(request, disciplina_id):

    
    ano_atual = _get_ano_atual()
   
    disciplina = get_object_or_404(
        Disciplina,
        id=disciplina_id
    )

    if request.method == 'POST':

        dados = json.loads(request.body)
        professor = dados.get('professor')
        turma = dados.get('turma')
        carga_horaria = dados.get('carga_horaria')
        action = request.GET.get('action')
        turma_id = request.GET.get('uuid')

        if action == 'edit' and turma_id:

            try:

                turma_disciplina = TurmaDisciplina.objects.get(id=turma_id)
                professor_obj = Funcionario.objects.get(id=professor)
                turma_obj = Turma.objects.get(id=turma)

                turma_disciplina.professor = professor_obj
                turma_disciplina.turma = turma_obj
                turma_disciplina.carga_horaria = carga_horaria


                turma_disciplina.save()

                return JsonResponse({'success': 'A troca de disciplina feita com sucesso'}, status=200)

            except Exception as e:
                print(e)

                return JsonResponse({'error': 'Houve um erro verifica os dados informado'}, status=500)

        else:
            try:

                TurmaDisciplina.objects.create(
                    disciplina=disciplina,
                    professor_id=professor,
                    turma_id=turma,
                    carga_horaria=carga_horaria,
                )

                return JsonResponse({'success': 'Disciplina atribuida com sucesso'}, status=200)

            except IntegrityError:

                return JsonResponse({'error': 'Essa disciplina já está associada a um professor!'}, status=500)
            
            except Exception  as e:

                return JsonResponse({'error': 'Houve um erro verifica os dados informado'}, status=500)

        
    else:

        turma_associadas = Turma.objects.filter(
            
            ano_lectivo = ano_atual
        )

        professores = Funcionario.objects.filter(
            
            tipo_funcionario='Professor',
            status='Activo'
        )
        
        
        turmas = AtribuicaoDocente.objects.filter(
            disciplina=disciplina,
        ).select_related('turma', 'professor')
        
        context = {
            'disciplina': disciplina,
            'turmas': turmas,
            'turma_associadas': turma_associadas,
            'professores': professores,
            'secao': 'disciplinas',
        }
        
        return render(request, 'disciplinas/detail.html', context)
    
@login_required
@require_http_methods('POST')
def disciplina_delete(request, disciplina_id):

    disciplina = Disciplina.objects.get(id=disciplina_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        
        utilizador=request.user,
        accao='delete',
        modulo='Disciplina',
        descricao=f'Disciplina: {disciplina.nome} eliminada',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    disciplina.delete()

    return redirect('disciplina_list')

@login_required
def curso_list(request):    
    
    cursos = Curso.objects.all().order_by('nome')

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(cursos, per_page)
    obj = paginator.page(page)

    context = {
        'secao': 'cursos',
        'cursos': obj,
    }
    
    return render(request, 'cursos/list.html', context)

@login_required
def curso_create(request):
   
    

    form = CriarCursoForm()

    if request.method == 'POST':

        form = CriarCursoForm(request.POST)
        
        if form.is_valid():

            curso = form.save()

            curso.save()
            
            return redirect('curso_detail', curso.id)
            
        else:
            context = {
                'erro': 'Erro ao criar a curso!',
                'secao': 'cursos',
                'form': form
            }

            return render(request, 'cursos/create.html', context)
    
    return render(request, 'cursos/create.html', {'form': form, 'secao': 'cursos',})

@login_required
def curso_update(request, curso_id):

    curso = Curso.objects.get(id=curso_id)
   
    

    form = EditarCursoForm(instance=curso)

    if request.method == 'POST':

        form = EditarCursoForm(request.POST, instance=curso)
        
        if form.is_valid():

            curso = form.save()

            curso.save()
            

            return redirect('curso_detail', curso.id)
            
        else:
            context = {
                'erro': 'Erro ao atualizada curso!',
                'secao': 'cursos',
                'form': form
            }

            return render(request, 'cursos/update.html', context)
    
    return render(request, 'cursos/update.html', {'form': form, 'curso': curso,'secao': 'cursos',})


@login_required
def curso_detail(request, curso_id):

    ano_atual = _get_ano_atual()
    
    curso = get_object_or_404(
        Curso,
        id=curso_id
    )
    
    turmas = Turma.objects.filter(
        curso=curso,
        
        ano_lectivo=ano_atual
    )

    total_alunos = Matricula.objects.filter(
        
        turma__curso = curso,
        ano_lectivo=ano_atual
    ).count()


    order_by = request.GET.get('order_by')

    if order_by:
        turmas = turmas.order_by(order_by)

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(turmas, per_page)
    obj = paginator.page(page)

    context = {
        'curso': curso,
        'secao': 'cursos',
        'total_alunos': total_alunos,
        'turmas': obj,
    }
    
    return render(request, 'cursos/detail.html', context)

@login_required
@require_http_methods('POST')
def curso_delete(request, curso_id):

    curso = Curso.objects.get(id=curso_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        
        utilizador=request.user,
        accao='delete',
        modulo='Curso',
        descricao=f'Curso: {curso.nome} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    curso.delete()

    return redirect('curso_list')

@login_required
def anoletivo_list(request):

    
    anoletivos = AnoLectivo.objects.all().order_by('-e_atual', '-designacao')
    
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(anoletivos, per_page)
    obj = paginator.page(page)

    context = {
        'secao': 'ano_letivos',
        'per_page': per_page,
        'anoletivos': obj,
    }
    
    return render(request, 'anoletivos/list.html', context)

@login_required
def anoletivo_create(request):
   
    

    form = CriarAnoLetivoForm()

    if request.method == 'POST':

        form = CriarAnoLetivoForm(request.POST)
        
        if form.is_valid():

            anoletivo = form.save()

            anoletivo.save()
            
            return redirect('anoletivo_detail', anoletivo.id)
            
        else:
            context = {
                'erro': 'Erro ao criar ano lectivo!',
                'secao': 'ano_letivos',
                'form': form
            }

            return render(request, 'anoletivos/create.html', context)
    
    return render(request, 'anoletivos/create.html', {'form': form, 'secao': 'ano_letivos',})

@login_required
def anoletivo_update(request, anoletivo_id):

    anoletivo = AnoLectivo.objects.get(id=anoletivo_id)
   
    

    form = EditarAnoLetivoForm(instance=anoletivo)

    if request.method == 'POST':

        form = EditarAnoLetivoForm(request.POST, instance=anoletivo)
        
        if form.is_valid():

            anoletivo = form.save()

            anoletivo.save()
            

            return redirect('anoletivo_detail', anoletivo.id)
            
        else:
            context = {
                'secao': 'ano_letivos',
                'erro': 'Erro ao atualizar ano lectivo!',
                'form': form,
                'anoletivo': anoletivo
            }

            return render(request, 'anoletivos/update.html', context)
    
    return render(request, 'anoletivos/update.html', {'form': form, 'anoletivo': anoletivo, 'secao': 'ano_letivos'})


@login_required
def anoletivo_detail(request, anoletivo_id):

    
   
    anoletivo = get_object_or_404(
        AnoLectivo,
        id=anoletivo_id
    )
    
    total_alunos = Matricula.objects.filter(
        ano_lectivo=anoletivo
    ).distinct('aluno').count()

    total_inscricao = Inscricao.objects.filter(
        ano_lectivo=anoletivo
    ).distinct('candidato').count()
    



    context = {
        'anoletivo': anoletivo,
        'total_inscricao': total_inscricao,
        'secao': 'ano_letivos',
        'total_alunos':total_alunos
    }
    
    return render(request, 'anoletivos/detail.html', context)

@login_required
def ano_lectivo_ativar(request, ano_id):
    """Ativar ano letivo"""
    ano_lectivo = get_object_or_404(AnoLectivo, id=ano_id)
    
    # Desativar outros anos
    AnoLectivo.objects.all().update(activo=False)
    
    # Ativar o selecionado
    ano_lectivo.activo = True
    ano_lectivo.save()
    
 
    messages.success(request, f'Ano letivo {ano_lectivo.designacao} ativado com sucesso!')
    return redirect('ano_lectivo_list')

@login_required
@require_http_methods('POST')
def anoletivo_delete(request, anoletivo_id):

    anoletivo = AnoLectivo.objects.get(id=anoletivo_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    LogAuditoria.objects.create(
        
        utilizador=request.user,
        accao='delete',
        modulo='AnoLectivo',
        descricao=f'Ano lectivo: {anoletivo.designacao} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    anoletivo.delete()

    return redirect('anoletivo_list')

@login_required
def periodo_list(request):

    
    periodos = Periodo.objects.all().order_by('-designacao')

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(periodos, per_page)
    obj = paginator.page(page)

    context = {
        'secao': 'periodos',
        'per_page': per_page,
        'periodos': obj,
    }
    
    return render(request, 'periodos/list.html', context)

@login_required
def periodo_create(request):
   
    

    form = CriarPeriodoForm()

    if request.method == 'POST':

        form = CriarPeriodoForm(request.POST)
        
        if form.is_valid():

            periodo = form.save()

            periodo.save()
            
            return redirect('periodo_detail', periodo.id)
            
        else:
            context = {
                'erro': 'Houve erro ao criar período!',
                'secao': 'periodos',
                'form': form
            }

            return render(request, 'periodos/create.html', context)
    
    return render(request, 'periodos/create.html', {'form': form, 'secao': 'periodos',})

@login_required
def periodo_detail(request, periodo_id):

    
   
    periodo = get_object_or_404(
        Periodo,
        id=periodo_id
    )
    
    total_alunos = Matricula.objects.filter(
        turma__periodo=periodo
    ).distinct('aluno').count()

    total_inscricao = Inscricao.objects.filter(
        periodo=periodo
    ).distinct('candidato').count()


    context = {
        'periodo': periodo,
        'total_inscricao': total_inscricao,
        'secao': 'periodos',
        'total_alunos':total_alunos
    }
    
    return render(request, 'periodos/detail.html', context)

@login_required
@role_required('director', 'secretario')
def trimestre_list(request)->HttpResponse:

    
    trimestres = Trimestre.objects.all().order_by('-activo', 'designacao')

    context = {
        'secao': 'trimestres',
        'trimestres':  trimestres
    }


    return render(request, 'trimestres/list.html', context)

@login_required
@role_required('director', 'secretario')
def trimestre_create(request):

    
    form = CriarTrimestreForm()

    context = {
        'secao': 'trimestres',
        'erro': None,
        'sucesso': None,
        'form': form
    }

    if request.method == 'POST':

        form = CriarTrimestreForm(request.POST)

        if form.is_valid():

            trimestre = form.save()

            try:
                with transaction.atomic():

                    if trimestre.activo:
                        Trimestre.objects.filter(activo=True).update(activo=False)

                    trimestre.save()

            except Exception as e:
                print(e)

                context.update(
                    erro='Houve erro ao criar o trimestre!',
                    form=form,
                )
                return render(request, 'trimestres/create.html', context)

            context.update(
                sucesso='Trimestre criado com sucesso!',
                form=form,
            )
            return render(request, 'trimestres/create.html', context)
        else:
            context.update(
                erro='Houve erro ao criar o trimestre!',
                form=form,
            )
            return render(request, 'trimestres/create.html', context)

    return render(request, 'trimestres/create.html', context)

@login_required
@role_required('director', 'secretario')
def trimestre_edit(request, trimestre_id:uuid):

    trimestre = get_object_or_404(Trimestre, id=trimestre_id)
    form = EditarTrimestreForm(trimestre=trimestre)

    context = {
        'secao': 'trimestres',
        'erro': None,
        'sucesso': None,
        'trimestre': trimestre,
        'form': form
    }

    if request.method == 'POST':

        form = EditarTrimestreForm(request.POST, trimestre=trimestre)

        if form.is_valid():

            trimestre = form.save()
            try:
                with transaction.atomic():

                    if trimestre.activo:
                        Trimestre.objects.filter(activo=True).update(activo=False)

                    trimestre.save()

            except Exception as e:

                context.update(
                    erro='Houve erro ao actualizar o trimestre!',
                    form=form,
                )
                return render(request, 'trimestres/edit.html', context)

            context.update(
                sucesso='Trimestre atualizado com sucesso!',
                form=form,
            )
            return render(request, 'trimestres/edit.html', context)
        else:
            context.update(
                erro='Houve erro ao actualizar o trimestre!',
                form=form,
            )
            return render(request, 'trimestres/edit.html', context)

    return render(request, 'trimestres/edit.html', context)

@login_required
@role_required('director', 'secretario')
def trimestre_detail(request, trimestre_id:uuid) -> HttpResponse:

    trimestre = get_object_or_404(Trimestre, id=trimestre_id)

    avalicao = AvaliacaoContinua.objects.filter(trimestre=trimestre)
    resultado = ResultadoTrimestral.objects.filter(trimestre=trimestre)

    context = {
        'avalicao': avalicao,
        'resultado': resultado,
        'trimestre': trimestre,
        'secao': 'trimestres'
    }

    return render(request, 'trimestres/detail.html', context)

@login_required
@role_required('director', 'secretario')
@require_http_methods(['POST'])
def trimestre_delete(request, trimestre_id:uuid):

    try:
        trimestre = get_object_or_404(Trimestre, id=trimestre_id)
        trimestre.delete()
    except Exception as e:
        return JsonResponse({'message': 'Erro ao eliminar o trimestre!'}, status=500)

    return JsonResponse({'message': 'Trimestre eliminado com sucesso!'}, status=200)

@login_required
def aluno_list(request):
    
    alunos = Aluno.objects.all().select_related('utilizador').order_by('nome_completo')
    
    search = request.GET.get('search')
    
    if search:
        alunos = alunos.filter(
            Q(bi__icontains=search) |
            Q(nome_completo__icontains=search) |
            Q(numero_estudante__icontains=search)
        )
    
    per_page = request.GET.get('per_page', 20)
    paginator = Paginator(alunos, per_page)
    page = request.GET.get('page', 1)
    alunos_page = paginator.get_page(page)
    
    context = {
        'alunos': alunos_page,
        'per_page': per_page,
        'search': search,
        'secao': 'alunos',
        'total_alunos': alunos.count(),
    }
    
    return render(request, 'alunos/list.html', context)


@login_required
def aluno_create(request):

    

    form = AlunoForm()

    if request.method == 'POST':

        form = AlunoForm(request.POST)

        if form.is_valid():

            aluno = form.save()

            aluno.save()
       
            context = {
                'sucesso': 'Aluno criado com sucesso!',
                 'form': form
            }

            return render(request, 'alunos/create.html', context)
        else:

            context = {
                'erro': 'Erro ao criar o Aluno!',
                'secao': 'alunos',
                 'form': form
            }

            return render(request, 'alunos/create.html', context)
        
    context = {
        'form': form
    }

    return render(request, 'alunos/create.html', context)


@login_required
def aluno_detail(request, aluno_id):

    

    aluno = get_object_or_404(Aluno, id=aluno_id)
    matriculas = Matricula.objects.filter(aluno=aluno).select_related(
        'ano_lectivo', 'turma'
    ).order_by('ano_lectivo__data_inicio')
    mat = Matricula.objects.filter(aluno=aluno).first()
    documentos = DocumentoAluno.objects.filter(aluno=aluno).order_by('-data_upload')
    conta = ContaAluno.objects.filter(aluno=aluno).first()


    turmas_ids = []

    for m in matriculas:
        turmas_ids.append(m.turma.id)

    turmas = Turma.objects.filter(curso=mat.turma.curso).exclude(id__in=turmas_ids)
    ano_lectivos = AnoLectivo.objects.all().order_by('e_atual')

    context = {
        'secao': 'alunos',
        'aluno': aluno,
        'turmas': turmas,
        'ano_lectivos': ano_lectivos,
        'matriculas': matriculas,
        'documentos': documentos,
        'conta': conta,
        'secao': 'alunos',
        'sucesso': None,
        'erro': None
    }

    if request.method == 'POST':

        turma = request.POST.get('turma')
        ano_lectivo = request.POST.get('ano_lectivo')

        if not turma or not ano_lectivo:
            context.update(
                erro=f'Os campos ano lectivo e turma são obrigatórios!'
            )

            return render(request, 'alunos/detail.html', context)

        try:

            with transaction.atomic():
                Matricula.objects.filter(aluno=aluno, status=Matricula.Status.ACTIVA).update(status=Matricula.Status.CONCLUIDA)

                matricula = Matricula(
                    aluno = aluno,
                    turma_id = turma,
                    ano_lectivo_id = ano_lectivo,
                    tipo_matricula = Matricula.TipoMatricula.RENOVACAO,
                    status = Matricula.Status.ACTIVA,
                    matriculado_por = request.user,
                )

                matricula.save()

                if matricula.turma.vagas_disponiveis:
                    matricula.turma.vagas_disponiveis -= 1

                    matricula.turma.save()

                context.update(
                    sucesso= f'O aluno {aluno.nome_completo} confirmado com sucesso!'
                )
                return redirect('aluno_detail', aluno_id=aluno_id)

        except IntegrityError as e:
            print(e)
            context.update(
                erro = f'Houve erro, O estudante {aluno.nome_completo} já está matriculado nesta turma ou neste ano lectivo!'
            )

            return render(request, 'alunos/detail.html', context)

    return render(request, 'alunos/detail.html', context)


@login_required
def aluno_update(request, aluno_id):

    aluno = get_object_or_404(Aluno, id=aluno_id)

    form = AlunoEditForm(aluno=aluno)
    
    if request.method == 'POST':

        form = AlunoEditForm(request.POST, aluno=aluno)

        if form.is_valid():

            aluno = form.save()
            aluno.save()

            
            return redirect('aluno_detail', aluno_id=aluno.id)
        
        else:

            context = {
                'aluno': aluno,
                'form': form,
                'secao': 'alunos',
                'erro': 'Erro ao atualizar dados do aluno!'
                }
            
            return render(request, 'alunos/update.html', context)
        
    context = {
        'aluno': aluno,
        'form': form,
        }
    return render(request, 'alunos/update.html', context)


@login_required
@require_http_methods('POST')
def aluno_delete(request, aluno_id):

    aluno = get_object_or_404(Aluno, id=aluno_id)
    
    if request.method == 'POST':
        aluno.status = 'Desistente'
        aluno.save()
        messages.success(request, 'Aluno desativado com sucesso!')
        return redirect('aluno_list')
    
    context = {'aluno': aluno}
    return render(request, 'alunos/delete.html', context)

@login_required
def lista_alunos(request):
    """Lista de alunos da escola com filtros."""
    
    status_f = request.GET.get('status', '')
    curso_f  = request.GET.get('curso', '')
    busca    = request.GET.get('q', '')

    alunos = (
        Aluno.objects
        .all()
        .order_by('nome_completo')
    )

    if status_f:
        alunos = alunos.filter(status=status_f)
    if curso_f:
        alunos = alunos.filter(matriculas__curso_id=curso_f)
    if busca:
        alunos = alunos.filter(
            Q(nome_completo__icontains=busca) |
            Q(numero_processo__icontains=busca) |
            Q(bi__icontains=busca)
        )

    cursos = Curso.objects.filter(activo=True)
    context = {
        'secao': 'alunos',
        
        'alunos': alunos,
        'cursos': cursos,
        'status_choices': Aluno.STATUS,
        'filtros': {'status': status_f, 'curso': curso_f, 'q': busca},
        'total': alunos.count(),
    }
    return render(request, 'diretor/alunos/lista.html', context)


@login_required
def detalhe_aluno(request, aluno_id):
    """Perfil completo do aluno: dados pessoais, matrículas, notas e documentos."""
    
    aluno = get_object_or_404(Aluno, id=aluno_id)

    matriculas   = aluno.matriculas.select_related('curso', 'turma', 'ano_lectivo').order_by('-data_matricula')
    documentos   = aluno.documentos.order_by('-data_upload')
    encarregados = AlunoEncarregado.objects.filter(aluno=aluno).select_related('encarregado')
    conta        = ContaAluno.objects.filter(aluno=aluno).select_related('ano_lectivo').first()

    # Notas do aluno agrupadas por disciplina
    notas = (
        Nota.objects
        .filter(aluno=aluno)
        .select_related('avaliacao__disciplina', 'avaliacao__tipo_avaliacao', 'avaliacao__turma')
        .order_by('avaliacao__disciplina__nome', 'avaliacao__data_realizacao')
    )
    media_aluno = notas.aggregate(media=Avg('nota'))['media']

    context = {
        'secao': 'alunos',
        
        'aluno': aluno,
        'matriculas': matriculas,
        'documentos': documentos,
        'encarregados': encarregados,
        'conta': conta,
        'notas': notas,
        'media_aluno': media_aluno,
    }
    return render(request, 'diretor/alunos/detalhe.html', context)

@login_required
def funcionario_create(request):

    form = FuncionarioForm()

    if request.method == 'POST':

        form = FuncionarioForm(request.POST)

        if form.is_valid():

            funcionario = form.save()

            try:
                with transaction.atomic():
                    
                    funcionario.save()
                   
                    role = None
                    
                    if funcionario.tipo_funcionario == Funcionario.TipoFuncionario.PROFESSOR:
                        role, created = Role.objects.get_or_create(nome=Role.NomeRole.PROFESSOR)
                    elif funcionario.tipo_funcionario == Funcionario.TipoFuncionario.ADMINISTRATIVO:
                        role, created = Role.objects.get_or_create(nome='secretario')

                    utilizador = Utilizador(
                        email=funcionario.email,
                        username=funcionario.email,
                        nome_completo=funcionario.nome_completo
                    )

                    utilizador.set_password('123467890')
                    utilizador.save()

                    userRole = UsuarioRole(
                        role=role,
                        utilizador=utilizador
                    )

                    userRole.atribuido_por = request.user

                    userRole.save()

                    funcionario.utilizador = utilizador

                    funcionario.save()

                    context = {
                        'secao': 'funcionarios',
                        'sucesso': 'Funcionário criado com sucesso!',
                         'form': form
                    }

                    return redirect('funcionario_create')
            except Exception as e:

                context = {
                    'secao': 'funcionarios',
                    'erro': 'Erro ao criar o funcionário!',
                    'form': form
                }

                return render(request, 'funcionarios/create.html', context)
        else:

            context = {
                'secao': 'funcionarios',
                'erro': 'Erro ao criar o funcionário!',
                 'form': form
            }

            return render(request, 'funcionarios/create.html', context)
        
    context = {
        'secao': 'funcionarios',
        'form': form
    }

    return render(request, 'funcionarios/create.html', context)

@login_required
def funcionario_list(request):
   
    
    
    funcionarios = (
        Funcionario.objects
        .all()
        .annotate(
            total_disciplinas=Count('atribuicao__disciplina', distinct=True),
            total_turmas=Count('atribuicao', distinct=True),
        )
        .order_by('nome_completo')
    )
    
   
    search = request.GET.get('search')
    if search:
        funcionarios = funcionarios.filter(
            Q(nome_completo__icontains=search) |
            Q(numero_agente__icontains=search) |
            Q(especialidade__icontains=search)
        )
    
    per_page = request.GET.get('per_page', 20)
    paginator = Paginator(funcionarios, per_page)
    page = request.GET.get('page', 1)
    funcionarios_page = paginator.get_page(page)
    
    context = {
        'secao': 'funcionarios',
        
        'per_page':  per_page,
        'funcionarios': funcionarios_page,
        'status_choices': Funcionario.Status,
        'total': funcionarios.count(),
    }
    
    return render(request, 'funcionarios/list.html', context)



@login_required
def funcionario_edit(request, funcionario_id):

    funcionario = Funcionario.objects.get(id=funcionario_id)

    form = FuncionarioEditForm(funcionario=funcionario)

    if request.method == 'POST':

        form = FuncionarioEditForm(request.POST,funcionario=funcionario)

        if form.is_valid():

            funcionario = form.save()

            try:
                with transaction.atomic():
                    funcionario.save()
                    
                    if not funcionario.utilizador:
                        role = None
                                            
                        if funcionario.tipo_funcionario == Funcionario.TipoFuncionario.PROFESSOR:
                            role, created = Role.objects.get_or_create(nome=Role.NomeRole.PROFESSOR)
                        elif funcionario.tipo_funcionario == Funcionario.TipoFuncionario.ADMINISTRATIVO:
                            role, created = Role.objects.get_or_create(nome='secretario')
    
                        utilizador = Utilizador(
                            email=funcionario.email,
                            username=funcionario.email,
                            nome_completo=funcionario.nome_completo
                        )
    
                        utilizador.set_password('123467890')
                        utilizador.save()
    
                        userRole = UsuarioRole(
                            role=role,
                            utilizador=utilizador
                        )
    
                        userRole.atribuido_por = request.user
    
                        userRole.save()
    
                        funcionario.utilizador = utilizador
                        
                        funcionario.save()
                        
                    else:
                    
                        funcionario.utilizador.email = funcionario.email
                        funcionario.utilizador.username = funcionario.email
                        funcionario.utilizador.save()

                    context = {
                        'secao': 'funcionarios',
                        'sucesso': 'Funcionário atualizado com sucesso!',
                        'form': form,
                        'funcionario': funcionario,
                    }

                    return redirect('funcionario_detail', funcionario.id)
            except Exception as e:
                
                context = {
                    'secao': 'funcionarios',
                    'erro': 'Erro ao atualizar o funcionário!',
                    'funcionario': funcionario,
                    'form': form
                }

                return render(request, 'funcionarios/edit.html', context)

        else:

            context = {
                'secao': 'funcionarios',
                'erro': 'Erro ao atualizar o funcionário!',
                'funcionario': funcionario,
                'form': form
            }

            return render(request, 'funcionarios/edit.html', context)
        
    context = {
        'secao': 'funcionarios',
        'funcionario': funcionario,
        'form': form
    }

    return render(request, 'funcionarios/edit.html', context)

@login_required
def funcionario_detail(request, funcionario_id):

    funcionario = get_object_or_404(Funcionario, id=funcionario_id)
    disciplinas = Disciplina.objects.all()
    turmas    = Turma.objects.all()
    
    
    disciplinas_atribuidas = AtribuicaoDocente.objects.filter(professor=funcionario).select_related('disciplina')

    config = TenantConfiguracao.objects.all().first()
    
    ano_lectivo_activo = _get_ano_atual()
    
    if request.method == 'POST':
    
        dados = json.loads(request.body)
        disciplina = dados.get('disciplina')
        turma = dados.get('turma')
        action = request.GET.get('action')
        turma_id = request.GET.get('uuid')

        if action == 'edit' and turma_id:

            try:

                docente_disciplina = AtribuicaoDocente.objects.get(id=funcionario_id)
                disciplina_obj = Disciplina.objects.get(id=disciplina)
                turma_obj = Turma.objects.get(id=turma)

                docente_disciplina.disciplina = disciplina_obj
                docente_disciplina.turma = turma_obj


                docente_disciplina.save()

                return JsonResponse({'success': 'A troca de professor feita com sucesso'}, status=200)

            except Exception as e:

                return JsonResponse({'error': 'Houve um erro verifica os dados informado'}, status=500)

        else:

            try:

                AtribuicaoDocente.objects.create(
                    professor=funcionario,
                    disciplina_id=disciplina,
                    turma_id=turma,
                )

                return JsonResponse({'success': 'Disciplina atribuida com sucesso'}, status=200)

            except IntegrityError as e:

                return JsonResponse({'error': 'Essa disciplina já está associada a um professor!'}, status=500)
            
            except Exception  as e:

                return JsonResponse({'error': 'Houve um erro verifica os dados informado'}, status=500)

        
    else:
    
        horario = HorarioAula.objects.filter(professor=funcionario).select_related(
            'turma', 'disciplina'
        ).order_by('dia_semana', 'hora_inicio')
        
        context = {
            'secao': 'funcionarios',
            'funcionario': funcionario,
            'disciplinas': disciplinas,
            'disciplinas_atribuidas': disciplinas_atribuidas,
            'turmas': turmas,
            'horario': horario,
        }
        
        return render(request, 'funcionarios/detail.html', context)

@login_required
@require_http_methods('POST')
def funcionario_delete(request, funcionario_id):

    funcionario = Funcionario.objects.get(id=funcionario_id)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao='delete',
        modulo='Funcionario',
        descricao=f'Funcionario: {funcionario.nome_completo} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    funcionario.delete()

    return redirect('funcionario_list')


@login_required
def detalhe_professor(request, funcionario_id):
    """Perfil do professor: disciplinas, turmas e carga horária."""
    
    professor = get_object_or_404(Funcionario, id=funcionario_id)

    disciplinas   = AtribuicaoDocente.objects.filter(
        professor=professor
    ).select_related('disciplina')

    # total_alunos = Matricula.objects.filter(
    #     turma__curso=curso
    # ).count()

    context = {
        'secao': 'professores',
        # 'total_alunos': total_alunos,
        'professor': professor,
        'disciplinas': disciplinas,
        # 'turmas_atrib': turmas_atrib,
    }
    return render(request, 'diretor/funcionarios/detalhe.html', context)


# ══════════════════════════════════════════════
# 5. AVALIAÇÕES E NOTAS
# ══════════════════════════════════════════════

@login_required
def painel_avaliacoes(request):
    """Visão geral das avaliações lançadas por turma e período."""
    
    turma_id   = request.GET.get('turma')
    periodo_id = request.GET.get('periodo')

    avaliacoes = (
        Avaliacao.objects
        .all()
        .select_related('turma__classe', 'disciplina', 'professor', 'periodo', 'tipo_avaliacao')
        .order_by('-data_realizacao')
    )

    if turma_id:
        avaliacoes = avaliacoes.filter(turma_id=turma_id)
    if periodo_id:
        avaliacoes = avaliacoes.filter(periodo_id=periodo_id)

    # Médias por turma
    medias_turma = (
        Nota.objects
        .all()
        .values('avaliacao__turma__designacao', 'avaliacao__turma__classe__designacao')
        .annotate(media=Avg('nota'), total_notas=Count('id'))
        .order_by('-media')
    )

    turmas   = Turma.objects.filter(activo=True).select_related('classe', 'curso')

    context = {
        'secao': 'avaliacoes',
        
        'avaliacoes': avaliacoes[:30],
        'medias_turma': list(medias_turma),
        'turmas': turmas,
        'filtros': {'turma_id': turma_id, 'periodo_id': periodo_id},
    }
    return render(request, 'diretor/avaliacoes/painel.html', context)


# ══════════════════════════════════════════════
# 6. MATRÍCULAS E INSCRIÇÕES
# ══════════════════════════════════════════════

@login_required
def painel_matriculas(request):
    """Gestão de matrículas e inscrições da escola."""
    
    ano_id    = request.GET.get('ano_lectivo')
    status_f  = request.GET.get('status', '')

    matriculas = (
        Matricula.objects
        .all()
        .select_related('aluno', 'curso', 'turma', 'ano_lectivo')
        .order_by('-data_matricula')
    )

    if ano_id:
        matriculas = matriculas.filter(ano_lectivo_id=ano_id)
    if status_f:
        matriculas = matriculas.filter(status=status_f)

    # Estatísticas rápidas
    stats = {
        'total':       matriculas.count(),
        'ativas':      matriculas.filter(status='Activa').count(),
        'canceladas':  matriculas.filter(status='Cancelada').count(),
        'transferidas':matriculas.filter(status='Transferida').count(),
        'concluidas':  matriculas.filter(status='Concluída').count(),
    }

    por_curso = (
        matriculas.values('curso__nome')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    anos_lectivos = AnoLectivo.objects.all().order_by('-data_inicio')

    context = {
        'secao': 'matriculas',
        
        'matriculas': matriculas[:50],
        'stats': stats,
        'por_curso': list(por_curso),
        'anos_lectivos': anos_lectivos,
        'status_choices': Matricula.STATUS,
        'filtros': {'ano_id': ano_id, 'status': status_f},
    }
    return render(request, 'diretor/matriculas/painel.html', context)


# ══════════════════════════════════════════════
# 7. FINANCEIRO DA ESCOLA
# ══════════════════════════════════════════════

@login_required
def painel_financeiro(request):
    """Resumo financeiro: contas dos alunos, cobranças e inadimplência."""
    
    ano_id   = request.GET.get('ano_lectivo')
    status_f = request.GET.get('status', '')

    contas = ContaAluno.objects.all().select_related('aluno', 'ano_lectivo')

    if ano_id:
        contas = contas.filter(ano_lectivo_id=ano_id)
    if status_f:
        contas = contas.filter(status=status_f)

    resumo = contas.aggregate(
        total_pago    = Sum('total_pago'),
        total_devido  = Sum('total_devido'),
        saldo_devedor = Sum('saldo_devedor'),
    )
    por_status = (
        contas.values('status')
        .annotate(quantidade=Count('id'), valor=Sum('saldo_devedor'))
        .order_by('status')
    )

    # Alunos com maior saldo devedor
    top_devedores = contas.filter(saldo_devedor__gt=0).order_by('-saldo_devedor')[:10]

    anos_lectivos = AnoLectivo.objects.all().order_by('-data_inicio')

    context = {
        'secao': 'financeiro',
        
        'resumo': resumo,
        'por_status': list(por_status),
        'top_devedores': top_devedores,
        'contas': contas[:40],
        'anos_lectivos': anos_lectivos,
        'status_choices': ContaAluno.STATUS,
        'filtros': {'ano_id': ano_id, 'status': status_f},
    }
    return render(request, 'diretor/financeiro/painel.html', context)

@login_required
def horario_turma(request, turma_id):
    """Horário da turma"""
    turma = get_object_or_404(Turma, id=turma_id)
    
    horarios = HorarioAula.objects.filter(turma=turma).select_related(
        'disciplina', 'professor'
    ).order_by('dia_semana', 'hora_inicio')
    
    # Organizar por dia da semana
    dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
    horario_organizado = {}
    
    for dia in dias:
        horario_organizado[dia] = horarios.filter(dia_semana=dia)
    
    context = {
        'turma': turma,
        'horario_organizado': horario_organizado,
    }
    
    return render(request, 'horarios/turma.html', context)


@login_required
def horario_professor(request, professor_id=None):

    if professor_id:
        professor = get_object_or_404(Professor, id=professor_id)
    else:
        if not hasattr(request.user, 'professor'):
            messages.error(request, 'Você não é um professor.')
            return redirect('dashboard_admin')
        professor = request.user.professor
    
    horarios = HorarioAula.objects.filter(professor=professor).select_related(
        'turma', 'disciplina'
    ).order_by('dia_semana', 'hora_inicio')
    
    # Organizar por dia da semana
    dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
    horario_organizado = {}
    
    for dia in dias:
        horario_organizado[dia] = horarios.filter(dia_semana=dia)
    
    context = {
        'professor': professor,
        'horario_organizado': horario_organizado,
    }
    
    return render(request, 'horarios/professor.html', context)


@login_required
def horario_create(request, turma_id):
    """Criar horário para turma"""
    turma = get_object_or_404(Turma, id=turma_id)
    
    if request.method == 'POST':
        # Processar criação de múltiplos horários
        messages.success(request, 'Horário criado com sucesso!')
        return redirect('horario_turma', turma_id=turma.id)
    
    # Disciplinas e professores da turma
    disciplinas_professores = TurmaDisciplinaProfessor.objects.filter(
        turma=turma
    ).select_related('disciplina', 'professor')
    
    context = {
        'turma': turma,
        'disciplinas_professores': disciplinas_professores,
    }
    
    return render(request, 'horarios/create.html', context)


# ══════════════════════════════════════════════
# 10. CONFIGURAÇÕES DA ESCOLA
# ══════════════════════════════════════════════

# @login_required
# def configuracoes_escola(request):
    

#     anos_lectivos = AnoLectivo.objects.all().order_by('-e_atual')

#     form = ConfiguracaoForm()

#     context = {
#         'secao': 'configuracoes',
        
#         'anos_lectivos': anos_lectivos,
#         'form': form
#     }
#     return render(request, 'configuracoes/configuracao.html', context)

# @login_required
# def periodo_avaliativo_list(request, ano_id):
#     """Lista de períodos avaliativos"""
#     ano_lectivo = get_object_or_404(AnoLectivo, id=ano_id)
#     periodos = PeriodoAvaliativo.objects.filter(ano_lectivo=ano_lectivo).order_by('numero_periodo')
    
#     context = {
#         'ano_lectivo': ano_lectivo,
#         'periodos': periodos,
#     }
    
#     return render(request, 'configuracoes/periodo_list.html', context)


@login_required
def periodo_avaliativo_create(request, ano_id):
    """Criar período avaliativo"""
    ano_lectivo = get_object_or_404(AnoLectivo, id=ano_id)
    
    if request.method == 'POST':
        # Processar criação
        messages.success(request, 'Período avaliativo criado com sucesso!')
        return redirect('periodo_avaliativo_list', ano_id=ano_lectivo.id)
    
    context = {
        'ano_lectivo': ano_lectivo,
    }
    
    return render(request, 'configuracoes/periodo_create.html', context)


@login_required
def tipo_avaliacao_list(request):
    """Lista de tipos de avaliação"""
    
    tipos = TipoAvaliacao.objects.all().order_by('designacao')
    
    context = {
        'tipos': tipos,
    }
    
    return render(request, 'configuracoes/tipo_avaliacao_list.html', context)


# ══════════════════════════════════════════════
# 11. RELATÓRIOS DO DIRECTOR
# ══════════════════════════════════════════════

@login_required
def relatorio_desempenho(request):
    """Relatório de desempenho académico da escola."""
    
    turma_id   = request.GET.get('turma')
    periodo_id = request.GET.get('periodo')

    notas_qs = Nota.objects.all()
    if turma_id:
        notas_qs = notas_qs.filter(avaliacao__turma_id=turma_id)
    if periodo_id:
        notas_qs = notas_qs.filter(avaliacao__periodo_id=periodo_id)

    media_escola = notas_qs.aggregate(media=Avg('nota'))['media']

    por_disciplina = (
        notas_qs.values('avaliacao__disciplina__nome')
        .annotate(media=Avg('nota'), total=Count('id'))
        .order_by('-media')
    )
    por_turma = (
        notas_qs.values(
            'avaliacao__turma__designacao',
            'avaliacao__turma__classe__designacao',
        )
        .annotate(media=Avg('nota'), total_alunos=Count('aluno', distinct=True))
        .order_by('-media')
    )
    # Taxa de aprovação (nota >= nota_minima_aprovacao)
    
    nota_min = 10.0

    total_notas    = notas_qs.count()
    notas_aprovadas = notas_qs.filter(nota__gte=nota_min).count()
    taxa_aprovacao  = (notas_aprovadas / total_notas * 100) if total_notas else 0

    turmas   = Turma.objects.filter(activo=True).select_related('classe', 'curso')
   
    context = {
        'secao': 'relatorios',
        
        'media_escola': media_escola,
        'taxa_aprovacao': taxa_aprovacao,
        'por_disciplina': list(por_disciplina),
        'por_turma': list(por_turma),
        'turmas': turmas,
        'filtros': {'turma_id': turma_id, 'periodo_id': periodo_id},
    }
    return render(request, 'diretor/relatorios/desempenho.html', context)


# ══════════════════════════════════════════════
# 12. ENDPOINT JSON — gráficos AJAX
# ══════════════════════════════════════════════

@login_required
def api_stats_diretor(request):
    """Dados JSON para os gráficos do dashboard do director."""
    
    hoje = date.today()

    matriculas_mensal = []
    for i in range(5, -1, -1):
        mes_ref = hoje.replace(day=1) - timedelta(days=i * 30)
        qtd = Matricula.objects.filter(
            
            data_matricula__year=mes_ref.year,
            data_matricula__month=mes_ref.month,
        ).count()
        matriculas_mensal.append({'mes': mes_ref.strftime('%b/%Y'), 'qtd': qtd})

    alunos_curso = list(
        Matricula.objects.filter(status='Activa')
        .values('curso__nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:6]
    )

    data = {
        'totais': {
            'alunos':      Aluno.objects.filter(status='Matriculado').count(),
            'professores': Funcionario.objects.filter(status='Activo').count(),
            'turmas':      Turma.objects.filter(activo=True).count(),
        },
        'matriculas_mensal': matriculas_mensal,
        'alunos_por_curso':  alunos_curso,
    }
    return JsonResponse(data)

@login_required
@require_http_methods(['POST'])
def api_atribuir_acesso_professor(request, professor_id:uuid):


    prof = Funcionario.objects.get(id=professor_id)
    role, created = None, None

    if prof.tipo_funcionario == Funcionario.TipoFuncionario.PROFESSOR:
        role, created = Role.objects.get_or_create(nome=Role.NomeRole.PROFESSOR)
    elif prof.tipo_funcionario == Funcionario.TipoFuncionario.ADMINISTRATIVO:
        role, created = Role.objects.get_or_create(nome='secretario')

    try:
        with transaction.atomic():
            usuario = Utilizador(
                nome_completo=prof.nome_completo,
                email=prof.email,
                username=prof.email,
                criado_por=request.user
            )

            if usuario.username == prof.utilizador.username:
                return JsonResponse({'message': 'Este usuário já existe!'}, status=500)
                
            usuario.set_password('1234567890')
            usuario.save()
            

            UsuarioRole.objects.create(
                role=role,
                utilizador=usuario,
                atribuido_por=request.user
            )

            prof.utilizador = usuario
            prof.save()

            return JsonResponse({'message': 'Acesso concedido com sucesso!'}, status=200)
    
    except Exception as e:

        return JsonResponse({'message': 'Houve erro ao conceder acesso!'}, status=500)
