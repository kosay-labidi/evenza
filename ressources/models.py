from django.core.exceptions import ValidationError
from django.db import models

from evenements.models import Evenement


class Ressource(models.Model):
    class Type(models.TextChoices):
        SALLE = "SALLE", "Salle"
        MATERIEL = "MATERIEL", "Matériel"
        VEHICULE = "VEHICULE", "Véhicule"

    nom = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    quantite = models.PositiveIntegerField("quantité", default=1, help_text="Nombre d'unités disponibles")

    class Meta:
        ordering = ["type", "nom"]

    def __str__(self):
        return f"{self.nom} ×{self.quantite}"


class Affectation(models.Model):
    ressource = models.ForeignKey(Ressource, on_delete=models.PROTECT, related_name="affectations")
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="affectations")
    debut = models.DateTimeField("début")
    fin = models.DateTimeField()
    quantite = models.PositiveIntegerField("quantité", default=1)

    class Meta:
        ordering = ["debut"]

    def __str__(self):
        return f"{self.ressource.nom} ×{self.quantite} → {self.evenement}"

    def clean(self):
        from .services import verifier_conflit
        if self.debut and self.fin and self.fin <= self.debut:
            raise ValidationError({"fin": "La fin doit être après le début."})
        if self.ressource_id and self.debut and self.fin:
            verifier_conflit(self)
