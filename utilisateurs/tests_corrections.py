"""Non-régression des corrections de l'audit final (P01 à P19, périmètre de la gestion des utilisateurs)."""
import re
import time
from datetime import timedelta
from unittest import mock

from django.contrib import admin
from django.contrib.auth import SESSION_KEY
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Utilisateur
from .tests import donnees_inscription

MDP = "Mdp-Audit-2026!"
LOGIN = reverse("utilisateurs:login")
REG = reverse("utilisateurs:register")
RESET = reverse("utilisateurs:password_reset")


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = Utilisateur.objects.create_user
        cls.admin = mk("chef", "chef@ex.tn", MDP, role="ADMIN", first_name="Chef")
        cls.admin2 = mk("adjoint", "adjoint@ex.tn", MDP, role="ADMIN")
        cls.orga = mk("orga", "orga@ex.tn", MDP, role="ORGANISATEUR")
        cls.part = mk("part", "part@ex.tn", MDP, role="PARTICIPANT")
        cls.root = Utilisateur.objects.create_superuser("root", "root@ex.tn", MDP)
        cls.tech = mk("tech", "tech@ex.tn", MDP, role="PARTICIPANT", is_staff=True)

    def setUp(self):
        cache.clear()

    def msgs(self, r):
        from django.contrib.messages import get_messages
        return [str(m) for m in get_messages(r.wsgi_request)]


# ===================================================================== P01 hiérarchie des comptes
class P01HierarchieTests(Base):
    actions = ("modifier", "desactiver", "supprimer")

    def test_regle_centrale(self):
        from core.permissions import niveau_technique, peut_gerer_compte
        self.assertEqual([niveau_technique(u) for u in (self.part, self.admin, self.tech, self.root)], [0, 0, 1, 2])
        self.assertTrue(peut_gerer_compte(self.admin, self.part))
        self.assertTrue(peut_gerer_compte(self.admin, self.admin2))     # admins métier entre eux
        self.assertTrue(peut_gerer_compte(self.admin, self.admin))      # son propre compte
        self.assertFalse(peut_gerer_compte(self.admin, self.root))
        self.assertFalse(peut_gerer_compte(self.admin, self.tech))
        self.assertTrue(peut_gerer_compte(self.root, self.tech))
        self.assertFalse(peut_gerer_compte(self.orga, self.part))       # non-admin : jamais

    def test_admin_metier_refuse_sur_superutilisateur_et_compte_technique_get_et_post(self):
        self.client.force_login(self.admin)
        for cible in (self.root, self.tech):
            for a in (*self.actions, "reactiver"):
                url = reverse(f"utilisateurs:utilisateur_{a}", args=[cible.pk])
                self.assertEqual(self.client.get(url).status_code, 403, f"GET {a} {cible}")
                self.assertEqual(self.client.post(url, {"username": cible.username, "email": "pirate@ex.tn",
                                                        "role": "PARTICIPANT"}).status_code, 403, f"POST {a} {cible}")
            cible.refresh_from_db()
            self.assertNotEqual(cible.email, "pirate@ex.tn")
            self.assertTrue(cible.is_active)
        self.assertTrue(Utilisateur.objects.filter(pk=self.root.pk).exists())

    def test_consultation_autorisee_mais_boutons_masques(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("utilisateurs:utilisateur_detail", args=[self.root.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Compte technique protégé")
        for a in self.actions:
            self.assertNotContains(r, reverse(f"utilisateurs:utilisateur_{a}", args=[self.root.pk]))
        liste = self.client.get(reverse("utilisateurs:utilisateur_liste")).content.decode()
        for a in self.actions:
            self.assertNotIn(reverse(f"utilisateurs:utilisateur_{a}", args=[self.root.pk]), liste)
        self.assertIn(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]), liste)

    def test_superutilisateur_gere_les_comptes_techniques(self):
        self.client.force_login(self.root)
        r = self.client.post(reverse("utilisateurs:utilisateur_desactiver", args=[self.tech.pk]))
        self.tech.refresh_from_db()
        self.assertFalse(self.tech.is_active)
        self.assertEqual(self.client.get(reverse("utilisateurs:utilisateur_modifier", args=[self.tech.pk])).status_code, 200)

    def test_admin_metier_gere_toujours_les_comptes_ordinaires(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                             {"username": "part", "email": "part2@ex.tn", "role": "CLIENT"})
        self.assertEqual(r.status_code, 302)


# ===================================================================== P02 origine du lien
class P02OrigineTests(Base):
    def test_hote_manipule_refuse_proprement(self):
        r = self.client.post(RESET, {"email": "part@ex.tn"}, HTTP_HOST="evil.example")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "momentanément indisponible")
        self.assertEqual(len(mail.outbox), 0)

    def test_local_fonctionne(self):
        for hote in ("testserver", "127.0.0.1:8000", "localhost"):
            mail.outbox.clear()
            self.client.post(RESET, {"email": "part@ex.tn"}, HTTP_HOST=hote)
            self.assertIn(f"http://{hote}/comptes/mot-de-passe/", mail.outbox[0].body, hote)
            cache.clear()

    @override_settings(EVENZA_URL_PUBLIQUE="https://app.exemple-agence.tn")
    def test_origine_configuree_prioritaire_meme_si_host_manipule(self):
        self.client.post(RESET, {"email": "part@ex.tn"}, HTTP_HOST="evil.example")
        corps = mail.outbox[0].body
        self.assertIn("https://app.exemple-agence.tn/comptes/mot-de-passe/", corps)
        self.assertNotIn("evil.example", corps)

    def test_variable_d_environnement(self):
        with mock.patch.dict("os.environ", {"EVENZA_URL_PUBLIQUE": "https://env.exemple.tn"}):
            self.client.post(RESET, {"email": "part@ex.tn"}, HTTP_HOST="evil.example")
        self.assertIn("https://env.exemple.tn/", mail.outbox[0].body)

    @override_settings(EVENZA_URL_PUBLIQUE="exemple.tn/chemin")
    def test_origine_mal_formee_refusee(self):
        r = self.client.post(RESET, {"email": "part@ex.tn"})
        self.assertContains(r, "momentanément indisponible")
        self.assertEqual(len(mail.outbox), 0)


