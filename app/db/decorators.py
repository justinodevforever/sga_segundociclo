# decorators.py
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from functools import wraps
from .permissions import has_any_role, has_all_roles, user_has_permission
from django.contrib import messages

def role_required(*role_names):

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            if has_any_role(request.user, role_names):
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied(
                f"Você precisa ter um dos seguintes roles: {', '.join(role_names)}"
            )
        return wrapper
    return decorator

def roles_required(*role_names):
    """
    Decorator que verifica se usuário tem TODOS os roles especificados.

    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            if has_all_roles(request.user, role_names):
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied(
                f"Você precisa ter todos os seguintes roles: {', '.join(role_names)}"
            )
        return wrapper
    return decorator

def permission_required(resource, action):
    """
    Decorator que verifica permissão específica (resource + action).
    
    Usage:
        @permission_required('product', 'create')
        def create_product(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            if user_has_permission(request.user, resource, action):
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied(
                f"Você não tem permissão para '{action}' em '{resource}'"
            )
        return wrapper
    return decorator

def any_permission_required(*permissions):
    """
    Decorator que verifica se usuário tem pelo menos uma das permissões.
    
    Usage:
        @any_permission_required(
            ('product', 'create'),
            ('product', 'update')
        )
        def edit_product(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            for resource, action in permissions:
                if user_has_permission(request.user, resource, action):
                    return view_func(request, *args, **kwargs)
            
            raise PermissionDenied(
                "Você não tem nenhuma das permissões necessárias"
            )
        return wrapper
    return decorator

def superuser_required(view_func):
    """
    Decorator que permite acesso apenas para superusers.
    
    Usage:
        @superuser_required
        def admin_only_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        if not request.user.is_superuser:
            raise PermissionDenied("Apenas superusers têm acesso")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def escola_ativa_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'escola'):
            messages.error(request, 'Usuário não possui escola associada.')
            return redirect('login')
        
        escola = request.user.escola
        
        if not escola.status_ensino:
            messages.error(request, 'Escola inativa. Entre em contato com o suporte.')
            return redirect('escola_inativa')
        
        # Verificar plano de subscrição
        from datetime import date
        if escola.data_expiracao_plano < date.today():
            messages.warning(request, 'Plano de subscrição expirado. Renove para continuar.')
            return redirect('renovar_plano')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def periodo_ativo_required(view_func):
    """
    Verifica se há um período avaliativo ativo
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'escola'):
            messages.error(request, 'Escola não encontrada.')
            return redirect('login')
        
        configuracao = request.user.escola.configuracao
        
        if not configuracao.periodo_activo:
            messages.warning(request, 'Nenhum período avaliativo ativo no momento.')
            return redirect('dashboard_admin')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def ano_lectivo_ativo_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'escola'):
            messages.error(request, 'Escola não encontrada.')
            return redirect('login')
        
        configuracao = request.user.escola.configuracao
        
        if not configuracao.ano_lectivo_activo:
            messages.warning(request, 'Nenhum ano letivo ativo no momento.')
            return redirect('configuracao_escola')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper