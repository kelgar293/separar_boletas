#!/usr/bin/env python3
"""Separa boletas escaneadas y nombra los PDF por nombre y consecutivo."""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


ETIQUETA_NOMBRE = (
    r"(?:nombre(?:s)?(?:\s+y\s+apellidos)?"
    r"(?:\s+(?:del|de la)\s+(?:cliente|titular|beneficiario|contribuyente|empleado))?"
    r"|(?:cliente|beneficiario|titular|contribuyente|empleado)(?=\s*[:=]))"
)
ABREVIATURA_NUMERO = r"(?:n[uú]m(?:ero)?\.?|n\.?\s*[°ºo]\.?|#)"
ETIQUETA_NUMERO = (
    rf"(?:{ABREVIATURA_NUMERO}\s*(?:de\s+)?boleta(?:\s+de\s+pago)?"
    rf"|boleta(?:\s+de\s+pago)?\s*(?:{ABREVIATURA_NUMERO})?)"
)
OTRO_CAMPO = (
    rf"\s+(?:(?:{ETIQUETA_NUMERO})\b|(?:fecha|nit|dpi|cui|monto|total|"
    r"direcci[oó]n|c[oó]digo|cuenta|referencia|firma)\s*[:=]"
    r"|c[oó]d\.?\s*[:=]?\s*\d|cta\.?\s+bco\b)"
)
ETIQUETA_EMPLEADO = r"c[oó]digo[ \t]*[/|][ \t]*empleado"
CODIGO_EMPLEADO = r"[A-Z0-9.-]*\d[A-Z0-9.-]*[ \t]*[/|]"
MONTO_EN_LETRAS = (
    r"(?:un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
    r"trece|catorce|quince|dieci\w+|veinte|veinti\w+|treinta|cuarenta|"
    r"cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|\w+cientos|mil)"
)
# En este escaneo, Tesseract confunde la I inicial de Itzep con una ele.
CORRECCIONES_NOMBRE = {
    "MARTA LIDIA VALENZUELA LTZEP": "MARTA LIDIA VALENZUELA ITZEP",
}


def validar_nombre(candidato, minimo_palabras=2):
    candidato = re.sub(r"[,¡]", " ", candidato.strip(" .:-"))
    candidato = " ".join(candidato.split()).upper()
    palabra = r"[^\W\d_]+(?:[.’'\-][^\W\d_]+)*"
    if len(candidato.split()) >= minimo_palabras and re.fullmatch(
        rf"{palabra}(?: {palabra})*\.?", candidato
    ):
        return CORRECCIONES_NOMBRE.get(candidato, candidato)
    return None


def extraer_nombre(texto, *, texto_distribuido=False):
    campos = (
        # En planillas, el nombre suele ir después del código de empleado.
        rf"\b{ETIQUETA_EMPLEADO}\b\s*[:=]?\s*{CODIGO_EMPLEADO}\s*([^\n]+)",
        rf"(?m)^[ \t]*{CODIGO_EMPLEADO}[ \t]*([^\n]+)\n\s*{ETIQUETA_EMPLEADO}\b",
        rf"\b{ETIQUETA_NOMBRE}\b[ \t]*[:=]?[ \t]*(?:\n[ \t]*)?([^\n]+)",
    )
    for campo in campos:
        for coincidencia in re.finditer(campo, texto, re.IGNORECASE):
            candidato = re.split(OTRO_CAMPO, coincidencia[1], maxsplit=1, flags=re.I)[0]
            nombre = validar_nombre(candidato)
            if nombre:
                return nombre

    if re.search(r"\bno\s+negociable\b", texto, re.I):
        cheque = re.search(
            rf"(?im)^\s*[\d|]+[ \t]+([^\n]+)\n\s*{MONTO_EN_LETRAS}\b[^\n]*\d{{2}}/100"
            rf"|^\s*([^\n]+)\n\s*{MONTO_EN_LETRAS}\b[^\n]*\d{{2}}/100",
            texto,
        )
        if cheque:
            return validar_nombre(cheque[1] or cheque[2], minimo_palabras=3)

    if texto_distribuido and re.search(r"\brecib[ií]\s+de\s*:", texto, re.I):
        recibo = re.search(
            r"(?im)^\s*([^\n]+)\n(?:[ \t]*\n)*"
            r"(?:[ \t]*[^\W\d_]{1,2}[ \t]*\n\s*){0,4}"
            r"[ \t]*ejecu[tl]ivo\s+de\s+ventas\b",
            texto,
        )
        if recibo:
            return validar_nombre(recibo[1], minimo_palabras=3)
    return None


