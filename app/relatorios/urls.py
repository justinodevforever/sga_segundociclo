from django.urls import path
from . import views

urlpatterns = [
    path("pautas/", views.mini_pauta_selecao, name="mini_pauta_selecao"),
    path(
        "pautas/<uuid:turma_id>/<uuid:disciplina_id>/",
        views.mini_pauta,
        name="mini_pauta",
    ),
    
    path("pauta-final/", views.pauta_final_lista, name="pauta_final_lista"),
    path("pauta-final/turma/<uuid:turma_id>/", views.pauta_final_turma, name="pauta_final_turma"),
    path("", views.index, name="index"),
    path("r/<slug:slug>/", views.relatorio, name="relatorio"),
    path("documento/<slug:tipo>/", views.documento, name="documento"),
    path("api/alunos/", views.api_alunos, name="api_alunos"),
    
    path('financa/', views.index_financa, name='rel_index_financa'),
    path('resumo/', views.resumo, name='rel_resumo'),
    path('comparativo/', views.comparativo, name='rel_comparativo'),
    path('pagamentos/', views.pagamentos, name='rel_pagamentos'),
    path('caixa-diario/', views.caixa_diario, name='rel_caixa'),
    path('receita-mensal/', views.receita_mensal, name='rel_receita_mensal'),
    path('por-metodo/', views.por_metodo, name='rel_por_metodo'),
    path('por-funcionario/', views.por_funcionario, name='rel_por_funcionario'),
    path('devedores/', views.devedores, name='rel_devedores'),
    path('maiores-devedores/', views.top_devedores, name='rel_top_devedores'),
    path('bloqueados/', views.bloqueados, name='rel_bloqueados'),
    path('por-estado/', views.por_status, name='rel_por_status'),
    path('antiguidade-divida/', views.aging, name='rel_aging'),
    path('propinas-atraso/', views.propinas_atraso, name='rel_propinas_atraso'),
    path('mapa-propinas/', views.mapa_propinas, name='rel_mapa_propinas'),
    path('matriz-propinas/', views.matriz_propinas, name='rel_matriz_propinas'),
    path('previsao/', views.previsao, name='rel_previsao'),
    path('extrato/', views.extrato_lista, name='rel_extrato_lista'),
    path('extrato/<int:conta_id>/', views.extrato, name='rel_extrato'),
    path('recibo/<int:pk>/', views.recibo, name='rel_recibo'),
    path('log/', views.log_financeiro, name='rel_log'),
    path('auditoria/', views.auditoria, name='rel_auditoria'),

]