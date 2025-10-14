from flask import Flask, render_template, request, redirect, url_for
import threading
import time
import os
from datetime import datetime, timedelta
from twilio.rest import Client
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()
app = Flask(__name__)

# === Twilio ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

# === Variables globales ===
bot_thread = None
bot_active = False
bot_logs = []  # logs visibles desde el menú hamburguesa


def log(msg: str):
    """Guarda y muestra mensajes del bot"""
    print(msg)
    bot_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(bot_logs) > 200:
        bot_logs.pop(0)


def run_bot(user, password, destino):
    """Bot de reservas sin Playwright"""
    global bot_active
    bot_active = True
    log("🚀 Bot iniciado (modo requests + BeautifulSoup)...")

    session = requests.Session()
    base_url = "https://clubcampestrebucaramanga.com"

    try:
        # === Iniciar sesión ===
        login_url = f"{base_url}/empresa/login"
        log("🌐 Iniciando sesión en el portal...")

        payload = {
            "txtEmail": user,
            "txtPassword": password
        }
        response = session.post(login_url, data=payload)
        if "empresa/home" not in response.text:
            raise Exception("Error al iniciar sesión. Credenciales incorrectas.")

        log("✅ Sesión iniciada correctamente.")

        # === Acceder al módulo Tee Time ===
        teetime_url = f"{base_url}/empresa/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09"
        log("📄 Abriendo módulo TeeTime...")
        r = session.get(teetime_url)
        soup = BeautifulSoup(r.text, "html.parser")

        # === Buscar el día siguiente ===
        manana = datetime.now() + timedelta(days=1)
        fecha_texto = manana.strftime("%d-%m-%Y")
        log(f"🗓 Buscando la fecha: {fecha_texto}")

        filas = soup.select("table.mitabla tbody tr.mitabla")
        fila_objetivo = None

        for fila in filas:
            if fecha_texto in fila.get_text():
                fila_objetivo = fila
                break

        if not fila_objetivo:
            raise Exception("❌ No se encontró la fecha disponible para reserva.")

        # Simular que entramos a la página del día
        link = fila_objetivo.find("a")["href"]
        detalle_url = f"{base_url}{link}"
        log(f"🔗 Entrando a {detalle_url}")
        r_detalle = session.get(detalle_url)
        soup_detalle = BeautifulSoup(r_detalle.text, "html.parser")

        botones = soup_detalle.select(".boton_tee")
        if not botones:
            raise Exception("❌ No se encontraron horarios disponibles.")

        horario_texto = botones[0].get_text(strip=True)
        log(f"⛳ Reserva simulada: {horario_texto}")

        # === Enviar WhatsApp ===
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            body=f"✅ Reserva detectada con éxito para {fecha_texto} - Horario: {horario_texto}",
            to=destino
        )

        log("📩 Mensaje de confirmación enviado por WhatsApp.")
        log("🎯 Bot finalizado correctamente.")

    except Exception as e:
        log(f"❌ Error: {e}")
        try:
            client = Client(ACCOUNT_SID, AUTH_TOKEN)
            client.messages.create(
                from_=TWILIO_WHATSAPP,
                body=f"❌ Error en el bot de reserva: {e}",
                to=destino
            )
        except Exception:
            log("⚠️ No se pudo enviar mensaje de error por WhatsApp.")
    finally:
        bot_active = False


@app.route("/", methods=["GET", "POST"])
def index():
    global bot_thread, bot_active

    if request.method == "POST":
        if "activar" in request.form:
            user = request.form.get("user")
            password = request.form.get("password")
            telefono = request.form.get("telefono")

            if not bot_active:
                bot_thread = threading.Thread(target=run_bot, args=(user, password, telefono))
                bot_thread.start()
                return redirect(url_for("index"))

        elif "pausar" in request.form:
            bot_active = False
            log("⏸ Bot pausado manualmente.")
            return redirect(url_for("index"))

    return render_template("index.html", bot_active=bot_active, logs=bot_logs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
