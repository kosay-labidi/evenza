from datetime import timedelta
from decimal import Decimal

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .forms import PrestataireForm, ReservationForm
from .models import Prestataire, Reservation, Service

MDP = "Test12345!"


class BaseTests(TestCase):
    """Jeu de données commun : un admin, deux organisateurs, un participant, un événement, un prestataire."""

    def setUp(self):
        self.admin = Utilisateur.objects.create_superuser("admin", "admin@ex.tn", MDP)
        self.org = Utilisateur.objects.create_user("org", password=MDP, role="ORGANISATEUR")
        self.autre_org = Utilisateur.objects.create_user("org2", password=MDP, role="ORGANISATEUR")
        self.participant = Utilisateur.objects.create_user("part", password=MDP, role="PARTICIPANT")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Gala")
        d = timezone.now() + timedelta(days=5)
        self.evt = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=self.org,
                                            date_debut=d, date_fin=d + timedelta(hours=2), capacite=10)
        self.evt_autre = Evenement.objects.create(titre="E2", categorie=cat, lieu=lieu, organisateur=self.autre_org,
                                                  date_debut=d, date_fin=d + timedelta(hours=2), capacite=10)
        self.traiteur = Service.objects.create(nom="Buffet", type="TRAITEUR")
        self.son = Service.objects.create(nom="Sono", type="SON")
        self.p = Prestataire.objects.create(nom="P", email="p@ex.tn")
        self.p.services.add(self.traiteur)

    def login(self, user):
        self.client.force_login(user)

    def reserver(self, evenement=None, statut="DEMANDEE"):
        return Reservation.objects.create(evenement=evenement or self.evt, prestataire=self.p,
                                          service=self.traiteur, montant=100, statut=statut)


