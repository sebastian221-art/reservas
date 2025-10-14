from flask import Flask, render_template, request, redirect, url_for, jsonify
import threading
import time
import os
from datetime import datetime, timedelta
from twilio.rest import Client
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

app = Flask(__name__)

# === Twilio ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

# === Variables globales ===
bot_thread = None
bot_active = False
bot_logs = []

# === Función de log ===
def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    bot_logs.append(entry)
    if len(bot_logs) > 150:
        bot_logs.pop(0)

# === Lógica del bot ===
def run_bot(user, password, destino):
    global bot_active
    bot_active = True
    log("🚀 Bot iniciado...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(20000)

            # --- Login ---
            log("🌐 Abriendo página de inicio de sesión...")
            page.goto("https://clubcampestrebucaramanga.com/empresa/login")

            page.fill("#txtEmail", user)
            page.fill("#txtPassword", password)
            page.click("button.btn.btn-success.btn-block, button[type='submit']")
            page.wait_for_url("**/empresa/home**")
            log("✅ Inicio de sesión exitoso.")

            # --- Ir al módulo TeeTime ---
            TEETIME_URL = "https://clubcampestrebucaramanga.com/empresa/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09"
            log("🏌️‍♂️ Entrando al módulo TeeTime...")
            page.goto(TEETIME_URL)
            time.sleep(2)

            try:
                frame = page.frame_locator("iframe")
                log("📄 Iframe encontrado, entrando...")
            except Exception:
                frame = page.main_frame
                log("⚠️ No se encontró iframe, usando frame principal.")

            # --- Buscar el día siguiente ---
            manana = datetime.now() + timedelta(days=1)
            fecha_texto = manana.strftime("%d-%m-%Y")
            log(f"🗓 Buscando la fecha: {fecha_texto}")

            intentos = 0
            reserva_completada = False

            while bot_active and not reserva_completada and intentos < 40:
                intentos += 1
                filas = frame.locator("table.mitabla tbody tr.mitabla")
                count = filas.count()
                log(f"🔎 Intento {intentos} - Filas encontradas: {count}")

                for i in range(count):
                    celdas = filas.nth(i).locator("td")
                    texto = celdas.nth(1).inner_text(timeout=1000)
                    if fecha_texto in texto:
                        log(f"✅ Fecha encontrada en fila {i+1}")
                        filas.nth(i).locator("a").click()
                        time.sleep(2)
                        reserva_completada = True
                        break

                if not reserva_completada:
                    time.sleep(1)
                    frame.reload()

            if not reserva_completada:
                raise Exception("No se encontró la fecha o no había horarios disponibles")

            log("⌚ Buscando horarios disponibles...")
            botones = frame.locator(".boton_tee")
            if botones.count() == 0:
                raise Exception("No se encontraron horarios")

            primer_horario = botones.nth(0)
            horario_texto = primer_horario.inner_text()
            primer_horario.click()
            log(f"⛳ Reserva realizada en horario: {horario_texto}")

            # --- WhatsApp ---
            client = Client(ACCOUNT_SID, AUTH_TOKEN)
            client.messages.create(
                from_=TWILIO_WHATSAPP,
                body=f"✅ Reserva completada: {horario_texto}",
                to=destino
            )
            log("📩 Notificación de WhatsApp enviada.")

            browser.close()
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
        except:
            log("⚠️ No se pudo enviar mensaje de error por WhatsApp.")
    finally:
        bot_active = False


# === Rutas Flask ===
@app.route("/", methods=["GET", "POST"])
def index():
    global bot_thread
    if request.method == "POST":
        if "activar" in request.form:
            user = request.form.get("user")
            password = request.form.get("password")
            telefono = request.form.get("telefono")
            if not bot_active:
                bot_thread = threading.Thread(target=run_bot, args=(user, password, telefono))
                bot_thread.start()
        elif "pausar" in request.form:
            global bot_active
            bot_active = False
            log("⏸ Bot pausado manualmente.")
    return render_template("index.html", bot_active=bot_active)


@app.route("/logs")
def get_logs():
    return jsonify(bot_logs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log("🧩 Servidor Flask iniciado.")
    app.run(host="0.0.0.0", port=port)
