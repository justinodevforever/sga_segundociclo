from django.core.management.base import BaseCommand
from db.models import TenantEscola
from doc.views import _criar_template_padrao
from doc.models import TemplateDocumento, AssinaturaDocumento

class Command(BaseCommand):
    help = 'Cria templates padrão de documentos para todas as escolas'

    def handle(self, *args, **options):
        for escola in TenantEscola.objects.filter(activo=True):
            for tipo, _ in TemplateDocumento.TipoDocumento.choices:
                if not TemplateDocumento.objects.filter(escola=escola, tipo=tipo).exists():
                    tmpl = _criar_template_padrao(escola, tipo, f'{tipo.title()} Padrão')
                    tmpl.e_padrao = True
                    tmpl.save()
                    self.stdout.write(f'✓ {escola.nome}: {tmpl.get_tipo_display()}')
        self.stdout.write(self.style.SUCCESS('Templates criados com sucesso!'))