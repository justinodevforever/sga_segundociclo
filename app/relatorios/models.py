from django.db import models
from app.db.models import *
from app.authenticate.models import *

# Create your models here.
class RelatorioConfiguracao(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TIPOS = [("Académico","Académico"),("Financeiro","Financeiro"),("Estatístico","Estatístico"),("INIDE","INIDE")]
    FORMATOS = [("PDF","PDF"),("Excel","Excel"),("CSV","CSV")]
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50, choices=TIPOS)
    template = models.TextField(blank=True)
    parametros = models.JSONField(default=dict, blank=True)
    formato_saida = models.CharField(max_length=10, choices=FORMATOS, default="PDF")
    agendamento = models.JSONField(default=dict, blank=True)
    activo = models.BooleanField(default=True)


class RelatorioGerado(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuracao = models.ForeignKey(RelatorioConfiguracao, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=200)
    parametros_usados = models.JSONField(default=dict, blank=True)
    arquivo = models.FileField(upload_to="relatorios/gerados/")
    gerado_por = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)