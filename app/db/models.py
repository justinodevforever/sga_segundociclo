from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
 
 
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.auth.models import AbstractUser
import uuid, math

NOTA_VALIDATORS = [MinValueValidator(0), MaxValueValidator(20)]

def campo_nota(**kw):
    return models.DecimalField(max_digits=4, decimal_places=2, null=True,
                               blank=True, validators=NOTA_VALIDATORS, **kw)
 
 
class TimestampMixin(models.Model):
    
    data_criacao = models.DateTimeField(auto_now_add=True, null=True, verbose_name=_("Data de Criação"))
    data_actualizacao = models.DateTimeField(auto_now=True,null=True, verbose_name=_("Data de Actualização"))

    class Meta:
        abstract = True

class SoftDeleteMixin(models.Model):

    activo = models.BooleanField(default=True, verbose_name=_("Activo"), db_index=True)
    data_desactivacao = models.DateTimeField(null=True, blank=True, verbose_name=_("Data de Desactivação"))

    class Meta:
        abstract = True

    def desactivar(self):
        self.activo = False
        self.data_desactivacao = timezone.now()
        self.save(update_fields=["activo", "data_desactivacao"])

    def activar(self):
        self.activo = True
        self.data_desactivacao = None
        self.save(update_fields=["activo", "data_desactivacao"])


class Utilizador(AbstractUser):

    class Genero(models.TextChoices):
        MASCULINO = "M", _("Masculino")
        FEMININO = "F", _("Feminino")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    nome_completo = models.CharField(
        max_length=200, blank=True, null=True,
        db_index=True,
        verbose_name=_("Nome Completo"),
    )
    verificado_email = models.BooleanField(
        default=False,
        verbose_name=_("E-mail Verificado"),
    )
    verificado_telefone = models.BooleanField(
        default=False,
        verbose_name=_("Telefone Verificado"),
    )
    ultimo_logout = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Última Saída"),
    )
    penultima_entrada = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("penúltima Saída"),
    )
    criado_por = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="utilizadores_criados",
        verbose_name=_("Criado por"),
    )
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Criação"))
    data_actualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Actualização"))

    REQUIRED_FIELDS = ["email", "nome_completo"]

    class Meta:
        db_table = "utilizador"
        verbose_name = _("Utilizador")
        verbose_name_plural = _("Utilizadores")
        ordering = ["nome_completo"]
        indexes = [
            models.Index(fields=[ "is_active"], name="idx_util_activo"),
            models.Index(fields=["email"], name="idx_util_email"),
            models.Index(fields=["username"], name="idx_util_username"),
            models.Index(fields=["nome_completo"], name="idx_util_nome"),
            models.Index(fields=["ultimo_logout"], name="idx_util_ultimo_logout"),
        ]

    def __str__(self) -> str:
        return self.nome_completo or self.username

    @property
    def esta_verificado(self) -> bool:
     
        return self.verificado_email and self.verificado_telefone

    def registar_acesso(self) -> None:
    
        self.ultimo_acesso = timezone.now()
        self.save(update_fields=["ultimo_acesso"])

class Role(TimestampMixin):

    class NomeRole(models.TextChoices):
        ADMIN = "admin", _("Administrador")
        ESTUDANTE = "estudante", _("Estudante")
        DIRECTOR = "director", _("Director")
        PROFESSOR = "professor", _("Professor")
        SECRETARIO = "secretario", _("Secretário")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(
        max_length=50,
        unique=True,
        choices=NomeRole.choices,
        verbose_name=_("Nome"),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Activo"))

    class Meta:
        db_table = "roles"
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["nome", "is_active"], name="idx_role_nome_activo"),
        ]
     

    def __str__(self) -> str:
        return self.get_nome_display()

