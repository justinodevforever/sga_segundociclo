import os

from django import forms
from django.utils.translation import gettext_lazy as _

from app.db.models import Aluno, Disciplina, DocumentoAluno, Reclamacao, Trimestre


class StyledFormMixin:
    """Aplica as classes CSS do portal a todos os campos."""

    def _estilizar(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.ClearableFileInput):
                w.attrs["class"] = "form-control"
            elif isinstance(w, forms.Select):
                w.attrs["class"] = "form-control"
            else:
                w.attrs["class"] = "form-control"


class AlunoPerfilForm(StyledFormMixin, forms.ModelForm):
    """O estudante só pode alterar dados de contacto e a foto."""

    class Meta:
        model = Aluno
        fields = ["telefone", "email", "endereco", "bairro", "foto"]
        widgets = {"endereco": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estilizar()

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and hasattr(foto, "size") and foto.size > 2 * 1024 * 1024:
            raise forms.ValidationError(_("A foto não pode exceder 2 MB."))
        return foto


class DocumentoForm(StyledFormMixin, forms.ModelForm):
    EXTENSOES = {".pdf", ".jpg", ".jpeg", ".png"}

    class Meta:
        model = DocumentoAluno
        fields = ["tipo_documento", "titulo", "arquivo"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estilizar()

    def clean_arquivo(self):
        arq = self.cleaned_data["arquivo"]
        if os.path.splitext(arq.name)[1].lower() not in self.EXTENSOES:
            raise forms.ValidationError(_("Formatos aceites: PDF, JPG ou PNG."))
        if arq.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("O ficheiro não pode exceder 5 MB."))
        return arq


class ReclamacaoForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Reclamacao
        fields = ["disciplina", "trimestre", "motivo"]
        widgets = {"motivo": forms.Textarea(attrs={"rows": 4, "placeholder": "Explique porque pede a revisão da nota."})}

    def __init__(self, *a, matricula=None, **kw):
        super().__init__(*a, **kw)
        self.matricula = matricula
        self.fields["disciplina"].queryset = Disciplina.objects.filter(
            resultadotrimestral__matricula=matricula
        ).distinct().order_by("nome")
        self.fields["trimestre"].queryset = Trimestre.objects.filter(ano_lectivo=matricula.ano_lectivo)
        self.fields["trimestre"].required = True
        self._estilizar()

    def clean_motivo(self):
        motivo = self.cleaned_data["motivo"].strip()
        if len(motivo) < 15:
            raise forms.ValidationError(_("Descreva o motivo com pelo menos 15 caracteres."))
        return motivo

    def clean(self):
        data = super().clean()
        disc, tri = data.get("disciplina"), data.get("trimestre")
        if disc and tri and Reclamacao.objects.filter(
            matricula=self.matricula, disciplina=disc, trimestre=tri, estado=Reclamacao.Estado.PENDENTE
        ).exists():
            raise forms.ValidationError(_("Já existe uma reclamação pendente para esta disciplina e trimestre."))
        return data
