"""Genera los textos en español del tema global-exchange para cualquier idioma.

Keycloak usa inglés siempre que el realm no tiene activada la
internacionalización, sin importar el tema. Para que el tema se vea en
español aunque nadie toque esa configuración, este script arma los
messages_en.properties del tema con contenido en español:

    traducción oficial al español de Keycloak (del .jar de la instalación)
  + textos propios del tema y traducciones faltantes
    (login/messages/messages_es.properties)

Correrlo de nuevo después de actualizar Keycloak:

    python keycloak/generar-mensajes.py --keycloak C:\\herramientas_IS2\\keycloak
"""
import argparse
import glob
import os
import re
import zipfile

TEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes", "global-exchange")

CLAVE = re.compile(r"^([^#!\s][^=]*?)\s*=")


def claves(texto):
    return {m.group(1) for m in map(CLAVE.match, texto.splitlines()) if m}


def leer_del_jar(jar, ruta):
    with zipfile.ZipFile(jar) as z:
        return z.read(ruta).decode("utf-8")


def generar(jar, tipo, propios=""):
    base_es = leer_del_jar(jar, f"theme/base/{tipo}/messages/messages_es.properties")
    base_en = leer_del_jar(jar, f"theme/base/{tipo}/messages/messages_en.properties")
    partes = [
        "# ARCHIVO GENERADO por keycloak/generar-mensajes.py: no editar a mano.\n"
        "# Contenido en español a propósito (ver el docstring del script).\n",
        base_es,
    ]
    sin_traducir = claves(base_en) - claves(base_es) - claves(propios)
    if propios:
        # Java Properties: ante claves repetidas gana la última, así que
        # los textos del tema pisan a los oficiales.
        partes.append("\n# --- Textos propios del tema (messages_es.properties) ---\n")
        partes.append(propios)
    destino = os.path.join(TEMA, tipo, "messages", "messages_en.properties")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(partes))
    print(f"{destino}: listo")
    if sin_traducir:
        print(f"  Atención, siguen en inglés: {', '.join(sorted(sin_traducir))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keycloak", default=r"C:\herramientas_IS2\keycloak")
    args = parser.parse_args()
    jars = glob.glob(os.path.join(args.keycloak, "lib", "lib", "main", "org.keycloak.keycloak-themes-[0-9]*.jar"))
    if not jars:
        raise SystemExit(f"No se encontró keycloak-themes-*.jar en {args.keycloak}")
    with open(os.path.join(TEMA, "login", "messages", "messages_es.properties"), encoding="utf-8") as f:
        propios_login = f.read()
    generar(jars[0], "login", propios_login)
    generar(jars[0], "email")


if __name__ == "__main__":
    main()