class UsuarioRole(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilizador = models.ForeignKey(
        Utilizador, on_delete=models.CASCADE,
        related_name="usuario_roles", verbose_name=_("Utilizador"),
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE,
        related_name="usuario_roles", verbose_name=_("Role"),
    )
    atribuido_em = models.DateTimeField(auto_now_add=True)
    atribuido_por = models.ForeignKey(
        Utilizador, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="roles_atribuidos", verbose_name=_("Atribuído por"),
    )

    class Meta:
        db_table = "role_usuario"
        unique_together = [["utilizador", "role"]]
        verbose_name = _("Role do Utilizador")
        verbose_name_plural = _("Roles dos Utilizadores")
        indexes = [
            models.Index(fields=["utilizador"], name="idx_usuariorole_utilizador"),
            models.Index(fields=["role"], name="idx_usuariorole_role"),
        ]

    def __str__(self) -> str:
        return f"{self.utilizador} — {self.role}"



class Periodo(models.Model):

    class Turno(models.TextChoices):
        MANHA = "manha", _("Manhã")
        TARDE = "tarde", _("Tarde")
        NOITE = "noite", _("Noite")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designacao = models.CharField(
        max_length=60,
        choices=Turno.choices,
        unique=True,
        verbose_name=_("Designação"),
    )

    class Meta:
        verbose_name = _("Período")
        verbose_name_plural = _("Períodos")

    def __str__(self) -> str:
        return self.get_designacao_display()



class AnoLectivo( TimestampMixin):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    semanas_lectivas = models.PositiveSmallIntegerField(default=33)
    designacao = models.CharField(max_length=50, verbose_name=_("Designação"))
    data_inicio = models.DateField(verbose_name=_("Data de Início"))
    data_fim = models.DateField(verbose_name=_("Data de Fim"))
    e_atual = models.BooleanField(default=False, db_index=True, verbose_name=_("É Actual"))

    class Meta:
        db_table = "ano_lectivo"
        verbose_name = _("Ano Lectivo")
        verbose_name_plural = _("Anos Lectivos")
        unique_together = [[ "designacao"]]
        indexes = [
            models.Index(fields=[ "e_atual"], name="idx_anolectivo_atual"),
            models.Index(fields=["data_inicio", "data_fim"], name="idx_anolectivo_periodo"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(data_fim__gt=models.F("data_inicio")),
                name="chk_anolectivo_datas_validas",
            )
        ]

    def __str__(self):
        return self.designacao

    def clean(self):
        if self.data_inicio and self.data_fim and self.data_fim <= self.data_inicio:
            raise ValidationError(_("A data de fim deve ser posterior à data de início."))

class Trimestre(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.CASCADE, related_name="trimestres")
    designacao = models.PositiveSmallIntegerField(choices=[(1, "1.º"), (2, "2.º"), (3, "3.º")])
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    lancamento_aberto = models.BooleanField(default=True, help_text="Permite lançar/alterar notas")

    activo = models.BooleanField(default=False)

    class Meta:
        unique_together = ("ano_lectivo", "designacao")
        verbose_name = _("Trimestre")
        verbose_name_plural = _("Trimestres")
        ordering = ["ano_lectivo", "designacao"]

    def __str__(self) -> str:
        
        return f"{self.designacao}.º Trimestre {self.ano_lectivo}"
    
class TenantConfiguracao(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
   
    ano_lectivo_activo = models.ForeignKey(
        AnoLectivo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Ano Lectivo Activo"),
    )

    periodo_exame = models.BooleanField(default=False)
    periodo_prova_1_trimestre = models.BooleanField(default=False)
    periodo_prova_2_trimestre = models.BooleanField(default=False)
    periodo_prova_3_trimestre = models.BooleanField(default=False)
    periodo_recurso = models.BooleanField(default=False)

    periodo_inscricao = models.BooleanField(default=False)
    periodo_confirmacao = models.BooleanField(default=False)
    periodo_matricula = models.BooleanField(default=False)

    dia_vencimento_propina = models.IntegerField(
        default=10,
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
        verbose_name=_("Dia Vencimento Propina"),
    )

    email_smtp_host = models.CharField(max_length=200, blank=True, verbose_name=_("SMTP Host"))
    email_smtp_port = models.IntegerField(default=587, verbose_name=_("SMTP Port"))
    email_remetente = models.EmailField(max_length=100, blank=True, verbose_name=_("E-mail Remetente"))
    # SMS
    sms_provider = models.CharField(max_length=50, blank=True, verbose_name=_("Provedor SMS"))
    sms_api_key = models.CharField(max_length=200, blank=True, verbose_name=_("SMS API Key"))
    # Pagamentos
    multicaixa_entity = models.CharField(max_length=20, blank=True, verbose_name=_("Multicaixa Entidade"))
    multicaixa_api_key = models.CharField(max_length=200, blank=True, verbose_name=_("Multicaixa API Key"))

    class Meta:
        db_table = "tenant_configuracao"
        verbose_name = _("Configuração da Escola")

    def __str__(self):
        return f"Config — {self.escola}"

class PessoaMixin(models.Model):

    class Genero(models.TextChoices):
        MASCULINO = "M", _("Masculino")
        FEMININO = "F", _("Feminino")

    class NivelAcademico(models.TextChoices):
        TECNICO_MEDIO = "Tecnico_medio", _("Técnico Médio")
        BACHAREL = "Bacharel", _("Bacharel")
        LICENCIADO = "Licenciado", _("Licenciado")
        MESTRE = "Mestre", _("Mestre")
        DOUTOR = "Doutor", _("Doutor")

    nome_completo = models.CharField(max_length=200, verbose_name=_("Nome Completo"), db_index=True)
    bi = models.CharField(max_length=20, verbose_name=_("Bilhete de Identidade"))
    data_nascimento = models.DateField(null=True, blank=True, verbose_name=_("Data de Nascimento"))
    genero = models.CharField(max_length=1, choices=Genero.choices, blank=True, null=True, verbose_name=_("Género"))
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Telefone"))
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name=_("E-mail"))
    endereco = models.TextField(blank=True, null=True, verbose_name=_("Endereço"))

    class Meta:
        abstract = True

    @property
    def idade(self) -> int | None:
        if not self.data_nascimento:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.data_nascimento.year - (
            (today.month, today.day) < (self.data_nascimento.month, self.data_nascimento.day)
        )


class Diretor( PessoaMixin, TimestampMixin):

    class Status(models.TextChoices):
        ACTIVO = "Activo", _("Activo")
        INACTIVO = "Inactivo", _("Inactivo")
        LICENCA = "Licença", _("Licença")
        DEMITIDO = "Demitido", _("Demitido")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilizador = models.OneToOneField(
        Utilizador, on_delete=models.CASCADE,
        verbose_name=_("Utilizador"), related_name="director"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVO, db_index=True, verbose_name=_("Estado"))

    class Meta:
        db_table = "diretor"
        verbose_name = _("Director")
        verbose_name_plural = _("Directores")
        indexes = [
            models.Index(fields=[ "status"], name="idx_diretor_status"),
        ]

    def __str__(self):
        return self.nome_completo

class Funcionario( PessoaMixin, TimestampMixin):

    class TipoContrato(models.TextChoices):
        EFECTIVO = "Efectivo", _("Efectivo")
        CONTRATADO = "Contratado", _("Contratado")
        ESTAGIARIO = "Estagiário", _("Estagiário")

    class TipoFuncionario(models.TextChoices):
        ADMINISTRATIVO = "Administrativo", _("Administrativo")
        PROFESSOR = "Professor", _("Professor")

    class Status(models.TextChoices):
        ACTIVO = "Activo", _("Activo")
        INACTIVO = "Inactivo", _("Inactivo")
        LICENCA = "Licença", _("Licença")
        DEMITIDO = "Demitido", _("Demitido")


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilizador = models.OneToOneField(
        Utilizador, on_delete=models.SET_NULL,
        blank=True, null=True, verbose_name=_("Utilizador"), related_name="funcionario"
    )
    numero_agente = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Nº Agente"))
    especialidade = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Especialidade"))
    nivel_academico = models.CharField(max_length=20, choices=PessoaMixin.NivelAcademico.choices, verbose_name=_("Nível Académico"))
    instituicao_formacao = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Instituição de Formação"))
    anos_experiencia = models.IntegerField(default=0, blank=True, null=True, validators=[MinValueValidator(0)], verbose_name=_("Anos de Experiência"))
    tipo_contrato = models.CharField(max_length=20, choices=TipoContrato.choices, blank=True, null=True, verbose_name=_("Tipo de Contrato"))
    tipo_funcionario = models.CharField(max_length=20, choices=TipoFuncionario.choices, blank=True, null=True, verbose_name=_("Tipo de Funcionário"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVO, db_index=True, verbose_name=_("Estado"))
    carga_horaria_semanal = models.IntegerField(
        default=0, blank=True, null=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("Carga Horária Semanal"),
    )

    class Meta:
        db_table = "funcionario"
        verbose_name = _("Funcionário")
        verbose_name_plural = _("Funcionários")
        indexes = [
            models.Index(fields=[ "status"], name="idx_funcionario_status"),
            models.Index(fields=["nome_completo"], name="idx_funcionario_nome"),
        ]

    def __str__(self):
        return self.nome_completo


class Curso( TimestampMixin, SoftDeleteMixin):

    class Tipo(models.TextChoices):
        GERAL = "GERAL", "Ensino Geral"
        TECNICO = "TECNICO", "Ensino Técnico-Profissional"
        PEDAGOGICO = "PEDAGOGICO", "Formação de Professores"
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=200, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.GERAL)
    nome_abreviado = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Nome Abreviado"))
    duracao_anos = models.IntegerField(
        default=3, blank=True, null=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name=_("Duração (anos)"),
    )
    exige_pap = models.BooleanField(default=False, verbose_name="Exige Prova de Aptidão Profissional")
    exige_estagio = models.BooleanField(default=False)

    class Meta:
        db_table = "curso"
        verbose_name = _("Curso")
        verbose_name_plural = _("Cursos")
        unique_together = [[ "nome"]]
        indexes = [
            models.Index(fields=[ "activo"], name="idx_curso_activo"),
        ]

    def __str__(self):
        return self.nome


class Classe(models.Model):
    
    class TipoClasse(models.IntegerChoices):
    
        DECIMA = 10, "10.ª Classe"
        DECIMA_PRIMEIRA = 11, "11.ª Classe"
        DECIMA_SEGUNDA = 12, "12.ª Classe"
        DECIMA_TERCEIRA = 13, "13.ª Classe (cursos técnicos)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero = models.IntegerField(
        blank=True, null=True, verbose_name=_("Número"),
    )
    designacao = models.PositiveSmallIntegerField(choices=TipoClasse.choices)
    ordem = models.IntegerField(blank=True, null=True, verbose_name=_("Ordem"))

    class Meta:
        db_table = "classe"
        verbose_name = _("Classe")
        verbose_name_plural = _("Classes")
        ordering = ["ordem"]
        unique_together = [[ "designacao"]]
        indexes = [
            models.Index(fields=[ "numero"], name="idx_classe_numero"),
        ]

    def __str__(self):
        return f'{self.designacao}'


