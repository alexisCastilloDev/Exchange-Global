#!/usr/bin/env python
"""Punto de entrada para los comandos administrativos de Django."""

import os
import sys


def main():
    """Configura Django y delega los argumentos al ejecutor de comandos."""
    os.environ.setdefault(
        'DJANGO_SETTINGS_MODULE',
        os.environ.get('DJANGO_SETTINGS_MODULE', 'global_exchange.settings.dev')
    )
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
