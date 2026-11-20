from django import forms
from django.utils import timezone

from .models import Evenement, Lieu

DT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class EvenementForm(forms.ModelForm):
    class Meta:
        model = Evenement
        fields = ("titre", "description", "categorie", "lieu", "date_debut", "date_fin", "capacite", "prix", "affiche")
        widgets = {"date_debut": DT, "date_fin": DT, "description": forms.Textarea(attrs={"rows": 4})}

    def clean_date_debut(self):
        d = self.cleaned_data.get("date_debut")
        # Seulement si la date est saisie ou modifiée : on peut encore éditer un événement en cours.
        if d and "date_debut" in self.changed_data and d < timezone.now():
            raise forms.ValidationError("La date de début ne peut pas être dans le passé.")
        return d


class LieuForm(forms.ModelForm):
    class Meta:
        model = Lieu
        fields = "__all__"


class RechercheForm(forms.Form):
    q = forms.CharField(required=False, label="Recherche")
    categorie = forms.IntegerField(required=False, widget=forms.HiddenInput)
