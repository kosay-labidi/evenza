"""Migration de données : garantit au moins un service pour chacun des 6 types du catalogue.

N'ajoute un service que si son type n'en a encore aucun. Ne supprime et ne modifie rien.
L'inverse est sans effet (noop) : on ne retire pas des services qui ont pu être réservés depuis.
"""
from django.db import migrations

# Valeurs figées ici (et non importées du modèle) pour que la migration reste stable dans le temps.
SERVICES_PAR_DEFAUT = {
    "TRAITEUR": "Service traiteur",
    "SON": "Sonorisation",
    "LUMIERE": "Éclairage scénique",
    "DECOR": "Décoration florale",
    "PHOTO": "Reportage photo",
    "SECURITE": "Agents de sécurité",
}


def ajouter_services_manquants(apps, schema_editor):
    Service = apps.get_model("prestataires", "Service")
    types_existants = set(Service.objects.values_list("type", flat=True))
    Service.objects.bulk_create(
        Service(nom=nom, type=type_) for type_, nom in SERVICES_PAR_DEFAUT.items() if type_ not in types_existants
    )


class Migration(migrations.Migration):

    dependencies = [
        ("prestataires", "0004_prestataire_photo"),
    ]

    operations = [
        migrations.RunPython(ajouter_services_manquants, migrations.RunPython.noop),
    ]
