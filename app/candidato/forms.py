import re
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from app.db.models import Candidato, Curso, Inscricao, Periodo

BI_RE = re.compile(r"^\d{9}[A-Z]{2}\d{3}$")
TEL_RE = re.compile(r"^(\+244)?9\d{8}$")

PROVINCIAS = [
    "Bengo", "Benguela", "Bié", "Cabinda", "Cuando", "Cubango", "Cuanza Norte",
    "Cuanza Sul", "Cunene", "Huambo", "Huíla", "Icolo e Bengo", "Luanda",
    "Lunda Norte", "Lunda Sul", "Malanje", "Moxico", "Moxico Leste", "Namibe",
    "Uíge", "Zaire",
]


def _normalizar_bi(valor: str) -> str:
    return re.sub(r"\s+", "", valor or "").upper()


class ConsultaForm(forms.Form):
    bi = forms.CharField(max_length=20, label="Nº do Bilhete de Identidade")
    data_nascimento = forms.DateField(
        label="Data de nascimento", widget=forms.DateInput(attrs={"type": "date"})
    )

    def clean_bi(self):
        return _normalizar_bi(self.cleaned_data["bi"])


class PreInscricaoForm(forms.Form):
    # Passo 1 — Dados pessoais
    nome_completo = forms.CharField(max_length=200, label="Nome completo")
    data_nascimento = forms.DateField(
        label="Data de nascimento", widget=forms.DateInput(attrs={"type": "date"})
    )
    genero = forms.ChoiceField(choices=[("", "Seleccione")] + list(Candidato.Genero.choices), label="Género")
    necessidades_especiais = forms.CharField(
        required=False, label="Necessidades especiais (se aplicável)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    # Passo 2 — Filiação e documento
    nome_pai = forms.CharField(max_length=200, label="Nome do pai")
    nome_mae = forms.CharField(max_length=200, label="Nome da mãe")
    bi = forms.CharField(max_length=20, label="Nº do Bilhete de Identidade",
                         help_text="Ex.: 004567890LA041")
    emitido_em = forms.CharField(max_length=200, label="BI emitido em (local)")
    data_emissao_bi = forms.CharField(max_length=200, label="Data de emissão do BI",
                                      widget=forms.DateInput(attrs={"type": "date"}))
    data_expiracao_bi = forms.DateField(required=False, label="Data de expiração do BI",
                                        widget=forms.DateInput(attrs={"type": "date"}))
    # Passo 3 — Contactos e residência
    telefone = forms.CharField(max_length=20, label="Telefone", help_text="Ex.: 923 456 789")
    email = forms.EmailField(required=False, label="E-mail")
    naturalidade = forms.CharField(max_length=100, label="Naturalidade")
    provincia = forms.ChoiceField(choices=[("", "Seleccione")] + [(p, p) for p in PROVINCIAS], label="Província")
    municipio = forms.CharField(max_length=50, label="Município")
    bairro = forms.CharField(max_length=100, required=False, label="Bairro")
    # Passo 4 — Curso
    curso = forms.ModelChoiceField(queryset=Curso.objects.none(), empty_label="Seleccione o curso", label="Curso pretendido")
    periodo = forms.ModelChoiceField(queryset=Periodo.objects.all(), empty_label="Seleccione o período", label="Período")
    aceito = forms.BooleanField(label="Declaro que os dados são verdadeiros e aceito ser contactado pela escola.")

    STEPS = [
        ("Dados pessoais", ["nome_completo", "data_nascimento", "genero", "necessidades_especiais"]),
        ("Filiação e BI", ["nome_pai", "nome_mae", "bi", "emitido_em", "data_emissao_bi", "data_expiracao_bi"]),
        ("Contactos e residência", ["telefone", "email", "naturalidade", "provincia", "municipio", "bairro"]),
        ("Curso e confirmação", ["curso", "periodo", "aceito"]),
    ]

    def __init__(self, *args, ano_lectivo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ano_lectivo = ano_lectivo
        self.fields["curso"].queryset = Curso.objects.filter(activo=True).order_by("nome")
        for name, f in self.fields.items():
            if not isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault("class", "inp")
            f.widget.attrs["autocomplete"] = "off"

    def steps(self):
        """Lista de passos com BoundFields e indicação de erros (para o template)."""
        out = []
        for i, (titulo, nomes) in enumerate(self.STEPS, 1):
            campos = [self[n] for n in nomes]
            out.append({"n": i, "titulo": titulo, "campos": campos,
                        "tem_erro": any(c.errors for c in campos)})
        return out

    def clean_bi(self):
        bi = _normalizar_bi(self.cleaned_data["bi"])
        if not BI_RE.match(bi):
            raise ValidationError("BI inválido. Use o formato 9 dígitos + 2 letras + 3 dígitos.")
        return bi

    def clean_telefone(self):
        tel = re.sub(r"[\s-]", "", self.cleaned_data["telefone"])
        if not TEL_RE.match(tel):
            raise ValidationError("Telefone inválido. Ex.: 923456789.")
        return tel

    def clean_data_nascimento(self):
        d = self.cleaned_data["data_nascimento"]
        if d >= date.today():
            raise ValidationError("A data de nascimento não pode ser futura.")
        return d

    def clean(self):
        data = super().clean()
        bi, curso = data.get("bi"), data.get("curso")
        if bi and curso and self.ano_lectivo:
            if Inscricao.objects.filter(candidato__bi=bi, ano_lectivo=self.ano_lectivo, curso=curso).exists():
                raise ValidationError("Já existe uma pré-inscrição com este BI para o curso escolhido. "
                                      "Consulte o progresso na página inicial.")
        return data

    @transaction.atomic
    def save(self):
        d = self.cleaned_data
        candidato = Candidato.objects.filter(bi=d["bi"]).first()
        if candidato is None:
            candidato = Candidato.objects.create(
                nome_completo=d["nome_completo"], bi=d["bi"], data_nascimento=d["data_nascimento"],
                genero=d["genero"], telefone=d["telefone"], email=d.get("email") or None,
                nome_pai=d["nome_pai"], nome_mae=d["nome_mae"], emitido_em=d["emitido_em"],
                data_emissao_bi=d["data_emissao_bi"], data_expiracao_bi=d.get("data_expiracao_bi"),
                necessidades_especiais=d.get("necessidades_especiais", ""),
                naturalidade=d["naturalidade"], provincia=d["provincia"],
                municipio=d["municipio"], bairro=d.get("bairro") or None,
            )
        return Inscricao.objects.create(
            candidato=candidato, periodo=d["periodo"], ano_lectivo=self.ano_lectivo,
            curso=d["curso"], status=Inscricao.Status.PENDENTE,
        )
