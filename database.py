# database.py
import aiosqlite
import os
import csv
from datetime import datetime, timedelta

DB_PATH = "bot_pedidos.db"

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # usuarios: idioma, rol (owner/admin/user), nombre
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id INTEGER PRIMARY KEY,
                nombre TEXT,
                idioma TEXT DEFAULT 'es',
                rol TEXT DEFAULT 'user',
                fecha_registro TEXT
            )
        """)
        # pedidos
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                ticket TEXT PRIMARY KEY,
                user_id INTEGER,
                tipo TEXT,
                descripcion TEXT,
                fecha TEXT
            )
        """)
        # Ensure new columns for estado/assignments exist (migrations)
        async with db.execute("PRAGMA table_info(pedidos)") as cur:
            cols = await cur.fetchall()
            col_names = [c[1] for c in cols]
        # Add estado
        if 'estado' not in col_names:
            try:
                await db.execute("ALTER TABLE pedidos ADD COLUMN estado TEXT DEFAULT 'pending'")
            except Exception:
                pass
        # Add assigned_admin_id
        if 'assigned_admin_id' not in col_names:
            try:
                await db.execute("ALTER TABLE pedidos ADD COLUMN assigned_admin_id INTEGER DEFAULT NULL")
            except Exception:
                pass
        # Add timestamps
        if 'assigned_at' not in col_names:
            try:
                await db.execute("ALTER TABLE pedidos ADD COLUMN assigned_at TEXT DEFAULT NULL")
            except Exception:
                pass
        if 'ready_at' not in col_names:
            try:
                await db.execute("ALTER TABLE pedidos ADD COLUMN ready_at TEXT DEFAULT NULL")
            except Exception:
                pass
        # soporte: mantiene mapping admin_msg_id -> user_id y user_msg_id
        await db.execute("""
            CREATE TABLE IF NOT EXISTS soporte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_msg_id INTEGER,
                user_msg_id INTEGER,
                estado TEXT DEFAULT 'open',
                fecha TEXT
            )
        """)
        # config: guarda keys como 'admin_group', 'canal_url', etc.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()

