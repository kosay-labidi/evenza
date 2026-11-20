from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .models import Inscription


class ListeAttenteTests(TestCase):
    def test_liste_attente_et_promotion(self):
        org = Utilisateur.objects.create_user("o", password="x", role="ORGANISATEUR")
        a = Utilisateur.objects.create_user("a", password="x")
        b = Utilisateur.objects.create_user("b", password="x")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="C")
        d = timezone.now() + timedelta(days=3)
        e = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=org, date_debut=d,
                                     date_fin=d + timedelta(hours=2), capacite=1, statut="PUBLIE")
        ia = Inscription.inscrire(e, a)
        ib = Inscription.inscrire(e, b)
        self.assertEqual(ib.statut, "ATTENTE")
        ia.annuler()
        ib.refresh_from_db()
        self.assertEqual(ib.statut, "CONFIRMEE")


class ReservationTests(TestCase):
    def setUp(self):
        from .models import TypeBillet
        self.org = Utilisateur.objects.create_user("o", password="Test12345!", role="ORGANISATEUR")
        self.p = Utilisateur.objects.create_user("p", password="Test12345!", email="p@x.tn")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Concert")
        d = timezone.now() + timedelta(days=3)
        self.e = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=self.org, date_debut=d,
                                          date_fin=d + timedelta(hours=2), capacite=5, prix=20, statut="PUBLIE")
        self.vip = TypeBillet.objects.create(evenement=self.e, nom="VIP", prix=50, quota=2)

    def test_reservation_en_trois_etapes(self):
        self.client.login(username="p", password="Test12345!")
        url = f"/participants/evenement/{self.e.pk}/reserver/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"type_billet": self.vip.pk, "quantite": 2})
        self.assertContains(r, "100,00 DT")                     # récapitulatif avec le total
        r = self.client.post(url, {"type_billet": self.vip.pk, "quantite": 2, "etape": "confirmer"})
        i = Inscription.objects.get(participant=self.p)
        self.assertEqual((i.quantite, i.montant, i.statut), (2, 100, "CONFIRMEE"))
        self.assertEqual(self.e.places_restantes, 3)

    def test_quota_du_type_de_billet(self):
        self.client.login(username="p", password="Test12345!")
        r = self.client.post(f"/participants/evenement/{self.e.pk}/reserver/", {"type_billet": self.vip.pk, "quantite": 3})
        self.assertContains(r, "Il ne reste que 2")

    def test_connexion_par_email(self):
        self.assertTrue(self.client.login(username="p@x.tn", password="Test12345!"))


