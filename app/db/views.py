from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
from .models import *
from .forms import *
from app.authenticate.models import *
from .decorators import *
from app.director.views import _get_ano_atual
from django.db import transaction,IntegrityError
from .permissions import *
from app.financa.models import *


@login_required
def dashboard(request):
    user = request.user

    if is_admin(user):
        return redirect('dashboard_administrador')
    elif is_professor(user):
        return redirect('dashboard_professor')
    elif is_secretario(user):
        return redirect('dashboard_diretor')
    elif is_director(user):
        return redirect('dashboard_diretor')
    else:
        messages.warning(request, 'Seu perfil não tem um dashboard específico.')
        return redirect('home')

@login_required
def dashboard_diretor(request):
  
    
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    # Estatísticas gerais
    total_alunos = Aluno.objects.filter( status='Matriculado').count()
    print(total_alunos)
    total_professores = Funcionario.objects.filter( status='Activo').count()
    total_turmas = Turma.objects.filter( ano_lectivo=ano_lectivo_activo, activo=True).count()
    total_cursos = Curso.objects.filter( activo=True).count()
    
    # Matrículas recentes
    matriculas_recentes = Matricula.objects.filter(
        ano_lectivo=ano_lectivo_activo
    ).select_related('aluno', 'turma').order_by('-data_matricula')[:10]
    
    # Alunos por turma
    alunos_por_turma = Turma.objects.filter(
        
        ano_lectivo=ano_lectivo_activo
    ).annotate(total_alunos=Count('matricula')).values('designacao', 'classe__designacao', 'total_alunos')
    
    # Situação financeira
    contas_atrasadas = ContaAluno.objects.filter(
        ano_lectivo=ano_lectivo_activo,
        status='Atrasado'
    ).count()
    
    total_receber = ContaAluno.objects.filter(
        ano_lectivo=ano_lectivo_activo
    ).aggregate(total=Sum('saldo_devedor'))['total'] or Decimal('0')
    
    context = {
        'total_alunos': total_alunos,
        'total_professores': total_professores,
        'total_turmas': total_turmas,
        'total_cursos': total_cursos,
        'matriculas_recentes': matriculas_recentes,
        'alunos_por_turma': alunos_por_turma,
        'contas_atrasadas': contas_atrasadas,
        'total_receber': total_receber,
        'ano_lectivo_activo': ano_lectivo_activo,
    }
    
    return render(request, 'dashboard/diretor.html', context)


@login_required
def dashboard_professor(request):
    
    professor = request.user.funcionario
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    minhas_turmas = AtribuicaoDocente.objects.filter(
        professor=professor,
        ano_lectivo=ano_lectivo_activo
    ).select_related('turma', 'disciplina').distinct()
    
    
    hoje = timezone.now()
    dia_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'][hoje.weekday()]
    
    aulas_hoje = HorarioAula.objects.filter(
        professor=professor,
        dia_semana=dia_semana
    ).select_related('turma', 'disciplina').order_by('hora_inicio')
    
    avaliacoes_pendentes = Avaliacao.objects.filter(
        professor=professor,
    ).annotate(
        notas_lancadas=Count('nota')
    ).order_by('-data_realizacao')[:10]
    
    context = {
        'minhas_turmas': minhas_turmas,
        'aulas_hoje': aulas_hoje,
        'avaliacoes_pendentes': avaliacoes_pendentes,
        'total_turmas': minhas_turmas.count(),
    }
    
    return render(request, 'dashboard/professor.html', context)


@login_required
def dashboard_aluno(request):

    aluno = request.user.aluno
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    matricula = Matricula.objects.filter(
        aluno=aluno,
        ano_lectivo=ano_lectivo_activo,
        status='Activa'
    ).select_related('turma', 'turma__classe', 'turma__curso').first()
    
    if not matricula:
        messages.warning(request, "Você não possui matrícula ativa neste ano letivo.")
        return render(request, 'dashboard/aluno.html', {'matricula': None})
    
    horario = HorarioAula.objects.filter(
        turma=matricula.turma
    ).select_related('disciplina', 'professor').order_by('dia_semana', 'hora_inicio')
    
   
    conta = ContaAluno.objects.filter(
        aluno=aluno,
        ano_lectivo=ano_lectivo_activo
    ).first()
    
   
    context = {
        'matricula': matricula,
        'horario': horario,
        'conta': conta,
    }
    
    return render(request, 'dashboard/aluno.html', context)


def _get_inscricao_aprovada(bi:str, curso):

    try:

        inscricao = Inscricao.objects.filter(
            candidato__bi=bi.strip(),
            curso_id=curso
        ).first()

    except Inscricao.DoesNotExist:
        return None

    return (
        Inscricao.objects.filter(
            candidato__bi=bi.strip(),
            curso_id=curso,
            status=Inscricao.Status.APROVADA
        ).first()
    )


@login_required
def matricula_list(request):
    
    matriculas = Matricula.objects.filter(
        ~Q(tipo_matricula='inscricao')
    ).select_related(
        'aluno', 'ano_lectivo', 'turma', 'turma__curso', 'turma__classe'
    ).order_by('-data_matricula')
    
    ano_lectivo_id = request.GET.get('ano_lectivo')
    turma_id = request.GET.get('turma')
    busca = request.GET.get('busca')
    
    if ano_lectivo_id:
        matriculas = matriculas.filter(ano_lectivo_id=ano_lectivo_id)

    if turma_id:
        matriculas = matriculas.filter(turma_id=turma_id)
    
    if busca:
        matriculas = matriculas.filter(
            Q(aluno__nome_completo__icontains=busca) |
            Q(numero_matricula__icontains=busca) |
            Q(aluno__numero_processo__icontains=busca)
        )
    
    order_by = request.GET.get('nome_completo', '-data_matricula')
    matriculas = matriculas.order_by(order_by)

    per_page = request.GET.get('per_page', 20)
    page = request.GET.get('page')

    paginator = Paginator(matriculas, per_page)
    matriculas_page = paginator.get_page(page)

    anos_lectivos = AnoLectivo.objects.all()
    turmas = Turma.objects.filter( activo=True)
    

    context = {
        'matriculas': matriculas_page,
        'anos_lectivos': anos_lectivos,
        'turmas': turmas,
        'total': matriculas.count(),
        'per_page': per_page,
        'busca': busca,
        'ano_lectivo_id': ano_lectivo_id,
        'turma_id': turma_id,
    }
    
    return render(request, 'matriculas/list.html', context)


