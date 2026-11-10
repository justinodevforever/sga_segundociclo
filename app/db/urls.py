from django.urls import path
from . import views

urlpatterns = [

    path('dashboard/diretor/', views.dashboard_diretor, name='dashboard_diretor'),
    path('dashboard/aluno/', views.dashboard_aluno, name='dashboard_aluno'),
    
    path('matriculas/', views.matricula_list, name='matricula_list'),
    path('matriculas/<uuid:matricula_id>/', views.matricula_detail, name='matricula_detail'),
    path('matriculas/criar/', views.matricula_create, name='matricula_create'),
    path('matriculas/<uuid:matricula_id>/editar', views.matricula_update, name='matricula_update'),
    path('matriculas/criar/<uuid:aluno_id>/', views.matricula_create, name='matricula_create_aluno'),

    path('matriculas/update/status/', views.matricula_update_status, name='matricula_update_status'),
    path('matricula/<uuid:matricula_id>/tancar/', views.trancar_matricula, name='trancar_matricula'),
    path('matricula/<uuid:matricula_id>/cancelar/', views.cancelar_matricula, name='cancelar_matricula'),
    path('matricula/<uuid:matricula_id>/reingresso/', views.reingresso_matricula, name='reingresso_matricula'),
    path('matricula/<uuid:matricula_id>/transferir/', views.transferencia_matricula, name='transferencia_matricula'),
    path('matricula/<uuid:matricula_id>/reactivar/', views.reactivar_matricula, name='reactivar_matricula'),

    path('confirmacao/<uuid:aluno_id>/', views.confirmar_matricula, name='confirmar_matricula'),
    path('confirmacao/', views.confirmar, name='confirmar'),

    path('inscricoes/', views.inscricao_list, name='inscricao_list'),
    path('inscricoes/<uuid:inscricao_id>/', views.inscricao_detail, name='inscricao_detail'),
    path('inscricoes/criar/', views.inscricao_create, name='inscricao_create'),
    path('inscricoes/<uuid:inscricao_id>/editar', views.inscricao_update, name='inscricao_update'),
    path('inscricoes/<uuid:inscricao_id>/excluir/', views.inscricao_delete, name='inscricao_delete'),
    
    path('perfil/', views.meu_perfil, name='meu_perfil'),
    path('perfil/alterar-senha/', views.alterar_senha, name='alterar_senha'),
    
    path('ajuda/', views.ajuda_index, name='ajuda_index'),
    path('ajuda/<str:categoria>/', views.ajuda_categoria, name='ajuda_categoria'),

    path('api/turma-por_curso/', views.api_turmas_por_curso, name='api_turmas_por_curso'),
    path('api/turma-ano-por_curso/', views.api_turmas_por_ano_lectivo_curso, name='api_turmas_por_ano_lectivo_curso'),

    # path('api/turmas-por-classe/', api_turmas_por_classe, name='api_turmas_por_classe'),
    # path('api/disciplinas-por-turma/', api_disciplinas_por_turma, name='api_disciplinas_por_turma'),
    # path('api/alunos-por-turma/', api_alunos_por_turma, name='api_alunos_por_turma'),
    # path('api/verificar-disponibilidade-turma/', api_verificar_disponibilidade_turma, name='api_verificar_disponibilidade_turma'),
    # path('api/notas-aluno/<uuid:aluno_id>/', api_notas_aluno, name='api_notas_aluno'),
    # path('api/estatisticas-dashboard/', api_estatisticas_dashboard, name='api_estatisticas_dashboard'),
    
    # path('busca/aluno/', busca_aluno, name='busca_aluno'),
    # path('busca/professor/', busca_professor, name='busca_professor'),
    
    # path('exportar/alunos/', exportar_lista_alunos, name='exportar_lista_alunos'),
    # path('exportar/pauta/<uuid:turma_id>/<uuid:periodo_id>/', exportar_pauta_pdf, name='exportar_pauta_pdf'),
    
    # path('notificacoes/', notificacoes_list, name='notificacoes_list'),
    # path('notificacoes/<int:notificacao_id>/marcar-lida/', marcar_notificacao_lida, name='marcar_notificacao_lida'),
]