class CorrectionsSecuriteTests(TestCase):
    """Non-régression des failles corrigées (check-in, quotas, liste d'attente, avis, annulation)."""

    def setUp(self):
        from .models import TypeBillet
        self.org = Utilisateur.objects.create_user("org", password="Test12345!", role="ORGANISATEUR")
        self.a = Utilisateur.objects.create_user("a", password="Test12345!")
        self.b = Utilisateur.objects.create_user("b", password="Test12345!")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Concert")
        d = timezone.now() + timedelta(days=3)
        self.e = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=self.org, date_debut=d,
                                          date_fin=d + timedelta(hours=2), capacite=5, prix=20, statut="PUBLIE")
        self.TypeBillet = TypeBillet

    def checkin(self, code):
        self.client.login(username="org", password="Test12345!")
        return self.client.post(f"/participants/evenement/{self.e.pk}/checkin/", {"code": code}, follow=True)

    # --- check-in ---
    def test_checkin_refuse_code_trop_court(self):
        i = Inscription.inscrire(self.e, self.a)
        self.checkin(str(i.code_billet)[0])
        i.refresh_from_db()
        self.assertFalse(i.present)

    def test_checkin_avec_code_court_puis_code_complet(self):
        i = Inscription.inscrire(self.e, self.a)
        r = self.checkin(i.code_court)
        self.assertContains(r, "Entrée enregistrée")
        i.refresh_from_db()
        self.assertTrue(i.present)
        r = self.checkin(str(i.code_billet))                 # deuxième passage : déjà entré
        self.assertContains(r, "déjà entré")

    def test_checkin_refuse_billet_en_attente(self):
        self.e.capacite = 1
        self.e.save()
        Inscription.inscrire(self.e, self.a)
        ib = Inscription.inscrire(self.e, self.b)
        self.assertEqual(ib.statut, "ATTENTE")
        self.checkin(ib.code_court)
        ib.refresh_from_db()
        self.assertFalse(ib.present)

    # --- réservation / quotas ---
    def test_inscrire_refuse_doublon(self):
        Inscription.inscrire(self.e, self.a)
        with self.assertRaises(ValidationError):
            Inscription.inscrire(self.e, self.a)

    def test_inscrire_respecte_quota_du_type(self):
        vip = self.TypeBillet.objects.create(evenement=self.e, nom="VIP", prix=50, quota=2)
        Inscription.inscrire(self.e, self.a, vip, 2)
        with self.assertRaises(ValidationError):
            Inscription.inscrire(self.e, self.b, vip, 1)

    def test_inscription_simple_redirige_si_types_de_billet(self):
        self.TypeBillet.objects.create(evenement=self.e, nom="VIP", prix=50)
        self.client.login(username="a", password="Test12345!")
        r = self.client.post(f"/participants/evenement/{self.e.pk}/inscrire/")
        self.assertRedirects(r, f"/participants/evenement/{self.e.pk}/reserver/")
        self.assertFalse(Inscription.objects.exists())

    def test_promotion_liste_attente_respecte_quota(self):
        vip = self.TypeBillet.objects.create(evenement=self.e, nom="VIP", prix=50, quota=1)
        std = self.TypeBillet.objects.create(evenement=self.e, nom="Std", prix=10)
        c = Utilisateur.objects.create_user("c", password="x")
        self.e.capacite = 2
        self.e.save()
        Inscription.inscrire(self.e, self.a, vip, 1)
        ib = Inscription.inscrire(self.e, self.b, std, 1)
        # c attend une place VIP alors que le quota VIP est déjà épuisé par a
        ic = Inscription.objects.create(evenement=self.e, participant=c, type_billet=vip, quantite=1, statut="ATTENTE")
        ib.annuler()
        ic.refresh_from_db()
        self.assertEqual(ic.statut, "ATTENTE")

    # --- annulation ---
    def test_annulation_impossible_apres_debut(self):
        i = Inscription.inscrire(self.e, self.a)
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() - timedelta(hours=1))
        self.client.login(username="a", password="Test12345!")
        self.client.post(f"/participants/inscription/{i.pk}/annuler/")
        i.refresh_from_db()
        self.assertEqual(i.statut, "CONFIRMEE")

    # --- avis ---
    def test_avis_refuse_avant_evenement(self):
        i = Inscription.inscrire(self.e, self.a)
        self.client.login(username="a", password="Test12345!")
        r = self.client.post(f"/participants/inscription/{i.pk}/avis/", {"note": 5, "commentaire": "Top"})
        self.assertEqual(r.status_code, 404)

    def test_avis_accepte_apres_evenement(self):
        i = Inscription.inscrire(self.e, self.a)
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() - timedelta(days=2),
                                                      date_fin=timezone.now() - timedelta(days=1))
        self.client.login(username="a", password="Test12345!")
        r = self.client.post(f"/participants/inscription/{i.pk}/avis/", {"note": 5, "commentaire": "Top"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(hasattr(Inscription.objects.get(pk=i.pk), "avis"))

    def test_prix_negatif_refuse(self):
        t = self.TypeBillet(evenement=self.e, nom="X", prix=-5)
        with self.assertRaises(ValidationError):
            t.full_clean()
