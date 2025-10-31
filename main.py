# main.py
import asyncio
import logging
from datetime import datetime
import os
import httpx
import nest_asyncio
import time
from telegram.error import TimedOut, BadRequest
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, ForceReply
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# default config values from config.py (fallbacks si la DB no tiene valores)
from config import *

# DB helpers (async)
from database import (
    init_db, add_user, set_lang, get_lang, add_pedido, get_pedidos, get_pedido,
    search_pedidos, delete_pedido, get_all_users, set_role, get_role,
    export_pedidos_csv, backup_db, cleanup_old_pedidos,
    soporte_create_entry, soporte_get_by_admin_msg, soporte_get_open_by_user, soporte_close_by_user,
    config_set, config_get
)
from database import count_users, count_admins
from database import set_pedido_estado, assign_pedido, count_pedidos_by_estado, get_pedido_full

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- i18n texts ----------------
TEXTS = {
    "es": {
        "start": "👋 ¡Hola {name}!\nUsa el menú para hacer un pedido o cambiar idioma.",
        "menu": "🗂 Menú principal",
        "pedir_choose": "¿Qué deseas pedir?",
        "pedir_prompt": "✍️ Escribe la descripción de tu pedido de {tipo}.",
    "pedido_ok": "✅ Pedido registrado.\n🎟 Ticket: <code>{ticket}</code>",
        "no_perms": "🚫 No tienes permisos para usar este comando.",
        "global_confirm": "📢 Vas a enviar un mensaje global a {n} usuarios. Confirmar?",
        "global_sent": "✅ Mensaje global enviado. Enviados: {sent} Fallidos: {failed}",
        "idioma_set": "✅ Idioma establecido a {lang}.",
        "export_ready": "✅ Export listo: ",
        "backup_done": "✅ Backup creado: {path}",
    "eliminar_ok": "🗑 Pedido <code>{ticket}</code> eliminado.",
        "eliminar_no": "⚠️ No se encontró el ticket {ticket}.",
        "mispedidos_title": "📋 Tus pedidos:",
        "verpedidos_title": "📋 Pedidos (últimos):",
        "admin_panel": "⚙️ Panel de Administración",
        "admin_config_saved": "✅ Configuración guardada.",
        "support_sent": "✅ Tu mensaje fue enviado a los administradores.",
        "support_closed": "✅ Conversación cerrada.",
        # botones y labels
        "main_pedir": "📝 Pedir",
        "main_idioma": "🌐 Idioma",
        "main_unirse": "📢 Unirse al canal",
        "main_admin": "🛠 Admin",
        "ped_serie": "📺 Serie",
        "ped_pelicula": "🎬 Película",
        "ped_juego": "🎮 Juego",
        "ped_otro": "💡 Otra cosa",
    "volver": "🔙 Volver",
        "admin_export": " Exportar pedidos",
        "admin_backup": "💾 Backup DB",
        "admin_global": "🌍 Enviar global",
        "admin_cleanup": "🧹 Limpiar pedidos antiguos",
        "confirmar": "✅ Confirmar",
    "cancelar": "❌ Cancelar",
    "responder": "💬 Responder",
        "take": "🖐 Tomar",
        "ready": "✅ Marcar listo",
        "cancel": "❌ Cancelar",
        "24h": "24 horas",
        "7d": "7 días",
        "15d": "15 días",
        "30d": "30 días",
    },
    "en": {
        "start": "👋 Hi {name}!\nUse the menu to make a request or change language.",
        "menu": "🗂 Main menu",
        "pedir_choose": "What do you want to request?",
        "pedir_prompt": "✍️ Write the description of your {tipo} request.",
        "pedido_ok": "✅ Order registered.\n🎟 Ticket: {ticket}",
        "no_perms": "🚫 You don't have permission to use this command.",
        "global_confirm": "📢 You are about to send a global message to {n} users. Confirm?",
        "global_sent": "✅ Global message sent. Sent: {sent} Failed: {failed}",
        "idioma_set": "✅ Language set to {lang}.",
        "export_ready": "✅ Export ready: ",
        "backup_done": "✅ Backup created: {path}",
        "eliminar_ok": "🗑 Deleted order {ticket}.",
        "eliminar_no": "⚠️ Ticket {ticket} not found.",
        "mispedidos_title": "📋 Your orders:",
        "verpedidos_title": "📋 Orders (recent):",
        "admin_panel": "⚙️ Admin Panel",
        "admin_config_saved": "✅ Configuration saved.",
        "support_sent": "✅ Your message was sent to administrators.",
        "support_closed": "✅ Conversation closed.",
        # botones y labels
        "main_pedir": "📝 Request",
        "main_idioma": "🌐 Language",
        "main_unirse": "📢 Join channel",
        "main_admin": "🛠 Admin",
        "ped_serie": "📺 Series",
        "ped_pelicula": "🎬 Movie",
        "ped_juego": "🎮 Game",
        "ped_otro": "💡 Other",
        "volver": "🔙 Back",
        "admin_export": " Export orders",
        "admin_backup": "💾 DB Backup",
        "admin_global": "🌍 Global send",
        "admin_cleanup": "🧹 Cleanup old orders",
        "confirmar": "✅ Confirm",
        "cancelar": "❌ Cancel",
        "take": "🖐 Take",
        "ready": "✅ Mark ready",
        "cancel": "❌ Cancel",
        "24h": "24 hours",
        "7d": "7 days",
        "15d": "15 days",
        "30d": "30 days",
    }
}

# ------------ Keyboards / buttons -------------
def kb_main(lang="es", is_admin: bool = False):
    """Teclado principal. Muestra botón Admin solo si is_admin=True."""
    buttons = [
        [InlineKeyboardButton(get_text(lang, "main_pedir"), callback_data="menu_pedir")],
        [InlineKeyboardButton(get_text(lang, "main_idioma"), callback_data="menu_idioma")],
        [InlineKeyboardButton(get_text(lang, "main_unirse"), callback_data="open_canal")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(get_text(lang, "main_admin"), callback_data="menu_admin")])
    return InlineKeyboardMarkup(buttons)


async def build_kb_main(context: ContextTypes.DEFAULT_TYPE, lang="es", is_admin: bool = False):
    """Construye el teclado principal; si hay `canal_url` configurado, el botón
    de 'Unirse al canal' será un botón URL directo para que abra la URL al tocar.
    """
    canal = await config_get("canal_url")
    if not canal and 'CANAL_USERNAME' in globals() and CANAL_USERNAME:
        canal = CANAL_USERNAME

    buttons = [
        [InlineKeyboardButton("📝 Pedir", callback_data="menu_pedir")],
        [InlineKeyboardButton("🌐 Idioma", callback_data="menu_idioma")],
    ]

    if canal:
        # usar botón URL directo para abrir el canal al tocar
        buttons.append([InlineKeyboardButton("📢 Unirse al canal", url=canal)])
    else:
        buttons.append([InlineKeyboardButton("📢 Unirse al canal", callback_data="open_canal")])

    if is_admin:
        buttons.append([InlineKeyboardButton("🛠 Admin", callback_data="menu_admin")])

    return InlineKeyboardMarkup(buttons)

