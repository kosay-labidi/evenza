"""Validations des données de compte, partagées par tous les formulaires de la gestion des utilisateurs
(inscription, profil, formulaires de l'administrateur, administration Django, mots de passe)."""
import re
import unicodedata

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------- prénom et nom
SEPARATEURS_NOM = " '’-."


def normaliser_nom(valeur):
    """Supprime les espaces en trop (début, fin, répétitions)."""
    return " ".join((valeur or "").split())


def valider_nom(valeur, libelle="Ce champ"):
    """Lettres de toutes les écritures (accents, arabe…) et leurs signes diacritiques,
    séparées par espace, apostrophe, trait d'union ou point. Pas de chiffres ni de balises."""
    v = normaliser_nom(valeur)
    if not v:
        return v
    if any(not (unicodedata.category(c)[0] in "LM" or c in SEPARATEURS_NOM) for c in v):
        raise ValidationError(f"{libelle} ne peut contenir que des lettres, des espaces, des apostrophes, "
                              "des traits d'union ou des points.", code="nom_invalide")
    if not unicodedata.category(v[0]).startswith("L") or re.search(r"[ '’\-.]{2,}", v.replace(". ", ".")):
        raise ValidationError(f"{libelle} doit commencer par une lettre et ne pas enchaîner plusieurs séparateurs.",
                              code="nom_invalide")
    return v


# ---------------------------------------------------------------- téléphone
TELEPHONE_TN = re.compile(r"(?:\+216|00216)?[2-9]\d{7}")


def valider_telephone(valeur):
    """Numéro tunisien : 8 chiffres (premier chiffre de 2 à 9), préfixe +216 ou 00216 facultatif.
    Espaces, points et tirets acceptés entre les chiffres. Valeur vide autorisée (champ facultatif)."""
    v = (valeur or "").strip()
    if v and not TELEPHONE_TN.fullmatch(re.sub(r"[\s.\-]", "", v)):
        raise ValidationError("Saisissez un numéro tunisien valide : 8 chiffres, avec ou sans +216 "
                              "(ex. 22 123 456 ou +216 22 123 456).", code="telephone_invalide")
    return v


# ---------------------------------------------------------------- identifiant
def valider_identifiant(valeur):
    """« @ » est réservé aux adresses e-mail : la connexion accepte l'identifiant OU l'e-mail."""
    if "@" in (valeur or ""):
        raise ValidationError("L'identifiant ne peut pas contenir « @ » : il serait confondu avec une adresse "
                              "e-mail lors de la connexion.", code="identifiant_ambigu")
    return valeur


# ---------------------------------------------------------------- mot de passe
LONGUEUR_MIN_INFO = 4   # en dessous, trop de faux positifs (ex. « Ali » dans « Salimata2026 »)


def valider_mdp_infos_personnelles(mot_de_passe, user):
    """Complète UserAttributeSimilarityValidator de Django (qui accepte « sara12345 » pour « sara ») :
    le mot de passe ne doit pas CONTENIR l'identifiant, le prénom, le nom ou la partie locale de l'e-mail."""
    if not mot_de_passe or user is None:
        return
    mdp = mot_de_passe.casefold()
    email = (getattr(user, "email", "") or "").split("@")[0]
    infos = [getattr(user, "username", ""), getattr(user, "first_name", ""), getattr(user, "last_name", ""), email]
    mdp_compact = re.sub(r"[\s'’\-._]+", "", mdp)
    for info in infos:
        info = (info or "").casefold()
        morceaux = [*re.split(r"[\s'’\-._]+", info), re.sub(r"[\s'’\-._]+", "", info)]   # « Ben Ali » → benali
        for morceau in morceaux:
            if len(morceau) >= LONGUEUR_MIN_INFO and (morceau in mdp or morceau in mdp_compact):
                raise ValidationError("Le mot de passe ne doit pas contenir votre identifiant, votre nom ou votre "
                                      "adresse e-mail.", code="mdp_infos_personnelles")


# ---------------------------------------------------------------- photo de profil
PHOTO_TAILLE_MAX_MO = 2
PHOTO_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
PHOTO_FORMATS_REELS = ("JPEG", "PNG", "WEBP")         # format détecté par Pillow dans le CONTENU du fichier
PHOTO_COTE_MAX = 4000                                 # pixels, largeur comme hauteur
PHOTO_PIXELS_MAX = 16_000_000                         # 16 mégapixels : protège contre les « bombes » d'images


def _image_envoyee(fichier):
    """Image Pillow d'un fichier NOUVELLEMENT envoyé (posée par forms.ImageField), sinon None.
    Une photo déjà enregistrée n'est pas relue à chaque enregistrement du compte (et surtout pas ouverte :
    accéder à FieldFile.file ouvre le fichier stocké, ce qui empêcherait ensuite sa suppression sous Windows)."""
    image = getattr(fichier, "image", None)
    if image is not None:
        return image
    if getattr(fichier, "_committed", True):          # fichier déjà stocké : rien à revérifier
        return None
    return getattr(getattr(fichier, "file", None), "image", None)


def valider_photo(fichier):
    """Photo de profil : JPG, PNG ou WebP réels, 2 Mo et 4000 × 4000 px (16 Mpx) au plus.

    Le contenu est vérifié par Pillow (ImageField) : un fichier qui n'est pas une image est refusé, et le format
    RÉEL (pas l'extension) doit être JPEG, PNG ou WebP : un GIF, un SVG ou un BMP renommé est refusé."""
    if not fichier:
        return fichier
    extension = fichier.name.rsplit(".", 1)[-1].lower() if "." in fichier.name else ""
    if extension not in PHOTO_EXTENSIONS:
        raise ValidationError("Format non pris en charge : choisissez une image JPG, PNG ou WebP.",
                              code="photo_format")
    if fichier.size > PHOTO_TAILLE_MAX_MO * 1024 * 1024:
        raise ValidationError(f"La photo ne doit pas dépasser {PHOTO_TAILLE_MAX_MO} Mo.", code="photo_trop_lourde")
    image = _image_envoyee(fichier)
    if image is not None:
        if (image.format or "").upper() not in PHOTO_FORMATS_REELS:
            raise ValidationError("Le contenu du fichier n'est pas une image JPG, PNG ou WebP.", code="photo_format")
        largeur, hauteur = image.size
        if largeur > PHOTO_COTE_MAX or hauteur > PHOTO_COTE_MAX or largeur * hauteur > PHOTO_PIXELS_MAX:
            raise ValidationError(f"Image trop grande : {PHOTO_COTE_MAX} × {PHOTO_COTE_MAX} pixels au maximum.",
                                  code="photo_dimensions")
    return fichier
