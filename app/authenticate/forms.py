from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _


class EstiloCampoMixin:
    """Aplica a classe CSS a todos os campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "campo")


class RecuperarSenhaForm(EstiloCampoMixin, PasswordResetForm):
    email = forms.EmailField(
        label=_("E-mail"),
        max_length=254,
        widget=forms.EmailInput(attrs={
            "autocomplete": "email",
            "placeholder": "seu@email.com",
            "autofocus": True,
        }),
    )


class DefinirNovaSenhaForm(EstiloCampoMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = _("Nova senha")
        self.fields["new_password2"].label = _("Confirmar nova senha")
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password", "autofocus": True})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})