from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from apps.divisas.models import Divisa
from apps.divisas.forms import DivisaForm

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
       # Permite el acceso si es superusuario/staff o si pertenece a los grupos de Agentes o Administradores
        es_super_o_staff = self.request.user.is_superuser or self.request.user.is_staff
        grupos_permitidos = ['admin', 'Admin']
        pertenece_a_grupo = self.request.user.groups.filter(name__in=grupos_permitidos).exists()

        return es_super_o_staff or pertenece_a_grupo

    def get_queryset(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no se muestran.
        """
        return Divisa.objects.filter(activa=True)

class AdminDivisasMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Control de acceso: Solo permite administradores."""
    def test_func(self):
        es_super = self.request.user.is_superuser
        # Revisa si está en algún grupo de administración que uses en Keycloak
        es_admin_grupo = self.request.user.groups.filter(name__in=['admin', 'Admin']).exists()
        
        return es_super or es_admin_grupo

class DivisaListView(AdminDivisasMixin, ListView):
    model = Divisa
    template_name = 'divisas/divisa_list.html'
    context_object_name = 'divisas'

class DivisaCreateView(AdminDivisasMixin, CreateView):
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')

class DivisaUpdateView(AdminDivisasMixin, UpdateView):
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')