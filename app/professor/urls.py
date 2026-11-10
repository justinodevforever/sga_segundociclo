from django.urls import path
from .views import *
app_name="professor"
urlpatterns = [

    path("", dashboard_professor, name="dashboard_professor"),

    path("turmas/", MinhasTurmasView.as_view(), name="minhas_turmas"),

    path("avaliacoes/", AvaliacoesView.as_view(), name="avaliacoes"),

    path('nota/exames/', lancar_nota_exame, name='lancar_nota_exame'),
    path("notas/<uuid:turma_disciplina_id>/", avaliacao_lancar_notas, name="lancamento_notas"),

    path('pautas/trimestral/', pauta_trimestral, name='pauta_trimestral'),
    path('pautas/anuais/', resultados_anuais, name='resultados_anuais'),

    path("horario/", HorarioView.as_view(), name="horario"),

    path("alunos/", MeusAlunosView.as_view(), name="meus_alunos"),
    path("alunos/<uuid:aluno_id>/", DetalheAlunoView.as_view(), name="detalhe_aluno"),

    path("frequencia/", FrequenciaView.as_view(), name="frequencia"),

    path("comunicados/", ComunicadosView.as_view(), name="comunicados"),
    path('alunos/<uuid:matricula_pk>/boletim/', boletim_aluno, name='boletim_aluno'),

    path('pauta/mini/', mini_pauta, name='mini_pauta',),
    path('pauta/mini/pdf/<uuid:trimestre_id>/<uuid:turma_id>/', exportar_pauta_pdf, name='mini_pauta_export_pdf',),

    path("api/turma/<uuid:turma_id>/alunos/", api_turma_alunos, name="api_turma_alunos"),
    path("api/turma/<uuid:turma_id>/estatisticas/", api_estatisticas_turma, name="api_estatisticas_turma"),
    path("api/notas/guardar/", api_guardar_nota_rapida, name="api_guardar_nota_rapida"),
]