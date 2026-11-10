from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages
from app.db.models import Utilizador
from django.http import JsonResponse
import logging
import json

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

from .forms import DefinirNovaSenhaForm, RecuperarSenhaForm

logger = logging.getLogger(__name__)
TPL = "contas/senha/"


def auth_user(request):

    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')
        remember = request.POST.get('remember')
        
        try: 
            user_obj = Utilizador.objects.get(
                (Q(username=username) | Q(email=username)) |
                Q(password=password)
            )

        except Utilizador.DoesNotExist:
            messages.error(request,  "Credenciais inválidas!")
            return render(request, 'login.html', {
                'next': request.POST.get('next')
            })

        user = authenticate(request, 
            username=user_obj.username, 
            password=password
        )
        

        if user:
            user.penultima_entrada = user.last_login
            user.last_login = timezone.now()
            user.save()
            login(request, user) 

            if remember:

                request.session.set_expiry(60 * 60 * 24 * 30)

            else:
                request.session.set_expiry(60*60) 
                
            next_url = request.POST.get('next') or '/dashboard'

            return redirect(next_url)

        else:

            messages.error(request,  "Credenciais inválidas!")
            return render(request, 'login.html', {
                'next': request.POST.get('next')
            })
    else:
        
        return render(request, 'login.html', {
            'next': request.GET.get('next', '/')
        })

def view_logaout(request):

    next_url = request.GET.get('next', '/')

    user = request.user
    user.ultimo_logout = timezone.now()
    user.save()

    logout(request)

    return redirect(f'/accounts/login/?next={next_url}')



@method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=True), name="dispatch")
class RecuperarSenhaView(auth_views.PasswordResetView):
    template_name = TPL + "recuperar.html"
    form_class = RecuperarSenhaForm
    email_template_name = TPL + "email_texto.txt"
    html_email_template_name = TPL + "email.html"
    subject_template_name = TPL + "email_assunto.txt"
    success_url = reverse_lazy("senha_recuperar_enviado")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except Exception:
            # Regista o erro, mas não revela nada ao utilizador
            logger.exception("Falha ao enviar e-mail de recuperação de senha")
            return super(auth_views.PasswordResetView, self).form_valid(form)
        
class RecuperarSenhaEnviadoView(auth_views.PasswordResetDoneView):
    """Passo 2: mensagem neutra (não revela se o e-mail existe)."""
    template_name = TPL + "recuperar_enviado.html"


class RedefinirSenhaView(auth_views.PasswordResetConfirmView):
    """Passo 3: link do e-mail -> formulário de nova senha."""
    template_name = TPL + "redefinir.html"
    form_class = DefinirNovaSenhaForm
    success_url = reverse_lazy("senha_redefinir_concluido")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Quem recebeu e usou o link provou ter acesso ao e-mail.
        # Opcional, mas coerente com o teu campo `verificado_email`.
        user = form.user
        if not user.verificado_email:
            user.verificado_email = True
            user.save(update_fields=["verificado_email"])
        return response


class RedefinirSenhaConcluidoView(auth_views.PasswordResetCompleteView):
    """Passo 4: sucesso."""
    template_name = TPL + "redefinir_concluido.html"
    
    
@login_required
@require_http_methods('POST')
def resetSenhaUsuario(request, usuario_id):
    
    usuario = Utilizador.objects.get(id=usuario_id)
    
    
    user = request.user
    
    dados = json.loads(request.body)
    user = request.user
    password = dados.get('password')

    if not user.check_password(password.strip()):

        return JsonResponse({'error': 'Credenciais inválidas'}, status=403)
    
    usuario.set_password('1234567890')
    usuario.save()
    messages.success(request,'Senha redifinida com sucesso!')
    
    
    return redirect('usuario_list')