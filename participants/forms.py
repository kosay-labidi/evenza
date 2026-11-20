from django import forms

from .models import Avis, TypeBillet


class AvisForm(forms.ModelForm):
    class Meta:
        model = Avis
        fields = ("note", "commentaire")
        widgets = {"note": forms.NumberInput(attrs={"min": 1, "max": 5}), "commentaire": forms.Textarea(attrs={"rows": 3})}


class CheckinForm(forms.Form):
    code = forms.CharField(label="Code du billet", help_text="Les 8 premiers caractères suffisent (ex. 3F2A9C1B).")

    def clean_code(self):
        """Normalise le code (sans tirets ni espaces, en minuscules) et exige au moins 8 caractères hexadécimaux."""
        import re
        code = re.sub(r"[\s-]", "", self.cleaned_data["code"]).lower()
        if not re.fullmatch(r"[0-9a-f]{8,32}", code):
            raise forms.ValidationError("Code invalide : saisissez au moins les 8 caractères du billet (0-9, A-F).")
        return code


class ReservationForm(forms.Form):
    """Étape 1 de la réservation : type de billet et nombre de places."""
    type_billet = forms.ModelChoiceField(queryset=TypeBillet.objects.none(), widget=forms.RadioSelect, empty_label=None,
                                         label="Type de billet", required=False)
    quantite = forms.TypedChoiceField(choices=[(i, i) for i in range(1, 11)], coerce=int, initial=1, label="Nombre de places")

    def __init__(self, *args, evenement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.evenement = evenement
        types = evenement.types_billet.all()
        self.fields["type_billet"].queryset = types
        self.fields["type_billet"].required = types.exists()
        if types.exists() and not self.is_bound:
            self.initial["type_billet"] = types.first().pk

    def clean(self):
        data = super().clean()
        t, q = data.get("type_billet"), data.get("quantite") or 1
        if t and t.restants is not None and q > t.restants:
            raise forms.ValidationError(f"Il ne reste que {t.restants} billet(s) « {t.nom} ».")
        data["prix_unitaire"] = t.prix if t else self.evenement.prix
        data["total"] = data["prix_unitaire"] * q
        return data


class TypeBilletForm(forms.ModelForm):
    class Meta:
        model = TypeBillet
        fields = ("nom", "description", "prix", "quota")
