import os
import re
import zipfile
import uuid
import threading
import tempfile
import glob
import shutil
import urllib.parse
from datetime import datetime
from yt_dlp.utils import DownloadError
from flask import (
    Flask, request, send_file, redirect,
    render_template, jsonify, after_this_request
)
from werkzeug.utils import safe_join
from yt_dlp import YoutubeDL

app = Flask(__name__)

# ──────────────────────────────────────────────────────────────
# Rutas de trabajo
TEMP_DIR = "temp"
DESCARGAS_DIR = os.path.join(tempfile.gettempdir(), "yt_descargas")
os.makedirs(TEMP_DIR,        exist_ok=True)
os.makedirs(DESCARGAS_DIR,   exist_ok=True)
# ──────────────────────────────────────────────────────────────

progresos  = {}
resultados = {}

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

# ─── AUDIO ────────────────────────────────────────────────────
@app.route("/convertir", methods=["POST"])
def convertir():
    urls = request.form.getlist("urls") or [request.form.get("url")] if request.form.get("url") else []
    if not urls:
        return jsonify({"error": "No se recibieron URLs para convertir"}), 400

    calidad = request.form.get("calidad", "192")
    formato = request.form.get("formato", "mp3")
    inicio  = request.form.get("inicio")
    fin     = request.form.get("fin")

    id_tarea = str(uuid.uuid4())
    progresos[id_tarea] = 0

    threading.Thread(
        target=convertir_todo,
        args=(urls, calidad, formato, inicio, fin, id_tarea)
    ).start()

    return jsonify({"id": id_tarea})

def convertir_todo(urls, calidad, formato, inicio, fin, id_tarea):
    try:
        carpeta = os.path.join(TEMP_DIR, id_tarea)
        os.makedirs(carpeta, exist_ok=True)

        for url in urls:
            ydl_opts = {
                "quiet": True,
                "progress_hooks": [lambda d: hook(d, id_tarea)],
                "outtmpl": f"{carpeta}/%(title)s.%(ext)s",   # dejamos que yt‑dlp nombre
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": formato,
                    "preferredquality": calidad,
                }],
            }
            if inicio or fin:
                ydl_opts["postprocessors"].insert(0, {
                    "key": "FFmpegAudioTrim",
                    "start_time": inicio or "0",
                    "end_time":   fin or None,
                })

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        # ── TOMAMOS lo que realmente quedó en la carpeta
        archivos_generados = glob.glob(os.path.join(carpeta, f"*.{formato}"))
        if not archivos_generados:
            raise RuntimeError("No se generó ningún archivo")

        # empaquetar o mover
        if len(archivos_generados) > 1:
            zip_path = os.path.join(DESCARGAS_DIR, f"{id_tarea}.zip")
            with zipfile.ZipFile(zip_path, "w") as z:
                for f in archivos_generados:
                    z.write(f, arcname=os.path.basename(f))
            guardar_historial("historial_audio.txt",
                              f"ZIP: {len(archivos_generados)} archivos convertidos")
            resultados[id_tarea] = os.path.basename(zip_path)
        else:
            origen   = archivos_generados[0]
            destino  = os.path.join(DESCARGAS_DIR,
                                    os.path.basename(origen))
            os.replace(origen, destino)
            guardar_historial("historial_audio.txt",
                              os.path.basename(destino))
            resultados[id_tarea] = os.path.basename(destino)

        progresos[id_tarea] = 100
    except Exception as e:
        print("Error en convertir_todo:", e)
        progresos[id_tarea] = -1
    finally:
        # Limpia la carpeta temp/<id_tarea> (aunque haya fallado)
        shutil.rmtree(carpeta, ignore_errors=True)

