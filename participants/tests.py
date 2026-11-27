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


# ---------------------------------------------------------------------------------------------
# CRUD complets de la gestion des participants (types de billets, inscriptions, avis)
# ---------------------------------------------------------------------------------------------
from django.urls import reverse  # noqa: E402

from .models import Avis, TypeBillet  # noqa: E402

MDP = "Test12345!"


class GestionBase(TestCase):
    """Jeu de données commun : un admin, deux organisateurs (chacun son événement), deux participants."""

    def setUp(self):
        mk = Utilisateur.objects.create_user
        self.admin = mk("adm", password=MDP, role="ADMIN")
        self.org = mk("org", password=MDP, role="ORGANISATEUR")
        self.org2 = mk("org2", password=MDP, role="ORGANISATEUR")
        self.a = mk("a", password=MDP)
        self.b = mk("b", password=MDP)
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Concert")
        d = timezone.now() + timedelta(days=3)
        self.e = Evenement.objects.create(titre="Festival", categorie=cat, lieu=lieu, organisateur=self.org, date_debut=d,
                                          date_fin=d + timedelta(hours=2), capacite=10, prix=20, statut="PUBLIE")
        self.e2 = Evenement.objects.create(titre="Autre soirée", categorie=cat, lieu=lieu, organisateur=self.org2,
                                           date_debut=d, date_fin=d + timedelta(hours=2), capacite=10, prix=5, statut="PUBLIE")
        self.vip = TypeBillet.objects.create(evenement=self.e, nom="VIP", prix=50, quota=5)
        self.std = TypeBillet.objects.create(evenement=self.e, nom="Standard", prix=10)
        self.autre_type = TypeBillet.objects.create(evenement=self.e2, nom="Secret", prix=1)

    def login(self, nom):
        self.assertTrue(self.client.login(username=nom, password=MDP))

    def termine(self, evenement=None):
        """Rend l'événement terminé (pour les avis)."""
        Evenement.objects.filter(pk=(evenement or self.e).pk).update(
            date_debut=timezone.now() - timedelta(days=2), date_fin=timezone.now() - timedelta(days=1))


class TypeBilletListeTests(GestionBase):
    url = "participants:typebillet_liste"

    def test_organisateur_voit_ses_types_avec_vendus_et_restants(self):
        Inscription.inscrire(self.e, self.a, self.vip, 2)
        self.login("org")
        r = self.client.get(reverse(self.url))
        self.assertEqual(r.status_code, 200)
        noms = [t.nom for t in r.context["object_list"]]
        self.assertCountEqual(noms, ["VIP", "Standard"])          # jamais « Secret » (autre organisateur)
        vip = next(t for t in r.context["object_list"] if t.nom == "VIP")
        self.assertEqual((vip.nb_vendus, vip.reste), (2, 3))
        std = next(t for t in r.context["object_list"] if t.nom == "Standard")
        self.assertIsNone(std.reste)                               # quota illimité

    def test_admin_voit_tous_les_types(self):
        self.login("adm")
        r = self.client.get(reverse(self.url))
        self.assertEqual(len(r.context["object_list"]), 3)

    def test_filtre_par_evenement_et_recherche(self):
        self.login("adm")
        r = self.client.get(reverse(self.url), {"evenement": self.e2.pk})
        self.assertEqual([t.nom for t in r.context["object_list"]], ["Secret"])
        r = self.client.get(reverse(self.url), {"q": "vip"})
        self.assertEqual([t.nom for t in r.context["object_list"]], ["VIP"])
        r = self.client.get(reverse(self.url), {"evenement": "abc"})   # paramètre invalide : ignoré
        self.assertEqual(r.status_code, 200)

    def test_pagination(self):
        for i in range(12):
            TypeBillet.objects.create(evenement=self.e, nom=f"T{i}", prix=i)
        self.login("org")
        r = self.client.get(reverse(self.url))
        self.assertTrue(r.context["is_paginated"])
        self.assertEqual(self.client.get(reverse(self.url), {"page": 2}).status_code, 200)

    def test_refus_participant_et_anonyme(self):
        self.login("a")
        self.assertEqual(self.client.get(reverse(self.url)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse(self.url)).status_code, 302)

    def test_sous_lien_dans_le_menu(self):
        self.login("org")
        r = self.client.get(reverse("participants:index"))
        self.assertContains(r, reverse(self.url))


class TypeBilletModificationTests(GestionBase):
    def url_mod(self, t=None):
        return reverse("participants:typebillet_modifier", args=[(t or self.vip).pk])

    def url_sup(self, t=None):
        return reverse("participants:typebillet_supprimer", args=[(t or self.vip).pk])

    def donnees(self, **kw):
        d = {"nom": "VIP", "description": "", "prix": "50", "quota": "5"}
        d.update(kw)
        return d

    # --- modification ---
    def test_modification_par_organisateur(self):
        self.login("org")
        self.assertEqual(self.client.get(self.url_mod()).status_code, 200)
        r = self.client.post(self.url_mod(), self.donnees(nom="VIP Gold", prix="60"))
        self.assertRedirects(r, reverse("participants:typebillet_liste"))
        self.vip.refresh_from_db()
        self.assertEqual((self.vip.nom, self.vip.prix), ("VIP Gold", 60))

    def test_modification_par_admin(self):
        self.login("adm")
        self.assertEqual(self.client.post(self.url_mod(), self.donnees(nom="X")).status_code, 302)

    def test_quota_inferieur_aux_vendus_refuse(self):
        Inscription.inscrire(self.e, self.a, self.vip, 3)
        self.login("org")
        r = self.client.post(self.url_mod(), self.donnees(quota="2"))
        self.assertContains(r, "déjà vendus")
        self.vip.refresh_from_db()
        self.assertEqual(self.vip.quota, 5)
        self.assertEqual(self.client.post(self.url_mod(), self.donnees(quota="3")).status_code, 302)   # égal aux vendus : OK
        self.assertEqual(self.client.post(self.url_mod(), self.donnees(quota="")).status_code, 302)    # sans limite : OK

    def test_modification_refusee(self):
        self.login("org2")                                           # organisateur d'un autre événement
        self.assertEqual(self.client.get(self.url_mod()).status_code, 403)
        self.assertEqual(self.client.post(self.url_mod(), self.donnees(nom="Piraté")).status_code, 403)
        self.vip.refresh_from_db()
        self.assertEqual(self.vip.nom, "VIP")
        self.client.logout()
        self.login("a")                                              # simple participant
        self.assertEqual(self.client.get(self.url_mod()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url_mod()).status_code, 302)   # anonyme -> connexion

    # --- suppression ---
    def test_suppression_avec_confirmation(self):
        self.login("org")
        r = self.client.get(self.url_sup(self.std))
        self.assertContains(r, "Oui, supprimer")
        self.assertTrue(TypeBillet.objects.filter(pk=self.std.pk).exists())     # GET ne supprime rien
        r = self.client.post(self.url_sup(self.std), follow=True)
        self.assertRedirects(r, reverse("participants:typebillet_liste"))
        self.assertFalse(TypeBillet.objects.filter(pk=self.std.pk).exists())
        self.assertContains(r, "a été supprimé")

    def test_suppression_bloquee_par_protect_avec_message(self):
        Inscription.inscrire(self.e, self.a, self.vip, 1)
        self.login("org")
        r = self.client.post(self.url_sup(), follow=True)
        self.assertEqual(r.status_code, 200)                          # pas d'erreur 500
        self.assertTrue(TypeBillet.objects.filter(pk=self.vip.pk).exists())
        self.assertContains(r, "Impossible de supprimer")

    def test_suppression_refusee(self):
        self.login("org2")
        self.assertEqual(self.client.get(self.url_sup()).status_code, 403)
        self.assertEqual(self.client.post(self.url_sup()).status_code, 403)
        self.client.logout()
        self.login("a")
        self.assertEqual(self.client.post(self.url_sup()).status_code, 403)
        self.assertTrue(TypeBillet.objects.filter(pk=self.vip.pk).exists())

    def test_boutons_dans_la_liste(self):
        self.login("org")
        r = self.client.get(reverse("participants:typebillet_liste"))
        self.assertContains(r, self.url_mod())
        self.assertContains(r, self.url_sup())


class InscriptionsOrganisateurTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 2)
        self.ib = Inscription.inscrire(self.e2, self.b)
        self.e.capacite = 2
        self.e.save()
        self.ic = Inscription.inscrire(self.e, self.b)             # événement plein -> liste d'attente
        self.assertEqual(self.ic.statut, "ATTENTE")

    # --- liste d'un événement ---
    def test_liste_evenement_organisateur_avec_lien_billet(self):
        self.login("org")
        url = reverse("participants:liste", args=[self.e.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertCountEqual([i.pk for i in r.context["object_list"]], [self.ia.pk, self.ic.pk])
        self.assertContains(r, self.ia.get_absolute_url())                         # lien vers le billet
        self.assertContains(r, reverse("participants:inscription_detail", args=[self.ia.pk]))

    def test_liste_evenement_filtre_statut_et_recherche(self):
        self.login("org")
        url = reverse("participants:liste", args=[self.e.pk])
        r = self.client.get(url, {"statut": "ATTENTE"})
        self.assertEqual([i.pk for i in r.context["object_list"]], [self.ic.pk])
        r = self.client.get(url, {"q": "a"})
        self.assertIn(self.ia.pk, [i.pk for i in r.context["object_list"]])
        r = self.client.get(url, {"q": self.ia.code_court})                          # recherche par code de billet
        self.assertEqual([i.pk for i in r.context["object_list"]], [self.ia.pk])
        r = self.client.get(url, {"statut": "n'importe quoi"})                       # statut invalide : ignoré
        self.assertEqual(len(r.context["object_list"]), 2)

    def test_liste_evenement_pagination(self):
        self.e.capacite = 100
        self.e.save()
        for i in range(16):
            Inscription.inscrire(self.e, Utilisateur.objects.create_user(f"u{i}", password=MDP))
        self.login("org")
        r = self.client.get(reverse("participants:liste", args=[self.e.pk]))
        self.assertTrue(r.context["is_paginated"])
        self.assertEqual(self.client.get(reverse("participants:liste", args=[self.e.pk]), {"page": 2}).status_code, 200)

    def test_liste_evenement_refus(self):
        url = reverse("participants:liste", args=[self.e.pk])
        self.login("org2")
        self.assertEqual(self.client.get(url).status_code, 403)       # organisateur d'un autre événement
        self.client.logout()
        self.login("a")
        self.assertEqual(self.client.get(url).status_code, 403)       # participant
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)       # anonyme
        self.login("adm")
        self.assertEqual(self.client.get(url).status_code, 200)       # admin

    # --- liste globale ---
    def test_liste_globale_limitee_aux_evenements_geres(self):
        self.login("org")
        r = self.client.get(reverse("participants:inscription_liste"))
        self.assertEqual(r.status_code, 200)
        self.assertCountEqual([i.pk for i in r.context["object_list"]], [self.ia.pk, self.ic.pk])   # pas celle de e2
        self.client.logout()
        self.login("adm")
        r = self.client.get(reverse("participants:inscription_liste"))
        self.assertEqual(len(r.context["object_list"]), 3)

    def test_liste_globale_filtres(self):
        self.login("adm")
        url = reverse("participants:inscription_liste")
        r = self.client.get(url, {"evenement": self.e2.pk})
        self.assertEqual([i.pk for i in r.context["object_list"]], [self.ib.pk])
        r = self.client.get(url, {"statut": "ATTENTE"})
        self.assertEqual([i.pk for i in r.context["object_list"]], [self.ic.pk])
        r = self.client.get(url, {"q": "Autre soirée"})
        self.assertEqual([i.pk for i in r.context["object_list"]], [self.ib.pk])
        self.assertEqual(self.client.get(url, {"evenement": "zzz"}).status_code, 200)

    def test_liste_globale_refus(self):
        url = reverse("participants:inscription_liste")
        self.login("a")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    # --- détail ---
    def test_detail_organisateur_et_admin(self):
        url = reverse("participants:inscription_detail", args=[self.ia.pk])
        for nom in ("org", "adm"):
            self.client.logout()
            self.login(nom)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, self.ia.code_court)
            self.assertContains(r, "VIP")

    def test_detail_refus(self):
        url = reverse("participants:inscription_detail", args=[self.ia.pk])
        self.login("a")                                               # le participant lui-même passe par le billet
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.login("org2")                                            # organisateur d'un autre événement : introuvable
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_menu_contient_inscriptions(self):
        self.login("org")
        self.assertContains(self.client.get(reverse("participants:index")), reverse("participants:inscription_liste"))


class ActionsOrganisateurTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.e.capacite = 2
        self.e.save()
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 2)
        self.ib = Inscription.inscrire(self.e, self.b)
        self.assertEqual(self.ib.statut, "ATTENTE")

    def url_annuler(self, i=None):
        return reverse("participants:inscription_annuler", args=[(i or self.ia).pk])

    def url_checkin(self, i=None):
        return reverse("participants:inscription_checkin_annuler", args=[(i or self.ia).pk])

    # --- annulation par l'organisateur ---
    def test_annulation_passe_par_annuler_et_promeut_la_liste_d_attente(self):
        self.login("org")
        r = self.client.post(self.url_annuler(), follow=True)
        self.assertRedirects(r, reverse("participants:inscription_detail", args=[self.ia.pk]))
        self.assertContains(r, "annulée")
        self.ia.refresh_from_db()
        self.ib.refresh_from_db()
        self.assertEqual(self.ia.statut, "ANNULEE")
        self.assertTrue(Inscription.objects.filter(pk=self.ia.pk).exists())     # pas de suppression physique
        self.assertEqual(self.ib.statut, "CONFIRMEE")                           # liste d'attente promue

    def test_annulation_deja_annulee_ou_deja_entre(self):
        self.login("org")
        self.client.post(self.url_annuler())
        r = self.client.post(self.url_annuler(), follow=True)
        self.assertContains(r, "déjà annulée")
        Inscription.objects.filter(pk=self.ib.pk).update(statut="CONFIRMEE", present=True)
        r = self.client.post(self.url_annuler(self.ib), follow=True)
        self.assertContains(r, "annulez d&#x27;abord son check-in")
        self.ib.refresh_from_db()
        self.assertEqual(self.ib.statut, "CONFIRMEE")

    def test_annulation_admin_ok(self):
        self.login("adm")
        self.assertEqual(self.client.post(self.url_annuler()).status_code, 302)
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.statut, "ANNULEE")

    def test_annulation_refusee(self):
        self.login("org2")                                               # organisateur d'un autre événement
        self.assertEqual(self.client.post(self.url_annuler()).status_code, 404)
        self.client.logout()
        self.login("b")                                                  # un autre participant
        self.assertEqual(self.client.post(self.url_annuler()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url_annuler()).status_code, 302)
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.statut, "CONFIRMEE")

    def test_annulation_get_interdit(self):
        self.login("org")
        self.assertEqual(self.client.get(self.url_annuler()).status_code, 405)

    # --- annulation du check-in ---
    def test_annulation_checkin(self):
        Inscription.objects.filter(pk=self.ia.pk).update(present=True)
        self.login("org")
        r = self.client.post(self.url_checkin(), follow=True)
        self.assertContains(r, "Entrée de")
        self.ia.refresh_from_db()
        self.assertFalse(self.ia.present)
        r = self.client.post(self.url_checkin(), follow=True)              # déjà non présent
        self.assertContains(r, "pas marqué comme présent")

    def test_annulation_checkin_refusee(self):
        Inscription.objects.filter(pk=self.ia.pk).update(present=True)
        self.login("org2")
        self.assertEqual(self.client.post(self.url_checkin()).status_code, 404)
        self.client.logout()
        self.login("a")
        self.assertEqual(self.client.post(self.url_checkin()).status_code, 403)
        self.ia.refresh_from_db()
        self.assertTrue(self.ia.present)

    def test_boutons_sur_la_page_detail(self):
        Inscription.objects.filter(pk=self.ia.pk).update(present=True)
        self.login("org")
        r = self.client.get(reverse("participants:inscription_detail", args=[self.ia.pk]))
        self.assertContains(r, self.url_annuler())
        self.assertContains(r, self.url_checkin())


class AvisCrudTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.ia = Inscription.inscrire(self.e, self.a)
        self.ib = Inscription.inscrire(self.e2, self.b)
        self.avis_a = Avis.objects.create(inscription=self.ia, note=4, commentaire="Très bien")
        self.avis_b = Avis.objects.create(inscription=self.ib, note=2, commentaire="Bof")

    def url_mod(self, a=None):
        return reverse("participants:avis_modifier", args=[(a or self.avis_a).pk])

    def url_sup(self, a=None):
        return reverse("participants:avis_supprimer", args=[(a or self.avis_a).pk])

    # --- liste ---
    def test_liste_organisateur_limitee_a_ses_evenements(self):
        self.login("org")
        r = self.client.get(reverse("participants:avis_liste"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([a.pk for a in r.context["object_list"]], [self.avis_a.pk])
        self.assertEqual(r.context["moyenne"], 4)
        self.assertContains(r, self.url_sup())

    def test_liste_admin_filtres(self):
        self.login("adm")
        url = reverse("participants:avis_liste")
        self.assertEqual(len(self.client.get(url).context["object_list"]), 2)
        self.assertEqual([a.pk for a in self.client.get(url, {"evenement": self.e2.pk}).context["object_list"]], [self.avis_b.pk])
        self.assertEqual([a.pk for a in self.client.get(url, {"note": 4}).context["object_list"]], [self.avis_a.pk])
        self.assertEqual([a.pk for a in self.client.get(url, {"q": "bof"}).context["object_list"]], [self.avis_b.pk])
        self.assertEqual(self.client.get(url, {"note": "x", "evenement": "y"}).status_code, 200)

    def test_liste_pagination(self):
        for i in range(13):
            u = Utilisateur.objects.create_user(f"u{i}", password=MDP)
            Avis.objects.create(inscription=Inscription.inscrire(self.e, u), note=3)
        self.login("org")
        self.assertTrue(self.client.get(reverse("participants:avis_liste")).context["is_paginated"])

    def test_liste_refus(self):
        url = reverse("participants:avis_liste")
        self.login("a")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    # --- modification par l'auteur ---
    def test_modification_par_auteur(self):
        self.login("a")
        self.assertEqual(self.client.get(self.url_mod()).status_code, 200)
        r = self.client.post(self.url_mod(), {"note": 5, "commentaire": "Excellent"})
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.avis_a.refresh_from_db()
        self.assertEqual((self.avis_a.note, self.avis_a.commentaire), (5, "Excellent"))

    def test_modification_note_invalide(self):
        self.login("a")
        r = self.client.post(self.url_mod(), {"note": 6, "commentaire": "x"})
        self.assertEqual(r.status_code, 200)
        self.avis_a.refresh_from_db()
        self.assertEqual(self.avis_a.note, 4)

    def test_modification_refusee_aux_autres(self):
        for nom in ("b", "org", "adm"):                                   # ni autre participant, ni organisateur, ni admin
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.get(self.url_mod()).status_code, 403, nom)
            self.assertEqual(self.client.post(self.url_mod(), {"note": 1, "commentaire": "x"}).status_code, 403, nom)
        self.client.logout()
        self.assertEqual(self.client.get(self.url_mod()).status_code, 302)
        self.avis_a.refresh_from_db()
        self.assertEqual(self.avis_a.note, 4)

    # --- suppression ---
    def test_suppression_par_auteur(self):
        self.login("a")
        self.assertContains(self.client.get(self.url_sup()), "Oui, supprimer")
        r = self.client.post(self.url_sup(), follow=True)
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.assertFalse(Avis.objects.filter(pk=self.avis_a.pk).exists())
        self.assertContains(r, "a été supprimé")

    def test_moderation_par_organisateur_et_admin(self):
        self.login("org")
        r = self.client.post(self.url_sup(), follow=True)
        self.assertRedirects(r, reverse("participants:avis_liste"))
        self.assertFalse(Avis.objects.filter(pk=self.avis_a.pk).exists())
        self.client.logout()
        self.login("adm")
        self.assertEqual(self.client.post(self.url_sup(self.avis_b)).status_code, 302)
        self.assertFalse(Avis.objects.filter(pk=self.avis_b.pk).exists())

    def test_suppression_refusee(self):
        self.login("org2")                                               # organisateur d'un autre evenement
        self.assertEqual(self.client.post(self.url_sup()).status_code, 403)
        self.client.logout()
        self.login("b")                                                  # participant qui n'est pas l'auteur
        self.assertEqual(self.client.post(self.url_sup()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url_sup()).status_code, 302)
        self.assertTrue(Avis.objects.filter(pk=self.avis_a.pk).exists())

    def test_nouvel_avis_possible_apres_suppression(self):
        self.termine()
        self.login("a")
        self.client.post(self.url_sup())
        r = self.client.post(reverse("participants:avis", args=[self.ia.pk]), {"note": 3, "commentaire": "Revu"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Inscription.objects.get(pk=self.ia.pk).avis.note, 3)

    # --- creation : doublon et inscription d'un autre (non-regression) ---
    def test_creation_doublon_refusee(self):
        self.termine()
        self.login("a")
        r = self.client.post(reverse("participants:avis", args=[self.ia.pk]), {"note": 1, "commentaire": "Encore"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Avis.objects.filter(inscription=self.ia).count(), 1)

    def test_creation_pour_inscription_d_un_autre_refusee(self):
        self.termine()
        ic = Inscription.inscrire(self.e, self.b)
        self.login("a")
        r = self.client.post(reverse("participants:avis", args=[ic.pk]), {"note": 1, "commentaire": "Intrus"})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Avis.objects.filter(inscription=ic).exists())

    # --- lien dans « Mes billets » ---
    def test_lien_avis_dans_mes_billets(self):
        Avis.objects.filter(pk=self.avis_a.pk).delete()
        self.login("a")
        url = reverse("participants:mes_inscriptions")
        lien = reverse("participants:avis", args=[self.ia.pk])
        self.assertNotContains(self.client.get(url), lien)               # evenement a venir, pas de check-in
        self.termine()
        self.assertContains(self.client.get(url), lien)                  # evenement termine, sans check-in : lien visible
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() + timedelta(days=3),
                                                      date_fin=timezone.now() + timedelta(days=4))
        self.assertNotContains(self.client.get(url), lien)
        Inscription.objects.filter(pk=self.ia.pk).update(present=True)
        self.assertContains(self.client.get(url), lien)                  # check-in effectue : lien visible

    def test_liens_modifier_supprimer_dans_mes_billets(self):
        self.login("a")
        r = self.client.get(reverse("participants:mes_inscriptions"))
        self.assertContains(r, self.url_mod())
        self.assertContains(r, self.url_sup())
        self.assertNotContains(r, reverse("participants:avis", args=[self.ia.pk]))

    def test_propriete_peut_donner_avis(self):
        Avis.objects.filter(pk=self.avis_a.pk).delete()
        i = Inscription.objects.get(pk=self.ia.pk)
        self.assertFalse(i.peut_donner_avis)
        i.present = True
        self.assertTrue(i.peut_donner_avis)
        i.statut = "ANNULEE"
        self.assertFalse(i.peut_donner_avis)


class TypeBilletCreationTests(GestionBase):
    def url(self, e=None):
        return reverse("participants:type_creer", args=[(e or self.e).pk])

    def test_creation_par_organisateur(self):
        self.login("org")
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        r = self.client.post(self.url(), {"nom": "Étudiant", "description": "Sur justificatif", "prix": "8", "quota": "30"})
        self.assertRedirects(r, self.e.get_absolute_url())
        t = TypeBillet.objects.get(nom="Étudiant")
        self.assertEqual((t.evenement, t.prix, t.quota), (self.e, 8, 30))

    def test_creation_par_admin(self):
        self.login("adm")
        r = self.client.post(self.url(self.e2), {"nom": "Gratuit", "prix": "0", "quota": ""})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(TypeBillet.objects.filter(nom="Gratuit", evenement=self.e2).exists())

    def test_prix_negatif_refuse_par_le_formulaire(self):
        self.login("org")
        r = self.client.post(self.url(), {"nom": "Négatif", "prix": "-5", "quota": ""})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(TypeBillet.objects.filter(nom="Négatif").exists())

    def test_creation_refusee(self):
        self.login("org2")                                               # organisateur d'un autre evenement
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), {"nom": "Pirate", "prix": "1"}).status_code, 403)
        self.client.logout()
        self.login("a")                                                  # simple participant
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)   # anonyme -> connexion
        self.assertFalse(TypeBillet.objects.filter(nom="Pirate").exists())


class BilletTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.i = Inscription.inscrire(self.e, self.a)

    def test_acces_autorises(self):
        for nom in ("a", "org", "adm"):                                  # participant, organisateur de l'evenement, admin
            self.client.logout()
            self.login(nom)
            r = self.client.get(self.i.get_absolute_url())
            self.assertEqual(r.status_code, 200, nom)
            self.assertContains(r, self.i.code_court)

    def test_acces_refuses(self):
        self.login("b")                                                  # autre participant
        self.assertEqual(self.client.get(self.i.get_absolute_url()).status_code, 404)
        self.client.logout()
        self.login("org2")                                               # organisateur d'un autre evenement
        self.assertEqual(self.client.get(self.i.get_absolute_url()).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.i.get_absolute_url()).status_code, 302)


class AnnulationParticipantTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.e.capacite = 1
        self.e.save()
        self.ia = Inscription.inscrire(self.e, self.a)
        self.ib = Inscription.inscrire(self.e, self.b)
        self.assertEqual(self.ib.statut, "ATTENTE")
        self.url = reverse("participants:annuler", args=[self.ia.pk])

    def test_annulation_reussie_et_promotion(self):
        self.login("a")
        r = self.client.post(self.url, follow=True)
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.assertContains(r, "Inscription annulée")
        self.ia.refresh_from_db()
        self.ib.refresh_from_db()
        self.assertEqual(self.ia.statut, "ANNULEE")                      # changement de statut, pas de suppression
        self.assertTrue(Inscription.objects.filter(pk=self.ia.pk).exists())
        self.assertEqual(self.ib.statut, "CONFIRMEE")                    # la liste d'attente est promue

    def test_annulation_deja_annulee(self):
        self.login("a")
        self.client.post(self.url)
        self.assertContains(self.client.post(self.url, follow=True), "déjà annulée")

    def test_annulation_refusee_pour_un_autre_utilisateur(self):
        for nom in ("b", "org", "adm"):                                  # seul le participant concerne peut annuler ici
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.post(self.url).status_code, 404, nom)
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.statut, "CONFIRMEE")



class AccesModuleParticipantsTests(GestionBase):
    """Accès (autorisé / refusé) aux pages historiques du module : check-in, synthèse, Mes billets."""

    def test_checkin_acces(self):
        url = reverse("participants:checkin", args=[self.e.pk])
        for nom, code in (("org", 200), ("adm", 200), ("org2", 403), ("a", 403)):
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.get(url).status_code, code, nom)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_synthese_acces(self):
        url = reverse("participants:index")
        self.login("a")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.login("org")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_mes_billets_ne_montre_que_ses_inscriptions(self):
        ia = Inscription.inscrire(self.e, self.a)
        ib = Inscription.inscrire(self.e, self.b)
        self.login("a")
        r = self.client.get(reverse("participants:mes_inscriptions"))
        self.assertEqual([i.pk for i in r.context["object_list"]], [ia.pk])
        self.assertNotContains(r, ib.code_court)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("participants:mes_inscriptions")).status_code, 302)


# ---------------------------------------------------------------------------------------------
# Pages de détail, modification / annulation avec confirmation par le participant, parcours complet
# ---------------------------------------------------------------------------------------------
from unittest import mock  # noqa: E402


class DetailsTests(GestionBase):
    def test_detail_type_billet(self):
        Inscription.inscrire(self.e, self.a, self.vip, 2)
        url = reverse("participants:typebillet_detail", args=[self.vip.pk])
        for nom in ("org", "adm"):
            self.client.logout()
            self.login(nom)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, nom)
            self.assertEqual(r.context["object"].vendus, 2)
            self.assertEqual(len(r.context["inscriptions"]), 1)
            self.assertContains(r, "Billets restants")
            self.assertContains(r, reverse("participants:typebillet_modifier", args=[self.vip.pk]))

    def test_detail_type_billet_refus(self):
        url = reverse("participants:typebillet_detail", args=[self.vip.pk])
        self.login("org2")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.login("a")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_liste_types_lie_vers_le_detail(self):
        self.login("org")
        self.assertContains(self.client.get(reverse("participants:typebillet_liste")),
                            reverse("participants:typebillet_detail", args=[self.vip.pk]))

    def test_detail_avis(self):
        i = Inscription.inscrire(self.e, self.a)
        avis = Avis.objects.create(inscription=i, note=5, commentaire="Génial")
        url = reverse("participants:avis_detail", args=[avis.pk])
        modifier = reverse("participants:avis_modifier", args=[avis.pk])
        self.login("a")                                                  # auteur : peut modifier
        r = self.client.get(url)
        self.assertContains(r, "Génial")
        self.assertContains(r, modifier)
        for nom in ("org", "adm"):                                       # modération : voit, ne modifie pas
            self.client.logout()
            self.login(nom)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, nom)
            self.assertNotContains(r, modifier)
            self.assertContains(r, reverse("participants:avis_supprimer", args=[avis.pk]))

    def test_detail_avis_refus(self):
        avis = Avis.objects.create(inscription=Inscription.inscrire(self.e, self.a), note=5)
        url = reverse("participants:avis_detail", args=[avis.pk])
        for nom in ("org2", "b"):
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.get(url).status_code, 403, nom)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)


class ModificationReservationTests(GestionBase):
    """Le participant modifie sa réservation (type de billet / quantité) : règles de Inscription.modifier()."""

    def setUp(self):
        super().setUp()
        self.e.capacite = 5
        self.e.save()
        self.vip.quota = 3
        self.vip.save()
        self.ia = Inscription.inscrire(self.e, self.a, self.std, 2)      # 20 DT
        self.ib = Inscription.inscrire(self.e, self.b, self.std, 1)

    def url(self, i=None):
        return reverse("participants:inscription_modifier", args=[(i or self.ia).pk])

    def poster(self, type_billet, quantite, i=None):
        return self.client.post(self.url(i), {"type_billet": type_billet.pk if type_billet else "", "quantite": quantite})

    # --- succès et montant ---
    def test_modification_reussie_et_montant_recalcule(self):
        code = self.ia.code_billet
        self.login("a")
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        r = self.poster(self.vip, 2)                                     # Standard x2 (20) -> VIP x2 (100)
        self.assertRedirects(r, self.ia.get_absolute_url())
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.type_billet, self.ia.quantite, self.ia.montant), (self.vip, 2, 100))
        self.assertEqual(self.ia.code_billet, code)                      # même billet
        self.assertEqual(self.ia.statut, "CONFIRMEE")
        self.poster(self.std, 4)                                         # -> Standard x4 (40)
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.quantite, self.ia.montant), (4, 40))

    def test_modification_evenement_sans_types(self):
        e3 = Evenement.objects.create(titre="Libre", categorie=self.e.categorie, lieu=self.e.lieu, organisateur=self.org,
                                      date_debut=self.e.date_debut, date_fin=self.e.date_fin, capacite=10, prix=20, statut="PUBLIE")
        i = Inscription.inscrire(e3, self.a)
        self.login("a")
        r = self.client.post(self.url(i), {"quantite": 3})
        self.assertEqual(r.status_code, 302)
        i.refresh_from_db()
        self.assertEqual((i.type_billet, i.quantite, i.montant), (None, 3, 60))

    def test_modification_identique_ne_change_rien(self):
        self.login("a")
        r = self.poster(self.std, 2, self.ia)
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.quantite, self.ia.montant), (2, 20))

    def test_formulaire_invalide(self):
        self.login("a")
        self.assertEqual(self.poster(self.std, 11).status_code, 200)     # plus de 10 places
        self.assertEqual(self.poster(self.autre_type, 1).status_code, 200)   # type d'un autre evenement
        self.assertEqual(self.poster(None, 1).status_code, 200)          # type obligatoire
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.type_billet, self.ia.quantite), (self.std, 2))

    # --- refus : places et quotas ---
    def test_refus_si_plus_assez_de_places(self):
        Inscription.inscrire(self.e, Utilisateur.objects.create_user("c", password=MDP), self.std, 2)   # 2+1+2 = 5 : complet
        self.login("a")
        r = self.poster(self.std, 4)                                     # 2 actuelles + 0 libre = 2 maximum
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Plus assez de places")
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.quantite, self.ia.montant), (2, 20))
        self.assertEqual(self.poster(self.std, 2).status_code, 302)      # inchange : accepte (aucune modification)

    def test_une_modification_ne_met_jamais_en_liste_d_attente(self):
        self.login("a")
        self.poster(self.std, 4)                                         # 4 + 1 = 5 : tient pile
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.quantite, self.ia.statut), (4, "CONFIRMEE"))
        with self.assertRaises(ValidationError):
            self.ia.modifier(self.std, 5)                                # 5 + 1 > 5
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.quantite, self.ia.statut), (4, "CONFIRMEE"))

    def test_refus_si_quota_du_type_insuffisant(self):
        Inscription.inscrire(self.e, Utilisateur.objects.create_user("c", password=MDP), self.vip, 2)   # reste 1 VIP
        self.login("a")
        r = self.poster(self.vip, 2)
        self.assertContains(r, "Il ne reste que 1 billet(s)")
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.type_billet, self.std)
        self.assertEqual(self.poster(self.vip, 1).status_code, 302)      # 1 VIP : OK

    def test_quota_du_meme_type_compte_ses_propres_places(self):
        self.ia.modifier(self.vip, 2)                                    # VIP x2 sur un quota de 3
        self.ia.modifier(self.vip, 3)                                    # +1 : tient (restants 1 + ses 2 places)
        self.assertEqual(self.ia.quantite, 3)
        with self.assertRaises(ValidationError):
            self.ia.modifier(self.vip, 4)

    # --- refus : etat de la reservation et proprietaire ---
    def test_refus_apres_le_debut(self):
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() - timedelta(hours=1))
        self.login("a")
        r = self.client.get(self.url(), follow=True)
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.assertContains(r, "a déjà commencé")
        self.assertEqual(self.poster(self.vip, 1).status_code, 302)
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.type_billet, self.ia.quantite), (self.std, 2))
        with self.assertRaises(ValidationError):                         # protection aussi dans le modele
            self.ia.modifier(self.vip, 1)

    def test_refus_reservation_annulee(self):
        self.ia.annuler()
        self.login("a")
        r = self.client.get(self.url(), follow=True)
        self.assertContains(r, "annulée ne peut pas être modifiée")
        with self.assertRaises(ValidationError):
            self.ia.modifier(self.vip, 1)

    def test_refus_pour_un_autre_utilisateur(self):
        for nom in ("b", "org", "adm"):                                  # ni autre participant, ni organisateur, ni admin
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.get(self.url()).status_code, 404, nom)
            self.assertEqual(self.poster(self.vip, 1).status_code, 404, nom)
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)
        self.ia.refresh_from_db()
        self.assertEqual((self.ia.type_billet, self.ia.quantite), (self.std, 2))

    # --- liste d'attente ---
    def test_promotion_de_la_liste_d_attente_quand_la_quantite_diminue(self):
        c = Utilisateur.objects.create_user("c", password=MDP)
        self.e.capacite = 4
        self.e.save()
        self.ia.modifier(self.std, 3)                                    # 3 + 1 = 4 : complet
        ic = Inscription.inscrire(self.e, c, self.std, 2)
        self.assertEqual(ic.statut, "ATTENTE")
        self.login("a")
        self.assertEqual(self.poster(self.std, 1).status_code, 302)      # libere 2 places
        ic.refresh_from_db()
        self.assertEqual(ic.statut, "CONFIRMEE")
        self.assertEqual(self.e.places_restantes, 0)

    def test_promotion_respecte_l_ordre_et_la_taille(self):
        c = Utilisateur.objects.create_user("c", password=MDP)
        d = Utilisateur.objects.create_user("d", password=MDP)
        self.e.capacite = 4
        self.e.save()
        self.ia.modifier(self.std, 3)
        ic = Inscription.inscrire(self.e, c, self.std, 3)                # attend 3 places
        id_ = Inscription.inscrire(self.e, d, self.std, 1)               # attend 1 place
        self.assertEqual((ic.statut, id_.statut), ("ATTENTE", "ATTENTE"))
        self.ia.modifier(self.std, 2)                                    # libere 1 place seulement
        ic.refresh_from_db()
        id_.refresh_from_db()
        self.assertEqual(ic.statut, "ATTENTE")                           # ne tient pas : reste en attente
        self.assertEqual(id_.statut, "CONFIRMEE")                        # la suivante, plus petite, tient

    def test_promotion_respecte_le_quota_du_type(self):
        c = Utilisateur.objects.create_user("c", password=MDP)
        self.e.capacite = 5
        self.e.save()
        self.ia.modifier(self.vip, 3)                                    # VIP epuise (quota 3)
        ic = Inscription.objects.create(evenement=self.e, participant=c, type_billet=self.vip, quantite=1, statut="ATTENTE")
        self.ia.modifier(self.std, 3)                                    # libere le quota VIP
        ic.refresh_from_db()
        self.assertEqual(ic.statut, "CONFIRMEE")                         # un changement de type libere aussi le quota

    def test_modification_d_une_reservation_en_attente(self):
        c = Utilisateur.objects.create_user("c", password=MDP)
        self.e.capacite = 3
        self.e.save()                                                    # a(2) + b(1) = 3 : complet
        ic = Inscription.inscrire(self.e, c, self.std, 1)
        self.assertEqual(ic.statut, "ATTENTE")
        ic.modifier(self.std, 2)                                         # reste en attente, montant recalcule
        ic.refresh_from_db()
        self.assertEqual((ic.statut, ic.quantite, ic.montant), ("ATTENTE", 2, 20))

    # --- interface ---
    def test_bouton_modifier_dans_mes_inscriptions(self):
        self.login("a")
        r = self.client.get(reverse("participants:mes_inscriptions"))
        self.assertContains(r, self.url())
        self.ia.annuler()
        self.assertNotContains(self.client.get(reverse("participants:mes_inscriptions")), self.url())
        Inscription.objects.filter(pk=self.ia.pk).update(statut="CONFIRMEE")
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() - timedelta(hours=1))
        self.assertNotContains(self.client.get(reverse("participants:mes_inscriptions")), self.url())


class AnnulationAvecConfirmationTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 2)
        self.url = reverse("participants:annuler", args=[self.ia.pk])

    def test_get_affiche_la_confirmation_sans_annuler(self):
        self.login("a")
        with mock.patch.object(Inscription, "annuler", autospec=True) as annuler:
            r = self.client.get(self.url)
            annuler.assert_not_called()
        self.assertContains(r, "Annuler cette réservation ?")
        self.assertContains(r, "Oui, annuler ma réservation")
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.statut, "CONFIRMEE")

    def test_post_annule_via_inscription_annuler(self):
        self.login("a")
        with mock.patch.object(Inscription, "annuler", autospec=True) as annuler:
            r = self.client.post(self.url)
            annuler.assert_called_once()
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))

    def test_post_reel_change_le_statut_et_promeut(self):
        self.e.capacite = 2
        self.e.save()
        ib = Inscription.inscrire(self.e, self.b, self.std, 1)
        self.assertEqual(ib.statut, "ATTENTE")
        self.login("a")
        self.client.post(self.url)
        self.ia.refresh_from_db()
        ib.refresh_from_db()
        self.assertEqual((self.ia.statut, ib.statut), ("ANNULEE", "CONFIRMEE"))

    def test_get_refuse_si_deja_annulee_ou_commence(self):
        self.login("a")
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() - timedelta(hours=1))
        self.assertContains(self.client.get(self.url, follow=True), "a déjà commencé")
        Evenement.objects.filter(pk=self.e.pk).update(date_debut=timezone.now() + timedelta(days=3))
        self.client.post(self.url)
        self.assertContains(self.client.get(self.url, follow=True), "déjà annulée")

    def test_refus_pour_un_autre_utilisateur(self):
        for nom in ("b", "org", "adm"):
            self.client.logout()
            self.login(nom)
            self.assertEqual(self.client.get(self.url).status_code, 404, nom)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_mes_inscriptions_renvoie_vers_la_confirmation(self):
        self.login("a")
        r = self.client.get(reverse("participants:mes_inscriptions"))
        self.assertContains(r, f'href="{self.url}"')
        self.assertNotContains(r, f'action="{self.url}"')                # plus de bouton d'annulation direct


