"""Fichier iCalendar (RFC 5545) d'une réservation, construit à la main (aucune bibliothèque externe).

- lignes terminées par CRLF, repliées à 75 octets (suite précédée d'une espace) ;
- texte échappé : « \\ », « ; », « , » et retours à la ligne ;
- dates en UTC (suffixe Z) ;
- UID stable, basé sur le code du billet.
"""
from datetime import timezone as dt_timezone

from django.utils import timezone

CRLF = "\r\n"


def echapper(texte):
    """Échappe une valeur de type TEXT (RFC 5545, section 3.3.11)."""
    texte = str(texte or "")
    texte = texte.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return texte.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


def date_utc(valeur):
    """Date-heure au format iCalendar en UTC : 20261127T183000Z."""
    if timezone.is_naive(valeur):
        valeur = timezone.make_aware(valeur)
    return valeur.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def replier(ligne):
    """Coupe une ligne trop longue en morceaux de 75 octets au plus (sans couper un caractère UTF-8)."""
    morceaux, courant, taille, limite = [], "", 0, 75
    for car in ligne:
        n = len(car.encode("utf-8"))
        if taille + n > limite:
            morceaux.append(courant)
            courant, taille, limite = " ", 1, 75          # la ligne de continuation commence par une espace
        courant += car
        taille += n
    morceaux.append(courant)
    return CRLF.join(morceaux)


def ics_inscription(inscription, lien_billet=""):
    """Contenu .ics (str) d'un événement pour une réservation."""
    e = inscription.evenement
    lieu = ", ".join(x for x in (e.lieu.nom, e.lieu.adresse, e.lieu.ville) if x)
    billet = f"{inscription.type_billet.nom if inscription.type_billet else 'Entrée'} × {inscription.quantite}"
    description = f"Billet : {billet}\nCode : {inscription.code_court}"
    if lien_billet:
        description += f"\nBillet (QR code) : {lien_billet}"
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Evenza//Participants//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{inscription.code_billet}@evenza",
        f"DTSTAMP:{date_utc(timezone.now())}",
        f"DTSTART:{date_utc(e.date_debut)}",
        f"DTEND:{date_utc(e.date_fin)}",
        f"SUMMARY:{echapper(e.titre)}",
        f"LOCATION:{echapper(lieu)}",
        f"DESCRIPTION:{echapper(description)}",
        "STATUS:CONFIRMED" if inscription.statut == "CONFIRMEE" else "STATUS:TENTATIVE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return CRLF.join(replier(l) for l in lignes) + CRLF
