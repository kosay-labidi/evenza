from django.core.exceptions import ValidationError
from django.db import models

from evenements.models import Evenement


class Intervenant(models.Model):
    nom = models.CharField(max_length=120)
    specialite = models.CharField("spécialité", max_length=120, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Seance(models.Model):
    """Composition : une séance n'existe pas sans son événement (CASCADE)."""
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="seances")
    titre = models.CharField(max_length=150)
    debut = models.DateTimeField("début")
    fin = models.DateTimeField()
    salle = models.CharField(max_length=80, blank=True)
    intervenants = models.ManyToManyField(Intervenant, blank=True, related_name="seances")

    class Meta:
        verbose_name = "séance"
        ordering = ["debut"]

    def __str__(self):
        return f"{self.titre} ({self.debut:%H:%M})"

    def clean(self):
        if self.debut and self.fin and self.fin <= self.debut:
            raise ValidationError({"fin": "La fin doit être après le début."})
        e = getattr(self, "evenement", None)
        if e and self.debut and self.fin and (self.debut < e.date_debut or self.fin > e.date_fin):
            raise ValidationError("La séance doit se dérouler pendant l'événement.")
