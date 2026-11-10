# permissions.py
from django.db.models import Q

def _user_has_role(user, role_name):
    if not user.is_authenticated:
        return False
    
    from .models import UsuarioRole
    return UsuarioRole.objects.filter(
        utilizador=user,
        role__nome=role_name,
        role__is_active=True
    ).exists()

def _user_has_any_role(user, role_names):
    """Verifica se usuário tem pelo menos um dos roles"""
    if not user.is_authenticated:
        return False
    
    from .models import UsuarioRole
    return UsuarioRole.objects.filter(
        utilizador=user,
        role__nome__in=role_names,
        role__is_active=True
    ).exists()

def _user_has_all_roles(user, role_names):
    """Verifica se usuário tem todos os roles"""
    if not user.is_authenticated:
        return False
    
    from .models import UsuarioRole
    user_roles = UsuarioRole.objects.filter(
        utilizador=user,
        role__is_active=True
    ).values_list('role__nome', flat=True)
    
    return all(role_name in user_roles for role_name in role_names)


def is_admin(user):
    return user.is_superuser or _user_has_role(user, 'Admin')

def is_professor(user):
    return _user_has_role(user, 'professor')

def is_estudante(user):
    return _user_has_role(user, 'estudante')

def is_secretario(user):
    return _user_has_role(user, 'secretario')

def is_director(user):
    return _user_has_role(user, 'director')


# Funções compostas
def is_admin_or_director(user):
    return is_admin(user) or is_director(user)

def is_admin_or_secretario(user):
    return is_admin(user) or is_secretario(user)


# Funções auxiliares genéricas
def has_any_role(user, role_names):
    """
    Verifica se o usuário tem pelo menos um dos roles especificados.
    
    Args:
        user: Instância do usuário
        role_names: Lista de nomes de roles
    
    Returns:
        bool: True se tiver pelo menos um role
    """
    if user.is_superuser:
        return True
    return _user_has_any_role(user, role_names)

def has_all_roles(user, role_names):
    """
    Verifica se o usuário tem todos os roles especificados.
    
    Args:
        user: Instância do usuário
        role_names: Lista de nomes de roles
    
    Returns:
        bool: True se tiver todos os roles
    """
    if user.is_superuser:
        return True
    return _user_has_all_roles(user, role_names)

def get_user_roles(user):
   
    if not user.is_authenticated:
        return []
    
    if user.is_superuser:
        return ['Administrador']
    
    from .models import UsuarioRole
    
    roles = UsuarioRole.objects.filter(
        utilizador=user,
        role__is_active=True
    ).select_related("role")

    return [r.role.get_nome_display() for r in roles]
    

def get_user_permissions(user):
    """
    Retorna todas as permissões do usuário baseado em seus roles.
    
    Args:
        user: Instância do usuário
    
    Returns:
        QuerySet: Permissões do usuário
    """
    if not user.is_authenticated:
        from .models import Permission
        return Permission.objects.none()
    
    if user.is_superuser:
        from .models import Permission
        return Permission.objects.all()
    
    from .models import UsuarioRole, RolePermissao, Permissao
    
    user_role_ids = UsuarioRole.objects.filter(
        utilizador=user,
        role__is_active=True
    ).values_list('role_id', flat=True)
    
    permission_ids = RolePermissao.objects.filter(
        role_id__in=user_role_ids
    ).values_list('permissao_id', flat=True)
    
    return Permission.objects.filter(id__in=permission_ids)

def user_has_permission(user, resource, action):
    """
    Verifica se usuário tem permissão específica.
    
    Args:
        user: Instância do usuário
        resource: Nome do recurso (ex: 'product', 'user')
        action: Ação (ex: 'create', 'read', 'update', 'delete')
    
    Returns:
        bool: True se tiver permissão
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    from .models import UsuarioRole, RolePermissao, Permissao
    
    try:
        permissao = Permissao.objects.get(resource=resource, action=action)
    except Permissao.DoesNotExist:
        return False
    
    user_role_ids = UsuarioRole.objects.filter(
        utilizador=user,
        role__is_active=True
    ).values_list('role_id', flat=True)
    
    return RolePermissao.objects.filter(
        role_id__in=user_role_ids,
        permissao=permissao
    ).exists()

def user_can_access_resource(user, nome):
    """
    Verifica se usuário tem qualquer permissão sobre um recurso.
    
    Args:
        user: Instância do usuário
        nome: Nome do recurso
    
    Returns:
        bool: True se tiver alguma permissão sobre o recurso
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    from .models import UsuarioRole, RolePermissao, Permissao
    
    user_role_ids = UsuarioRole.objects.filter(
        utilizador=user,
        role__is_active=True
    ).values_list('role_id', flat=True)
    
    return RolePermissao.objects.filter(
        role_id__in=user_role_ids,
        permissao__nome=nome
    ).exists()