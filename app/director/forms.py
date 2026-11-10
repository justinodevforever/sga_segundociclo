
from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import date
from django.core.validators import MinValueValidator, MaxValueValidator

import string, secrets

from django.shortcuts import get_list_or_404

from app.db.models import *
from app.financa.models import ConfiguracaoFinanceira

class ConfiguracaoForm(forms.Form):

    periodo_exame = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'id':'chec', 'hidden':'hidden'})
    )
    periodo_prova_1_trimestre = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput()
    )
    periodo_prova_2_trimestre = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput()
    )
    periodo_prova_3_trimestre = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput()
    )
    periodo_recurso = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput()
    )

    periodo_inscricao = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput())
    periodo_confirmacao = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput())
    periodo_matricula = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput())

    dia_vencimento_propina = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    def save(self):

        config = TenantConfiguracao(
            periodo_exame=self.cleaned_data.get('periodo_exame'),
            periodo_prova_1_trimestre=self.cleaned_data.get('periodo_prova_1_trimestre'),
            periodo_prova_2_trimestre=self.cleaned_data.get('periodo_prova_2_trimestre'),
            periodo_prova_3_trimestre=self.cleaned_data.get('periodo_prova_3_trimestre'),
            periodo_recurso=self.cleaned_data.get('periodo_recurso'),
            periodo_inscricao=self.cleaned_data.get('periodo_inscricao'),
            periodo_confirmacao=self.cleaned_data.get('periodo_confirmacao'),
            periodo_matricula=self.cleaned_data.get('periodo_matricula'),
            dia_vencimento_propina=self.cleaned_data.get('dia_vencimento_propina'),
        )

        return config