class Disciplina( TimestampMixin, SoftDeleteMixin):

    class Componente(models.TextChoices):
        SOCIOCULTURAL = "SC", "Sociocultural"
        CIENTIFICA = "CT", "Científica"
        TECNICA = "TE", "Técnica / Tecnológica"
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=200, verbose_name=_("Nome"))
    nome_abreviado = models.CharField(max_length=10, verbose_name=_("Abreviatura"))
    componente = models.CharField(max_length=2, choices=Componente.choices)
    
    class Meta:
        db_table = "disciplina"
        verbose_name = _("Disciplina")
        verbose_name_plural = _("Disciplinas")
        indexes = [
            models.Index(fields=["activo"], name="idx_disciplina_activo"),
            models.Index(fields=["nome"], name="idx_disciplina_nome"),
        ]

    def __str__(self):
        return self.nome

class PlanoCurricular(models.Model):
    
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="plano")
    classe = classe = models.ForeignKey(Classe, on_delete=models.CASCADE, verbose_name=_("Classe"), related_name='Plano')
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    carga_horaria_semanal = models.PositiveSmallIntegerField(help_text="Tempos lectivos por semana")
    tem_exame_nacional = models.BooleanField(default=False)
 
    class Meta:
        unique_together = ("curso", "classe", "disciplina")
 
    def __str__(self):
        return f"{self.curso} - {self.classe}.ª - {self.disciplina}"


