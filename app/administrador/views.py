from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from decimal import Decimal
import json
from app.db.models import *
from app.authenticate.models import *
from app.db.decorators import role_required, roles_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import date, timedelta
from .forms import *
from .permissions import *

from django.db import transaction

@login_required
def dashboard(request):
    user = request.user
    
    if is_admin(user):
        return redirect('dashboard_admin')
    elif is_professor(user):
        return redirect('dashboard_professor')
    elif is_tecnico_financa(user):
        return redirect('dashboard_tecnico_financa')
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


@login_required
@role_required('admin')
def dashboard_administrador(request):

    ano_atual = AnoLectivo.objects.filter(e_atual=True).first()

    hoje = date.today()

    

    limite = hoje + timedelta(days=30)
    
    role_usuarios = UsuarioRole.objects.all().annotate(
        total_usuarios=Count('utilizador')
    )


    context = {
        'secao': 'dashboard',
        'role_usuarios': role_usuarios,
    }

    return render(request, 'administrador/index.html', context)


@login_required
@role_required('admin')
def list_director(request):

    directores = Diretor.objects.all()

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(directores, per_page)
    directores = paginator.page(page)

    context = {
        'secao': 'directores',
        'directores': directores
    }

    return render(request, 'directores/lista.html', context)


@login_required
@role_required('admin')
def criar_director(request, escola_id):

    form = CriarDirectorForm()

    escola = TenantEscola.objects.get(id=escola_id)

    if request.method == 'POST':

        form = CriarDirectorForm(request.POST)

        if form.is_valid():

            director = form.save()
            director.escola = escola 

            if transaction.atomic():

                user = Utilizador(
                    nome_completo=director.nome_completo,
                    email=director.email,
                    username=director.email,
                    escola=escola
                )

                user.set_password('1234')


                user.save()

                role = Role.objects.filter(nome='director').first()

                UsuarioRole.objects.create(
                    role=role,
                    utilizador=user,
                    atribuido_por=request.user
                )

                director.utilizador = user

                director.save()

                director.save()

            context = {
                'form': form,
                'escola':escola,
                'secao': 'escola',
                'sucesso': 'Director actualizado com sucesso!'
            }

            return render(request, 'directores/criar.html', context)

        else:

            context = {
                'form': form,
                'escola':escola,
                'secao': 'escola',
                'erro': 'Houve erro ao actualizar o director!'
            }

            return render(request, 'directores/criar.html', context)

    else:

        context = {
            'form': form,
            'escola':escola,
            'secao': 'escola',
        }

        return render(request, 'directores/criar.html', context)


@login_required
@role_required('admin')
def editar_director(request, director_id):

    director = Diretor.objects.get(id=director_id)

    form = EditarDirectorForm(director=director)

    if request.method == 'POST':

        form = EditarDirectorForm(request.POST, director=director)

        if form.is_valid():

            director = form.save()

            director.save()

            director.utilizador.email = director.email
            director.utilizador.username = director.email
            director.utilizador.save()

            context = {
                'form': form,
                'director': director,
                'secao': 'directores',
                'sucesso': 'Director criado com sucesso!'
            }

            return render(request, 'directores/editar.html', context)

        else:

            context = {
                'form': form,
                'director': director,
                'secao': 'directores',
                'erro': 'Houve erro ao cria o director!'
            }

            return render(request, 'directores/editar.html', context)

    else:

        context = {
            'form': form,
            'director': director,
            'secao': 'directores',
        }

        return render(request, 'directores/editar.html', context)


@login_required
def criar_escola(request):

    planos = PlanoSubscricao.objects.all()

    if request.method == 'POST':

        form = CriarEscolaForm(request.POST)

        if form.is_valid():

            escola = form.save()

            escola.save()

            context = {
                'sucesso': 'Escola Criada com sucesso!',
                'planos': planos,
                'form': form
            }

            return render(request, 'escolas/criar.html', context)
        
        else:

            context = {
                'erro': 'Houve um erro ao criar a escola!',
                'planos': planos,
                'form': form
            }

            return render(request, 'escolas/criar.html', context)

    else:

        form = CriarEscolaForm()

        context = {
            'planos': planos,
            'form': form
        }

        return render(request, 'escolas/criar.html', context)


