from django.conf import settings

def test_django_settings_loaded():
    assert settings.configured is True