from django.urls import path
from . import views

urlpatterns = [

    path('', views.dashboard_financeiro, name='financeiro_dashboard'),

    path('contas/', views.conta_list, name='conta_list'),
    path('contas/nova/', views.conta_create, name='conta_create'),
    path('contas/<int:pk>/', views.conta_detail, name='conta_detail'),
    path('contas/<int:pk>/editar/', views.conta_edit, name='conta_edit'),
    path('contas/<int:pk>/excluir/', views.conta_delete, name='conta_delete'),

    path('pagamentos/', views.pagamento_list, name='pagamento_list'),
    path('pagamentos/novo/', views.pagamento_create, name='pagamento_create'),
    path('pagamentos/novo/<int:conta_pk>/', views.pagamento_create, name='pagamento_create_conta'),

    path('propinas/<int:conta_pk>/', views.propinas_conta, name='propinas_conta'),

    path('recibo/<str:numero>/', views.recibo_detalhe, name='recibo_detalhe'),
    path('recibo/<str:numero>/pdf/', views.recibo_pdf, name='recibo_pdf'),

    path('validar/<str:numero>/', views.validar_recibo, name='validar_recibo'),

    path('relatorios/', views.relatorio_financeiro, name='relatorio_financeiro'),

    path('api/conta/<int:conta_pk>/', views.api_conta_info, name='api_conta_info'),
]