@login_required
def matricula_create(request):
   
    
    cursos = Curso.objects.all()
    
    context = {
        'step': 'buscar',
        'cursos': cursos,
        'inscricao': None,
        'candidato': None,
        'form': None,
        'sucesso': None,
        'erro': None,
        'secao': 'matriculas'
    }

    if request.method == 'POST':

        step = request.POST.get('step', 'buscar')

        if step == 'buscar':

            bi = request.POST.get('bi', '')
            curso = request.POST.get('curso', '')

            if not curso or not bi:

                context.update(
                    erro='Os campos B.I e Curso são obrigatórios!'
                )

                return render(request, 'matriculas/create.html', context)

            inscricao = _get_inscricao_aprovada(bi, curso)

            if inscricao == None:

                context.update(
                    erro=f'O candidato com B.I: {bi} não foi encontrado no ano lectivo {_get_ano_atual()}'
                )

                return render(request, 'matriculas/create.html', context)

            turmas = Turma.objects.filter(
                curso=inscricao.curso,
                ano_lectivo=inscricao.ano_lectivo
            )

            form = MatriculaForm(turmas=turmas)

            context.update(
                step='confirmar',
                inscricao=inscricao,
                candidato=inscricao.candidato,
                form=form
            )

            return render( request, 'matriculas/create.html', context)

        elif step == 'confirmar':

            inscricao_id = request.POST.get('inscricao_id')

            inscricao = get_object_or_404(
                Inscricao.objects.select_related('curso', 'candidato', 'ano_lectivo'),
                pk=inscricao_id
            )

            form = MatriculaForm(request.POST)

            if Aluno.objects.filter( bi=inscricao.candidato.bi).exists():
                context.update(
                    form=form,
                    inscricao=inscricao,
                    candidato=inscricao.candidato,
                    step='confirmar',
                    erro=f'Houve erro, O estudante {inscricao.candidato.nome_completo} já está matriculado!'
                )

                return render(request, 'matriculas/create.html', context)


            if form.is_valid():

                matricula = form.save()

                try:

                    with transaction.atomic():
                        
                        ano = timezone.now().year

                        ultimo = Aluno.objects.filter(
                            numero_estudante__startswith=ano
                        ).count()

                        numero_estudante = f'{ano}{str(ultimo + 1).zfill(5)}'
                        
                        aluno = Aluno(
                            
                            numero_estudante=numero_estudante,
                            nome_completo=inscricao.candidato.nome_completo,
                            nome_pai=inscricao.candidato.nome_pai,
                            nome_mae=inscricao.candidato.nome_mae,
                            data_nascimento=inscricao.candidato.data_nascimento,
                            naturalidade=inscricao.candidato.naturalidade,
                            telefone=inscricao.candidato.telefone,
                            bi=inscricao.candidato.bi,
                            emitido_em=inscricao.candidato.emitido_em,
                            data_expiracao_bi=inscricao.candidato.data_expiracao_bi,
                            data_emissao_bi=inscricao.candidato.data_emissao_bi,
                            genero=inscricao.candidato.genero,
                            provincia=inscricao.candidato.provincia,
                            municipio=inscricao.candidato.municipio,
                            bairro=inscricao.candidato.bairro,
                        )

                        aluno.save()

                        matricula.aluno = aluno
                        matricula.ano_lectivo = inscricao.ano_lectivo
                        matricula.tipo_matricula = Matricula.TipoMatricula.NOVA
                        matricula.status = Matricula.Status.ACTIVA
                        matricula.matriculado_por = request.user

                        matricula.save()

                        if matricula.turma.vagas_disponiveis:
                            matricula.turma.vagas_disponiveis -= 1

                            matricula.turma.save()

                        context.update(
                            sucesso=f'O estudante {inscricao.candidato.nome_completo} matriculado com sucesso!'
                        )

                        return render(request, 'matriculas/create.html', context)

                except IntegrityError as e:

                    context.update(
                        form=form,
                        inscricao=inscricao,
                        candidato=inscricao.candidato,
                        step='confirmar',
                        erro= f'Houve erro, O estudante {inscricao.candidato.nome_completo} já está matriculado nesta turma!'
                    )

                    return render(request, 'matriculas/create.html', context)
            else:
                context.update(
                    form=form,
                    inscricao=inscricao,
                    candidato=inscricao.candidato,
                    step='confirmar',
                    erro=f'Houve erro ao matricular o estudante!'
                )

                return render(request, 'matriculas/create.html', context)


    return render(request, 'matriculas/create.html', context)


@login_required
def matricula_update(request, matricula_id):
   
    matricula = Matricula.objects.get(id=matricula_id)
    form = MatriculaEditForm(matricula=matricula)
    
    if request.method == 'POST':
        form = MatriculaEditForm(request.POST, matricula=matricula)
        
        if form.is_valid():

            turma = Turma.objects.get(id=matricula.turma.id)

            matr, aluno = form.save()

            aluno.save()

            matr.save()

            if matr.turma.id != turma.id:
                turma_nova = Turma.objects.get(id=matr.turma.id)
                turma.vagas_disponiveis += 1
                turma_nova.vagas_disponiveis -= 1

                turma_nova.save()
                turma.save()

            context = {
                'sucesso': f'Erro, ao atualizar a matrícula!',
                'matricula': matricula,
                'form': form
            }
            return redirect('matricula_detail', matricula_id=matricula.id)
            
        else:
            context = {
                'erro': f'Erro, ao atualizar a matrícula!',
                'matricula': matricula,
                'form': form,
            }
            return render( request, 'matriculas/update.html', context)
    
    context = {
        'form': form,
        'matricula': matricula,
        
    }
    
    return render(request, 'matriculas/update.html', context)


