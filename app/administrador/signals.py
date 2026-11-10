from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Role

User = get_user_model()

@receiver(post_migrate)
def create_default_superuser(sender, **kwargs):
    if sender.name != 'administrador': 
        return

    if Role.objects.count() == 0:
        admin_role = Role.objects.create(nome=1)
    else:
        admin_role = Role.objects.get(nome=1)

    if not User.objects.all().exists():
        User.objects.create_superuser(
            username="admin",
            password="admin123",
            nome_completo="Administrador do Sistema",
            role=admin_role
        )
        
    print(">> Usuário admin criado automaticamente!")