# ===================================================================== P05 limitation des demandes
class P05LimitationResetTests(Base):
    def test_trois_demandes_par_email_puis_reponse_generique(self):
        for _ in range(5):
            r = self.client.post(RESET, {"email": "part@ex.tn"})
            self.assertRedirects(r, reverse("utilisateurs:password_reset_done"))
        self.assertEqual(len(mail.outbox), 3)
        self.client.post(RESET, {"email": "chef@ex.tn"})                 # une autre adresse fonctionne
        self.assertEqual(len(mail.outbox), 4)

    def test_compte_inexistant_meme_reponse_meme_bloque(self):
        for _ in range(5):
            r = self.client.post(RESET, {"email": "personne@ex.tn"})
            self.assertRedirects(r, reverse("utilisateurs:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_limite_par_ip(self):
        for i in range(10):
            self.client.post(RESET, {"email": f"x{i}@ex.tn"})
        self.client.post(RESET, {"email": "part@ex.tn"})
        self.assertEqual(len(mail.outbox), 0)
        Client(REMOTE_ADDR="10.0.0.9").post(RESET, {"email": "part@ex.tn"})
        self.assertEqual(len(mail.outbox), 1)

    def test_expiration_du_blocage(self):
        for _ in range(3):
            self.client.post(RESET, {"email": "part@ex.tn"})
        t0 = time.time()
        with mock.patch("time.time", return_value=t0 + 15 * 60 + 1):
            self.client.post(RESET, {"email": "part@ex.tn"})
        self.assertEqual(len(mail.outbox), 4)


# ===================================================================== P03 conditions d'utilisation
class P03CguTests(Base):
    def test_refus_serveur_sans_cgu(self):
        data = donnees_inscription(); data.pop("cgu")
        r = self.client.post(REG, data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].errors["cgu"],
                         ["Vous devez accepter les conditions d'utilisation pour créer un compte."])
        self.assertContains(r, 'id="cgu-err"')
        self.assertFalse(Utilisateur.objects.filter(username="sara").exists())

    def test_case_reelle_et_obligatoire_dans_le_html(self):
        html = self.client.get(REG).content.decode()
        case = re.search(r'<input[^>]*id="id_cgu"[^>]*>', html).group(0)
        self.assertIn('name="cgu"', case)
        self.assertIn("required", case)
        self.assertIn("form.addEventListener('submit'", html)          # vérification navigateur avant envoi

    def test_case_cochee_conservee_apres_erreur(self):
        r = self.client.post(REG, donnees_inscription(email="pas-un-email"))
        self.assertRegex(r.content.decode(), r'<input[^>]*id="id_cgu"[^>]*checked')


# ===================================================================== P04 identifiant / e-mail
class P04IdentifiantTests(Base):
    MSG = "L'identifiant ne peut pas contenir « @ »"

    def test_inscription_refuse_arobase(self):
        r = self.client.post(REG, donnees_inscription(username="part@ex.tn", email="autre@ex.tn"))
        self.assertTrue(any(self.MSG in e for e in r.context["form"].errors["username"]))

    def test_admin_refuse_arobase_creation_et_renommage(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_creer"), {
            "username": "a@b", "email": "ab@ex.tn", "role": "CLIENT", "is_active": "on",
            "password1": "Tres-Secret-42", "password2": "Tres-Secret-42"})
        self.assertTrue(any(self.MSG in e for e in r.context["form"].errors["username"]))
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                             {"username": "part@x", "email": "part@ex.tn", "role": "PARTICIPANT"})
        self.assertTrue(any(self.MSG in e for e in r.context["form"].errors["username"]))

    def test_ancien_identifiant_conserve_et_connexion_preservee(self):
        """Compte existant dont l'identifiant est l'e-mail d'un autre : il garde son identifiant et se connecte."""
        ancien = Utilisateur.objects.create_user("part@ex.tn", "ancien@ex.tn", "Ancien-Secret-77")
        self.assertEqual(Client().post(LOGIN, {"username": "part@ex.tn", "password": "Ancien-Secret-77"}).status_code, 302)
        c = Client()
        c.post(LOGIN, {"username": "part@ex.tn", "password": MDP})                        # propriétaire de l'e-mail
        self.assertEqual(int(c.session[SESSION_KEY]), self.part.pk)
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[ancien.pk]),
                             {"username": "part@ex.tn", "email": "ancien@ex.tn", "role": "PARTICIPANT"})
        self.assertEqual(r.status_code, 302)                                              # pas de renommage forcé


