"""Numéros de téléphone tunisiens des prestataires.

Saisies acceptées : « 22123456 », « 22 123 456 », « 22-123-456 », « +216 22 123 456 », « 00216 22 123 456 ».
Format enregistré (unique, partout) : « 22 123 456 ».
Règle : 8 chiffres, le premier étant 2, 3, 4, 5, 7 ou 9.
"""
import re

from django.core.exceptions import ValidationError

PREMIERS_CHIFFRES = "234579"
MSG_LONGUEUR = "Le numéro doit contenir 8 chiffres."
MSG_INVALIDE = "Ce numéro n'est pas un numéro tunisien valide."
MSG_DOUBLON = "Ce numéro est déjà utilisé par un autre prestataire."

# Attributs HTML du champ (le pattern accepte les mêmes saisies que normaliser()).
PATTERN_HTML = r"(?:(?:\+|00)216[ \-]?)?[234579][0-9](?:[ \-]?[0-9]){6}"
LONGUEUR_MAX_SAISIE = 16          # « 00216 22 123 456 »


def chiffres(valeur):
    """Les 8 chiffres nationaux (séparateurs et indicatif +216 / 00216 retirés), sans vérification."""
    brut = re.sub(r"[\s\-.]", "", valeur or "")
    for indicatif in ("+216", "00216"):
        if brut.startswith(indicatif):
            return brut[len(indicatif):]
    return brut


def normaliser(valeur):
    """Renvoie « 22 123 456 » ou lève ValidationError avec un message clair."""
    n = chiffres(valeur)
    if not n.isdigit() or len(n) != 8:
        raise ValidationError(MSG_LONGUEUR, code="longueur")
    if n[0] not in PREMIERS_CHIFFRES:
        raise ValidationError(MSG_INVALIDE, code="invalide")
    return f"{n[:2]} {n[2:5]} {n[5:]}"


def cle(valeur):
    """Clé de comparaison pour l'unicité (« 22-123-456 » et « +216 22123456 » sont le même numéro)."""
    return chiffres(valeur)
