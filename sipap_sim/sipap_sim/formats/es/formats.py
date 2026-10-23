"""Formato numérico para el locale "es": miles con "." y decimales con ",".

Django trae, para "es", miles separados con un espacio fino (``\xa0``) en vez
de un punto. Este módulo lo reemplaza por la convención paraguaya (puntos de
miles, coma decimal), igual que ``global_exchange.formats`` del lado de
Global Exchange (ver ``FORMAT_MODULE_PATH`` en ``sipap_sim.settings``).
"""

THOUSAND_SEPARATOR = '.'
DECIMAL_SEPARATOR = ','
NUMBER_GROUPING = 3