# ─── VIDEO ────────────────────────────────────────────────────
@app.route("/descargar-video", methods=["POST"])
def descargar_video():
    url           = request.form["url_video"]
    calidad_video = request.form.get("calidad_video", "720")

    id_tarea = str(uuid.uuid4())
    progresos[id_tarea] = 0

    formato_yt = {
        "240": "bestvideo[height<=240]+bestaudio/best[height<=240]",
        "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    }.get(calidad_video, "bestvideo[height<=720]+bestaudio/best[height<=720]")

    threading.Thread(
        target=descargar_y_procesar_video,
        args=(url, formato_yt, id_tarea)
    ).start()

    return jsonify({"id": id_tarea})

def descargar_y_procesar_video(url, formato_yt, id_tarea):
    try:
        carpeta = os.path.join(TEMP_DIR, id_tarea)
        os.makedirs(carpeta, exist_ok=True)

        ydl_opts = {
            "format": formato_yt,
            "outtmpl": f"{carpeta}/%(title)s.%(ext)s",
            "merge_output_format": "mp4",
            "progress_hooks": [lambda d: hook(d, id_tarea)],
            "quiet": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        nombre_video = limpiar(info.get("title", "video")) + ".mp4"
        destino = os.path.join(DESCARGAS_DIR, nombre_video)
        origen  = os.path.join(carpeta, os.listdir(carpeta)[0])
        os.replace(origen, destino)

        guardar_historial("historial_video.txt", nombre_video)
        resultados[id_tarea] = nombre_video
        progresos[id_tarea] = 100
    except Exception as e:
        print("Error descargar_video:", e)
        progresos[id_tarea] = -1
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

# ─── PROGRESO / RESULTADO ────────────────────────────────────
@app.route("/progreso/<id>")
def progreso(id):
    return jsonify({"porcentaje": progresos.get(id, 0)})

@app.route("/resultado/<id>")
def resultado(id):
    nombre = resultados.get(id)
    if not nombre:
        return "Archivo no encontrado", 404
    return render_template(
        "resultado.html",
        nombre=nombre,
        nombre_original=nombre,
        url_descarga=f"/descargas/{nombre}"
    )

# ─── DESCARGA DIRECTA (autolimpia) ───────────────────────────
@app.route("/descargas/<nombre>")
def descargar_directo(nombre):
    path = safe_join(DESCARGAS_DIR, nombre)
    if not os.path.exists(path):
        return "Archivo no encontrado", 404

    @after_this_request
    def cleanup(response):
        try:
            os.remove(path)
        except Exception as e:
            print("No se pudo eliminar:", e)
        return response

    return send_file(path, as_attachment=True, download_name=nombre)

# ─── DETECCIÓN DE PLAYLIST ───────────────────────────────────
@app.route("/detectar_playlist", methods=["POST"])
def detectar_playlist():
    url = request.form["url"].strip()
    parsed  = urllib.parse.urlparse(url)
    list_id = urllib.parse.parse_qs(parsed.query).get("list", [None])[0]

    # ➊ Si es un mix RD… lo devolvemos como “no playlist”
    if list_id and list_id.startswith("RD"):
        return jsonify({"es_playlist": False})

    playlist_url = f"https://www.youtube.com/playlist?list={list_id}" if list_id else url

    try:
        with YoutubeDL({"quiet": True,
                        "extract_flat": True,
                        "skip_download": True}) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            if info.get("_type") == "playlist":
                return jsonify({
                    "es_playlist": True,
                    "videos": [{"title": e["title"], "url": e["url"]}
                               for e in info.get("entries", [])]
                })
    except DownloadError as e:
        # ➋ Cualquier playlist “unviewable” ⇒ devolvemos False
        if "unviewable" in str(e):
            return jsonify({"es_playlist": False})
        print("Error al detectar playlist:", e)

    return jsonify({"es_playlist": False})
# ─── UTILIDADES ──────────────────────────────────────────────
def guardar_historial(archivo, texto):
    with open(archivo, "a", encoding="utf-8") as h:
        h.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {texto}\n")

def limpiar(texto):
    return re.sub(r'[\\/*?"<>|]', "", texto)

def hook(d, id_tarea):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        descargado = d.get("downloaded_bytes", 0)
        if total:
            progresos[id_tarea] = int(descargado * 100 / total)
    elif d["status"] == "finished":
        progresos[id_tarea] = 95

if __name__ == "__main__":
    app.run(debug=True)
