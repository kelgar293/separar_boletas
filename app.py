import os
import sys
import tkinter as tk
from collections import Counter
from pathlib import Path
from queue import Empty, Queue
from tempfile import mkdtemp
from threading import Thread
from tkinter import filedialog, messagebox, ttk

from separar_boletas import ejecutar, procesar_pdf


def separar(entrada, salida, informar):
    if "spa" not in ejecutar(["tesseract", "--list-langs"]).decode().splitlines():
        raise RuntimeError("Faltan los datos de OCR en español.")
    pdfs = sorted(p for p in entrada.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        raise ValueError("La carpeta seleccionada no contiene PDF.")

    consecutivos = Counter()
    pendientes = errores = 0
    for indice, pdf in enumerate(pdfs, 1):
        informar(f"PDF {indice} de {len(pdfs)} · {pdf.name}")
        try:
            pendientes += procesar_pdf(pdf, salida, 1, 1, 300, consecutivos, informar)
        except Exception as error:
            errores += 1
            informar(f"Error en {pdf.name} · {error}")
    return pendientes, errores


def abrir_ventana():
    ventana = tk.Tk()
    ventana.title("Separar boletas")
    ventana.minsize(650, 350)
    panel = ttk.Frame(ventana, padding=20)
    panel.pack(fill="both", expand=True)
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(4, weight=1)

    carpeta = tk.StringVar()
    estado = tk.StringVar(value="Selecciona la carpeta que contiene los PDF.")
    mensajes = Queue()
    salida = None
    trabajando = False

    def elegir():
        seleccion = filedialog.askdirectory(parent=ventana, title="Carpeta de PDF")
        if seleccion:
            carpeta.set(seleccion)
            iniciar.state(["!disabled"])

    def procesar():
        nonlocal trabajando, salida
        entrada = Path(carpeta.get())
        try:
            salida = Path(mkdtemp(prefix="boletas_separadas_", dir=entrada))
        except OSError as error:
            messagebox.showerror("No se pudo crear la carpeta de resultados", str(error))
            return
        trabajando = True
        elegir_boton.state(["disabled"])
        iniciar.state(["disabled"])
        resultados.state(["disabled"])
        historial.configure(state="normal")
        historial.delete("1.0", "end")
        historial.configure(state="disabled")
        estado.set("Procesando PDF…")
        progreso.start()

        def tarea():
            try:
                resumen = separar(entrada, salida, lambda texto: mensajes.put(("texto", texto)))
            except Exception as error:
                mensajes.put(("error", str(error)))
            else:
                mensajes.put(("fin", resumen))

        Thread(target=tarea).start()

    def leer_mensajes():
        nonlocal trabajando
        try:
            while True:
                tipo, valor = mensajes.get_nowait()
                if tipo == "texto":
                    historial.configure(state="normal")
                    historial.insert("end", valor + "\n")
                    historial.see("end")
                    historial.configure(state="disabled")
                    continue
                trabajando = False
                progreso.stop()
                elegir_boton.state(["!disabled"])
                iniciar.state(["!disabled"])
                if tipo == "fin":
                    pendientes, errores = valor
                    estado.set(f"Terminado · {pendientes} para revisar · {errores} PDF con errores")
                    resultados.state(["!disabled"])
                else:
                    estado.set("No se pudo completar el proceso.")
                    messagebox.showerror("Error al separar boletas", valor)
        except Empty:
            ventana.after(100, leer_mensajes)

    def abrir_resultados():
        try:
            os.startfile(salida)
        except OSError as error:
            messagebox.showerror("No se pudo abrir la carpeta de resultados", str(error))

    def cerrar():
        if trabajando:
            messagebox.showinfo("Separando boletas", "Espera a que termine el proceso.")
        else:
            ventana.destroy()

    ttk.Label(panel, text="Carpeta de PDF").grid(row=0, column=0, sticky="w")
    ttk.Entry(panel, textvariable=carpeta, state="readonly").grid(
        row=1, column=0, sticky="ew", padx=(0, 8)
    )
    elegir_boton = ttk.Button(panel, text="Elegir carpeta", command=elegir)
    elegir_boton.grid(row=1, column=1, sticky="ew")
    iniciar = ttk.Button(panel, text="Separar boletas", command=procesar, state="disabled")
    iniciar.grid(row=2, column=0, sticky="w", pady=12)
    resultados = ttk.Button(
        panel, text="Abrir resultados", command=abrir_resultados, state="disabled"
    )
    resultados.grid(row=2, column=1, sticky="ew", pady=12)
    progreso = ttk.Progressbar(panel, mode="indeterminate")
    progreso.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    historial = tk.Text(panel, height=10, wrap="word", state="disabled")
    historial.grid(row=4, column=0, columnspan=2, sticky="nsew")
    ttk.Label(panel, textvariable=estado).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ventana.protocol("WM_DELETE_WINDOW", cerrar)
    ventana.after(100, leer_mensajes)
    ventana.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--verificar":
        destino = Path(sys.argv[3])
        destino.mkdir()
        sys.exit(int(separar(Path(sys.argv[2]), destino, lambda _: None) != (0, 0)))
    abrir_ventana()
