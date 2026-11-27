from django import forms
from django.core.files.uploadedfile import UploadedFile

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
