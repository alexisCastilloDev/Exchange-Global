Referencia de templates
=======================

Los templates Django no tienen docstrings nativos como los módulos Python. Para
hacerlos documentables, cada archivo contiene un bloque de comentario inicial
con el propósito, la herencia, los bloques expuestos y las variables que espera
recibir desde la vista. Esta página incorpora esos encabezados en la salida de
Sphinx.

Template base
-------------

.. literalinclude:: ../../templates/base.html
   :language: html
   :lines: 1-7

Páginas generales
-----------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Template
     - Responsabilidad
   * - ``home.html``
     - Inicio según el rol del usuario.
   * - ``panel.html``
     - Panel protegido de demostración.
   * - ``panel_admin.html``
     - Panel administrativo de clientes.
   * - ``perfil.html``
     - Perfil y contexto operativo.
   * - ``user_list.html``
     - Listado de usuarios.
   * - ``user_edit.html``
     - Edición de datos de usuario.
   * - ``user_roles.html``
     - Administración de roles en Keycloak.

.. literalinclude:: ../../templates/home.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/panel.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/panel_admin.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/perfil.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/user_list.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/user_edit.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/user_roles.html
   :language: html
   :lines: 1-7

Clientes y bajas
----------------

.. literalinclude:: ../../templates/clientes/cliente_form.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/cliente_detail.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/asociar_usuarios.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/seleccionar_cliente.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/metodo_pago_list.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/metodo_pago_form.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/clientes/metodo_pago_confirm_delete.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/bajas/confirmar_baja.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/bajas/historial_bajas.html
   :language: html
   :lines: 1-7

Divisas
-------

.. literalinclude:: ../../templates/divisas/tasas_vigentes.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/calculo_operacion.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/triangulacion.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/simulacion_divisas.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/comision_list.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/comision_form.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/cotizacion_form.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/divisa_form.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/divisa_list.html
   :language: html
   :lines: 1-7

.. literalinclude:: ../../templates/divisas/historial_cotizaciones.html
   :language: html
   :lines: 1-7

Parciales
---------

.. literalinclude:: ../../templates/partials/mensajes.html
   :language: html
   :lines: 1-7
