from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Utilisateur


class InscriptionCompteForm(UserCreationForm):
    """Création de compte : seuls les rôles publics sont proposés."""
    role = forms.ChoiceField(choices=[
        (Utilisateur.Role.PARTICIPANT, "Participant"),
        (Utilisateur.Role.ORGANISATEUR, "Organisateur"),
        (Utilisateur.Role.CLIENT, "Client"),
    ])

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["first_name"].label = "Prénom"
        self.fields["last_name"].label = "Nom"
        ph = {"username": "ex. sara.benali", "email": "vous@exemple.tn", "telephone": "ex. 22 123 456", "first_name": "Sara", "last_name": "Ben Ali"}
        for k, v in ph.items():
            self.fields[k].widget.attrs["placeholder"] = v
        for k in ("first_name", "last_name", "username", "email", "password1", "password2"):
            self.fields[k].widget.attrs["required"] = True

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Utilisateur.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte utilise déjà cette adresse e-mail.")
        return email


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ("first_name", "last_name", "email", "telephone")


# ---- gestion des utilisateurs par l'administrateur ----
class UtilisateurCreationAdminForm(UserCreationForm):
    """Ajout d'un compte par l'admin : tous les rôles sont proposés."""

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].label = "Prénom"
        self.fields["last_name"].label = "Nom"
        self.fields["is_active"].label = "Compte actif"

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email and Utilisateur.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte utilise déjà cette adresse e-mail.")
        return email


class UtilisateurAdminForm(forms.ModelForm):
    """Modification d'un compte par l'admin (le mot de passe se change via « Mot de passe oublié »)."""

    class Meta:
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role", "is_active")
        labels = {"first_name": "Prénom", "last_name": "Nom", "is_active": "Compte actif"}

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email and Utilisateur.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Un compte utilise déjà cette adresse e-mail.")
        return email
