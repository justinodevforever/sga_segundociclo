from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, Avg
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from decimal import Decimal
import calendar
import json
from app.db.models import *

from .models import (
    ContaAluno, PropinaMensal, Pagamento,
    LogFinanceiro, ConfiguracaoFinanceira, MESES
)
from .forms import (
    ContaAlunoForm, PagamentoForm, PropinaMensalForm,
    FiltroContaForm, ConfiguracaoFinanceiraForm
)
from .utils import gerar_recibo_pdf, gerar_relatorio_pdf


@login_required
def dashboard_financeiro(request):
    hoje = timezone.now().date()

    # Totais gerais
    totais = ContaAluno.objects.aggregate(
        total_devido=Sum('total_devido'),
        total_pago=Sum('total_pago'),
        total_saldo=Sum('saldo_devedor'),
    )
    total_devido  = totais['total_devido']  or Decimal('0')
    total_pago    = totais['total_pago']    or Decimal('0')
    total_saldo   = totais['total_saldo']   or Decimal('0')

    # Contagem por status
    status_counts = dict(
        ContaAluno.objects.values('status')
        .annotate(n=Count('id'))
        .values_list('status', 'n')
    )

    # Pagamentos recentes
    pagamentos_recentes = (
        Pagamento.objects
        .select_related('conta_aluno__aluno', 'registado_por')
        .order_by('-data_pagamento', '-data_criacao')[:8]
    )

    # Propinas vencidas este mês
    propinas_vencidas = PropinaMensal.objects.filter(
        status='atrasado'
    ).select_related('conta_aluno__aluno').count()

    # Pagamentos por mês (últimos 6 meses)
    pagamentos_mensais = []
    for i in range(5, -1, -1):
        mes_ref = hoje.month - i
        ano_ref = hoje.year
        while mes_ref <= 0:
            mes_ref += 12
            ano_ref -= 1
        total_mes = Pagamento.objects.filter(
            data_pagamento__year=ano_ref,
            data_pagamento__month=mes_ref
        ).aggregate(t=Sum('valor'))['t'] or Decimal('0')
        pagamentos_mensais.append({
            'mes': calendar.month_abbr[mes_ref],
            'total': float(total_mes),
        })

    # Contas bloqueadas recentes
    contas_bloqueadas = (
        ContaAluno.objects
        .filter(status='bloqueado')
        .select_related('aluno', 'ano_lectivo')
        .order_by('-saldo_devedor')[:5]
    )
    print('kkkkkkkkkkkkkk')

    context = {
        'secao': 'financeiro',
        'total_devido': total_devido,
        'total_pago': total_pago,
        'total_saldo': total_saldo,
        'status_counts': status_counts,
        'pagamentos_recentes': pagamentos_recentes,
        'propinas_vencidas': propinas_vencidas,
        'pagamentos_mensais': pagamentos_mensais,
        'contas_bloqueadas': contas_bloqueadas,
        'total_contas': ContaAluno.objects.count(),
        'hoje': hoje,
    }
    return render(request, 'financeiro/dashboard.html', context)