@login_required
def matricula_detail(request, matricula_id):
   
    matricula = get_object_or_404(
        Matricula.objects.select_related(
            'aluno', 'ano_lectivo', 'turma', 'turma__curso', 
            'turma__classe', 'matriculado_por'
        ),
        id=matricula_id
    )
    
    encarregados = matricula.aluno.encarregados.all()
    
    context = {
        'matricula': matricula,
        'encarregados': encarregados,
    }
    
    return render(request, 'matriculas/detail.html', context)

@login_required
def matricula_update_status(request) -> HttpResponse:

    
    cursos = Curso.objects.all()

    status = request.GET.get('t')

    context = {
        'step': 'buscar',
        'cursos': cursos,
        'matricula': None,
        'aluno': None,
        'form': None,
        'status':status,
        'turmas':None,
        'secao': 'matriculas'
    }

    ano_letivo = _get_ano_atual()

    if request.method == 'POST':

        step = request.POST.get('step', 'buscar')

        if step == 'buscar':

            bi = request.POST.get('bi', '')
            curso = request.POST.get('curso', '')

            if not curso or not bi:
                context.update(
                    erro='Os campos B.I e Curso são obrigatórios!'
                )

                return render(request, 'matriculas/matricula_update.html', context)

            matricula = Matricula.objects.filter(
                aluno__bi=bi,
                turma__curso_id=curso
            ).first()

            if matricula == None:
                context.update(
                    erro=f'O aluno com B.I: {bi} não foi encontrado no ano lectivo {_get_ano_atual()}'
                )

                return render(request, 'matriculas/matricula_update.html', context)

            turmas = Turma.objects.filter(
                curso=matricula.turma.curso,
                ano_lectivo=_get_ano_atual()
            )

            context.update(
                step='confirmar',
                matricula=matricula,
                aluno=matricula.aluno,
                turmas=turmas

            )

            return render(request, 'matriculas/matricula_update.html', context)

        elif step == 'confirmar':

            matricula_id = request.POST.get('matricula_id')

            matricula = get_object_or_404(
                Matricula.objects.select_related('turma__curso', 'aluno', 'ano_lectivo'),
                pk=matricula_id
            )

            turmas = Turma.objects.filter(
                curso=matricula.turma.curso,
                ano_lectivo=_get_ano_atual()
            )

            context.update(
                matricula=matricula,
                aluno=matricula.aluno,
                step='confirmar',
                turmas=turmas

            )

            return render(request, 'matriculas/matricula_update.html', context)

    return render(request, 'matriculas/matricula_update.html', context)

@login_required
def trancar_matricula(request, matricula_id:uuid):

    matricula = get_object_or_404( Matricula,pk=matricula_id )

    try:

        with transaction.atomic():

            matricula.status = Matricula.Status.TRANCAMENTO
            matricula.matriculado_por = request.user
            matricula.save()
            print(matricula_id)

            return redirect('aluno_detail', aluno_id=matricula.aluno.id)

    except Exception as e:
        print(e)
        return redirect('aluno_detail', aluno_id=matricula.aluno.id)


@login_required
def reactivar_matricula(request, matricula_id: uuid):
    matricula = get_object_or_404(Matricula, pk=matricula_id)

    try:

        with transaction.atomic():

            matricula.status = Matricula.Status.ACTIVA
            matricula.matriculado_por = request.user
            matricula.save()
            print(matricula_id)

            return redirect('aluno_detail', aluno_id=matricula.aluno.id)

    except Exception as e:
        print(e)
        return redirect('aluno_detail', aluno_id=matricula.aluno.id)


@login_required
def cancelar_matricula(request, matricula_id:uuid):

    matricula = get_object_or_404( Matricula,pk=matricula_id )

    try:

        with transaction.atomic():

            matricula.status = Matricula.Status.CANCELADA
            matricula.matriculado_por = request.user
            matricula.save()

            return redirect('aluno_detail', aluno_id=matricula.aluno.id)

    except Exception as e:

        
        messages.error('Houve erro ao trancar matrícula!')
        

        return redirect('aluno_detail', aluno_id=matricula.aluno.id)

@login_required
@require_http_methods(['POST'])
def reingresso_matricula(request, matricula_id:uuid) -> HttpResponse:

    
    ano_lectivo = _get_ano_atual()

    turma = request.POST.get('turma')
    matricula = None

    context={
        'step': 'confirmar',
        'secao': 'matriculas',
        'sucesso': None,
        'erro': None,
        'matricula': matricula,
        'aluno': None,
        'turmas': None,
        'status': 'reingresso',
    }

    try:

        with transaction.atomic():

            matricula = Matricula.objects.create(
                
                aluno=matricula.aluno,
                ano_lectivo=ano_lectivo,
                turma_id=turma,
                status=Matricula.Status.ACTIVA,
                tipo_matricula=Matricula.TipoMatricula.NOVA,
                matriculado_por=request.user,
            )

            turmas = Turma.objects.filter(
                curso=matricula.turma.curso,
                ano_lectivo=_get_ano_atual()
            )

            context.update(
                sucesso=f'Matricula do {matricula.aluno.nome_completo} foi activa com sucesso!',
                matricula=matricula,
                aluno=matricula.aluno,
                turmas=turmas,
                step='confirmar'
            )

            return render(request, 'matriculas/matricula_update.html', context)
    except IntegrityError:

        turmas = Turma.objects.filter(
            curso=matricula.turma.curso,
            ano_lectivo=_get_ano_atual()
        )

        context.update(
            erro='Houve erro, o aluno já tem matricula nesta turma ou neste ano lectivo!',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)

    except Exception as e:

        turmas = Turma.objects.filter(
            curso=matricula.turma.curso,
            ano_lectivo=_get_ano_atual()
        )
        context.update(
            erro='Houve erro ao activar matrícula!',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)

    return render(request, 'matriculas/matricula_update.html', context)

