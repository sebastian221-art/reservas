require('dotenv').config();
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const axios = require('axios');
const cheerio = require('cheerio');
const { Client } = require('twilio');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.urlencoded({ extended: true }));
app.set('view engine', 'ejs');

const ACCOUNT_SID = process.env.TWILIO_SID;
const AUTH_TOKEN = process.env.AUTH_TOKEN;
const TWILIO_WHATSAPP = process.env.TWILIO_WHATSAPP;

let bot_active = false;

function log(msg) {
    const timestamp = new Date().toLocaleTimeString();
    const line = `[${timestamp}] ${msg}`;
    console.log(line);
    io.emit('log', line);
}

async function runBot(user, password, destino) {
    bot_active = true;
    log("🚀 Bot iniciado");

    const session = axios.create({
        baseURL: 'https://clubcampestrebucaramanga.com/empresa',
        headers: { 'User-Agent': 'Mozilla/5.0' }
    });

    try {
        log("🌐 Iniciando sesión...");
        const loginForm = new URLSearchParams();
        loginForm.append('txtEmail', user);
        loginForm.append('txtPassword', password);
        loginForm.append('origen', 'login');

        const loginRes = await session.post('/login', loginForm.toString(), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });

        if (!loginRes.data.includes('empresa/home')) throw new Error("❌ Credenciales incorrectas");
        log("✅ Sesión iniciada correctamente");

        log("📄 Abriendo módulo TeeTime...");
        const teetimeRes = await session.get('/home/teetime/d2JjS0E1bCtmeFhlZ3FmMnBHa2RrUT09');
        const $ = cheerio.load(teetimeRes.data);

        const manana = new Date();
        manana.setDate(manana.getDate() + 1);
        const fechaTexto = manana.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' });
        log(`🗓 Buscando la fecha: ${fechaTexto}`);

        let linkDia = null;
        $('table.mitabla tbody tr').each((i, el) => {
            if ($(el).text().includes(fechaTexto)) {
                linkDia = $(el).find('a').attr('href');
            }
        });

        if (!linkDia) throw new Error("❌ No se encontró la fecha disponible");

        const detalleRes = await session.get(linkDia);
        const $$ = cheerio.load(detalleRes.data);
        const boton = $$('.boton_tee').first();
        if (!boton.length) throw new Error("❌ No hay horarios disponibles");

        const horario = boton.text().trim();
        log(`⛳ Reserva simulada: ${horario}`);

        const client = new Client(ACCOUNT_SID, AUTH_TOKEN);
        await client.messages.create({
            from: TWILIO_WHATSAPP,
            body: `✅ Reserva detectada para ${fechaTexto} - Horario: ${horario}`,
            to: destino
        });
        log("📩 Mensaje enviado por WhatsApp");

    } catch (err) {
        log(`❌ Error: ${err.message}`);
        try {
            const client = new Client(ACCOUNT_SID, AUTH_TOKEN);
            await client.messages.create({
                from: TWILIO_WHATSAPP,
                body: `❌ Error en bot de reserva: ${err.message}`,
                to: destino
            });
        } catch {
            log("⚠️ No se pudo enviar mensaje de error por WhatsApp");
        }
    } finally {
        bot_active = false;
    }
}

app.get('/', (req, res) => res.render('index'));

app.post('/', (req, res) => {
    if (req.body.activar && !bot_active) {
        runBot(req.body.user, req.body.password, req.body.telefono);
    } else if (req.body.pausar) {
        bot_active = false;
        log("⏸ Bot pausado manualmente");
    }
    res.redirect('/');
});

const PORT = process.env.PORT || 5000;
server.listen(PORT, () => log(`Servidor escuchando en puerto ${PORT}`));