# ─────────────────────────────────────────────────────────
#  CONTAS DOS ALUNOS
# ─────────────────────────────────────────────────────────
@login_required
def conta_list(request):
    qs = (
        ContaAluno.objects
        .select_related('aluno', 'ano_lectivo')
        .prefetch_related('propinas', 'pagamentos')
        .order_by('-ano_lectivo', 'aluno__nome_completo')
    )
    
    anos_lectivos = AnoLectivo.objects.all()


    bi = request.GET.get('bi', '')
    ano_id = request.GET.get('ano_letivo', '')
    ano_ale = None

    if bi:
        qs = qs.filter(aluno__bi=bi)
    if ano_id:
        qs = qs.filter(ano_lectivo_id=ano_id)
        ano_ale = AnoLectivo.objects.get(id=ano_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    context = {
        'secao': 'contas',
        'contas': page,
        'bi': bi,
        'total_contas': qs.count(),
        'ano_ale': ano_ale,
        'anos_lectivos':anos_lectivos
    }
    return render(request, 'financeiro/conta_list.html', context)


@login_required
def conta_detail(request, pk):
    conta = get_object_or_404(
        ContaAluno.objects
        .select_related('aluno', 'ano_lectivo')
        .prefetch_related('propinas', 'pagamentos__registado_por'),
        pk=pk
    )
    propinas = conta.propinas.order_by('mes')
    pagamentos = conta.pagamentos.order_by('-data_pagamento')
    logs = conta.logs.select_related('usuario').order_by('-data')[:20]

    context = {
        'secao': 'contas',
        'conta': conta,
        'propinas': propinas,
        'pagamentos': pagamentos,
        'logs': logs,
        'pode_exame': conta.pode_fazer_exame(),
        'pode_matricula': conta.pode_matricular(),
        'pode_notas': conta.pode_ver_notas(),
    }
    return render(request, 'financeiro/conta_detail.html', context)


@login_required
def conta_create(request):
    if request.method == 'POST':
        form = ContaAlunoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                conta = form.save(commit=False)
                conta.total_devido = conta.valor_propina_mensal * 10
                conta.save()
                _gerar_propinas(conta, request)
                LogFinanceiro.objects.create(
                    conta_aluno=conta,
                    acao='conta_criada',
                    descricao=f'Conta criada para {conta.aluno} — {conta.ano_lectivo}',
                    usuario=request.user,
                    dados_extras={'valor_mensal': float(conta.valor_propina_mensal)},
                )
            messages.success(request, f'Conta criada com sucesso para {conta.aluno}!')
            return redirect('conta_detail', pk=conta.pk)
    else:
        form = ContaAlunoForm()

    return render(request, 'financeiro/conta_form.html', {
        'secao': 'contas', 'form': form, 'acao': 'Criar'
    })


@login_required

def conta_edit(request, pk):
    conta = get_object_or_404(ContaAluno, pk=pk)
    if request.method == 'POST':
        form = ContaAlunoForm(request.POST, instance=conta)
        if form.is_valid():
            form.save()
            messages.success(request, 'Conta actualizada com sucesso!')
            return redirect('conta_detail', pk=conta.pk)
    else:
        form = ContaAlunoForm(instance=conta)

    return render(request, 'financeiro/conta_form.html', {
        'secao': 'contas', 'form': form, 'conta': conta, 'acao': 'Editar'
    })

@login_required
@require_http_methods('POST')
def conta_delete(request, pk):

    conta = ContaAluno.objects.get(id=pk)

    user = request.user

    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao='delete',
        modulo='ContaAluno',
        descricao=f'ContaAluno: {conta.aluno.nome_completo} eliminado',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    conta.delete()
    
    return redirect('conta_list')
    
@login_required
def pagamento_create(request, conta_pk=None):
    conta = None
    if conta_pk:
        conta = get_object_or_404(ContaAluno, pk=conta_pk)

    if request.method == 'POST':
        form = PagamentoForm(request.POST, conta_aluno_id=conta_pk)
        if form.is_valid():
            with transaction.atomic():
                pagamento = form.save(commit=False)
                pagamento.registado_por = request.user
                pagamento.save()

                LogFinanceiro.objects.create(
                    conta_aluno=pagamento.conta_aluno,
                    acao='pagamento',
                    descricao=(
                        f'Pagamento de {pagamento.valor} Kz registado. '
                        f'Recibo: {pagamento.numero_recibo}'
                    ),
                    usuario=request.user,
                    dados_extras={
                        'valor': float(pagamento.valor),
                        'recibo': pagamento.numero_recibo,
                        'metodo': pagamento.metodo_pagamento,
                    },
                )
            messages.success(
                request,
                f'Pagamento registado! Recibo: {pagamento.numero_recibo}'
            )
            return redirect('recibo_detalhe', numero=pagamento.numero_recibo)
    else:
        form = PagamentoForm(conta_aluno_id=conta_pk)

    context = {
        'secao': 'financeiro',
        'form': form,
        'conta': conta,
    }
    return render(request, 'financeiro/pagamento_form.html', context)


@login_required
def pagamento_list(request):
    qs = (
        Pagamento.objects
        .select_related('conta_aluno__aluno', 'registado_por')
        .order_by('-data_pagamento', '-data_criacao')
    )
    busca = request.GET.get('busca', '').strip()
    if busca:
        qs = qs.filter(
            Q(numero_recibo__icontains=busca) |
            Q(conta_aluno__aluno__nome__icontains=busca)
        )

    totais = qs.aggregate(total=Sum('valor'))
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'financeiro/pagamento_list.html', {
        'secao': 'financeiro',
        'pagamentos': page,
        'busca': busca,
        'total_geral': totais['total'] or Decimal('0'),
    })


