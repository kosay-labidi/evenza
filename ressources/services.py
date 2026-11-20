"""Logique métier réutilisable : détection des conflits de ressources."""
from django.core.exceptions import ValidationError
from django.db.models import Sum


def verifier_conflit(affectation):
    """Refuse l'affectation si la ressource est déjà trop utilisée sur le même créneau."""
    chevauchent = (affectation.ressource.affectations
                   .filter(debut__lt=affectation.fin, fin__gt=affectation.debut)
                   .exclude(pk=affectation.pk))
    deja = chevauchent.aggregate(total=Sum("quantite"))["total"] or 0
    dispo = affectation.ressource.quantite - deja
    if affectation.quantite > dispo:
        raise ValidationError(
            f"Conflit : « {affectation.ressource.nom} » n'a que {max(dispo, 0)} unité(s) libre(s) sur ce créneau."
        )