class FuncionarioForm(forms.Form):

    nome_completo = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Nome completo', 'class': 'form-control-custom'
        })
    )
    data_nascimento = forms.DateField(
        required=True,
        widget= forms.DateInput(attrs={'type': 'date', 'class': 'form-control-custom'})
    )
    genero = forms.ChoiceField(
        choices= PessoaMixin.Genero.choices,
        required=True,
        widget= forms.Select(attrs={'class': 'form-control-custom'})
    )
    telefone = forms.CharField(
        max_length=9,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Número de telefone','class': 'form-control-custom'})
    )
    numero_agente = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Número de agente', 'class': 'form-control-custom'})
    )
    bi = forms.CharField(
        required=True,
        max_length=14,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Número de B.I', 'class': 'form-control-custom'
        })
    )
    especialidade = forms.CharField(
        required=False,
        max_length=100,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'especialidade', 'class': 'form-control-custom'
        })
    )
    nivel_academico = forms.ChoiceField(
        required=False,
        choices=PessoaMixin.NivelAcademico.choices,
        widget= forms.Select(attrs={'class': 'form-control-custom'})
    )
    instituicao_formacao = forms.CharField(
        required=False,
        max_length=200,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Instituição de formação', 'class': 'form-control-custom'
        })
    )
    anos_experiencia = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()', 'class': 'form-control-custom'
        }),
    )
    email = forms.EmailField(
        required=True,
        max_length=100,
        widget=forms.TextInput(attrs={
            'type': 'email',
            'placeholder': 'Email', 'class': 'form-control-custom'
        })
    )
    endereco = forms.CharField(
        required=False,
        widget= forms.Textarea(attrs={
            'id': 'textarea',
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Ex.: Rua Comadante Dangereux, Popular', 'class': 'form-control-custom'
        })
    )
    tipo_contrato = forms.ChoiceField(
        required=True,
        choices=Funcionario.TipoContrato.choices,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    tipo_funcionario = forms.ChoiceField(
        required=True,
        choices=Funcionario.TipoFuncionario.choices,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    carga_horaria_semanal = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom'})
    )
   

    def save(self):

        funcionario = Funcionario(
            nome_completo = self.cleaned_data['nome_completo'],
            tipo_funcionario = self.cleaned_data['tipo_funcionario'],
            telefone = self.cleaned_data['telefone'],
            genero = self.cleaned_data['genero'],
            data_nascimento = self.cleaned_data['data_nascimento'],
            numero_agente = self.cleaned_data['numero_agente'],
            bi = self.cleaned_data['bi'],
            especialidade = self.cleaned_data['especialidade'],
            nivel_academico = self.cleaned_data['nivel_academico'],
            instituicao_formacao = self.cleaned_data['instituicao_formacao'],
            anos_experiencia = self.cleaned_data['anos_experiencia'],
            email = self.cleaned_data['email'],
            endereco = self.cleaned_data['endereco'],
            tipo_contrato = self.cleaned_data['tipo_contrato'],
            carga_horaria_semanal = self.cleaned_data['carga_horaria_semanal'],
        )
        
        return funcionario
        
        
        
class FuncionarioEditForm(forms.Form):

    nome_completo = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Nome completo', 'class': 'form-control-custom'
        })
    )
    data_nascimento = forms.DateField(
        required=True,
        widget= forms.DateInput(attrs={'type': 'date','class': 'form-control-custom'})
    )
    genero = forms.ChoiceField(
        choices= PessoaMixin.Genero.choices,
        required=True,
        widget= forms.Select(attrs={'class': 'form-control-custom'})
    )
    telefone = forms.CharField(
        max_length=9,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Número de telefone', 'class': 'form-control-custom'})
    )

    numero_agente = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Número de agente', 'class': 'form-control-custom'})
    )
    bi = forms.CharField(
        required=True,
        max_length=14,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Número de B.I', 'class': 'form-control-custom'
        })
    )
    especialidade = forms.CharField(
        required=False,
        max_length=100,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'especialidade', 'class': 'form-control-custom'
        })
    )
    nivel_academico = forms.ChoiceField(
        required=True,
        choices=PessoaMixin.NivelAcademico.choices,
        widget= forms.Select(attrs={'class': 'form-control-custom'})
    )
    instituicao_formacao = forms.CharField(
        required=False,
        max_length=200,
        widget= forms.TextInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Instituição de formação', 'class': 'form-control-custom'
        })
    )
    tipo_funcionario = forms.ChoiceField(
        required=True,
        choices=Funcionario.TipoFuncionario.choices,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )       
    anos_experiencia = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={
            'oninput': 'this.value=this.value.toUpperCase()', 'class': 'form-control-custom'
        }),
    )
    email = forms.EmailField(
        required=True,
        max_length=100,
        widget=forms.TextInput(attrs={
            'type': 'email',
            'placeholder': 'Email',
            'class': 'form-control-custom'
        })
    )
    endereco = forms.CharField(
        required=False,
        widget= forms.Textarea(attrs={
            'id': 'textarea',
            'oninput': 'this.value=this.value.toUpperCase()',
            'placeholder': 'Instituição de formação',
            'class': 'form-control-custom'
        })
    )
    tipo_contrato = forms.ChoiceField(
        required=True,
        choices=Funcionario.TipoContrato.choices,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    carga_horaria_semanal = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom'})
    )
    status = forms.ChoiceField(
        required=True,
        choices=Funcionario.Status.choices,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )

    def __init__(self, *args, **kwargs):

        self.funcionario = kwargs.pop('funcionario', None)
        super().__init__(*args, **kwargs)

        self.fields['nome_completo'].initial = self.funcionario.nome_completo
        self.fields['tipo_funcionario'].initial = self.funcionario.tipo_funcionario
        self.fields['telefone'].initial = self.funcionario.telefone
        self.fields['genero'].initial = self.funcionario.genero
        self.fields['data_nascimento'].initial = self.funcionario.data_nascimento
        self.fields['bi'].initial = self.funcionario.bi
        self.fields['especialidade'].initial = self.funcionario.especialidade
        self.fields['nivel_academico'].initial = self.funcionario.nivel_academico
        self.fields['instituicao_formacao'].initial = self.funcionario.instituicao_formacao
        self.fields['anos_experiencia'].initial = self.funcionario.anos_experiencia
        self.fields['email'].initial = self.funcionario.email
        self.fields['endereco'].initial = self.funcionario.endereco
        self.fields['tipo_contrato'].initial = self.funcionario.tipo_contrato
        self.fields['carga_horaria_semanal'].initial = self.funcionario.carga_horaria_semanal 
        self.fields['numero_agente'].initial = self.funcionario.numero_agente
        self.fields['status'].initial = self.funcionario.status
   

    def save(self):

        self.funcionario.nome_completo = self.cleaned_data['nome_completo'] 
        self.funcionario.tipo_funcionario = self.cleaned_data['tipo_funcionario']
        self.funcionario.telefone = self.cleaned_data['telefone']
        self.funcionario.genero = self.cleaned_data['genero']
        self.funcionario.data_nascimento = self.cleaned_data['data_nascimento']
        self.funcionario.numero_agente = self.cleaned_data['numero_agente']
        self.funcionario.bi = self.cleaned_data['bi']
        self.funcionario.especialidade = self.cleaned_data['especialidade']
        self.funcionario.nivel_academico = self.cleaned_data['nivel_academico']
        self.funcionario.instituicao_formacao = self.cleaned_data['instituicao_formacao']
        self.funcionario.anos_experiencia = self.cleaned_data['anos_experiencia']
        self.funcionario.email = self.cleaned_data['email']
        self.funcionario.endereco = self.cleaned_data['endereco']
        self.funcionario.tipo_contrato = self.cleaned_data['tipo_contrato']
        self.funcionario.carga_horaria_semanal = self.cleaned_data['carga_horaria_semanal']
        self.funcionario.status = self.cleaned_data['status']

        return self.funcionario

class AlunoForm(forms.Form):

    nome_completo = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome completo'})
    )
    nome_pai = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome do pai'})
    )
    nome_mae = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome da mãe'})
    )
    data_nascimento = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
  
    naturalidade = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Naturalidade'})
    )
    bi = forms.CharField(
        max_length=14, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'B.I'})
    )
    data_emissao_bi = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    genero = forms.ChoiceField(choices=PessoaMixin.Genero.choices)
    provincia = forms.CharField(
        max_length=50, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Província'})
        
    )
    telefone = forms.CharField(
        max_length=9, 
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Telefone', 'id': 'telefone'})
    )
    municipio = forms.CharField(
        max_length=50, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Município'})
    )
    bairro = forms.CharField(
        max_length=100, 
        required=False,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Bairro'})
    )
    endereco_completo = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'endereço completo'})
    )


    def clean(self):
        clean_data =  super().clean()

        telefone=self.cleaned_data['telefone']
        
        if telefone:
            telefone_validade = int(telefone[0])

            if telefone_validade != 9:
                self.add_error('telefone', 'Número de telefone inválido!')

        return clean_data

    def save(self):

        aluno = Aluno(
            nome_completo=self.cleaned_data['nome_completo'],
            nome_pai=self.cleaned_data['nome_pai'],
            nome_mae=self.cleaned_data['nome_mae'],
            data_nascimento=self.cleaned_data['data_nascimento'],
            naturalidade=self.cleaned_data['naturalidade'],
            telefone=self.cleaned_data['telefone'],
            bi=self.cleaned_data.get('bi'),
            data_emissao_bi=self.cleaned_data.get('data_emissao_bi'),
            genero=self.cleaned_data['genero'],
            provincia=self.cleaned_data['provincia'],
            municipio=self.cleaned_data['municipio'],
            bairro=self.cleaned_data['bairro'],
            endereco_completo=self.cleaned_data['endereco_completo'],
        )

        return aluno
    

    