def ejecutar(comando, entrada=None):
    if getattr(sys, "frozen", False):
        carpeta = Path(sys._MEIPASS) / "motores"
        comando = [str(carpeta / (comando[0] + ".exe")), *comando[1:]]
        entorno = os.environ.copy()
        entorno["TESSDATA_PREFIX"] = str(carpeta / "tessdata")
        resultado = subprocess.run(
            comando, input=entrada, capture_output=True, check=False,
            env=entorno, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        resultado = subprocess.run(comando, input=entrada, capture_output=True, check=False)
    if resultado.returncode:
        detalle = resultado.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{comando[0]}: {detalle or 'error al ejecutar'}")
    return resultado.stdout


def renderizar(origen, pagina, dpi):
    datos = ejecutar([
        "pdftoppm", "-f", str(pagina), "-l", str(pagina), "-r", str(dpi),
        "-cropbox", "-singlefile", "-png", str(origen),
    ])
    with Image.open(io.BytesIO(datos)) as imagen:
        return imagen.convert("RGB")


def leer_ocr(imagen, dpi, modo=6):
    datos = io.BytesIO()
    imagen.save(datos, format="PNG")
    texto = ejecutar(
        ["tesseract", "stdin", "stdout", "-l", "spa", "--dpi", str(dpi), "--psm", str(modo)],
        datos.getvalue(),
    )
    return unicodedata.normalize("NFKC", texto.decode("utf-8", errors="replace"))


def guardar(destino, nombre, generar_pdf):
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nombre).strip(" .")[:75].rstrip(" .")
    intento = 1
    while True:
        sufijo = "" if intento == 1 else f" ({intento})"
        ruta = destino / f"{nombre}{sufijo}.pdf"
        try:
            archivo = ruta.open("xb")
        except FileExistsError:
            intento += 1
            continue
        try:
            with archivo:
                generar_pdf(archivo)
        except BaseException:
            ruta.unlink(missing_ok=True)
            raise
        return ruta


def guardar_pagina(archivo, pagina):
    escritor = PdfWriter()
    escritor.add_page(pagina)
    escritor.write(archivo)


def procesar_pdf(origen, salida, filas, columnas, dpi, consecutivos, informar=print):
    pendientes = 0
    with origen.open("rb") as archivo:
        lector = PdfReader(archivo)
        for indice, pagina in enumerate(lector.pages, start=1):
            imagen = renderizar(origen, indice, dpi)
            ancho, alto = imagen.size
            for fila in range(filas):
                for columna in range(columnas):
                    region = imagen.crop((
                        columna * ancho // columnas, fila * alto // filas,
                        (columna + 1) * ancho // columnas, (fila + 1) * alto // filas,
                    ))
                    nombre = extraer_nombre(leer_ocr(region, dpi))
                    if nombre is None:
                        nombre = extraer_nombre(
                            leer_ocr(region, dpi, modo=11), texto_distribuido=True
                        )
                    referencia = f"{origen.stem[:48]} p{indice} b{fila * columnas + columna + 1}"
                    if nombre:
                        destino = salida
                        etiqueta = f"{nombre[:60]} - {consecutivos[nombre] + 1}"
                    else:
                        destino = salida / "REVISAR"
                        destino.mkdir(exist_ok=True)
                        etiqueta = f"{referencia} - SIN NOMBRE"
                        pendientes += 1

                    def generar_pdf(archivo_salida):
                        if filas == columnas == 1:
                            guardar_pagina(archivo_salida, pagina)
                        else:
                            region.save(archivo_salida, format="PDF", resolution=dpi, quality=95)

                    ruta = guardar(destino, etiqueta, generar_pdf)
                    if nombre:
                        consecutivos[nombre] += 1
                    informar(f"{referencia} → {ruta.relative_to(salida)}")
    return pendientes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("carpeta", type=Path, help="Carpeta de los PDF originales")
    parser.add_argument("--salida", type=Path, help="Por defecto: boletas_separadas dentro de la carpeta")
    parser.add_argument("--filas", type=int, default=1, help="Filas de boletas por página")
    parser.add_argument("--columnas", type=int, default=1, help="Columnas de boletas por página")
    parser.add_argument("--dpi", type=int, default=300, help="Resolución de lectura OCR")
    args = parser.parse_args()

    if min(args.filas, args.columnas, args.dpi) < 1:
        parser.error("Las filas, las columnas y los dpi deben ser mayores que cero.")
    if not args.carpeta.is_dir():
        parser.error(f"No existe la carpeta {args.carpeta}")
    for programa in ("pdftoppm", "tesseract"):
        if not shutil.which(programa):
            parser.error(f"Instala {programa} y agrégalo al PATH.")
    idiomas = ejecutar(["tesseract", "--list-langs"]).decode().splitlines()
    if "spa" not in idiomas:
        parser.error("Instala los datos de idioma español (spa) para Tesseract.")

    pdfs = sorted(ruta.resolve() for ruta in args.carpeta.iterdir()
                  if ruta.is_file() and ruta.suffix.lower() == ".pdf")
    if not pdfs:
        parser.error("La carpeta no contiene archivos PDF.")
    salida = (args.salida or args.carpeta / "boletas_separadas").resolve()
    if salida == args.carpeta.resolve():
        parser.error("Usa una carpeta de salida distinta de la de los originales.")
    salida.mkdir(parents=True, exist_ok=True)

    pendientes = 0
    errores = 0
    consecutivos = Counter()
    for pdf in pdfs:
        try:
            pendientes += procesar_pdf(pdf, salida, args.filas, args.columnas, args.dpi, consecutivos)
        except Exception as error:
            print(f"Error en {pdf.name}: {error}", file=sys.stderr)
            errores += 1
    print(f"Boletas para revisar: {pendientes}. PDF con errores: {errores}.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
