from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

if not SECRET_KEY or len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("Defina SECRET_KEY (>= 50 caracteres) no ambiente.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Defina ALLOWED_HOSTS explicitamente.")

# HTTPS e cookies
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # só com Nginx confiável
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = [f"https://{h.lstrip('.')}" for h in ALLOWED_HOSTS if h not in ("*",)]  # noqa: F405

# HSTS: aumente gradualmente depois de confirmar que o HTTPS funciona.
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Ligação cifrada à base de dados, se o servidor suportar
DATABASES["default"].setdefault("OPTIONS", {})  # noqa: F405
DATABASES["default"]["OPTIONS"].setdefault("sslmode", env("DB_SSLMODE", default="prefer"))  # noqa: F405

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
