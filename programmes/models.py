from django.core.exceptions import ValidationError
from django.db import models

from evenements.models import Evenement


class Seance(models.Model):
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="seances")
    titre = models.CharField(max_length=30)
    description = models.CharField(blank=True)
    date = models.DateTimeField()

    def __str__(self):
        return f"{self.titre} ({self.date:%H:%M})"

    def clean(self):
        evenement = getattr(self, "evenement", None)
        if evenement and self.date and (self.date < evenement.date_debut or self.date > evenement.date_fin):
            raise ValidationError({"date": "La séance doit se dérouler pendant l'événement."})
