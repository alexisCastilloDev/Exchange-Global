from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from apps.divisas.models import Divisa


class TasasVigentesListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Divisa
    template_name = 'divisas/tasas_vigentes.html'
    context_object_name = 'divisas'

    def test_func(self):
        """
        Autorización 100% contra Keycloak (sesión), sin auth.Group.
        Acceso para 'admin' o para el rol de negocio 'agentes'.
        """
        roles = self.request.session.get('keycloak_roles', [])
        return 'admin' in roles or 'agentes' in roles

    def get_queryset(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no se muestran.
        """
        return Divisa.objects.filter(activa=True)