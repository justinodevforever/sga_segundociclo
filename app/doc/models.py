"""
Modelos para Certificados e Declarações do II Ciclo — Angola.

Arquitectura:
  - TemplateDocumento: Define o modelo (certificado ou declaração)
    com blocos de texto personalizáveis e variáveis dinâmicas.
  - DocumentoGerado: Registo de cada documento emitido.
  - AssinaturaDocumento: Assinaturas configuradas por escola.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import uuid


class TemplateDocumento(models.Model):
    """
    Template personalizável de Certificado ou Declaração.

    O utilizador pode editar os blocos de texto do template.
    As variáveis dinâmicas são substituídas na geração do documento.

    Variáveis disponíveis (sintaxe: {{variavel}}):
      Aluno:
        {{aluno_nome}}          — Nome completo do aluno
        {{aluno_bi}}            — Bilhete de Identidade
        {{aluno_naturalidade}}  — Naturalidade
        {{aluno_data_nasc}}     — Data de nascimento
        {{aluno_nome_pai}}      — Nome do pai
        {{aluno_nome_mae}}      — Nome da mãe
        {{aluno_numero_processo}} — Número de processo

      Académico:
        {{ano_lectivo}}         — Ex: "2023/2024"
        {{classe}}              — Ex: "12ª Classe"
        {{curso}}               — Nome do curso
        {{turma}}               — Designação da turma
        {{periodo}}             — Manhã / Tarde / Noite

      Resultado:
        {{nota_final_extenso}}  — Ex: "Dezasseis valores"
        {{nota_final_num}}      — Ex: "16"
        {{situacao_final}}      — Ex: "Aprovado"
        {{media_geral}}         — Média geral das disciplinas

      Escola:
        {{nome}}         — Nome da escola
        {{escola_provincia}}    — Província
        {{escola_municipio}}    — Município
        {{escola_nif}}          — NIF
        {{escola_director}}     — Nome do director

      Data/Assinatura:
        {{data_emissao}}        — Data de emissão do documento
        {{local_emissao}}       — Local de emissão
        {{numero_documento}}    — Número sequencial do documento
        {{registado_por}}       — Nome de quem registou
    """

    class TipoDocumento(models.TextChoices):
        CERTIFICADO = "certificado", _("Certificado de Habilitações")
        DECLARACAO_MATRICULA = "declaracao_matricula", _("Declaração de Matrícula")
        DECLARACAO_FREQUENCIA = "declaracao_frequencia", _("Declaração de Frequência")
        DECLARACAO_NOTAS = "declaracao_notas", _("Declaração de Notas")
        DECLARACAO_CONCLUSAO = "declaracao_conclusao", _("Declaração de Conclusão de Curso")
        HISTORICO = "historico", _("Histórico Escolar")

    class Orientacao(models.TextChoices):
        RETRATO = "retrato", _("Retrato (Portrait)")
        PAISAGEM = "paisagem", _("Paisagem (Landscape)")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    tipo = models.CharField(
        max_length=40,
        choices=TipoDocumento.choices,
        verbose_name=_("Tipo de Documento"),
    )
    nome = models.CharField(
        max_length=200,
        verbose_name=_("Nome do Template"),
        help_text=_("Nome interno para identificar este template."),
    )
    e_padrao = models.BooleanField(
        default=False,
        verbose_name=_("É Padrão"),
        help_text=_("Se marcado, é o template usado por omissão para este tipo."),
    )
    activo = models.BooleanField(default=True, verbose_name=_("Activo"))

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    cabecalho_titulo = models.CharField(
        max_length=300,
        verbose_name=_("Título do Documento"),
        default="CERTIFICADO DE HABILITAÇÕES",
        help_text=_("Texto principal em destaque no topo. Suporta variáveis."),
    )
    cabecalho_subtitulo = models.CharField(
        max_length=300, blank=True,
        verbose_name=_("Subtítulo"),
        help_text=_("Ex: 'REPÚBLICA DE ANGOLA - MINISTÉRIO DA EDUCAÇÃO'"),
    )
    mostrar_brasao = models.BooleanField(
        default=True,
        verbose_name=_("Mostrar Brasão/Logótipo"),
    )
    mostrar_cabecalho_escola = models.BooleanField(
        default=True,
        verbose_name=_("Mostrar Cabeçalho da Escola"),
    )

    # ── Corpo principal ────────────────────────────────────────────────────────
    texto_abertura = models.TextField(
        verbose_name=_("Texto de Abertura"),
        default=(
            "O Director(a) da {{escola_nome}}, no uso das suas competências "
            "e nos termos da legislação em vigor, certifica que:"
        ),
        help_text=_("Parágrafo introdutório. Suporta variáveis {{...}}."),
    )
    texto_identificacao = models.TextField(
        verbose_name=_("Bloco de Identificação"),
        default=(
            "{{aluno_nome}}, filho(a) de {{aluno_nome_pai}} e de {{aluno_nome_mae}}, "
            "nascido(a) em {{aluno_data_nasc}}, natural de {{aluno_naturalidade}}, "
            "portador(a) do Bilhete de Identidade n.º {{aluno_bi}},"
        ),
        help_text=_("Identificação do aluno. Suporta variáveis {{...}}."),
    )
    texto_corpo = models.TextField(
        verbose_name=_("Corpo do Documento"),
        default=(
            "concluiu com aproveitamento o {{classe}} do Ensino Secundário, "
            "Curso de {{curso}}, no ano lectivo {{ano_lectivo}}, "
            "tendo obtido a classificação final de {{nota_final_num}} ({{nota_final_extenso}}) valores, "
            "situação: {{situacao_final}}."
        ),
        help_text=_("Texto central do documento. Suporta variáveis {{...}}."),
    )
    texto_rodape = models.TextField(
        blank=True,
        verbose_name=_("Texto de Rodapé"),
        default=(
            "O presente {{tipo_documento}} é passado a pedido do(a) interessado(a) "
            "e para os fins que o(a) mesmo(a) entender convenientes."
        ),
        help_text=_("Parágrafo final antes das assinaturas. Suporta variáveis {{...}}."),
    )

    # ── Tabela de notas ────────────────────────────────────────────────────────
    incluir_tabela_notas = models.BooleanField(
        default=True,
        verbose_name=_("Incluir Tabela de Notas"),
    )
    texto_antes_tabela = models.CharField(
        max_length=300, blank=True,
        verbose_name=_("Texto antes da Tabela"),
        default="Classificações obtidas:",
    )

    # ── Assinatura / Local ─────────────────────────────────────────────────────
    local_emissao = models.CharField(
        max_length=100,
        verbose_name=_("Local de Emissão"),
        help_text=_("Ex: 'Luanda'. Pode usar {{escola_municipio}}."),
        default="{{escola_municipio}}",
    )
    texto_data_emissao = models.CharField(
        max_length=200,
        verbose_name=_("Formato da Data"),
        default="{{local_emissao}}, {{data_emissao}}",
        help_text=_("Formato da linha de data e local."),
    )

    # ── Layout / Impressão ─────────────────────────────────────────────────────
    orientacao = models.CharField(
        max_length=10,
        choices=Orientacao.choices,
        default=Orientacao.RETRATO,
        verbose_name=_("Orientação"),
    )
    margem_topo = models.IntegerField(default=2, verbose_name=_("Margem Topo (cm)"))
    margem_lateral = models.IntegerField(default=2, verbose_name=_("Margem Lateral (cm)"))
    tamanho_fonte_corpo = models.IntegerField(
        default=12,
        verbose_name=_("Tamanho da Fonte (corpo)"),
        help_text=_("Em pontos (pt). Recomendado: 11-13."),
    )
    usar_borda = models.BooleanField(default=True, verbose_name=_("Usar Borda Decorativa"))

    # ── Numeração ──────────────────────────────────────────────────────────────
    prefixo_numeracao = models.CharField(
        max_length=20, blank=True,
        verbose_name=_("Prefixo de Numeração"),
        help_text=_("Ex: 'CERT', 'DECL'. O número será: CERT-2024-0001."),
    )
    contador_atual = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Contador Actual"),
    )

    # ── Metadados ──────────────────────────────────────────────────────────────
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_actualizacao = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        "db.Utilizador",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="templates_criados",
        verbose_name=_("Criado por"),
    )

    class Meta:
        db_table = "template_documento"
        verbose_name = _("Template de Documento")
        verbose_name_plural = _("Templates de Documentos")
        ordering = ["tipo", "nome"]
        indexes = [
            models.Index(fields=["tipo", "activo"], name="idx_template_escola_tipo"),
            models.Index(fields=["e_padrao"], name="idx_template_padrao"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.nome}"

    def proximo_numero(self) -> str:
        """Gera o próximo número de documento e incrementa o contador."""
        self.contador_atual += 1
        self.save(update_fields=["contador_atual"])
        ano = timezone.now().year
        prefixo = self.prefixo_numeracao or self.get_tipo_display()[:4].upper()
        return f"{prefixo}-{ano}-{self.contador_atual:04d}"


class AssinaturaDocumento(models.Model):
    """
    Configuração das assinaturas que aparecem nos documentos.
    Cada escola pode ter múltiplas assinaturas (ex: Director, Secretário).
    """

    class Cargo(models.TextChoices):
        DIRECTOR = "director", _("Director(a)")
        SUBDIRECTOR = "subdirector", _("Subdirector(a) Pedagógico(a)")
        SECRETARIO = "secretario", _("Chefe de Secretaria")
        OUTRO = "outro", _("Outro")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    nome_completo = models.CharField(max_length=200, verbose_name=_("Nome Completo"))
    cargo = models.CharField(
        max_length=20,
        choices=Cargo.choices,
        verbose_name=_("Cargo"),
    )
    cargo_customizado = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Cargo Customizado"),
        help_text=_("Preenchido quando cargo = Outro."),
    )
    ordem = models.PositiveIntegerField(default=1, verbose_name=_("Ordem de Exibição"))
    activo = models.BooleanField(default=True, verbose_name=_("Activo"))
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assinatura_documento"
        verbose_name = _("Assinatura de Documento")
        verbose_name_plural = _("Assinaturas de Documentos")
        ordering = ["ordem"]
        indexes = [
            models.Index(fields=["activo"], name="idx_assinatura_activo"),
        ]

    def __str__(self):
        return f"{self.nome_completo} — {self.get_cargo_display()}"

    @property
    def cargo_display(self) -> str:
        return self.cargo_customizado if self.cargo == self.Cargo.OUTRO else self.get_cargo_display()


class DocumentoGerado(models.Model):
    """
    Registo de cada documento emitido (certificado ou declaração).
    Mantém histórico para fins legais e auditoria.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EMITIDO = "emitido", _("Emitido")
        ANULADO = "anulado", _("Anulado")
        SEGUNDA_VIA = "segunda_via", _("Segunda Via")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    template = models.ForeignKey(
        TemplateDocumento,
        on_delete=models.PROTECT,
        related_name="documentos_gerados",
        verbose_name=_("Template Utilizado"),
    )
    aluno = models.ForeignKey(
        "db.Aluno",
        on_delete=models.PROTECT,
        related_name="documentos_gerados",
        verbose_name=_("Aluno"),
    )
    matricula = models.ForeignKey(
        "db.Matricula",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="documentos_gerados",
        verbose_name=_("Matrícula"),
    )
    ano_lectivo = models.ForeignKey(
        "db.AnoLectivo",
        on_delete=models.PROTECT,
        related_name="documentos_gerados",
        verbose_name=_("Ano Lectivo"),
    )

    # ── Identificação ──────────────────────────────────────────────────────────
    numero_documento = models.CharField(
        max_length=50, unique=True,
        db_index=True,
        verbose_name=_("Número do Documento"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RASCUNHO,
        db_index=True,
        verbose_name=_("Estado"),
    )

    # ── Snapshot do conteúdo ───────────────────────────────────────────────────
    # Guardamos o HTML/texto final gerado para imutabilidade legal
    conteudo_html = models.TextField(
        blank=True,
        verbose_name=_("Conteúdo HTML"),
        help_text=_("Snapshot do documento gerado (para reimpressão idêntica)."),
    )
    dados_snapshot = models.JSONField(
        default=dict,
        verbose_name=_("Dados no momento da Emissão"),
        help_text=_("Snapshot de todos os dados usados na geração."),
    )

    # ── Controlo ───────────────────────────────────────────────────────────────
    motivo_anulacao = models.TextField(
        blank=True,
        verbose_name=_("Motivo de Anulação"),
    )
    documento_original = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="segundas_vias",
        verbose_name=_("Documento Original"),
        help_text=_("Preenchido quando se trata de uma 2ª via."),
    )

    # ── Datas e responsável ────────────────────────────────────────────────────
    data_emissao = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Data de Emissão"),
    )
    emitido_por = models.ForeignKey(
        "db.Utilizador",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="documentos_emitidos",
        verbose_name=_("Emitido por"),
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_actualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documento_gerado"
        verbose_name = _("Documento Gerado")
        verbose_name_plural = _("Documentos Gerados")
        ordering = ["-data_emissao"]
        indexes = [
            models.Index(fields=["status"], name="idx_docger_status"),
            models.Index(fields=["aluno", "template"], name="idx_docger_aluno_template"),
            models.Index(fields=["numero_documento"], name="idx_docger_numero"),
            models.Index(fields=["data_emissao"], name="idx_docger_data"),
        ]

    def __str__(self):
        return f"{self.numero_documento} — {self.aluno} ({self.get_status_display()})"

    def emitir(self, utilizador):
        """Marca o documento como emitido."""
        if self.status != self.Status.RASCUNHO:
            raise ValidationError(_("Apenas rascunhos podem ser emitidos."))
        self.status = self.Status.EMITIDO
        self.data_emissao = timezone.now()
        self.emitido_por = utilizador
        self.save(update_fields=["status", "data_emissao", "emitido_por"])

    def anular(self, motivo: str):
        """Anula o documento."""
        if self.status == self.Status.ANULADO:
            raise ValidationError(_("O documento já está anulado."))
        self.status = self.Status.ANULADO
        self.motivo_anulacao = motivo
        self.save(update_fields=["status", "motivo_anulacao"])