class Turma( TimestampMixin, SoftDeleteMixin):

    class Turno(models.TextChoices):
        MANHA = "M", "Manhã"
        TARDE = "T", "Tarde"
        NOITE = "N", "Noite"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designacao = models.CharField(max_length=60, verbose_name=_("Designação"))
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.CASCADE, verbose_name=_("Ano Lectivo"), related_name='turmas')
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, verbose_name=_("Curso"), related_name='turmas')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, verbose_name=_("Classe"), related_name='turmas')
    periodo = models.CharField(max_length=1, choices=Turno.choices)
    sala = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Sala"))
    capacidade_maxima = models.IntegerField(
        default=40, blank=True, null=True,
        validators=[MinValueValidator(1)],
        verbose_name=_("Capacidade Máxima"),
    )
    vagas_disponiveis = models.IntegerField(
        default=40, blank=True, null=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("Vagas Disponíveis"),
    )
    classificacao_positiva = models.CharField(max_length=40, verbose_name=_("Classificação positiva"))
    classificacao_negativa = models.CharField(max_length=40, verbose_name=_("Classificação negativa"))
    valor_minimo = models.PositiveIntegerField(default=0, verbose_name=_("Valor mínimo"))
    valor_maximo = models.PositiveIntegerField(default=20, verbose_name=_("Valor máximo"))

    preco_matricula = models.DecimalField(max_digits=12, blank=True, null=True, decimal_places=2, verbose_name=_("Preço matrícula"))
    preco_propina = models.DecimalField(max_digits=12, blank=True, null=True, decimal_places=2, verbose_name=_("Preço propina"))
    preco_confirmacao = models.DecimalField(max_digits=12, blank=True, null=True, decimal_places=2, verbose_name=_("Preço confirmação"))

    class Meta:
        db_table = "turma"
        verbose_name = _("Turma")
        verbose_name_plural = _("Turmas")
        unique_together = ("ano_lectivo", "curso", "classe", "designacao", "periodo")
        indexes = [
            models.Index(fields=["ano_lectivo"], name="idx_turma_ano"),
            models.Index(fields=["ano_lectivo", "activo"], name="idx_turma_activa"),
            models.Index(fields=["curso", "classe"], name="idx_turma_curso_classe"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(vagas_disponiveis__lte=models.F("capacidade_maxima")),
                name="chk_turma_vagas_nao_excedem_capacidade",
            )
        ]

    def __str__(self):
        return f"T: {self.designacao} {self.classe}.ª  - {self.curso} ({self.ano_lectivo})"
 

class HorarioAula(models.Model):

    class DiaSemana(models.TextChoices):
        SEGUNDA = "Segunda", _("Segunda-feira")
        TERCA = "Terça", _("Terça-feira")
        QUARTA = "Quarta", _("Quarta-feira")
        QUINTA = "Quinta", _("Quinta-feira")
        SEXTA = "Sexta", _("Sexta-feira")
        SABADO = "Sábado", _("Sábado")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    turma = models.ForeignKey(Turma, on_delete=models.CASCADE, related_name="horarios", verbose_name=_("Turma"))
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE, verbose_name=_("Disciplina"))
    professor = models.ForeignKey(Funcionario, on_delete=models.CASCADE, verbose_name=_("Professor"))
    dia_semana = models.CharField(max_length=10, choices=DiaSemana.choices, verbose_name=_("Dia da Semana"))
    hora_inicio = models.TimeField(verbose_name=_("Hora de Início"))
    hora_fim = models.TimeField(verbose_name=_("Hora de Fim"))
    sala = models.CharField(max_length=50, blank=True, verbose_name=_("Sala"))

    class Meta:
        db_table = "horario_aula"
        verbose_name = _("Horário de Aula")
        verbose_name_plural = _("Horários de Aulas")
        indexes = [
            models.Index(fields=["turma", "dia_semana"], name="idx_horario_turma_dia"),
            models.Index(fields=["professor", "dia_semana"], name="idx_horario_professor_dia"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_fim__gt=models.F("hora_inicio")),
                name="chk_horario_horas_validas",
            )
        ]

    def __str__(self):
        return f"{self.dia_semana} {self.hora_inicio}–{self.hora_fim} | {self.turma}"

    def clean(self):
        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            raise ValidationError(_("A hora de fim deve ser posterior à hora de início."))