# ---------- US 4.1 — Créer ----------
class CreerPrestataireTests(BaseTests):
    def donnees(self, **kw):
        d = {"nom": "Nouveau", "telephone": "71 234 567", "email": "nouveau@ex.tn", "services": [self.traiteur.pk, self.son.pk]}
        d.update(kw)
        return d

    def test_creation_enregistre_prestataire_et_services(self):
        self.login(self.org)
        r = self.client.post(reverse("prestataires:creer"), self.donnees(), follow=True)
        p = Prestataire.objects.get(nom="Nouveau")
        self.assertEqual(set(p.services.all()), {self.traiteur, self.son})
        self.assertContains(r, "envoyé à l&#x27;administrateur pour validation")

    def test_email_obligatoire_et_valide(self):
        self.assertFalse(PrestataireForm(data=self.donnees(email="")).is_valid())
        self.assertFalse(PrestataireForm(data=self.donnees(email="pas-un-email")).is_valid())

    def test_email_unique_insensible_a_la_casse(self):
        form = PrestataireForm(data=self.donnees(email="P@EX.TN"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_modifier_sans_changer_son_email_reste_valide(self):
        form = PrestataireForm(data=self.donnees(email="p@ex.tn"), instance=self.p)
        self.assertTrue(form.is_valid(), form.errors)

    def test_au_moins_un_service(self):
        form = PrestataireForm(data=self.donnees(services=[]))
        self.assertFalse(form.is_valid())
        self.assertIn("services", form.errors)


# ---------- US 4.2 — Consulter ----------
class ConsulterPrestatairesTests(BaseTests):
    def test_liste_et_detail_pour_organisateur_et_admin(self):
        for u in (self.org, self.admin):
            self.login(u)
            r = self.client.get(reverse("prestataires:liste"))
            self.assertContains(r, self.p.get_absolute_url())
            self.assertContains(r, "Traiteur")
            self.assertEqual(self.client.get(reverse("prestataires:detail", args=[self.p.pk])).status_code, 200)

    def test_acces_refuse_aux_autres_roles(self):
        self.login(self.participant)
        self.assertEqual(self.client.get(reverse("prestataires:liste")).status_code, 403)
        self.assertEqual(self.client.get(reverse("prestataires:detail", args=[self.p.pk])).status_code, 403)

    def test_anonyme_redirige_vers_connexion(self):
        self.assertEqual(self.client.get(reverse("prestataires:liste")).status_code, 302)

    def compter_requetes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("prestataires:liste"))
        return len(ctx.captured_queries)

    def test_liste_sans_requete_n_plus_1(self):
        """Le nombre de requêtes ne dépend pas du nombre de cartes (annotate + prefetch_related)."""
        self.login(self.org)
        self.compter_requetes()  # préchauffe session / cache
        avant = self.compter_requetes()
        for i in range(6):
            x = Prestataire.objects.create(nom=f"X{i}", email=f"x{i}@ex.tn")
            x.services.add(self.son, self.traiteur)
            Reservation.objects.create(evenement=self.evt, prestataire=x, service=self.son, montant=10)
        self.assertEqual(self.compter_requetes(), avant)


# ---------- Mise en page de la liste : recherche, filtre, pagination ----------
class ListeRechercheFiltrePaginationTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.lumiere = Service.objects.create(nom="Spots", type="LUMIERE")
        self.sono = Prestataire.objects.create(nom="Sono Plus", email="contact@sono.tn", telephone="22123456")
        self.sono.services.add(self.son)
        self.eclat = Prestataire.objects.create(nom="Éclat", email="eclat@ex.tn", telephone="98765432")
        self.eclat.services.add(self.lumiere, self.son)
        self.login(self.org)

    def noms(self, **params):
        r = self.client.get(reverse("prestataires:liste"), params)
        self.assertEqual(r.status_code, 200)
        return [p.nom for p in r.context["object_list"]]

    def test_recherche_par_nom_email_telephone(self):
        self.assertEqual(self.noms(q="sono"), ["Sono Plus"])
        self.assertEqual(self.noms(q="ECLAT@ex"), ["Éclat"])
        self.assertEqual(self.noms(q="98765"), ["Éclat"])

    def test_filtre_par_type_de_service_sans_doublon(self):
        self.assertEqual(self.noms(service="SON"), ["Sono Plus", "Éclat"])
        self.assertEqual(self.noms(service="LUMIERE"), ["Éclat"])
        self.assertEqual(self.noms(service="TRAITEUR"), ["P"])

    def test_filtre_inconnu_ignore(self):
        self.assertEqual(len(self.noms(service="PIRATE")), 3)

    def test_recherche_et_filtre_combines(self):
        self.assertEqual(self.noms(q="sono", service="SON"), ["Sono Plus"])
        self.assertEqual(self.noms(q="sono", service="LUMIERE"), [])

    def test_pastille_active_et_etat_vide(self):
        r = self.client.get(reverse("prestataires:liste"), {"service": "LUMIERE", "q": "zzz"})
        self.assertContains(r, 'href="?service=LUMIERE&amp;q=zzz" aria-current="true"')
        self.assertContains(r, "Aucun prestataire ne correspond à ta recherche")
        self.assertContains(r, "Réinitialiser les filtres")

    def test_compteurs_reservations_par_carte(self):
        self.reserver(statut="DEMANDEE")
        self.reserver(statut="CONFIRMEE")
        self.reserver(statut="ANNULEE")
        r = self.client.get(reverse("prestataires:liste"), {"q": "P"})
        p = next(x for x in r.context["object_list"] if x.pk == self.p.pk)
        self.assertEqual((p.nb_reservations, p.nb_en_cours), (3, 2))
        self.assertEqual(r.context["stats"]["nb_demandees"], 1)

    def test_pagination_9_par_page_garde_les_filtres(self):
        for i in range(10):
            Prestataire.objects.create(nom=f"Son {i:02d}", email=f"son{i}@ex.tn").services.add(self.son)
        r = self.client.get(reverse("prestataires:liste"), {"q": "son", "service": "SON"})
        self.assertEqual(len(r.context["object_list"]), 9)
        self.assertEqual(r.context["paginator"].count, 11)   # 10 « Son xx » + « Sono Plus »
        self.assertContains(r, "?page=2&amp;q=son&amp;service=SON")
        r2 = self.client.get(reverse("prestataires:liste"), {"q": "son", "service": "SON", "page": 2})
        self.assertEqual(len(r2.context["object_list"]), 2)

    def test_bouton_reserver_preremplit_le_prestataire(self):
        r = self.client.get(reverse("prestataires:reserver_prestataire", args=[self.sono.pk]))
        url = reverse("prestataires:reserver", args=[self.evt.pk]) + f"?prestataire={self.sono.pk}"
        self.assertContains(r, url)
        self.assertNotContains(r, reverse("prestataires:reserver", args=[self.evt_autre.pk]))
        form = self.client.get(url).context["form"]
        self.assertEqual(str(form["prestataire"].value()), str(self.sono.pk))

    def test_detail_total_confirme_et_badges(self):
        self.reserver(statut="CONFIRMEE")
        self.reserver(statut="DEMANDEE")
        r = self.client.get(self.p.get_absolute_url())
        self.assertEqual(r.context["total_confirme"], Decimal("100"))
        self.assertContains(r, 'class="pr-badge confirmee">Confirmée')
        self.assertContains(r, 'class="pr-badge demandee">Demandée')
        self.assertContains(r, "prestataires/css/prestataires.css")


# ---------- US 4.3 — Réserver ----------
class ReserverTests(BaseTests):
    def url(self, evt=None):
        return reverse("prestataires:reserver", args=[(evt or self.evt).pk])

    def test_reservation_creee_avec_statut_demandee(self):
        self.login(self.org)
        self.client.post(self.url(), {"prestataire": self.p.pk, "service": self.traiteur.pk, "montant": "250"})
        r = Reservation.objects.get()
        self.assertEqual(r.statut, Reservation.Statut.DEMANDEE)
        self.assertEqual(r.evenement, self.evt)
        self.assertEqual(r.montant, Decimal("250"))

    def test_service_non_propose_refuse(self):
        form = ReservationForm(data={"prestataire": self.p.pk, "service": self.son.pk, "montant": "100"})
        self.assertFalse(form.is_valid())
        self.assertIn("service", form.errors)

    def test_montant_strictement_positif(self):
        for montant in ("0", "-5"):
            form = ReservationForm(data={"prestataire": self.p.pk, "service": self.traiteur.pk, "montant": montant})
            self.assertFalse(form.is_valid())
            self.assertIn("montant", form.errors)

    def test_regle_aussi_dans_le_modele(self):
        r = Reservation(evenement=self.evt, prestataire=self.p, service=self.son, montant=0)
        with self.assertRaises(ValidationError) as ctx:
            r.full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {"montant", "service"})

    def test_organisateur_ne_reserve_pas_pour_l_evenement_d_un_autre(self):
        self.login(self.org)
        r = self.client.post(self.url(self.evt_autre), {"prestataire": self.p.pk, "service": self.traiteur.pk,
                                                        "montant": "100"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Reservation.objects.exists())


# ---------- US 4.4 — Confirmer / Annuler ----------
class ReservationStatutTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.r = self.reserver()
        self.login(self.org)

    def changer(self, statut, **data):
        reponse = self.client.post(reverse("prestataires:reservation_statut", args=[self.r.pk, statut]), data)
        self.r.refresh_from_db()
        return reponse

    def test_demandee_vers_confirmee_puis_annulee(self):
        self.changer("CONFIRMEE")
        self.assertEqual(self.r.statut, "CONFIRMEE")
        self.changer("ANNULEE")
        self.assertEqual(self.r.statut, "ANNULEE")

    def test_demandee_vers_annulee(self):
        self.changer("ANNULEE")
        self.assertEqual(self.r.statut, "ANNULEE")

    def test_annulee_est_definitive(self):
        self.changer("ANNULEE")
        reponse = self.changer("CONFIRMEE")
        self.assertEqual(self.r.statut, "ANNULEE")
        self.assertIn("Impossible", " ".join(m.message for m in get_messages(reponse.wsgi_request)))

    def test_confirmee_ne_revient_pas_a_demandee(self):
        self.changer("CONFIRMEE")
        self.changer("DEMANDEE")
        self.assertEqual(self.r.statut, "CONFIRMEE")

    def test_statut_inconnu_refuse(self):
        self.changer("PIRATE")
        self.assertEqual(self.r.statut, "DEMANDEE")

    def test_get_interdit(self):
        r = self.client.get(reverse("prestataires:reservation_statut", args=[self.r.pk, "CONFIRMEE"]))
        self.assertEqual(r.status_code, 405)

    def test_autre_organisateur_refuse(self):
        self.login(self.autre_org)
        self.assertEqual(self.changer("CONFIRMEE").status_code, 403)
        self.assertEqual(self.r.statut, "DEMANDEE")

    def test_admin_autorise(self):
        self.login(self.admin)
        self.changer("CONFIRMEE")
        self.assertEqual(self.r.statut, "CONFIRMEE")

    def test_redirection_par_defaut_vers_reservations_de_l_evenement(self):
        reponse = self.changer("CONFIRMEE")
        self.assertRedirects(reponse, reverse("prestataires:reservations_evenement", args=[self.evt.pk]))

    def test_redirection_next_sur(self):
        url = self.evt.get_absolute_url()
        self.assertRedirects(self.changer("CONFIRMEE", next=url), url, fetch_redirect_response=False)

    def test_redirection_next_externe_ignoree(self):
        reponse = self.changer("CONFIRMEE", next="https://pirate.example.com/")
        self.assertRedirects(reponse, reverse("prestataires:reservations_evenement", args=[self.evt.pk]))

    def test_page_reservations_evenement(self):
        url = reverse("prestataires:reservations_evenement", args=[self.evt.pk])
        r = self.client.get(url)
        self.assertContains(r, "Confirmer")
        self.assertContains(r, "Annuler")
        self.login(self.autre_org)
        self.assertEqual(self.client.get(url).status_code, 403)


# ---------- US 4.5 — Catalogue des services ----------
class ServicesTests(BaseTests):
    def test_liaison_services_prestataires(self):
        p2 = Prestataire.objects.create(nom="P2", email="p2@ex.tn")
        p2.services.set([self.traiteur, self.son])
        self.assertEqual(set(self.traiteur.prestataires.all()), {self.p, p2})
        self.assertEqual(list(self.son.prestataires.all()), [p2])
        p2.services.remove(self.son)
        self.assertFalse(self.son.prestataires.exists())

    def test_admin_ajout_modification_suppression_service(self):
        self.login(self.admin)
        self.client.post(reverse("admin:prestataires_service_add"), {"nom": "Spots", "type": "LUMIERE"})
        s = Service.objects.get(nom="Spots")
        self.client.post(reverse("admin:prestataires_service_change", args=[s.pk]), {"nom": "Spots LED", "type": "LUMIERE"})
        s.refresh_from_db()
        self.assertEqual(s.nom, "Spots LED")
        self.client.post(reverse("admin:prestataires_service_delete", args=[s.pk]), {"post": "yes"})
        self.assertFalse(Service.objects.filter(pk=s.pk).exists())

    def test_admin_selection_multiple_des_services(self):
        self.login(self.admin)
        r = self.client.post(reverse("admin:prestataires_prestataire_add"),
                             {"nom": "Multi", "email": "multi@ex.tn", "telephone": "55 444 333",
                              "services": [self.traiteur.pk, self.son.pk], "statut_validation": "APPROUVE"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Prestataire.objects.get(nom="Multi").services.count(), 2)
        r = self.client.get(reverse("admin:prestataires_prestataire_add"))
        self.assertContains(r, "selectfilter")  # widget filter_horizontal


# ---------- US 4.6 — Modifier / Supprimer ----------
class ModifierSupprimerTests(BaseTests):
    def test_admin_modifie_cote_site(self):
        self.login(self.admin)
        r = self.client.post(reverse("prestataires:modifier", args=[self.p.pk]),
                             {"nom": "P modifié", "telephone": "29 000 111", "email": "p@ex.tn", "services": [self.son.pk]},
                             follow=True)
        self.p.refresh_from_db()
        self.assertEqual(self.p.nom, "P modifié")
        self.assertEqual(list(self.p.services.all()), [self.son])
        self.assertContains(r, "a été modifié")

    def test_page_de_confirmation_puis_suppression(self):
        self.login(self.admin)
        url = reverse("prestataires:supprimer", args=[self.p.pk])
        self.assertContains(self.client.get(url), "Oui, supprimer")
        r = self.client.post(url, follow=True)
        self.assertFalse(Prestataire.objects.filter(pk=self.p.pk).exists())
        self.assertContains(r, "a été supprimé")

    def test_suppression_bloquee_si_reservations(self):
        self.reserver()
        self.login(self.admin)
        url = reverse("prestataires:supprimer", args=[self.p.pk])
        self.assertContains(self.client.get(url), "la suppression sera refusée")
        r = self.client.post(url, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Prestataire.objects.filter(pk=self.p.pk).exists())
        self.assertContains(r, "Impossible de supprimer")

    def test_suppression_bloquee_dans_l_admin_sans_erreur_500(self):
        self.reserver()
        self.login(self.admin)
        r = self.client.post(reverse("admin:prestataires_prestataire_delete", args=[self.p.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Prestataire.objects.filter(pk=self.p.pk).exists())

    def test_organisateur_ne_peut_ni_modifier_ni_supprimer(self):
        self.login(self.org)
        self.assertEqual(self.client.get(reverse("prestataires:modifier", args=[self.p.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("prestataires:supprimer", args=[self.p.pk])).status_code, 403)
        self.assertTrue(Prestataire.objects.filter(pk=self.p.pk).exists())


# ---------- US 4.7 — Superviser ----------
class SuperviserReservationsTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.r1 = self.reserver(self.evt, "DEMANDEE")
        self.r2 = self.reserver(self.evt_autre, "CONFIRMEE")
        self.r3 = self.reserver(self.evt_autre, "ANNULEE")
        self.login(self.admin)
        self.url = reverse("admin:prestataires_reservation_changelist")

    def test_admin_voit_les_reservations_de_tous_les_evenements(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.context["cl"].queryset), {self.r1, self.r2, self.r3})
        for colonne in ("column-evenement", "column-prestataire", "column-service", "column-montant", "column-statut"):
            self.assertContains(r, colonne)

    def test_filtre_par_statut(self):
        for statut, attendu in (("DEMANDEE", self.r1), ("CONFIRMEE", self.r2), ("ANNULEE", self.r3)):
            r = self.client.get(self.url, {"statut__exact": statut})
            self.assertEqual(list(r.context["cl"].queryset), [attendu])

    def test_organisateur_n_accede_pas_a_l_admin(self):
        self.login(self.org)
        self.assertEqual(self.client.get(self.url).status_code, 302)


# ---------- Mise en page : images, photo, Kanban, blocage expliqué ----------
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from .models import IMAGES_TEMPORAIRES, image_prestataires

MEDIA_TEST = tempfile.mkdtemp(prefix="evenza-media-test-")


def image_png(nom="logo.png", taille=(40, 40)):
    tampon = io.BytesIO()
    Image.new("RGB", taille, (81, 45, 59)).save(tampon, "PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class PhotoPrestataireTests(BaseTests):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)
        super().tearDownClass()

    def donnees(self, **kw):
        d = {"nom": "Studio Photo", "telephone": "22123456", "email": "studio@ex.tn", "services": [self.traiteur.pk]}
        d.update(kw)
        return d

    def test_ajout_avec_photo_affichee_sur_la_carte_et_la_fiche(self):
        self.login(self.org)
        self.client.post(reverse("prestataires:creer"), self.donnees(photo=image_png()))
        p = Prestataire.objects.get(email="studio@ex.tn")
        self.assertTrue(p.photo.name.startswith("prestataires/"))
        self.assertContains(self.client.get(reverse("prestataires:liste")), p.photo.url)
        self.assertContains(self.client.get(p.get_absolute_url()), p.photo.url)

    def test_photo_facultative(self):
        form = PrestataireForm(data=self.donnees())
        self.assertTrue(form.is_valid(), form.errors)

    def test_photo_trop_lourde_refusee(self):
        from unittest import mock
        with mock.patch("prestataires.forms.PHOTO_TAILLE_MAX", 10):
            form = PrestataireForm(data=self.donnees(), files={"photo": image_png()})
            self.assertFalse(form.is_valid())
            self.assertIn("3 Mo maximum", form.errors["photo"][0])

    def test_fichier_qui_n_est_pas_une_image_refuse(self):
        faux = SimpleUploadedFile("logo.png", b"pas une image", content_type="image/png")
        form = PrestataireForm(data=self.donnees(), files={"photo": faux})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_formulaire_multipart_avec_depot_et_apercu(self):
        self.login(self.org)
        r = self.client.get(reverse("prestataires:creer"))
        self.assertContains(r, 'enctype="multipart/form-data"')
        self.assertContains(r, "data-pr-depot")
        self.assertContains(r, "data-pr-apercu")
        self.assertContains(r, "Téléphone")
        self.assertContains(r, self.traiteur.couverture_url)   # services en cartes photo


class ImagesEtPagesTests(BaseTests):
    def test_image_temporaire_si_fichier_absent(self):
        from unittest import mock
        with mock.patch("prestataires.models.finders.find", return_value=None):   # simule « fichier absent »
            self.assertTrue(image_prestataires("services/securite").endswith(IMAGES_TEMPORAIRES["services/securite"]))
            self.assertTrue(self.p.couverture_url.endswith(IMAGES_TEMPORAIRES["services/traiteur"]))

    def test_images_definitives_du_module(self):
        for nom in IMAGES_TEMPORAIRES:
            self.assertEqual(image_prestataires(nom), f"/static/prestataires/img/{nom}.webp")

    def test_liste_bandeau_cartes_et_script(self):
        self.login(self.org)
        r = self.client.get(reverse("prestataires:liste"))
        self.assertContains(r, "pr-bandeau")
        self.assertContains(r, 'data-count="1"')
        self.assertContains(r, "data-pr-tilt")
        self.assertContains(r, "prestataires/js/prestataires.js")

    def test_etat_vide_illustre(self):
        self.login(self.org)
        r = self.client.get(reverse("prestataires:liste"), {"q": "introuvable"})
        self.assertContains(r, 'class="pr-illu"')

    def test_fiche_taux_de_confirmation(self):
        self.reserver(statut="CONFIRMEE")
        self.reserver(statut="DEMANDEE")
        self.reserver(statut="ANNULEE")
        self.reserver(statut="CONFIRMEE")
        self.login(self.admin)
        r = self.client.get(self.p.get_absolute_url())
        self.assertEqual(r.context["taux_confirmation"], 50)
        self.assertContains(r, "--taux:50")

    def test_kanban_trois_colonnes_et_boutons_selon_transitions(self):
        demandee, confirmee, annulee = (self.reserver(statut=s) for s in ("DEMANDEE", "CONFIRMEE", "ANNULEE"))
        self.login(self.org)
        r = self.client.get(reverse("prestataires:reservations_evenement", args=[self.evt.pk]))
        cols = {c["code"]: c["reservations"] for c in r.context["colonnes"]}
        self.assertEqual((cols["DEMANDEE"], cols["CONFIRMEE"], cols["ANNULEE"]), ([demandee], [confirmee], [annulee]))
        self.assertEqual(r.context["total_confirme"], Decimal("100"))
        self.assertContains(r, f'data-id="{demandee.pk}" tabindex="-1"\n    data-vers="CONFIRMEE ANNULEE"')
        self.assertContains(r, f'data-id="{confirmee.pk}" tabindex="-1"\n    data-vers="ANNULEE"')
        self.assertContains(r, reverse("prestataires:reservation_statut", args=[demandee.pk, "CONFIRMEE"]))
        self.assertNotContains(r, reverse("prestataires:reservation_statut", args=[annulee.pk, "CONFIRMEE"]))
        self.assertNotContains(r, reverse("prestataires:reservation_statut", args=[annulee.pk, "ANNULEE"]))

    def test_blocage_explique_liste_les_reservations(self):
        self.reserver(statut="CONFIRMEE")
        self.login(self.admin)
        r = self.client.get(reverse("prestataires:supprimer", args=[self.p.pk]))
        self.assertContains(r, 'class="pr-badge confirmee">Confirmée')
        self.assertContains(r, reverse("prestataires:reservations_evenement", args=[self.evt.pk]))
        self.assertNotContains(r, "Oui, supprimer")


# ---------- Validation des prestataires par l'administrateur ----------
class ValidationPrestatairesTests(BaseTests):
    def creer(self, user, nom="Proposé", email="propose@ex.tn"):
        self.login(user)
        return self.client.post(reverse("prestataires:creer"),
                                {"nom": nom, "telephone": "40 111 222", "email": email, "services": [self.traiteur.pk]},
                                follow=True)

    def en_attente(self, nom="Attente", par=None):
        p = Prestataire.objects.create(nom=nom, email=f"{nom.lower()}@ex.tn", cree_par=par or self.org,
                                       statut_validation=Prestataire.Validation.EN_ATTENTE)
        p.services.add(self.traiteur)
        return p

    # -- création
    def test_creation_organisateur_en_attente(self):
        r = self.creer(self.org)
        p = Prestataire.objects.get(nom="Proposé")
        self.assertEqual(p.statut_validation, Prestataire.Validation.EN_ATTENTE)
        self.assertEqual(p.cree_par, self.org)
        self.assertIsNone(p.valide_par)
        self.assertContains(r, "envoyé à l&#x27;administrateur pour validation")
        self.assertContains(r, "En attente de validation")

    def test_creation_admin_approuve_directement(self):
        r = self.creer(self.admin)
        p = Prestataire.objects.get(nom="Proposé")
        self.assertEqual(p.statut_validation, Prestataire.Validation.APPROUVE)
        self.assertEqual((p.cree_par, p.valide_par), (self.admin, self.admin))
        self.assertIsNotNone(p.date_validation)
        self.assertContains(r, "a été ajouté")

    def test_creation_dans_l_admin_django_approuve(self):
        self.login(self.admin)
        self.client.post(reverse("admin:prestataires_prestataire_add"),
                         {"nom": "Via admin", "email": "via@ex.tn", "telephone": "41 111 222",
                          "services": [self.son.pk], "statut_validation": "APPROUVE"})
        p = Prestataire.objects.get(nom="Via admin")
        self.assertEqual((p.statut_validation, p.cree_par, p.valide_par), ("APPROUVE", self.admin, self.admin))

    # -- seul l'admin valide
    def test_seul_l_admin_valide(self):
        p = self.en_attente()
        for u in (self.org, self.autre_org, self.participant):
            self.login(u)
            self.assertEqual(self.client.get(reverse("prestataires:a_valider")).status_code, 403)
            self.assertEqual(self.client.post(reverse("prestataires:approuver", args=[p.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("prestataires:refuser", args=[p.pk]),
                                              {"motif": "Non"}).status_code, 403)
        p.refresh_from_db()
        self.assertTrue(p.est_en_attente)

    def test_admin_approuve(self):
        p = self.en_attente()
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("prestataires:a_valider")), p.nom)
        fiche = self.client.get(p.get_absolute_url())
        self.assertContains(fiche, reverse("prestataires:approuver", args=[p.pk]))
        self.assertContains(fiche, reverse("prestataires:refuser", args=[p.pk]))
        self.client.post(reverse("prestataires:approuver", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual((p.statut_validation, p.valide_par), ("APPROUVE", self.admin))
        self.assertIsNotNone(p.date_validation)

    def test_refus_exige_un_motif(self):
        p = self.en_attente()
        self.login(self.admin)
        r = self.client.post(reverse("prestataires:refuser", args=[p.pk]), {"motif": "   "}, follow=True)
        p.refresh_from_db()
        self.assertTrue(p.est_en_attente)
        self.assertContains(r, "le motif est obligatoire")
        self.client.post(reverse("prestataires:refuser", args=[p.pk]), {"motif": "Coordonnées invérifiables"})
        p.refresh_from_db()
        self.assertEqual((p.statut_validation, p.motif_refus), ("REFUSE", "Coordonnées invérifiables"))

    def test_validation_uniquement_en_post(self):
        p = self.en_attente()
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("prestataires:approuver", args=[p.pk])).status_code, 405)

    def test_compteur_en_attente_pour_l_admin(self):
        self.en_attente("A1")
        self.en_attente("A2")
        self.login(self.admin)
        r = self.client.get(reverse("prestataires:liste"))
        self.assertEqual(r.context["nb_en_attente"], 2)
        self.assertContains(r, "2 en attente")
        self.assertContains(r, reverse("prestataires:a_valider"))
        self.login(self.org)
        self.assertNotContains(self.client.get(reverse("prestataires:liste")), reverse("prestataires:a_valider"))

    # -- catalogue
    def test_catalogue_uniquement_approuves_sauf_les_siens(self):
        a = self.en_attente("Mien", par=self.org)
        b = self.en_attente("Autre", par=self.autre_org)
        b.refuser(self.admin, "Doublon")
        self.login(self.org)
        r = self.client.get(reverse("prestataires:liste"))
        self.assertEqual([p.nom for p in r.context["object_list"]], ["Mien", "P"])
        self.assertContains(r, 'class="pr-badge en_attente"')
        self.assertNotContains(r, reverse("prestataires:reserver_prestataire", args=[a.pk]))
        self.assertContains(r, reverse("prestataires:reserver_prestataire", args=[self.p.pk]))
        self.assertEqual(r.context["stats"]["nb_prestataires"], 1)
        # fiche d'un prestataire non approuvé proposé par un autre organisateur : introuvable
        self.assertEqual(self.client.get(b.get_absolute_url()).status_code, 404)

    def test_organisateur_voit_son_refus_et_le_motif(self):
        a = self.en_attente("Mien", par=self.org)
        a.refuser(self.admin, "Pas d'assurance professionnelle")
        self.login(self.org)
        for url in (reverse("prestataires:liste"), a.get_absolute_url()):
            r = self.client.get(url)
            self.assertContains(r, 'class="pr-badge refuse"')
            self.assertContains(r, "Pas d&#x27;assurance professionnelle")
            self.assertNotContains(r, reverse("prestataires:reserver_prestataire", args=[a.pk]))

    # -- réservation
    def test_prestataire_non_approuve_non_reservable(self):
        attente = self.en_attente("Att")
        refuse = self.en_attente("Ref")
        refuse.refuser(self.admin, "Non")
        self.login(self.org)
        for p in (attente, refuse):
            # règle du modèle (Reservation.clean)
            with self.assertRaises(ValidationError) as ctx:
                Reservation(evenement=self.evt, prestataire=p, service=self.traiteur, montant=10).full_clean()
            self.assertIn("prestataire", ctx.exception.message_dict)
            # via l'URL, même en forgeant l'identifiant
            url_choix = reverse("prestataires:reserver_prestataire", args=[p.pk])
            self.assertEqual(self.client.get(url_choix).status_code, 404)
            r = self.client.post(reverse("prestataires:reserver", args=[self.evt.pk]) + f"?prestataire={p.pk}",
                                 {"prestataire": p.pk, "service": self.traiteur.pk, "montant": "100"})
            self.assertEqual(r.status_code, 200)
            self.assertIn("prestataire", r.context["form"].errors)
        self.assertFalse(Reservation.objects.exists())

    def test_reservation_refusee_aussi_dans_l_admin_django(self):
        """Le formulaire de l'admin Django applique Reservation.clean() (testé ici hors vue : l'ajout y est fermé)."""
        from django.contrib.admin.sites import site
        p = self.en_attente()
        from django.test import RequestFactory
        requete = RequestFactory().get("/")
        requete.user = self.admin
        Form = site._registry[Reservation].get_form(requete)
        form = Form(data={"evenement": self.evt.pk, "prestataire": p.pk, "service": self.traiteur.pk,
                          "montant": "50", "statut": "DEMANDEE"})
        self.assertFalse(form.is_valid())
        self.assertIn("prestataire", form.errors)

    def test_prestataires_existants_toujours_reservables(self):
        self.assertTrue(self.p.est_approuve)    # défaut du modèle = APPROUVE, comme la migration
        self.login(self.org)
        self.client.post(reverse("prestataires:reserver", args=[self.evt.pk]),
                         {"prestataire": self.p.pk, "service": self.traiteur.pk, "montant": "80"})
        self.assertEqual(Reservation.objects.get().prestataire, self.p)

    def test_reservation_existante_reste_modifiable_apres_refus(self):
        r = self.reserver()
        self.p.refuser(self.admin, "Plus partenaire")
        r.montant = 120
        r.full_clean()           # pas d'erreur : le prestataire de la réservation n'a pas changé
        self.login(self.org)
        self.client.post(reverse("prestataires:reservation_statut", args=[r.pk, "ANNULEE"]))
        r.refresh_from_db()
        self.assertEqual(r.statut, "ANNULEE")

    def test_migration_approuve_les_existants(self):
        from importlib import import_module

        from django.apps import apps as django_apps
        Prestataire.objects.update(statut_validation="EN_ATTENTE")
        import_module("prestataires.migrations.0006_validation_prestataires").approuver_existants(django_apps, None)
        self.assertFalse(Prestataire.objects.exclude(statut_validation="APPROUVE").exists())

    # -- admin Django
    def test_admin_django_filtre_et_actions_groupees(self):
        a, b = self.en_attente("A1"), self.en_attente("A2")
        self.login(self.admin)
        url = reverse("admin:prestataires_prestataire_changelist")
        r = self.client.get(url, {"statut_validation__exact": "EN_ATTENTE"})
        self.assertEqual(set(r.context["cl"].queryset), {a, b})
        self.client.post(url, {"action": "approuver", "_selected_action": [a.pk]})
        a.refresh_from_db()
        self.assertTrue(a.est_approuve)
        # Refuser : page intermédiaire, motif obligatoire
        r = self.client.post(url, {"action": "refuser", "_selected_action": [b.pk]})
        self.assertContains(r, "Motif du refus")
        self.client.post(url, {"action": "refuser", "_selected_action": [b.pk], "confirmer_refus": "1", "motif": ""})
        b.refresh_from_db()
        self.assertTrue(b.est_en_attente)
        self.client.post(url, {"action": "refuser", "_selected_action": [b.pk], "confirmer_refus": "1",
                               "motif": "Incomplet"})
        b.refresh_from_db()
        self.assertEqual((b.statut_validation, b.motif_refus, b.valide_par), ("REFUSE", "Incomplet", self.admin))

    def test_refus_sans_motif_refuse_par_le_modele(self):
        p = self.en_attente()
        p.statut_validation = Prestataire.Validation.REFUSE
        with self.assertRaises(ValidationError):
            p.full_clean()
        with self.assertRaises(ValidationError):
            p.refuser(self.admin, "  ")


# ---------- L'administrateur ne réserve pas ----------
class AdminNeReservePasTests(BaseTests):
    def test_admin_recoit_403_sur_les_vues_de_reservation(self):
        self.login(self.admin)
        url_choix = reverse("prestataires:reserver_prestataire", args=[self.p.pk])
        url_form = reverse("prestataires:reserver", args=[self.evt.pk])
        self.assertEqual(self.client.get(url_choix).status_code, 403)
        self.assertEqual(self.client.get(url_form).status_code, 403)
        r = self.client.post(url_form, {"prestataire": self.p.pk, "service": self.traiteur.pk, "montant": "100"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Reservation.objects.exists())
        # ni dans l'admin Django (supervision seulement)
        self.assertEqual(self.client.get(reverse("admin:prestataires_reservation_add")).status_code, 403)

    def test_bouton_reserver_absent_pour_l_admin(self):
        self.login(self.admin)
        url_choix = reverse("prestataires:reserver_prestataire", args=[self.p.pk])
        url_form = reverse("prestataires:reserver", args=[self.evt.pk])
        self.assertNotContains(self.client.get(reverse("prestataires:liste")), url_choix)
        self.assertNotContains(self.client.get(self.p.get_absolute_url()), url_choix)
        page = self.client.get(reverse("prestataires:reservations_evenement", args=[self.evt.pk]))
        self.assertEqual(page.status_code, 200)            # supervision conservée
        self.assertNotContains(page, url_form)

    def test_admin_garde_ses_autres_droits(self):
        r = self.reserver()
        self.login(self.admin)
        for url in (reverse("prestataires:creer"), reverse("prestataires:modifier", args=[self.p.pk]),
                    reverse("prestataires:supprimer", args=[self.p.pk]), reverse("prestataires:a_valider"),
                    reverse("admin:prestataires_reservation_changelist"), self.p.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse("admin:prestataires_reservation_changelist")), r.evenement.titre)

    def test_organisateur_peut_toujours_reserver(self):
        self.login(self.org)
        url_choix = reverse("prestataires:reserver_prestataire", args=[self.p.pk])
        url_form = reverse("prestataires:reserver", args=[self.evt.pk])
        self.assertContains(self.client.get(reverse("prestataires:liste")), url_choix)
        self.assertContains(self.client.get(self.p.get_absolute_url()), url_choix)
        self.assertContains(self.client.get(reverse("prestataires:reservations_evenement", args=[self.evt.pk])),
                            url_form)
        self.assertEqual(self.client.get(url_choix).status_code, 200)
        self.client.post(url_form, {"prestataire": self.p.pk, "service": self.traiteur.pk, "montant": "100"})
        self.assertEqual(Reservation.objects.get().evenement, self.evt)


# ---------- Téléphone tunisien ----------
class TelephoneTests(BaseTests):
    def form(self, tel, instance=None, admin=False):
        from .forms import PrestataireAdminForm
        Form = PrestataireAdminForm if admin else PrestataireForm
        data = {"nom": "T", "email": "t@ex.tn", "telephone": tel, "services": [self.traiteur.pk],
                "statut_validation": "APPROUVE"}
        return Form(data=data, instance=instance)

    def test_numeros_valides_acceptes_et_normalises(self):
        for saisie in ("22123456", "22 123 456", "22-123-456", "+216 22 123 456", "+21622123456",
                       "00216 22 123 456", "0021622123456", " 22 123 456 "):
            for admin in (False, True):
                f = self.form(saisie, admin=admin)
                self.assertTrue(f.is_valid(), (saisie, f.errors))
                self.assertEqual(f.cleaned_data["telephone"], "22 123 456")
        for premier in "234579":
            self.assertTrue(self.form(f"{premier}1234567").is_valid(), premier)

    def assertErreur(self, tel, message, **kw):
        f = self.form(tel, **kw)
        self.assertFalse(f.is_valid())
        self.assertEqual(f.errors["telephone"], [message])

    def test_trop_court_trop_long_lettres_vide(self):
        for tel in ("2212345", "221234567", "22ab3456", "téléphone", "", "+216 2212345"):
            self.assertErreur(tel, "Le numéro doit contenir 8 chiffres.")

    def test_premier_chiffre_invalide(self):
        for tel in ("12123456", "62123456", "82123456", "02123456"):
            self.assertErreur(tel, "Ce numéro n'est pas un numéro tunisien valide.")

    def test_doublon_refuse_quel_que_soit_le_format(self):
        Prestataire.objects.create(nom="Ancien", email="ancien@ex.tn", telephone="22-123-456")  # ancienne saisie
        for tel in ("22 123 456", "+216 22123456"):
            self.assertErreur(tel, "Ce numéro est déjà utilisé par un autre prestataire.")
            self.assertErreur(tel, "Ce numéro est déjà utilisé par un autre prestataire.", admin=True)

    def test_modifier_en_gardant_son_numero(self):
        self.p.telephone = "22 123 456"
        self.p.save()
        self.assertTrue(self.form("22123456", instance=self.p).is_valid())

    def test_enregistre_au_format_unique_et_affiche_sur_la_carte(self):
        self.login(self.admin)
        self.client.post(reverse("prestataires:creer"), {"nom": "Format", "email": "format@ex.tn",
                                                         "telephone": "+216-98-765-432",
                                                         "services": [self.traiteur.pk]})
        p = Prestataire.objects.get(nom="Format")
        self.assertEqual(p.telephone, "98 765 432")
        self.assertContains(self.client.get(reverse("prestataires:liste")), "98 765 432")
        self.assertContains(self.client.get(reverse("prestataires:modifier", args=[p.pk])),
                            '<p class="pr-card-meta" data-pr-apercu-tel>98 765 432</p>', html=False)

    def test_attributs_html_du_champ(self):
        self.login(self.org)
        r = self.client.get(reverse("prestataires:creer"))
        for attendu in ('type="tel"', 'inputmode="numeric"', 'maxlength="16"', 'pattern="',
                        "8 chiffres, ex. 22 123 456", "data-pr-tel"):
            self.assertContains(r, attendu)

    def test_erreur_affichee_sous_le_champ(self):
        self.login(self.org)
        r = self.client.post(reverse("prestataires:creer"), {"nom": "X", "email": "x@ex.tn", "telephone": "12345678",
                                                             "services": [self.traiteur.pk]})
        self.assertContains(r, '<small class="pr-err" role="alert">Ce numéro n&#x27;est pas un numéro tunisien valide.')
        self.assertFalse(Prestataire.objects.filter(nom="X").exists())
