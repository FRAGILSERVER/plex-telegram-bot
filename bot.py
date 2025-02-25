# bot_plex.py
import os
import telebot
import requests  # Para comprobar si la imagen es válida
import threading
import signal
from plexapi.server import PlexServer
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PLEX_SERVER_ID = os.getenv("PLEX_SERVER_ID")

# Inicializar clientes
plex = PlexServer(PLEX_URL, PLEX_TOKEN)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

MAX_CAPTION_LENGTH = 1024  # Límite de caracteres en caption de Telegram
MAX_MESSAGE_LENGTH = 4096  # Límite de caracteres en un mensaje de Telegram

def enviar_mensaje_con_imagen(chat_id, imagen_local, mensaje):
    """
    Envía una imagen con un mensaje, asegurando que la `caption` no supere el límite.
    """
    mensaje = escape_markdown_v2(mensaje)  # ✅ Aplicamos escape antes de enviar

    if len(mensaje) > MAX_CAPTION_LENGTH:
        # Si el mensaje es demasiado largo, enviar la imagen sin caption
        with open(imagen_local, "rb") as img:
            bot.send_photo(chat_id=chat_id, photo=img)  # ✅ Enviar sin caption para evitar errores

        # Luego enviar el mensaje completo dividido en partes de 4096 caracteres
        partes = [mensaje[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(mensaje), MAX_MESSAGE_LENGTH)]
        for parte in partes:
            bot.send_message(chat_id, parte, parse_mode="MarkdownV2")
    else:
        # Si el mensaje cabe en una caption, enviarlo como caption de la imagen
        with open(imagen_local, "rb") as img:
            bot.send_photo(chat_id=chat_id, photo=img, caption=mensaje, parse_mode="MarkdownV2")


def validar_imagen(url):
    """
    Verifica si la URL devuelve una imagen válida (JPEG, PNG, etc.).
    """
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "image" in response.headers["Content-Type"]:
            return True
    except requests.RequestException:
        return False
    return False


def enviar_mensaje_largo(chat_id, mensaje):
    """ Divide el mensaje si excede el límite de Telegram (4096 caracteres) """
    max_length = 4000
    for i in range(0, len(mensaje), max_length):
        bot.send_message(chat_id, mensaje[i:i+max_length], parse_mode="MarkdownV2")

@bot.message_handler(commands=['listar'])
def listar_peliculas(message):
    query = message.text.replace('/listar', '').strip().lower()  # ✅ Eliminar espacios extra

    if not query:  # ✅ Si el usuario no especifica "pelis" o "series"
        bot.reply_to(message, "❌ Debes especificar qué listar:\n"
                              "📽 `/listar pelis` para películas\n"
                              "📺 `/listar series` para series", parse_mode="MarkdownV2")
        return

    try:
        if query == "pelis":
            peliculas = plex.library.section('PELIIIIIIIS').all()
            if not peliculas:
                bot.reply_to(message, "❌ No hay películas en el servidor.")
                return

            respuesta = "🎬 *Lista de Películas Disponibles:*\n\n"
            respuesta += "\n".join([f"📌 {escape_markdown_v2(movie.title)} \\({movie.year}\\)" for movie in peliculas])
            enviar_mensaje_largo(message.chat.id, respuesta)

        elif query == "series":
            series = plex.library.section('SERIEEEEES').all()
            if not series:
                bot.reply_to(message, "❌ No hay series en el servidor.")
                return

            respuesta = "📺 *Lista de Series Disponibles:*\n\n"
            respuesta += "\n".join([f"📌 {escape_markdown_v2(serie.title)} \\({serie.year}\\)" for serie in series])
            enviar_mensaje_largo(message.chat.id, respuesta)

        else:
            bot.reply_to(message, "❌ Comando incorrecto. Usa:\n"
                                  "- `/listar pelis` para listar películas\n"
                                  "- `/listar series` para listar series", parse_mode="MarkdownV2")

    except Exception as e:
        print(f"Error en listar_peliculas: {e}")
        bot.reply_to(message, "❌ Ocurrió un error al obtener la lista de contenidos.")


def obtener_plex_server_id():
    """
    Obtiene automáticamente el ID del servidor Plex.
    """
    try:
        return plex.machineIdentifier  # Identificador único del servidor
    except Exception as e:
        print(f"Error al obtener PLEX_SERVER_ID: {e}")
        return None


