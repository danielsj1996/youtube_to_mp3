import os
import re
import zipfile
import uuid
import threading
from datetime import datetime
from flask import Flask, request, send_file, redirect, render_template, jsonify
from werkzeug.utils import safe_join
from yt_dlp import YoutubeDL

app = Flask(__name__)

progresos = {}
resultados = {}
os.makedirs("temp", exist_ok=True)
os.makedirs("descargas", exist_ok=True)

@app.route("/")
def index():
    return render_template(
        "index.html",
        historial_audio=leer_historial("historial_audio.txt"),
        historial_video=leer_historial("historial_video.txt"),
    )

def leer_historial(nombre):
    if os.path.exists(nombre):
        with open(nombre, "r", encoding="utf-8") as f:
            lineas = f.readlines()[-5:]
            return "<ul>" + "".join(f"<li>{l.strip()}</li>" for l in reversed(lineas)) + "</ul>"
    return "<p>No hay conversiones aún.</p>"

@app.route("/convertir", methods=["POST"])
def convertir():
    urls = request.form.getlist("urls")
    if not urls or len(urls) == 0:
        single_url = request.form.get("url")
        if single_url:
            urls = [single_url]
    if not urls or len(urls) == 0:
        return jsonify({"error": "No se recibieron URLs para convertir"}), 400

    calidad = request.form.get("calidad", "192")
    formato = request.form.get("formato", "mp3")
    inicio = request.form.get("inicio")
    fin = request.form.get("fin")

    id_tarea = str(uuid.uuid4())
    progresos[id_tarea] = 0

    def convertir_todo(urls, calidad, formato, inicio, fin, id_tarea):
        try:
            carpeta = f"temp/{id_tarea}"
            os.makedirs(carpeta, exist_ok=True)
            archivos_generados = []

            for url in urls:
                ydl_opts = {
                    'quiet': True,
                    'progress_hooks': [lambda d: hook(d, id_tarea)],
                    'outtmpl': f'{carpeta}/%(title)s.%(ext)s',
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': formato,
                        'preferredquality': calidad
                    }],
                }

                if inicio or fin:
                    postproc_trim = {
                        'key': 'FFmpegAudioTrim',
                        'start_time': inicio if inicio else '0',
                        'end_time': fin if fin else None
                    }
                    ydl_opts['postprocessors'].insert(0, postproc_trim)

                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = limpiar(info['title']) + f".{formato}"
                    archivos_generados.append(os.path.join(carpeta, filename))

            if len(archivos_generados) > 1:
                zip_path = f"descargas/{id_tarea}.zip"
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                with zipfile.ZipFile(zip_path, 'w') as z:
                    for file in archivos_generados:
                        z.write(file, arcname=os.path.basename(file))
                guardar_historial("historial_audio.txt", f"ZIP: {len(archivos_generados)} archivos convertidos")
                resultados[id_tarea] = f"{id_tarea}.zip"
            else:
                archivo_unico = archivos_generados[0]
                nombre_final = os.path.basename(archivo_unico)
                destino = f"descargas/{nombre_final}"
                if os.path.exists(destino):
                    os.remove(destino)
                os.rename(archivo_unico, destino)
                guardar_historial("historial_audio.txt", nombre_final)
                resultados[id_tarea] = nombre_final

            progresos[id_tarea] = 100

        except Exception as e:
            print(f"Error en convertir_todo: {e}")
            progresos[id_tarea] = -1

    threading.Thread(target=convertir_todo, args=(urls, calidad, formato, inicio, fin, id_tarea)).start()
    return jsonify({"id": id_tarea})

@app.route("/progreso/<id>")
def progreso(id):
    return jsonify({'porcentaje': progresos.get(id, 0)})

@app.route("/resultado/<id>")
def resultado(id):
    nombre = resultados.get(id)
    if nombre:
        ruta = os.path.join("descargas", nombre)
        if os.path.exists(ruta):
            return render_template("resultado.html",
                                   nombre=nombre,
                                   nombre_original=nombre,
                                   url_descarga=f"/descargas/{nombre}")
    return "Archivo no encontrado", 404

@app.route("/descargar-video", methods=["POST"])
def descargar_video():
    url = request.form["url_video"]
    calidad_video = request.form.get("calidad_video", "720")

    id_tarea = str(uuid.uuid4())
    progresos[id_tarea] = 0

    format_map = {
        "240": "bestvideo[height<=240]+bestaudio/best[height<=240]",
        "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    }
    formato_yt = format_map.get(calidad_video, "bestvideo[height<=720]+bestaudio/best[height<=720]")

    def descargar_y_procesar():
        try:
            carpeta = f"temp/{id_tarea}"
            os.makedirs(carpeta, exist_ok=True)
            ydl_opts = {
                'format': formato_yt,
                'outtmpl': f'{carpeta}/%(title)s.%(ext)s',
                'merge_output_format': 'mp4',
                'progress_hooks': [lambda d: hook(d, id_tarea)],
                'quiet': True
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            nombre_video = limpiar(info.get("title", "video")) + ".mp4"
            destino = f"descargas/{nombre_video}"

            archivos = os.listdir(carpeta)
            if archivos:
                origen = os.path.join(carpeta, archivos[0])
                if os.path.exists(destino):
                    os.remove(destino)
                os.rename(origen, destino)

            guardar_historial("historial_video.txt", nombre_video)
            resultados[id_tarea] = nombre_video
            progresos[id_tarea] = 100
        except Exception as e:
            print(f"Error descargar_video: {e}")
            progresos[id_tarea] = -1

    hilo = threading.Thread(target=descargar_y_procesar)
    hilo.start()

    # Retornamos ID para que el front pueda usar el progreso y luego acceder al resultado
    return jsonify({"id": id_tarea})

@app.route("/descargas/<nombre>")
def descargar_directo(nombre):
    path = safe_join("descargas", nombre)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=nombre)
    return "Archivo no encontrado", 404

@app.route("/detectar_playlist", methods=["POST"])
def detectar_playlist():
    url = request.form["url"]
    try:
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get('_type') == 'playlist':
                return jsonify({
                    'es_playlist': True,
                    'videos': [
                        {'title': entry['title'], 'url': entry['webpage_url']}
                        for entry in info['entries']
                    ]
                })
    except Exception as e:
        print("Error al detectar playlist:", e)

    return jsonify({'es_playlist': False})

def guardar_historial(archivo, texto):
    with open(archivo, "a", encoding="utf-8") as h:
        h.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {texto}\n")

def limpiar(texto):
    return re.sub(r'[\\/*?"<>|]', "", texto)

def hook(d, id):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        if total:
            progresos[id] = int(downloaded * 100 / total)
    elif d['status'] == 'finished':
        progresos[id] = 95

if __name__ == "__main__":
    app.run(debug=True)