class AlunoEditForm(forms.Form):

    nome_completo = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome completo'})
    )
    nome_pai = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome do pai'})
    )
    nome_mae = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Nome da mãe'})
    )
    data_nascimento = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
  
    naturalidade = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Naturalidade'})
    )
    bi = forms.CharField(
        max_length=14, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'B.I'})
    )
    data_emissao_bi = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    genero = forms.ChoiceField(choices=PessoaMixin.Genero.choices)
    provincia = forms.CharField(
        max_length=50, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Província'})
        
    )
    telefone = forms.CharField(
        max_length=9, 
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Telefone', 'id': 'telefone'})
    )
    municipio = forms.CharField(
        max_length=50, 
        required=True,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Município'})
    )
    bairro = forms.CharField(
        max_length=100, 
        required=False,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'Bairro'})
    )
    endereco_completo = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'oninput': 'this.value=this.value.toUpperCase()', 'placeholder': 'endereço completo'})
    )

    def __init__(self, *args, **kwargs):
        self.aluno = kwargs.pop("aluno")
        super().__init__(*args, **kwargs)

        if self.aluno:
            self.fields['nome_completo'].initial = self.aluno.nome_completo
            self.fields['nome_pai'].initial = self.aluno.nome_pai
            self.fields['nome_mae'].initial = self.aluno.nome_mae
            self.fields['data_nascimento'].initial = self.aluno.data_nascimento
            self.fields['naturalidade'].initial = self.aluno.naturalidade
            self.fields['telefone'].initial = self.aluno.telefone
            self.fields['bi'].initial = self.aluno.bi
            self.fields['data_emissao_bi'].initial = self.aluno.data_emissao_bi
            self.fields['genero'].initial = self.aluno.genero
            self.fields['provincia'].initial = self.aluno.provincia
            self.fields['municipio'].initial = self.aluno.municipio
            self.fields['endereco_completo'].initial = self.aluno.endereco_completo
            self.fields['bairro'].initial = self.aluno.bairro
           
    def clean(self):
        clean_data =  super().clean()

        telefone=self.cleaned_data['telefone']
        
        if telefone:
            telefone_validade = int(telefone[0])

            if telefone_validade != 9:
                self.add_error('telefone', 'Número de telefone inválido!')

        return clean_data

    def save(self):

        
        self.aluno.nome_completo=self.cleaned_data['nome_completo']
        self.aluno.nome_pai=self.cleaned_data['nome_pai']
        self.aluno.nome_mae=self.cleaned_data['nome_mae']
        self.aluno.data_nascimento=self.cleaned_data['data_nascimento']
        self.aluno.naturalidade=self.cleaned_data['naturalidade']
        self.aluno.telefone=self.cleaned_data['telefone']
        self.aluno.bi=self.cleaned_data.get('bi')
        self.aluno.data_emissao_bi=self.cleaned_data.get('data_emissao_bi')
        self.aluno.genero=self.cleaned_data['genero']
        self.aluno.provincia=self.cleaned_data['provincia']
        self.aluno.municipio=self.cleaned_data['municipio']
        self.aluno.endereco_completo=self.cleaned_data['endereco_completo']
        self.aluno.bairro=self.cleaned_data['bairro']
        

        return self.aluno


