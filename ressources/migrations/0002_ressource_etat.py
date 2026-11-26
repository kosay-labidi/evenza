import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ressources", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ressource",
            name="etat",
            field=models.CharField(
                choices=[
                    ("DISPONIBLE", "Disponible"),
                    ("MAINTENANCE", "En maintenance"),
                    ("HORS_SERVICE", "Hors service"),
                ],
                default="DISPONIBLE",
                max_length=15,
                verbose_name="état",
            ),
        ),
        migrations.AlterField(
            model_name="ressource",
            name="quantite",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Nombre d'unités disponibles",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="quantité",
            ),
        ),
    ]
