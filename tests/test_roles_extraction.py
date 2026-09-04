import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.authentication.backends import KeycloakOIDCAuthenticationBackend, ROLES_DE_NEGOCIO

User = get_user_model()


@pytest.mark.django_db
def test_realm_access_roles_syncs_to_groups_and_is_staff():
    """
    Si el token tiene roles en realm_access.roles (por ejemplo 'admin'),
    el backend debe añadir el Group correspondiente y marcar is_staff.
    """
    user = User.objects.create_user(username='u_realm', email='realm@example.test')
    backend = KeycloakOIDCAuthenticationBackend()

    claims = {
        'given_name': 'Rey',
        'family_name': 'Realm',
        'email': 'realm@example.test',
        'email_verified': True,
        'realm_access': {'roles': ['admin']},
    }

    backend.update_user_claims(user, claims)
    user.refresh_from_db()

    grupos = set(user.groups.values_list('name', flat=True))
    assert 'admin' in grupos
    assert user.is_staff is True


@pytest.mark.django_db
def test_custom_claim_roles_syncs_to_groups():
    """
    Si el token incluye un claim 'roles' (mapper personalizado), debe sincronizarse.
    """
    user = User.objects.create_user(username='u_custom', email='custom@example.test')
    backend = KeycloakOIDCAuthenticationBackend()

    claims = {
        'email': 'custom@example.test',
        'email_verified': True,
        'roles': ['cajero'],  # claim personalizado
    }

    backend.update_user_claims(user, claims)
    user.refresh_from_db()

    grupos = set(user.groups.values_list('name', flat=True))
    assert 'cajero' in grupos
    # cajero no es admin => no debe ser is_staff
    assert user.is_staff is False


@pytest.mark.django_db
def test_resource_access_client_roles_syncs_to_groups():
    """
    Si Keycloak manda client-specific roles en resource_access.<client>.roles,
    deben incluirse en la sincronización.
    """
    user = User.objects.create_user(username='u_client', email='client@example.test')
    backend = KeycloakOIDCAuthenticationBackend()

    claims = {
        'email': 'client@example.test',
        'email_verified': True,
        'resource_access': {
            'global-exchange-django': {
                'roles': ['analista_cambiario']
            }
        }
    }

    backend.update_user_claims(user, claims)
    user.refresh_from_db()

    grupos = set(user.groups.values_list('name', flat=True))
    assert 'analista_cambiario' in grupos
    assert user.is_staff is False


@pytest.mark.django_db
def test_unknown_roles_are_ignored_and_external_groups_preserved():
    """
    Roles que no están en ROLES_DE_NEGOCIO no deben crear nuevos groups gestionados,
    y los grupos externos que el usuario tuviera deben permanecer.
    """
    user = User.objects.create_user(username='u_ext', email='ext@example.test')
    backend = KeycloakOIDCAuthenticationBackend()

    # Grupo externo que no gestionamos
    grupo_externo = Group.objects.create(name='external_group')
    user.groups.add(grupo_externo)

    claims = {
        'email': 'ext@example.test',
        'email_verified': True,
        'realm_access': {'roles': ['some_unmanaged_role']},
    }

    backend.update_user_claims(user, claims)
    user.refresh_from_db()

    grupos = set(user.groups.values_list('name', flat=True))
    # 'some_unmanaged_role' no pertenece a ROLES_DE_NEGOCIO, no debe crear group gestionado
    assert 'some_unmanaged_role' not in grupos
    # El grupo externo debe seguir presente
    assert 'external_group' in grupos