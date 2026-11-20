from django import forms

from evenements.forms import DT

from .models import Affectation, Ressource


class AffectationForm(forms.ModelForm):
    class Meta:
        model = Affectation
        fields = ("ressource", "quantite", "debut", "fin")
        widgets = {"debut": DT, "fin": DT}


class RessourceForm(forms.ModelForm):
    class Meta:
        model = Ressource
        fields = "__all__"
