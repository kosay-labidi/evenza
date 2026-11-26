from django import forms

from evenements.forms import DT

from .models import Seance


class SeanceForm(forms.ModelForm):
    class Meta:
        model = Seance
        fields = ("titre", "description", "date")
        widgets = {
            "titre": forms.TextInput(attrs={"maxlength": 30}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "date": DT,
        }

    def clean_date(self):
        date = self.cleaned_data["date"]
        evenement = self.instance.evenement
        if date < evenement.date_debut or date > evenement.date_fin:
            raise forms.ValidationError("La séance doit se dérouler pendant les dates de l’événement.")
        return date