@login_required
def recibo_detalhe(request, numero):
    pagamento = get_object_or_404(
        Pagamento.objects.select_related(
            'conta_aluno__aluno', 'conta_aluno__ano_lectivo', 'registado_por'
        ),
        numero_recibo=numero
    )
    qr_base64 = pagamento.gerar_qr_code()
    return render(request, 'financeiro/recibo.html', {
        'secao': 'financeiro',
        'pagamento': pagamento,
        'qr_base64': qr_base64,
    })


@login_required
def recibo_pdf(request, numero):
    pagamento = get_object_or_404(
        Pagamento.objects.select_related(
            'conta_aluno__aluno', 'conta_aluno__ano_lectivo', 'registado_por'
        ),
        numero_recibo=numero
    )
    return gerar_recibo_pdf(request, pagamento)


def validar_recibo(request, numero):
    
    pagamento = get_object_or_404(
        Pagamento.objects.select_related('conta_aluno__aluno'),
        numero_recibo=numero
    )
    return render(request, 'financeiro/validar_recibo.html', {
        'pagamento': pagamento,
        'valido': True,
    })


# ─────────────────────────────────────────────────────────
#  PROPINAS
# ─────────────────────────────────────────────────────────
@login_required
def propinas_conta(request, conta_pk):
    conta = get_object_or_404(
        ContaAluno.objects.select_related('aluno', 'ano_lectivo'),
        pk=conta_pk
    )
    propinas = conta.propinas.order_by('mes')
    return render(request, 'financeiro/propinas.html', {
        'secao': 'financeiro',
        'conta': conta,
        'propinas': propinas,
    })


# ─────────────────────────────────────────────────────────
#  RELATÓRIOS
# ─────────────────────────────────────────────────────────
@login_required
def relatorio_financeiro(request):
    hoje = timezone.now().date()
    ano_id = request.GET.get('ano_lectivo')

    contas = ContaAluno.objects.select_related('aluno', 'ano_lectivo')
    if ano_id:
        contas = contas.filter(ano_lectivo_id=ano_id)

    totais = contas.aggregate(
        total_devido=Sum('total_devido'),
        total_pago=Sum('total_pago'),
        total_saldo=Sum('saldo_devedor'),
        total_contas=Count('id'),
    )

    por_status = list(
        contas.values('status')
        .annotate(n=Count('id'), total=Sum('saldo_devedor'))
        .order_by('status')
    )

    if request.GET.get('exportar') == 'pdf':
        return gerar_relatorio_pdf(request, contas, totais, por_status)

    return render(request, 'financeiro/relatorio.html', {
        'secao': 'financeiro',
        'totais': totais,
        'por_status': por_status,
        'contas': contas.order_by('-saldo_devedor')[:50],
        'hoje': hoje,
    })


# ─────────────────────────────────────────────────────────
#  API JSON (para AJAX)
# ─────────────────────────────────────────────────────────
@login_required
def api_conta_info(request, conta_pk):
    conta = get_object_or_404(ContaAluno, pk=conta_pk)
    return JsonResponse({
        'id': conta.pk,
        'aluno': str(conta.aluno),
        'total_devido': float(conta.total_devido),
        'total_pago': float(conta.total_pago),
        'saldo_devedor': float(conta.saldo_devedor),
        'status': conta.status,
        'pode_exame': conta.pode_fazer_exame(),
        'pode_matricula': conta.pode_matricular(),
    })


# ─────────────────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────
def _gerar_propinas(conta, request):
    """Gera as 12 propinas mensais para uma conta."""
    try:
        config = ConfiguracaoFinanceira.objects.get(
            ano_lectivo=conta.ano_lectivo
        )
        dia_venc = config.dia_vencimento
    except ConfiguracaoFinanceira.DoesNotExist:
        dia_venc = 10

    ano = conta.ano_lectivo.ano_inicio if hasattr(conta.ano_lectivo, 'ano_inicio') else timezone.now().year

    propinas = []
    for mes_num, mes_nome in MESES:
        import datetime
        ultimo_dia = calendar.monthrange(ano, mes_num)[1]
        dia = min(dia_venc, ultimo_dia)
        try:
            data_venc = datetime.date(ano, mes_num, dia)
        except ValueError:
            data_venc = datetime.date(ano, mes_num, ultimo_dia)

        propinas.append(PropinaMensal(
            conta_aluno=conta,
            mes=mes_num,
            valor=conta.valor_propina_mensal,
            data_vencimento=data_venc,
            status='pendente',
        ))

    PropinaMensal.objects.bulk_create(propinas)
    conta.total_devido = conta.valor_propina_mensal * 10
    conta.save(update_fields=['total_devido', 'saldo_devedor'])