class Aluno( PessoaMixin, TimestampMixin):

    class Status(models.TextChoices):
        MATRICULADO = "Matriculado", _("Matriculado")
        TRANSFERIDO = "Transferido", _("Transferido")
        DESISTENTE = "Desistente", _("Desistente")
        CONCLUIDO = "Concluído", _("Concluído")
        SUSPENSO = "Suspenso", _("Suspenso")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilizador = models.OneToOneField(
        'Utilizador', on_delete=models.SET_NULL,
        blank=True, null=True, verbose_name=_("Utilizador"), related_name="aluno"
    )
    numero_processo = models.CharField(
        max_length=50, unique=True, blank=True, null=True, verbose_name=_("Nº Processo"),
    )
    numero_estudante = models.CharField(
        max_length=50, unique=True, blank=True, null=True, verbose_name=_("Nº Matrícula"),
    )
    nome_completo = models.CharField(max_length=200, db_index=True, verbose_name=_("Nome Completo"))
    nome_pai = models.CharField(max_length=200, verbose_name=_("Nome do Pai"))
    nome_mae = models.CharField(max_length=200, verbose_name=_("Nome da Mãe"))
    data_emissao_bi = models.DateField(null=True, blank=True, verbose_name=_("Data de Emissão do BI"))
    data_expiracao_bi = models.DateField(null=True, blank=True, verbose_name=_("Data de Expiração do BI"))
    emitido_em = models.CharField(max_length=200, verbose_name=_("Emitido em"))
    necessidades_especiais = models.TextField(blank=True, verbose_name=_("Necessidades Especiais"))
    foto = models.ImageField(upload_to="alunos/fotos/", blank=True, null=True, verbose_name=_("Foto"))
    telefone = models.CharField(max_length=20, blank=True, verbose_name=_("Telefone"))
    naturalidade = models.CharField(max_length=100, verbose_name=_("Naturalidade"))
    provincia = models.CharField(max_length=50, verbose_name=_("Província"))
    municipio = models.CharField(max_length=50, verbose_name=_("Município"))
    bairro = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Bairro"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MATRICULADO, db_index=True, verbose_name=_("Estado"))
    criado_por = models.ForeignKey(
        Utilizador, on_delete=models.SET_NULL, null=True,
        related_name="alunos_criado", verbose_name=_("Criado por"),
    )

    class Meta:
        db_table = "aluno"
        verbose_name = _("Aluno")
        verbose_name_plural = _("Alunos")
        indexes = [
            models.Index(fields=["status"], name="idx_aluno_status"),
            models.Index(fields=["nome_completo"], name="idx_aluno_nome"),
            models.Index(fields=["numero_processo"], name="idx_aluno_processo"),
            models.Index(fields=["bi"], name="idx_aluno_bi"),
            models.Index(fields=["numero_estudante"], name="idx_numero_estudante_bi"),
        ]

    def __str__(self):
        return self.nome_completo
    
 
class AtribuicaoDocente(models.Model):
    professor = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='atribuicao')
    turma = models.ForeignKey(Turma, on_delete=models.CASCADE)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT, related_name='atribuicao')
 
    class Meta:
        unique_together = ("turma", "disciplina")
 
    def __str__(self):
        return f"{self.professor} - {self.disciplina} - {self.turma}"


class Candidato( PessoaMixin, TimestampMixin):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    utilizador = models.OneToOneField(
        Utilizador, on_delete=models.SET_NULL,
        blank=True, null=True, verbose_name=_("Utilizador"), related_name="candidato"
    )
    nome_completo = models.CharField(max_length=200, db_index=True, verbose_name=_("Nome Completo"))
    nome_pai = models.CharField(max_length=200, verbose_name=_("Nome do Pai"))
    nome_mae = models.CharField(max_length=200, verbose_name=_("Nome da Mãe"))
    emitido_em = models.CharField(max_length=200, verbose_name=_("Emitido em"))
    genero = models.CharField(max_length=1, choices=PessoaMixin.Genero.choices, verbose_name=_("Género"))
    data_expiracao_bi = models.DateField(null=True, blank=True, verbose_name=_("Data de Expiração do BI"))
    data_emissao_bi = models.CharField(max_length=200, verbose_name=_("Data da emissão"))
    necessidades_especiais = models.TextField(blank=True, verbose_name=_("Necessidades Especiais"))
    telefone = models.CharField(max_length=20, blank=True, verbose_name=_("Telefone"))
    naturalidade = models.CharField(max_length=100, verbose_name=_("Naturalidade"))
    provincia = models.CharField(max_length=50, verbose_name=_("Província"))
    municipio = models.CharField(max_length=50, verbose_name=_("Município"))
    bairro = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Bairro"))
    criado_por = models.ForeignKey(
        Utilizador, on_delete=models.SET_NULL, null=True,
        related_name="alunos_criados", verbose_name=_("Criado por"),
    )

    class Meta:
        db_table = "candidato"
        verbose_name = _("Candidato")
        verbose_name_plural = _("Candidatos")
        indexes = [
            models.Index(fields=["nome_completo"], name="idx_candidato_nome"),
            models.Index(fields=["bi"], name="idx_candidato_bi"),
        ]

    def __str__(self):
        return self.nome_completo

class Inscricao( TimestampMixin):

    class Status(models.TextChoices):
        ATIVA = "ativa", _("Activa")
        APROVADA = "aprovada", _("Aprovada")
        REPROVADA = "reprovada", _("Reprovada")


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    candidato = models.ForeignKey(Candidato, on_delete=models.PROTECT, related_name="inscricoes", verbose_name=_("candidato"))
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="inscricoes", verbose_name=_("Período"))
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.PROTECT, verbose_name=_("Ano Lectivo"), related_name="inscricoes")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, verbose_name=_("Curso"), related_name="inscricoes")
    inscrito_por = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, verbose_name=_("Inscrito por"))
    data_inscricao = models.DateField(auto_now_add=True, verbose_name=_("Data de Inscrição"))
    status = models.CharField(max_length=20, choices=Status.choices, default='ativa')

    class Meta:
        db_table = "inscricao"
        verbose_name = _("Inscrição")
        verbose_name_plural = _("Inscrições")
        indexes = [
            models.Index(fields=["ano_lectivo"], name="idx_inscricao_ano"),
        ]

    def __str__(self):
        return f"{self.candidato} — {self.ano_lectivo}"