class CriarDisciplinaForm(forms.Form):

    nome = forms.CharField(
        required=True,
        max_length=200,
        label="Nome",
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex: Matemática',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    componente = forms.ChoiceField(
        required=True,
        choices=Disciplina.Componente.choices,
        widget=forms.Select(attrs={
            'class': 'form-control-custom',
        })
    )
    
    nome_abreviado = forms.CharField(
        required=True,
        max_length=10,
        label="Nome Abreviado",
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex: MAT',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
  

    def save(self):

        disciplina = Disciplina(
            nome = self.cleaned_data['nome'],
            nome_abreviado = self.cleaned_data['nome_abreviado'],
            componente = self.cleaned_data['componente'],
        )


        return disciplina
    
class EditarDisciplinaForm(forms.Form):


    nome = forms.CharField(
        required=True,
        max_length=200,
        label="Nome",
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex: Matemática',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    componente = forms.ChoiceField(
        required=True,
        choices=Disciplina.Componente.choices,
        widget=forms.Select(attrs={
            'class': 'form-control-custom',
        })
    )
    nome_abreviado = forms.CharField(
        required=True,
        max_length=10,
        label="Nome Abreviado",
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex: MAT',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )

    def __init__(self, *args, **kwargs):
        self.disciplina = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)
     
        self.fields['nome'].initial = self.disciplina.nome
        self.fields['nome_abreviado'].initial = self.disciplina.nome_abreviado
        self.fields['componente'].initial = self.disciplina.componente


    def save(self):

        self.disciplina.nome = self.cleaned_data['nome']
        self.disciplina.nome_abreviado = self.cleaned_data['nome_abreviado']
        self.disciplina.componente = self.cleaned_data['componente']

        self.disciplina.save()

        return self.disciplina 


class CriarClasseForm(forms.Form):
    
    designacao = forms.IntegerField(
        required=True,
        widget= forms.NumberInput(attrs={'id': 'designacao', 'placeholder': 'Ex.: 10ª classe', 'class': 'form-control-custom'})
    )
    numero = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={'id': 'designacao', 'placeholder': 'Ex.: 10', 'class': 'form-control-custom'})
    )
    ordem = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={'id': 'ordem', 'placeholder': 'ex.: 2', 'class': 'form-control-custom'})
    )


    def __init__(self, *args, **kwargs):
        self.classe = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.classe:

            self.fields['designacao'].initial = self.classe.designacao
            self.fields['numero'].initial = self.classe.numero
            self.fields['ordem'].initial = self.classe.ordem

    def clean(self):
        self.cleaned_data = super().clean()

        classe = self.cleaned_data['designacao']

        if classe:

            if classe < 0:
                return self.add_error('designacao', 'Formato de classe errado, dever ser um número positivo')

        return self.cleaned_data

    def save(self):

        classe = Classe(
            designacao = self.cleaned_data['designacao'],
            numero = self.cleaned_data['numero'],
            ordem = self.cleaned_data['ordem'],
        )

        return classe
    
class EditarClasseForm(forms.Form):
    
    designacao = forms.IntegerField(
        required=True,
        widget= forms.NumberInput(attrs={'id': 'designacao', 'placeholder': 'Ex.: 10ª classe', 'class': 'form-control-custom'})
    )
    numero = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={'id': 'designacao', 'placeholder': 'Ex.: 10', 'class': 'form-control-custom'})
    )
    ordem = forms.IntegerField(
        required=False,
        widget= forms.NumberInput(attrs={'id': 'ordem', 'placeholder': 'ex.: 2', 'class': 'form-control-custom'})
    )


    def __init__(self, *args, **kwargs):
        self.classe = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.classe:

            self.fields['designacao'].initial = self.classe.designacao
            self.fields['numero'].initial = self.classe.numero
            self.fields['ordem'].initial = self.classe.ordem

    def clean(self):
        self.cleaned_data = super().clean()

        classe = self.cleaned_data['designacao']
        
        if classe:
        
            if classe < 0:
                return self.add_error('designacao', 'Formato de classe errado, dever ser um número positivo')

        return self.cleaned_data

    def save(self):

        self.classe.designacao = self.cleaned_data['designacao']
        self.classe.numero = self.cleaned_data['numero']
        self.classe.ordem = self.cleaned_data['ordem']

        return self.classe

class CriarTrimestreForm(forms.Form):
    designacao = forms.ChoiceField(
        required=True,
        choices=[(1, "1.º"), (2, "2.º"), (3, "3.º")],
        widget=forms.Select(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex.: Iº trimestre',
        })
    )
    ano_lectivo = forms.ModelChoiceField(
        queryset=AnoLectivo.objects.all(),
        empty_label='Selecione ano',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    data_inicio = forms.DateField(
        required=False, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_inicio', 'type': 'date'})
    )
    data_fim = forms.DateField(
        required=False, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_fim', 'type': 'date'})
    )
    lancamento_aberto = forms.BooleanField(required=False)

    activo = forms.BooleanField(required=False)


    def clean(self):
        self.cleaned_data = super().clean()

        designacao = self.cleaned_data.get('designcao')


    def save(self):

        trimestre = Trimestre(
            designacao=self.cleaned_data.get('designacao'),
            ano_lectivo=self.cleaned_data.get('ano_lectivo'),
            data_inicio=self.cleaned_data.get('data_inicio'),
            data_fim=self.cleaned_data.get('data_fim'),
            lancamento_aberto=self.cleaned_data.get('lancamento_aberto'),
            activo=self.cleaned_data.get('activo')
        )

        return trimestre

class EditarTrimestreForm(forms.Form):
    designacao = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control-custom',
            'placeholder': 'Ex.: Iº trimestre',
        })
    )
    ano_lectivo = forms.ModelChoiceField(
        queryset=AnoLectivo.objects.all(),
        empty_label='Selecione ano',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    data_inicio = forms.DateField(
        required=False, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_inicio', 'type': 'date'})
    )
    data_fim = forms.DateField(
        required=False, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_fim', 'type': 'date'})
    )
    lancamento_aberto = forms.BooleanField(required=False)

    activo = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        self.trimestre = kwargs.pop('trimestre', None)
        super().__init__(*args, **kwargs)

        if self.trimestre:

            self.fields['designacao'].initial = self.trimestre.designacao
            self.fields['ano_lectivo'].initial = self.trimestre.ano_lectivo
            self.fields['data_inicio'].initial = self.trimestre.data_inicio
            self.fields['data_fim'].initial = self.trimestre.data_fim
            self.fields['lancamento_aberto'].initial = self.trimestre.designacao
            self.fields['activo'].initial = self.trimestre.activo

    def clean(self):
        self.cleaned_data = super().clean()

        designacao = self.cleaned_data.get('designcao')


    def save(self):

        self.trimestre.designacao=self.cleaned_data.get('designacao')
        self.trimestre.ano_lectivo=self.cleaned_data.get('ano_lectivo')
        self.trimestre.data_inicio=self.cleaned_data.get('data_inicio')
        self.trimestre.data_fim=self.cleaned_data.get('data_fim')
        self.trimestre.lancamento_aberto=self.cleaned_data.get('lancamento_aberto')
        self.trimestre.activo=self.cleaned_data.get('activo')

        return self.trimestre


        
class CriarCursoForm(forms.Form):
    
    nome = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={
            'id': 'nome',
            'oninput': 'this.value=this.value.toUpperCase()', 
            'placeholder': 'Nome do curso',
            'class': 'form-control-custom'
            })
    )

    nome_abreviado = forms.CharField(
        required=False,
        widget= forms.TextInput(attrs={
            'id': 'nome_abreviado',
            'placeholder': 'Abreviatura do curso',
            'oninput': 'this.value=this.value.toUpperCase()',
            'class': 'form-control-custom'
        })
    )


    duracao_anos = forms.IntegerField(
        required=True,
        widget= forms.NumberInput(attrs={'id': 'duracao_anos', 'placeholder': 'Ex.: 3',
            'class': 'form-control-custom'})
    )


    def __init__(self, *args, **kwargs):
        self.curso = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.curso:

            self.fields['nome'].initial = self.curso.nome
            self.fields['codigo'].initial = self.curso.codigo
            self.fields['nome_abreviado'].initial = self.curso.nome_abreviado
            self.fields['descricao'].initial = self.curso.descricao
            self.fields['duracao_anos'].initial = self.curso.duracao_anos


    def save(self):

        curso = Curso(
            nome = self.cleaned_data['nome'],
            nome_abreviado = self.cleaned_data['nome_abreviado'],
            duracao_anos = self.cleaned_data['duracao_anos'],
        )

        return curso


