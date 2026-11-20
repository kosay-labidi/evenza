from django import forms

from .models import Prestataire, Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ("prestataire", "service", "montant")

    def clean(self):
        data = super().clean()
        p, s = data.get("prestataire"), data.get("service")
        if p and s and not p.services.filter(pk=s.pk).exists():
            raise forms.ValidationError(f"{p} ne propose pas le service « {s} ».")
        return data


class PrestataireForm(forms.ModelForm):
    class Meta:
        model = Prestataire
        fields = ("nom", "telephone", "email", "services")
        widgets = {"services": forms.CheckboxSelectMultiple}