@bot.message_handler(commands=['buscar'])
def buscar_pelicula(message):
    query = message.text.replace('/buscar', '').strip()

    if not query or len(query) < 3:
        bot.reply_to(message, "❌ Debes escribir al menos 3 caracteres para buscar.\nEjemplo: `/buscar Batman 2008`", parse_mode="MarkdownV2")
        return

    # Intentar extraer el año de la consulta
    match = re.search(r'\b(\d{4})\b', query)
    year = None
    if match:
        try:
            year = int(match.group(1))
            query = query.replace(str(year), "").strip()
        except ValueError:
            year = None

    try:
        parametros_busqueda = {"title": query}
        if year:
            parametros_busqueda["year"] = year

        resultados_peliculas = plex.library.section('PELIIIIIIIS').search(**parametros_busqueda, maxresults=3)
        resultados_series = plex.library.section('SERIEEEEES').search(**parametros_busqueda, maxresults=3)

        # Si no hay resultados exactos, hacer búsqueda parcial con regex
        if not resultados_peliculas and not resultados_series:
            regex = re.compile(rf".*{re.escape(query)}.*", re.IGNORECASE)
            todas_peliculas = plex.library.section('PELIIIIIIIS').all()
            todas_series = plex.library.section('SERIEEEEES').all()

            sugerencias_peliculas = [p for p in todas_peliculas if regex.search(p.title)]
            sugerencias_series = [s for s in todas_series if regex.search(s.title)]

            if sugerencias_peliculas or sugerencias_series:
                respuesta = "⚠️ No encontré exactamente lo que buscas, pero quizás te interese:\n\n"
                for p in sugerencias_peliculas[:3]:
                    respuesta += f"🎬 {p.title} ({p.year})\n"
                for s in sugerencias_series[:3]:
                    respuesta += f"📺 {s.title} ({s.year})\n"

                bot.reply_to(message, escape_markdown_v2(respuesta), parse_mode="MarkdownV2")
                return
            else:
                bot.reply_to(message, f"❌ No encontré nada relacionado con '{query}'.", parse_mode="MarkdownV2")
                return

    except Exception as e:
        print(f"Error en buscar_pelicula: {e}")
        bot.reply_to(message, "❌ Error al conectar con Plex.")
        return

    # Construcción del mensaje con información detallada
    for movie in resultados_peliculas:
        titulo = escape_markdown_v2(movie.title or "Desconocido", strict=False)
        anio = escape_markdown_v2(str(movie.year or "Desconocido"), strict=False)
        sinopsis = escape_markdown_v2(movie.summary or "Sin descripción.", strict=False)

        enlace_web = f"https://app.plex.tv/desktop/#!/server/{PLEX_SERVER_ID}/details?key={movie.key}"
        enlace_app = f"https://l.plex.tv/desktop#!/server/{PLEX_SERVER_ID}/details?key={movie.key}"

        duracion = f"{round(movie.duration / 60000)} min" if movie.duration else "Desconocida"
        miniatura = movie.thumbUrl if movie.thumb else None

        mensaje = (
            f"🎬 *{titulo}* ({anio})\n"
            f"📖 {sinopsis}\n"
            f"⏳ Duración: {duracion}\n"
            f"🔗 [Abrir en Plex Web]({escape_markdown_v2(enlace_web)})\n"
            f"📲 [Abrir en App]({escape_markdown_v2(enlace_app)})"
        )

        if miniatura:
            enviar_mensaje_con_imagen(message.chat.id, miniatura, mensaje)
        else:
            bot.send_message(message.chat.id, mensaje, parse_mode="MarkdownV2")

    for serie in resultados_series:
        titulo = escape_markdown_v2(serie.title or "Desconocido", strict=False)
        anio = escape_markdown_v2(str(serie.year or "Desconocido"), strict=False)
        sinopsis = escape_markdown_v2(serie.summary or "Sin descripción.", strict=False)

        enlace_web = f"https://app.plex.tv/desktop/#!/server/{PLEX_SERVER_ID}/details?key={serie.key}"
        enlace_app = f"https://l.plex.tv/desktop#!/server/{PLEX_SERVER_ID}/details?key={serie.key}"

        temporadas = len(serie.seasons())
        episodios_totales = sum(len(temp.episodes()) for temp in serie.seasons())
        miniatura = serie.thumbUrl if serie.thumb else None

        mensaje = (
            f"📺 *{titulo}* ({anio})\n"
            f"📖 {sinopsis}\n"
            f"📅 Temporadas: {temporadas}\n"
            f"🎬 Episodios: {episodios_totales}\n"
            f"🔗 [Abrir en Plex Web]({escape_markdown_v2(enlace_web)})\n"
            f"📲 [Abrir en App]({escape_markdown_v2(enlace_app)})"
        )

        if miniatura:
            enviar_mensaje_con_imagen(message.chat.id, miniatura, mensaje)
        else:
            bot.send_message(message.chat.id, mensaje, parse_mode="MarkdownV2")


      
@bot.message_handler(commands=['reportar'])
def reportar_error(message):
    reporte = message.text.replace('/reportar ', '').strip()
    if reporte:
        with open("reportes.txt", "a") as file:
            file.write(reporte + "\n")
        bot.reply_to(message, f"⚠️ Reporte enviado: {escape_markdown_v2(reporte)}", parse_mode="MarkdownV2")
    else:
        bot.reply_to(message, "❌ Escribe el problema después de /reportar.")

@bot.message_handler(func=lambda message: True)
def responder(message):
    bot.reply_to(message, "🤖 *Comandos disponibles:*\n"
                          "🔍 `/listar [pelis o series]`\n"  
                          "🔍 `/buscar [película o serie]`\n"
                          "📩 `/solicitar [película o serie]`\n"
                          "⚠️ `/reportar [problema]`\n",
                 parse_mode="MarkdownV2")

def manejar_salida(sig, frame):
    """ Maneja la salida limpia del bot al recibir SIGINT (Ctrl+C) """
    print("⛔ Deteniendo el bot...")
    bot.stop_polling()
    os._exit(0)  # Cierra el script completamente

# Registrar el manejador de señal para Ctrl+C
signal.signal(signal.SIGINT, manejar_salida)

if __name__ == "__main__":
    print("🤖 Bot ejecutándose... Presiona Ctrl+C para detenerlo.")

    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"⚠️ Error en bot.polling(): {e}")
