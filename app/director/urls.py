from django.urls import path
from .views import *

urlpatterns = [
    
    path('', dashboard_diretor, name='dashboard_diretor'),
    
    path("director/configuracoes/", ConfiguracoesEscolaView.as_view(), name="configuracoes_escola"),
    
    path('dashboard/', dashboard, name='dashboard'),

    path('usarios/', usuario_list, name='usuario_list'),
    path('usarios/<uuid:usuario_id>/', usuario_datail, name='usuario_datail'),
    path('usarios/<uuid:usuario_id>/edit/', usuario_edit, name='usuario_edit'),

    path('alunos/', aluno_list, name='aluno_list'),
    path('alunos/criar/', aluno_create, name='aluno_create'),
    path('alunos/<uuid:aluno_id>/', aluno_detail, name='aluno_detail'),
    path('alunos/<uuid:aluno_id>/editar/', aluno_update, name='aluno_update'),
    path('alunos/<uuid:aluno_id>/excluir/', aluno_delete, name='aluno_delete'),
    
    path('funcionarios/', funcionario_list, name='funcionario_list'),
    path('funcionarios/criar/', funcionario_create, name='funcionario_create'),
    path('funcionarios/<uuid:funcionario_id>/', funcionario_detail, name='funcionario_detail'),
    path('funcionarios/<uuid:funcionario_id>/editar/', funcionario_edit, name='funcionario_edit'),
    path('funcionarios/<uuid:funcionario_id>/excluir/', funcionario_delete, name='funcionario_delete'),
    
    path('turmas/', turma_list, name='turma_list'),
    path('turmas/criar/', turma_create, name='turma_create'),
    path('turmas/<uuid:turma_id>/', turma_detail, name='turma_detail'),
    path('turmas/<uuid:turma_id>/update/', turma_update, name='turma_update'),
    path('turmas/<uuid:turma_id>/estudantes/', turma_estudante_list, name='turma_estudante_list'),
    path('turmas/<uuid:turma_id>/excluir/', turma_delete, name='turma_delete'),
    #path('turmas/<uuid:turma_id>/atribuir-professor/', turma_atribuir_professor, name='turma_atribuir_professor'),
    
    path('disciplinas/', disciplina_list, name='disciplina_list'),
    path('disciplinas/criar/', disciplina_create, name='disciplina_create'),
    path('disciplinas/<uuid:disciplina_id>/', disciplina_detail, name='disciplina_detail'),
    path('disciplinas/<uuid:disciplina_id>/editar/', disciplina_edit, name='disciplina_edit'),
    path('disciplinas/<uuid:disciplina_id>/excluir/', disciplina_delete, name='disciplina_excluir'),

    path('classes/', classe_list, name='classe_list'),
    path('classes/criar/', classe_create, name='classe_create'),
    path('classes/<uuid:classe_id>', classe_detail, name='classe_detail'),
    path('classes/<uuid:classe_id>/', classe_update, name='classe_update'),
    path('classes/<uuid:classe_id>/excluir/', classe_delete, name='classe_delete'),

    path('periodos/', periodo_list, name='periodo_list'),
    path('periodos/criar/', periodo_create, name='periodo_create'),
    path('periodos/<uuid:periodo_id>', periodo_detail, name='periodo_detail'),

    path('cursos/', curso_list, name='curso_list'),
    path('cursos/criar/', curso_create, name='curso_create'),
    path('cursos/<uuid:curso_id>', curso_detail, name='curso_detail'),
    path('cursos/<uuid:curso_id>/', curso_update, name='curso_update'),
    path('cursos/<uuid:curso_id>/excluir/', curso_delete, name='curso_delete'),
    

    path('ano_letivos/', anoletivo_list, name='anoletivo_list'),
    path('ano_letivos/criar/', anoletivo_create, name='anoletivo_create'),
    path('ano_letivos/<uuid:anoletivo_id>', anoletivo_detail, name='anoletivo_detail'),
    path('ano_letivos/<uuid:anoletivo_id>/', anoletivo_update, name='anoletivo_update'),
    path('ano_letivos/<uuid:anoletivo_id>/excluir/', anoletivo_delete, name='anoletivo_delete'),

    path('trimestres/', trimestre_list, name='trimestre_list'),
    path('trimestres/criar/', trimestre_create, name='trimestre_create'),
    path('trimestres/<uuid:trimestre_id>', trimestre_edit, name='trimestre_edit'),
    path('trimestres/<uuid:trimestre_id>/', trimestre_detail, name='trimestre_detail'),
    path('trimestres/<uuid:trimestre_id>/excluir/', trimestre_delete, name='trimestre_delete'),

    # path('financeiro/', financeiro_dashboard, name='financeiro_dashboard'),
    # path('financeiro/contas/', financeiro_contas_list, name='financeiro_contas_list'),
    # path('financeiro/contas/<uuid:conta_id>/', financeiro_conta_detail, name='financeiro_conta_detail'),

    
    path('horarios/turma/<uuid:turma_id>/', horario_turma, name='horario_turma'),
    path('horarios/professor/', horario_professor, name='horario_professor'),
    path('horarios/professor/<uuid:professor_id>/', horario_professor, name='horario_professor_detail'),
    path('horarios/turma/<uuid:turma_id>/criar/', horario_create, name='horario_create'),
 
    
    # path('configuracoes/escola/', configuracoes_escola, name='configuracoes_escola'),
    path('configuracoes/anos-lectivos/<uuid:ano_id>/ativar/', ano_lectivo_ativar, name='ano_lectivo_ativar'),
    # path('configuracoes/periodos/<uuid:ano_id>/', periodo_avaliativo_list, name='periodo_avaliativo_list'),
    path('configuracoes/periodos/<uuid:ano_id>/criar/', periodo_avaliativo_create, name='periodo_avaliativo_create'),
    path('configuracoes/tipos-avaliacao/', tipo_avaliacao_list, name='tipo_avaliacao_list'),

    path('api/atribuir-acesso-professor/<uuid:professor_id>/', api_atribuir_acesso_professor, name='api_atribuir_acesso_professor')
    
]
