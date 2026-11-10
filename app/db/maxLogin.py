from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.base import ContextMixin
from django.shortcuts import redirect
from django.contrib import messages

class EscolaContextMixin(ContextMixin):
    """
    Adiciona informações da escola ao contexto
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'escola'):
            escola = self.request.user.escola
            context['escola'] = escola
            context['configuracoes'] = escola.configuracao
            context['ano_lectivo_activo'] = escola.configuracao.ano_lectivo_activo
            context['periodo_activo'] = escola.configuracao.periodo_activo
        
        return context


class EscolaAtivaRequiredMixin(UserPassesTestMixin):
    """
    Verifica se a escola está ativa (para CBV)
    """
    def test_func(self):
        if not hasattr(self.request.user, 'escola'):
            return False
        
        escola = self.request.user.escola
        
        if not escola.activo:
            return False
        
        from datetime import date
        if escola.data_expiracao_plano < date.today():
            return False
        
        return True
    
    def handle_no_permission(self):
        messages.error(self.request, 'Escola inativa ou plano expirado.')
        return redirect('escola_inativa')


class ProfessorRequiredMixin(UserPassesTestMixin):
    """
    Verifica se o usuário é professor (para CBV)
    """
    def test_func(self):
        return (hasattr(self.request.user, 'professor') and 
                self.request.user.professor.status == 'Activo')
    
    def handle_no_permission(self):
        messages.error(self.request, 'Acesso restrito a professores.')
        return redirect('dashboard_admin')


class AlunoRequiredMixin(UserPassesTestMixin):
    """
    Verifica se o usuário é aluno (para CBV)
    """
    def test_func(self):
        return (hasattr(self.request.user, 'aluno') and 
                self.request.user.aluno.status == 'Matriculado')
    
    def handle_no_permission(self):
        messages.error(self.request, 'Acesso restrito a alunos.')
        return redirect('dashboard_admin')


class EncarregadoRequiredMixin(UserPassesTestMixin):
    """
    Verifica se o usuário é encarregado (para CBV)
    """
    def test_func(self):
        return hasattr(self.request.user, 'encarregadoeducacao')
    
    def handle_no_permission(self):
        messages.error(self.request, 'Acesso restrito a encarregados.')
        return redirect('dashboard_admin')


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Verifica se o usuário é administrador (para CBV)
    """
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(self.request, 'Acesso restrito a administradores.')
        raise PermissionDenied


class MultiplePermissionsRequiredMixin(UserPassesTestMixin):
    """
    Verifica múltiplas permissões
    """
    permissions_required = []
    
    def test_func(self):
        user = self.request.user
        
        for perm in self.permissions_required:
            if perm == 'is_professor':
                if not hasattr(user, 'professor'):
                    return False
            elif perm == 'is_aluno':
                if not hasattr(user, 'aluno'):
                    return False
            elif perm == 'is_encarregado':
                if not hasattr(user, 'encarregadoeducacao'):
                    return False
            elif perm == 'is_admin':
                if not (user.is_staff or user.is_superuser):
                    return False
        
        return True