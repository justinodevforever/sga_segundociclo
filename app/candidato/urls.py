from django.urls import path

from . import views

app_name = "candidato"

urlpatterns = [
    path("portal/", views.home, name="home"),
    path("pre-inscricao/", views.pre_inscricao, name="pre_inscricao"),
    path("pre-inscricao/concluida/<uuid:pk>/", views.sucesso, name="sucesso"),
    path("consultar/", views.consultar, name="consultar"),
    path("acompanhar/", views.acompanhar, name="acompanhar"),
    path("api/progresso/", views.api_progresso, name="api_progresso"),
    path("sair/", views.sair, name="sair"),
]


