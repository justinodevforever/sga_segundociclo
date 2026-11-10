from django.urls import path
from .views import *



urlpatterns = [
    
    path('', dashboard_administrador, name='dashboard_admin'),

    path('director/lista/', list_director, name='list_director'),
    path('director/<str:director_id>/editar/', editar_director, name='editar_director'),
    path('director/criar/<str:escola_id>/', criar_director, name='criar_director'),

    path('escola/lista/', lista_escolas, name='lista_escolas'),
    path('escola/<str:escola_id>/detalhe/', detalhe_escola, name='detalhe_escola'),
    path('escola/<str:escola_id>/remover/', delete_school, name='delete_school'),
    path('escola/<str:escola_id>/editar/', editar_escola, name='editar_escola'),
    path('escola/criar/', criar_escola, name='criar_escola'),

    path('plano/lista/', lista_planos, name='lista_planos'),
    path('plano/criar/', criar_plano, name='criar_plano'),
    path('plano/<str:plano_id>/detalhe', detalhe_plano, name='detalhe_plano'),
    path('plano/<str:plano_id>/editar', editar_plano, name='editar_plano'),

]