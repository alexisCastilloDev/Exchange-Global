"""Formato numérico para el locale en_US: miles con "." y decimales con ",".

Django trae, para "en-us", la convención inglesa (miles con "," y decimales
con "."). Este módulo la reemplaza por la convención paraguaya/argentina
sin cambiar ``LANGUAGE_CODE`` (ver ``FORMAT_MODULE_PATH`` en
``global_exchange.settings.base``).
"""

THOUSAND_SEPARATOR = '.'
DECIMAL_SEPARATOR = ','
NUMBER_GROUPING = 3
