from flask import Flask, render_template, request, redirect, url_for
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
bot_logs = []  # logs visibles desde el menú hamburguesa

def log(msg: str):
    """Guarda y muestra mensajes del bot"""
    print(msg)
    bot_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(bot_logs) > 200:
        bot_logs.pop(0)

def run_bot(user, password, destino):
    """Ejecuta el bot principal"""
    global bot_active
    bot_active = True
    log("🚀 Bot iniciado...")

    try:
        with sync_playwright() as p:
            # ✅ Configurar Chromium correctamente para Render
            browser = p.chromium.launch(
                headless=True,
                executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_PATH", None)
            )
            page = browser.new_page()
            page.set_default_timeout(25000)

            log("🌐 Abriendo página de inicio de sesión...")
            page.goto("https://clubcampestrebucaramanga.com/empresa/login", wait_until="domcontentloaded")

            page.fill("#txtEmail", user)
            page.fill("#txtPassword", password)
            page.click("button.btn.btn-success.btn-block, button[type='submit']")

            # Esperar a que cargue el home
            page.wait_for_url("**/empresa/home**", timeout=25000)
            log("✅ Inicio de sesión exitoso.")

            # === Ir al módulo TeeTime ===
            TEETIME_URL = "https://clubcampestrebucaramanga.com/empresa/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09"
            page.goto(TEETIME_URL)
            time.sleep(3)

            # === Intentar acceder al iframe ===
            frames = page.frames
            frame = None
            for f in frames:
                if "teetime" in (f.url or ""):
                    frame = f
                    break

            if not frame:
                frame = page.main_frame
                log("⚠️ No se detectó iframe, usando frame principal.")
            else:
                log("📄 Iframe de TeeTime encontrado correctamente.")

            # === Buscar el día siguiente ===
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
                    try:
                        celdas = filas.nth(i).locator("td")
                        texto = celdas.nth(1).inner_text(timeout=1500)
                        if fecha_texto in texto:
                            log(f"✅ Fecha encontrada en fila {i + 1}")
                            filas.nth(i).locator("a").click()
                            time.sleep(2)
                            reserva_completada = True
                            break
                    except Exception:
                        continue

                if not reserva_completada:
                    time.sleep(2)
                    try:
                        frame.reload()
                    except Exception:
                        page.reload()

            if not reserva_completada:
                raise Exception("❌ No se encontró la fecha o no había horarios disponibles.")

            # === Buscar horarios ===
            log("🔔 Buscando horarios disponibles...")
            botones = frame.locator(".boton_tee")
            if botones.count() == 0:
                raise Exception("No se encontraron horarios disponibles.")

            primer_horario = botones.nth(0)
            horario_texto = primer_horario.inner_text()
            primer_horario.click()
            log(f"⛳ Reserva realizada en horario: {horario_texto}")

            # === Enviar WhatsApp de confirmación ===
            client = Client(ACCOUNT_SID, AUTH_TOKEN)
            client.messages.create(
                from_=TWILIO_WHATSAPP,
                body=f"✅ Reserva completada con éxito para el {fecha_texto} - Horario: {horario_texto}",
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
