Global Exchange
===============

Documentación técnica del sistema de operaciones cambiarias, gestión de
clientes, usuarios y control de acceso.

.. note::

   Esta documentación se genera automáticamente con Sphinx a partir de los
   docstrings del código fuente y de las guías del proyecto.

Esta documentación describe la estructura del proyecto, los módulos principales,
la gestión de clientes, divisas y la lógica de autenticación que soporta la
aplicación.

Panorama
--------

Global Exchange organiza su lógica en aplicaciones Django especializadas.
Keycloak gestiona la autenticación y los roles efectivos; Django conserva los
datos operativos, las auditorías y las vistas de la aplicación.

Contenido
---------

* Gestión de clientes y usuarios.
* Administración de divisas y cotizaciones.
* Simulación de conversiones entre monedas.
* Seguridad y roles de acceso.
* Referencia técnica de módulos y clases.

.. toctree::
   :maxdepth: 2
   :caption: Contenidos:
   :hidden:

   guia
   base-datos-roles
   templates
   reference/modules

Guías rápidas
-------------

* :doc:`guia`: mapa de componentes y flujo general de la aplicación.
* :doc:`base-datos-roles`: tablas, relaciones y mecanismo de roles.
* :doc:`templates`: variables, bloques y herencia de los templates Django.
* :doc:`reference/modules`: referencia API generada desde el código fuente.

Navegación
----------

Use la barra lateral para recorrer las guías y la referencia API. La búsqueda
permite localizar clases, funciones, vistas y términos del proyecto.