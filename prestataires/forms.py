from django import forms
from django.core.files.uploadedfile import UploadedFile

from . import telephone
from .models import Prestataire, Reservation

PHOTO_TAILLE_MAX = 3 * 1024 * 1024          # 3 Mo
PHOTO_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


class ReservationForm(forms.ModelForm):
    """Réservation d'un prestataire (US 4.3).

    Les règles métier (montant > 0, service proposé par le prestataire) sont dans
    ``Reservation.clean()`` : elles s'appliquent aussi dans l'admin Django.
    """

    class Meta:
        model = Reservation
        fields = ("prestataire", "service", "montant")
        widgets = {"montant": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"})}
        labels = {"prestataire": "Prestataire", "service": "Service", "montant": "Montant (DT)"}
        help_texts = {"service": "Le prestataire choisi doit proposer ce service.",
                      "montant": "En dinars, strictement supérieur à 0."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Liste déroulante : seulement les prestataires approuvés. La règle elle-même est dans
        # Reservation.clean() (un identifiant forgé dans l'URL ou le POST est donc refusé aussi).
        self.fields["prestataire"].queryset = Prestataire.objects.approuves()
        self.fields["prestataire"].error_messages["invalid_choice"] = (
            "Ce prestataire n'est pas approuvé par l'administrateur : il ne peut pas être réservé.")


class PrestataireForm(forms.ModelForm):
    """Ajout / modification d'un prestataire (US 4.1, 4.6)."""

    class Meta:
        model = Prestataire
        fields = ("nom", "photo", "telephone", "email", "services")
        widgets = {"services": forms.CheckboxSelectMultiple,
                   "photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})}
        labels = {"nom": "Nom", "photo": "Photo ou logo", "telephone": "Téléphone", "email": "E-mail",
                  "services": "Services proposés"}
        error_messages = {"services": {"required": "Choisissez au moins un service."}}
        help_texts = {"nom": "Nom commercial affiché sur les cartes.",
                      "photo": "Facultatif. JPG, PNG ou WebP, 3 Mo maximum. Sans photo, les initiales s'affichent.",
                      "telephone": "8 chiffres, ex. 22 123 456",
                      "email": "Adresse unique : deux prestataires ne peuvent pas partager le même e-mail.",
                      "services": "Cochez au moins un service proposé."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True          # obligatoire côté formulaire (sans migration)
        self.fields["services"].required = True
        # Téléphone : obligatoire, format tunisien (vérifié dans clean_telephone ; aussi dans l'admin Django).
        tel = self.fields["telephone"]
        tel.required = True
        tel.error_messages["required"] = telephone.MSG_LONGUEUR
        tel.widget.input_type = "tel"
        tel.widget.attrs.update({"inputmode": "numeric", "autocomplete": "tel", "placeholder": "22 123 456",
                                 "maxlength": telephone.LONGUEUR_MAX_SAISIE, "pattern": telephone.PATTERN_HTML,
                                 "title": "8 chiffres, ex. 22 123 456", "data-pr-tel": ""})

    def clean_telephone(self):
        """Format tunisien, enregistré « 22 123 456 », unique parmi les prestataires (US 4.1.3)."""
        numero = telephone.normaliser(self.cleaned_data.get("telephone", ""))
        autres = Prestataire.objects.exclude(telephone="")
        if self.instance.pk:
            autres = autres.exclude(pk=self.instance.pk)
        # Comparaison sur les 8 chiffres : les anciens numéros saisis sans format sont aussi détectés.
        cle = telephone.cle(numero)
        if any(telephone.cle(t) == cle for t in autres.values_list("telephone", flat=True)):
            raise forms.ValidationError(telephone.MSG_DOUBLON, code="doublon")
        return numero

    def clean_photo(self):
        """Nouvelle photo : format courant et 3 Mo maximum (Pillow vérifie déjà que c'est une image)."""
        photo = self.cleaned_data.get("photo")
        if isinstance(photo, UploadedFile):
            if photo.name.rsplit(".", 1)[-1].lower() not in PHOTO_EXTENSIONS:
                raise forms.ValidationError("Format non accepté : choisissez une image JPG, PNG ou WebP.")
            if photo.size > PHOTO_TAILLE_MAX:
                raise forms.ValidationError("Image trop lourde : 3 Mo maximum.")
        return photo

    def clean_email(self):
        """E-mail unique sans tenir compte des majuscules (US 4.1.3)."""
        email = self.cleaned_data["email"].strip().lower()
        doublons = Prestataire.objects.filter(email__iexact=email)
        if self.instance.pk:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError("Un prestataire utilise déjà cette adresse e-mail.")
        return email


class PrestataireAdminForm(PrestataireForm):
    """Même validation dans l'admin, mais avec le widget filter_horizontal de l'admin."""

    class Meta(PrestataireForm.Meta):
        fields = "__all__"
        widgets = {}


class RefusPrestataireForm(forms.Form):
    """Refus d'un prestataire en attente : le motif est obligatoire (il est montré à l'organisateur)."""
    motif = forms.CharField(label="Motif du refus", max_length=1000, strip=True,
                            widget=forms.Textarea(attrs={"rows": 3}),
                            error_messages={"required": "Indiquez le motif du refus."})
