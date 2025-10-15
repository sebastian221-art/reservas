require('dotenv').config();
const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const { Client } = require('twilio');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'views')));

// Twilio
const ACCOUNT_SID = process.env.TWILIO_SID;
const AUTH_TOKEN = process.env.AUTH_TOKEN;
const TWILIO_WHATSAPP = process.env.TWILIO_WHATSAPP;

// Estado del bot y logs
let bot_active = false;
let bot_logs = [];
let stopRequested = false;

// Función para agregar logs
function log(msg) {
    const timestamp = new Date().toLocaleTimeString();
    const line = `[${timestamp}] ${msg}`;
    console.log(line);
    bot_logs.push(line);
    if (bot_logs.length > 200) bot_logs.shift();
}

// Función para dormir X ms
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Función principal del bot con reintentos
async function runBot(user, password, telefono) {
    bot_active = true;
    stopRequested = false;
    log("🚀 Bot iniciado...");

    const session = axios.create({
        baseURL: 'https://clubcampestrebucaramanga.com/empresa',
        headers: { 'User-Agent': 'Mozilla/5.0' }
    });

    while (!stopRequested) {
        try {
            // LOGIN
            log("🌐 Intentando iniciar sesión...");
            const loginForm = new URLSearchParams();
            loginForm.append('txtEmail', user);
            loginForm.append('txtPassword', password);
            loginForm.append('origen', 'login');

            const loginRes = await session.post('/login', loginForm.toString(), {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
            });

            if (loginRes.status !== 200 || !loginRes.data.includes('empresa/home')) {
                throw new Error("❌ Credenciales incorrectas o login fallido");
            }
            log("✅ Sesión iniciada correctamente");

            // ABRIR TEE TIME
            log("📄 Abriendo módulo TeeTime...");
            const teetimeRes = await session.get('/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09');
            const $ = cheerio.load(teetimeRes.data);

            // FECHA DEL DÍA SIGUIENTE
            const manana = new Date();
            manana.setDate(manana.getDate() + 1);
            const fechaTexto = manana.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' });
            log(`🗓 Buscando la fecha: ${fechaTexto}`);

            // BUSCAR LINK DE LA FECHA
            let linkDia = null;
            $('table.mitabla tbody tr').each((i, el) => {
                if ($(el).text().includes(fechaTexto)) {
                    linkDia = $(el).find('a').attr('href');
                }
            });

            if (!linkDia) {
                log("❌ No se encontró la fecha disponible. Reintentando en 10s...");
                await sleep(10000);
                continue; // Reintenta
            }

            // OBTENER HORARIOS
            const detalleRes = await session.get(linkDia);
            const $$ = cheerio.load(detalleRes.data);
            const boton = $$('.boton_tee').first();

            if (!boton.length) {
                log("❌ No hay horarios disponibles. Reintentando en 10s...");
                await sleep(10000);
                continue; // Reintenta
            }

            const horario = boton.text().trim();
            log(`⛳ Reserva detectada: ${horario}`);

            // ENVIAR MENSAJE POR WHATSAPP
            const client = new Client(ACCOUNT_SID, AUTH_TOKEN);
            await client.messages.create({
                from: TWILIO_WHATSAPP,
                body: `✅ Reserva detectada para ${fechaTexto} - Horario: ${horario}`,
                to: telefono
            });
            log("📩 Mensaje enviado por WhatsApp");

            break; // Encontró horario, salir del bucle

        } catch (err) {
            log(`❌ Error: ${err.message}`);
            try {
                const client = new Client(ACCOUNT_SID, AUTH_TOKEN);
                await client.messages.create({
                    from: TWILIO_WHATSAPP,
                    body: `❌ Error en bot de reserva: ${err.message}`,
                    to: telefono
                });
            } catch {
                log("⚠️ No se pudo enviar mensaje de error por WhatsApp");
            }
            log("Reintentando en 10s...");
            await sleep(10000); // Espera antes de reintentar
        }
    }

    bot_active = false;
    log("🛑 Bot finalizado");
}

// ENDPOINTS

// Obtener logs en tiempo real
app.get('/logs', (req, res) => {
    res.json({ logs: bot_logs, bot_active });
});

// Activar o pausar bot
app.post('/bot', (req, res) => {
    const { action, user, password, telefono } = req.body;
    if (action === 'activar' && !bot_active) {
        runBot(user, password, telefono);
    } else if (action === 'pausar') {
        stopRequested = true;
        log("⏸ Bot pausado manualmente");
    }
    res.json({ success: true });
});

// SERVIDOR
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Servidor escuchando en puerto ${PORT}`));
