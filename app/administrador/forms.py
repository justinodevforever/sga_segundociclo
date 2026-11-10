
from django import forms
from app.db.models import *
from django.db.models import Q
import string, secrets

from django.shortcuts import get_list_or_404

from django import forms
from django.utils import timezone


PROVINCIAS_ANGOLA = [
    ('', 'Selecione a província…'),
    ('Bengo', 'Bengo'),
    ('Benguela', 'Benguela'),
    ('Bié', 'Bié'),
    ('Cabinda', 'Cabinda'),
    ('Cuando Cubango', 'Cuando Cubango'),
    ('Cuanza Norte', 'Cuanza Norte'),
    ('Cuanza Sul', 'Cuanza Sul'),
    ('Cunene', 'Cunene'),
    ('Huambo', 'Huambo'),
    ('Huíla', 'Huíla'),
    ('Luanda', 'Luanda'),
    ('Lunda Norte', 'Lunda Norte'),
    ('Lunda Sul', 'Lunda Sul'),
    ('Malanje', 'Malanje'),
    ('Moxico', 'Moxico'),
    ('Namibe', 'Namibe'),
    ('Uíge', 'Uíge'),
    ('Zaire', 'Zaire'),
]

class CriarDirectorForm(forms.Form):

    nome_completo = forms.CharField(
        max_length=2000,
        required=True,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Nome completo'})
    )

    bi = forms.CharField(
        max_length=14,
        min_length=14,
        required=True,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Nº de Bilhete'})
    )
    data_nascimento = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'class':'form-control-custom', 'type': 'date'})
    )
    genero = forms.ChoiceField(
        choices=Diretor.Genero.choices,
        required=True,
        widget=forms.Select(attrs={'class':'form-control-custom', 'placeholder': 'Preço anual'})
    )
    telefone = forms.CharField(
        required=True,
        max_length=9,
        min_length=9,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: 938 775 839'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: chitombi@gmail.com'})
    )
    endereco = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: Luena, Bairro 4 de Fevereio'})
    )
 
    def save(self):

        director = Diretor(
            nome_completo=self.cleaned_data.get('nome_completo'),
            bi=self.cleaned_data.get('bi'),
            genero=self.cleaned_data.get('genero'),
            data_nascimento=self.cleaned_data.get('data_nascimento'),
            telefone=self.cleaned_data.get('telefone'),
            email=self.cleaned_data.get('email'),
            endereco=self.cleaned_data.get('endereco'),
        )

        return director


class EditarDirectorForm(forms.Form):

    nome_completo = forms.CharField(
        max_length=2000,
        required=True,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Nome completo'})
    )



    bi = forms.CharField(
        max_length=14,
        min_length=14,
        required=True,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Nº de Bilhete'})
    )
    data_nascimento = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'class':'form-control-custom', 'type': 'date'})
    )
    genero = forms.ChoiceField(
        choices=Diretor.Genero.choices,
        required=True,
        widget=forms.Select(attrs={'class':'form-control-custom', 'placeholder': 'Preço anual'})
    )
    telefone = forms.CharField(
        required=True,
        max_length=9,
        min_length=9,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: 938 775 839'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: chitombi@gmail.com'})
    )
    endereco = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class':'form-control-custom', 'placeholder': 'Ex.: Luena, Bairro 4 de Fevereio'})
    )

    def __init__(self, *args, **kwargs):
        self.director = kwargs.pop('director', None)
        super().__init__(*args, **kwargs)


        if self.director:
            self.fields['nome_completo'].initial = self.director.nome_completo
            self.fields['bi'].initial = self.director.bi
            self.fields['genero'].initial = self.director.genero
            self.fields['data_nascimento'].initial = self.director.data_nascimento
            self.fields['telefone'].initial = self.director.telefone
            self.fields['email'].initial = self.director.email
            self.fields['endereco'].initial = self.director.endereco
 
    def save(self):

        self.director.nome_completo=self.cleaned_data.get('nome_completo')
        self.director.bi=self.cleaned_data.get('bi')
        self.director.genero=self.cleaned_data.get('genero')
        self.director.data_nascimento=self.cleaned_data.get('data_nascimento')
        self.director.telefone=self.cleaned_data.get('telefone')
        self.director.email=self.cleaned_data.get('email')

        return self.director



class UsuarioForm(forms.Form):
    


    nome_completo = forms.CharField(
        required=True, 
        widget= forms.TextInput(attrs={'id': 'nome_completo', 'placeholder': 'Nome completo'})
    )

    email = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={'id': 'email', 'placeholder': 'E-mail'})
    )

    username = forms.CharField(
        required=True,
        widget= forms.TextInput(attrs={'id': 'username', 'placeholder': 'Nome do usuário'})
    )

    password = forms.CharField(
        required=True,
        widget= forms.PasswordInput(attrs={'id': 'password', 'placeholder': 'Senha'})
    )

    is_active = forms.BooleanField(
        required=False,
        widget= forms.CheckboxInput()
    )

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        if self.usuario:

            self.fields['username'].initial = self.usuario.username
            self.fields['nome_completo'].initial = self.usuario.nome_completo
            self.fields['email'].initial = self.usuario.email
            self.fields['role'].initial = self.usuario.role


    def save(self):

        if self.usuario is None:

            usuario = Utilizador(
                username = self.cleaned_data['username'],
                nome_completo = self.cleaned_data['nome_completo'],
                role = self.cleaned_data['role'],
                email = self.cleaned_data['email'],
                is_active = True,
            )

            if self.cleaned_data['role'].nome == 1:
                usuario.is_staff = True
                usuario.is_superuser = True
            
            usuario.set_password(self.cleaned_data['password'])

            usuario.save()

            return usuario
        
        else:

            self.usuario.username = self.cleaned_data['username']
            self.usuario.nome_completo = self.cleaned_data['nome_completo']
            self.usuario.role = self.cleaned_data['role']
            self.usuario.email = self.cleaned_data['email']
            self.usuario.is_active = self.cleaned_data['is_active']

            if self.cleaned_data['role'].nome == 1:

                self.usuario.is_staff = True
                self.usuario.is_superuser = True

            else:
                self.usuario.is_staff = False
                self.usuario.is_superuser = False

            
            self.usuario.save()


            return self.usuario
        

