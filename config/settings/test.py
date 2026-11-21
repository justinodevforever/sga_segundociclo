import tempfile

from .base import *  # noqa: F401,F403

SECRET_KEY = "chave-de-testes"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = tempfile.mkdtemp(prefix="repo_isp_media_")
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="repo_isp_privado_")
if env("TEST_DATABASE_URL", default=""):
    DATABASES = {"default": env.db("TEST_DATABASE_URL")}
CSP_POLICY = ""
LOGGING = {"version": 1, "disable_existing_loggers": True}
