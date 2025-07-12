# youtube_to_mp3

Requisitos para ejecutar el proyecto
1. Python 3.8 o superior
Podés descargarlo desde: https://www.python.org/downloads/

2. FFmpeg (🔧 requerido para convertir audio/video)
Es esencial para que yt-dlp pueda recodificar, cortar, unir o extraer audio.

👉 Cómo instalarlo:
En Windows:
Descargá el .zip de https://ffmpeg.org/download.html > Windows > git builds (por ejemplo: Gyan.dev)

Extraé la carpeta y agregá la ruta de /bin al PATH del sistema (en variables de entorno)

3. Librerías Python necesarias
En la raíz del proyecto tendrás un archivo requirements.txt. Para instalar todas las dependencias, solo ejecutá:

pip install -r requirements.txt

Ese archivo incluye:
Flask==2.3.2
yt-dlp==2025.06.06

Forma de uso
Copiar el enlace del video de youtube a convertir y luego hacer clic en convertir, anteriormente seleccionando el formato de audio y calidad 