class ParcoursReservationTests(GestionBase):
    """Parcours complet : formulaire -> verification -> recapitulatif -> confirmation -> billet (non-regression)."""

    def url(self, e=None):
        return reverse("participants:reserver", args=[(e or self.e).pk])

    def sans_types(self, prix=15, capacite=10):
        return Evenement.objects.create(titre="Libre", categorie=self.e.categorie, lieu=self.e.lieu, organisateur=self.org,
                                        date_debut=self.e.date_debut, date_fin=self.e.date_fin, capacite=capacite,
                                        prix=prix, statut="PUBLIE")

    def test_parcours_complet_avec_types_de_billets(self):
        self.login("a")
        r = self.client.get(self.url())                                  # 1. formulaire
        self.assertTemplateUsed(r, "participants/reservation_choix.html")
        r = self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 0})        # erreurs
        self.assertTemplateUsed(r, "participants/reservation_choix.html")
        self.assertTrue(r.context["form"].errors)
        r = self.client.post(self.url(), {"quantite": 2})                # type de billet manquant
        self.assertTemplateUsed(r, "participants/reservation_choix.html")
        self.assertIn("type_billet", r.context["form"].errors)
        self.assertFalse(Inscription.objects.exists())

        r = self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 3})        # 2. recapitulatif
        self.assertTemplateUsed(r, "participants/reservation_recap.html")
        self.assertEqual(r.context["total"], 30)
        self.assertFalse(r.context["complet"])
        self.assertFalse(Inscription.objects.exists())                   # rien n'est cree avant la confirmation

        r = self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 3, "etape": "confirmer"})   # 3.
        i = Inscription.objects.get(participant=self.a)
        self.assertRedirects(r, i.get_absolute_url())                    # -> billet
        self.assertEqual((i.type_billet, i.quantite, i.montant, i.statut), (self.std, 3, 30, "CONFIRMEE"))
        r = self.client.get(i.get_absolute_url())
        self.assertTemplateUsed(r, "participants/billet.html")
        self.assertContains(r, 'id="qr"')                                # QR code
        self.assertContains(r, str(i.code_billet))
        self.assertEqual(self.e.places_restantes, 7)

    def test_parcours_sans_types_utilise_le_prix_de_l_evenement(self):
        e3 = self.sans_types(prix=15)
        self.login("a")
        r = self.client.post(self.url(e3), {"quantite": 2})
        self.assertEqual(r.context["total"], 30)
        self.client.post(self.url(e3), {"quantite": 2, "etape": "confirmer"})
        i = Inscription.objects.get(participant=self.a, evenement=e3)
        self.assertEqual((i.type_billet, i.quantite, i.montant, i.statut), (None, 2, 30, "CONFIRMEE"))

    def test_inscription_simple_sans_types(self):
        e3 = self.sans_types(prix=15)
        self.login("a")
        r = self.client.post(reverse("participants:inscrire", args=[e3.pk]))
        i = Inscription.objects.get(participant=self.a, evenement=e3)
        self.assertRedirects(r, i.get_absolute_url())
        self.assertEqual((i.quantite, i.montant), (1, 15))

    def test_evenement_complet_liste_d_attente(self):
        self.e.capacite = 2
        self.e.save()
        Inscription.inscrire(self.e, self.a, self.std, 2)                # l'evenement est plein
        self.login("b")
        r = self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 1})
        self.assertTrue(r.context["complet"])                            # le recapitulatif prévient
        self.assertContains(r, "liste d'attente")
        r = self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 1, "etape": "confirmer"})
        i = Inscription.objects.get(participant=self.b)
        self.assertRedirects(r, i.get_absolute_url())
        self.assertEqual((i.statut, i.montant), ("ATTENTE", 10))
        self.assertContains(self.client.get(i.get_absolute_url()), "Liste d&#x27;attente")
        self.assertEqual(self.e.places_restantes, 0)

    def test_deja_reserve_refuse(self):
        self.login("a")
        self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 1, "etape": "confirmer"})
        i = Inscription.objects.get(participant=self.a)
        self.assertRedirects(self.client.get(self.url()), i.get_absolute_url())             # formulaire : renvoye au billet
        self.assertRedirects(self.client.post(self.url(), {"type_billet": self.std.pk, "quantite": 2}),
                             i.get_absolute_url())
        r = self.client.post(self.url(), {"type_billet": self.vip.pk, "quantite": 2, "etape": "confirmer"})
        self.assertRedirects(r, i.get_absolute_url())
        self.assertEqual(Inscription.objects.filter(participant=self.a, evenement=self.e).count(), 1)
        i.refresh_from_db()
        self.assertEqual((i.type_billet, i.quantite, i.montant), (self.std, 1, 10))        # reservation initiale intacte
        with self.assertRaises(ValidationError):
            Inscription.inscrire(self.e, self.a, self.std, 1)

    def test_inscription_simple_deja_inscrit(self):
        e3 = self.sans_types()
        self.login("a")
        self.client.post(reverse("participants:inscrire", args=[e3.pk]))
        r = self.client.post(reverse("participants:inscrire", args=[e3.pk]), follow=True)
        self.assertContains(r, "déjà inscrit")
        self.assertEqual(Inscription.objects.filter(participant=self.a, evenement=e3).count(), 1)

    def test_quota_epuise_refuse_avec_message(self):
        Inscription.inscrire(self.e, self.b, self.vip, 5)                # quota VIP = 5 : epuise
        self.login("a")
        r = self.client.post(self.url(), {"type_billet": self.vip.pk, "quantite": 1})
        self.assertTemplateUsed(r, "participants/reservation_choix.html")
        self.assertContains(r, "Il ne reste que 0")
        self.assertFalse(Inscription.objects.filter(participant=self.a).exists())

    def test_acces_au_parcours(self):
        self.assertEqual(self.client.get(self.url()).status_code, 302)   # anonyme -> connexion
        Evenement.objects.filter(pk=self.e.pk).update(statut="BROUILLON")
        self.login("a")
        self.assertEqual(self.client.get(self.url()).status_code, 404)   # evenement non publie


class PositionListeAttenteTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.e.capacite = 1
        self.e.save()
        self.c = Utilisateur.objects.create_user("c", password=MDP)
        self.ia = Inscription.inscrire(self.e, self.a, self.std, 1)      # confirmée
        self.ib = Inscription.inscrire(self.e, self.b, self.std, 1)      # 1re en attente
        self.ic = Inscription.inscrire(self.e, self.c, self.std, 1)      # 2e en attente

    def test_positions(self):
        self.assertIsNone(self.ia.position_attente)                      # confirmée : pas de position
        self.assertEqual((self.ib.position_attente, self.ic.position_attente), (1, 2))

    def test_la_position_baisse_apres_promotion(self):
        self.ia.annuler()                                                # b est promue
        for i in (self.ib, self.ic):
            i.refresh_from_db()
        self.assertEqual(self.ib.statut, "CONFIRMEE")
        self.assertIsNone(self.ib.position_attente)
        self.assertEqual(self.ic.position_attente, 1)

    def test_annulee_n_a_pas_de_position(self):
        self.ib.annuler()
        self.assertIsNone(self.ib.position_attente)
        self.assertEqual(self.ic.position_attente, 1)

    def test_autre_evenement_non_compte(self):
        self.e2.capacite = 1
        self.e2.save()
        Inscription.inscrire(self.e2, self.a, None, 1)
        autre = Inscription.inscrire(self.e2, self.b, None, 1)           # 1re en attente de e2
        self.assertEqual(autre.position_attente, 1)
        self.assertEqual(self.ic.position_attente, 2)

    def test_meme_horodatage_departage_par_identifiant(self):
        Inscription.objects.filter(pk__in=[self.ib.pk, self.ic.pk]).update(date_inscription=self.ib.date_inscription)
        self.ib.refresh_from_db()
        self.ic.refresh_from_db()
        self.assertEqual((self.ib.position_attente, self.ic.position_attente), (1, 2))

    def test_affichage_dans_mes_inscriptions(self):
        self.login("b")
        self.assertContains(self.client.get(reverse("participants:mes_inscriptions")),
                            "Vous êtes 1er sur la liste d'attente")
        self.client.logout()
        self.login("c")
        self.assertContains(self.client.get(reverse("participants:mes_inscriptions")),
                            "Vous êtes 2e sur la liste d'attente")
        self.client.logout()
        self.login("a")
        self.assertNotContains(self.client.get(reverse("participants:mes_inscriptions")), "sur la liste d'attente")

    def test_affichage_sur_le_billet(self):
        self.login("c")
        self.assertContains(self.client.get(self.ic.get_absolute_url()), "Vous êtes 2e sur la liste d'attente")
        self.client.logout()
        self.login("org")                                                # l'organisateur voit la position, pas « Vous êtes »
        r = self.client.get(self.ic.get_absolute_url())
        self.assertContains(r, "Position : 2e sur la liste d'attente")
        self.assertNotContains(r, "Vous êtes")
        self.client.logout()
        self.login("a")
        self.assertNotContains(self.client.get(self.ia.get_absolute_url()), "sur la liste d'attente")


# =====================================================================================
# Améliorations : transfert, .ics, e-mail de promotion, check-in caméra, tableau de bord,
# export CSV, badge « Plus que X places »
# =====================================================================================
import csv as _csv  # noqa: E402
import io as _io  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.core import mail  # noqa: E402
from django.test import Client  # noqa: E402

from .calendrier import echapper, ics_inscription  # noqa: E402
from .templatetags.participants_badges import badge_places  # noqa: E402


def _commencer(evenement):
    """L'événement a commencé (début passé, fin à venir)."""
    Evenement.objects.filter(pk=evenement.pk).update(date_debut=timezone.now() - timedelta(hours=1),
                                                     date_fin=timezone.now() + timedelta(hours=2))


class TransfertModeleTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.c = Utilisateur.objects.create_user("c", password=MDP, email="C@Evenza.tn")
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 2)

    def test_transfert_reussi(self):
        ancien = self.ia.code_billet
        self.ia.transferer(self.b)
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.participant, self.b)
        self.assertNotEqual(self.ia.code_billet, ancien)
        self.assertEqual((self.ia.type_billet, self.ia.quantite, self.ia.montant, self.ia.statut),
                         (self.vip, 2, Decimal("100"), "CONFIRMEE"))
        self.assertFalse(self.ia.present)
        self.assertEqual(Inscription.objects.filter(evenement=self.e).count(), 1)      # pas de doublon

    def test_refus_soi_meme(self):
        with self.assertRaisesMessage(ValidationError, "propre billet"):
            self.ia.transferer(self.a)

    def test_refus_destinataire_deja_inscrit(self):
        Inscription.inscrire(self.e, self.b)
        with self.assertRaisesMessage(ValidationError, "déjà une réservation"):
            self.ia.transferer(self.b)

    def test_ligne_annulee_du_destinataire_remplacee(self):
        ib = Inscription.inscrire(self.e, self.b)
        ib.annuler()
        self.ia.transferer(self.b)
        self.assertFalse(Inscription.objects.filter(pk=ib.pk).exists())
        self.assertEqual(Inscription.objects.get(evenement=self.e, participant=self.b).pk, self.ia.pk)

    def test_refus_reservation_annulee_ou_en_attente(self):
        self.ia.annuler()
        with self.assertRaisesMessage(ValidationError, "annulée"):
            self.ia.transferer(self.b)
        Evenement.objects.filter(pk=self.e.pk).update(capacite=1)
        Inscription.inscrire(self.e, self.c)                     # confirmée (1 place)
        attente = Inscription.inscrire(self.e, self.b)
        self.assertEqual(attente.statut, "ATTENTE")
        with self.assertRaisesMessage(ValidationError, "confirmée"):
            attente.transferer(self.a)

    def test_refus_billet_deja_scanne(self):
        Inscription.objects.filter(pk=self.ia.pk).update(present=True)
        with self.assertRaisesMessage(ValidationError, "scanné"):
            self.ia.transferer(self.b)

    def test_refus_evenement_commence(self):
        _commencer(self.e)
        with self.assertRaisesMessage(ValidationError, "commencé"):
            self.ia.transferer(self.b)

    def test_refus_destinataire_inactif(self):
        self.b.is_active = False
        self.b.save()
        with self.assertRaises(ValidationError):
            self.ia.transferer(self.b)


class TransfertVueTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.c = Utilisateur.objects.create_user("c", password=MDP, email="C@Evenza.tn")
        self.ia = Inscription.inscrire(self.e, self.a, self.std, 1)
        self.url = reverse("participants:inscription_transferer", args=[self.ia.pk])

    def test_confirmation_puis_transfert_par_email(self):
        self.login("a")
        ancien_billet = self.ia.get_absolute_url()
        r = self.client.post(self.url, {"destinataire": "c@evenza.TN"})          # étape 2 : confirmation
        self.assertContains(r, "Confirmer le transfert")
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.participant, self.a)                           # rien n'a changé
        r = self.client.post(self.url, {"destinataire": "c@evenza.TN", "etape": "confirmer"}, follow=True)
        self.assertContains(r, "Billet transféré à c")
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.participant, self.c)
        self.assertEqual(self.client.get(ancien_billet).status_code, 404)        # l'ancien code ne marche plus
        self.client.logout()
        self.login("c")
        self.assertEqual(self.client.get(self.ia.get_absolute_url()).status_code, 200)

    def test_destinataire_inconnu(self):
        self.login("a")
        r = self.client.post(self.url, {"destinataire": "personne", "etape": "confirmer"})
        self.assertContains(r, "Aucun compte actif")
        self.ia.refresh_from_db()
        self.assertEqual(self.ia.participant, self.a)

    def test_soi_meme_refuse_avec_message(self):
        self.login("a")
        r = self.client.post(self.url, {"destinataire": "A", "etape": "confirmer"})
        self.assertContains(r, "propre billet")

    def test_reservation_d_un_autre_404_et_anonyme(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.login("b")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_evenement_commence_redirige_avec_message(self):
        _commencer(self.e)
        self.login("a")
        r = self.client.get(self.url, follow=True)
        self.assertRedirects(r, reverse("participants:mes_inscriptions"))
        self.assertContains(r, "commencé")

    def test_bouton_dans_mes_inscriptions(self):
        self.login("a")
        self.assertContains(self.client.get(reverse("participants:mes_inscriptions")), self.url)


class CalendrierIcsTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 1)
        self.url = reverse("participants:billet_ics", args=[self.ia.code_billet])

    def test_contenu_et_en_tetes(self):
        from datetime import timezone as dt_tz
        self.login("a")
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/calendar"))
        self.assertIn("attachment;", r["Content-Disposition"])
        self.assertIn(".ics", r["Content-Disposition"])
        texte = r.content.decode("utf-8")
        self.assertTrue(texte.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(texte.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", texte.replace("\r\n", ""))                       # uniquement des CRLF
        debut = self.e.date_debut.astimezone(dt_tz.utc).strftime("%Y%m%dT%H%M%SZ")
        for attendu in ("VERSION:2.0", "BEGIN:VEVENT", f"UID:{self.ia.code_billet}@evenza", f"DTSTART:{debut}",
                        "DTEND:", "DTSTAMP:", "SUMMARY:Festival", "LOCATION:L\\, a\\, Tunis", "END:VEVENT"):
            self.assertIn(attendu, texte)

    def test_caracteres_speciaux_et_lignes_repliees(self):
        self.assertEqual(echapper("Gala; jazz, rock \\ nuit\nfin"), "Gala\\; jazz\\, rock \\\\ nuit\\nfin")
        Evenement.objects.filter(pk=self.e.pk).update(titre="Soirée « été » ; jazz, " + "très long titre " * 8)
        self.ia = Inscription.objects.select_related("evenement", "evenement__lieu").get(pk=self.ia.pk)
        texte = ics_inscription(self.ia)
        for ligne in texte.split("\r\n"):
            self.assertLessEqual(len(ligne.encode("utf-8")), 75)
        deplie = texte.replace("\r\n ", "")                                     # dépliage RFC 5545
        self.assertIn("SUMMARY:Soirée « été » \\; jazz\\, " + "très long titre " * 3, deplie)

    def test_refus_autre_annulee_anonyme_organisateur(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for nom in ("b", "org", "adm"):
            self.login(nom)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.client.logout()
        self.ia.annuler()
        self.login("a")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_boutons_billet_et_mes_inscriptions(self):
        self.login("a")
        self.assertContains(self.client.get(self.ia.get_absolute_url()), self.url)
        self.assertContains(self.client.get(reverse("participants:mes_inscriptions")), self.url)


class NotificationPromotionTests(GestionBase):
    def setUp(self):
        super().setUp()
        Evenement.objects.filter(pk=self.e.pk).update(capacite=1)
        self.e.refresh_from_db()
        self.b.email = "b@evenza.tn"
        self.b.save()
        self.ia = Inscription.inscrire(self.e, self.a)
        self.ib = Inscription.inscrire(self.e, self.b)
        self.assertEqual(self.ib.statut, "ATTENTE")

    def test_promotion_par_annuler_envoie_un_seul_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ia.annuler()
        self.ib.refresh_from_db()
        self.assertEqual(self.ib.statut, "CONFIRMEE")
        self.assertEqual(len(mail.outbox), 1)                                   # pas de doublon
        m = mail.outbox[0]
        self.assertEqual(m.to, ["b@evenza.tn"])
        self.assertIn("Festival", m.subject)
        self.assertIn("Festival", m.body)
        self.assertIn(self.ib.get_absolute_url(), m.body)
        self.assertIn(self.ib.code_court, m.body)

    def test_email_envoye_seulement_apres_validation(self):
        with self.captureOnCommitCallbacks(execute=False) as rappels:
            self.ia.annuler()
        self.assertEqual(len(mail.outbox), 0)                                  # rien tant que la transaction n'est pas validée
        self.assertEqual(len(rappels), 1)

    def test_promotion_par_modifier(self):
        Evenement.objects.filter(pk=self.e.pk).update(capacite=2)
        Inscription.objects.filter(pk=self.ia.pk).update(quantite=2)           # a occupe les 2 places
        self.ia.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.ia.modifier(self.std, 1)                                      # l'événement a des types : il en faut un
        self.ib.refresh_from_db()
        self.assertEqual(self.ib.statut, "CONFIRMEE")
        self.assertEqual([m.to for m in mail.outbox], [["b@evenza.tn"]])

    def test_pas_d_email_sans_adresse(self):
        self.b.email = ""
        self.b.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.ia.annuler()
        self.ib.refresh_from_db()
        self.assertEqual(self.ib.statut, "CONFIRMEE")
        self.assertEqual(len(mail.outbox), 0)

    def test_pas_d_email_sans_promotion_ni_a_la_creation(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ib.annuler()                                                  # annulation d'une attente : personne promu
            Inscription.inscrire(self.e2, self.b)                              # création directe en CONFIRMEE
        self.assertEqual(len(mail.outbox), 0)

    def test_echec_d_envoi_ne_bloque_pas_l_annulation(self):
        with mock.patch("participants.notifications.send_mail", side_effect=OSError("SMTP en panne")):
            with self.assertLogs("participants.notifications", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    self.ia.annuler()
        self.ia.refresh_from_db()
        self.ib.refresh_from_db()
        self.assertEqual((self.ia.statut, self.ib.statut), ("ANNULEE", "CONFIRMEE"))

    def test_annulation_par_l_organisateur_notifie_aussi(self):
        self.login("org")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("participants:inscription_annuler", args=[self.ia.pk]))
        self.assertEqual(len(mail.outbox), 1)


class CheckinCameraTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("participants:checkin", args=[self.e.pk])
        self.ia = Inscription.inscrire(self.e, self.a)

    def scanner(self, code):
        r = self.client.post(self.url, {"code": code}, HTTP_ACCEPT="application/json")
        return r, r.json()

    def test_page_contient_le_lecteur_et_la_saisie_manuelle(self):
        self.login("org")
        r = self.client.get(self.url)
        self.assertContains(r, 'id="scan-start"')
        self.assertContains(r, "html5-qrcode@2.3.8/html5-qrcode.min.js")
        self.assertContains(r, 'integrity="sha384-')
        self.assertContains(r, 'name="code"')
        self.assertContains(r, "csrfmiddlewaretoken")

    def test_resultats_valide_deja_present_inconnu_non_confirme(self):
        self.login("org")
        r, j = self.scanner(str(self.ia.code_billet))                           # code complet du QR (avec tirets)
        self.assertEqual((r.status_code, j["resultat"], j["presents"]), (200, "valide", 1))
        self.assertEqual(self.scanner(str(self.ia.code_billet))[1]["resultat"], "deja_present")
        self.assertEqual(self.scanner("0123abcd")[1]["resultat"], "inconnu")
        ib = Inscription.inscrire(self.e, self.b)
        ib.annuler()
        _, j = self.scanner(ib.code_court)
        self.assertEqual(j["resultat"], "non_confirme")
        self.assertIn("non confirmé", j["message"])
        r, j = self.scanner("xyz")
        self.assertEqual((r.status_code, j["resultat"]), (400, "invalide"))

    def test_csrf_obligatoire_et_permissions(self):
        c = Client(enforce_csrf_checks=True)
        c.login(username="org", password=MDP)
        self.assertEqual(c.post(self.url, {"code": self.ia.code_court}, HTTP_ACCEPT="application/json").status_code, 403)
        self.ia.refresh_from_db()
        self.assertFalse(self.ia.present)
        self.login("org2")
        r = self.client.post(self.url, {"code": self.ia.code_court}, HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 403)

    def test_formulaire_classique_inchange(self):
        self.login("org")
        r = self.client.post(self.url, {"code": self.ia.code_court}, follow=True)
        self.assertRedirects(r, self.url)
        self.assertContains(r, "Entrée enregistrée")


class TableauBordTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("participants:tableau_de_bord", args=[self.e.pk])

    def test_chiffres_exacts(self):
        Evenement.objects.filter(pk=self.e.pk).update(capacite=4)
        ia = Inscription.inscrire(self.e, self.a, self.vip, 2)                  # 100 DT
        ib = Inscription.inscrire(self.e, self.b, self.std, 1)                  # 10 DT
        c = Utilisateur.objects.create_user("c", password=MDP)
        d = Utilisateur.objects.create_user("d", password=MDP)
        dd = Inscription.inscrire(self.e, d, self.std, 1)                       # confirmée puis annulée
        dd.annuler()
        Inscription.inscrire(self.e, c, self.std, 2)                            # attente (1 place restante)
        Inscription.objects.filter(pk=ia.pk).update(present=True)
        self.termine()
        Avis.objects.create(inscription=ia, note=4)
        Avis.objects.create(inscription=ib, note=5)
        self.login("org")
        r = self.client.get(self.url)
        k = r.context["indicateurs"]
        self.assertEqual((k["confirmes"], k["places_confirmees"], k["attente"], k["annules"]), (2, 3, 1, 1))
        self.assertEqual(k["taux_remplissage"], 75)
        self.assertEqual(k["chiffre_affaires"], Decimal("110"))
        self.assertEqual(k["taux_presence"], 50)
        self.assertEqual(k["note_moyenne"], 4.5)
        g = r.context["graphiques"]
        self.assertEqual(g["statuts"]["valeurs"], [2, 1, 1])
        self.assertEqual(dict(zip(g["ventes"]["labels"], g["ventes"]["places"])), {"VIP": 2, "Standard": 1})
        self.assertEqual(sum(g["jours"]["valeurs"]), 4)
        self.assertContains(r, 'id="donnees-graphiques"')
        self.assertContains(r, "chart.js@4.4.1")

    def test_evenement_vide(self):
        self.login("org")
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        k = r.context["indicateurs"]
        self.assertEqual((k["confirmes"], k["taux_remplissage"], k["taux_presence"], k["note_moyenne"]), (0, 0, 0, None))
        self.assertNotContains(r, "chart.js")

    def test_permissions(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)            # anonyme
        for nom, attendu in (("org", 200), ("adm", 200), ("org2", 403), ("a", 403)):
            self.login(nom)
            self.assertEqual(self.client.get(self.url).status_code, attendu, nom)
            self.client.logout()


class ExportCsvTests(GestionBase):
    def setUp(self):
        super().setUp()
        self.a.first_name, self.a.last_name, self.a.email = "Amel", "Ben Ali", "amel@evenza.tn"
        self.a.save()
        self.ia = Inscription.inscrire(self.e, self.a, self.vip, 2)
        self.ib = Inscription.inscrire(self.e, self.b, self.std, 1)
        self.ib.annuler()
        self.i2 = Inscription.inscrire(self.e2, self.a)
        self.url = reverse("participants:inscription_export")

    def lire(self, r):
        self.assertTrue(r.content.startswith(b"\xef\xbb\xbf"))                  # BOM utf-8-sig pour Excel
        return list(_csv.reader(_io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))

    def test_en_tetes_et_lignes(self):
        self.login("org")
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment;", r["Content-Disposition"])
        lignes = self.lire(r)
        self.assertEqual(lignes[0], ["Nom", "E-mail", "Type de billet", "Quantité", "Montant (DT)", "Statut",
                                     "Date d'inscription", "Présent", "Code"])
        self.assertEqual(len(lignes), 3)                                        # seulement l'événement de org
        amel = next(l for l in lignes[1:] if l[0] == "Amel Ben Ali")
        self.assertEqual(amel[1:6], ["amel@evenza.tn", "VIP", "2", "100,00", "Confirmée"])
        self.assertEqual((amel[7], amel[8]), ("Non", self.ia.code_court))
        b = next(l for l in lignes[1:] if l[0] == "b")
        self.assertEqual((b[2], b[5]), ("Standard", "Annulée"))

    def test_filtres_de_la_liste_appliques(self):
        self.login("adm")
        self.assertEqual(len(self.lire(self.client.get(self.url))), 4)          # l'admin voit tout
        lignes = self.lire(self.client.get(self.url, {"evenement": self.e.pk, "statut": "CONFIRMEE"}))
        self.assertEqual([l[0] for l in lignes[1:]], ["Amel Ben Ali"])

    def test_formules_neutralisees(self):
        self.b.first_name = "=HYPERLINK(1)"
        self.b.save()
        self.login("org")
        lignes = self.lire(self.client.get(self.url))
        self.assertIn("'=HYPERLINK(1)", [l[0] for l in lignes])

    def test_permissions_et_bouton(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.login("a")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.login("org")
        self.assertContains(self.client.get(reverse("participants:inscription_liste")), "Exporter CSV")
        self.assertContains(self.client.get(reverse("participants:liste", args=[self.e.pk])),
                            f"{self.url}?evenement={self.e.pk}")


class BadgePlacesTests(GestionBase):
    def test_balise(self):
        self.assertEqual(badge_places(None), "")
        self.assertEqual(badge_places(6), "")
        self.assertIn("Plus que 5 places", badge_places(5))
        self.assertIn("Plus que 1 place<", badge_places(1))
        self.assertIn("Complet", badge_places(0))

    def test_page_de_reservation(self):
        self.login("a")
        url = reverse("participants:reserver", args=[self.e.pk])
        self.assertContains(self.client.get(url), "Plus que 5 places")          # VIP : quota 5
        Inscription.inscrire(self.e, self.b, self.vip, 5)
        r = self.client.get(url)
        self.assertContains(r, "Complet")                                       # VIP épuisé
        self.assertContains(r, "Plus que 5 places")                             # événement : 5 places sur 10

    def test_page_de_modification(self):
        ia = Inscription.inscrire(self.e, self.a, self.std, 1)
        Inscription.inscrire(self.e, self.b, self.std, 7)                       # 2 places restantes
        self.login("a")
        r = self.client.get(reverse("participants:inscription_modifier", args=[ia.pk]))
        self.assertContains(r, "Plus que 2 places")
        self.assertContains(r, "Plus que 5 places")                             # VIP
