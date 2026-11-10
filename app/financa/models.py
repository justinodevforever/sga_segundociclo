from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db.models import Sum
import uuid
import qrcode
import io
import base64
from decimal import Decimal
from app.db.models import TimestampMixin


MESES = [
    (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'),
    (4, 'Abril'), (5, 'Maio'), (6, 'Junho'),
    (9, 'Setembro'),
    (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
]

STATUS_CONTA = [
    ('em_dia', 'Em Dia'),
    ('pendente', 'Pendente'),
    ('atrasado', 'Atrasado'),
    ('bloqueado', 'Bloqueado'),
]

STATUS_PROPINA = [
    ('pago', 'Pago'),
    ('pendente', 'Pendente'),
    ('atrasado', 'Atrasado'),
]


class ContaAluno(models.Model):
    
    aluno = models.ForeignKey(
        'db.Aluno', on_delete=models.CASCADE,
        related_name='contas', verbose_name='Aluno'
    )
    ano_lectivo = models.ForeignKey(
        'db.AnoLectivo', on_delete=models.CASCADE,
        related_name='contas', verbose_name='Ano Lectivo'
    )
    total_devido = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], verbose_name='Total Devido (Kz)'
    )
    total_pago = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], verbose_name='Total Pago (Kz)'
    )
    saldo_devedor = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Saldo Devedor (Kz)'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CONTA,
        default='pendente', verbose_name='Status'
    )
    valor_propina_mensal = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Valor Propina Mensal (Kz)'
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    class Meta:
        unique_together = ('aluno', 'ano_lectivo')
        verbose_name = 'Conta do Aluno'
        verbose_name_plural = 'Contas dos Alunos'
        ordering = ['-ano_lectivo__data_inicio', 'aluno__nome_completo']

    def __str__(self):
        return f"{self.aluno} — {self.ano_lectivo}"

    def calcular_saldo(self):
        self.total_pago = self.pagamentos.aggregate(
            total=Sum('valor')
        )['total'] or Decimal('0')
        self.saldo_devedor = max(self.total_devido - self.total_pago, Decimal('0'))
        self.atualizar_status()

    def atualizar_status(self):
        hoje = timezone.now().date()
        propinas_atrasadas = self.propinas.filter(
            status='atrasado'
        ).exists()
        propinas_pendentes = self.propinas.filter(
            status='pendente',
            data_vencimento__lt=hoje
        ).exists()

        if self.saldo_devedor == 0:
            self.status = 'em_dia'
        elif self.saldo_devedor >= (self.valor_propina_mensal * 3):
            self.status = 'bloqueado'
        elif propinas_atrasadas or propinas_pendentes:
            self.status = 'atrasado'
        else:
            self.status = 'pendente'

    def pode_fazer_exame(self):
        return self.status != 'bloqueado'

    def pode_matricular(self):
        return self.status != 'bloqueado'

    def pode_ver_notas(self):
        return self.saldo_devedor == 0

    @property
    def percentagem_pago(self):
        if self.total_devido == 0:
            return 100
        return int((self.total_pago / self.total_devido) * 100)

    @property
    def status_display_class(self):
        mapa = {
            'em_dia': 'tag-green',
            'pendente': 'tag-yellow',
            'atrasado': 'tag-red',
            'bloqueado': 'tag-red',
        }
        return mapa.get(self.status, 'tag-gray')

    def save(self, *args, **kwargs):
        self.saldo_devedor = max(self.total_devido - self.total_pago, Decimal('0'))
        super().save(*args, **kwargs)


class PropinaMensal(TimestampMixin):
    
    conta_aluno = models.ForeignKey(
        ContaAluno, on_delete=models.CASCADE,
        related_name='propinas', verbose_name='Conta do Aluno'
    )
    mes = models.PositiveSmallIntegerField(choices=MESES, verbose_name='Mês')
    valor = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)], verbose_name='Valor (Kz)'
    )
    valor_pago = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Valor Pago (Kz)'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_PROPINA,
        default='pendente', verbose_name='Status'
    )
    data_vencimento = models.DateField(verbose_name='Data de Vencimento')
    data_pagamento = models.DateField(
        null=True, blank=True, verbose_name='Data de Pagamento'
    )

    class Meta:
        unique_together = ('conta_aluno', 'mes')
        verbose_name = 'Propina Mensal'
        verbose_name_plural = 'Propinas Mensais'
        ordering = ['mes']

    def __str__(self):
        return f"{self.get_mes_display()} — {self.conta_aluno}"

    @property
    def saldo_propina(self):
        return max(self.valor - self.valor_pago, Decimal('0'))

    def atualizar_status(self):
        hoje = timezone.now().date()
        if self.valor_pago >= self.valor:
            self.status = 'pago'
            if not self.data_pagamento:
                self.data_pagamento = hoje
        elif self.data_vencimento < hoje:
            self.status = 'atrasado'
        else:
            self.status = 'pendente'


