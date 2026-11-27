from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse

from evenements.models import Evenement

# ---- Images fixes du module ----
# Les images définitives vont dans prestataires/static/prestataires/img/ (.webp ou .jpg).
# Tant qu'un fichier manque, on affiche l'image temporaire de static/img/ indiquée ici.
IMAGES_TEMPORAIRES = {
    "bandeau": "img/categories/gala.jpg",
    "services/traiteur": "img/categories/mariage.jpg",
    "services/son": "img/categories/concert.jpg",
    "services/lumiere": "img/categories/festival.jpg",
    "services/decor": "img/categories/gala.jpg",
    "services/photo": "img/categories/conference.jpg",
    "services/securite": "img/hero/terrasse.jpg",
}


def image_prestataires(nom):
    """URL de prestataires/img/<nom>.webp (ou .jpg) si le fichier existe, sinon de l'image temporaire."""
    for ext in ("webp", "jpg"):
        chemin = f"prestataires/img/{nom}.{ext}"
        if finders.find(chemin):
            return static(chemin)
    return static(IMAGES_TEMPORAIRES.get(nom, IMAGES_TEMPORAIRES["bandeau"]))


class Service(models.Model):
    class Type(models.TextChoices):
        TRAITEUR = "TRAITEUR", "Traiteur"
        SON = "SON", "Son"
        LUMIERE = "LUMIERE", "Lumière"
        DECOR = "DECOR", "Décoration"
        PHOTO = "PHOTO", "Photo / vidéo"
        SECURITE = "SECURITE", "Sécurité"

    nom = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=Type.choices)

    class Meta:
        ordering = ["type", "nom"]

    def __str__(self):
        return f"{self.nom} ({self.get_type_display()})"

    @property
    def couverture_url(self):
        """Photo d'ambiance du type de service (ex. services/lumiere.webp)."""
        return image_prestataires(f"services/{self.type.lower()}")


class Prestataire(models.Model):
    compte = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="prestataire")
    nom = models.CharField(max_length=120)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    services = models.ManyToManyField(Service, related_name="prestataires")
    photo = models.ImageField("photo ou logo", upload_to="prestataires/", blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    @property
    def service_principal(self):
        """Premier service (utilise le prefetch_related("services") s'il existe)."""
        return next(iter(self.services.all()), None)

    @property
    def couverture_url(self):
        """Image de couverture : celle du premier service, sinon le bandeau du module."""
        svc = self.service_principal
        return svc.couverture_url if svc else image_prestataires("bandeau")

    def get_absolute_url(self):
        return reverse("prestataires:detail", args=[self.pk])

    @property
    def initiales(self):
        """Deux premières initiales du nom (ex. « Sound & Light Tunis » → « SL »), pour l'avatar."""
        mots = [m for m in self.nom.split() if m[:1].isalnum()]
        return "".join(m[0] for m in mots[:2]).upper() or "?"


class Reservation(models.Model):
    """Association Événement–Prestataire, porteuse d'attributs (montant, statut)."""

    class Statut(models.TextChoices):
        DEMANDEE = "DEMANDEE", "Demandée"
        CONFIRMEE = "CONFIRMEE", "Confirmée"
        ANNULEE = "ANNULEE", "Annulée"

    # Transitions de statut autorisées (règle métier US 4.4.2).
    # Une réservation annulée est définitive : il faut en créer une nouvelle.
    TRANSITIONS = {
        Statut.DEMANDEE: {Statut.CONFIRMEE, Statut.ANNULEE},
        Statut.CONFIRMEE: {Statut.ANNULEE},
        Statut.ANNULEE: set(),
    }

    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="reservations")
    prestataire = models.ForeignKey(Prestataire, on_delete=models.PROTECT, related_name="reservations")
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    montant = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.DEMANDEE)
    date_demande = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "réservation"
        ordering = ["-date_demande"]

    def __str__(self):
        return f"{self.prestataire} → {self.evenement}"

    def clean(self):
        """Règles métier (US 4.3.3) : montant strictement positif, service proposé par le prestataire."""
        erreurs = {}
        if self.montant is not None and self.montant <= 0:
            erreurs["montant"] = "Le montant doit être strictement supérieur à 0."
        if self.prestataire_id and self.service_id and \
                not self.prestataire.services.filter(pk=self.service_id).exists():
            erreurs["service"] = f"{self.prestataire} ne propose pas le service « {self.service} »."
        if erreurs:
            raise ValidationError(erreurs)

    # ---- Transitions de statut (US 4.4.2) ----
    def peut_passer_a(self, statut):
        return statut in self.TRANSITIONS.get(self.statut, set())

    @property
    def peut_confirmer(self):
        return self.peut_passer_a(self.Statut.CONFIRMEE)

    @property
    def peut_annuler(self):
        return self.peut_passer_a(self.Statut.ANNULEE)

    def changer_statut(self, statut):
        """Applique la transition si elle est autorisée, sinon lève ValidationError."""
        if not self.peut_passer_a(statut):
            libelle = dict(self.Statut.choices).get(statut, statut)
            raise ValidationError(f"Impossible de passer une réservation « {self.get_statut_display()} » "
                                  f"au statut « {libelle} ».")
        self.statut = statut
        self.save(update_fields=["statut"])
