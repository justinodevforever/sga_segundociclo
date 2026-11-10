from django.urls import path

from . import views

app_name = "avaliacao"

urlpatterns = [
    path("", views.turmas, name="turmas"),
    path("turma/<uuid:turma_id>/", views.turma_detalhe, name="turma_detalhe"),
    path("turma/<uuid:turma_id>/disciplina/<uuid:disciplina_id>/trimestre/<uuid:trimestre_id>/notas/",
         views.lancar_notas, name="lancar_notas"),
    path("turma/<uuid:turma_id>/disciplina/<uuid:disciplina_id>/trimestre/<uuid:trimestre_id>/continua/",
         views.lancar_continua, name="lancar_continua"),
    path("turma/<uuid:turma_id>/disciplina/<uuid:disciplina_id>/exame/",
         views.lancar_exame, name="lancar_exame"),
    path("turma/<uuid:turma_id>/pauta/trimestre/<uuid:trimestre_id>/",
         views.pauta_trimestral, name="pauta_trimestral"),
    path("turma/<uuid:turma_id>/pauta-final/", views.pauta_final, name="pauta_final"),
    path("turma/<uuid:turma_id>/calcular/", views.calcular_resultados, name="calcular_resultados"),
    path("matricula/<uuid:matricula_id>/boletim/", views.boletim, name="boletim"),
]