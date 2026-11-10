from django.contrib import admin
from .models import *
from app.financa.models import *
# Register your models here.

admin.site.register(Disciplina)
admin.site.register(TenantConfiguracao)
admin.site.register(Turma)
admin.site.register(Funcionario)
admin.site.register(Aluno)
admin.site.register(Diretor)
admin.site.register(AnoLectivo)
admin.site.register(Curso)
admin.site.register(Classe)
admin.site.register(HorarioAula)
admin.site.register(Matricula)
admin.site.register(UsuarioRole)
admin.site.register(Role)
admin.site.register(Candidato)
admin.site.register(Utilizador)
admin.site.register(Inscricao)
admin.site.register(ResultadoTrimestral)
admin.site.register(ResultadoAnual)
admin.site.register(Periodo)
admin.site.register(Trimestre)
admin.site.register(AtribuicaoDocente)
admin.site.register(PlanoCurricular)
admin.site.register(RegraAvaliacao)
admin.site.register(Pagamento)
admin.site.register(PropinaMensal)
admin.site.register(DocumentoAluno)

