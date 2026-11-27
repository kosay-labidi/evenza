from django import forms
from django.contrib.auth import get_user_model

from .models import Avis, TypeBillet


class TransfertForm(forms.Form):
    """Choix du destinataire d'un transfert de billet : nom d'utilisateur ou e-mail (correspondance exacte,
    sans tenir compte des majuscules). Le modèle utilisateur est seulement lu (get_user_model)."""
    destinataire = forms.CharField(label="Nom d'utilisateur ou e-mail du destinataire", max_length=254,
                                   help_text="La personne doit déjà avoir un compte Évenza.")

    def clean_destinataire(self):
        saisie = self.cleaned_data["destinataire"].strip()
        User = get_user_model()
        actifs = User.objects.filter(is_active=True)
        par_nom = actifs.filter(username__iexact=saisie).first()          # le nom d'utilisateur est prioritaire
        if par_nom:
            return par_nom
        trouves = list(actifs.filter(email__iexact=saisie)[:2])
        if not trouves:
            raise forms.ValidationError("Aucun compte actif ne correspond à ce nom d'utilisateur ou à cet e-mail.")
        if len(trouves) > 1:
            raise forms.ValidationError("Plusieurs comptes utilisent cet e-mail : saisissez le nom d'utilisateur.")
        return trouves[0]


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

    def clean_quota(self):
        """Un quota ne peut pas être inférieur au nombre de billets déjà vendus (réservations confirmées)."""
        quota = self.cleaned_data.get("quota")
        if quota is not None and self.instance.pk and quota < self.instance.vendus:
            raise forms.ValidationError(
                f"{self.instance.vendus} billet(s) sont déjà vendus : le quota ne peut pas être inférieur à ce nombre.")
        return quota


class ModificationReservationForm(forms.Form):
    """Modification d'une réservation existante par son participant : type de billet et nombre de places.
    (Formulaire distinct de ``ReservationForm`` : le parcours de réservation n'est pas touché.)"""
    type_billet = forms.ModelChoiceField(queryset=TypeBillet.objects.none(), empty_label=None, required=False,
                                         label="Type de billet")
    quantite = forms.TypedChoiceField(choices=[(i, i) for i in range(1, 11)], coerce=int, label="Nombre de places")

    def __init__(self, *args, inscription, **kwargs):
        super().__init__(*args, **kwargs)
        self.inscription = inscription
        types = inscription.evenement.types_billet.all()
        self.fields["type_billet"].queryset = types
        self.fields["type_billet"].required = types.exists()
        if not types.exists():
            del self.fields["type_billet"]                   # événement sans types : prix de l'événement
        if not self.is_bound:
            self.initial.update(type_billet=inscription.type_billet_id, quantite=inscription.quantite)