def kb_pedir(lang="es"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(lang, "ped_serie"), callback_data="pedido_serie"),
         InlineKeyboardButton(get_text(lang, "ped_pelicula"), callback_data="pedido_pelicula")],
        [InlineKeyboardButton(get_text(lang, "ped_juego"), callback_data="pedido_juego"),
         InlineKeyboardButton(get_text(lang, "ped_otro"), callback_data="pedido_otro")],
        [InlineKeyboardButton(get_text(lang, "volver"), callback_data="menu_main")]
    ])

def kb_idioma():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu_main")]
    ])

def kb_admin_main():
    # default lang es usado por quien llame esta función; muchas llamadas pasarán get_lang
    def _kb(lang="es"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, "admin_export"), callback_data="admin_export")],
            [InlineKeyboardButton(get_text(lang, "admin_backup"), callback_data="admin_backup")],
            [InlineKeyboardButton(get_text(lang, "admin_global"), callback_data="admin_global")],
            [InlineKeyboardButton(get_text(lang, "admin_cleanup"), callback_data="admin_cleanup")],
            [InlineKeyboardButton(get_text(lang, "volver"), callback_data="menu_main")]
        ])
    return _kb


def kb_admin_cleanup_options():
    # retornará un function-style builder si queremos pasar lang
    def _kb(lang="es"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, "24h"), callback_data="cleanup_days_1")],
            [InlineKeyboardButton(get_text(lang, "7d"), callback_data="cleanup_days_7")],
            [InlineKeyboardButton(get_text(lang, "15d"), callback_data="cleanup_days_15")],
            [InlineKeyboardButton(get_text(lang, "30d"), callback_data="cleanup_days_30")],
            [InlineKeyboardButton(get_text(lang, "volver"), callback_data="menu_admin")]
        ])
    return _kb

def kb_admin_config():
    # Ya no permitimos configurar canal/grupo desde el bot; todo en config.py
    def _kb(lang="es"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, "volver"), callback_data="menu_admin")]
        ])
    return _kb

def kb_confirm_global():
    def _kb(lang="es"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, "confirmar"), callback_data="global_confirm_yes"),
             InlineKeyboardButton(get_text(lang, "cancelar"), callback_data="global_confirm_no")]
        ])
    return _kb