@login_required
@require_http_methods(['POST'])
def transferencia_matricula(request, matricula_id:uuid) -> HttpResponse:

    
    ano_lectivo = _get_ano_atual()
    cursos = Curso.objects.all()

    turma = request.POST.get('turma')
    print(turma)
    matricula = None

    context={
        'step': 'confirmar',
        'cursos':cursos,
        'secao': 'matriculas',
        'sucesso': None,
        'erro': None,
        'matricula': matricula,
        'aluno': None,
        'turmas': None,
        'status': 'transferencia',
    }
    try:
        matricula = get_object_or_404(
            Matricula,
            pk=matricula_id,
            status=Matricula.Status.ACTIVA
        )
    except Exception as e:

        context.update(
            erro='Nenhuma matrícula activa encontrada para este aluno!',
            step='buscar'
        )

        return render(request, 'matriculas/matricula_update.html', context)

    turmas = Turma.objects.filter(
        curso=matricula.turma.curso,
        ano_lectivo=_get_ano_atual()
    )

    if len(Matricula.objects.filter(aluno=matricula.aluno)) > 1:
        context.update(
            erro='Houve erro, o aluno não pode ser transferido porque já tem o histórico nas turmas anteriores',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)

    nota = AvaliacaoContinua.objects.filter(
        matricula=matricula
    )

    if nota:
        context.update(
            erro='Houve erro, o aluno não pode ser transferido porque já realizou as avalicões',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)


    try:

        with transaction.atomic():

            Matricula.objects.create(
                
                aluno=matricula.aluno,
                ano_lectivo=ano_lectivo,
                turma_id=turma,
                status=Matricula.Status.ACTIVA,
                tipo_matricula=Matricula.TipoMatricula.NOVA,
                matriculado_por=request.user,
            )

            m = Matricula.objects.get(
                
                aluno=matricula.aluno,
                id=matricula.id,
            )

            m.delete()

            context.update(
                sucesso=f'O aluno foi transferido com sucesso!',
                matricula=matricula,
                aluno=matricula.aluno,
                turmas=turmas,
                step='confirmar'
            )

            return render(request, 'matriculas/matricula_update.html', context)
    except IntegrityError:

        context.update(
            erro='Houve erro, o aluno já tem matricula nesta turma ou neste ano lectivo!',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)

    except Exception as e:
        print(e)
        context.update(
            erro='Houve erro ao transferir o aluno!',
            step='confirmar',
            matricula=matricula,
            aluno=matricula.aluno,
            turmas=turmas
        )

        return render(request, 'matriculas/matricula_update.html', context)

    return render(request, 'matriculas/matricula_update.html', context)


@login_required
def confirmar(request) -> HttpResponse:
    
    cursos = Curso.objects.all()

    context = {
        'step': 'buscar',
        'cursos': cursos,
        'matricula': None,
        'aluno': None,
        'form': None,
        'sucesso': None,
        'erro': None,
        'secao': 'confirmacoes'
    }


    if request.method == 'POST':
        
        ano_letivo = _get_ano_atual()

        step = request.POST.get('step', 'buscar')

        if step == 'buscar':


            bi = request.POST.get('bi', '')
            curso = request.POST.get('curso', '')

            if not curso or not bi:
                context.update(
                    erro='Os campos B.I e Curso são obrigatórios!'
                )

                return render(request, 'reconfirmacao/create.html', context)

            matricula = Matricula.objects.filter(
                status=Matricula.Status.ACTIVA,
                aluno__bi=bi,
                turma__curso_id=curso
            ).first()

            if matricula == None:
                context.update(
                    erro=f'O aluno com B.I: {bi} não foi encontrado no ano lectivo {_get_ano_atual()}'
                )

                return render(request, 'reconfirmacao/create.html', context)

            turmas = Turma.objects.filter(
                curso=matricula.turma.curso,
                ano_lectivo=ano_letivo
            )

            form = ConfirmacaoForm(turmas=turmas)

            context.update(
                step='confirmar',
                matricula=matricula,
                aluno=matricula.aluno,
                form=form
            )

            return render(request, 'reconfirmacao/create.html', context)

        elif step == 'confirmar':

            matricula_id = request.POST.get('matricula_id')

            matricula = get_object_or_404(
                Matricula.objects.select_related('turma__curso', 'aluno', 'ano_lectivo'),
                pk=matricula_id
            )

            form = ConfirmacaoForm(request.POST)

            if form.is_valid():

                mat = form.save()

                try:

                    with transaction.atomic():
                        Matricula.objects.filter(aluno=matricula.aluno, status=Matricula.Status.ACTIVA,
                                                ).update(status=Matricula.Status.CONCLUIDA)

                        mat.aluno = matricula.aluno
                        mat.tipo_matricula = Matricula.TipoMatricula.CONFIRMACAO
                        mat.status = Matricula.Status.ACTIVA
                        mat.matriculado_por = request.user

                        mat.save()

                        if mat.turma.vagas_disponiveis:
                            mat.turma.vagas_disponiveis -= 1

                            mat.turma.save()

                        context.update(
                            sucesso=f'O aluno {mat.aluno.nome_completo} confirmado com sucesso!'
                        )

                        return render(request, 'reconfirmacao/create.html', context)

                except IntegrityError as e:

                    context.update(
                        form=form,
                        matricula=matricula,
                        aluno=matricula.aluno,
                        step='confirmar',
                        erro=f'Houve erro, O estudante {matricula.aluno.nome_completo} já está matriculado nesta turma ou ano lectivo!'
                    )

                    return render(request, 'reconfirmacao/create.html', context)
            else:
                context.update(
                    form=form,
                    matricula=matricula,
                    aluno=matricula.aluno,
                    step='confirmar',
                    erro=f'Houve erro ao confirmar matrícula o aluno!'
                )

                return render(request, 'reconfirmacao/create.html', context)

    return render(request, 'reconfirmacao/create.html', context)


