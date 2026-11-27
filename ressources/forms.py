from django import forms
from django.db.models import Q

from evenements.forms import DT

from .models import Affectation, Ressource


class AffectationForm(forms.ModelForm):
    class Meta:
        model = Affectation
        fields = ("ressource", "quantite", "debut", "fin")
        widgets = {"debut": DT, "fin": DT}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Une ressource en maintenance ou hors service ne peut pas être affectée à un événement
        # (on garde celle déjà choisie pour pouvoir modifier une ancienne affectation).
        filtre = Q(etat=Ressource.Etat.DISPONIBLE)
        if self.instance.pk:
            filtre |= Q(pk=self.instance.ressource_id)
        self.fields["ressource"].queryset = Ressource.objects.filter(filtre)


class RessourceForm(forms.ModelForm):
    class Meta:
        model = Ressource
        fields = "__all__"
