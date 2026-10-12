Guía de base de datos y roles
==============================

Esta guía describe el estado actual de la base de datos de Global Exchange y el
mecanismo de roles. La fuente de verdad se verificó contra la configuración de
Django y las tablas existentes en la base activa el 15/09/2026.

Resumen de responsabilidades
----------------------------

El sistema separa dos responsabilidades:

* **Keycloak:** autentica al usuario y administra los roles de negocio.
* **Django/PostgreSQL:** conserva los datos operativos, la sesión, las
  auditorías y una representación local del usuario necesaria para relacionar
  esos datos.

Los roles de negocio no se guardan en una columna de ``auth_user`` ni en un
modelo propio de Django. Al iniciar sesión, Keycloak entrega las roles en las
claims OIDC. El backend las filtra y las coloca en
``request.session['keycloak_roles']``. Las vistas consultan esa sesión durante
la solicitud.

Base de datos utilizada
-----------------------

Los entornos de desarrollo y producción usan PostgreSQL. La conexión se toma
del archivo ``.env`` mediante estas variables:

* ``DB_NAME_DEV`` para desarrollo.
* ``DB_NAME_PROD`` para producción.
* ``DB_USER``, ``DB_PASSWORD``, ``DB_HOST`` y ``DB_PORT`` como datos comunes.

La base activa verificada contiene estas 17 tablas:

.. list-table:: Tablas actuales
   :header-rows: 1
   :widths: 28 48 24

   * - Tabla
     - Propósito
     - Tipo
   * - ``auth_user``
     - Usuarios locales sincronizados o creados por Django.
     - Negocio / identidad local
   * - ``clientes_cliente``
     - Perfil, identificación, tipo, segmento y estado del cliente.
     - Negocio
   * - ``clientes_cliente_usuarios``
     - Relación muchos a muchos entre clientes y usuarios operadores.
     - Relación de negocio
   * - ``clientes_metodopago``
     - Métodos de pago asociados al usuario cliente.
     - Negocio
   * - ``divisas_divisa``
     - Catálogo de divisas y su estado activo/inactivo.
     - Negocio
   * - ``divisas_cotizacion``
     - Historial de tasas de compra y venta por divisa.
     - Negocio
   * - ``divisas_calculooperacion``
     - Cálculos de compra/venta, comisión, tasa aplicada y vencimiento.
     - Negocio
   * - ``authentication_historialbaja``
     - Auditoría de bajas lógicas de usuarios, clientes y divisas.
     - Auditoría
   * - ``django_session``
     - Sesiones HTTP, incluyendo los roles efectivos de Keycloak.
     - Técnica
   * - ``django_migrations``
     - Registro de migraciones aplicadas.
     - Técnica
   * - ``django_content_type``
     - Catálogo interno de modelos de Django.
     - Técnica
   * - ``auth_permission``
     - Permisos nativos de Django.
     - Técnica / histórica
   * - ``auth_group``
     - Grupos nativos de Django.
     - Técnica / histórica
   * - ``auth_group_permissions``
     - Relación entre grupos y permisos nativos.
     - Técnica / histórica
   * - ``auth_user_groups``
     - Relación entre usuarios locales y grupos nativos.
     - Técnica / histórica
   * - ``auth_user_user_permissions``
     - Permisos directos de usuarios locales.
     - Técnica / histórica
   * - ``django_admin_log``
     - Registro de acciones realizadas desde el admin de Django.
     - Técnica

Tablas de negocio
-----------------

``auth_user``
~~~~~~~~~~~~~

Es el usuario local de Django. Guarda username, correo, nombre, estado activo,
``is_staff`` y ``is_superuser``. El backend OIDC busca o crea este registro a
partir del correo o username recibido desde Keycloak.

La regla actual es:

* ``admin`` recibido desde Keycloak activa ``is_staff``.
* El backend fuerza ``is_superuser`` a ``False``; el rol admin no debe saltarse
  los controles de la aplicación mediante el superusuario.
* Los demás roles no se escriben en ``auth_user``.

``clientes_cliente``
~~~~~~~~~~~~~~~~~~~~

Representa el perfil comercial del cliente. Incluye:

* titular opcional mediante ``user_id``;
* identificación CI/RUC;
* persona física o jurídica;
* segmento: minorista, VIP o corporativo;
* correo y fecha de registro;
* ``is_active`` para baja lógica.

``clientes_cliente_usuarios``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Es la tabla intermedia de la relación muchos a muchos entre un cliente y los
usuarios del sistema que pueden operar o representarlo. No define roles; solo
define asociaciones de acceso a clientes.

``clientes_metodopago``
~~~~~~~~~~~~~~~~~~~~~~~~

Guarda cuentas, tarjetas o billeteras del usuario cliente. Incluye reglas para
que cada titular tenga como máximo un método predeterminado y permite conservar
los datos necesarios para la gestión de pagos.

