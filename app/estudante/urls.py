from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "estudante"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard_estudante"),
    path("notas/", views.NotasView.as_view(), name="notas"),
    path("historico/", views.HistoricoView.as_view(), name="historico"),
    path("financeiro/", views.FinanceiroView.as_view(), name="financeiro"),
    path("financeiro/recibo/<int:pk>/", views.ReciboView.as_view(), name="recibo"),
    path("faltas/", views.FaltasView.as_view(), name="faltas"),
    path("horario/", views.HorarioView.as_view(), name="horario"),
    path("reclamacoes/", views.ReclamacoesView.as_view(), name="reclamacoes"),
    path("perfil/", views.PerfilView.as_view(), name="perfil"),
    path(
        "perfil/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="portal/password.html", success_url=reverse_lazy("portal:perfil")
        ),
        name="password",
    ),
]