@login_required
def editar_escola(request, escola_id:str):

    planos = PlanoSubscricao.objects.all()

    escola = TenantEscola.objects.get(id=escola_id)

    if request.method == 'POST':

        form = EditarEscolaForm(request.POST, escola=escola)

        if form.is_valid():

            escola = form.save()

            escola.save()

            context = {
                'sucesso': 'Escola Criada com sucesso!',
                'planos': planos,
                'escola':escola,
                'form': form
            }

            return render(request, 'escolas/criar.html', context)
        
        else:

            context = {
                'erro': 'Houve um erro ao criar a escola!',
                'planos': planos,
                'escola':escola,
                'form': form
            }

            return render(request, 'escolas/criar.html', context)

    else:

        form = EditarEscolaForm(escola=escola)

        context = {
            'planos': planos,
            'escola':escola,
            'form': form
        }

        return render(request, 'escolas/editar.html', context)


@login_required
@role_required('admin')
def lista_escolas(request):

    escolas = (
        TenantEscola.objects
        .select_related('plano_subscricao')
        .annotate(
            total_alunos=Count('aluno', distinct=True),
            total_professores=Count('funcionario', distinct=True),
        )
        .order_by('nome')
    )


    hoje = timezone.now().date()

    total_escola_ativa = escolas.filter(status_ensino='activa').count()
    total_escola_inativa = escolas.filter(status_ensino='inactiva').count()
    total_escola_pendente = escolas.filter(status_ensino='pendente').count()  
    total_escola = escolas.count()

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(escolas, per_page)
    escolas = paginator.page(page)


    planos = PlanoSubscricao.objects.filter(activo=True)
    context = {
        'secao': 'escolas',
        'hoje': hoje,
        'total_escola_ativa':total_escola_ativa,
        'total_escola_pendente':total_escola_pendente,
        'total_escola_inativa':total_escola_inativa,
        'escolas': escolas,
        'planos': planos,
        'per_page': per_page,
        'total_escola': total_escola,
    }
    return render(request, 'escolas/lista.html', context)


@login_required
@role_required('admin')
@require_http_methods(['POST'])
def delete_school(request, escola_id):

    escola = TenantEscola.objects.get(id=escola_id)
    direct = Diretor.objects.filter(escola=escola).first()
  

    if direct:

        return JsonResponse({'error': 'Essa escola não pode ser eliminada porque tem dados associados!'}, status=403)

  
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao='delete',
        modulo='TenantEscola',
        objeto_id=escola.id,
        descricao=f'Escola: {escola.nome} eliminada',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    escola.delete()

    return redirect('lista_escolas')


@login_required
def detalhe_escola(request, escola_id:str):
 
    escola = get_object_or_404(
        TenantEscola.objects.select_related('plano_subscricao'),
        id=escola_id
    )
    director = Diretor.objects.filter(escola=escola).first()
    print(director)
  
    ano_lectivo_atual = AnoLectivo.objects.filter(
        escola=escola, e_atual=True
    ).first()

    stats = {
        'alunos': Aluno.objects.filter(escola=escola, status='Matriculado').count(),
        'professores': Funcionario.objects.filter(escola=escola, status='Activo').count(),
        'turmas': Turma.objects.filter(escola=escola, activo=True).count(),
        'cursos': Curso.objects.filter(escola=escola, activo=True).count(),
    }
   

    context = {
        'secao': 'escolas',
        'director': director,
        'escola': escola,
        'ano_lectivo_atual': ano_lectivo_atual,
        'stats': stats,
    }
    return render(request, 'escolas/detalhe.html', context)



@login_required
def lista_roles(request):
    """Lista todos os roles/perfis com contagem de utilizadores."""
    roles = (
        Role.objects
        .annotate(total_utilizadores=Count('usuario_roles', distinct=True))
        .prefetch_related('role_permissoes__permissao')
        .order_by('nome')
    )
    context = {
        'secao': 'roles',
        'roles': roles,
    }
    return render(request, 'admin/roles/lista.html', context)


