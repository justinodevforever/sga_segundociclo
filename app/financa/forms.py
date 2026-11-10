from django import forms
from django.utils import timezone
from .models import ContaAluno, Pagamento, PropinaMensal, ConfiguracaoFinanceira
from decimal import Decimal


class ContaAlunoForm(forms.ModelForm):
    class Meta:
        model = ContaAluno
        fields = ['aluno', 'ano_lectivo','valor_propina_mensal', 'observacoes']
        widgets = {
            'aluno': forms.Select(attrs={
                'class': 'form-control-custom',
            }),
            'ano_lectivo': forms.Select(attrs={
                'class': 'form-control-custom',
            }),
            'valor_propina_mensal': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'placeholder': 'Ex: 15000',
                'min': '0',
                'step': '0.01',
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control-custom',
                'rows': 3,
                'placeholder': 'Observações adicionais...',
            }),
        }
        labels = {
            'aluno': 'Aluno',
            'ano_lectivo': 'Ano Lectivo',
            'valor_propina_mensal': 'Valor da Propina Mensal (Kz)',
            'observacoes': 'Observações',
        }

    def clean(self):
        cleaned_data = super().clean()
        aluno = cleaned_data.get('aluno')
        ano_lectivo = cleaned_data.get('ano_lectivo')
        if aluno and ano_lectivo:
            exists = ContaAluno.objects.filter(
                aluno=aluno, ano_lectivo=ano_lectivo
            ).exclude(pk=self.instance.pk).exists()
            if exists:
                raise forms.ValidationError(
                    'Este aluno já possui uma conta para este ano lectivo.'
                )
        return cleaned_data


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = [
            'conta_aluno', 'valor', 'data_pagamento',
            'metodo_pagamento', 'referencia', 'observacoes'
        ]
        widgets = {
            'conta_aluno': forms.Select(attrs={
                'class': 'form-control-custom',
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'placeholder': 'Ex: 15000.00',
                'min': '0.01',
                'step': '0.01',
            }),
            'data_pagamento': forms.DateInput(attrs={
                'class': 'form-control-custom',
                'type': 'date',
            }),
            'metodo_pagamento': forms.Select(attrs={
                'class': 'form-control-custom',
            }),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control-custom',
                'placeholder': 'Referência bancária, nº de ordem, etc.',
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control-custom',
                'rows': 3,
                'placeholder': 'Observações sobre o pagamento...',
            }),
        }
        labels = {
            'conta_aluno': 'Conta do Aluno',
            'valor': 'Valor Pago (Kz)',
            'data_pagamento': 'Data do Pagamento',
            'metodo_pagamento': 'Método de Pagamento',
            'referencia': 'Referência',
            'observacoes': 'Observações',
        }

    def __init__(self, *args, **kwargs):
        conta_aluno_id = kwargs.pop('conta_aluno_id', None)
        super().__init__(*args, **kwargs)
        if conta_aluno_id:
            self.fields['conta_aluno'].initial = conta_aluno_id
            self.fields['conta_aluno'].widget = forms.HiddenInput()
        self.fields['data_pagamento'].initial = timezone.now().date()

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        if valor and valor <= 0:
            raise forms.ValidationError('O valor deve ser maior que zero.')
        return valor

    def clean(self):
        cleaned_data = super().clean()
        conta = cleaned_data.get('conta_aluno')
        valor = cleaned_data.get('valor')
        if conta and valor:
            if valor > conta.saldo_devedor and conta.saldo_devedor > 0:
                # Permitir pagamento maior (crédito)
                pass
        return cleaned_data


class PropinaMensalForm(forms.ModelForm):
    class Meta:
        model = PropinaMensal
        fields = ['mes', 'valor', 'data_vencimento', 'status']
        widgets = {
            'mes': forms.Select(attrs={'class': 'form-control-custom'}),
            'valor': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'min': '0',
                'step': '0.01',
            }),
            'data_vencimento': forms.DateInput(attrs={
                'class': 'form-control-custom',
                'type': 'date',
            }),
            'status': forms.Select(attrs={'class': 'form-control-custom'}),
        }


class FiltroContaForm(forms.Form):
    STATUS_CHOICES = [('', 'Todos os Status')] + list(ContaAluno._meta.get_field('status').choices)

    busca = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Buscar por nome ou número...',
        })
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    ano_lectivo = forms.IntegerField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )

    def __init__(self, *args, anos=None, **kwargs):
        super().__init__(*args, **kwargs)
        if anos:
            self.fields['ano_lectivo'].widget.choices = (
                [('', 'Todos os Anos')] +
                [(a.id, str(a)) for a in anos]
            )


class ConfiguracaoFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoFinanceira
        fields = [
            'ano_lectivo', 'valor_propina_padrao',
            'dia_vencimento', 'limite_bloqueio_meses', 'taxa_matricula'
        ]
        widgets = {
            'ano_lectivo': forms.Select(attrs={'class': 'form-control-custom'}),
            'valor_propina_padrao': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'placeholder': 'Ex: 15000',
                'min': '0', 'step': '0.01',
            }),
            'dia_vencimento': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'min': '1', 'max': '28',
            }),
            'limite_bloqueio_meses': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'min': '1', 'max': '12',
            }),
            'taxa_matricula': forms.NumberInput(attrs={
                'class': 'form-control-custom',
                'placeholder': 'Ex: 5000',
                'min': '0', 'step': '0.01',
            }),
        }
        labels = {
            'ano_lectivo': 'Ano Lectivo',
            'valor_propina_padrao': 'Valor Padrão da Propina (Kz)',
            'dia_vencimento': 'Dia de Vencimento Mensal',
            'limite_bloqueio_meses': 'Meses para Bloqueio Automático',
            'taxa_matricula': 'Taxa de Matrícula (Kz)',
        }