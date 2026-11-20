from django import forms

from evenements.forms import DT

from .models import Intervenant, Seance


class SeanceForm(forms.ModelForm):
    class Meta:
        model = Seance
        fields = ("titre", "debut", "fin", "salle", "intervenants")
        widgets = {"debut": DT, "fin": DT, "intervenants": forms.CheckboxSelectMultiple}


class IntervenantForm(forms.ModelForm):
    class Meta:
        model = Intervenant
        fields = "__all__"
