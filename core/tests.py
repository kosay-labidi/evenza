"""Tests de l'architecture commune : barre latérale par rôle, accès direct aux six modules,
contrôle des permissions côté serveur, absence du préfixe « Gestion des » dans l'interface."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .navigation import ORDRE_MODULES, get_module, modules

MDP = "Mdp-12345!"
ENTREES = {m: get_module(m).url_name for m in ORDRE_MODULES}   # page d'entrée de chaque module


class Fixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = Utilisateur.objects.create_user
        cls.admin = mk("admin", "admin@ex.tn", MDP, role="ADMIN")
        cls.orga = mk("orga", "orga@ex.tn", MDP, role="ORGANISATEUR")
        cls.orga2 = mk("orga2", "orga2@ex.tn", MDP, role="ORGANISATEUR")
        cls.part = mk("part", "part@ex.tn", MDP, role="PARTICIPANT")
        cls.client_ = mk("client", "client@ex.tn", MDP, role="CLIENT")
        cls.presta = mk("presta", "presta@ex.tn", MDP, role="PRESTATAIRE")
        lieu = Lieu.objects.create(nom="Salle", adresse="a", ville="Tunis", capacite=500)
        cat = Categorie.objects.create(nom="Gala")
        d = timezone.now() + timedelta(days=5)
        kw = dict(categorie=cat, lieu=lieu, date_debut=d, date_fin=d + timedelta(hours=3), capacite=100)
        cls.e_orga = Evenement.objects.create(titre="Gala de l'orga", organisateur=cls.orga, **kw)
        cls.e_orga2 = Evenement.objects.create(titre="Soirée d'un autre", organisateur=cls.orga2, **kw)

    def nav(self, user, url_name="core:dashboard"):
        self.client.force_login(user)
        r = self.client.get(reverse(url_name))
        self.assertEqual(r.status_code, 200)
        return r, [m["cle"] for m in r.context["nav_espace"]["principale"]]


class RegistreTests(TestCase):
    def test_six_modules_declares_par_leur_application(self):
        self.assertEqual([m.cle for m in modules()], list(ORDRE_MODULES))
        for m in modules():
            self.assertTrue(m.url_name.startswith(m.namespace + ":"), m)
            reverse(m.url_name)                                  # la page d'entrée existe
            for lien in m.sous_liens:
                reverse(lien.url_name)

    def test_aucun_intitule_gestion_des(self):
        for m in modules():
            self.assertNotIn("gestion", m.label.lower())


class MenuParRoleTests(Fixtures):
    def test_admin_voit_toutes_les_gestions(self):
        _, cles = self.nav(self.admin)
        self.assertEqual(cles, ["apercu", *ORDRE_MODULES])

    def test_organisateur_voit_cinq_gestions_sans_utilisateurs(self):
        _, cles = self.nav(self.orga)
        self.assertEqual(cles, ["apercu", "evenements", "participants", "programmes", "prestataires", "ressources"])

    def test_participant_client_prestataire_ne_voient_que_la_vue_d_ensemble(self):
        for u in (self.part, self.client_, self.presta):
            r, cles = self.nav(u)
            self.assertEqual(cles, ["apercu"], u.role)
            perso = [m["cle"] for m in r.context["nav_espace"]["personnelle"]]
            self.assertEqual(perso, ["billets", "profil"])

    def test_libelles_de_la_barre_laterale(self):
        r, _ = self.nav(self.admin)
        for label in ("Vue d'ensemble", "Événements", "Participants", "Programmes", "Prestataires", "Ressources",
                      "Utilisateurs", "Mon profil", "Retour au site", "Déconnexion"):
            self.assertContains(r, escape(label))
        self.assertNotContains(r, "Gestion des")

    def test_module_actif_et_sous_liens(self):
        r, _ = self.nav(self.orga, "programmes:intervenants")
        actif = r.context["nav_espace"]["actif"]
        self.assertEqual(actif["cle"], "programmes")
        self.assertEqual([l["label"] for l in actif["sous_liens"] if l["actif"]], ["Intervenants"])
        r, _ = self.nav(self.orga, "participants:mes_inscriptions")
        self.assertEqual(r.context["nav_espace"]["actif"]["cle"], "billets")       # espace personnel
        r, _ = self.nav(self.orga, "utilisateurs:profil")
        self.assertEqual(r.context["nav_espace"]["actif"]["cle"], "profil")


class AccesDirectTests(Fixtures):
    def test_admin_ouvre_directement_les_six_modules(self):
        self.client.force_login(self.admin)
        for module, url in ENTREES.items():
            self.assertEqual(self.client.get(reverse(url)).status_code, 200, module)

    def test_organisateur_ouvre_ses_cinq_modules(self):
        self.client.force_login(self.orga)
        for module, url in ENTREES.items():
            attendu = 403 if module == "utilisateurs" else 200
            self.assertEqual(self.client.get(reverse(url)).status_code, attendu, module)

    def test_controle_cote_serveur_pour_les_autres_roles(self):
        for u in (self.part, self.client_, self.presta):
            self.client.force_login(u)
            for module, url in ENTREES.items():
                self.assertEqual(self.client.get(reverse(url)).status_code, 403, f"{u.role} → {module}")

    def test_anonyme_redirige_vers_la_connexion(self):
        for url in ENTREES.values():
            r = self.client.get(reverse(url))
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("utilisateurs:login"), r["Location"])

    def test_participants_n_affiche_que_les_evenements_geres(self):
        self.client.force_login(self.orga)
        r = self.client.get(reverse("participants:index"))
        self.assertContains(r, "Gala de l&#x27;orga")
        self.assertNotContains(r, "Soirée d&#x27;un autre")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("participants:index")), "Soirée d&#x27;un autre")

    def test_vue_d_ensemble_propose_les_modules(self):
        r, _ = self.nav(self.orga)
        self.assertContains(r, 'class="module-card"', count=5)


class SitePublicTests(TestCase):
    def test_pages_publiques_sans_barre_laterale(self):
        for url in ("core:home", "evenements:liste", "core:a_propos", "core:faq", "core:contact",
                    "utilisateurs:login", "utilisateurs:register"):
            r = self.client.get(reverse(url))
            self.assertEqual(r.status_code, 200, url)
            self.assertNotContains(r, 'id="app-side"')