``divisas_divisa``
~~~~~~~~~~~~~~~~~~

Catálogo de divisas con código ISO, nombre, símbolo y estado ``activa``. Las
divisas inactivas se conservan para mantener historial, pero no aparecen como
opciones operativas.

``divisas_cotizacion``
~~~~~~~~~~~~~~~~~~~~~~

Registra cada actualización de tasas. Cada fila guarda tasa de compra, tasa de
venta, usuario que actualizó y fecha. No se sobrescribe el historial: la tasa
vigente es la cotización más reciente de la divisa.

``divisas_calculooperacion``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Guarda un cálculo previo de compra o venta. Conserva el monto de origen, la
tasa aplicada, la comisión, el monto final, la divisa, el usuario y ``vence_en``.
Cuando el cálculo vence, la confirmación se rechaza y se debe recalcular para
usar una cotización actualizada.

``authentication_historialbaja``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Es una auditoría de bajas lógicas. Identifica el tipo y el id del recurso,
guarda su nombre, la causa, quién realizó la baja y cuándo ocurrió. No elimina
el registro principal de cliente, divisa o usuario.

Tablas técnicas de Django
-------------------------

Django crea tablas para administrar migraciones, sesiones, permisos nativos,
grupos, tipos de contenido y el panel administrativo. Estas tablas deben existir
para que el proyecto funcione, aunque no todas participan en la autorización de
negocio.

En particular, ``auth_group`` y sus tablas relacionadas pertenecen al sistema
nativo de Django. El proyecto dejó de usar grupos y permisos como fuente de
roles de negocio. La migración ``authentication.0006_eliminar_rol_agente``
eliminó el grupo local duplicado anterior sin tocar usuarios, clientes ni sus
relaciones. Las tablas nativas se conservan porque Django y el admin pueden
necesitarlas.

Roles de negocio actuales
-------------------------

Los únicos roles funcionales definidos para el proyecto son:

.. list-table:: Roles de Keycloak
   :header-rows: 1
   :widths: 25 55 20

   * - Rol
     - Responsabilidad
     - Persistencia
   * - ``admin``
     - Administración de clientes, usuarios, roles, divisas y tasas.
     - Keycloak + ``auth_user.is_staff`` local
   * - ``analista_cambiario``
     - Consulta y actualización de cotizaciones y operación cambiaria.
     - Keycloak + sesión
   * - ``usuarios``
     - Listado y edición de usuarios.
     - Keycloak + sesión
   * - ``gestion_roles``
     - Administración de roles mediante la API de Keycloak.
     - Keycloak + sesión
   * - ``cliente``
     - Operaciones de cliente, selección de cliente y métodos de pago.
     - Keycloak + sesión

No existe un modelo ``Rol`` propio. Tampoco debe agregarse un campo de rol a
``auth_user``: eso duplicaría la información administrada por Keycloak.

Mecanismo de autorización
-------------------------

#. El usuario inicia sesión mediante OIDC en Keycloak.
#. Keycloak devuelve las claims del usuario y sus roles.
#. ``KeycloakOIDCAuthenticationBackend`` valida el correo, busca o crea el
   usuario local y extrae roles desde ``realm_access.roles``, ``roles`` o
   ``resource_access``.
#. Se eliminan únicamente roles técnicos de Keycloak, como
   ``offline_access`` y ``default-roles-*``.
#. Los roles de negocio se ordenan y guardan en
   ``request.session['keycloak_roles']``.
#. Los decoradores ``requiere_permiso`` y ``requiere_rol`` consultan esa sesión.
   Las vistas de divisas usan ``UserPassesTestMixin`` con el mismo mecanismo.
#. El context processor calcula los accesos visibles del menú. Esto solo cambia
   la interfaz; nunca reemplaza la protección de la vista.

Por eso un cambio de rol en Keycloak se refleja al volver a iniciar sesión. Una
sesión ya abierta conserva sus roles hasta que se renueva o se cierra.

Qué debe existir y qué no debe modificarse
-------------------------------------------

Debe existir:

* todas las tablas listadas por las migraciones aplicadas;
* al menos un usuario local por cada usuario que deba relacionarse con datos
  de Django;
* las divisas activas y sus cotizaciones necesarias para operar;
* la migración de ``CalculoOperacion`` para el cálculo con comisión y
  vencimiento.

No debe gestionarse manualmente en PostgreSQL:

* los roles de negocio de Keycloak;
* la asignación de roles de usuarios;
* la eliminación física de clientes, usuarios o divisas que tengan historial;
* cambios directos en tablas intermedias de clientes sin pasar por la
  aplicación.

Los cambios estructurales deben hacerse mediante migraciones. Los roles deben
crearse, asignarse o eliminarse en Keycloak; la base de Django solo conserva el
estado local necesario para operar y auditar.
