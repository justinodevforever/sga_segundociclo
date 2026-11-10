from app.db.models import *
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

def _tenant():
    obj = TenantConfiguracao.objects.first()
    return obj or TenantConfiguracao.objects.create()


def _erros(form):
    msgs = []
    for campo, lista in form.errors.items():
        nome = form.fields[campo].label if campo in form.fields else ""
        for e in lista:
            msgs.append(f"{nome}: {e}" if nome else e)
    return " ".join(msgs)


def _log(request, descricao, obj=None):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
          or request.META.get("REMOTE_ADDR") or "0.0.0.0")
    LogAuditoria.objects.create(
        utilizador=request.user,
        accao=LogAuditoria.Accao.ACTUALIZAR,
        modulo=LogAuditoria.Modulo.CONFIGURACAO,
        descricao=descricao,
        objeto_id=str(obj.pk) if obj is not None else None,
        objeto_tipo=obj.__class__.__name__ if obj is not None else None,
        ip_address=ip,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )


class DirectorAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    roles_permitidos = ("admin", "director")

    def test_func(self):
        u = self.request.user
        return u.is_superuser or u.usuario_roles.filter(
            role__nome__in=self.roles_permitidos, role__is_active=True
        ).exists()