# ===================================================================== P10 informations personnelles
class P10CoordonneesTests(Base):
    NOMS_OK = ("Zoé", "Ben Ali", "O'Neil", "N’Diaye", "Jean-Pierre", "محمد", "مُحَمَّد", "Abd el-Kader", "J. Dupont")
    NOMS_KO = ("<b>x</b>", "123", "Sara2", "--Ali", "a@b", "Ali  --  B")
    TEL_OK = ("22123456", "22 123 456", "+216 22 123 456", "0021622123456", "71.123.456", "")
    TEL_KO = ("abc", "1234567", "12345678", "+33612345678", "2212345678", "<script>")

    def form(self, **kw):
        from .forms import InscriptionCompteForm
        return InscriptionCompteForm(donnees_inscription(**kw))

    def test_noms_legitimes_acceptes(self):
        for i, nom in enumerate(self.NOMS_OK):
            f = self.form(first_name=nom, last_name=nom, username=f"n{i}", email=f"n{i}@ex.tn")
            self.assertTrue(f.is_valid(), f"{nom!r} : {f.errors.as_text()}")

    def test_noms_invalides_ou_vides_refuses(self):
        for nom in (*self.NOMS_KO, "", "    "):
            self.assertIn("first_name", self.form(first_name=nom).errors, repr(nom))

    def test_espaces_normalises(self):
        f = self.form(first_name="  Zoé   Marie  ")
        self.assertTrue(f.is_valid())
        self.assertEqual(f.cleaned_data["first_name"], "Zoé Marie")

    def test_telephone(self):
        for i, t in enumerate(self.TEL_OK):
            self.assertNotIn("telephone", self.form(telephone=t, username=f"t{i}", email=f"t{i}@ex.tn").errors, t)
        for t in self.TEL_KO:
            self.assertIn("telephone", self.form(telephone=t).errors, t)

    def test_profil_et_admin_appliquent_les_memes_regles(self):
        from .forms import ProfilForm, UtilisateurAdminForm, UtilisateurCreationAdminForm
        p = ProfilForm({"first_name": "", "last_name": "<i>", "email": "part@ex.tn", "telephone": "abc"},
                       instance=self.part)
        self.assertEqual(set(p.errors), {"first_name", "last_name", "telephone"})
        a = UtilisateurAdminForm({"username": "part", "email": "part@ex.tn", "role": "PARTICIPANT",
                                  "first_name": "123", "telephone": "abc"}, instance=self.part, acteur=self.admin)
        self.assertEqual(set(a.errors), {"first_name", "telephone"})
        c = UtilisateurCreationAdminForm({"username": "n", "email": "n@ex.tn", "role": "CLIENT", "last_name": "x1",
                                          "password1": "Tres-Secret-42", "password2": "Tres-Secret-42"})
        self.assertIn("last_name", c.errors)
        self.assertTrue(UtilisateurAdminForm({"username": "part", "email": "part@ex.tn", "role": "PARTICIPANT"},
                                             instance=self.part, acteur=self.admin).is_valid())  # noms facultatifs (admin)