# ---------------- Users ----------------
async def add_user(user_id: int, nombre: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO usuarios (user_id, nombre, fecha_registro) VALUES (?, ?, ?)",
            (user_id, nombre, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def set_lang(user_id: int, idioma: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE usuarios SET idioma=? WHERE user_id=?", (idioma, user_id))
        await db.commit()

async def get_lang(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT idioma FROM usuarios WHERE user_id=?", (user_id,)) as cur:
            r = await cur.fetchone()
            return r[0] if r else "es"

async def set_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # if user exists update, else insert minimal row with role
        await db.execute("""
            INSERT INTO usuarios (user_id, nombre, idioma, rol, fecha_registro)
            VALUES (?, COALESCE((SELECT nombre FROM usuarios WHERE user_id=?), ''), COALESCE((SELECT idioma FROM usuarios WHERE user_id=?), 'es'), ?, COALESCE((SELECT fecha_registro FROM usuarios WHERE user_id=?), ?))
            ON CONFLICT(user_id) DO UPDATE SET rol=excluded.rol
        """, (user_id, user_id, user_id, role, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()

async def get_role(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rol FROM usuarios WHERE user_id=?", (user_id,)) as cur:
            r = await cur.fetchone()
            return r[0] if r else "user"

async def get_all_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM usuarios") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM usuarios") as cur:
            r = await cur.fetchone()
            return r[0] if r else 0

async def count_admins() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin'") as cur:
            r = await cur.fetchone()
            return r[0] if r else 0

# ---------------- Pedidos ----------------
def _ticket_now() -> str:
    return "TCK" + datetime.now().strftime("%Y%m%d%H%M%S%f")[-14:]

async def add_pedido(user_id: int, tipo: str, descripcion: str) -> str:
    ticket = _ticket_now()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pedidos (ticket, user_id, tipo, descripcion, fecha, estado) VALUES (?, ?, ?, ?, ?, 'pending')",
            (ticket, user_id, tipo, descripcion, fecha)
        )
        await db.commit()
    return ticket

async def get_pedidos(limit: int = 100) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT ticket, user_id, tipo, descripcion, fecha FROM pedidos ORDER BY fecha DESC LIMIT ?", (limit,)) as cur:
            return await cur.fetchall()

async def get_pedido(ticket: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT ticket, user_id, tipo, descripcion, fecha FROM pedidos WHERE ticket=?", (ticket,)) as cur:
            return await cur.fetchone()


async def get_pedido_full(ticket: str):
    """Devuelve todos los campos disponibles del pedido (si existen columnas nuevas)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Seleccionamos todas las columnas existentes en la tabla
        async with db.execute("PRAGMA table_info(pedidos)") as cur:
            cols = await cur.fetchall()
            col_names = [c[1] for c in cols]
        cols_sql = ", ".join(col_names)
        query = f"SELECT {cols_sql} FROM pedidos WHERE ticket=?"
        async with db.execute(query, (ticket,)) as cur:
            row = await cur.fetchone()
            # devolver como dict para mayor comodidad
            if not row:
                return None
            return dict(zip(col_names, row))

async def search_pedidos(term: str, limit: int = 100):
    like = f"%{term}%"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ticket, user_id, tipo, descripcion, fecha FROM pedidos WHERE descripcion LIKE ? OR tipo LIKE ? ORDER BY fecha DESC LIMIT ?",
            (like, like, limit)
        ) as cur:
            return await cur.fetchall()

async def delete_pedido(ticket: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pedidos WHERE ticket=?", (ticket,))
        await db.commit()
    return True


async def set_pedido_estado(ticket: str, estado: str):
    """Establece el estado de un pedido y registra timestamp si corresponde."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE pedidos SET estado=? WHERE ticket=?", (estado, ticket))
        if estado == 'in_progress':
            # registrar assigned_at si existe la columna
            try:
                await db.execute("UPDATE pedidos SET assigned_at=? WHERE ticket=?", (now, ticket))
            except Exception:
                pass
        if estado == 'ready':
            try:
                await db.execute("UPDATE pedidos SET ready_at=? WHERE ticket=?", (now, ticket))
            except Exception:
                pass
        await db.commit()


async def assign_pedido(ticket: str, admin_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE pedidos SET assigned_admin_id=? WHERE ticket=?", (admin_id, ticket))
        try:
            await db.execute("UPDATE pedidos SET assigned_at=? WHERE ticket=?", (now, ticket))
        except Exception:
            pass
        await db.commit()


async def count_pedidos_by_estado() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT estado, COUNT(*) FROM pedidos GROUP BY estado") as cur:
            rows = await cur.fetchall()
            return {r[0] or 'unknown': r[1] for r in rows}

# ---------------- Soporte (chat admin) ----------------
async def soporte_create_entry(user_id: int, user_msg_id: int, admin_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO soporte (user_id, admin_msg_id, user_msg_id, estado, fecha) VALUES (?, ?, ?, 'open', ?)",
            (user_id, admin_msg_id, user_msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def soporte_get_by_admin_msg(admin_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, user_id, user_msg_id, estado FROM soporte WHERE admin_msg_id=?", (admin_msg_id,)) as cur:
            return await cur.fetchone()

async def soporte_get_open_by_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, admin_msg_id, user_msg_id, estado FROM soporte WHERE user_id=? AND estado='open' ORDER BY fecha DESC LIMIT 1", (user_id,)) as cur:
            return await cur.fetchone()

async def soporte_close_by_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE soporte SET estado='closed' WHERE user_id=? AND estado='open'", (user_id,))
        await db.commit()

# ---------------- Config ----------------
async def config_set(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        await db.commit()

async def config_get(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM config WHERE key=?", (key,)) as cur:
            r = await cur.fetchone()
            return r[0] if r else None

# ---------------- Export/Backup/Cleanup ----------------
async def export_pedidos_csv(path: str, limit: int = 10000) -> str:
    rows = await get_pedidos(limit)
    with open(path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticket", "user_id", "tipo", "descripcion", "fecha"])
        for r in rows:
            writer.writerow(r)
    return path

async def backup_db(backup_path: str = None) -> str:
    backup_path = backup_path or f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    # ensure DB committed
    async with aiosqlite.connect(DB_PATH) as db:
        await db.commit()
    import shutil
    shutil.copyfile(DB_PATH, backup_path)
    return backup_path

async def cleanup_old_pedidos(days: int = 30):
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        # contar cuántos registros serán eliminados
        async with db.execute("SELECT COUNT(*) FROM pedidos WHERE fecha < ?", (cutoff_str,)) as cur:
            r = await cur.fetchone()
            to_delete = r[0] if r else 0
        await db.execute("DELETE FROM pedidos WHERE fecha < ?", (cutoff_str,))
        await db.commit()
    return to_delete