def kb_admin_actions(ticket: str, user_id: int = None, assigned: int = None):
    """Teclado que muestran los admins junto al mensaje del pedido para
    tomar/ marcar listo/ cancelar.
    """
    row1 = [InlineKeyboardButton("🖐 Tomar", callback_data=f"take_{ticket}"),
            InlineKeyboardButton("✅ Marcar listo", callback_data=f"ready_{ticket}")]
    row2 = [InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{ticket}")]
    # si disponemos del user_id, añadir botón responder
    if user_id:
        # usar etiqueta localizada si es posible
        try:
            label = get_text('es', 'responder')
        except Exception:
            label = "💬 Responder"
        row2.insert(0, InlineKeyboardButton(label, callback_data=f"responder_ticket_{ticket}_{user_id}"))
    buttons = [row1, row2]
    return InlineKeyboardMarkup(buttons)

# ------------ util helpers -------------
def get_text(lang, key, **kwargs):
    # asegurar que las plantillas que usan {lang} reciben ese valor
    if 'lang' not in kwargs:
        kwargs['lang'] = lang
    return TEXTS.get(lang, TEXTS["es"]).get(key, key).format(**kwargs)

def generate_ticket():
    return "TCK" + datetime.now().strftime("%Y%m%d%H%M%S%f")[-14:]


# ---------------- Resiliencia: helpers con reintentos/backoff ---------------
async def _retry_call(func, *args, retries: int = 3, backoff: float = 0.5, **kwargs):
    """Llama a una coroutine `func` con reintentos exponenciales en caso de fallo.

    - retries: número total de intentos (incluye el intento inicial)
    - backoff: tiempo base en segundos, se multiplica por 2**attempt
    Devuelve el resultado de la función o None si todos los intentos fallan.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except TimedOut as e:
            last_exc = e
            logger.warning("TimedOut en %s (intento %d/%d): %s", getattr(func, '__name__', str(func)), attempt+1, retries, e)
        except Exception as e:
            # Registrar y volver a intentar en caso de errores transitorios de red
            last_exc = e
            logger.exception("Error en %s (intento %d/%d): %s", getattr(func, '__name__', str(func)), attempt+1, retries, e)

        # esperar antes del siguiente intento (si habrá otro)
        if attempt < retries - 1:
            await asyncio.sleep(backoff * (2 ** attempt))

    logger.error("Fallo tras %d intentos en %s. Última excepción: %s", retries, getattr(func, '__name__', str(func)), last_exc)
    return None


async def safe_answer(query, *args, retries: int = 3, backoff: float = 0.5, **kwargs):
    """Respuesta segura a callback query (usa reintentos)."""
    if not query:
        return None
    return await _retry_call(query.answer, *args, retries=retries, backoff=backoff, **kwargs)


async def safe_send_message(bot, chat_id, text=None, *args, retries: int = 3, backoff: float = 0.5, **kwargs):
    """Envía un mensaje con reintentos y logging.

    Retorna el Message o None si falla.
    """
    if not bot:
        return None
    return await _retry_call(bot.send_message, chat_id, text, *args, retries=retries, backoff=backoff, **kwargs)


async def safe_send_document(bot, chat_id, document, *args, retries: int = 3, backoff: float = 0.5, **kwargs):
    """Envía un documento con reintentos/backoff."""
    if not bot:
        return None
    return await _retry_call(bot.send_document, chat_id, document, *args, retries=retries, backoff=backoff, **kwargs)


async def safe_delete_message(bot, chat_id, message_id, retries: int = 2, backoff: float = 0.2):
    """Intenta eliminar un mensaje con reintentos (silencioso)."""
    if not bot:
        return None
    try:
        return await _retry_call(bot.delete_message, chat_id, message_id, retries=retries, backoff=backoff)
    except Exception:
        logger.exception("safe_delete_message fallo para %s:%s", chat_id, message_id)
        return None



# ---------------- Channel membership helpers ----------------
async def is_member_of_channel(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Comprueba si `user_id` es miembro del canal configurado.

    Devuelve True si no hay canal configurado (permite uso), o si la comprobación
    falla por permisos, para evitar bloquear el bot accidentalmente.
    """
    canal = await config_get("canal_url")
    # fallback a config.py
    if not canal and 'CANAL_USERNAME' in globals() and CANAL_USERNAME:
        canal = CANAL_USERNAME
    if not canal:
        return True
    # normalizar: si es URL extraer username
    if canal.startswith("https://t.me/") or canal.startswith("http://t.me/"):
        canal = canal.rstrip("/").split("/")[-1]
        if canal and not canal.startswith("@"):
            canal = f"@{canal}"
    try:
        member = await context.bot.get_chat_member(canal, user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except BadRequest as e:
        # Si la comprobación falla (p. ej. bot no es miembro/admin), no bloquear por completo.
        logger.warning("No se pudo comprobar membresía del usuario %s en %s: %s", user_id, canal, e)
        return True


async def ensure_channel_member(update, context) -> bool:
    """Si el usuario no está en el canal, notifica y devuelve False.

    Se exime al OWNER_ID para evitar bloqueo accidental del dueño.
    """
    user = update.effective_user or (update.callback_query.from_user if getattr(update, 'callback_query', None) else None)
    if not user:
        return True
    uid = user.id
    if uid == OWNER_ID:
        return True

    allowed = await is_member_of_channel(uid, context)
    if allowed:
        return True

    # Notificar al usuario que debe unirse y ofrecer botón URL
    canal = await config_get("canal_url")
    if not canal and 'CANAL_USERNAME' in globals() and CANAL_USERNAME:
        canal = CANAL_USERNAME
    canal = canal or "https://t.me/tu_canal"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Unirse al canal", url=canal)]])

    # Si es callback query, responder con alerta y enviar mensaje privado con el enlace
    try:
        if getattr(update, 'callback_query', None):
            try:
                await safe_answer(update.callback_query, "Debes unirte al canal para usar el bot.", show_alert=True)
            except Exception:
                pass
            try:
                await safe_send_message(context.bot, uid, "Debes unirte al canal para usar el bot.", reply_markup=kb)
            except Exception:
                logger.exception("No se pudo enviar el enlace de canal al usuario %s", uid)
        else:
            try:
                await update.message.reply_text("Debes unirte al canal para usar el bot.", reply_markup=kb)
            except Exception:
                logger.exception("No se pudo enviar el enlace de canal en el chat de usuario %s", uid)
    except Exception:
        logger.exception("Error notificando sobre membresía al usuario %s", uid)

    return False


def require_channel_member(func):
    """Decorador para bloquear ejecución de handlers si el usuario no está en el canal."""
    async def wrapper(update, context, *args, **kwargs):
        ok = await ensure_channel_member(update, context)
        if not ok:
            return
        result = None
        try:
            result = await func(update, context, *args, **kwargs)
            return result
        except TimedOut:
            # Timeouts de red ocurren ocasionalmente (connect/read). No queremos
            # que el bot se derrumbe o que no haya manejo de la excepción.
            logger.warning("Telegram request timed out in handler %s", getattr(func, '__name__', str(func)))
            return
        except Exception:
            # Re-lanzar para que el manejador global de errores lo capture
            logger.exception("Unhandled exception in handler %s", getattr(func, '__name__', str(func)))
            raise
        finally:
            # Si el update fue un comando de texto (ej: /start), intentar eliminar
            # el mensaje del usuario para que no quede registrado en el chat.
            try:
                msg = getattr(update, 'message', None)
                if msg and isinstance(getattr(msg, 'text', None), str) and msg.text.strip().startswith('/'):
                    chat_id = getattr(update.effective_chat, 'id', None)
                    if chat_id:
                        await safe_delete_message(context.bot, chat_id, msg.message_id)
            except Exception:
                # Silenciar cualquier error al intentar borrar el mensaje
                logger.debug("No se pudo eliminar el mensaje de comando (posible falta de permisos).")
    return wrapper


def require_private_chat(func):
    """Decorador: asegura que el comando se ejecute en chat privado del bot.

    Si se ejecuta en un grupo, responde indicando que debe usarse en privado.
    """
    async def wrapper(update, context, *args, **kwargs):
        chat = getattr(update, 'effective_chat', None)
        # Algunos updates (callback_query) tienen chat asociado también
        if not chat or getattr(chat, 'type', None) != 'private':
            try:
                # preferir responder de forma adecuada según el tipo de update
                if getattr(update, 'callback_query', None):
                    await safe_answer(update.callback_query, "Por favor usa este comando en el chat privado del bot.", show_alert=True)
                elif getattr(update, 'message', None):
                    await update.message.reply_text("Por favor usa este comando en el chat privado del bot.")
            except Exception:
                logger.debug("No se pudo notificar al usuario que el comando debe usarse en privado")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --------------- Handlers ----------------
@require_channel_member
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.first_name)
    lang = await get_lang(user.id)
    text = get_text(lang, "start", name=user.first_name)
    role = await get_role(user.id)
    is_admin = (user.id == OWNER_ID) or (role == "admin")
    kb = await build_kb_main(context, lang, is_admin)
    await update.message.reply_text(text, reply_markup=kb)

# --------- Menu navigation ----------
@require_channel_member
async def menu_main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    lang = await get_lang(uid)
    role = await get_role(uid)
    is_admin = (uid == OWNER_ID) or (role == "admin")
    kb = await build_kb_main(context, lang, is_admin)
    await query.edit_message_text(get_text(lang, "menu"), reply_markup=kb)

@require_channel_member
async def menu_pedir_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    lang = await get_lang(uid)
    await query.edit_message_text(get_text(lang, "pedir_choose"), reply_markup=kb_pedir(lang))

@require_channel_member
async def pedido_tipo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    tipo = query.data.split("_", 1)[1]
    context.user_data["pending_tipo"] = tipo
    lang = await get_lang(uid)
    await query.edit_message_text(get_text(lang, "pedir_prompt", tipo=tipo))

# ---------- receive pedido (user types description) ----------
@require_channel_member
async def recibir_pedido_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    tipo = context.user_data.get("pending_tipo")
    if not tipo:
        # Perhaps it's a support flow or ignored message
        # If user has support_open, route to support flow
        if context.user_data.get("support_open"):
            # forward to admin group as support message
            admin_group = await config_get("admin_group")
            # fallback a valor por defecto en config.py si no hay configurado en DB
            if not admin_group and 'ADMIN_GROUP_ID' in globals() and ADMIN_GROUP_ID:
                admin_group = str(ADMIN_GROUP_ID)
            if not admin_group:
                await update.message.reply_text("No hay grupo de administradores configurado.")
                return
            try:
                logger.info("Forwarding support message from %s to admin_group %s", uid, admin_group)
                sent = await safe_send_message(context.bot, int(admin_group),
                                               f"📨 Mensaje de @{user.username or user.first_name} (ID <code>{uid}</code>):\n\n{update.message.text}",
                                               parse_mode="HTML",
                                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(await get_lang(int(admin_group)), 'responder'), callback_data=f"responder_support_{uid}_{update.message.message_id}")]]))
                logger.info("Forward result: %s", bool(sent))
                # record mapping: admin_msg_id -> user_id, user_msg_id
                if sent:
                    await soporte_create_entry(uid, update.message.message_id, sent.message_id)
                else:
                    await soporte_create_entry(uid, update.message.message_id, None)
                await update.message.reply_text(get_text(await get_lang(uid), "support_sent"))
            except Exception as e:
                logger.exception("Error forwarding support message: %s", e)
                await update.message.reply_text("Error al enviar el mensaje a administradores.")
        return

    descripcion = update.message.text
    ticket = await add_pedido(uid, tipo, descripcion)
    lang = await get_lang(uid)
    await update.message.reply_text(get_text(lang, "pedido_ok", ticket=ticket), parse_mode="HTML")

    # notify admin group
    admin_group = await config_get("admin_group")
    # fallback a valor por defecto en config.py si no hay configurado en DB
    if not admin_group and 'ADMIN_GROUP_ID' in globals() and ADMIN_GROUP_ID:
        admin_group = str(ADMIN_GROUP_ID)

    if admin_group:
        try:
            gid = int(admin_group)
        except Exception:
            logger.warning("El admin_group configurado no es numérico: %s", admin_group)
            gid = None

        if gid:
            try:
                text = (
                    f"📩 <b>Nuevo pedido</b>\n"
                    f"👤 {user.full_name} (@{user.username or 'sin_username'})\n"
                    f"🆔 <code>{uid}</code>\n"
                    f"📂 {tipo}\n"
                    f"📝 {descripcion}\n"
                    f"🎟 <code>{ticket}</code>\n"
                    f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                # enviar mensaje al grupo de admins con teclado de acciones
                try:
                    kb_actions = kb_admin_actions(ticket, user.id)
                except Exception:
                    kb_actions = None
                sent = await safe_send_message(context.bot, gid, text, parse_mode="HTML", reply_markup=kb_actions)
                # also create soporte mapping for possible replies (optional: reuse soporte table)
                if sent:
                    await soporte_create_entry(uid, update.message.message_id, sent.message_id)
                else:
                    await soporte_create_entry(uid, update.message.message_id, None)
            except Exception as e:
                logger.exception("Error sending order to admin group: %s", e)
                try:
                    await safe_send_message(context.bot, OWNER_ID, f"Error al notificar pedidos al grupo: {e}")
                except: pass
    else:
        # admin group not configured
        try:
            await safe_send_message(context.bot, OWNER_ID, f"⚠️ Admin group not configured. Pedido {ticket} created by {uid}.")
        except: pass

    context.user_data.pop("pending_tipo", None)
    return

# --------- Idioma ----------
@require_channel_member
async def menu_idioma_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.edit_message_text("🔤 Elige idioma / Choose language", reply_markup=kb_idioma())


@require_channel_member
async def idioma_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /idioma — envía el teclado de selección de idioma como mensaje.

    `menu_idioma_cb` está pensado para callbacks; este comando permite abrir
    el selector desde un comando de texto (mensaje).
    """
    if not update.message:
        return
    await update.message.reply_text("🔤 Elige idioma / Choose language", reply_markup=kb_idioma())

@require_channel_member
async def lang_set_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    code = query.data.split("_",1)[1]
    await set_lang(uid, code)
    await query.edit_message_text(get_text(code, "idioma_set"))

# --------- Admin panel (buttons) ----------
@require_channel_member
async def menu_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    lang = await get_lang(uid)
    await query.edit_message_text(get_text(lang, "admin_panel"), reply_markup=kb_admin_main()(lang))

# Admin submenus
@require_channel_member
async def admin_config_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.edit_message_text("🔧 Configuración del bot", reply_markup=kb_admin_config())

# Nota: la configuración de canal y admin_group se realiza directamente en config.py
# por seguridad y simplicidad. Las funciones para establecer canal/grupo desde
# el bot fueron eliminadas.

@require_channel_member
async def admin_export_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    filename = f"bot_pedidos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    await export_pedidos_csv(filename, limit=10000)
    await query.edit_message_text("✅ Preparando exportación, enviando archivo...")
    # enviar el archivo al usuario que pidió el export
    res = await safe_send_document(context.bot, uid, document=open(filename, "rb"))
    try:
        os.remove(filename)
    except Exception:
        logger.exception("No se pudo eliminar archivo temporal %s", filename)
    if res is not None:
        await safe_answer(query, "✅ Envío listo: " + filename)
    else:
        await safe_answer(query, "❌ Error al enviar el export.")

# Admin backup
@require_channel_member
async def admin_backup_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    p = await backup_db()
    await query.edit_message_text(get_text(await get_lang(uid), "backup_done", path=p))

# Admin global flow: ask text and confirm
@require_channel_member
async def admin_global_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    # Enviar un ForceReply por privado para recoger el texto con más fiabilidad
    context.user_data["admin_pending"] = {"action": "global"}
    # fallback: almacenar también en application.bot_data por admin uid para
    # evitar perder el estado si el mensaje privado llega en otro contexto.
    context.application.bot_data[f"admin_pending:{uid}"] = {"action": "global"}
    logger.info("admin_global_cb: admin_pending set for user %s", uid)
    try:
        await safe_send_message(context.bot, uid, "✍️ Escribe ahora el mensaje global que quieres enviar:", reply_markup=ForceReply(selective=True))
        await query.edit_message_text("He enviado un mensaje privado; responde ahí con el texto a enviar.")
    except Exception:
        # fallback: pedir en el mismo chat
        logger.exception("No se pudo enviar ForceReply privado para admin_global, pidiendo en el chat en su lugar.")
        await query.edit_message_text("✍️ Escribe ahora el mensaje global que quieres enviar:")
    logger.debug("admin_global_cb: finished for user %s", uid)

@require_channel_member
async def admin_cleanup_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    # Mostrar opciones de limpieza para que el admin elija el periodo
    lang = await get_lang(uid)
    await query.edit_message_text(get_text(lang, "admin_cleanup"), reply_markup=kb_admin_cleanup_options()(lang))


@require_channel_member
async def admin_cleanup_do_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        await safe_answer(query, "No tienes permisos.", show_alert=True)
        return
    # callback data formato: cleanup_days_<n>
    data = query.data
    try:
        days = int(data.split("_")[-1])
    except Exception:
        await query.edit_message_text("Parámetro inválido.")
        return
    deleted = await cleanup_old_pedidos(days)
    label = f"{days} días" if days != 1 else "24 horas"
    await query.edit_message_text(f"🧹 Limpieza completa: eliminados {deleted} pedidos de hace más de {label}.")


@require_channel_member
async def admin_take_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        return await safe_answer(query, "No tienes permisos.", show_alert=True)
    # extraer ticket
    ticket = query.data.split("_", 1)[1]
    # asignar y marcar in_progress
    try:
        await assign_pedido(ticket, uid)
        await set_pedido_estado(ticket, 'in_progress')
    except Exception as e:
        logger.exception("Error asignando pedido %s: %s", ticket, e)
        return await safe_answer(query, "Error asignando el pedido.", show_alert=True)

    # notificar al usuario
    try:
        pedido = await get_pedido_full(ticket)
        if pedido and pedido.get('user_id'):
            admin_name = (query.from_user.username and f"@{query.from_user.username}") or query.from_user.full_name
            msg = f"🟡 Tu pedido {ticket} está siendo atendido por {admin_name}."
            await safe_send_message(context.bot, int(pedido.get('user_id')), msg)
    except Exception:
        logger.exception("No se pudo notificar al usuario sobre asignación del pedido %s", ticket)

    # actualizar el mensaje en el grupo de admins para indicar quien tomó el pedido
    try:
        text = (query.message.text or "") + f"\n\n🟡 Tomado por {(query.from_user.username and '@'+query.from_user.username) or query.from_user.full_name}"
        await query.edit_message_text(text)
    except Exception:
        # si no podemos editar el texto, al menos responder
        await safe_answer(query, "Pedido asignado.")


@require_channel_member
async def admin_ready_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        return await safe_answer(query, "No tienes permisos.", show_alert=True)
    ticket = query.data.split("_", 1)[1]
    try:
        await set_pedido_estado(ticket, 'ready')
    except Exception:
        logger.exception("Error estableciendo estado ready para %s", ticket)

    # notificar y eliminar (consistente con /pedidolisto)
    try:
        pedido = await get_pedido_full(ticket)
        if pedido and pedido.get('user_id'):
            try:
                admin_name = (query.from_user.username and f"@{query.from_user.username}") or query.from_user.full_name
                notify_text = f"{admin_name}, su pedido ({ticket}) ya está listo."
                await safe_send_message(context.bot, int(pedido.get('user_id')), notify_text)
            except Exception:
                logger.exception("No se pudo notificar al usuario que su pedido %s está listo", ticket)
        # eliminar pedido tras notificar
        await delete_pedido(ticket)
    except Exception:
        logger.exception("Error procesando ready para %s", ticket)

    try:
        text = (query.message.text or "") + f"\n\n✅ Listo por {(query.from_user.username and '@'+query.from_user.username) or query.from_user.full_name}"
        await query.edit_message_text(text)
    except Exception:
        await safe_answer(query, "Pedido marcado como listo.")


@require_channel_member
async def admin_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        return await safe_answer(query, "No tienes permisos.", show_alert=True)
    ticket = query.data.split("_", 1)[1]
    try:
        await set_pedido_estado(ticket, 'cancelled')
    except Exception:
        logger.exception("Error estableciendo estado cancelled para %s", ticket)

    try:
        pedido = await get_pedido_full(ticket)
        if pedido and pedido.get('user_id'):
            try:
                admin_name = (query.from_user.username and f"@{query.from_user.username}") or query.from_user.full_name
                notify_text = f"Tu pedido {ticket} ha sido cancelado por {admin_name}."
                await safe_send_message(context.bot, int(pedido.get('user_id')), notify_text)
            except Exception:
                logger.exception("No se pudo notificar al usuario sobre cancelación del pedido %s", ticket)
        await delete_pedido(ticket)
    except Exception:
        logger.exception("Error procesando cancel para %s", ticket)

    try:
        text = (query.message.text or "") + f"\n\n❌ Cancelado por {(query.from_user.username and '@'+query.from_user.username) or query.from_user.full_name}"
        await query.edit_message_text(text)
    except Exception:
        await safe_answer(query, "Pedido cancelado.")

# confirm global callbacks
@require_channel_member
async def global_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    data = query.data
    pending = context.application.bot_data.get("pending_global")
    if not pending:
        return await query.edit_message_text("No hay mensaje pendiente.")
    if data.endswith("yes"):
        text = pending["text"]
        users = await get_all_users()
        sent = 0
        failed = 0
        msg = await query.edit_message_text(f"Enviando a {len(users)} usuarios...")
        for u in users:
            try:
                res = await safe_send_message(context.bot, u, text)
                if res is not None:
                    sent += 1
                else:
                    failed += 1
                await asyncio.sleep(0.12)
            except Exception:
                failed += 1
        await msg.edit_text(get_text(await get_lang(uid), "global_sent", sent=sent, failed=failed))
        context.application.bot_data.pop("pending_global", None)
    else:
        context.application.bot_data.pop("pending_global", None)
        await query.edit_message_text("Envío cancelado.")

# ---------- admin menu callbacks router ------------
@require_channel_member
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    # routing admin and menu callbacks
    if data == "menu_main":
        await menu_main_cb(update, context)
    elif data == "menu_pedir":
        await menu_pedir_cb(update, context)
    elif data.startswith("pedido_"):
        await pedido_tipo_cb(update, context)
    elif data == "menu_idioma":
        await menu_idioma_cb(update, context)
    elif data.startswith("lang_"):
        await lang_set_cb(update, context)
    elif data == "menu_admin":
        await menu_admin_cb(update, context)
    elif data == "admin_config":
        await admin_config_cb(update, context)
    elif data == "admin_export":
        await admin_export_cb(update, context)
    elif data == "admin_backup":
        await admin_backup_cb(update, context)
    elif data == "admin_global":
        await admin_global_cb(update, context)
    elif data == "admin_cleanup":
        await admin_cleanup_cb(update, context)
    elif data.startswith("cleanup_days_"):
        await admin_cleanup_do_cb(update, context)
    elif data.startswith("take_"):
        await admin_take_cb(update, context)
    elif data.startswith("ready_"):
        await admin_ready_cb(update, context)
    elif data.startswith("cancel_"):
        await admin_cancel_cb(update, context)
    elif data.startswith("responder_"):
        await admin_responder_cb(update, context)
    elif data.startswith("global_confirm_"):
        await global_confirm_cb(update, context)
    elif data == "open_canal":
        # open canal: fetch config canal_url
        canal = await config_get("canal_url")
        # fallback a valor en config.py si existe
        if not canal and 'CANAL_USERNAME' in globals() and CANAL_USERNAME:
            canal = CANAL_USERNAME
        canal = canal or "https://t.me/tu_canal"
        try:
            await safe_answer(update.callback_query, url=canal)  # note: not all clients will open from answer
        except BadRequest:
            # Some clients / values trigger Url_invalid. Fallback: show the link in the chat
            logger.exception("Url inválida en canal: %s", canal)
            try:
                await safe_answer(update.callback_query)
                await update.callback_query.edit_message_text(f"Canal: {canal}")
            except Exception:
                # última opción: enviar el enlace como mensaje privado al usuario
                try:
                    await safe_send_message(context.bot, update.callback_query.from_user.id, f"Canal: {canal}")
                except Exception:
                    logger.exception("No se pudo enviar canal al usuario: %s", canal)
    else:
        await safe_answer(update.callback_query)  # default

# ------------- Admin set values via plain text --------------
@require_channel_member
async def admin_plain_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    logger.info("admin_plain_text_router called: uid=%s chat=%s pending=%s", uid, getattr(update.effective_chat, 'id', None), bool(context.user_data.get('admin_pending')))
    # Not accepting canal/group config via bot anymore. Only accept admin_pending actions (global message) or support replies.

    # admin pending actions e.g., admin_global or admin replies
    pending = context.user_data.get("admin_pending")
    if pending:
        action = pending.get("action")
        logger.info("admin_plain_text_router: pending action=%s for uid=%s", action, uid)
        if action == "global":
            text = update.message.text
            context.application.bot_data["pending_global"] = {"text": text, "owner": uid}
            logger.info("admin_plain_text_router: pending_global stored owner=%s len=%s", uid, len(text) if text else 0)
            lang = await get_lang(uid)
            await update.message.reply_text(get_text(lang, "global_confirm", n=len(await get_all_users())), reply_markup=kb_confirm_global()(lang))
            # limpiar ambos lugares donde pudimos guardar el pending
            context.user_data.pop("admin_pending", None)
            context.application.bot_data.pop(f"admin_pending:{uid}", None)
            return
        elif action == "reply":
            # admin is replying to a prior 'responder' callback, target contains type and ids
            target = pending.get("target", {})
            text = update.message.text
            try:
                if target.get("type") == "ticket":
                    user_id = int(target.get("user_id"))
                    ticket = target.get("ticket")
                    # enviar respuesta al usuario sobre el pedido
                    body = f"Respuesta de administración sobre el pedido <code>{ticket}</code>:\n\n{text}"
                    await safe_send_message(context.bot, user_id, body, parse_mode="HTML")
                    await update.message.reply_text("Respuesta enviada al usuario.")
                elif target.get("type") == "support":
                    user_id = int(target.get("user_id"))
                    await safe_send_message(context.bot, user_id, f"Respuesta de administración:\n\n{text}")
                    await update.message.reply_text("Respuesta enviada al usuario.")
                else:
                    await update.message.reply_text("Target de respuesta inválido.")
            except Exception:
                logger.exception("Error enviando respuesta admin a usuario %s", target)
                await update.message.reply_text("No se pudo enviar la respuesta al usuario.")
            # limpiar ambos lugares donde pudimos guardar el pending
            context.user_data.pop("admin_pending", None)
            context.application.bot_data.pop(f"admin_pending:{uid}", None)
            return

    # support: if admin writes plain text in admin group replying to support message, handle in admin_reply_handler (separate)
    # otherwise ignore or route
    # If user has support_open true (user side), handled in recibir_pedido_msg previously.

# ---------------- Support: admin reply handler (endurecido) -------------
@require_channel_member
async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler triggers when an admin replies inside admin group
    chat = update.effective_chat
    if not chat:
        return
    # get admin_group from config
    admin_group = await config_get("admin_group")
    if not admin_group:
        # no configurado en DB: usar fallback si está disponible
        if 'ADMIN_GROUP_ID' in globals() and ADMIN_GROUP_ID:
            admin_group = str(ADMIN_GROUP_ID)
        else:
            return
    try:
        if int(admin_group) != chat.id:
            return
    except Exception:
        return

    # must be a reply
    if not update.message.reply_to_message:
        return
    replied_id = update.message.reply_to_message.message_id
    # lookup mapping: admin_msg_id -> user_id
    rec = await soporte_get_by_admin_msg(replied_id)
    user_id = None
    if rec:
        # rec: (id, user_id, user_msg_id, estado)
        user_id = rec[1]
    else:
        # try to find ID in text as fallback
        import re
        m = re.search(r"ID (\d+)", update.message.reply_to_message.text or "")
        if m:
            user_id = int(m.group(1))
        txt = update.message.reply_to_message.text or ""
        # 1) buscar dentro de etiquetas HTML <code>...</code>
        m = re.search(r"<code>(\d+)</code>", txt)
        if m:
            user_id = int(m.group(1))
        else:
            # 2) buscar patrones tipo 'ID 12345' o 'ID:12345'
            m = re.search(r"ID\s*[:#-]?\s*(\d+)", txt)
            if m:
                user_id = int(m.group(1))
            else:
                # 3) fallback: cualquier número razonablemente largo (>=5 dígitos)
                m = re.search(r"(\d{5,})", txt)
                if m:
                    user_id = int(m.group(1))
    if not user_id:
        await update.message.reply_text("No puedo encontrar a qué usuario corresponde este hilo.")
        return
    # añadir un botón responder junto al mensaje del admin si se desea (ya manejado en forward)

    # forward admin reply to user
    try:
        res = await safe_send_message(context.bot, user_id, f"🛠 Respuesta del admin:\n\n{update.message.text}")
        if res is not None:
            await update.message.reply_text("✅ Enviado al usuario.")
        else:
            await update.message.reply_text("❌ Error al enviar al usuario.")
    except Exception as e:
        await update.message.reply_text("❌ Error al enviar al usuario.")
        logger.exception("Error forwarding admin reply: %s", e)


@require_channel_member
async def admin_responder_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para iniciar el flujo de respuesta: enviamos un ForceReply privado al admin
    y guardamos en user_data el target para cuando el admin responda en privado.
    """
    query = update.callback_query
    await safe_answer(query)
    uid = query.from_user.id
    role = await get_role(uid)
    if uid != OWNER_ID and role != "admin":
        return await safe_answer(query, "No tienes permisos.", show_alert=True)
    data = query.data
    parts = data.split("_", 3)
    # formatos: responder_ticket_<ticket>_<user_id>  OR responder_support_<user_id>_<user_msg_id>
    if len(parts) < 4:
        await safe_answer(query, "Parámetros inválidos.", show_alert=True)
        return
    _, kind, a, b = parts
    if kind == "ticket":
        logger.info("admin_responder_cb: responder ticket=%s user_id=%s (admin=%s)", a, b, uid)
        ticket = a
        user_id = b
        pending = {"action": "reply", "target": {"type": "ticket", "ticket": ticket, "user_id": user_id}}
        context.user_data["admin_pending"] = pending
        # fallback storage keyed by admin id
        context.application.bot_data[f"admin_pending:{uid}"] = pending
        # pedir respuesta en privado con ForceReply
        try:
            await safe_send_message(context.bot, uid, "✍️ Escribe la respuesta que se enviará al usuario (responde a este mensaje):", reply_markup=ForceReply(selective=True))
            await query.edit_message_text((query.message.text or "") + "\n\n💬 Petición de respuesta enviada al admin en privado.")
        except Exception:
            logger.exception("No se pudo iniciar flujo de respuesta privada para admin %s", uid)
            await safe_answer(query, "No pude enviar el mensaje privado. Intenta escribir la respuesta en este chat.")
    elif kind == "support":
        logger.info("admin_responder_cb: responder support user_id=%s user_msg_id=%s (admin=%s)", a, b, uid)
        user_id = a
        user_msg_id = b
        pending = {"action": "reply", "target": {"type": "support", "user_id": user_id, "user_msg_id": user_msg_id}}
        context.user_data["admin_pending"] = pending
        context.application.bot_data[f"admin_pending:{uid}"] = pending
        try:
            await safe_send_message(context.bot, uid, "✍️ Escribe la respuesta que se enviará al usuario (responde a este mensaje):", reply_markup=ForceReply(selective=True))
            await query.edit_message_text((query.message.text or "") + "\n\n💬 Petición de respuesta enviada al admin en privado.")
        except Exception:
            logger.exception("No se pudo iniciar flujo de respuesta privada para admin %s (support)", uid)
            await safe_answer(query, "No pude enviar el mensaje privado. Intenta escribir la respuesta en este chat.")

# ---------------- Close support by admin ----------------
@require_channel_member
async def admin_close_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # either button or command to close conversation: expects an argument user_id
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text("No tienes permisos.")
    args = context.args
    if not args:
        return await update.message.reply_text("Uso: /cerrar <user_id>")
    try:
        uid = int(args[0])
        await soporte_close_by_user(uid)
        await update.message.reply_text(get_text(await get_lang(user.id), "support_closed"))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ---------------- Misc admin commands ----------------
@require_private_chat
@require_channel_member
async def ver_pedidos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text(get_text(await get_lang(user.id), "no_perms"))
    rows = await get_pedidos(100)
    if not rows:
        return await update.message.reply_text("📭 No hay pedidos.")
    text = get_text(await get_lang(user.id), "verpedidos_title") + "\n\n"
    for r in rows:
        text += f"🎟 <b>{r[0]}</b> — {r[2]} — {r[3][:120]}...\n"
    await update.message.reply_text(text, parse_mode="HTML")


@require_private_chat
@require_channel_member
async def stadistics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas básicas: usuarios totales y admins."""
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text(get_text(await get_lang(user.id), "no_perms"))

    total = await count_users()
    admins = await count_admins()
    owners = 1 if 'OWNER_ID' in globals() and OWNER_ID else 0

    # contar pedidos por estado
    try:
        estados = await count_pedidos_by_estado()
    except Exception:
        logger.exception("Error obteniendo conteos por estado")
        estados = {}

    lines = [f"📊 Estadísticas:", f"- Usuarios registrados: {total}", f"- Administradores: {admins}", f"- Dueños: {owners}", "- Pedidos por estado:"]
    # presentar estados comunes en orden
    for k in ("pending", "in_progress", "ready", "cancelled", "unknown"):
        if k in estados:
            lines.append(f"  - {k}: {estados[k]}")
    # cualquier estado adicional
    for k, v in estados.items():
        if k not in ("pending", "in_progress", "ready", "cancelled", "unknown"):
            lines.append(f"  - {k}: {v}")

    await update.message.reply_text("\n".join(lines))

@require_private_chat
@require_channel_member
async def ver_pedido_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Uso: /verpedido <TICKET>")
    ticket = context.args[0].strip()
    row = await get_pedido(ticket)
    if not row:
        return await update.message.reply_text("No encontrado.")
    text = f"🎟 <b>{row[0]}</b>\n👤 {row[1]}\n📂 {row[2]}\n📝 {row[3]}\n🕒 {row[4]}"
    await update.message.reply_text(text, parse_mode="HTML")

@require_private_chat
@require_channel_member
async def buscopedido_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Uso: /buscopedido <texto>")
    term = " ".join(context.args)
    rows = await search_pedidos(term, limit=50)
    if not rows:
        return await update.message.reply_text("No hay resultados.")
    text = "🔎 Resultados:\n\n"
    for r in rows:
        text += f"🎟 <b>{r[0]}</b> — {r[2]} — {r[3][:120]}...\n"
    await update.message.reply_text(text, parse_mode="HTML")

@require_private_chat
@require_channel_member
async def eliminarpedido_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text(get_text(await get_lang(user.id), "no_perms"))
    if not context.args:
        return await update.message.reply_text("Uso: /eliminarpedido <TICKET>")
    ticket = context.args[0].strip()
    # intentar obtener info del pedido para notificar al usuario
    row = await get_pedido(ticket)
    if not row:
        return await update.message.reply_text(get_text(await get_lang(user.id), "eliminar_no", ticket=ticket), parse_mode="HTML")
    # row: (ticket, user_id, tipo, descripcion, fecha)
    _, uid, tipo, descripcion, fecha = row
    # notificar al usuario que su pedido fue eliminado
    try:
        chat = await context.bot.get_chat(uid)
        name = getattr(chat, 'username', None) or getattr(chat, 'first_name', None) or str(uid)
        notify_text = f"@{name}, tu pedido {ticket} de {tipo} fue eliminado por un administrador."
        await safe_send_message(context.bot, uid, notify_text)
    except Exception:
        logger.exception("No se pudo notificar al usuario %s sobre eliminación del pedido %s", uid, ticket)

    await delete_pedido(ticket)
    await update.message.reply_text(get_text(await get_lang(user.id), "eliminar_ok", ticket=ticket), parse_mode="HTML")

@require_private_chat
@require_channel_member
async def agregaradmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        return await update.message.reply_text("Solo el dueño puede agregar admins.")
    if not context.args:
        return await update.message.reply_text("Uso: /agregaradmin <user_id>")
    try:
        uid = int(context.args[0])
        await set_role(uid, "admin")
        await update.message.reply_text(f"✅ Usuario {uid} ahora es admin.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@require_private_chat
@require_channel_member
async def eliminaradmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        return await update.message.reply_text("Solo el dueño puede eliminar admins.")
    if not context.args:
        return await update.message.reply_text("Uso: /eliminaradmin <user_id>")
    try:
        uid = int(context.args[0])
        await set_role(uid, "user")
        await update.message.reply_text(f"✅ Usuario {uid} ya no es admin.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

@require_channel_member
async def mispedidos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = await get_pedidos(1000)
    user_rows = [r for r in rows if r[1] == user.id]
    if not user_rows:
        return await update.message.reply_text("No tienes pedidos.")
    text = get_text(await get_lang(user.id), "mispedidos_title") + "\n\n"
    for r in user_rows:
        text += f"🎟 <b>{r[0]}</b> — {r[2]} — {r[3][:120]}...\n"
    await update.message.reply_text(text, parse_mode="HTML")


@require_private_chat
@require_channel_member
async def pedidolisto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marcar un pedido como listo por ticket y notificar al usuario.

    Uso: /pedidolisto <TICKET>
    Solo OWNER o admins.
    """
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text(get_text(await get_lang(user.id), "no_perms"))
    if not context.args:
        return await update.message.reply_text("Uso: /pedidolisto <TICKET>")
    ticket = context.args[0].strip()
    row = await get_pedido(ticket)
    if not row:
        return await update.message.reply_text("Ticket no encontrado.")
    # row: (ticket, user_id, tipo, descripcion, fecha)
    _, uid, tipo, descripcion, fecha = row

    # intentar obtener username para el mention
    try:
        chat = await context.bot.get_chat(uid)
        username = getattr(chat, 'username', None)
    except Exception:
        username = None

    mention = f"@{username}" if username else str(uid)
    notify_text = f"{mention}, su pedido de {tipo} ('{descripcion[:80]}') ya está listo."

    res = await safe_send_message(context.bot, uid, notify_text)
    # eliminar pedido tras notificar
    await delete_pedido(ticket)

    await update.message.reply_text(f"✅ Pedido {ticket} marcado como listo. Notificado al usuario: {'OK' if res else 'FALLÓ'}.")

@require_private_chat
@require_channel_member
async def exportar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = await get_role(user.id)
    if user.id != OWNER_ID and role != "admin":
        return await update.message.reply_text("No tienes permiso.")
    filename = f"bot_pedidos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    await export_pedidos_csv(filename, 10000)
    res = await safe_send_document(context.bot, user.id, document=open(filename, 'rb'))
    try:
        os.remove(filename)
    except Exception:
        logger.exception("No se pudo eliminar archivo temporal %s", filename)
    if res is not None:
        await update.message.reply_text(f"✅ Envío listo: {filename}")
    else:
        await update.message.reply_text("❌ Error al enviar el export.")

@require_private_chat
@require_channel_member
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        return await update.message.reply_text("Solo el dueño puede crear backup.")
    p = await backup_db()
    await update.message.reply_text(get_text(await get_lang(user.id), "backup_done", path=p))

# ----------------- Support open command (user) ----------------
@require_channel_member
async def chatadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data["support_open"] = True
    await update.message.reply_text("✉️ Escribe tu mensaje y lo enviaremos a los administradores. Usa /cerrar para cerrar el chat.")

@require_channel_member
async def cerrar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await soporte_close_by_user(user.id)
    context.user_data.pop("support_open", None)
    await update.message.reply_text(get_text(await get_lang(user.id), "support_closed"))



# --- Tarea periódica ---
async def periodic_cleanup_task(application):
    while True:
        try:
            await cleanup_old_pedidos(30)
            await asyncio.sleep(86400)  # 24h
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error en tarea periódica")
            await asyncio.sleep(60)

# --- Función de inicio que se ejecuta cuando el bot está listo ---
async def on_startup(app):
    """Función que corre tareas después de que la app está inicializada."""
    try:
        app.create_task(periodic_cleanup_task(app))
        logger.info("🧹 Tarea de limpieza periódica iniciada correctamente.")
    except Exception as e:
        logger.error(f"⚠️ Error iniciando tarea periódica: {e}")


async def application_error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador global de errores para que las excepciones no queden sin tratar.

    Envía un log detallado y notifica al OWNER_ID (si está configurado).
    """
    # Context.error debería contener la excepción en PTB v20+
    try:
        logger.exception("Unhandled exception while processing update: %s", context.error)
    except Exception:
        logger.exception("Unhandled exception in error handler")

    # Intentar notificar al OWNER_ID con un breve mensaje (no bloquear si falla)
    try:
        if 'OWNER_ID' in globals() and OWNER_ID:
            # Evitar llamadas largas que puedan fallar también; intentamos una notificación simple
            await safe_send_message(context.bot, OWNER_ID, f"⚠️ Error en bot: {getattr(context, 'error', 'unknown')}")
    except Exception:
        logger.exception("No se pudo notificar al OWNER_ID sobre la excepción")

def main():
    # Inicializar DB en un pequeño loop y luego ejecutar la app de forma síncrona
    import asyncio as _asyncio
    _asyncio.run(init_db())
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # Registrar manejador global de errores para evitar "No error handlers are registered"
    app.add_error_handler(application_error_handler)

    logger.info("Bot iniciado.")

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    # Callback queries -> router (single handler sufficient)
    app.add_handler(CallbackQueryHandler(callback_router, pattern=".*"))
    app.add_handler(CommandHandler("verpedidos", ver_pedidos_cmd))
    app.add_handler(CommandHandler("verpedido", ver_pedido_cmd))
    app.add_handler(CommandHandler("buscopedido", buscopedido_cmd))
    app.add_handler(CommandHandler("eliminarpedido", eliminarpedido_cmd))
    app.add_handler(CommandHandler("pedidolisto", pedidolisto_cmd))
    app.add_handler(CommandHandler("stadistics", stadistics_cmd))
    app.add_handler(CommandHandler("agregaradmin", agregaradmin_cmd))
    app.add_handler(CommandHandler("eliminaradmin", eliminaradmin_cmd))
    app.add_handler(CommandHandler("mispedidos", mispedidos_cmd))
    app.add_handler(CommandHandler("exportar", exportar_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("chatadmin", chatadmin_cmd))
    app.add_handler(CommandHandler("cerrar", cerrar_cmd))
    # comando para mostrar selector de idioma (usa mensaje en vez de callback)
    app.add_handler(CommandHandler("idioma", idioma_cmd))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_pedido_msg))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plain_text_router))
    app.add_handler(MessageHandler(filters.REPLY & filters.ChatType.GROUPS & filters.TEXT, admin_reply_handler))


    try:
        # Asegurar que hay un event loop en el hilo principal para que
        # Application.run_polling() pueda obtenerlo.
        import asyncio as _asyncio_internal
        loop = _asyncio_internal.new_event_loop()
        _asyncio_internal.set_event_loop(loop)

        # Antes de usar getUpdates (polling), intentamos eliminar cualquier
        # webhook previo que pudiera estar configurado. Si existe un webhook
        # activo, las llamadas a getUpdates recibirán 409 Conflict.
        # Hacemos varios reintentos con backoff para cubrir entornos con
        # conectividad intermitente (ej: DNS temporal, redes sin salida).
        delete_ok = False
        for attempt in range(3):
            try:
                resp = httpx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=5.0)
                if resp.status_code == 200:
                    logger.info("Webhook eliminado o no existía (deleteWebhook ok).")
                    delete_ok = True
                    break
                else:
                    logger.warning("deleteWebhook returned %s: %s", resp.status_code, resp.text)
                    # no break: intentar de nuevo por si fue un fallo transitorio
            except (httpx.RequestError, OSError) as e:
                logger.warning("Intento %s: No se pudo ejecutar deleteWebhook: %s", attempt + 1, e)
            # exponencial backoff pequeño
            time.sleep(1 + attempt * 2)
        if not delete_ok:
            logger.warning("No se pudo eliminar webhook tras varios intentos; continuando con polling.")

        # Ejecutar polling con reintentos en caso de errores de tiempo de espera
        max_restarts = 5
        restarts = 0
        while True:
            try:
                # run_polling gestiona el ciclo de vida internamente; llamamos desde contexto síncrono
                app.run_polling()
                break
            except KeyboardInterrupt:
                logger.info("Bot detenido por teclado.")
                raise
            except (TimedOut, httpx.TimeoutException, httpx.RequestError, OSError) as e:
                restarts += 1
                logger.warning("Polling interrumpido por timeout/IO: %s. Reintentando (%s/%s)...", e, restarts, max_restarts)
                if restarts >= max_restarts:
                    logger.exception("Polling falló repetidamente por timeouts; abortando.")
                    break
                time.sleep(5)
                continue
            except Exception as e:
                logger.exception(f"Error crítico en el polling: {e}")
                break
    except KeyboardInterrupt:
        logger.info("Bot detenido por teclado.")
    except Exception as e:
        logger.exception(f"Error crítico en el polling: {e}")


if __name__ == "__main__":
    try:
        # Ejecutar la función main de forma síncrona (main ya gestiona el loop)
        main()
    except KeyboardInterrupt:
        logger.info("Bot detenido por teclado.")
