from config.settings import base as settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app.authenticate.urls')),
    path('', include('app.db.urls')),
    path('', include('app.secretario.urls')),
    path('avaliacao/', include('app.avaliacao.urls')),
    path('financa/', include('app.financa.urls')),
    path('', include('app.director.urls')),
    path('professor/', include('app.professor.urls')),
    path('relatorios/', include('app.relatorios.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )