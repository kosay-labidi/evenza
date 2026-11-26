from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("evenements", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Seance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titre", models.CharField(max_length=30)),
                ("description", models.CharField(blank=True)),
                ("date", models.DateTimeField()),
                ("evenement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seances", to="evenements.evenement")),
            ],
        ),
    ]