# ===================================================================== P11 / P14
class P11P14Tests(Base):
    def test_inscription_redirige_un_utilisateur_connecte(self):
        self.client.force_login(self.part)
        self.assertRedirects(self.client.get(REG), reverse("core:dashboard"))
        self.client.post(REG, donnees_inscription(username="second", email="second@ex.tn"))
        self.assertFalse(Utilisateur.objects.filter(username="second").exists())
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.part.pk)

    def test_email_obligatoire_creation_admin(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_creer"), {
            "username": "sansmail", "email": "", "role": "PRESTATAIRE", "is_active": "on",
            "password1": "Tres-Secret-42", "password2": "Tres-Secret-42"})
        self.assertEqual(r.context["form"].errors["email"], ["L'adresse e-mail est obligatoire."])
        self.assertFalse(Utilisateur.objects.filter(username="sansmail").exists())

    def test_ancien_compte_sans_email_reste_modifiable_mais_adresse_non_effacable(self):
        ancien = Utilisateur.objects.create_user("ancien", "", MDP)
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[ancien.pk]),
                             {"username": "ancien", "email": "", "role": "PARTICIPANT"})
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                             {"username": "part", "email": "", "role": "PARTICIPANT"})
        self.assertEqual(r.status_code, 200)
        self.part.refresh_from_db()
        self.assertEqual(self.part.email, "part@ex.tn")


# ===================================================================== P06 suppression destructive
class P06SuppressionTests(Base):
    def evenement(self, organisateur):
        from evenements.models import Categorie, Evenement, Lieu
        d = timezone.now() + timedelta(days=5)
        return Evenement.objects.create(titre="Gala", description="d", categorie=Categorie.objects.create(nom="G"),
                                        lieu=Lieu.objects.create(nom="S", ville="Tunis", adresse="x", capacite=50),
                                        organisateur=organisateur, date_debut=d, date_fin=d + timedelta(hours=2),
                                        capacite=50, statut="PUBLIE")

    def test_refus_si_billets_d_autres_participants(self):
        from participants.models import Inscription
        e = self.evenement(self.orga)
        Inscription.objects.create(evenement=e, participant=self.part)
        self.client.force_login(self.admin)
        url = reverse("utilisateurs:utilisateur_supprimer", args=[self.orga.pk])
        r = self.client.get(url)
        self.assertContains(r, "Suppression impossible")
        self.assertNotContains(r, "Oui, supprimer")
        self.assertContains(r, "Désactiver plutôt")
        r = self.client.post(url)
        self.assertTrue(any("Suppression impossible" in m for m in self.msgs(r)))
        self.assertTrue(Utilisateur.objects.filter(pk=self.orga.pk).exists())
        self.assertTrue(Inscription.objects.filter(participant=self.part).exists())

    def test_suppression_sure_preservee(self):
        self.evenement(self.orga)        # événement sans billet d'autrui : seules ses propres données
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_supprimer", args=[self.orga.pk]))
        self.assertRedirects(r, reverse("utilisateurs:utilisateur_liste"))
        self.assertFalse(Utilisateur.objects.filter(pk=self.orga.pk).exists())