@login_required
def detalhe_role(request, role_id):
    """Detalhes de um role com suas permissões."""
    role = get_object_or_404(Role, id=role_id)
    permissoes = (
        Permissao.objects
        .filter(role_permissoes__role=role)
        .values('nome', 'acao')
        .order_by('nome', 'acao')
    )
    utilizadores = (
        UsuarioRole.objects
        .filter(role=role)
        .select_related('utilizador', 'atribuido_por')
        .order_by('atribuido_em')
    )
    context = {
        'secao': 'roles',
        'role': role,
        'permissoes': permissoes,
        'utilizadores': utilizadores,
    }
    return render(request, 'admin/roles/detalhe.html', context)


@login_required
def lista_permissoes(request):
    """Lista todas as permissões agrupadas por recurso."""
    permissoes = (
        Permissao.objects
        .values('nome')
        .annotate(total_acoes=Count('id'))
        .order_by('nome')
    )
    todas = Permissao.objects.order_by('nome', 'acao')
    context = {
        'secao': 'permissoes',
        'permissoes_agrupadas': permissoes,
        'todas_permissoes': todas,
    }
    return render(request, 'admin/permissoes/lista.html', context)



@login_required
def lista_planos(request):
   
    planos = (
        PlanoSubscricao.objects
        .annotate(
            total_escolas=Count('tenantescola', distinct=True),
            escolas_ativas=Count(
                'tenantescola',
                filter=Q(tenantescola__activo=True),
                distinct=True,
            ),
        )
        .order_by('preco_mensal')
    )

    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)

    paginator = Paginator(planos, per_page)
    planos = paginator.page(page)

    context = {
        'secao': 'planos',
        'planos': planos,
    }
    return render(request, 'planos/lista.html', context)

@login_required
@role_required('admin')
def criar_plano(request):

    form = CriarPlanoForm()

    if request.method == 'POST':

        form = CriarPlanoForm(request.POST)

        if form.is_valid():

            plano = form.save()

            plano.save()

            context = {
                'form': form,
                'sucesso': 'Plano ciado com sucesso!'
            }

            return render(request, 'planos/criar.html', context)

        else:

            context = {
                'form': form,
                'erro': 'Houve erro ao cria o plano!'
            }

            return render(request, 'planos/criar.html', context)

    else:

        context = {
            'form': form,
        }

        return render(request, 'planos/criar.html', context)

@login_required
@role_required('admin')
def editar_plano(request, plano_id):

    plano_oject = PlanoSubscricao.objects.get(id=plano_id)

    if request.method == 'POST':

        form = EditarPlanoForm(request.POST, plano=plano_oject)

        if form.is_valid():

            plano = form.save()

            plano.save()

            context = {
                'form': form,
                'sucesso': 'Plano Actualizado com sucesso!'
            }

            return render(request, 'planos/editar.html', context)

        else:

            context = {
                'form': form,
                'erro': 'Houve erro ao actualizar o plano!'
            }

            return render(request, 'planos/editar.html', context)

    else:

        form = EditarPlanoForm(plano=plano_oject)

        context = {
            'form': form,
        }

        return render(request, 'planos/editar.html', context)

@login_required
@role_required('admin')
def detalhe_plano(request, plano_id):

    plano = PlanoSubscricao.objects.filter(id=plano_id).annotate(
            total_escolas=Count('tenantescola', distinct=True),
            escolas_ativas=Count(
                'tenantescola',
                filter=Q(tenantescola__activo=True),
                distinct=True,
            ),
        ).first()


    return render(request, 'planos/detalhe.html', {'plano': plano, 'secao': 'planos'}) 


# ──────────────────────────────────────────────
# GESTÃO DE ALUNOS (visão global)
# ──────────────────────────────────────────────

