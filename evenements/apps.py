from django.apps import AppConfig


class EvenementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "evenements"
    verbose_name = "Gestion des événements"

    def ready(self):
        from django.core.exceptions import ValidationError
        from django.db.models.signals import pre_save

        def bloquer_reservation_si_non_publie(sender, instance, **kwargs):
            """Une réservation nouvelle n'est acceptée que sur un événement publié."""
            if instance.pk or not instance.evenement_id:
                return
            if getattr(instance, "statut", "") == "ANNULEE":
                return
            from .models import Evenement
            statut = Evenement.objects.filter(pk=instance.evenement_id).values_list("statut", flat=True).first()
            if statut and statut != Evenement.Statut.PUBLIE:
                raise ValidationError("Les réservations sont fermées : l'événement n'est pas publié.")

        from participants.models import Inscription
        pre_save.connect(
            bloquer_reservation_si_non_publie,
            sender=Inscription,
            dispatch_uid="evenements.bloquer_reservation_si_non_publie",
        )
