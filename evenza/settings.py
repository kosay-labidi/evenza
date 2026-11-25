"""Configuration du projet Évenza (architecture MVT de Django)."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-evenza-cle-a-changer-en-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"] if DEBUG else os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # --- applications Évenza (une app par gestion) ---
    "core",
    "utilisateurs",
    "evenements",
    "programmes",
    "prestataires",
    "participants",
    "ressources",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "evenza.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],          # templates globaux (base.html, partials)
        "APP_DIRS": True,                          # + templates/ de chaque app
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.evenza",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "evenza.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_USER_MODEL = "utilisateurs.Utilisateur"
AUTHENTICATION_BACKENDS = ["utilisateurs.backends.EmailOuUsernameBackend"]   # nom d'utilisateur ou e-mail

# E-mails (mot de passe oublié) : en développement, ils s'affichent dans le terminal de runserver.
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = "Évenza <no-reply@evenza.tn>"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "utilisateurs:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Coordonnées de l'agence affichées dans le pied de page et la page Contact.
# Réseaux sociaux : ajoutez des paires (nom, url), ex. ("Instagram", "https://instagram.com/…").
# Seuls les réseaux renseignés ici sont affichés.
EVENZA_CONTACT = {
    "email": "contact@evenza.tn",
    "telephone": "+216 70 000 000",
    "adresse": "ESPRIT, Pôle technologique El Ghazala, Ariana",
    "horaires": "Lundi – vendredi · 9 h – 18 h",
    "reseaux": [],
}