class EditarCursoForm(forms.Form):
    
    nome = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={
            'id': 'nome',
            'oninput': 'this.value=this.value.toUpperCase()', 
            'placeholder': 'Nome do curso',
            'class': 'form-control-custom'
            })
    )

    nome_abreviado = forms.CharField(
        required=False,
        widget= forms.TextInput(attrs={
            'id': 'nome_abreviado',
            'placeholder': 'Abreviatura do curso',
            'oninput': 'this.value=this.value.toUpperCase()',
            'class': 'form-control-custom'
        })
    )


    duracao_anos = forms.IntegerField(
        required=True,
        widget= forms.NumberInput(attrs={'id': 'duracao_anos', 'placeholder': 'Ex.: 3',
            'class': 'form-control-custom'})
    )


    def __init__(self, *args, **kwargs):
        self.curso = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.curso:

            self.fields['nome'].initial = self.curso.nome
            self.fields['nome_abreviado'].initial = self.curso.nome_abreviado
            self.fields['duracao_anos'].initial = self.curso.duracao_anos


    def save(self):


        self.curso.nome = self.cleaned_data['nome']
        self.curso.nome_abreviado = self.cleaned_data['nome_abreviado']
        self.curso.duracao_anos = self.cleaned_data['duracao_anos']

        return self.curso

class CriarAnoLetivoForm(forms.Form):

    designacao = forms.CharField(
        required=True, 
        widget= forms.TextInput(attrs={'class': 'form-control-custom','id': 'ano', 'placeholder': 'Ex.: 2024/2025'})
    )
    data_inicio = forms.DateField(
        required=True, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_inicio', 'type': 'date'})
    )
    data_fim = forms.DateField(
        required=True, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_fim', 'type': 'date'})
    )
    e_atual = forms.BooleanField(
        required=False, 
        widget= forms.CheckboxInput(attrs={'class': 'checkbox','id': 'e_atual'})
    )

   

    def clean(self):
        cleaned_data = super().clean()

        designacao = cleaned_data.get('designacao')
        e_atual = cleaned_data.get('e_atual')

        if e_atual == True:
            AnoLectivo.objects.all().update(e_atual=False)

        if AnoLectivo.objects.filter(designacao=designacao).exists():
            self.add_error('designacao', 'Esse ano lectivo já existe')

    def save(self):

        ano_letivo = AnoLectivo(
            designacao = self.cleaned_data['designacao'],
            data_inicio = self.cleaned_data['data_inicio'],
            data_fim = self.cleaned_data['data_fim'],
            e_atual = self.cleaned_data['e_atual'],
        )

        return ano_letivo


class EditarAnoLetivoForm(forms.Form):

    designacao = forms.CharField(
        required=True, 
        widget= forms.TextInput(attrs={'class': 'form-control-custom','id': 'ano', 'placeholder': 'Ex.: 2024/2025'})
    )
    data_inicio = forms.DateField(
        required=True, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_inicio', 'type': 'date'})
    )
    data_fim = forms.DateField(
        required=True, 
        widget= forms.DateInput(attrs={'class': 'form-control-custom','id': 'data_fim', 'type': 'date'})
    )
    e_atual = forms.BooleanField(
        required=False, 
        widget= forms.CheckboxInput(attrs={'class': 'custom-control-input','id': 'e_atual'})
    )

    def __init__(self, *args, **kwargs):
        self.ano_letivo = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.ano_letivo:

            self.fields['designacao'].initial = self.ano_letivo.designacao
            self.fields['e_atual'].initial = self.ano_letivo.e_atual
            self.fields['data_fim'].initial = self.ano_letivo.data_fim
            self.fields['data_inicio'].initial = self.ano_letivo.data_inicio

    def clean(self):
        cleaned_data = super().clean()

        designacao = cleaned_data.get('designacao')
        e_atual = cleaned_data.get('e_atual')

        if e_atual == True:
            AnoLectivo.objects.all().update(e_atual=False)

    def save(self):

        self.ano_letivo.designacao = self.cleaned_data['designacao']
        self.ano_letivo.data_inicio = self.cleaned_data['data_inicio']
        self.ano_letivo.data_fim = self.cleaned_data['data_fim']
        self.ano_letivo.e_atual = self.cleaned_data['e_atual']

        self.ano_letivo.save()

        return self.ano_letivo


