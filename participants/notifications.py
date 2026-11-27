"""E-mails envoyés aux participants (configuration e-mail du projet utilisée telle quelle).

``notifier_promotion`` est appelée par ``Inscription._promouvoir_liste_attente()`` via ``transaction.on_commit`` :
elle ne s'exécute que si la transaction a été validée. Un échec d'envoi est journalisé et n'est jamais propagé
(l'annulation ou la modification qui a libéré la place est déjà enregistrée).
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def lien_absolu(chemin):
    """URL complète si le projet définit SITE_URL (ex. « https://evenza.tn »), sinon le chemin seul."""
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}{chemin}" if base else chemin


def notifier_promotion(inscription_pk):
    """Prévient le participant que sa réservation est passée de la liste d'attente à « Confirmée »."""
    from .models import Inscription

    try:
        insc = (Inscription.objects.select_related("participant", "evenement", "evenement__lieu", "type_billet")
                .get(pk=inscription_pk))
    except Inscription.DoesNotExist:
        return False
    if insc.statut != Inscription.Statut.CONFIRMEE or not insc.participant.email:
        return False
    ctx = {"inscription": insc, "evenement": insc.evenement, "participant": insc.participant,
           "lien_billet": lien_absolu(insc.get_absolute_url())}
    sujet = " ".join(render_to_string("participants/emails/promotion_sujet.txt", ctx).split())
    corps = render_to_string("participants/emails/promotion.txt", ctx)
    try:
        send_mail(sujet, corps, None, [insc.participant.email])      # None = DEFAULT_FROM_EMAIL
    except Exception:                                                # un e-mail en échec ne bloque rien
        logger.exception("E-mail de promotion non envoyé (inscription %s)", inscription_pk)
        return False
    return True
