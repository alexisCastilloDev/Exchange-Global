from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from apps.divisas.models import Divisa

class TasasVigentesListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Divisa
    template_name = 'divisas/tasas_vigentes.html'
    context_object_name = 'divisas'

    def test_func(self):
        """
        Control de acceso: Evita el error 403 Forbidden.
        Permite el acceso si el usuario pertenece al grupo 'Agentes'
        O si es un superusuario/administrador del sistema.
        """
        es_agente = self.request.user.groups.filter(name='Agentes').exists()
        es_admin = self.request.user.is_superuser

        return es_agente or es_admin

    def get_queryset(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no se muestran.
        """
        return Divisa.objects.filter(activa=True)