@login_required
@require_http_methods(['POST'])
def confirmar_matricula(request, aluno_id:uuid) -> HttpResponse:

    

    ano_lectivo = _get_ano_atual()

    turma = request.POST.get('turma')
    ano = request.POST.get('ano_lectivo')
    if not ano:
        ano = ano_lectivo.id

    try:
        if transaction.atomic():
            Matricula.objects.filter(aluno_id=aluno_id, status=Matricula.Status.ACTIVA).update(status=Matricula.Status.CONCLUIDA)

            matricula = Matricula.objects.create(
                turma_id=turma,
                
                aluno_id=aluno_id,
                ano_lectivo_id=ano,
                tipo_matricula=Matricula.TipoMatricula.RENOVACAO,
                status=Matricula.Status.ACTIVA
            )
    except IntegrityError:
        messages.error(request, 'Houve erro, o aluno já está confirma do neste ano lectivo ou turma!')

    return redirect('aluno_detail', aluno_id=aluno_id)

@login_required
def inscricao_list(request):
   
    

    ano_letivo = _get_ano_atual()
    
    inscricoes = Inscricao.objects.filter(
        ano_lectivo=ano_letivo,
    ).select_related(
        'candidato', 'ano_lectivo'
    ).order_by('-data_inscricao')
    
    ano_lectivo_id = request.GET.get('ano_lectivo')
    busca = request.GET.get('busca')
    
    if ano_lectivo_id:
        inscricoes = inscricoes.filter(ano_lectivo_id=ano_lectivo_id)

    
    if busca:
        inscricoes = inscricoes.filter(
            Q(aluno__nome_completo__icontains=busca)
        )
    
    order_by = request.GET.get('nome_completo', '-data_inscricao')
    inscricoes = inscricoes.order_by(order_by)

    per_page = request.GET.get('per_page', 20)
    page = request.GET.get('page')

    paginator = Paginator(inscricoes, per_page)
    inscricoes_page = paginator.get_page(page)

    anos_lectivos = AnoLectivo.objects.all()
    

    context = {
        'secao': 'inscricoes',
        'inscricoes': inscricoes_page,
        'anos_lectivos': anos_lectivos,
        'total': inscricoes.count(),
        'per_page': per_page,
        'busca': busca,
        'ano_lectivo_id': ano_lectivo_id,
    }
    
    return render(request, 'inscricoes/list.html', context)


@login_required
def inscricao_create(request):
   
    
    form = InscricaoForm()
    
    if request.method == 'POST':
        form = InscricaoForm(request.POST)
        
        if form.is_valid():

            if transaction.atomic():

                inscricao, candidato = form.save()

                
                candidato.save()

                inscricao.candidato = candidato
                inscricao.inscrito_por = request.user

                inscricao.save()

            context = {
                'secao': 'inscricoes',
                'sucesso': f'Inscrição  feita com sucesso!',
                'form': form
            }
            return render( request, 'inscricoes/create.html', context)
            
        else:
            context = {
                'secao': 'inscricoes',
                'erro': f'Erro, ao realizar matrícula!',
                'form': form
            }
            return render( request, 'inscricoes/create.html', context)
    
    context = {
        'secao': 'inscricoes',
        'form': form,
        
    }
    
    return render(request, 'inscricoes/create.html', context)

@login_required
def inscricao_update(request, inscricao_id):
   
    inscricao = Inscricao.objects.get(id=inscricao_id)
    form = EditarInscricaoForm(inscricao=inscricao)
    
    if request.method == 'POST':
        form = EditarInscricaoForm(request.POST, inscricao=inscricao)
        
        if form.is_valid():

            if transaction.atomic():

                inscricao, candidato = form.save()
            
                candidato.save()

                inscricao.save()

            context = {
                'secao': 'inscricoes',
                'sucesso': f'Inscrição actualizada com sucesso!',
                'inscricao': inscricao,
                'form': form
            }
            return redirect('inscricao_detail', inscricao_id=inscricao_id)
            
        else:
            context = {
                'secao': 'inscricoes',
                'erro': f'Erro, ao atualizar a inscrição!',
                'inscricao': inscricao,
                'form': form,
            }
            return render( request, 'inscricoes/update.html', context)
    
    context = {
        'secao': 'inscricoes',
        'form': form,
        'inscricao': inscricao,
        
    }
    
    return render(request, 'inscricoes/update.html', context)


@login_required
def inscricao_detail(request, inscricao_id):

    
   
    inscricao = get_object_or_404(
        Inscricao.objects.select_related(
            'candidato', 'ano_lectivo', 'inscrito_por'
        ),
        id=inscricao_id,
        
    )
    
    context = {
        'secao': 'inscricoes',
        'inscricao': inscricao,
    }
    
    return render(request, 'inscricoes/detail.html', context)

@login_required
@role_required('director','secretario')
@require_http_methods(['POST'])
def inscricao_delete(request, inscricao_id:uuid):

    try:
        inscricao = get_object_or_404(Inscricao, id=inscricao_id)
        inscricao.delete()
        return JsonResponse({'message': 'Inscrição eliminada com sucesso!'}, status=200)
    except Exception as e:
        return JsonResponse({'message': 'Houve erro ao eliminar a inscrição'}, status=500)

@login_required
def avaliacao_list(request):
   
    
    
    avaliacoes = Avaliacao.objects.filter(
        turma__
    ).select_related(
        'turma', 'disciplina', 'professor', 'periodo', 'tipo_avaliacao'
    ).order_by('-data_realizacao')
    
    turma_id = request.GET.get('turma')
    disciplina_id = request.GET.get('disciplina')
    periodo_id = request.GET.get('periodo')
    
    if turma_id:
        avaliacoes = avaliacoes.filter(turma_id=turma_id)
    if disciplina_id:
        avaliacoes = avaliacoes.filter(disciplina_id=disciplina_id)
    if periodo_id:
        avaliacoes = avaliacoes.filter(periodo_id=periodo_id)
    
    paginator = Paginator(avaliacoes, 20)
    page = request.GET.get('page')
    avaliacoes_page = paginator.get_page(page)
    
    turmas = Turma.objects.filter( activo=True)
    disciplinas = Disciplina.objects.filter( activo=True)

    context = {
        'avaliacoes': avaliacoes_page,
        'turmas': turmas,
        'disciplinas': disciplinas,
    }
    
    return render(request, 'avaliacoes/lista.html', context)


