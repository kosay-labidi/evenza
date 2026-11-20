from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .models import Prestataire, Reservation, Service


class ReservationStatutTests(TestCase):
    def setUp(self):
        self.org = Utilisateur.objects.create_user("org", password="Test12345!", role="ORGANISATEUR")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Gala")
        d = timezone.now() + timedelta(days=5)
        e = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=self.org, date_debut=d,
                                     date_fin=d + timedelta(hours=2), capacite=10)
        s = Service.objects.create(nom="Buffet", type="TRAITEUR")
        p = Prestataire.objects.create(nom="P")
        p.services.add(s)
        self.r = Reservation.objects.create(evenement=e, prestataire=p, service=s, montant=100)
        self.client.login(username="org", password="Test12345!")

    def changer(self, statut):
        self.client.post(f"/prestataires/reservation/{self.r.pk}/{statut}/")
        self.r.refresh_from_db()

    def test_transitions_autorisees(self):
        self.changer("CONFIRMEE")
        self.assertEqual(self.r.statut, "CONFIRMEE")
        self.changer("ANNULEE")
        self.assertEqual(self.r.statut, "ANNULEE")

    def test_annulee_est_definitive(self):
        self.changer("ANNULEE")
        self.changer("CONFIRMEE")
        self.assertEqual(self.r.statut, "ANNULEE")

    def test_statut_inconnu_refuse(self):
        self.changer("PIRATE")
        self.assertEqual(self.r.statut, "DEMANDEE")
