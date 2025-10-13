# main.py
from flask import Flask, render_template, request, redirect, url_for
import threading
import time
from datetime import datetime, timedelta
from twilio.rest import Client
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

app = Flask(__name__)

# === Twilio ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

bot_thread = None
bot_active = False

TEETIME_URL = "https://clubcampestrebucaramanga.com/empresa/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09"
INTENTOS = 50
ESPERA_ENTRE_INTENTOS = 1

def run_bot(user, password, destino):
    global bot_active
    bot_active = True

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)  # Headless para servidores
            page = browser.new_page()
            
            # === Login ===
            page.goto("https://clubcampestrebucaramanga.com/empresa/login")
            page.fill("#txtEmail", user)
            page.fill("#txtPassword", password)
            
            # Intentar click en botón "Ingresar"
            try:
                botones = page.query_selector_all("button.btn.btn-success.btn-block")
                for btn in botones:
                    if "Ingresar" in btn.inner_text():
                        btn.click()
                        break
            except:
                page.click("button[type='submit']")
            
            # Esperar a la página principal
            page.wait_for_url("/empresa/home", timeout=15000)
            print("✅ Inicio de sesión completado.")
            
            # === Ir a Teetime ===
            page.goto(TEETIME_URL)
            time.sleep(2)
            
            # Manejar iframe si existe
            try:
                frame = page.frame_locator("iframe")
            except:
                frame = page

            manana = datetime.now() + timedelta(days=1)
            fecha_texto = manana.strftime("%d-%m-%Y")
            reserva_completada = False
            intentos_realizados = 0

            while bot_active and not reserva_completada and intentos_realizados < INTENTOS:
                intentos_realizados += 1

                # Buscar fechas
                links_fecha = frame.locator("a").all()
                fecha_disponible = None
                for link in links_fecha:
                    try:
                        onclick = link.get_attribute("onclick") or ""
                        text = link.inner_text() or ""
                        if fecha_texto in onclick or fecha_texto in text:
                            link.scroll_into_view_if_needed()
                            link.click()
                            time.sleep(0.5)
                            fecha_disponible = link
                            break
                    except PlaywrightTimeoutError:
                        continue

                if not fecha_disponible:
                    time.sleep(ESPERA_ENTRE_INTENTOS)
                    page.reload()
                    continue

                # Buscar primer horario disponible
                botones_hora = frame.locator(".boton_tee").all()
                if not botones_hora:
                    time.sleep(ESPERA_ENTRE_INTENTOS)
                    page.reload()
                    continue

                primer_boton = botones_hora[0]
                primer_boton.scroll_into_view_if_needed()
                primer_boton.click()
                
                # Enviar WhatsApp
                client = Client(ACCOUNT_SID, AUTH_TOKEN)
                client.messages.create(
                    from_=TWILIO_WHATSAPP,
                    body=f"✅ Reserva completada: {primer_boton.inner_text().strip()}",
                    to=destino
                )
                reserva_completada = True

            browser.close()

    except Exception as e:
        # Enviar mensaje si falla
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            body=f"❌ Error en el bot de reserva: {e}",
            to=destino
        )
    finally:
        bot_active = False

@app.route("/", methods=["GET", "POST"])
def index():
    global bot_thread
    if request.method == "POST":
        if "activar" in request.form:
            user = request.form.get("user")
            password = request.form.get("password")
            telefono = request.form.get("telefono")

            bot_thread = threading.Thread(target=run_bot, args=(user, password, telefono))
            bot_thread.start()
            return redirect(url_for("index"))

        elif "pausar" in request.form:
            global bot_active
            bot_active = False
            return redirect(url_for("index"))

    return render_template("index.html", bot_active=bot_active)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