@login_required
def avaliacao_create(request):
  
    
    
    if request.method == 'POST':
        turma_id = request.POST.get('turma')
        disciplina_id = request.POST.get('disciplina')
        periodo_id = request.POST.get('periodo')
        tipo_avaliacao_id = request.POST.get('tipo_avaliacao')
        designacao = request.POST.get('designacao')
        data_realizacao = request.POST.get('data_realizacao')
        nota_maxima = request.POST.get('nota_maxima', 20)
        observacoes = request.POST.get('observacoes', '')
        
        try:
            tdp = TurmaDisciplinaProfessor.objects.filter(
                turma_id=turma_id,
                disciplina_id=disciplina_id
            ).first()
            
            avaliacao = Avaliacao.objects.create(
                turma_id=turma_id,
                disciplina_id=disciplina_id,
                professor=tdp.professor if tdp else None,
                periodo_id=periodo_id,
                tipo_avaliacao_id=tipo_avaliacao_id if tipo_avaliacao_id else None,
                designacao=designacao,
                data_realizacao=data_realizacao,
                nota_maxima=nota_maxima,
                observacoes=observacoes,
                criado_por=request.user
            )
            
            messages.success(request, 'Avaliação criada com sucesso!')
            return redirect('lancar_notas', avaliacao_id=avaliacao.id)
            
        except Exception as e:
            messages.error(request, f'Erro ao criar avaliação: {str(e)}')
    
    turmas = Turma.objects.filter( activo=True)
    disciplinas = Disciplina.objects.filter( activo=True)
    periodos = PeriodoAvaliativo.objects.filter(ano_lectivo__)
    tipos_avaliacao = TipoAvaliacao.objects.all()
    
    context = {
        'turmas': turmas,
        'disciplinas': disciplinas,
        'periodos': periodos,
        'tipos_avaliacao': tipos_avaliacao,
    }
    
    return render(request, 'avaliacoes/criar.html', context)



@login_required
def avaliacao_lancar_notas(request, avaliacao_id):
 
    avaliacao = get_object_or_404(
        Avaliacao.objects.select_related(
            'turma', 'disciplina', 'periodo'
        ),
        id=avaliacao_id
    )
    
    if request.method == 'POST':
        try:
            for key, value in request.POST.items():
                if key.startswith('nota_'):
                    aluno_id = key.replace('nota_', '')
                    nota_valor = value.strip()
                    
                    if nota_valor:
                        aluno = Aluno.objects.get(id=aluno_id)
                        observacao = request.POST.get(f'obs_{aluno_id}', '')
                        
                        nota_obj, created = Nota.objects.get_or_create(
                            avaliacao=avaliacao,
                            aluno=aluno,
                            defaults={
                                'nota': float(nota_valor),
                                'observacao': observacao,
                                'lancado_por': request.user.professor if hasattr(request.user, 'professor') else None
                            }
                        )
                        
                        if not created:
                            nota_obj.nota = float(nota_valor)
                            nota_obj.observacao = observacao
                            nota_obj.save()
            
            messages.success(request, 'Notas lançadas com sucesso!')
            return redirect('lancar_notas', avaliacao_id=avaliacao_id)
            
        except Exception as e:
            messages.error(request, f'Erro ao lançar notas: {str(e)}')
    
    matriculas = Matricula.objects.filter(
        turma=avaliacao.turma,
        status='Activa'
    ).select_related('aluno').order_by('aluno__nome_completo')
    
    # Buscar notas já lançadas
    notas_lancadas = {
        nota.aluno_id: nota 
        for nota in Nota.objects.filter(avaliacao=avaliacao)
    }
    
    # Preparar dados para o template
    alunos_notas = []
    for matricula in matriculas:
        aluno = matricula.aluno
        nota = notas_lancadas.get(aluno.id)
        alunos_notas.append({
            'aluno': aluno,
            'nota': nota.nota if nota else '',
            'observacao': nota.observacao if nota else '',
        })
    
    context = {
        'avaliacao': avaliacao,
        'alunos_notas': alunos_notas,
    }
    
    return render(request, 'notas/lancar.html', context)


@login_required
def avaliacao_pauta(request, turma_id, periodo_id):
  
    turma = get_object_or_404(Turma, id=turma_id)
    periodo = get_object_or_404(PeriodoAvaliativo, id=periodo_id)
    
    disciplinas = TurmaDisciplinaProfessor.objects.filter(
        turma=turma
    ).select_related('disciplina', 'professor')
    
    matriculas = Matricula.objects.filter(
        turma=turma,
        status='Activa'
    ).select_related('aluno').order_by('aluno__nome_completo')
    
    # Preparar dados da pauta
    pauta_dados = []
    for matricula in matriculas:
        aluno = matricula.aluno
        notas_disciplinas = {}
        
        for tdp in disciplinas:
            # Buscar avaliações da disciplina no período
            avaliacoes = Avaliacao.objects.filter(
                turma=turma,
                disciplina=tdp.disciplina,
                periodo=periodo
            )
            
            # Calcular média das notas
            notas = Nota.objects.filter(
                avaliacao__in=avaliacoes,
                aluno=aluno
            )
            
            if notas.exists():
                media = notas.aggregate(Avg('nota'))['nota__avg']
                notas_disciplinas[tdp.disciplina.id] = round(media, 2) if media else 0
            else:
                notas_disciplinas[tdp.disciplina.id] = None
        
        # Calcular média geral
        notas_validas = [n for n in notas_disciplinas.values() if n is not None]
        media_geral = sum(notas_validas) / len(notas_validas) if notas_validas else 0
        
        pauta_dados.append({
            'aluno': aluno,
            'notas': notas_disciplinas,
            'media_geral': round(media_geral, 2)
        })
    
    context = {
        'turma': turma,
        'periodo': periodo,
        'disciplinas': disciplinas,
        'pauta_dados': pauta_dados,
    }
    
    return render(request, 'notas/pauta.html', context)