class Matricula( TimestampMixin):

    class TipoMatricula(models.TextChoices):
        NOVA = "NOVA", "Nova matrícula"
        CONFIRMACAO = "CONF", "Confirmação"
        REPETENTE = "REP", "Repetente"
        TRANSFERENCIA = "TRANS", "Transferência"

    class Status(models.TextChoices):
        ACTIVA = "Activa", _("Activa")
        CANCELADA = "Cancelada", _("Cancelada")
        TRANSFERIDA = "Transferida", _("Transferida")
        CONCLUIDA = "Concluída", _("Concluída")
        TRANCAMENTO = "Trancamento", _("Trancamento")
        DESISTENTE = "Desistente", _("Desistente")
        
    class Situacao(models.TextChoices):
        EM_CURSO = "EM_CURSO", "Em curso"
        APROVADO = "APROVADO", "Aprovado"
        REPROVADO = "REPROVADO", "Reprovado"
        REPROVADO_FALTAS = "REP_FALTAS", "Reprovado por faltas"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name="matriculas", verbose_name=_("Aluno"))
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.CASCADE, verbose_name=_("Ano Lectivo"), related_name="matriculas")
    turma = models.ForeignKey(Turma, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_("Turma"), related_name='matriculas')
    tipo_matricula = models.CharField(max_length=20, default='Nova', choices=TipoMatricula.choices, verbose_name=_("Tipo"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVA, db_index=True, verbose_name=_("Estado"))
    situacao_final = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.EM_CURSO)
    motivo_cancelamento = models.TextField(blank=True, null=True, verbose_name=_("Motivo de Cancelamento"))
    observacoes = models.TextField(blank=True, verbose_name=_("Observações"))
    matriculado_por = models.ForeignKey(
        Utilizador, on_delete=models.SET_NULL, null=True,
        verbose_name=_("Matriculado por"), related_name="matriculas"
    )
    data_matricula = models.DateField(auto_now_add=True, verbose_name=_("Data de Matrícula"))

    class Meta:
        db_table = "matricula"
        verbose_name = _("Matrícula")
        verbose_name_plural = _("Matrículas")
        unique_together = [["aluno", "ano_lectivo"]]
        indexes = [
            models.Index(fields=[ "ano_lectivo", "status"], name="matricula_ano_status"),
            models.Index(fields=["aluno", "ano_lectivo"], name="idx_matricula_aluno_ano"),
            models.Index(fields=["turma", "ano_lectivo"], name="idx_matricula_turma_ano"),
        ]

    def __str__(self):
         return f"{self.aluno.nome_completo} - {self.turma}"


class DocumentoAluno( TimestampMixin):

    class TipoDocumento(models.TextChoices):
        BI = "BI", _("Bilhete de Identidade")
        CERTIFICADO = "Certificado", _("Certificado")
        ATESTADO = "Atestado", _("Atestado Médico")
        FOTO = "Foto", _("Fotografia")
        BOLETIM = "Boletim", _("Boletim de Notas")
        OUTROS = "Outros", _("Outros")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name="documentos", verbose_name=_("Aluno"))
    tipo_documento = models.CharField(max_length=20, choices=TipoDocumento.choices, verbose_name=_("Tipo"))
    titulo = models.CharField(max_length=200, verbose_name=_("Título"))
    arquivo = models.FileField(upload_to="alunos/documentos/", verbose_name=_("Arquivo"))
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Upload"))
    uploaded_por = models.ForeignKey(
        Utilizador, on_delete=models.SET_NULL, null=True,
        verbose_name=_("Carregado por"),
    )

    class Meta:
        db_table = "documento_aluno"
        verbose_name = _("Documento do Aluno")
        verbose_name_plural = _("Documentos dos Alunos")
        indexes = [
            models.Index(fields=["aluno", "tipo_documento"], name="idx_docaluno_aluno_tipo"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.aluno})"

class RegraAvaliacao(models.Model):
    """
    Define as regras por ano lectivo e, opcionalmente, por classe.
    Prioridade: (ano + classe) > (ano, classe vazia).
    """
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.CASCADE)
    classe = classe = models.ForeignKey(Classe, on_delete=models.CASCADE, verbose_name=_("Classe"), related_name='regras')
    nota_minima_positiva = models.DecimalField(max_digits=4, decimal_places=2, default=10)
    nota_maxima = models.DecimalField(max_digits=4, decimal_places=2, default=20)
 
    # MT = (MAC*p_mac + PP*p_pp + PT*p_pt) / (p_mac + p_pp + p_pt)
    peso_mac = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    peso_pp = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    peso_pt = models.DecimalField(max_digits=4, decimal_places=2, default=1)
 
    arredondar_unidades = models.BooleanField(default=True,
                                              help_text="Arredonda médias às unidades (0,5 sobe)")
 
    # Classes com exame nacional: NF = MFD*(1-peso) + Exame*peso
    peso_exame_na_nota_final = models.DecimalField(max_digits=3, decimal_places=2, default=0.50)
    nota_minima_exame = models.DecimalField(max_digits=4, decimal_places=2, default=10)
 
    # Transição de classe
    max_negativas_transicao = models.PositiveSmallIntegerField(
        default=2, help_text="Nº máximo de disciplinas negativas para transitar (classes sem exame)")
    classe_exame_exige_todas_positivas = models.BooleanField(default=True)
 
    # Assiduidade
    limite_faltas_injustificadas_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=30,
        help_text="% de faltas injustificadas acima da qual há reprovação por faltas")
 
    class Meta:
        unique_together = ("ano_lectivo", "classe")
        verbose_name = "Regra de avaliação"
        verbose_name_plural = "Regras de avaliação"
 
    def __str__(self):
        return f"Regras {self.ano_lectivo} / {self.classe or 'todas'}"
  

