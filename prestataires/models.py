from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from evenements.models import Evenement


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


class Prestataire(models.Model):
    compte = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="prestataire")
    nom = models.CharField(max_length=120)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    services = models.ManyToManyField(Service, related_name="prestataires")

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Reservation(models.Model):
    """Association Événement–Prestataire, porteuse d'attributs (montant, statut)."""

    class Statut(models.TextChoices):
        DEMANDEE = "DEMANDEE", "Demandée"
        CONFIRMEE = "CONFIRMEE", "Confirmée"
        ANNULEE = "ANNULEE", "Annulée"

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