@login_required
def boletim_aluno(request, aluno_id, ano_lectivo_id):
   
    aluno = get_object_or_404(Aluno, id=aluno_id)
    ano_lectivo = get_object_or_404(AnoLectivo, id=ano_lectivo_id)
    
    # Buscar matrícula do aluno
    matricula = get_object_or_404(
        Matricula,
        aluno=aluno,
        ano_lectivo=ano_lectivo
    )
    
    turma = matricula.turma
    
    # Buscar períodos
    periodos = PeriodoAvaliativo.objects.filter(ano_lectivo=ano_lectivo)
    
    # Buscar disciplinas da turma
    disciplinas = TurmaDisciplinaProfessor.objects.filter(
        turma=turma
    ).select_related('disciplina', 'professor')
    
    # Preparar dados do boletim
    boletim_dados = []
    for tdp in disciplinas:
        notas_periodos = {}
        
        for periodo in periodos:
            # Buscar avaliações e notas
            avaliacoes = Avaliacao.objects.filter(
                turma=turma,
                disciplina=tdp.disciplina,
                periodo=periodo
            )
            
            notas = Nota.objects.filter(
                avaliacao__in=avaliacoes,
                aluno=aluno
            )
            
            if notas.exists():
                media = notas.aggregate(Avg('nota'))['nota__avg']
                notas_periodos[periodo.numero_periodo] = round(media, 2) if media else 0
            else:
                notas_periodos[periodo.numero_periodo] = None
        
        # Calcular média final da disciplina
        notas_validas = [n for n in notas_periodos.values() if n is not None]
        media_final = sum(notas_validas) / len(notas_validas) if notas_validas else 0
        
        boletim_dados.append({
            'disciplina': tdp.disciplina,
            'professor': tdp.professor,
            'notas_periodos': notas_periodos,
            'media_final': round(media_final, 2)
        })
    
    context = {
        'aluno': aluno,
        'matricula': matricula,
        'ano_lectivo': ano_lectivo,
        'turma': turma,
        'periodos': periodos,
        'boletim_dados': boletim_dados,
    }
    
    return render(request, 'notas/boletim.html', context)



# ==================== CONFIGURAÇÕES VIEWS ====================

@login_required
def configuracao_escola(request):

    
    configuracao, created = TenantConfiguracao.objects.get_or_create()
    
    if request.method == 'POST':

        messages.success(request, 'Configurações atualizadas com sucesso!')
        return redirect('configuracao_escola')
    
    context = {
        'configuracoes': configuracao,
        'escola': escola,
        'anos_lectivos': AnoLectivo.objects.all().order_by('-data_inicio'),
    }
    
    return render(request, 'configuracoes/configuracao.html', context)



# ==================== API VIEWS (JSON) ====================

@login_required
def api_turmas_por_classe(request):
    """API: Retorna turmas filtradas por classe"""
    classe_id = request.GET.get('classe_id')
    
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    turmas = Turma.objects.filter(
        
        ano_lectivo=ano_lectivo_activo,
        classe_id=classe_id,
        activo=True
    ).values('id', 'designacao', 'turno', 'vagas_disponiveis')
    
    return JsonResponse(list(turmas), safe=False)

@login_required
def api_turmas_por_ano_lectivo_curso(request):

    ano_lectivo_id = request.GET.get('ano_lectivo_id')
    curso_id = request.GET.get('curso_id')
    

    turmas = Turma.objects.filter(
        
        ano_lectivo_id=ano_lectivo_id
    ).values('id','designacao')

    return JsonResponse(list(turmas), safe=False)

@login_required
def api_turmas_por_curso(request):

    curso_id = request.GET.get('curso_id')
    
    ano_atual = _get_ano_atual()

    turmas = Turma.objects.filter(
        
        ano_lectivo=ano_atual,
        curso_id=curso_id
    ).values('id','designacao')

    return JsonResponse(list(turmas), safe=False)

@login_required
def api_disciplinas_por_turma(request):
    """API: Retorna disciplinas de uma turma"""
    turma_id = request.GET.get('turma_id')
    
    disciplinas = TurmaDisciplinaProfessor.objects.filter(
        turma_id=turma_id
    ).select_related('disciplina', 'professor').values(
        'disciplina__id',
        'disciplina__nome',
        'disciplina__nome_abreviado',
        'professor__id',
        'professor__nome_completo'
    )
    
    return JsonResponse(list(disciplinas), safe=False)


@login_required
def api_alunos_por_turma(request):
    """API: Retorna alunos de uma turma"""
    turma_id = request.GET.get('turma_id')
    
    matriculas = Matricula.objects.filter(
        turma_id=turma_id,
        status='Activa'
    ).select_related('aluno').values(
        'aluno__id',
        'aluno__nome_completo',
        'aluno__numero_processo',
        'aluno__foto'
    ).order_by('aluno__nome_completo')
    
    return JsonResponse(list(matriculas), safe=False)


@login_required
def api_verificar_disponibilidade_turma(request):
    """API: Verifica disponibilidade de vagas na turma"""
    turma_id = request.GET.get('turma_id')
    
    try:
        turma = Turma.objects.get(id=turma_id)
        return JsonResponse({
            'disponivel': turma.vagas_disponiveis > 0,
            'vagas_disponiveis': turma.vagas_disponiveis,
            'capacidade_maxima': turma.capacidade_maxima
        })
    except Turma.DoesNotExist:
        return JsonResponse({'erro': 'Turma não encontrada'}, status=404)