class AvaliacaoContinua(models.Model):
   
    class Tipo(models.TextChoices):
        TESTE = "TESTE", "Teste"
        TRABALHO = "TRAB", "Trabalho"
        PARTICIPACAO = "PART", "Participação"
        PRATICA = "PRAT", "Actividade prática"
        OUTRO = "OUTRO", "Outro"
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True)
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="avaliacoes_continuas")
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    trimestre = models.ForeignKey(Trimestre, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=5, choices=Tipo.choices, default=Tipo.TESTE)
    descricao = models.CharField(max_length=150, blank=True)
    data = models.DateField()
    valor = models.DecimalField(max_digits=4, decimal_places=2, validators=NOTA_VALIDATORS)
    lancado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"{self.matricula.aluno} {self.disciplina} {self.valor}"

 
 
class ResultadoTrimestral(models.Model):
    """MAC (calculado), PP, PT (lançadas) e MT (calculada)."""
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True)
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="resultados_trimestrais")
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    trimestre = models.ForeignKey(Trimestre, on_delete=models.PROTECT)
    mac = campo_nota(verbose_name="MAC", editable=False)
    pp = campo_nota(verbose_name="Prova do Professor")
    pt = campo_nota(verbose_name="Prova Trimestral")
    mt = campo_nota(verbose_name="Média Trimestral", editable=False)
    lancado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actualizado_em = models.DateTimeField(auto_now=True)
 
    class Meta:
        unique_together = ("matricula", "disciplina", "trimestre")
 
    def save(self, *args, **kwargs):
        from app.avaliacao.services.regras_avaliacao import recalcular_trimestral
        recalcular_trimestral(self)
        super().save(*args, **kwargs)
 
    def __str__(self):
        return f"{self.matricula.aluno} {self.disciplina} T{self.trimestre.designacao}: {self.mt}"

class Exame(models.Model):
    class Tipo(models.TextChoices):
        NACIONAL = "NAC", "Exame Nacional"
        RECURSO = "REC", "Exame de Recurso"
        ESPECIAL = "ESP", "Época Especial"
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True)
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="exames")
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=3, choices=Tipo.choices, default=Tipo.NACIONAL)
    data = models.DateField(null=True, blank=True)
    nota = campo_nota()
 
    def __str__(self):
        return f"{self.get_tipo_display()} {self.disciplina} {self.nota}"

class ProvaAptidaoProfissional(models.Model):
    """PAP e estágio - cursos técnicos (classe terminal)."""
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True)
    matricula = models.OneToOneField(Matricula, on_delete=models.CASCADE, related_name="pap")
    tema = models.CharField(max_length=250, blank=True)
    nota_estagio = campo_nota()
    nota_pap = campo_nota()
 
 
class ResultadoAnual(models.Model):
    
    class Situacao(models.TextChoices):
        PENDENTE = "PEND", "Pendente"
        POSITIVA = "POS", "Apto"
        NEGATIVA = "NEG", "N/Apto"
        APROVADO = "Aprovado", _("Aprovado")
        APROVADO_EXAME = "Aprovado por Exame", _("Aprovado por Exame")
        REPROVADO = "Reprovado", _("Reprovado")
        REPROVADO_EXAME = "Reprovado em Exame", _("Reprovado em Exame")
        ADMITIDO_EXAME = "Admitido a Exame", _("Admitido a Exame")
        TRANSFERIDO = "Transferido", _("Transferido")
        DESISTENTE = "Desistente", _("Desistente")
        AGUARDAR_EXAME = "Aguardar Exame", _("Aguardar Exame")
    
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True)
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="resultados_anuais")
    ano_lectivo = models.ForeignKey(AnoLectivo, on_delete=models.SET_NULL, null=True, related_name="resultados_anuais")
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    mt1 = campo_nota(editable=False)
    mt2 = campo_nota(editable=False)
    mt3 = campo_nota(editable=False)
    mfd = campo_nota(verbose_name="Média Final da Disciplina", editable=False)
    nota_exame = campo_nota(editable=False)
    nota_final = campo_nota(editable=False)
    situacao = models.CharField(max_length=40, choices=Situacao.choices, default=Situacao.PENDENTE)
 
    class Meta:
        unique_together = ("matricula", "disciplina")
 
    def __str__(self):
        return f"{self.matricula.aluno} {self.disciplina}: {self.nota_final}"
        

# --------------------------------------------------------------------------
# Assiduidade, reclamações e auditoria
# --------------------------------------------------------------------------
class Falta(models.Model):
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name="faltas")
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    data = models.DateField()
    tempos = models.PositiveSmallIntegerField(default=1)
    justificada = models.BooleanField(default=False)
    motivo = models.CharField(max_length=200, blank=True)
 
 
