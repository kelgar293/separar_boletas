param(
    [Parameter(Mandatory = $true)]
    [string]$CarpetaConda
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$bin = Join-Path (Resolve-Path -LiteralPath $CarpetaConda) 'Library\bin'
foreach ($motor in 'pdftoppm.exe', 'tesseract.exe') {
    if (!(Test-Path -LiteralPath (Join-Path $bin $motor))) {
        throw "Falta $motor en $bin"
    }
}

python -m pip install 'pyinstaller>=6.12,<7' 'pypdf>=5,<7' 'Pillow>=11,<13'
if ($LASTEXITCODE -ne 0) { throw 'Error al instalar dependencias de compilación.' }

python -m PyInstaller --noconfirm --clean --onedir --windowed --name SepararBoletas app.py
if ($LASTEXITCODE -ne 0) { throw 'Error de PyInstaller.' }

$aplicacion = Join-Path $PWD 'dist\SepararBoletas'
$motores = Join-Path $aplicacion '_internal\motores'
$idiomas = Join-Path $motores 'tessdata'
New-Item -ItemType Directory -Force -Path $idiomas | Out-Null
Copy-Item -LiteralPath (Join-Path $bin 'tesseract.exe'), (Join-Path $bin 'pdftoppm.exe') -Destination $motores
Get-ChildItem -LiteralPath $bin -Filter '*.dll' -File | Copy-Item -Destination $motores
Copy-Item -LiteralPath 'spa.traineddata' -Destination $idiomas

# Prueba el ejecutable empaquetado con un escaneo ficticio y sin Conda en PATH.
$prueba = Join-Path ([System.IO.Path]::GetTempPath()) ("boletas-" + [guid]::NewGuid())
$entrada = Join-Path $prueba 'entrada'
$salida = Join-Path $prueba 'salida'
New-Item -ItemType Directory -Path $entrada -Force | Out-Null
$pathOriginal = $env:PATH
try {
    python -c 'from PIL import Image, ImageDraw, ImageFont; import sys; im = Image.new("RGB",(1100,550),"white"); d = ImageDraw.Draw(im); f = ImageFont.load_default(size=48); d.text((80,100),"Nombre: ANA EJEMPLO",font=f,fill="black"); im.save(sys.argv[1],resolution=150,save_all=True,append_images=[im])' (Join-Path $entrada 'ejemplo.pdf')
    if ($LASTEXITCODE -ne 0) { throw 'Error al crear el escaneo de prueba.' }
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $exe = Join-Path $aplicacion 'SepararBoletas.exe'
    $argumentos = '--verificar "{0}" "{1}"' -f $entrada, $salida
    $proceso = Start-Process -FilePath $exe -ArgumentList $argumentos -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { throw "Falló la prueba del ejecutable (código $($proceso.ExitCode))." }
    foreach ($n in 1, 2) {
        if (!(Test-Path -LiteralPath (Join-Path $salida "ANA EJEMPLO - $n.pdf"))) {
            throw "No se generó la boleta de prueba $n."
        }
    }
}
finally {
    $env:PATH = $pathOriginal
    Remove-Item -LiteralPath $prueba -Recurse
}

Compress-Archive -LiteralPath $aplicacion -DestinationPath 'dist\SepararBoletas-Windows-x64.zip' -Force