# ===================================================================== P07 administration Django
class P07AdminDjangoTests(Base):
    def setUp(self):
        super().setUp()
        self.ma = admin.site._registry[Utilisateur]

    def req(self, user):
        r = RequestFactory().get("/admin/"); r.user = user
        return r

    def form_change(self, acteur, compte, **changes):
        # instances relues : la validation d'un ModelForm modifie l'objet en mémoire, même si elle échoue
        acteur, compte = Utilisateur.objects.get(pk=acteur.pk), Utilisateur.objects.get(pk=compte.pk)
        Form = self.ma.get_form(self.req(acteur), compte, change=True)
        data = {f: getattr(compte, f) for f in ("username", "email", "first_name", "last_name", "telephone", "role")}
        data.update(is_active=compte.is_active, is_staff=compte.is_staff, is_superuser=compte.is_superuser,
                    date_joined_0="2026-01-01", date_joined_1="00:00:00", password=compte.password)
        data.update(changes)
        data = {k: v for k, v in data.items() if v is not False}   # case décochée = champ absent
        return Form(data, instance=compte)

    def test_hierarchie_dans_l_admin(self):
        staff_admin = Utilisateur.objects.create_user("sa", "sa@ex.tn", MDP, role="ADMIN", is_staff=True)
        self.assertFalse(self.ma.has_change_permission(self.req(staff_admin), self.root))
        self.assertFalse(self.ma.has_delete_permission(self.req(staff_admin), self.root))
        self.assertIn("is_superuser", self.ma.get_readonly_fields(self.req(staff_admin), self.part))
        self.assertNotIn("is_superuser", self.ma.get_readonly_fields(self.req(self.root), self.part))

    def test_auto_desactivation_et_auto_retrogradation_refusees(self):
        self.assertFalse(self.form_change(self.root, self.root, is_active=False).is_valid())
        f = self.form_change(self.root, self.root, is_superuser=False)
        self.assertFalse(f.is_valid())
        self.assertIn("Vous ne pouvez pas retirer vos propres droits de superutilisateur.", f.non_field_errors())

    def test_dernier_admin_protege(self):
        """Formulaire ouvert par un superutilisateur qui perd ses droits avant l'envoi : « chef » devient
        le dernier administrateur actif, sa rétrogradation est refusée (contrôle fait sur l'état en base)."""
        Form = self.ma.get_form(self.req(self.root), self.admin, change=True)
        Utilisateur.objects.filter(pk=self.admin2.pk).update(role="PARTICIPANT")
        Utilisateur.objects.filter(pk=self.root.pk).update(is_superuser=False)
        chef = Utilisateur.objects.get(pk=self.admin.pk)
        f = Form({"username": "chef", "email": "chef@ex.tn", "role": "PARTICIPANT", "is_active": "on",
                  "date_joined_0": "2026-01-01", "date_joined_1": "00:00:00"}, instance=chef)
        self.assertFalse(f.is_valid())
        self.assertIn("Impossible : c'est le dernier administrateur actif de la plateforme.", f.non_field_errors())

    def test_suppression_groupee_tout_ou_rien(self):
        """Une sélection contenant un compte non supprimable (ici : le sien) ne supprime RIEN."""
        qs = Utilisateur.objects.filter(pk__in=[self.part.pk, self.orga.pk, self.root.pk])
        with self.assertRaises(PermissionDenied):
            self.ma.delete_queryset(self.req(self.root), qs)
        self.assertEqual(qs.count(), 3)
        # sans compte interdit, la suppression groupée reste possible
        self.ma.delete_queryset(self.req(self.root), Utilisateur.objects.filter(pk__in=[self.part.pk, self.orga.pk]))
        self.assertFalse(Utilisateur.objects.filter(pk__in=[self.part.pk, self.orga.pk]).exists())

    def test_action_groupee_par_l_interface(self):
        c = Client(); c.force_login(self.root)
        r = c.post(reverse("admin:utilisateurs_utilisateur_changelist"),
                   {"action": "delete_selected", "_selected_action": [self.root.pk, self.part.pk], "post": "yes"})
        self.assertEqual(r.status_code, 403)                                   # inclut son propre compte
        self.assertTrue(Utilisateur.objects.filter(pk__in=[self.root.pk, self.part.pk]).count() == 2)

    def test_pas_de_privilege_automatique_pour_le_role_admin(self):
        c = Client(); c.force_login(self.root)
        c.post(reverse("admin:utilisateurs_utilisateur_add"), {
            "username": "nouvadm", "email": "na@ex.tn", "usable_password": "true", "password1": "Tres-Secret-42",
            "password2": "Tres-Secret-42", "role": "ADMIN", "first_name": "", "last_name": "", "telephone": ""})
        u = Utilisateur.objects.get(username="nouvadm")
        self.assertEqual((u.role, u.is_staff, u.is_superuser), ("ADMIN", False, False))