class Reclamacao(models.Model):
    class Estado(models.TextChoices):
        PENDENTE = "PEND", "Pendente"
        DEFERIDA = "DEF", "Deferida"
        INDEFERIDA = "INDEF", "Indeferida"
 
    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    trimestre = models.ForeignKey(Trimestre, on_delete=models.PROTECT, null=True, blank=True)
    motivo = models.TextField()
    nota_original = campo_nota()
    nota_revista = campo_nota()
    estado = models.CharField(max_length=5, choices=Estado.choices, default=Estado.PENDENTE)
    criada_em = models.DateTimeField(auto_now_add=True)
    decidida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
 
 
class HistoricoNota(models.Model):
    """Auditoria de alterações a notas."""
    modelo = models.CharField(max_length=60)
    objecto_id = models.PositiveIntegerField()
    campo = models.CharField(max_length=40)
    valor_anterior = models.CharField(max_length=20, blank=True)
    valor_novo = models.CharField(max_length=20, blank=True)
    motivo = models.CharField(max_length=200, blank=True)
    utilizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    data = models.DateTimeField(auto_now_add=True)
 
 
# --------------------------------------------------------------------------
# Sinais: recálculo automático em cascata
# --------------------------------------------------------------------------
@receiver([post_save, post_delete], sender=AvaliacaoContinua)
def _actualiza_mac(sender, instance, **kw):
    r, _ = ResultadoTrimestral.objects.get_or_create(
        matricula=instance.matricula, disciplina=instance.disciplina, trimestre=instance.trimestre)
    r.save()
 
 
@receiver(post_save, sender=ResultadoTrimestral)
def _actualiza_anual(sender, instance, **kw):
    from app.avaliacao.services.regras_avaliacao import recalcular_anual
    recalcular_anual(instance.matricula, instance.disciplina)
 
 
@receiver([post_save, post_delete], sender=Exame)
def _actualiza_anual_exame(sender, instance, **kw):
    from app.avaliacao.services.regras_avaliacao import recalcular_anual
    recalcular_anual(instance.matricula, instance.disciplina)

class LogAuditoria(models.Model):

    class Accao(models.TextChoices):
        CRIAR = "criar", _("Criar")
        ACTUALIZAR = "actualizar", _("Actualizar")
        ELIMINAR = "eliminar", _("Eliminar")
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        EXPORTAR = "exportar", _("Exportar")
        IMPRIMIR = "imprimir", _("Imprimir")
        OUTRO = "outro", _("Outro")

    class Modulo(models.TextChoices):
        ALUNO = "aluno", _("Aluno")
        PROFESSOR = "professor", _("Professor")
        MATRICULA = "matricula", _("Matrícula")
        INSCRICAO = "inscricao", _("Inscrição")
        NOTA = "nota", _("Nota")
        FINANCEIRO = "financeiro", _("Financeiro")
        UTILIZADOR = "utilizador", _("Utilizador")
        CONFIGURACAO = "configuracoes", _("Configuração")
        TURMA = "turma", _("Turma")
        COMUNICADO = "comunicado", _("Comunicado")
        SISTEMA = "sistema", _("Sistema")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    utilizador = models.ForeignKey(
        Utilizador,
        on_delete=models.SET_NULL,
        null=True,
        related_name="logs_auditoria",
        verbose_name=_("Utilizador"),
    )
    accao = models.CharField(
        max_length=100,
        choices=Accao.choices,
        verbose_name=_("Acção"),
    )
    modulo = models.CharField(
        max_length=50,
        choices=Modulo.choices,
        verbose_name=_("Módulo"),
    )
    descricao = models.TextField(verbose_name=_("Descrição"))
    objeto_id = models.CharField(
        max_length=100, blank=True, null=True,
        db_index=True,
        verbose_name=_("ID do Objecto"),
    )
    objeto_tipo = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name=_("Tipo do Objecto"),
    )
    ip_address = models.GenericIPAddressField(verbose_name=_("Endereço IP"))
    user_agent = models.TextField(blank=True, verbose_name=_("User Agent"))
    dados_antes = models.JSONField(null=True, blank=True, verbose_name=_("Dados Antes"))
    dados_depois = models.JSONField(null=True, blank=True, verbose_name=_("Dados Depois"))
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Timestamp"))

    class Meta:
        db_table = "log_auditoria"
        verbose_name = _("Log de Auditoria")
        verbose_name_plural = _("Logs de Auditoria")
        ordering = ["-timestamp"]
        # Logs nunca devem ser alterados — managed=True mas sem update
        indexes = [
            models.Index(fields=[ "timestamp"], name="idx_log_timestamp"),
            models.Index(fields=[ "modulo", "timestamp"], name="idx_log_modulo"),
            models.Index(fields=["utilizador", "timestamp"], name="idx_log_utilizador_timestamp"),
            models.Index(fields=["accao", "modulo"], name="idx_log_accao_modulo"),
            models.Index(fields=["objeto_id", "objeto_tipo"], name="idx_log_objeto"),
            models.Index(fields=["ip_address"], name="idx_log_ip"),
        ]

    def __str__(self) -> str:
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.utilizador} — {self.accao} em {self.modulo}"

    def save(self, *args, **kwargs):
        """Logs de auditoria são imutáveis — impede actualizações."""
        if self.pk and LogAuditoria.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Logs de auditoria não podem ser modificados."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Logs de auditoria não podem ser eliminados."""
        raise ValidationError(_("Logs de auditoria não podem ser eliminados."))
