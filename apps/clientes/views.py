from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from .models import Cliente
from .forms import ClienteForm

class ClienteCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/cliente_form.html'
    
    # A dónde nos redirige el sistema al guardar el cliente con éxito
    success_url = reverse_lazy('home') 
    
    success_message = "¡El cliente %(nombre)s %(apellido)s ha sido registrado exitosamente!"
    def test_func(self):
        """Valida que el usuario tenga el rol de admin (is_staff)"""
        return self.request.user.is_staff or self.request.user.is_superuser