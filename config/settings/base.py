from pathlib import Path
import environ
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"]
)

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'app.administrador',
    'app.professor',
    'app.secretario',
    'app.authenticate',
    'app.relatorios',
    'app.db',
    'app.doc',
    'app.avaliacao',
    'app.director',
    'app.financa',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'



DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("DB_NAME"),
        'USER': os.getenv("DB_USER"),
        'PASSWORD': os.getenv("DB_PASSWORD"),
        'HOST': os.getenv("DB_HOST"),
        'PORT': os.getenv("DB_PORT"),
    }
}


AUTH_USER_MODEL = 'db.Utilizador'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/index/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

SESSION_COOKIE_AGE = 60 * 60
SESSION_SAVE_EVERY_REQUEST = True

# Proteção HSTS (HTTP Strict Transport Security): 
# Obriga o navegador a comunicar com o seu site 
# apenas através de conexões seguras (HTTPS).
SECURE_HSTS_SECONDS = 31536000  # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Proteção Contra Clickjacking: Ativa o cabeçalho
# X-Frame-Options para impedir que o seu site seja 
# renderizado dentro de <iframe> de terceiros.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Redirecionamento SSL Automático: Garante que qualquer tentativa 
# de acesso via HTTP (porta 80) seja imediatamente enviada para HTTPS (porta 443).
#SECURE_SSL_REDIRECT = True

# Cookies Apenas Via HTTPS: Impede 
# que os cookies de sessão e CSRF sejam intercetados em redes públicas.
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True 
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',"OPTIONS": {"min_length": 8}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    
]


DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "O Meu Sistema <nao-responder@meusistema.ao>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Por omissão: consola em DEBUG, SMTP em produção.
# Para testar envio real em desenvolvimento, define EMAIL_BACKEND no .env.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")



MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"contas": {"handlers": ["console"], "level": "INFO"}},
}

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = 'pt-ao'

TIME_ZONE = 'Africa/Luanda'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS =[
    BASE_DIR / 'static'
]
STATIC_ROOT = BASE_DIR / "staticfiles"




DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
