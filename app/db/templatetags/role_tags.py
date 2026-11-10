from django import template
from ..permissions import *

register = template.Library()

@register.filter(name='has_role')
def has_role(user, role_name):
    """
    Uso: {% if request.user|has_role:'Admin' %}
    """
    from ..permissions import _user_has_role
    return _user_has_role(user, role_name)

@register.filter(name='has_any_role')
def has_any_roles_filter(user, role_names):
    """
    Uso: {% if request.user|has_any_role:'Admin,Coordenador' %}
    """
    if isinstance(role_names, str):
        role_names = [r.strip() for r in role_names.split(',')]
    return has_any_role(user, role_names)

@register.filter(name='has_all_roles')
def has_all_roles_filter(user, role_names):
    """
    Uso: {% if request.user|has_all_roles:'Professor,Coordenador' %}
    """
    if isinstance(role_names, str):
        role_names = [r.strip() for r in role_names.split(',')]
    return has_all_roles(user, role_names)

@register.filter(name='has_permission')
def has_permission_filter(user, permission):
    """
    Uso: {% if request.user|has_permission:'product.create' %}
    """
    if '.' not in permission:
        return False
    resource, action = permission.split('.', 1)
    return user_has_permission(user, resource, action)

@register.simple_tag
def user_can(user, resource, action):
    """
    Uso: {% user_can request.user 'product' 'create' as can_create %}
          {% if can_create %}...{% endif %}
    """
    return user_has_permission(user, resource, action)

@register.simple_tag
def check_role(user, role_name):
    """
    Uso: {% check_role request.user 'Admin' as is_admin %}
          {% if is_admin %}...{% endif %}
    """
    from ..permissions import _user_has_role
    return _user_has_role(user, role_name)

@register.simple_tag
def check_any_role(user, *role_names):
    """
    Uso: {% check_any_role request.user 'Admin' 'Coordenador' as has_access %}
          {% if has_access %}...{% endif %}
    """
    return has_any_role(user, role_names)

# Funções específicas como filtros
@register.filter
def is_admin_user(user):
    return is_admin(user)

@register.filter
def is_director_user(user):
    return is_director(user)

@register.filter
def is_professor_user(user):
    return is_professor(user)

@register.filter
def is_secretario_user(user):
    return is_secretario(user)

@register.filter
def is_estudante_user(user):
    return is_estudante(user)

@register.simple_tag
def get_roles(user):

    return get_user_roles(user)

@register.inclusion_tag('components/role_badge.html')
def show_user_roles(user):

    return {
        'roles': get_user_roles(user),
        'user': user
    }