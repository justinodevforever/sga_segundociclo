from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden

def escola_ativa_required(view_func):
    """
    Verifica se a escola do usuário está ativa e com plano válido
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'escola'):
            messages.error(request, 'Usuário não possui escola associada.')
            return redirect('login')
        
        escola = request.user.escola
        
        if not escola.activo:
            messages.error(request, 'Escola inativa. Entre em contato com o suporte.')
            return redirect('escola_inativa')
        
        # Verificar plano de subscrição
        from datetime import date
        if escola.data_expiracao_plano < date.today():
            messages.warning(request, 'Plano de subscrição expirado. Renove para continuar.')
            return redirect('renovar_plano')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def diretor_required(view_func):
    """
    Verifica se o usuário é um diretor
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'diretor'):
            messages.error(request, 'Acesso restrito a director.')
            return redirect('home')
        
        if request.user.diretor.status != 'Activo':
            messages.error(request, 'Director inativo.')
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper

def professor_required(view_func):
    """
    Verifica se o usuário é um professor
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'professor'):
            messages.error(request, 'Acesso restrito a professores.')
            return redirect('dashboard_admin')
        
        if request.user.professor.status != 'Activo':
            messages.error(request, 'Professor inativo.')
            return redirect('dashboard_admin')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def aluno_required(view_func):
    """
    Verifica se o usuário é um aluno
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'aluno'):
            messages.error(request, 'Acesso restrito a alunos.')
            return redirect('dashboard_admin')
        
        if request.user.aluno.status != 'Matriculado':
            messages.warning(request, 'Situação acadêmica irregular.')
            return redirect('dashboard_aluno')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def encarregado_required(view_func):
    """
    Verifica se o usuário é um encarregado de educação
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'encarregadoeducacao'):
            messages.error(request, 'Acesso restrito a encarregados de educação.')
            return redirect('dashboard_admin')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def admin_or_staff_required(view_func):
    """
    Verifica se o usuário é administrador ou staff
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Acesso restrito a administradores.')
            raise PermissionDenied
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def ajax_required(view_func):
    """
    Verifica se a requisição é AJAX
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return HttpResponseForbidden('Apenas requisições AJAX são permitidas.')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
