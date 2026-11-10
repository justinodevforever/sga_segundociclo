# """
# Configuração do Django Admin para Certificados e Declarações.
# """
#
from django.contrib import admin
# from django.utils.html import format_html
# from django.utils.translation import gettext_lazy as _
#

# from academico.models import (
#     Avaliacao,
#     Nota,
#     ResultadoAnual,
#     ResultadoTrimestral,
#     TipoAvaliacao,
# )
from .models import (
    AssinaturaDocumento,
    DocumentoGerado,
    TemplateDocumento,
)

admin.site.register(DocumentoGerado)
#
#
# # ── Avaliação ──────────────────────────────────────────────────────────────────
#
# @admin.register(TipoAvaliacao)
# class TipoAvaliacaoAdmin(admin.ModelAdmin):
#     list_display = ["designacao", "categoria", "peso", "conta_para_mac", "escola"]
#     list_filter = ["categoria", "conta_para_mac", "escola"]
#     search_fields = ["designacao"]
#     ordering = ["escola", "categoria", "designacao"]
#
#
# @admin.register(Avaliacao)
# class AvaliacaoAdmin(admin.ModelAdmin):
#     list_display = ["designacao", "turma", "disciplina", "trimestre", "tipo_avaliacao", "data_realizacao"]
#     list_filter = ["escola", "trimestre", "tipo_avaliacao__categoria"]
#     search_fields = ["designacao", "turma__designacao", "disciplina__nome"]
#     date_hierarchy = "data_realizacao"
#     raw_id_fields = ["turma", "disciplina", "professor", "trimestre"]
#
#
# class NotaInline(admin.TabularInline):
#     model = Nota
#     fields = ["matricula", "nota", "faltou", "observacao"]
#     extra = 0
#     raw_id_fields = ["matricula"]
#
#
# @admin.register(Nota)
# class NotaAdmin(admin.ModelAdmin):
#     list_display = ["matricula", "avaliacao", "nota", "faltou", "data_lancamento"]
#     list_filter = ["escola", "faltou"]
#     search_fields = ["matricula__nome_completo", "avaliacao__designacao"]
#     raw_id_fields = ["matricula", "avaliacao", "lancado_por"]
#
#
# @admin.register(ResultadoTrimestral)
# class ResultadoTrimestralAdmin(admin.ModelAdmin):
#     list_display = ["matricula", "disciplina", "trimestre", "mac", "aprovado_trimestre", "ano_lectivo"]
#     list_filter = ["escola", "trimestre", "aprovado_trimestre", "ano_lectivo"]
#     search_fields = ["matricula__nome_completo", "disciplina__nome"]
#     raw_id_fields = ["matricula", "disciplina", "trimestre", "turma", "ano_lectivo"]
#
#
# @admin.register(ResultadoAnual)
# class ResultadoAnualAdmin(admin.ModelAdmin):
#     list_display = [
#         "matricula", "disciplina", "ano_lectivo",
#         "mac_1_trimestre", "mac_2_trimestre", "mac_3_trimestre",
#         "mac_anual", "nota_exame", "nota_final", "situacao",
#     ]
#     list_filter = ["escola", "ano_lectivo", "situacao"]
#     search_fields = ["matricula__nome_completo", "disciplina__nome"]
#     raw_id_fields = ["matricula", "disciplina", "turma", "ano_lectivo"]
#     readonly_fields = ["mac_anual", "nota_final", "situacao"]
#
#
# # ── Templates e Documentos ─────────────────────────────────────────────────────
#
# @admin.register(TemplateDocumento)
# class TemplateDocumentoAdmin(admin.ModelAdmin):
#     list_display = ["nome", "tipo_display", "escola", "e_padrao", "activo", "contador_atual"]
#     list_filter = ["tipo", "activo", "e_padrao", "escola"]
#     search_fields = ["nome", "escola__nome"]
#     readonly_fields = ["contador_atual"]
#     fieldsets = (
#         (_("Identificação"), {
#             "fields": ("escola", "tipo", "nome", "e_padrao", "activo"),
#         }),
#         (_("Cabeçalho"), {
#             "fields": ("cabecalho_titulo", "cabecalho_subtitulo", "mostrar_brasao", "mostrar_cabecalho_escola"),
#         }),
#         (_("Corpo"), {
#             "fields": ("texto_abertura", "texto_identificacao", "texto_corpo", "texto_rodape",
#                        "incluir_tabela_notas", "texto_antes_tabela"),
#         }),
#         (_("Data e Local"), {
#             "fields": ("local_emissao", "texto_data_emissao"),
#         }),
#         (_("Layout"), {
#             "fields": ("orientacao", "margem_topo", "margem_lateral", "tamanho_fonte_corpo", "usar_borda"),
#         }),
#         (_("Numeração"), {
#             "fields": ("prefixo_numeracao", "contador_atual"),
#         }),
#     )
#
#     @admin.display(description="Tipo")
#     def tipo_display(self, obj):
#         return obj.get_tipo_display()
#
#
# @admin.register(AssinaturaDocumento)
# class AssinaturaDocumentoAdmin(admin.ModelAdmin):
#     list_display = ["nome_completo", "cargo_display_admin", "escola", "ordem", "activo"]
#     list_filter = ["cargo", "activo", "escola"]
#     search_fields = ["nome_completo", "escola__nome"]
#     ordering = ["escola", "ordem"]
#
#     @admin.display(description="Cargo")
#     def cargo_display_admin(self, obj):
#         return obj.cargo_display
#
#
# @admin.register(DocumentoGerado)
# class DocumentoGeradoAdmin(admin.ModelAdmin):
#     list_display = [
#         "numero_documento_link", "matricula", "tipo_doc",
#         "ano_lectivo", "status_badge", "data_emissao", "emitido_por",
#     ]
#     list_filter = ["status", "template__tipo", "escola", "ano_lectivo"]
#     search_fields = ["numero_documento", "matricula__nome_completo"]
#     readonly_fields = [
#         "numero_documento", "conteudo_html", "dados_snapshot",
#         "data_emissao", "emitido_por", "data_criacao", "data_actualizacao",
#     ]
#     raw_id_fields = ["matricula", "matricula", "ano_lectivo", "template", "documento_original"]
#     ordering = ["-data_emissao"]
#
#     @admin.display(description="N.º Documento")
#     def numero_documento_link(self, obj):
#         if obj.status != "anulado":
#             return format_html(
#                 '<a href="/documentos/imprimir/{}/" target="_blank">{}</a>',
#                 obj.id,
#                 obj.numero_documento,
#             )
#         return format_html('<span style="color:#999;">{}</span>', obj.numero_documento)
#
#     @admin.display(description="Tipo")
#     def tipo_doc(self, obj):
#         return obj.template.get_tipo_display()
#
#     @admin.display(description="Estado")
#     def status_badge(self, obj):
#         cores = {
#             "emitido": ("#155724", "#d4edda"),
#             "rascunho": ("#856404", "#fff3cd"),
#             "anulado": ("#721c24", "#f8d7da"),
#             "segunda_via": ("#0c5460", "#d1ecf1"),
#         }
#         cor_texto, cor_fundo = cores.get(obj.status, ("#333", "#eee"))
#         return format_html(
#             '<span style="background:{};color:{};padding:2px 8px;border-radius:20px;font-size:0.78rem;font-weight:bold;">{}</span>',
#             cor_fundo, cor_texto, obj.get_status_display(),
#         )
#
#     def has_delete_permission(self, request, obj=None):
#         """Documentos emitidos não devem ser eliminados pelo admin."""
#         if obj and obj.status == "emitido":
#             return False
#         return super().has_delete_permission(request, obj)