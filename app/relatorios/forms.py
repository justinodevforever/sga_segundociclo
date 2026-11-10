from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from app.db.models import (AnoLectivo, Aluno, Classe, Curso, Disciplina, Funcionario,
                        Matricula, Turma)

W = {"class": "form-control-custom"}
VAZIO = [("", "Todos")]


class TurmaField(forms.ModelChoiceField):
    def label_from_instance(self, t):
        return (f"{t.classe.designacao}.ª {t.designacao} - {t.curso.nome_abreviado or t.curso.nome} "
                f"- {t.get_periodo_display()} ({t.ano_lectivo})")


class ClasseField(forms.ModelChoiceField):
    def label_from_instance(self, c):
        return f"{c.designacao}.ª Classe"


class FiltroRelatorioForm(forms.Form):
    ano_lectivo = forms.ModelChoiceField(AnoLectivo.objects.all(), required=False, label="Ano lectivo",
                                         empty_label="Seleccione", widget=forms.Select(attrs=W))
    trimestre = forms.ChoiceField(choices=[("", "Todos"), ("1", "1.º Trimestre"), ("2", "2.º Trimestre"),
                                           ("3", "3.º Trimestre")], required=False, label="Trimestre",
                                  widget=forms.Select(attrs=W))
    curso = forms.ModelChoiceField(Curso.objects.filter(activo=True), required=False, label="Curso",
                                   empty_label="Todos", widget=forms.Select(attrs=W))
    classe = ClasseField(Classe.objects.order_by("designacao"), required=False, label="Classe",
                         empty_label="Todas", widget=forms.Select(attrs=W))
    turma = TurmaField(Turma.objects.none(), required=False, label="Turma",
                       empty_label="Seleccione", widget=forms.Select(attrs=W))
    disciplina = forms.ModelChoiceField(Disciplina.objects.filter(activo=True).order_by("nome"), required=False,
                                        label="Disciplina", empty_label="Todas", widget=forms.Select(attrs=W))
    professor = forms.ModelChoiceField(
        Funcionario.objects.filter(tipo_funcionario="Professor").order_by("nome_completo"),
        required=False, label="Professor", empty_label="Todos", widget=forms.Select(attrs=W))
    genero = forms.ChoiceField(choices=VAZIO + [("M", "Masculino"), ("F", "Feminino")], required=False,
                               label="Género", widget=forms.Select(attrs=W))
    turno = forms.ChoiceField(choices=VAZIO + list(Turma.Turno.choices), required=False, label="Turno",
                              widget=forms.Select(attrs=W))
    status_matricula = forms.ChoiceField(choices=VAZIO + list(Matricula.Status.choices), required=False,
                                         label="Estado da matrícula", widget=forms.Select(attrs=W))
    situacao = forms.ChoiceField(choices=VAZIO + list(Matricula.Situacao.choices), required=False,
                                 label="Situação final", widget=forms.Select(attrs=W))
    status_funcionario = forms.ChoiceField(choices=VAZIO + list(Funcionario.Status.choices), required=False,
                                           label="Estado do funcionário", widget=forms.Select(attrs=W))
    tipo_funcionario = forms.ChoiceField(choices=VAZIO + list(Funcionario.TipoFuncionario.choices), required=False,
                                         label="Tipo de funcionário", widget=forms.Select(attrs=W))
    data_inicio = forms.DateField(required=False, label="Data de início",
                                  widget=forms.DateInput(attrs={**W, "type": "date"}))
    data_fim = forms.DateField(required=False, label="Data de fim",
                               widget=forms.DateInput(attrs={**W, "type": "date"}))
    limite = forms.IntegerField(required=False, min_value=0, label="Limite", widget=forms.NumberInput(attrs=W))
    aluno = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, campos=(), obrigatorios=(), rotulos=None, **kw):
        super().__init__(*args, **kw)
        for nome in list(self.fields):
            if nome not in campos:
                del self.fields[nome]
        for nome in obrigatorios:
            if nome in self.fields:
                self.fields[nome].required = True
        for nome, rotulo in (rotulos or {}).items():
            if nome in self.fields:
                self.fields[nome].label = rotulo
        if "turma" in self.fields:
            qs = Turma.objects.select_related("ano_lectivo", "curso", "classe").order_by(
                "-ano_lectivo__data_inicio", "classe__designacao", "designacao")
            ano = (self.data.get("ano_lectivo") if self.is_bound
                   else getattr(self.initial.get("ano_lectivo"), "pk", None))
            if ano:
                try:
                    qs = qs.filter(ano_lectivo_id=ano)
                    list(qs[:1])
                except (ValidationError, ValueError):
                    qs = Turma.objects.none()
            self.fields["turma"].queryset = qs

    def clean_aluno(self):
        v = self.cleaned_data.get("aluno")
        if not v:
            return None
        try:
            return Aluno.objects.get(pk=v)
        except (Aluno.DoesNotExist, ValueError, ValidationError):
            raise forms.ValidationError("Aluno inválido.")

    def resumo(self):
        """Texto com os filtros aplicados (cabeçalho dos relatórios)."""
        partes = []
        for nome, val in self.cleaned_data.items():
            if val in (None, "") or nome == "aluno":
                continue
            campo = self.fields[nome]
            if isinstance(campo, forms.ModelChoiceField):
                val = campo.label_from_instance(val)
            elif isinstance(campo, forms.ChoiceField):
                val = dict(campo.choices).get(val, val)
            elif isinstance(val, date):
                val = val.strftime("%d/%m/%Y")
            partes.append(f"{campo.label}: {val}")
        return "  |  ".join(partes)