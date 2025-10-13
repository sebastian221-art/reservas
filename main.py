from flask import Flask, render_template, request, redirect, url_for
import threading
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
from twilio.rest import Client
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
options.add_argument("--headless")  # necesario en servidores
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


load_dotenv()

app = Flask(__name__)

# Twilio
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

bot_thread = None
bot_active = False

def run_bot(user, password, destino):
    global bot_active
    bot_active = True

    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # webdriver-manager se encarga de descargar ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    TEETIME_URL = "https://clubcampestrebucaramanga.com/empresa/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09"
    INTENTOS = 50
    ESPERA_ENTRE_INTENTOS = 1

    try:
        driver.get("https://clubcampestrebucaramanga.com/empresa/login")
        wait.until(EC.presence_of_element_located((By.ID, "txtEmail")))
        driver.find_element(By.ID, "txtEmail").send_keys(user)
        driver.find_element(By.ID, "txtPassword").send_keys(password)

        botones = driver.find_elements(By.CSS_SELECTOR, "button.btn.btn-success.btn-block")
        for btn in botones:
            if "Ingresar" in btn.text:
                btn.click()
                break

        wait.until(EC.url_contains("/empresa/home"))
        driver.get(TEETIME_URL)
        time.sleep(2)

        try:
            iframe = driver.find_element(By.TAG_NAME, "iframe")
            driver.switch_to.frame(iframe)
        except:
            pass

        manana = datetime.now() + timedelta(days=1)
        fecha_texto = manana.strftime("%d-%m-%Y")
        reserva_completada = False
        intentos_realizados = 0

        while bot_active and not reserva_completada and intentos_realizados < INTENTOS:
            intentos_realizados += 1
            links_fecha = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'xajax_teeTimeFecha')]")
            fecha_disponible = None

            for link in links_fecha:
                if fecha_texto in link.get_attribute("onclick") or fecha_texto in link.text:
                    driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    time.sleep(0.1)
                    link.click()
                    time.sleep(0.5)
                    fecha_disponible = link
                    break

            if not fecha_disponible:
                time.sleep(ESPERA_ENTRE_INTENTOS)
                driver.refresh()
                continue

            botones_hora = driver.find_elements(By.CLASS_NAME, "boton_tee")
            if len(botones_hora) == 0:
                time.sleep(ESPERA_ENTRE_INTENTOS)
                driver.refresh()
                continue

            primer_boton = botones_hora[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", primer_boton)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", primer_boton)

            # Enviar mensaje WhatsApp
            client = Client(ACCOUNT_SID, AUTH_TOKEN)
            client.messages.create(
                from_=TWILIO_WHATSAPP,
                body=f"✅ Reserva completada: {primer_boton.text.strip()}",
                to=destino
            )
            reserva_completada = True

    except Exception as e:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            body=f"❌ Error en el bot de reserva: {e}",
            to=destino
        )
    finally:
        driver.quit()
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
    app.run(debug=False)  # debug=False para versión final
