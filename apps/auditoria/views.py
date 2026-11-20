"""Vista de consulta del registro de actividades (GE-71)."""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView

from apps.auditoria.forms import FiltroRegistroActividadForm
from apps.auditoria.models import RegistroActividad


class RegistroActividadListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Listado paginado y filtrable del registro de actividades, solo para administradores.

    Muestra las actividades de la más reciente a la más antigua (orden de
    ``RegistroActividad.Meta``), 20 por página, filtrables por usuario,
    tipo de acción, tipo de registro y rango de fechas (ver
    ``FiltroRegistroActividadForm``). Es de solo consulta: solo acepta
    GET, así que un POST, PUT o DELETE recibe un 405 y no existe ninguna
    forma de modificar o eliminar un registro desde la aplicación. Si los
    filtros no son válidos, se muestra el motivo y el listado queda vacío,
    en vez de ignorar el filtro y mostrar resultados que no se pidieron.
    """

    model = RegistroActividad
    template_name = 'auditoria/registro_actividades.html'
    context_object_name = 'registros'
    paginate_by = 20
    http_method_names = ['get', 'head', 'options']

    def test_func(self):
        """Permite el acceso solo con el rol 'admin' de Keycloak en la sesión."""
        return 'admin' in self.request.session.get('keycloak_roles', [])

    def get_queryset(self):
        """Devuelve los registros que cumplen los filtros de la URL."""
        self.filtros = FiltroRegistroActividadForm(self.request.GET or None)
        queryset = RegistroActividad.objects.select_related('usuario')
        if not self.filtros.is_bound:
            return queryset
        if not self.filtros.is_valid():
            return queryset.none()
        return self.filtros.filtrar(queryset)

    def get_context_data(self, **kwargs):
        """Agrega el formulario de filtros y la querystring para la paginación."""
        context = super().get_context_data(**kwargs)
        querystring = self.request.GET.copy()
        querystring.pop('page', None)
        context['filtros'] = self.filtros
        context['querystring'] = querystring.urlencode()
        return context
