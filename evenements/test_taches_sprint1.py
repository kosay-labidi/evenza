"""Tests des tâches 2.1.3, 2.2.3, 2.3.3 et 2.4.3 (Sprint 1 — gestion des événements).

La base utilisée est la base de test Django (SQLite en mémoire), distincte de db.sqlite3.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from participants.models import Inscription
from utilisateurs.models import Utilisateur

from .models import Categorie, Evenement, Lieu


class BaseEvenement(TestCase):
    password = "Test12345!"

    def setUp(self):
        self.org = Utilisateur.objects.create_user("org", password=self.password, role="ORGANISATEUR")
        self.autre_org = Utilisateur.objects.create_user("autre_org", password=self.password, role="ORGANISATEUR")
        self.part = Utilisateur.objects.create_user("part", password=self.password, role="PARTICIPANT")
        self.lieu = Lieu.objects.create(nom="Salle", adresse="Rue 1", ville="Tunis", capacite=200)
        self.autre_lieu = Lieu.objects.create(nom="Palais", adresse="Rue 2", ville="Sousse", capacite=300)
        self.cat = Categorie.objects.create(nom="Concert")
        self.autre_cat = Categorie.objects.create(nom="Gala")

    def creer(self, titre="Soirée", lieu=None, categorie=None, jours=10, statut=None, **extra):
        debut = timezone.now() + timedelta(days=jours)
        data = dict(
            titre=titre,
            description="Description de l'événement.",
            categorie=categorie or self.cat,
            lieu=lieu or self.lieu,
            organisateur=self.org,
            date_debut=debut,
            date_fin=debut + timedelta(hours=3),
            capacite=50,
            prix=Decimal("20.00"),
        )
        data.update(extra)
        e = Evenement.objects.create(**data)
        if statut:
            e.statut = statut
            e.save(update_fields=["statut"])
        return e

    def payload(self, **over):
        debut = timezone.localtime(timezone.now() + timedelta(days=20))
        fin = debut + timedelta(hours=4)
        data = {
            "titre": "Gala Évenza",
            "description": "Soirée de gala avec dîner et concert.",
            "categorie": self.cat.pk,
            "lieu": self.lieu.pk,
            "date_debut": debut.strftime("%Y-%m-%dT%H:%M"),
            "date_fin": fin.strftime("%Y-%m-%dT%H:%M"),
            "capacite": 80,
            "prix": "45.00",
        }
        data.update(over)
        return data


class CreationEvenementTests(BaseEvenement):
    """US 2.1.3 — champs obligatoires et enregistrement."""

    def test_creation_valide(self):
        self.client.login(username="org", password=self.password)
        avant = Evenement.objects.count()
        r = self.client.post(reverse("evenements:creer"), self.payload())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Evenement.objects.count(), avant + 1)
        e = Evenement.objects.get(titre="Gala Évenza")
        self.assertEqual(e.organisateur, self.org)
        self.assertEqual(e.capacite, 80)
        self.assertEqual(e.prix, Decimal("45.00"))
        self.assertEqual(e.lieu, self.lieu)

    def test_champ_obligatoire_manquant(self):
        self.client.login(username="org", password=self.password)
        data = self.payload()
        data["titre"] = ""
        data["description"] = ""
        avant = Evenement.objects.count()
        r = self.client.post(reverse("evenements:creer"), data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Evenement.objects.count(), avant)
        self.assertIn("titre", r.context["form"].errors)
        self.assertIn("description", r.context["form"].errors)

    def test_date_fin_anterieure_refusee(self):
        self.client.login(username="org", password=self.password)
        debut = timezone.localtime(timezone.now() + timedelta(days=12))
        data = self.payload(
            date_debut=debut.strftime("%Y-%m-%dT%H:%M"),
            date_fin=(debut - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        )
        r = self.client.post(reverse("evenements:creer"), data)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Evenement.objects.filter(titre="Gala Évenza").exists())
        self.assertTrue(r.context["form"].errors)

    def test_capacite_ou_prix_negatif(self):
        self.client.login(username="org", password=self.password)
        r = self.client.post(reverse("evenements:creer"), self.payload(capacite=-5, prix="-12.50"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Evenement.objects.filter(titre="Gala Évenza").exists())
        self.assertIn("capacite", r.context["form"].errors)
        self.assertIn("prix", r.context["form"].errors)

    def test_statut_par_defaut_brouillon(self):
        self.client.login(username="org", password=self.password)
        self.client.post(reverse("evenements:creer"), self.payload(titre="Brouillon auto"))
        e = Evenement.objects.get(titre="Brouillon auto")
        e.refresh_from_db()
        self.assertEqual(e.statut, Evenement.Statut.BROUILLON)


class ConsultationEvenementTests(BaseEvenement):
    """US 2.2.3 — liste, détail, filtres, pagination."""

    def test_liste_non_vide(self):
        self.creer("Concert visible", statut=Evenement.Statut.PUBLIE)
        r = self.client.get(reverse("evenements:liste"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Concert visible")
        self.assertGreaterEqual(len(r.context["object_list"]), 1)

    def test_liste_vide(self):
        self.creer("Brouillon caché")  # non publié : absent du catalogue
        r = self.client.get(reverse("evenements:liste"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Aucun événement")
        self.assertEqual(list(r.context["object_list"]), [])

    def test_filtre_combine(self):
        cible = self.creer("Forum Sousse", lieu=self.autre_lieu, categorie=self.autre_cat,
                           jours=30, statut=Evenement.Statut.PUBLIE)
        self.creer("Concert Tunis", jours=5, statut=Evenement.Statut.PUBLIE)
        self.creer("Gala annulé", lieu=self.autre_lieu, categorie=self.autre_cat,
                   jours=30, statut=Evenement.Statut.ANNULE)
        r = self.client.get(reverse("evenements:liste"), {
            "categorie": self.autre_cat.pk,
            "lieu": self.autre_lieu.pk,
            "ville": "Sousse",
            "date": (timezone.localdate() + timedelta(days=20)).isoformat(),
            "statut": Evenement.Statut.PUBLIE,
        })
        self.assertContains(r, "Forum Sousse")
        self.assertNotContains(r, "Concert Tunis")
        self.assertNotContains(r, "Gala annulé")
        self.assertEqual(list(r.context["object_list"]), [cible])

    def test_pagination_premiere_derniere_et_page_inexistante(self):
        for i in range(1, 11):
            self.creer(f"PageEvent {i:02d}", jours=i, statut=Evenement.Statut.PUBLIE)
        premiere = self.client.get(reverse("evenements:liste"), {"page": 1})
        self.assertEqual(premiere.status_code, 200)
        self.assertContains(premiere, "PageEvent 01")
        self.assertContains(premiere, "PageEvent 09")
        self.assertNotContains(premiere, "PageEvent 10")
        self.assertEqual(premiere.context["page_obj"].number, 1)

        derniere = self.client.get(reverse("evenements:liste"), {"page": 2})
        self.assertEqual(derniere.status_code, 200)
        self.assertContains(derniere, "PageEvent 10")
        self.assertNotContains(derniere, "PageEvent 01")
        self.assertEqual(derniere.context["page_obj"].number, 2)
        self.assertFalse(derniere.context["page_obj"].has_next())

        self.assertEqual(self.client.get(reverse("evenements:liste"), {"page": 99}).status_code, 404)
        self.assertEqual(self.client.get(reverse("evenements:liste"), {"page": "abc"}).status_code, 404)

    def test_detail_existant_et_inexistant(self):
        e = self.creer("Détail public", statut=Evenement.Statut.PUBLIE)
        ok = self.client.get(reverse("evenements:detail", args=[e.pk]))
        self.assertEqual(ok.status_code, 200)
        self.assertContains(ok, "Détail public")
        self.assertEqual(self.client.get(reverse("evenements:detail", args=[999999])).status_code, 404)


class ModificationEvenementTests(BaseEvenement):
    """US 2.3.3 — droits et modification."""

    def setUp(self):
        super().setUp()
        self.e = self.creer("À modifier", statut=Evenement.Statut.PUBLIE)

    def test_proprietaire_modifie(self):
        self.client.login(username="org", password=self.password)
        r = self.client.post(reverse("evenements:modifier", args=[self.e.pk]), self.payload(
            titre="Titre mis à jour",
            description="Nouvelle description suffisamment longue.",
            categorie=self.e.categorie_id,
            lieu=self.e.lieu_id,
            date_debut=timezone.localtime(self.e.date_debut).strftime("%Y-%m-%dT%H:%M"),
            date_fin=timezone.localtime(self.e.date_fin).strftime("%Y-%m-%dT%H:%M"),
            capacite=self.e.capacite,
            prix=str(self.e.prix),
        ))
        self.assertEqual(r.status_code, 302)
        self.e.refresh_from_db()
        self.assertEqual(self.e.titre, "Titre mis à jour")

    def test_autre_organisateur_refuse(self):
        self.client.login(username="autre_org", password=self.password)
        r = self.client.post(reverse("evenements:modifier", args=[self.e.pk]), self.payload(titre="Piraté"))
        self.assertEqual(r.status_code, 403)
        self.e.refresh_from_db()
        self.assertEqual(self.e.titre, "À modifier")

    def test_participant_refuse(self):
        self.client.login(username="part", password=self.password)
        r = self.client.get(reverse("evenements:modifier", args=[self.e.pk]))
        self.assertEqual(r.status_code, 403)

    def test_anonyme_redirige(self):
        url = reverse("evenements:modifier", args=[self.e.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("utilisateurs:login"), r.url)

    def test_donnees_invalides_rejetees(self):
        self.client.login(username="org", password=self.password)
        debut = timezone.localtime(self.e.date_debut)
        r = self.client.post(reverse("evenements:modifier", args=[self.e.pk]), self.payload(
            titre="Titre invalide",
            date_debut=debut.strftime("%Y-%m-%dT%H:%M"),
            date_fin=(debut - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        ))
        self.assertEqual(r.status_code, 200)
        self.e.refresh_from_db()
        self.assertEqual(self.e.titre, "À modifier")
        self.assertTrue(r.context["form"].errors)


class AnnulationEvenementTests(BaseEvenement):
    """US 2.4.3 — annulation, droits, réservation bloquée, événement inexistant."""

    def setUp(self):
        super().setUp()
        self.e = self.creer("À annuler", statut=Evenement.Statut.PUBLIE)

    def test_proprietaire_annule(self):
        self.client.login(username="org", password=self.password)
        r = self.client.post(reverse("evenements:annuler", args=[self.e.pk]))
        self.assertEqual(r.status_code, 302)
        self.e.refresh_from_db()
        self.assertEqual(self.e.statut, Evenement.Statut.ANNULE)

    def test_droits_insuffisants(self):
        self.client.login(username="autre_org", password=self.password)
        self.assertEqual(self.client.post(reverse("evenements:annuler", args=[self.e.pk])).status_code, 403)
        self.client.logout()
        self.client.login(username="part", password=self.password)
        self.assertEqual(self.client.post(reverse("evenements:annuler", args=[self.e.pk])).status_code, 403)
        self.client.logout()
        r = self.client.post(reverse("evenements:annuler", args=[self.e.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("utilisateurs:login"), r.url)
        self.e.refresh_from_db()
        self.assertEqual(self.e.statut, Evenement.Statut.PUBLIE)

    def test_reservation_impossible_si_annule(self):
        self.e.annuler()
        self.client.login(username="part", password=self.password)
        r = self.client.post(reverse("participants:inscrire", args=[self.e.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Inscription.objects.filter(evenement=self.e, participant=self.part).exists())
        with self.assertRaises(ValidationError):
            Inscription.inscrire(self.e, self.part)

    def test_evenement_inexistant(self):
        self.client.login(username="org", password=self.password)
        self.assertEqual(self.client.post(reverse("evenements:annuler", args=[999999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("evenements:supprimer", args=[999999])).status_code, 404)
