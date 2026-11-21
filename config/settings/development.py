from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = SECRET_KEY or "chave-insegura-apenas-para-desenvolvimento"  # noqa: F405
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CSP_POLICY = ""