@login_required
def lista_alunos_global(request):
    """Lista global de alunos de todas as escolas com filtros."""
    escola_id = request.GET.get('escola')
    status_filtro = request.GET.get('status', '')
    busca = request.GET.get('q', '')

    alunos = Aluno.objects.select_related('escola').order_by('nome_completo')

    if escola_id:
        alunos = alunos.filter(escola_id=escola_id)
    if status_filtro:
        alunos = alunos.filter(status=status_filtro)
    if busca:
        alunos = alunos.filter(
            Q(nome_completo__icontains=busca) |
            Q(numero_processo__icontains=busca) |
            Q(bi__icontains=busca)
        )

    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')
    context = {
        'secao': 'alunos',
        'alunos': alunos,
        'escolas': escolas,
        'status_choices': Aluno.STATUS,
        'filtros': {
            'escola_id': escola_id,
            'status': status_filtro,
            'q': busca,
        },
        'total': alunos.count(),
    }
    return render(request, 'admin/alunos/lista.html', context)


# ──────────────────────────────────────────────
# GESTÃO DE PROFESSORES (visão global)
# ──────────────────────────────────────────────

@login_required
def lista_professores_global(request):
    """Lista global de professores com filtros."""
    escola_id = request.GET.get('escola')
    status_filtro = request.GET.get('status', '')
    busca = request.GET.get('q', '')

    professores = (
        Professor.objects
        .select_related('escola', 'categoria')
        .annotate(total_disciplinas=Count('disciplinas_lecionadas', distinct=True))
        .order_by('nome_completo')
    )

    if escola_id:
        professores = professores.filter(escola_id=escola_id)
    if status_filtro:
        professores = professores.filter(status=status_filtro)
    if busca:
        professores = professores.filter(
            Q(nome_completo__icontains=busca) |
            Q(numero_agente__icontains=busca) |
            Q(bi__icontains=busca)
        )

    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')
    context = {
        'secao': 'professores',
        'professores': professores,
        'escolas': escolas,
        'status_choices': Professor.STATUS,
        'filtros': {
            'escola_id': escola_id,
            'status': status_filtro,
            'q': busca,
        },
        'total': professores.count(),
    }
    return render(request, 'admin/professores/lista.html', context)


# ──────────────────────────────────────────────
# RELATÓRIOS E ESTATÍSTICAS
# ──────────────────────────────────────────────