class CriarPeriodoForm(forms.Form):

    designacao = forms.ChoiceField(
        choices=Periodo.Turno.choices,
        required=True, 
        widget= forms.Select(attrs={'class': 'form-control-custom','id': 'periodo'})
    )


    def clean(self):
        cleaned_data = super().clean()

        designacao = cleaned_data.get('designacao')

        if Periodo.objects.filter(designacao=designacao).exists():
            self.add_error('designacao', 'Esse período já existe')

    def save(self):

        periodo = Periodo(
            designacao = self.cleaned_data['designacao']
        )

        return periodo


class HorarioAulaForm(forms.Form):

    turma = forms.ModelChoiceField(queryset=Turma.objects.all(), label="Turma")
    disciplina = forms.ModelChoiceField(queryset=Disciplina.objects.all(), label="Disciplina")
    professor = forms.ModelChoiceField(queryset=Funcionario.objects.all(), label="Professor")
    ano_letivo = forms.ModelChoiceField(queryset=AnoLectivo.objects.all(), label="Ano lectivo")
    dia_semana = forms.ChoiceField(
        choices=HorarioAula.DiaSemana.choices,
        label="Dia da Semana"
    )
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}), label="Hora Início")
    hora_fim = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}), label="Hora Fim")
    tipo = forms.ChoiceField(
        choices=[('prova', 'Prova'), ('aula', 'Aula')],
        label="Tipo",
    )
    data_prova = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False,
        label="Data da Prova"
    )
    sala = forms.CharField(max_length=50, label="Sala")

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        data_prova = cleaned_data.get('data_prova')

        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fim = cleaned_data.get('hora_fim')

        if hora_inicio > hora_fim:

            self.add_error('hora_inicio', 'Hora início não pode ser maior que hora final')

        if tipo == 'prova' and not data_prova:
            self.add_error('data_prova', 'A data da prova é obrigatória quando o tipo é Prova.')
            
        return cleaned_data


