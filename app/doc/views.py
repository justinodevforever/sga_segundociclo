"""
Views para Certificados e Declarações — II Ciclo Angola.

URLs sugeridas (inclui no seu urls.py):

    path('documentos/', include('documentos.urls')),

Funcionalidades:
  - Listar/criar/editar templates
  - Pré-visualizar documento antes de emitir
  - Emitir documento (cria DocumentoGerado)
  - Imprimir documento (HTML para impressão)
  - Histórico de documentos emitidos
  - Anular / segunda via
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .models import (
    AssinaturaDocumento,
    DocumentoGerado,
    TemplateDocumento,
)
from .utils.gerador import construir_snapshot, gerar_html_documento


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_escola(request):
    """Obtém a escola do utilizador autenticado."""
    return request.user.escola


def _get_resultados(aluno, matricula, ano_lectivo):
    """Obtém os ResultadoAnual do aluno para o ano lectivo."""
    from app.db.models import ResultadoAnual
    if not matricula or not matricula.turma:
        return []
    return list(
        ResultadoAnual.objects.filter(
            aluno=aluno,
            ano_lectivo=ano_lectivo,
            escola=aluno.escola,
        ).select_related("disciplina").order_by("disciplina__nome")
    )


def _get_assinaturas(escola):
    return list(AssinaturaDocumento.objects.filter(escola=escola, activo=True).order_by("ordem"))


# ── Templates de documentos ────────────────────────────────────────────────────

@login_required
def lista_templates(request):
    """Lista todos os templates de documentos da escola."""
    escola = _get_escola(request)
    templates = TemplateDocumento.objects.filter(escola=escola).order_by("tipo", "nome")

    contexto = {
        "templates": templates,
        "tipos": TemplateDocumento.TipoDocumento.choices,
        "titulo": _("Templates de Documentos"),
    }
    return render(request, "documentos/templates/lista.html", contexto)


@login_required
def detalhe_template(request, template_id):
    """Edita um template de documento."""
    escola = _get_escola(request)
    template = get_object_or_404(TemplateDocumento, id=template_id, escola=escola)

    if request.method == "POST":
        # Actualiza apenas os campos editáveis pelo utilizador
        campos_editaveis = [
            "cabecalho_titulo", "cabecalho_subtitulo", "texto_abertura",
            "texto_identificacao", "texto_corpo", "texto_rodape",
            "texto_antes_tabela", "local_emissao", "texto_data_emissao",
            "mostrar_brasao", "mostrar_cabecalho_escola",
            "incluir_tabela_notas", "usar_borda",
            "orientacao", "margem_topo", "margem_lateral",
            "tamanho_fonte_corpo", "prefixo_numeracao", "nome", "e_padrao",
        ]
        for campo in campos_editaveis:
            if campo in request.POST:
                valor = request.POST[campo]
                if isinstance(getattr(TemplateDocumento, campo, None), property):
                    continue
                campo_info = TemplateDocumento._meta.get_field(campo)
                if campo_info.get_internal_type() == "BooleanField":
                    valor = campo in request.POST
                elif campo_info.get_internal_type() == "IntegerField":
                    try:
                        valor = int(valor)
                    except (ValueError, TypeError):
                        continue
                setattr(template, campo, valor)

        try:
            template.full_clean()
            template.save()
            messages.success(request, _("Template actualizado com sucesso."))
        except Exception as e:
            messages.error(request, f"Erro: {e}")

        return redirect("documentos:detalhe_template", template_id=template.id)

    contexto = {
        "template": template,
        "variaveis_disponiveis": _VARIAVEIS_DESCRICAO,
        "titulo": f"Editar Template — {template.nome}",
    }
    return render(request, "documentos/templates/editar.html", contexto)


@login_required
def criar_template(request):
    """Cria um novo template a partir de um tipo seleccionado."""
    escola = _get_escola(request)

    if request.method == "POST":
        tipo = request.POST.get("tipo")
        nome = request.POST.get("nome", "Novo Template")

        if tipo not in dict(TemplateDocumento.TipoDocumento.choices):
            messages.error(request, _("Tipo de documento inválido."))
            return redirect("documentos:lista_templates")

        # Cria com valores por defeito adequados ao tipo
        template = _criar_template_padrao(escola, tipo, nome)
        messages.success(request, _("Template criado. Personalize-o agora."))
        return redirect("documentos:detalhe_template", template_id=template.id)

    contexto = {
        "tipos": TemplateDocumento.TipoDocumento.choices,
        "titulo": _("Criar Novo Template"),
    }
    return render(request, "documentos/templates/criar.html", contexto)


# ── Geração de documentos ──────────────────────────────────────────────────────

@login_required
def selecionar_aluno_documento(request):
    """
    Passo 1: Seleccionar o aluno e o tipo de documento a gerar.
    """
    from academico.models import Aluno, AnoLectivo
    escola = _get_escola(request)

    alunos = Aluno.objects.filter(escola=escola).order_by("nome_completo")
    templates = TemplateDocumento.objects.filter(escola=escola, activo=True).order_by("tipo", "nome")
    anos = AnoLectivo.objects.filter(escola=escola).order_by("-designacao")

    contexto = {
        "alunos": alunos,
        "templates": templates,
        "anos_lectivos": anos,
        "titulo": _("Gerar Documento"),
    }
    return render(request, "documentos/gerar/selecionar.html", contexto)


@login_required
def previsualizar_documento(request):
    """
    Passo 2: Pré-visualiza o documento com os dados do aluno.
    Recebe via GET: aluno_id, template_id, ano_lectivo_id
    """
    from academico.models import Aluno, AnoLectivo, Matricula
    escola = _get_escola(request)

    aluno_id = request.GET.get("aluno_id") or request.POST.get("aluno_id")
    template_id = request.GET.get("template_id") or request.POST.get("template_id")
    ano_lectivo_id = request.GET.get("ano_lectivo_id") or request.POST.get("ano_lectivo_id")

    if not all([aluno_id, template_id, ano_lectivo_id]):
        messages.error(request, _("Parâmetros em falta. Seleccione aluno, template e ano lectivo."))
        return redirect("documentos:selecionar_aluno_documento")

    aluno = get_object_or_404(Aluno, id=aluno_id, escola=escola)
    template = get_object_or_404(TemplateDocumento, id=template_id, escola=escola)
    ano_lectivo = get_object_or_404(AnoLectivo, id=ano_lectivo_id, escola=escola)

    matricula = Matricula.objects.filter(
        aluno=aluno, ano_lectivo=ano_lectivo
    ).select_related("turma", "turma__classe", "turma__curso", "turma__periodo").first()

    resultados = _get_resultados(aluno, matricula, ano_lectivo)
    assinaturas = _get_assinaturas(escola)

    html_documento = gerar_html_documento(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados,
        assinaturas=assinaturas,
        numero_documento="PRÉ-VISUALIZAÇÃO",
    )

    contexto = {
        "html_documento": html_documento,
        "aluno": aluno,
        "template": template,
        "ano_lectivo": ano_lectivo,
        "matricula": matricula,
        "resultados": resultados,
        "titulo": _("Pré-visualização do Documento"),
    }
    return render(request, "documentos/gerar/previsualizar.html", contexto)


@login_required
@require_POST
def emitir_documento(request):
    """
    Passo 3: Emite o documento (cria DocumentoGerado com status=emitido).
    """
    from academico.models import Aluno, AnoLectivo, Matricula
    escola = _get_escola(request)

    aluno_id = request.POST.get("aluno_id")
    template_id = request.POST.get("template_id")
    ano_lectivo_id = request.POST.get("ano_lectivo_id")

    aluno = get_object_or_404(Aluno, id=aluno_id, escola=escola)
    template = get_object_or_404(TemplateDocumento, id=template_id, escola=escola)
    ano_lectivo = get_object_or_404(AnoLectivo, id=ano_lectivo_id, escola=escola)

    matricula = Matricula.objects.filter(
        aluno=aluno, ano_lectivo=ano_lectivo
    ).select_related("turma", "turma__classe", "turma__curso", "turma__periodo").first()

    resultados = _get_resultados(aluno, matricula, ano_lectivo)
    assinaturas = _get_assinaturas(escola)
    numero_documento = template.proximo_numero()

    html_documento = gerar_html_documento(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados,
        assinaturas=assinaturas,
        numero_documento=numero_documento,
        data_emissao=timezone.now().date(),
    )

    snapshot = construir_snapshot(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados,
        numero_documento=numero_documento,
    )

    documento = DocumentoGerado.objects.create(
        escola=escola,
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        numero_documento=numero_documento,
        conteudo_html=html_documento,
        dados_snapshot=snapshot,
        status=DocumentoGerado.Status.EMITIDO,
        data_emissao=timezone.now(),
        emitido_por=request.user,
    )

    messages.success(request, _(f"Documento {numero_documento} emitido com sucesso."))
    return redirect("documentos:imprimir_documento", documento_id=documento.id)


@login_required
def imprimir_documento(request, documento_id):
    """
    Serve o HTML do documento para impressão.
    Usa o snapshot guardado para garantir imutabilidade.
    """
    escola = _get_escola(request)
    documento = get_object_or_404(DocumentoGerado, id=documento_id, escola=escola)

    if documento.status == DocumentoGerado.Status.ANULADO:
        messages.error(request, _("Este documento foi anulado e não pode ser impresso."))
        return redirect("documentos:historico_documentos")

    # Serve o HTML guardado (snapshot imutável)
    return HttpResponse(documento.conteudo_html, content_type="text/html; charset=utf-8")


@login_required
def imprimir_novo(request, documento_id):
    """
    Regenera e serve o HTML de um documento existente para reimpressão.
    Usa os dados do snapshot para reconstituir o documento idêntico.
    """
    escola = _get_escola(request)
    documento = get_object_or_404(DocumentoGerado, id=documento_id, escola=escola)

    if documento.status == DocumentoGerado.Status.ANULADO:
        messages.error(request, _("Documento anulado."))
        return redirect("documentos:historico_documentos")

    # Usa o conteúdo guardado
    return HttpResponse(documento.conteudo_html, content_type="text/html; charset=utf-8")


# ── Histórico ──────────────────────────────────────────────────────────────────

@login_required
def historico_documentos(request):
    """Lista todos os documentos emitidos da escola."""
    escola = _get_escola(request)

    documentos = DocumentoGerado.objects.filter(escola=escola).select_related(
        "aluno", "template", "ano_lectivo", "emitido_por"
    ).order_by("-data_emissao")

    # Filtros
    aluno_q = request.GET.get("aluno", "")
    tipo_q = request.GET.get("tipo", "")
    status_q = request.GET.get("status", "")

    if aluno_q:
        documentos = documentos.filter(aluno__nome_completo__icontains=aluno_q)
    if tipo_q:
        documentos = documentos.filter(template__tipo=tipo_q)
    if status_q:
        documentos = documentos.filter(status=status_q)

    contexto = {
        "documentos": documentos,
        "tipos": TemplateDocumento.TipoDocumento.choices,
        "status_choices": DocumentoGerado.Status.choices,
        "filtro_aluno": aluno_q,
        "filtro_tipo": tipo_q,
        "filtro_status": status_q,
        "titulo": _("Histórico de Documentos Emitidos"),
    }
    return render(request, "documentos/historico/lista.html", contexto)


@login_required
@require_POST
def anular_documento(request, documento_id):
    """Anula um documento emitido."""
    escola = _get_escola(request)
    documento = get_object_or_404(DocumentoGerado, id=documento_id, escola=escola)
    motivo = request.POST.get("motivo", "").strip()

    if not motivo:
        messages.error(request, _("É obrigatório indicar o motivo da anulação."))
        return redirect("documentos:historico_documentos")

    try:
        documento.anular(motivo)
        messages.success(request, _(f"Documento {documento.numero_documento} anulado."))
    except Exception as e:
        messages.error(request, str(e))

    return redirect("documentos:historico_documentos")


@login_required
@require_POST
def segunda_via(request, documento_id):
    """Emite uma segunda via de um documento existente."""
    from academico.models import Matricula
    escola = _get_escola(request)
    original = get_object_or_404(DocumentoGerado, id=documento_id, escola=escola)

    if original.status != DocumentoGerado.Status.EMITIDO:
        messages.error(request, _("Apenas documentos emitidos podem ter 2ª via."))
        return redirect("documentos:historico_documentos")

    numero_documento = original.template.proximo_numero()

    # Regenera com novo número e data
    assinaturas = _get_assinaturas(escola)
    resultados = _get_resultados(
        original.aluno,
        original.matricula,
        original.ano_lectivo,
    )
    html_documento = gerar_html_documento(
        template=original.template,
        aluno=original.aluno,
        matricula=original.matricula,
        ano_lectivo=original.ano_lectivo,
        resultados_anuais=resultados,
        assinaturas=assinaturas,
        numero_documento=numero_documento,
        data_emissao=timezone.now().date(),
    )
    snapshot = construir_snapshot(
        template=original.template,
        aluno=original.aluno,
        matricula=original.matricula,
        ano_lectivo=original.ano_lectivo,
        resultados_anuais=resultados,
        numero_documento=numero_documento,
    )

    segunda = DocumentoGerado.objects.create(
        escola=escola,
        template=original.template,
        aluno=original.aluno,
        matricula=original.matricula,
        ano_lectivo=original.ano_lectivo,
        numero_documento=numero_documento,
        conteudo_html=html_documento,
        dados_snapshot=snapshot,
        status=DocumentoGerado.Status.SEGUNDA_VIA,
        data_emissao=timezone.now(),
        emitido_por=request.user,
        documento_original=original,
    )

    messages.success(request, _(f"2ª via emitida: {numero_documento}."))
    return redirect("documentos:imprimir_documento", documento_id=segunda.id)


# ── API JSON (para pré-visualização AJAX) ─────────────────────────────────────

@login_required
def api_previsualizar_html(request):
    """
    Endpoint JSON que devolve o HTML do documento para pré-visualização
    em iframe sem navegar para nova página.
    """
    from academico.models import Aluno, AnoLectivo, Matricula

    escola = _get_escola(request)
    aluno_id = request.GET.get("aluno_id")
    template_id = request.GET.get("template_id")
    ano_lectivo_id = request.GET.get("ano_lectivo_id")

    try:
        aluno = Aluno.objects.get(id=aluno_id, escola=escola)
        template = TemplateDocumento.objects.get(id=template_id, escola=escola)
        ano_lectivo = AnoLectivo.objects.get(id=ano_lectivo_id, escola=escola)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=400)

    matricula = Matricula.objects.filter(
        aluno=aluno, ano_lectivo=ano_lectivo
    ).select_related("turma__classe", "turma__curso", "turma__periodo").first()

    resultados = _get_resultados(aluno, matricula, ano_lectivo)
    assinaturas = _get_assinaturas(escola)

    html = gerar_html_documento(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados,
        assinaturas=assinaturas,
        numero_documento="PRÉ-VISUALIZAÇÃO",
    )
    return JsonResponse({"html": html})


# ── Dados auxiliares ───────────────────────────────────────────────────────────

_VARIAVEIS_DESCRICAO = [
    ("aluno_nome", "Nome completo do aluno"),
    ("aluno_bi", "Bilhete de Identidade"),
    ("aluno_naturalidade", "Naturalidade"),
    ("aluno_data_nasc", "Data de nascimento"),
    ("aluno_nome_pai", "Nome do pai"),
    ("aluno_nome_mae", "Nome da mãe"),
    ("aluno_numero_processo", "Número de processo"),
    ("ano_lectivo", "Ano lectivo (ex: 2023/2024)"),
    ("classe", "Classe (ex: 12ª Classe)"),
    ("curso", "Nome do curso"),
    ("turma", "Designação da turma"),
    ("periodo", "Período (Manhã/Tarde/Noite)"),
    ("nota_final_num", "Nota final numérica"),
    ("nota_final_extenso", "Nota final por extenso"),
    ("situacao_final", "Situação final (Aprovado/Reprovado)"),
    ("media_geral", "Média geral das disciplinas"),
    ("escola_nome", "Nome da escola"),
    ("escola_provincia", "Província da escola"),
    ("escola_municipio", "Município da escola"),
    ("escola_nif", "NIF da escola"),
    ("escola_director", "Nome do director"),
    ("data_emissao", "Data de emissão"),
    ("local_emissao", "Local de emissão"),
    ("numero_documento", "Número do documento"),
    ("tipo_documento", "Tipo do documento (ex: certificado)"),
]


def _criar_template_padrao(escola, tipo, nome) -> TemplateDocumento:
    """Cria um template com textos padrão adequados ao tipo."""
    DEFAULTS = {
        TemplateDocumento.TipoDocumento.CERTIFICADO: {
            "cabecalho_titulo": "CERTIFICADO DE HABILITAÇÕES",
            "texto_abertura": (
                "O(A) Director(a) da {{escola_nome}}, no uso das suas competências "
                "e ao abrigo do Decreto Executivo n.º 3/19 de 2 de Janeiro, certifica que:"
            ),
            "texto_corpo": (
                "concluiu com aproveitamento o {{classe}} do Ensino Secundário, "
                "Curso de {{curso}}, Período: {{periodo}}, no ano lectivo {{ano_lectivo}}, "
                "tendo obtido a classificação final de {{nota_final_num}} valores "
                "({{nota_final_extenso}}), com situação final: {{situacao_final}}."
            ),
            "texto_rodape": (
                "O presente certificado é emitido a pedido do(a) interessado(a) "
                "e para os fins que o(a) mesmo(a) entender convenientes, "
                "sendo passado em duplicado, fazendo fé onde for apresentado."
            ),
            "prefixo_numeracao": "CERT",
            "incluir_tabela_notas": True,
        },
        TemplateDocumento.TipoDocumento.DECLARACAO_MATRICULA: {
            "cabecalho_titulo": "DECLARAÇÃO DE MATRÍCULA",
            "texto_abertura": (
                "O(A) Director(a) da {{escola_nome}}, declara para os devidos efeitos legais que:"
            ),
            "texto_corpo": (
                "se encontra regularmente matriculado(a) no {{classe}} do Ensino Secundário, "
                "Curso de {{curso}}, Turma {{turma}}, Período {{periodo}}, "
                "no ano lectivo {{ano_lectivo}}."
            ),
            "texto_rodape": (
                "A presente declaração é emitida a pedido do(a) interessado(a) "
                "para os fins que o(a) mesmo(a) entender."
            ),
            "prefixo_numeracao": "DM",
            "incluir_tabela_notas": False,
        },
        TemplateDocumento.TipoDocumento.DECLARACAO_FREQUENCIA: {
            "cabecalho_titulo": "DECLARAÇÃO DE FREQUÊNCIA",
            "texto_abertura": (
                "O(A) Director(a) da {{escola_nome}}, declara para os devidos efeitos que:"
            ),
            "texto_corpo": (
                "frequentou com regularidade o {{classe}} do Ensino Secundário, "
                "Curso de {{curso}}, Turma {{turma}}, Período {{periodo}}, "
                "no ano lectivo {{ano_lectivo}}."
            ),
            "texto_rodape": (
                "A presente declaração é emitida a pedido do(a) interessado(a) "
                "para os fins que o(a) mesmo(a) entender."
            ),
            "prefixo_numeracao": "DF",
            "incluir_tabela_notas": False,
        },
        TemplateDocumento.TipoDocumento.DECLARACAO_NOTAS: {
            "cabecalho_titulo": "DECLARAÇÃO DE NOTAS",
            "texto_abertura": (
                "O(A) Director(a) da {{escola_nome}}, declara que o(a) aluno(a):"
            ),
            "texto_corpo": (
                "obteve as seguintes classificações no {{classe}} do Ensino Secundário, "
                "Curso de {{curso}}, no ano lectivo {{ano_lectivo}}, "
                "conforme tabela abaixo."
            ),
            "texto_rodape": (
                "A presente declaração é emitida a pedido do(a) interessado(a) "
                "para os fins que o(a) mesmo(a) entender."
            ),
            "prefixo_numeracao": "DN",
            "incluir_tabela_notas": True,
        },
        TemplateDocumento.TipoDocumento.DECLARACAO_CONCLUSAO: {
            "cabecalho_titulo": "DECLARAÇÃO DE CONCLUSÃO DE CURSO",
            "texto_abertura": (
                "O(A) Director(a) da {{escola_nome}}, declara para os devidos efeitos que:"
            ),
            "texto_corpo": (
                "concluiu com sucesso o Ensino Secundário, {{classe}}, "
                "Curso de {{curso}}, no ano lectivo {{ano_lectivo}}, "
                "obtendo a média geral de {{media_geral}} valores."
            ),
            "texto_rodape": (
                "A presente declaração é emitida a pedido do(a) interessado(a), "
                "aguardando a emissão do Certificado definitivo."
            ),
            "prefixo_numeracao": "DC",
            "incluir_tabela_notas": True,
        },
    }

    defaults = DEFAULTS.get(tipo, {})
    template = TemplateDocumento(
        escola=escola,
        tipo=tipo,
        nome=nome,
        criado_por=None,
        **defaults,
    )
    template.save()
    return template