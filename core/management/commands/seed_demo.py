"""Crée des données de démonstration idempotentes pour Evenza."""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from participants.models import Inscription, TypeBillet
from prestataires.models import Prestataire, Reservation, Service
from programmes.models import Seance
from ressources.models import Affectation, Ressource
from utilisateurs.models import Utilisateur

MDP = "Demo12345!"


class Command(BaseCommand):
    help = "Crée des utilisateurs, référentiels, événements et données métier de démonstration."

    @transaction.atomic
    def handle(self, *args, **opts):
        admin, created = Utilisateur.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@evenza.tn",
                "role": "ADMIN",
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Admin",
            },
        )
        if created:
            admin.set_password("Admin12345!")
            admin.save()

        def user(username, role, first_name, last_name):
            account, account_created = Utilisateur.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{username}@evenza.tn",
                },
            )
            if account_created:
                account.set_password(MDP)
                account.save()
            return account

        organizer = user("organisateur", "ORGANISATEUR", "Koussay", "Organisateur")
        participants = [user("participant", "PARTICIPANT", "Sara", "Ben Ali")]
        participants += [
            user(f"participant{i}", "PARTICIPANT", first_name, last_name)
            for i, (first_name, last_name) in enumerate(
                [
                    ("Yassine", "Trabelsi"),
                    ("Amira", "Gharbi"),
                    ("Omar", "Jaziri"),
                    ("Lina", "Mansour"),
                ],
                start=2,
            )
        ]
        user("prestataire", "PRESTATAIRE", "Nour", "Traiteur")

        # Exactly three named demonstration categories. Existing unrelated
        # categories are left untouched because the seed never deletes data.
        category_data = {
            "Concert": {},
            "Conférence": {},
            "Mariage": {},
        }
        categories = {
            name: Categorie.objects.update_or_create(nom=name, defaults=defaults)[0]
            for name, defaults in category_data.items()
        }

        # Exactly five named demonstration venues with varied capacities.
        venue_data = {
            "carthage": {
                "nom": "Théâtre antique de Carthage",
                "adresse": "Rue du Théâtre romain",
                "ville": "Carthage",
                "capacite": 5000,
            },
            "sidi_bou_said": {
                "nom": "Dar Sidi Bou Saïd",
                "adresse": "Rue Habib Thameur",
                "ville": "Sidi Bou Saïd",
                "capacite": 250,
            },
            "sousse": {
                "nom": "Palais des congrès de Sousse",
                "adresse": "Boulevard du 14 janvier",
                "ville": "Sousse",
                "capacite": 900,
            },
            "esprit": {
                "nom": "ESPRIT – Amphi A",
                "adresse": "Pôle technologique El Ghazala",
                "ville": "Ariana",
                "capacite": 300,
            },
            "hammamet": {
                "nom": "Centre culturel de Hammamet",
                "adresse": "Avenue de la République",
                "ville": "Hammamet",
                "capacite": 650,
            },
        }
        venues = {
            key: Lieu.objects.update_or_create(
                nom=data["nom"],
                ville=data["ville"],
                defaults={key: value for key, value in data.items() if key not in {"nom", "ville"}},
            )[0]
            for key, data in venue_data.items()
        }

        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        def event(title, category, venue, days, hour, duration, capacity, price, description):
            start = (now + timedelta(days=days)).replace(hour=hour)
            return Evenement.objects.update_or_create(
                titre=title,
                defaults={
                    "categorie": categories[category],
                    "lieu": venues[venue],
                    "organisateur": organizer,
                    "date_debut": start,
                    "date_fin": start + timedelta(hours=duration),
                    "capacite": capacity,
                    "prix": price,
                    "statut": Evenement.Statut.PUBLIE,
                    "description": description,
                },
            )[0]

        # Exactly two named demonstration events with different scales and prices.
        festival = event(
            "Tunis Summer Festival",
            "Concert",
            "carthage",
            20,
            21,
            4,
            5000,
            Decimal("45.00"),
            "Trois artistes, une scène et une nuit d'été face aux ruines de Carthage.",
        )
        conference = event(
            "Forum IA & Logiciel",
            "Conférence",
            "sousse",
            12,
            9,
            8,
            600,
            Decimal("20.00"),
            "Une journée de conférences sur l'intelligence artificielle et le génie logiciel.",
        )
        demo_events = (festival, conference)

        # Ticket types are scoped to the two demonstration events only.
        for demo_event in demo_events:
            if demo_event.types_billet.exists():
                continue
            TypeBillet.objects.create(
                evenement=demo_event,
                nom="Standard",
                prix=demo_event.prix,
                description="Accès à l'événement",
            )
            TypeBillet.objects.create(
                evenement=demo_event,
                nom="VIP",
                prix=demo_event.prix * Decimal("2.5"),
                quota=max(1, demo_event.capacite // 10),
                description="Accueil privilégié et placement réservé",
            )

        # Programme built only with the current Seance model.
        if not conference.seances.exists():
            start = conference.date_debut
            for title, duration, description in [
                ("Ouverture", 1, "Accueil des participants et présentation de la journée."),
                ("L'IA générative en entreprise", 2, "Conférence sur les usages de l'IA générative."),
                ("Architecture MVT et microservices", 2, "Séance consacrée aux architectures applicatives."),
                ("Table ronde", 2, "Échanges avec les participants."),
            ]:
                Seance.objects.create(
                    evenement=conference,
                    titre=title,
                    description=description,
                    date=start,
                )
                start += timedelta(hours=duration)
        if not festival.seances.exists():
            start = festival.date_debut
            for title in ("Ouverture des portes", "Première partie", "Le show"):
                Seance.objects.create(
                    evenement=festival,
                    titre=title,
                    description="Programme du festival.",
                    date=start,
                )
                start += timedelta(hours=1)

        services = {
            service_type: Service.objects.get_or_create(nom=name, type=service_type)[0]
            for service_type, name in [
                ("TRAITEUR", "Dîner complet"),
                ("SON", "Sonorisation"),
                ("LUMIERE", "Éclairage de scène"),
                ("PHOTO", "Reportage photo"),
            ]
        }
        caterer = Prestataire.objects.get_or_create(
            nom="Délices de Carthage",
            defaults={"telephone": "71 000 001", "email": "contact@delices.tn"},
        )[0]
        caterer.services.add(services["TRAITEUR"])
        sound_provider = Prestataire.objects.get_or_create(
            nom="Sound & Light Tunis",
            defaults={"telephone": "71 000 002"},
        )[0]
        sound_provider.services.add(services["SON"], services["LUMIERE"])
        photographer = Prestataire.objects.get_or_create(
            nom="Studio Lumière",
            defaults={"telephone": "71 000 003"},
        )[0]
        photographer.services.add(services["PHOTO"])
        Reservation.objects.get_or_create(
            evenement=festival,
            prestataire=sound_provider,
            service=services["SON"],
            defaults={"montant": 8000, "statut": "CONFIRMEE"},
        )
        Reservation.objects.get_or_create(
            evenement=conference,
            prestataire=caterer,
            service=services["TRAITEUR"],
            defaults={"montant": 12000},
        )
        Reservation.objects.get_or_create(
            evenement=conference,
            prestataire=photographer,
            service=services["PHOTO"],
            defaults={"montant": 2500},
        )

        screen = Ressource.objects.get_or_create(
            nom="Écran LED 6×3 m",
            defaults={"type": "MATERIEL", "quantite": 2},
        )[0]
        projector = Ressource.objects.get_or_create(
            nom="Projecteur lyre",
            defaults={"type": "MATERIEL", "quantite": 24},
        )[0]
        Ressource.objects.get_or_create(
            nom="Minibus 20 places",
            defaults={"type": "VEHICULE", "quantite": 3},
        )
        Affectation.objects.get_or_create(
            ressource=screen,
            evenement=festival,
            defaults={"debut": festival.date_debut, "fin": festival.date_fin, "quantite": 1},
        )
        Affectation.objects.get_or_create(
            ressource=projector,
            evenement=festival,
            defaults={"debut": festival.date_debut, "fin": festival.date_fin, "quantite": 16},
        )

        for participant in participants[:4]:
            if not festival.inscriptions.filter(participant=participant).exists():
                Inscription.inscrire(festival, participant, festival.types_billet.first(), 2)
        for participant in participants[:2]:
            if not conference.inscriptions.filter(participant=participant).exists():
                Inscription.inscrire(conference, participant, conference.types_billet.first())

        self.stdout.write(self.style.SUCCESS("Données de démonstration créées ou mises à jour."))
        self.stdout.write(
            f"  {len(categories)} catégories, {len(venues)} lieux, {len(demo_events)} événements"
        )
        self.stdout.write("  admin        / Admin12345!   (superutilisateur, /admin/)")
        self.stdout.write(f"  organisateur / {MDP}")
        self.stdout.write(f"  participant  / {MDP}")
