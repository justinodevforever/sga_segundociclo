from django.urls import path
from .views import *

urlpatterns = [
    path('accounts/login/', auth_user, name='login'),
    path('logout/', view_logaout, name='logout'),
    
    path("senha/recuperar/", RecuperarSenhaView.as_view(), name="senha_recuperar"),
    path("senha/recuperar/enviado/", RecuperarSenhaEnviadoView.as_view(), name="senha_recuperar_enviado"),
    path("senha/redefinir/<uidb64>/<token>/", RedefinirSenhaView.as_view(), name="senha_redefinir"),
    path("senha/redefinir/concluido/", RedefinirSenhaConcluidoView.as_view(), name="senha_redefinir_concluido"),

    path('rest_senha/<uuid:usuario_id>/', resetSenhaUsuario, name='reset_senha_usuario'),
]