@login_required
def relatorio_matriculas(request):
    """Relatório de matrículas por escola, curso e ano lectivo."""
    ano_id = request.GET.get('ano_lectivo')
    escola_id = request.GET.get('escola')

    matriculas = Matricula.objects.select_related(
        'escola', 'aluno', 'curso', 'turma', 'ano_lectivo'
    )

    if ano_id:
        matriculas = matriculas.filter(ano_lectivo_id=ano_id)
    if escola_id:
        matriculas = matriculas.filter(escola_id=escola_id)

    por_status = (
        matriculas.values('status')
        .annotate(total=Count('id'))
        .order_by('status')
    )
    por_tipo = (
        matriculas.values('tipo_matricula')
        .annotate(total=Count('id'))
        .order_by('tipo_matricula')
    )
    por_curso = (
        matriculas.values('curso__nome')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    anos_lectivos = AnoLectivo.objects.order_by('-data_inicio')
    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')

    context = {
        'secao': 'relatorios',
        'total_matriculas': matriculas.count(),
        'por_status': list(por_status),
        'por_tipo': list(por_tipo),
        'por_curso': list(por_curso),
        'anos_lectivos': anos_lectivos,
        'escolas': escolas,
        'filtros': {'ano_id': ano_id, 'escola_id': escola_id},
    }
    return render(request, 'admin/relatorios/matriculas.html', context)


@login_required
def relatorio_financeiro(request):
    """Relatório financeiro consolidado."""
    escola_id = request.GET.get('escola')
    ano_id = request.GET.get('ano_lectivo')

    contas = ContaAluno.objects.select_related('escola', 'aluno', 'ano_lectivo')

    if escola_id:
        contas = contas.filter(escola_id=escola_id)
    if ano_id:
        contas = contas.filter(ano_lectivo_id=ano_id)

    resumo = contas.aggregate(
        total_pago=Sum('total_pago'),
        total_devido=Sum('total_devido'),
        saldo_devedor=Sum('saldo_devedor'),
    )
    por_status = (
        contas.values('status')
        .annotate(
            quantidade=Count('id'),
            valor=Sum('saldo_devedor'),
        )
        .order_by('status')
    )
    por_escola = (
        contas.values('escola__nome')
        .annotate(
            total_pago=Sum('total_pago'),
            saldo_devedor=Sum('saldo_devedor'),
        )
        .order_by('-total_pago')[:10]
    )

    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')
    anos_lectivos = AnoLectivo.objects.order_by('-data_inicio')

    context = {
        'secao': 'relatorios',
        'resumo': resumo,
        'por_status': list(por_status),
        'por_escola': list(por_escola),
        'escolas': escolas,
        'anos_lectivos': anos_lectivos,
        'filtros': {'escola_id': escola_id, 'ano_id': ano_id},
    }
    return render(request, 'admin/relatorios/financeiro.html', context)


@login_required
def relatorio_notas(request):
    """Relatório de desempenho académico por escola/turma/disciplina."""
    escola_id = request.GET.get('escola')
    turma_id = request.GET.get('turma')

    notas = Nota.objects.select_related(
        'escola', 'aluno', 'avaliacao__disciplina', 'avaliacao__turma'
    )
    if escola_id:
        notas = notas.filter(escola_id=escola_id)
    if turma_id:
        notas = notas.filter(avaliacao__turma_id=turma_id)

    media_geral = notas.aggregate(media=Avg('nota'))['media']

    por_disciplina = (
        notas.values('avaliacao__disciplina__nome')
        .annotate(
            media=Avg('nota'),
            total_alunos=Count('aluno', distinct=True),
        )
        .order_by('-media')[:10]
    )

    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')
    turmas = Turma.objects.select_related('classe', 'curso').filter(activo=True)

    context = {
        'secao': 'relatorios',
        'media_geral': media_geral,
        'por_disciplina': list(por_disciplina),
        'escolas': escolas,
        'turmas': turmas,
        'filtros': {'escola_id': escola_id, 'turma_id': turma_id},
    }
    return render(request, 'admin/relatorios/notas.html', context)


# ──────────────────────────────────────────────
# COMUNICADOS (visão global do admin)
# ──────────────────────────────────────────────

@login_required
def lista_comunicados(request):
    """Lista de comunicados de todas as escolas."""
    escola_id = request.GET.get('escola')
    tipo_filtro = request.GET.get('tipo', '')

    comunicados = Comunicado.objects.select_related(
        'escola', 'publicado_por', 'turma'
    ).order_by('-data_publicacao')

    if escola_id:
        comunicados = comunicados.filter(escola_id=escola_id)
    if tipo_filtro:
        comunicados = comunicados.filter(tipo=tipo_filtro)

    escolas = TenantEscola.objects.filter(activo=True).order_by('nome')

    context = {
        'secao': 'comunicados',
        'comunicados': comunicados[:50],
        'escolas': escolas,
        'tipos': Comunicado.TIPOS,
        'filtros': {'escola_id': escola_id, 'tipo': tipo_filtro},
        'total': comunicados.count(),
    }
    return render(request, 'admin/comunicados/lista.html', context)


# ──────────────────────────────────────────────
# ENDPOINTS JSON (para gráficos via AJAX)
# ──────────────────────────────────────────────

@login_required
def api_stats_dashboard(request):
    """Retorna estatísticas em JSON para actualização dinâmica dos gráficos."""
    hoje = date.today()

    matriculas_mensal = []
    for i in range(5, -1, -1):
        mes_ref = hoje.replace(day=1) - timedelta(days=i * 30)
        qtd = Matricula.objects.filter(
            data_matricula__year=mes_ref.year,
            data_matricula__month=mes_ref.month,
        ).count()
        matriculas_mensal.append({'mes': mes_ref.strftime('%b/%Y'), 'qtd': qtd})

    alunos_status = list(
        Aluno.objects.values('status').annotate(total=Count('id'))
    )

    data = {
        'totais': {
            'escolas': TenantEscola.objects.filter(activo=True).count(),
            'alunos': Aluno.objects.filter(status='Matriculado').count(),
            'professores': Professor.objects.filter(status='Activo').count(),
            'turmas': Turma.objects.filter(activo=True).count(),
        },
        'matriculas_mensal': matriculas_mensal,
        'alunos_status': alunos_status,
    }
    return JsonResponse(data)