class TurmaForm(forms.Form):

    ano_lectivo = forms.ModelChoiceField(
        queryset=AnoLectivo.objects.none(),
        empty_label='Selecione ano',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.none(),
        empty_label='Selecione curso',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    classe = forms.ModelChoiceField(
        queryset=Classe.objects.all(),
        empty_label='Selecione classe',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    designacao = forms.CharField(
        max_length=60,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: CFB-TA-10ªclasse', 
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    sala = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: Sala 101',
            'class': 'form-control-custom'
        })
    )
    periodo = forms.ChoiceField(
        choices=Turma.Turno.choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom',})
    )
    capacidade_maxima = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=40,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    vagas_disponiveis = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=40,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    classificacao_positiva = forms.CharField(
        max_length=10,
        required=True,
        initial='APTO',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: APTO',
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    classificacao_negativa = forms.CharField(
        max_length=10,
        required=True,
        initial='N/APTO',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: N/APTO',
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    valor_minimo = forms.IntegerField(
        min_value=0,
        max_value=12,
        initial=0,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    valor_maximo = forms.IntegerField(
        min_value=0,
        max_value=20,
        initial=20,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_matricula = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_propina = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_confirmacao = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['ano_lectivo'].queryset = AnoLectivo.objects.all().order_by('-e_atual', '-data_inicio')
        
        self.fields['curso'].queryset = Curso.objects.all().order_by('nome')
            
    
    def clean(self):
        designacao=self.cleaned_data['designacao']
        ano_lectivo=self.cleaned_data['ano_lectivo']
        classe=self.cleaned_data['classe']
        periodo=self.cleaned_data['periodo']
        curso=self.cleaned_data['curso']

        try:

            if Turma.objects.filter( 
                Q(designacao=designacao) & 
                Q(ano_lectivo=ano_lectivo) & 
                Q(classe=classe) & 
                Q(curso=curso) & 
                Q(periodo=periodo) 
                
                ).exists():

                self.add_error('designacao', 'Está turma já existe!')

        except Turma.DoesNotExist:
            pass

    def save(self):


        turma = Turma(
            designacao=self.cleaned_data['designacao'],
            ano_lectivo=self.cleaned_data['ano_lectivo'],
            classe=self.cleaned_data['classe'],
            periodo=self.cleaned_data['periodo'],
            curso=self.cleaned_data['curso'],
            sala=self.cleaned_data['sala'],
            capacidade_maxima=self.cleaned_data['capacidade_maxima'],
            vagas_disponiveis=self.cleaned_data['vagas_disponiveis'],
            classificacao_positiva=self.cleaned_data['classificacao_positiva'],
            classificacao_negativa=self.cleaned_data['classificacao_negativa'],
            valor_minimo=self.cleaned_data['valor_minimo'],
            valor_maximo=self.cleaned_data['valor_maximo'],
            preco_matricula=self.cleaned_data['preco_matricula'],
            preco_propina=self.cleaned_data['preco_propina'],
            preco_confirmacao=self.cleaned_data['preco_confirmacao'],
        )


        return turma
    
class TurmaEditForm(forms.Form):

    ano_lectivo = forms.ModelChoiceField(
        queryset=AnoLectivo.objects.none(),
        empty_label='Selecione ano',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.none(),
        empty_label='Selecione curso',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    classe = forms.ModelChoiceField(
        queryset=Classe.objects.all(),
        empty_label='Selecione classe',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom'})
    )
    designacao = forms.CharField(
        max_length=60,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: CFB-TA-10ªclasse', 
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    sala = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: Sala 101',
            'class': 'form-control-custom'
        })
    )
    periodo = forms.ChoiceField(
        choices=Turma.Turno.choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control-custom',})
    )
    capacidade_maxima = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=40,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    vagas_disponiveis = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=40,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    classificacao_positiva = forms.CharField(
        max_length=10,
        required=True,
        initial='APTO',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: APTO',
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    classificacao_negativa = forms.CharField(
        max_length=10,
        required=True,
        initial='N/APTO',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: N/APTO',
            'class': 'form-control-custom',
            'oninput': 'this.value=this.value.toUpperCase()'
        })
    )
    valor_minimo = forms.IntegerField(
        min_value=0,
        max_value=12,
        initial=0,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    valor_maximo = forms.IntegerField(
        min_value=0,
        max_value=20,
        initial=20,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_matricula = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_propina = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )
    preco_confirmacao = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control-custom',})
    )

    def __init__(self, *args, turma=None, **kwargs):
        self.turma = turma
        super().__init__(*args, **kwargs)

        self.fields['ano_lectivo'].queryset = AnoLectivo.objects.all().order_by('-e_atual', '-data_inicio')
        
        self.fields['curso'].queryset = Curso.objects.all().order_by('nome')

        self.fields['classe'].queryset = Classe.objects.all().order_by('designacao')
        
        self.fields['periodo'].queryset = Periodo.objects.all()
        
        if turma:
            self.fields['designacao'].initial = turma.designacao
            self.fields['sala'].initial = turma.sala
            self.fields['periodo'].initial = turma.periodo
            self.fields['sala'].initial = turma.sala
            self.fields['capacidade_maxima'].initial = turma.capacidade_maxima
            self.fields['vagas_disponiveis'].initial = turma.vagas_disponiveis
            self.fields['ano_lectivo'].initial = turma.ano_lectivo
            self.fields['curso'].initial = turma.curso
            self.fields['classe'].initial = turma.classe
            self.fields['capacidade_maxima'].initial = turma.capacidade_maxima
            self.fields['classificacao_positiva'].initial = turma.classificacao_positiva
            self.fields['classificacao_negativa'].initial = turma.classificacao_negativa
            self.fields['valor_minimo'].initial = turma.valor_minimo
            self.fields['valor_maximo'].initial = turma.valor_maximo
            self.fields['preco_matricula'].initial = turma.preco_matricula
            self.fields['preco_propina'].initial = turma.preco_propina
            self.fields['preco_confirmacao'].initial = turma.preco_confirmacao
    

    def save(self):

        self.turma.designacao=self.cleaned_data['designacao']
        self.turma.ano_lectivo=self.cleaned_data['ano_lectivo']
        self.turma.classe=self.cleaned_data['classe']
        self.turma.periodo=self.cleaned_data['periodo']
        self.turma.curso=self.cleaned_data['curso']
        self.turma.sala=self.cleaned_data['sala']
        self.turma.capacidade_maxima=self.cleaned_data['capacidade_maxima']
        self.turma.vagas_disponiveis=self.cleaned_data['vagas_disponiveis']
        self.turma.classificacao_positiva=self.cleaned_data['classificacao_positiva']
        self.turma.classificacao_negativa=self.cleaned_data['classificacao_negativa']
        self.turma.valor_minimo=self.cleaned_data['valor_minimo']
        self.turma.valor_maximo=self.cleaned_data['valor_maximo']
        self.turma.preco_matricula=self.cleaned_data['preco_matricula']
        self.turma.preco_propina=self.cleaned_data['preco_propina']
        self.turma.preco_confirmacao=self.cleaned_data['preco_confirmacao']

        return self.turma


class _EstiloMixin:
    """Aplica as classes CSS do template a todos os widgets."""

    def _estilizar(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, forms.Select):
                w.attrs["class"] = "cfg-input cfg-select"
            else:
                w.attrs["class"] = "cfg-input"


class AnoLectivoForm(_EstiloMixin, forms.ModelForm):
    class Meta:
        model = AnoLectivo
        fields = ["designacao", "data_inicio", "data_fim", "semanas_lectivas"]
        widgets = {
            "designacao": forms.TextInput(attrs={"placeholder": "Ex.: 2025/2026"}),
            "data_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estilizar()


class TrimestreForm(_EstiloMixin, forms.ModelForm):
    class Meta:
        model = Trimestre
        fields = ["designacao", "data_inicio", "data_fim", "lancamento_aberto"]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *a, ano=None, **kw):
        super().__init__(*a, **kw)
        self.ano = ano
        self._estilizar()

    def clean(self):
        d = super().clean()
        ini, fim = d.get("data_inicio"), d.get("data_fim")
        if ini and fim:
            if fim <= ini:
                raise forms.ValidationError("A data de fim deve ser posterior à data de início.")
            if self.ano and (ini < self.ano.data_inicio or fim > self.ano.data_fim):
                raise forms.ValidationError(
                    f"As datas devem estar dentro do ano lectivo "
                    f"({self.ano.data_inicio:%d/%m/%Y} – {self.ano.data_fim:%d/%m/%Y})."
                )
        return d


class CalendarioForm(_EstiloMixin, forms.ModelForm):
    """Períodos (janelas) abertos/fechados no sistema."""
    class Meta:
        model = TenantConfiguracao
        fields = [
            "periodo_inscricao", "periodo_matricula", "periodo_confirmacao",
            "periodo_prova_1_trimestre", "periodo_prova_2_trimestre",
            "periodo_prova_3_trimestre", "periodo_exame", "periodo_recurso",
        ]
        labels = {
            "periodo_inscricao": "Inscrições abertas",
            "periodo_matricula": "Matrículas abertas",
            "periodo_confirmacao": "Confirmações abertas",
            "periodo_prova_1_trimestre": "Provas do 1.º trimestre",
            "periodo_prova_2_trimestre": "Provas do 2.º trimestre",
            "periodo_prova_3_trimestre": "Provas do 3.º trimestre",
            "periodo_exame": "Período de exames",
            "periodo_recurso": "Período de recurso",
        }
        help_texts = {
            "periodo_inscricao": "Candidatos podem submeter inscrições.",
            "periodo_matricula": "Secretaria pode matricular alunos.",
            "periodo_confirmacao": "Alunos transitados podem confirmar matrícula.",
            "periodo_prova_1_trimestre": "Permite lançar a prova trimestral (PT).",
            "periodo_prova_2_trimestre": "Permite lançar a prova trimestral (PT).",
            "periodo_prova_3_trimestre": "Permite lançar a prova trimestral (PT).",
            "periodo_exame": "Permite lançar notas de exame nacional.",
            "periodo_recurso": "Permite lançar notas de recurso.",
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estilizar()


class RegraAvaliacaoForm(_EstiloMixin, forms.ModelForm):
    class Meta:
        model = RegraAvaliacao
        exclude = ["ano_lectivo", "classe"]
        labels = {
            "nota_minima_positiva": "Nota mínima positiva",
            "nota_maxima": "Nota máxima",
            "peso_mac": "Peso MAC",
            "peso_pp": "Peso PP",
            "peso_pt": "Peso PT",
            "arredondar_unidades": "Arredondar médias às unidades",
            "peso_exame_na_nota_final": "Peso do exame (0 a 1)",
            "nota_minima_exame": "Nota mínima no exame",
            "max_negativas_transicao": "Máx. negativas para transitar",
            "classe_exame_exige_todas_positivas": "Classe com exame exige todas positivas",
            "limite_faltas_injustificadas_pct": "Limite de faltas injustificadas (%)",
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estilizar()

    def clean(self):
        d = super().clean()
        if d.get("nota_minima_positiva") is not None and d.get("nota_maxima") is not None:
            if d["nota_minima_positiva"] > d["nota_maxima"]:
                raise forms.ValidationError("A nota mínima positiva não pode exceder a nota máxima.")
        if all(d.get(k) is not None for k in ("peso_mac", "peso_pp", "peso_pt")):
            if d["peso_mac"] + d["peso_pp"] + d["peso_pt"] <= 0:
                raise forms.ValidationError("A soma dos pesos MAC + PP + PT deve ser maior que zero.")
        peso = d.get("peso_exame_na_nota_final")
        if peso is not None and not (0 <= peso <= 1):
            raise forms.ValidationError("O peso do exame deve estar entre 0 e 1 (ex.: 0,50).")
        pct = d.get("limite_faltas_injustificadas_pct")
        if pct is not None and not (0 < pct <= 100):
            raise forms.ValidationError("O limite de faltas deve estar entre 0 e 100%.")
        return d


class FinanceiroForm(_EstiloMixin, forms.ModelForm):
    dia_vencimento = forms.IntegerField(
        label="Dia de vencimento mensal",
        validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text="Entre 1 e 28, para valer em todos os meses.",
    )

    class Meta:
        model = ConfiguracaoFinanceira
        fields = ["valor_propina_padrao", "dia_vencimento",
                  "limite_bloqueio_meses", "taxa_matricula"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["limite_bloqueio_meses"].help_text = (
            "Saldo devedor ≥ propina × este número bloqueia a conta do aluno."
        )
        self._estilizar()


class IntegracoesForm(_EstiloMixin, forms.ModelForm):
    class Meta:
        model = TenantConfiguracao
        fields = [
            "email_smtp_host", "email_smtp_port", "email_remetente",
            "sms_provider", "sms_api_key",
            "multicaixa_entity", "multicaixa_api_key",
        ]
        widgets = {
            "sms_api_key": forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
            "multicaixa_api_key": forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for k in ("sms_api_key", "multicaixa_api_key"):
            self.fields[k].required = False
            self.fields[k].help_text = "Deixe em branco para manter a chave actual."
        self._estilizar()

    # Chaves nunca são reapresentadas; em branco = manter.
    def clean_sms_api_key(self):
        return self.cleaned_data.get("sms_api_key") or self.instance.sms_api_key

    def clean_multicaixa_api_key(self):
        return self.cleaned_data.get("multicaixa_api_key") or self.instance.multicaixa_api_key