# ===================================================================== P09 / P19
class P09P19Tests(Base):
    def test_verrou_appelable_dans_une_transaction(self):
        from django.db import transaction
        from .views import verrouiller_admins
        with transaction.atomic():
            verrouiller_admins()    # PostgreSQL : FOR UPDATE ; SQLite : clause ignorée (voir le rapport)

    def test_desactivation_croisee_sequentielle_impossible(self):
        Utilisateur.objects.filter(pk=self.root.pk).update(is_superuser=False)
        a, b = Client(), Client()
        a.force_login(self.admin); b.force_login(self.admin2)
        a.post(reverse("utilisateurs:utilisateur_desactiver", args=[self.admin2.pk]))
        b.post(reverse("utilisateurs:utilisateur_desactiver", args=[self.admin.pk]))   # session de b invalidée
        self.assertTrue(Utilisateur.objects.filter(pk=self.admin.pk, is_active=True).exists())

    def test_mixin_sans_regle(self):
        from django.http import HttpResponse
        from django.views import View
        from core.mixins import PermissionRequiseMixin
        Vue = type("Vue", (PermissionRequiseMixin, View), {"get": lambda s, r: HttpResponse("ok")})
        req = RequestFactory().get("/"); req.user = self.part
        with self.assertRaisesMessage(ImproperlyConfigured, "doit définir « permission »"):
            Vue.as_view()(req)


# ===================================================================== P12 changement de mot de passe
class P12ChangementMotDePasseTests(Base):
    url = reverse("utilisateurs:password_change")

    def test_reserve_aux_comptes_connectes(self):
        self.assertIn(LOGIN, Client().get(self.url)["Location"])

    def test_lien_depuis_le_profil(self):
        self.client.force_login(self.part)
        self.assertContains(self.client.get(reverse("utilisateurs:profil")), self.url)

    def test_ancien_mot_de_passe_et_validations(self):
        self.client.force_login(self.part)
        r = self.client.post(self.url, {"old_password": "faux", "new_password1": "Nouveau-Secret-88",
                                        "new_password2": "Nouveau-Secret-88"})
        self.assertTrue(r.context["form"].errors.get("old_password"))
        r = self.client.post(self.url, {"old_password": MDP, "new_password1": "12345678", "new_password2": "12345678"})
        self.assertTrue(r.context["form"].errors.get("new_password2"))
        r = self.client.post(self.url, {"old_password": MDP, "new_password1": "Nouveau-Secret-88",
                                        "new_password2": "Autre-Secret-88"})
        self.assertTrue(r.context["form"].errors.get("new_password2"))

    def test_succes_session_courante_gardee_autres_sessions_fermees(self):
        autre = Client()
        autre.post(LOGIN, {"username": "part", "password": MDP})
        self.client.post(LOGIN, {"username": "part", "password": MDP})
        r = self.client.post(self.url, {"old_password": MDP, "new_password1": "Nouveau-Secret-88",
                                        "new_password2": "Nouveau-Secret-88"})
        self.assertRedirects(r, reverse("utilisateurs:profil"))
        self.assertTrue(any("mot de passe a été modifié" in m for m in self.msgs(r)))
        self.assertEqual(self.client.get(reverse("utilisateurs:profil")).status_code, 200)   # session courante
        self.assertEqual(autre.get(reverse("utilisateurs:profil")).status_code, 302)         # autre session
        self.assertEqual(Client().post(LOGIN, {"username": "part", "password": "Nouveau-Secret-88"}).status_code, 302)

    def test_csrf(self):
        c = Client(enforce_csrf_checks=True); c.force_login(self.part)
        self.assertEqual(c.post(self.url, {"old_password": MDP, "new_password1": "Nouveau-Secret-88",
                                           "new_password2": "Nouveau-Secret-88"}).status_code, 403)