@login_required
def api_notas_aluno(request, aluno_id):
    """API: Retorna todas as notas de um aluno"""
    periodo_id = request.GET.get('periodo_id')
    
    notas = Nota.objects.filter(
        aluno_id=aluno_id
    ).select_related('avaliacao', 'avaliacao__disciplina', 'avaliacao__periodo')
    
    if periodo_id:
        notas = notas.filter(avaliacao__periodo_id=periodo_id)
    
    dados = []
    for nota in notas:
        dados.append({
            'disciplina': nota.avaliacao.disciplina.nome,
            'avaliacao': nota.avaliacao.designacao,
            'periodo': nota.avaliacao.periodo.designacao,
            'nota': float(nota.nota),
            'nota_maxima': float(nota.avaliacao.nota_maxima),
            'data': nota.data_lancamento.strftime('%d/%m/%Y')
        })
    
    return JsonResponse(dados, safe=False)


@login_required
def api_estatisticas_dashboard(request):
    """API: Estatísticas para o dashboard"""
    
    ano_lectivo_activo = AnoLectivo.objects.filter(e_atual=True).first()
    
    dados = {
        'total_alunos': Aluno.objects.filter( status='Matriculado').count(),
        'total_professores': Funcionario.objects.filter( status='Activo').count(),
        'total_turmas': Turma.objects.filter( ano_lectivo=ano_lectivo_activo, activo=True).count(),
        'total_matriculas': Matricula.objects.filter(
            ano_lectivo=ano_lectivo_activo,
            status='Activa'
        ).count(),
        'contas_atrasadas': ContaAluno.objects.filter(
            ano_lectivo=ano_lectivo_activo,
            status='Atrasado'
        ).count(),
    }
    
    return JsonResponse(dados)


# ==================== VIEWS DE BUSCA E AUTOCOMPLETE ====================

@login_required
def busca_aluno(request):
    """Busca de alunos (autocomplete)"""
    termo = request.GET.get('q', '')
    
    
    if len(termo) < 3:
        return JsonResponse([], safe=False)
    
    alunos = Aluno.objects.filter(
        
        nome_completo__icontains=termo
    ).values('id', 'nome_completo', 'numero_processo', 'foto')[:10]
    
    return JsonResponse(list(alunos), safe=False)


@login_required
def busca_professor(request):
    """Busca de professores (autocomplete)"""
    termo = request.GET.get('q', '')
    
    
    if len(termo) < 3:
        return JsonResponse([], safe=False)
    
    professores = Professor.objects.filter(
        
        nome_completo__icontains=termo,
        status='Activo'
    ).values('id', 'nome_completo', 'numero_agente', 'especialidade')[:10]
    
    return JsonResponse(list(professores), safe=False)


# ==================== VIEWS DE EXPORTAÇÃO ====================

@login_required
def exportar_lista_alunos(request):
    """Exportar lista de alunos para Excel"""
    import openpyxl
    from openpyxl.styles import Font, Alignment
    
    
    
    # Criar workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lista de Alunos"
    
    # Cabeçalhos
    headers = ['Nº Processo', 'Nome Completo', 'Data Nascimento', 'Gênero', 'Status', 'Província', 'Telefone', 'Email']
    ws.append(headers)
    
    # Estilizar cabeçalhos
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')
    
    # Dados
    alunos = Aluno.objects.all().order_by('nome_completo')
    for aluno in alunos:
        ws.append([
            aluno.numero_processo,
            aluno.nome_completo,
            aluno.data_nascimento.strftime('%d/%m/%Y'),
            aluno.get_genero_display(),
            aluno.get_status_display(),
            aluno.provincia,
            aluno.telefone,
            aluno.email
        ])
    
    # Ajustar largura das colunas
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Preparar resposta
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=lista_alunos_.xlsx'
    wb.save(response)
    
    return response


@login_required
def exportar_pauta_pdf(request, turma_id, periodo_id):
    """Exportar pauta de avaliação para PDF"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    
    turma = get_object_or_404(Turma, id=turma_id)
    
    # Criar PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    titulo = Paragraph(f"<b>PAUTA DE AVALIAÇÃO - {turma.classe.designacao} {turma.designacao}</b>", styles['Title'])
    elements.append(titulo)
    elements.append(Spacer(1, 12))
    
    subtitulo = Paragraph(f"{turma.ano_lectivo.designacao}", styles['Normal'])
    elements.append(subtitulo)
    elements.append(Spacer(1, 20))
    
    # Preparar dados da tabela
    # ... (implementar lógica de montagem da tabela)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=pauta_{turma.designacao}_.pdf'
    
    return response


# ==================== VIEWS DE NOTIFICAÇÕES ====================

@login_required
def notificacoes_list(request):
    """Lista de notificações do usuário"""
    # Implementar sistema de notificações
    context = {}
    return render(request, 'notificacoes/list.html', context)


@login_required
def marcar_notificacao_lida(request, notificacao_id):
    """Marcar notificação como lida"""
    # Implementar
    return JsonResponse({'status': 'ok'})


# ==================== VIEWS DE PERFIL ====================

@login_required
def meu_perfil(request):
    """Perfil do usuário logado"""
    user = request.user
    
    if request.method == 'POST':
        # Processar atualização do perfil
        messages.success(request, 'Perfil atualizado com sucesso!')
        return redirect('meu_perfil')
    
    context = {
        'user': user,
    }
    
    # Adicionar dados específicos por tipo de usuário
    if hasattr(user, 'professor'):
        context['professor'] = user.professor
    elif hasattr(user, 'aluno'):
        context['aluno'] = user.aluno
    elif hasattr(user, 'encarregadoeducacao'):
        context['encarregado'] = user.encarregadoeducacao
    
    return render(request, 'perfil/meu_perfil.html', context)


@login_required
def alterar_senha(request):
 
    if request.method == 'POST':
        messages.success(request, 'Senha alterada com sucesso!')
        return redirect('meu_perfil')
    
    return render(request, 'perfil/alterar_senha.html')


# ==================== VIEWS DE AJUDA ====================

@login_required
def ajuda_index(request):
    """Página de ajuda"""
    return render(request, 'ajuda/index.html')


@login_required
def ajuda_categoria(request, categoria):
    """Ajuda por categoria"""
    context = {
        'categoria': categoria,
    }
    return render(request, 'ajuda/categoria.html', context)