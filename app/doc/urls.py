from django.urls import path
from .views import *

app_name = "documentos"

urlpatterns = [

    path("templates/", lista_templates, name="lista_templates"),
    path("templates/criar/", criar_template, name="criar_template"),
    path("templates/<uuid:template_id>/", detalhe_template, name="detalhe_template"),

    path("gerar/", selecionar_aluno_documento, name="selecionar_aluno_documento"),
    path("gerar/previsualizar/", previsualizar_documento, name="previsualizar_documento"),
    path("gerar/emitir/", emitir_documento, name="emitir_documento"),

    path("imprimir/<uuid:documento_id>/", imprimir_documento, name="imprimir_documento"),
    path("imprimir/<uuid:documento_id>/novo/", imprimir_novo, name="imprimir_novo"),

    path("historico/", historico_documentos, name="historico_documentos"),
    path("historico/<uuid:documento_id>/anular/", anular_documento, name="anular_documento"),
    path("historico/<uuid:documento_id>/segunda-via/", segunda_via, name="segunda_via"),

    path("api/previsualizar/", api_previsualizar_html, name="api_previsualizar_html"),
]