class Pagamento(TimestampMixin):
    
    conta_aluno = models.ForeignKey(
        ContaAluno, on_delete=models.CASCADE,
        related_name='pagamentos', verbose_name='Conta do Aluno'
    )
    valor = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Valor Pago (Kz)'
    )
    data_pagamento = models.DateField(
        default=timezone.now, verbose_name='Data do Pagamento'
    )
    numero_recibo = models.CharField(
        max_length=30, unique=True, verbose_name='Número do Recibo'
    )
    referencia = models.CharField(
        max_length=100, blank=True, verbose_name='Referência'
    )
    metodo_pagamento = models.CharField(
        max_length=30, choices=[
            ('dinheiro', 'Dinheiro'),
            ('transferencia', 'Transferência Bancária'),
            ('multicaixa', 'Multicaixa'),
            ('cheque', 'Cheque'),
        ],
        default='dinheiro', verbose_name='Método de Pagamento'
    )
    registado_por = models.ForeignKey(
        'db.Utilizador', on_delete=models.SET_NULL, null=True,
        related_name='pagamentos_registados', verbose_name='Registado por'
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    uuid_validacao = models.UUIDField(
        default=uuid.uuid4, unique=True, verbose_name='UUID de Validação'
    )
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-data_pagamento', '-data_criacao']

    def __str__(self):
        return f"Recibo {self.numero_recibo} — {self.conta_aluno.aluno}"

    def gerar_numero_recibo(self):
        ano = timezone.now().year
        ultimo = Pagamento.objects.filter(
            numero_recibo__startswith=f'REC-{ano}-'
        ).count()
        return f'REC-{ano}-{str(ultimo + 1).zfill(5)}'

    def gerar_qr_code(self):
        url = f"/financeiro/validar/{self.numero_recibo}/"
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode()

    def save(self, *args, **kwargs):
        if not self.numero_recibo:
            self.numero_recibo = self.gerar_numero_recibo()
        super().save(*args, **kwargs)
        self._distribuir_pagamento()
        self._atualizar_conta()

    def _distribuir_pagamento(self):
        """Distribui o valor pelas propinas pendentes (FIFO)."""
        propinas = self.conta_aluno.propinas.exclude(
            status='pago'
        ).order_by('mes')
        restante = self.valor
        for propina in propinas:
            if restante <= 0:
                break
            abater = min(restante, propina.saldo_propina)
            propina.valor_pago += abater
            restante -= abater
            propina.atualizar_status()
            propina.save()

    def _atualizar_conta(self):
        conta = self.conta_aluno
        conta.calcular_saldo()
        conta.save()


class LogFinanceiro(TimestampMixin):
    ACOES = [
        ('pagamento', 'Pagamento Registado'),
        ('conta_criada', 'Conta Criada'),
        ('status_alterado', 'Status Alterado'),
        ('propina_gerada', 'Propinas Geradas'),
    ]
    
    conta_aluno = models.ForeignKey(
        ContaAluno, on_delete=models.CASCADE,
        related_name='logs', verbose_name='Conta'
    )
    acao = models.CharField(max_length=30, choices=ACOES)
    descricao = models.TextField()
    usuario = models.ForeignKey(
        'db.Utilizador', on_delete=models.SET_NULL, null=True
    )
    data = models.DateTimeField(auto_now_add=True)
    dados_extras = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-data']
        verbose_name = 'Log Financeiro'

    def __str__(self):
        return f"{self.get_acao_display()} — {self.conta_aluno}"


class ConfiguracaoFinanceira(TimestampMixin):
    
    ano_lectivo = models.OneToOneField(
        'db.AnoLectivo', on_delete=models.CASCADE,
        related_name='config_financeira'
    )
    valor_propina_padrao = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Valor Padrão da Propina (Kz)'
    )
    dia_vencimento = models.PositiveSmallIntegerField(
        default=10, verbose_name='Dia de Vencimento Mensal'
    )
    limite_bloqueio_meses = models.PositiveSmallIntegerField(
        default=3, verbose_name='Meses em Atraso para Bloqueio'
    )
    taxa_matricula = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Taxa de Matrícula (Kz)'
    )

    class Meta:
        verbose_name = 'Configuração Financeira'

    def __str__(self):
        return f"Config Financeira — {self.ano_lectivo}"