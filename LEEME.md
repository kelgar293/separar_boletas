# Separar boletas en Windows x64

Este ZIP contiene el código y los archivos para compilar. GitHub Actions genera el ZIP portátil en una máquina Windows. La PC donde se procesan las boletas solo necesita poder ejecutar programas portátiles.

1. Descomprime este ZIP y coloca su contenido en la raíz de un repositorio privado de GitHub. Incluye la carpeta oculta `.github`. El repositorio contiene únicamente el código de la aplicación y los datos de idioma del OCR.
2. En GitHub, abre **Actions → Compilar portable Windows → Run workflow**. Espera a que la ejecución termine en verde.
3. Abre la ejecución y descarga el artefacto **SepararBoletas-Windows-x64**. Dentro encontrarás `SepararBoletas-Windows-x64.zip`.
4. Descomprime ese ZIP en la PC de destino. Conserva toda la carpeta `SepararBoletas` y abre `SepararBoletas.exe`.
5. Pulsa **Elegir carpeta** y **Separar boletas**. La aplicación procesa una boleta por página. Pulsa **Abrir resultados** para ver la carpeta de esa ejecución, creada dentro de la carpeta de los PDF.

Los PDF se procesan en la PC. La compilación usa una boleta ficticia para comprobar que el programa abre el escaneo y numera dos boletas del mismo nombre. Mantén tus PDF reales fuera del repositorio.

Para compilar en otra PC Windows x64, instala Python 3.12 y Miniforge en esa máquina de compilación. Desde PowerShell, en la carpeta de este proyecto, ejecuta:

```powershell
conda create --yes --prefix .\motores --override-channels --channel conda-forge poppler tesseract
.\compilar.ps1 -CarpetaConda .\motores
```

El ZIP portátil se genera en `dist/SepararBoletas-Windows-x64.zip`. El archivo `spa.traineddata` pertenece al proyecto [Tesseract tessdata](https://github.com/tesseract-ocr/tessdata) y usa la [licencia Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).