# ===================================================================== P15 UX / accessibilité
class P15UxTests(Base):
    def test_se_souvenir_decoche_par_defaut_et_alertes(self):
        html = self.client.get(LOGIN).content.decode()
        self.assertNotRegex(html, r'name="remember"[^>]*checked')
        r = self.client.post(LOGIN, {"username": "part", "password": "faux"})
        self.assertContains(r, 'role="alert"')

    def test_inscription_utilisable_sans_javascript(self):
        html = self.client.get(REG).content.decode()
        self.assertNotRegex(html, r'<fieldset class="step"[^>]*hidden')
        self.assertRegex(html, r'<button[^>]*id="send"(?![^>]*hidden)[^>]*>')
        self.assertIn('aria-live="polite"', html)

    def test_donnees_conservees_sauf_mots_de_passe(self):
        r = self.client.post(REG, donnees_inscription(email="pas-un-email"))
        html = r.content.decode()
        self.assertIn('value="Sara"', html)
        self.assertIn('value="sara"', html)
        self.assertNotIn("Tres-Secret-42", html)
        self.assertContains(r, 'role="alert"')

    def test_page_hors_limites_affiche_la_derniere(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"), {"page": 999})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"), {"page": "abc"})
        self.assertEqual(r.status_code, 200)


# ===================================================================== P18 mots de passe
class P18MotsDePasseTests(Base):
    def test_inscription(self):
        from .forms import InscriptionCompteForm
        for mdp in ("sara12345", "Sara2026!", "benali-2026", "sara@ex.tn!"):
            f = InscriptionCompteForm(donnees_inscription(password1=mdp, password2=mdp))
            self.assertIn("password2", f.errors, mdp)
        f = InscriptionCompteForm(donnees_inscription(password1="Lune-Orage-71", password2="Lune-Orage-71"))
        self.assertTrue(f.is_valid(), f.errors.as_text())

    def test_changement_et_reinitialisation(self):
        from .forms import ChangementMotDePasseForm, NouveauMotDePasseForm
        f = ChangementMotDePasseForm(self.admin, {"old_password": MDP, "new_password1": "Chef-2026-Tunis",
                                                  "new_password2": "Chef-2026-Tunis"})
        self.assertIn("new_password2", f.errors)
        f = NouveauMotDePasseForm(self.part, {"new_password1": "part-secret-99", "new_password2": "part-secret-99"})
        self.assertIn("new_password2", f.errors)
        self.assertTrue(NouveauMotDePasseForm(self.part, {"new_password1": "Lune-Orage-71",
                                                          "new_password2": "Lune-Orage-71"}).is_valid())

    def test_creation_admin(self):
        from .forms import UtilisateurCreationAdminForm
        f = UtilisateurCreationAdminForm({"username": "karim", "email": "k@ex.tn", "role": "CLIENT",
                                          "password1": "karim-2026!", "password2": "karim-2026!"})
        self.assertIn("password2", f.errors)
