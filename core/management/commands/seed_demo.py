"""python manage.py seed_demo : remplit la base avec des données de démonstration."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from participants.models import Inscription, TypeBillet
from prestataires.models import Prestataire, Reservation, Service
from programmes.models import Intervenant, Seance
from ressources.models import Affectation, Ressource
from utilisateurs.models import Utilisateur

MDP = "Demo12345!"


class Command(BaseCommand):
    help = "Crée des utilisateurs, événements, programmes, prestataires, inscriptions et ressources de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Vide les données Évenza avant de recréer.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            for m in (Affectation, Reservation, Inscription, TypeBillet, Seance, Evenement, Ressource, Prestataire, Service,
                      Intervenant, Lieu, Categorie):
                m.objects.all().delete()
            Utilisateur.objects.exclude(is_superuser=True).delete()

        # --- utilisateurs ---
        admin, created = Utilisateur.objects.get_or_create(username="admin", defaults={
            "email": "admin@evenza.tn", "role": "ADMIN", "is_staff": True, "is_superuser": True, "first_name": "Admin"})
        if created:
            admin.set_password("Admin12345!"); admin.save()
        def user(username, role, prenom, nom):
            u, c = Utilisateur.objects.get_or_create(username=username, defaults={
                "role": role, "first_name": prenom, "last_name": nom, "email": f"{username}@evenza.tn"})
            if c:
                u.set_password(MDP); u.save()
            return u
        org = user("organisateur", "ORGANISATEUR", "Koussay", "Organisateur")
        parts = [user("participant", "PARTICIPANT", "Sara", "Ben Ali")] + [
            user(f"participant{i}", "PARTICIPANT", p, n) for i, (p, n) in enumerate(
                [("Yassine", "Trabelsi"), ("Amira", "Gharbi"), ("Omar", "Jaziri"), ("Lina", "Mansour")], start=2)]
        user("prestataire", "PRESTATAIRE", "Nour", "Traiteur")

        # --- référentiels ---
        cats = {n: Categorie.objects.get_or_create(nom=n)[0] for n in ["Concert", "Mariage", "Conférence", "Gala", "Festival"]}
        lieux = {
            "carthage": Lieu.objects.get_or_create(nom="Théâtre de Carthage", defaults={"adresse": "Carthage", "ville": "Tunis", "capacite": 7500})[0],
            "sbs": Lieu.objects.get_or_create(nom="Dar Sidi Bou Saïd", defaults={"adresse": "Rue Habib Thameur", "ville": "Sidi Bou Saïd", "capacite": 250})[0],
            "sousse": Lieu.objects.get_or_create(nom="Palais des congrès", defaults={"adresse": "Bd du 14 janvier", "ville": "Sousse", "capacite": 900})[0],
            "esprit": Lieu.objects.get_or_create(nom="ESPRIT – Amphi A", defaults={"adresse": "El Ghazala", "ville": "Ariana", "capacite": 300})[0],
        }

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        def evt(titre, cat, lieu, jours, heure, duree, cap, prix, statut="PUBLIE", desc=""):
            d = (now + timedelta(days=jours)).replace(hour=heure)
            e, _ = Evenement.objects.get_or_create(titre=titre, defaults=dict(
                categorie=cats[cat], lieu=lieux[lieu], organisateur=org, date_debut=d, date_fin=d + timedelta(hours=duree),
                capacite=cap, prix=prix, statut=statut, description=desc))
            return e
        festival = evt("Tunis Summer Festival", "Concert", "carthage", 20, 21, 4, 5000, 45,
                       desc="Trois artistes, une scène, une nuit d'été à Carthage.")
        mariage = evt("Mariage Ines & Karim", "Mariage", "sbs", 35, 19, 6, 120, 0,
                      desc="Cérémonie, dîner et soirée dansante.")
        conf = evt("Forum IA & Logiciel", "Conférence", "sousse", 12, 9, 8, 600, 20,
                   desc="Journée de conférences sur l'IA et le génie logiciel.")
        evt("Gala de fin d'année ESPRIT", "Gala", "esprit", 50, 20, 4, 3, 30,
            desc="Dîner de gala (3 places pour tester la liste d'attente).")
        evt("Festival Jazz de Tabarka", "Festival", "carthage", 60, 18, 6, 4000, 35,
            desc="Trois jours de jazz face à la mer.")
        evt("Festival de Hammamet (brouillon)", "Festival", "carthage", 70, 18, 6, 3000, 35, statut="BROUILLON")

        # --- types de billets ---
        for e in Evenement.objects.all():
            if e.types_billet.exists():
                continue
            if e.prix:
                TypeBillet.objects.create(evenement=e, nom="Standard", prix=e.prix, description="Accès à l'événement")
                TypeBillet.objects.create(evenement=e, nom="VIP", prix=round(e.prix * 25) / 10, quota=max(1, e.capacite // 10),
                                          description="Placement privilégié et accueil dédié")
                TypeBillet.objects.create(evenement=e, nom="Étudiant", prix=round(e.prix * 6) / 10,
                                          description="Sur présentation de la carte étudiante")
            else:
                TypeBillet.objects.create(evenement=e, nom="Invité", prix=0, description="Sur invitation")

        # --- programme ---
        i1 = Intervenant.objects.get_or_create(nom="Dr. Salma Haddad", defaults={"specialite": "Intelligence artificielle"})[0]
        i2 = Intervenant.objects.get_or_create(nom="Mehdi Karoui", defaults={"specialite": "Architecture logicielle"})[0]
        if not conf.seances.exists():
            s = conf.date_debut
            for k, (t, h, iv) in enumerate([("Ouverture", 1, []), ("L'IA générative en entreprise", 2, [i1]),
                                            ("Architecture MVT et microservices", 2, [i2]), ("Table ronde", 2, [i1, i2])]):
                se = Seance.objects.create(evenement=conf, titre=t, debut=s, fin=s + timedelta(hours=h), salle="Salle A")
                se.intervenants.set(iv); s += timedelta(hours=h)
        if not festival.seances.exists():
            s = festival.date_debut
            for t in ["Ouverture des portes", "Première partie", "Le show"]:
                Seance.objects.create(evenement=festival, titre=t, debut=s, fin=s + timedelta(hours=1), salle="Scène")
                s += timedelta(hours=1)

        # --- prestataires ---
        svc = {t: Service.objects.get_or_create(nom=n, type=t)[0] for t, n in
               [("TRAITEUR", "Dîner complet"), ("SON", "Sonorisation"), ("LUMIERE", "Éclairage scène"), ("PHOTO", "Reportage photo")]}
        p1 = Prestataire.objects.get_or_create(nom="Délices de Carthage", defaults={"telephone": "71 000 001", "email": "contact@delices.tn"})[0]
        p1.services.add(svc["TRAITEUR"])
        p2 = Prestataire.objects.get_or_create(nom="Sound & Light Tunis", defaults={"telephone": "71 000 002"})[0]
        p2.services.add(svc["SON"], svc["LUMIERE"])
        p3 = Prestataire.objects.get_or_create(nom="Studio Lumière", defaults={"telephone": "71 000 003"})[0]
        p3.services.add(svc["PHOTO"])
        Reservation.objects.get_or_create(evenement=festival, prestataire=p2, service=svc["SON"], defaults={"montant": 8000, "statut": "CONFIRMEE"})
        Reservation.objects.get_or_create(evenement=mariage, prestataire=p1, service=svc["TRAITEUR"], defaults={"montant": 12000})
        Reservation.objects.get_or_create(evenement=mariage, prestataire=p3, service=svc["PHOTO"], defaults={"montant": 2500})

        # --- ressources ---
        r1 = Ressource.objects.get_or_create(nom="Écran LED 6×3 m", defaults={"type": "MATERIEL", "quantite": 2})[0]
        r2 = Ressource.objects.get_or_create(nom="Projecteur lyre", defaults={"type": "MATERIEL", "quantite": 24})[0]
        Ressource.objects.get_or_create(nom="Minibus 20 places", defaults={"type": "VEHICULE", "quantite": 3})
        Affectation.objects.get_or_create(ressource=r1, evenement=festival, defaults={"debut": festival.date_debut, "fin": festival.date_fin, "quantite": 1})
        Affectation.objects.get_or_create(ressource=r2, evenement=festival, defaults={"debut": festival.date_debut, "fin": festival.date_fin, "quantite": 16})

        # --- inscriptions ---
        for p in parts[:4]:
            if not festival.inscriptions.filter(participant=p).exists():
                Inscription.inscrire(festival, p, festival.types_billet.first(), 2)
        for p in parts[:2]:
            if not conf.inscriptions.filter(participant=p).exists():
                Inscription.inscrire(conf, p)

        self.stdout.write(self.style.SUCCESS("Données de démonstration créées."))
        self.stdout.write("  admin        / Admin12345!   (superutilisateur, /admin/)")
        self.stdout.write(f"  organisateur / {MDP}")
        self.stdout.write(f"  participant  / {MDP}")
