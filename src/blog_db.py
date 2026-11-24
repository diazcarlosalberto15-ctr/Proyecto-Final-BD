"""blog_db.py — CAPA DE DATOS del blog (todo lo que habla con Neo4j).

¿Para qué sirve este archivo?
    Aquí vive TODA la lógica de base de datos: conectarse a Neo4j, validar
    contraseñas y ejecutar las consultas Cypher del CRUD. La interfaz gráfica
    (main.py) nunca escribe Cypher: solo llama a las funciones de este archivo.

Contenido, en este orden:
    1. CONFIGURACIÓN  -> lee los datos de conexión desde el archivo .env
    2. CONEXIÓN       -> clase que abre la conexión y ejecuta consultas
    3. CONTRASEÑAS    -> funciones para guardar/verificar contraseñas de forma segura
    4. UTILIDADES     -> funciones auxiliares (slug de url, generador de ids)
    5. SERVICIOS      -> el CRUD: usuarios, artículos, categorías/etiquetas, comentarios

Modelo de grafo (el definido por el equipo en cypher/01..04):
    (:User {email, name})            + password_hash, salt, rol  <- agregadas por esta app para el login
    (:Article {id, title, date, text})
    (:Category {name, url})          (:Tag {name, url})
    (:Comment {id, name, url})       <- OJO: 'name' guarda el TEXTO del comentario

    (:User)-[:PUBLICO]->(:Article)                       un usuario publica un artículo
    (:Article)-[:PERTENECE_A]->(:Category)               un artículo puede tener VARIAS categorías
    (:Article)-[:TIENE_ETIQUETA]->(:Tag)                 y varias etiquetas
    (:Article)-[:TIENE_COMENTARIO]->(:Comment)           un artículo tiene comentarios
    (:User)-[:ESCRIBIO]->(:Comment)                      y cada comentario lo escribió un usuario

Seguridad: todas las consultas usan PARÁMETROS ($nombre). Nunca se pega texto del
usuario directamente dentro del Cypher, así se evita la "inyección de Cypher"
(el equivalente a la inyección SQL).
"""
# Esta línea hace que las anotaciones de tipo (list[dict], etc.) se lean "perezosamente".
# Es necesaria porque varias clases tienen un método llamado list() que, sin esto,
# taparía al tipo list[...] y daría error.
from __future__ import annotations

import hashlib                      # algoritmo de hash para las contraseñas (PBKDF2)
import hmac                         # comparación segura de hashes
import os                           # leer variables de entorno
import re                           # expresiones regulares (validar correo, extraer números de ids)
import secrets                      # generador de números aleatorios seguro (para la "sal")
import unicodedata                  # quitar acentos al crear los slugs
from dataclasses import dataclass   # forma corta de crear una clase que solo guarda datos
from datetime import date           # fecha de hoy para los artículos nuevos
from pathlib import Path            # manejo de rutas de archivos

from neo4j import GraphDatabase     # el driver oficial de Neo4j para Python

try:
    from dotenv import load_dotenv  # librería que lee el archivo .env
except ImportError:                 # si no está instalada, no pasa nada: se usan las variables del sistema
    load_dotenv = None

# =========================================================================== #
# 1. CONFIGURACIÓN
# =========================================================================== #
# __file__ es este archivo (src/blog_db.py). parents[1] sube un nivel -> la raíz del repo.
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"        # el .env debe estar en la raíz del proyecto


@dataclass(frozen=True)             # frozen=True: una vez creado, no se puede modificar
class Settings:
    """Los 4 datos necesarios para conectarse a Neo4j."""
    uri: str        # dirección del servidor, ej. neo4j://127.0.0.1:7687
    user: str       # usuario de Neo4j (normalmente 'neo4j')
    password: str   # contraseña de Neo4j (la de tu instancia, NO la del blog)
    database: str   # nombre de la base de datos (normalmente 'neo4j')


def load_settings() -> Settings:
    """Lee la configuración del archivo .env (o de las variables de entorno del sistema).

    Así las contraseñas nunca quedan escritas en el código.
    """
    if load_dotenv is not None:
        load_dotenv(ENV_PATH)       # carga las variables del .env al entorno
    return Settings(
        # os.getenv("NOMBRE", "valor_por_defecto") busca la variable; si no existe usa el valor por defecto
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        # Se aceptan ambos nombres: NEO4J_USER y NEO4J_USERNAME (este último es el que usa AuraDB)
        user=os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j",
        password=os.getenv("NEO4J_PASSWORD", ""),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )


# =========================================================================== #
# 2. CONEXIÓN A NEO4J
# =========================================================================== #
# Estas son las mismas restricciones e índices de cypher/01_schema_constraints.cypher.
# Gracias a "IF NOT EXISTS" se pueden ejecutar muchas veces sin error: si ya existen, no hace nada.
SCHEMA_STATEMENTS = [
    # UNIQUE: no pueden existir dos nodos con el mismo valor en esa propiedad
    "CREATE CONSTRAINT constraint_user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE",
    "CREATE CONSTRAINT constraint_article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_tag_name IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT constraint_category_name IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE",
    # Índices: hacen más rápidas las búsquedas y ordenamientos por título y fecha
    "CREATE INDEX index_article_title IF NOT EXISTS FOR (a:Article) ON (a.title)",
    "CREATE INDEX index_article_date IF NOT EXISTS FOR (a:Article) ON (a.date)",
]


class Neo4jConnection:
    """Envuelve el driver de Neo4j con métodos simples: read() para leer y write() para escribir.

    Es la ÚNICA clase que usa el driver directamente; el resto del programa
    solo le pasa consultas Cypher.
    """

    def __init__(self, settings: Settings):
        self.settings = settings    # guarda los datos de conexión
        self._driver = None         # todavía no hay conexión abierta

    def connect(self) -> None:
        """Abre la conexión y comprueba que funciona (servidor encendido y credenciales correctas)."""
        self._driver = GraphDatabase.driver(
            self.settings.uri, auth=(self.settings.user, self.settings.password))
        # Si el servidor está apagado o la contraseña es incorrecta, esta línea lanza un error
        self._driver.verify_connectivity()

    def close(self) -> None:
        """Cierra la conexión (se llama al salir de la aplicación)."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def ensure_schema(self) -> None:
        """Crea las restricciones e índices si todavía no existen."""
        with self._driver.session(database=self.settings.database) as session:
            for statement in SCHEMA_STATEMENTS:
                session.run(statement).consume()    # consume() espera a que termine

    def read(self, query: str, params: dict | None = None) -> list[dict]:
        """Ejecuta una consulta de SOLO LECTURA y devuelve una lista de diccionarios.

        Ejemplo de resultado: [{"id": "art-001", "title": "..."}, {...}]
        """
        # Una "sesión" es una conversación con la base de datos
        with self._driver.session(database=self.settings.database) as session:
            # execute_read corre la consulta dentro de una transacción de lectura.
            # .data() convierte el resultado en una lista de diccionarios de Python.
            return session.execute_read(lambda tx: tx.run(query, params or {}).data())

    def write(self, query: str, params: dict | None = None) -> list[dict]:
        """Ejecuta UNA sentencia que modifica datos (crear, actualizar, borrar)."""
        return self.write_many([(query, params or {})])[0]

    def write_many(self, statements: list[tuple[str, dict]]) -> list[list[dict]]:
        """Ejecuta VARIAS sentencias en una sola transacción: o se hacen todas o no se hace ninguna.

        Es importante para que un artículo no quede a medias (por ejemplo, creado
        pero sin sus categorías) si algo falla a la mitad.
        """
        def work(tx):
            return [tx.run(query, params).data() for query, params in statements]

        with self._driver.session(database=self.settings.database) as session:
            return session.execute_write(work)


# =========================================================================== #
# 3. CONTRASEÑAS
# =========================================================================== #
# NUNCA se guarda la contraseña real. Se guarda un "hash": el resultado de pasar la
# contraseña por una función matemática de un solo sentido (no se puede revertir).
# Además se le agrega una "sal" aleatoria distinta por usuario, para que dos usuarios
# con la misma contraseña tengan hashes distintos.
ITERATIONS = 200_000    # cuántas veces se repite el cálculo (más vueltas = más difícil de atacar)


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Convierte una contraseña en (hash, sal), ambos como texto hexadecimal.

    Si no se entrega una sal, genera una nueva (se usa al crear/cambiar contraseña).
    Si se entrega, la reutiliza (se usa al verificar un login).
    """
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Revisa si una contraseña escrita coincide con el hash guardado.

    Calcula el hash de lo que escribió el usuario con la MISMA sal y lo compara.
    compare_digest compara en tiempo constante para evitar ataques por tiempo.
    """
    calculado, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(calculado, hash_hex)


# =========================================================================== #
# 4. UTILIDADES
# =========================================================================== #
ROLES = ("admin", "autor")      # los dos roles permitidos


def slugify(texto: str) -> str:
    """Convierte un nombre en un fragmento de URL: 'Bases de Datos' -> 'bases-de-datos'.

    Se usa para llenar la propiedad url de las categorías y etiquetas, igual que en el seed.
    """
    # NFKD separa las letras de sus acentos; encode("ascii","ignore") descarta los acentos
    ascii_ = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    # Reemplaza todo lo que no sea letra o número por un guion, y quita guiones de los extremos
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-") or "sin-nombre"


def siguiente_id(db: Neo4jConnection, label: str, prefijo: str, inicio: int) -> str:
    """Genera el siguiente id con el mismo formato del seed: 'art-003', 'cmt-104'...

    Busca todos los ids existentes, toma el número más alto y le suma 1.
    ``label`` y ``prefijo`` son constantes internas (no vienen del usuario).
    """
    filas = db.read(f"MATCH (n:{label}) RETURN n.id AS id")
    # De cada id como 'art-002' extrae el número 2 (solo si coincide con el formato esperado)
    numeros = [int(m.group(1)) for f in filas
               if (m := re.fullmatch(rf"{prefijo}-(\d+)", f["id"] or ""))]
    # Si no hay ninguno, empieza desde 'inicio'. :03d rellena con ceros: 3 -> '003'
    return f"{prefijo}-{max(numeros, default=inicio - 1) + 1:03d}"


# =========================================================================== #
# 5. SERVICIOS (el CRUD)
# =========================================================================== #
class UserService:
    """Todo lo relacionado con usuarios (nodos :User). El correo es la llave y el 'usuario' del login."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    def _get(self, email: str) -> dict | None:
        """Busca un usuario por correo. Devuelve sus datos, o None si no existe."""
        rows = self.db.read(
            # MATCH busca el nodo; RETURN elige qué propiedades devolver.
            # coalesce(u.rol,'autor') = "usa u.rol, y si no tiene, usa 'autor'" (los del seed no tienen rol)
            """MATCH (u:User {email: $email})
               RETURN u.email AS email, u.name AS name, coalesce(u.rol, 'autor') AS rol,
                      u.password_hash AS password_hash, u.salt AS salt""",
            {"email": email})
        return rows[0] if rows else None

    def _count_admins(self) -> int:
        """Cuenta cuántos administradores con contraseña existen (para no borrar al último)."""
        return self.db.read(
            "MATCH (u:User {rol: 'admin'}) WHERE u.password_hash IS NOT NULL RETURN count(u) AS n")[0]["n"]

    def count_with_password(self) -> int:
        """Cuenta los usuarios que ya pueden iniciar sesión. Si es 0 -> es la primera configuración."""
        return self.db.read(
            "MATCH (u:User) WHERE u.password_hash IS NOT NULL RETURN count(u) AS n")[0]["n"]

    @staticmethod
    def _validar(email=None, password=None, rol=None):
        """Revisa que los datos tengan sentido. Si algo está mal lanza ValueError con un mensaje
        en español que la interfaz muestra en una ventana. Solo valida lo que se le pase."""
        if email is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Escribe un correo válido (ej. carlos@example.com).")
        if password is not None and len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        if rol is not None and rol not in ROLES:
            raise ValueError(f"Rol inválido. Usa: {', '.join(ROLES)}.")

    # -- LOGIN ---------------------------------------------------------------
    def authenticate(self, email: str, password: str) -> dict | None:
        """Comprueba correo y contraseña. Devuelve {email, name, rol} si son correctos; si no, None."""
        row = self._get(email.strip().lower())
        if not row or not row["password_hash"]:
            return None          # el usuario no existe, o existe pero aún no tiene contraseña
        if not verify_password(password, row["password_hash"], row["salt"]):
            return None          # contraseña incorrecta
        return {"email": row["email"], "name": row["name"], "rol": row["rol"]}

    def setup_first_admin(self, email: str, name: str, password: str) -> None:
        """PRIMERA CONFIGURACIÓN: convierte en administrador a un usuario del seed (o crea uno nuevo).

        Solo se permite mientras NINGÚN usuario tenga contraseña; después ya no, para que
        nadie pueda "reclamar" cuentas ajenas.
        """
        email = email.strip().lower()
        self._validar(email, password)
        if self.count_with_password() > 0:
            raise ValueError("Ya hay usuarios con contraseña; inicia sesión.")
        h, salt = hash_password(password)
        self.db.write(
            # MERGE = "búscalo; si no existe, créalo". Así sirve tanto para un usuario del seed como para uno nuevo.
            # ON CREATE SET solo se ejecuta si el nodo se acaba de crear (así no pisa el nombre de uno existente).
            # SET siempre se ejecuta: guarda la contraseña (hash + sal) y el rol admin.
            """MERGE (u:User {email: $email})
               ON CREATE SET u.name = $name
               SET u.password_hash = $h, u.salt = $salt, u.rol = 'admin'""",
            {"email": email, "name": name.strip() or email.split("@")[0], "h": h, "salt": salt})

    # -- CRUD ----------------------------------------------------------------
    def create(self, email: str, name: str, password: str = "", rol: str = "autor") -> None:
        """CREATE: crea un usuario. Sin contraseña queda "sin acceso" (solo figura como autor/comentarista)."""
        email = email.strip().lower()
        self._validar(email, password or None, rol)
        if self._get(email):
            raise ValueError("Ya existe un usuario con ese correo.")
        params = {"email": email, "name": name.strip() or email.split("@")[0], "rol": rol}
        extra = ""                                   # fragmento opcional de la consulta
        if password:
            params["h"], params["salt"] = hash_password(password)
            extra = ", password_hash: $h, salt: $salt"
        # {{ }} dobles porque dentro de un f-string las llaves se escriben duplicadas
        self.db.write(f"CREATE (u:User {{email: $email, name: $name, rol: $rol{extra}}})", params)

    def list(self) -> list[dict]:
        """READ: lista todos los usuarios con su rol, si pueden entrar y cuántos artículos tienen."""
        return self.db.read(
            # OPTIONAL MATCH = "si tiene artículos, tráelos; si no, igual devuelve al usuario"
            # count(a) cuenta los artículos de cada usuario
            """MATCH (u:User)
               OPTIONAL MATCH (u)-[:PUBLICO]->(a:Article)
               RETURN u.email AS email, u.name AS name, coalesce(u.rol, 'autor') AS rol,
                      u.password_hash IS NOT NULL AS acceso, count(a) AS articulos
               ORDER BY u.email""")

    def update(self, email: str, name: str, rol: str, password: str | None = None) -> None:
        """UPDATE: cambia nombre y rol. La contraseña solo se cambia si se entrega una nueva."""
        self._validar(rol=rol)
        actual = self._get(email)
        if actual is None:
            raise ValueError("El usuario no existe.")
        # Protección: no se puede quitar el rol admin al único administrador
        if (actual["rol"] == "admin" and actual["password_hash"] and rol != "admin"
                and self._count_admins() <= 1):
            raise ValueError("Debe existir al menos un administrador.")
        params = {"email": email, "name": name.strip() or email, "rol": rol}
        extra = ""
        if password:                                  # solo si escribió una contraseña nueva
            self._validar(password=password)
            params["h"], params["salt"] = hash_password(password)
            extra = ", u.password_hash = $h, u.salt = $salt"
        self.db.write(
            f"MATCH (u:User {{email: $email}}) SET u.name = $name, u.rol = $rol{extra}", params)

    def delete(self, email: str) -> None:
        """DELETE: elimina al usuario y los comentarios que escribió. Sus artículos permanecen."""
        actual = self._get(email)
        if actual is None:
            raise ValueError("El usuario no existe.")
        if actual["rol"] == "admin" and actual["password_hash"] and self._count_admins() <= 1:
            raise ValueError("No puedes eliminar al único administrador.")
        self.db.write(
            # DETACH DELETE borra el nodo Y todas sus relaciones (Neo4j no deja borrar un nodo con relaciones sueltas)
            """MATCH (u:User {email: $email})
               OPTIONAL MATCH (u)-[:ESCRIBIO]->(c:Comment)
               DETACH DELETE c, u""",
            {"email": email})


class ArticleService:
    """Todo lo relacionado con artículos (nodos :Article) y sus conexiones a autor, categorías y etiquetas."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    @staticmethod
    def _relaciones(article_id: str, categorias: list[str], etiquetas: list[str]) -> list[tuple[str, dict]]:
        """Arma las sentencias que REEMPLAZAN las categorías y etiquetas de un artículo.

        Primero borra las conexiones actuales y luego crea las nuevas. Se usa tanto al crear
        como al actualizar, así el artículo siempre queda con exactamente lo que se eligió.
        """
        stmts = [(
            # Borra solo las RELACIONES (no las categorías ni etiquetas en sí)
            "MATCH (a:Article {id: $id}) "
            "OPTIONAL MATCH (a)-[r:PERTENECE_A|TIENE_ETIQUETA]->() DELETE r",
            {"id": article_id})]
        if categorias:    # solo se vinculan categorías que YA existen
            stmts.append((
                # UNWIND convierte la lista en filas, una por categoría.
                # MATCH (no MERGE) para NO crear categorías nuevas por accidente.
                "MATCH (a:Article {id: $id}) UNWIND $cats AS nombre "
                "MATCH (c:Category {name: nombre}) MERGE (a)-[:PERTENECE_A]->(c)",
                {"id": article_id, "cats": categorias}))
        if etiquetas:     # las etiquetas nuevas SÍ se crean al vuelo (con su url)
            stmts.append((
                # MERGE busca la etiqueta; si no existe la crea (ON CREATE SET le pone su url).
                # Esto evita duplicar etiquetas que ya existen.
                "MATCH (a:Article {id: $id}) UNWIND $tags AS tag "
                "MERGE (t:Tag {name: tag.name}) ON CREATE SET t.url = tag.url "
                "MERGE (a)-[:TIENE_ETIQUETA]->(t)",
                {"id": article_id,
                 "tags": [{"name": t, "url": f"/tags/{slugify(t)}"} for t in etiquetas]}))
        return stmts

    @staticmethod
    def _limpiar(title, text, categorias, etiquetas):
        """Valida y normaliza los datos del formulario: quita espacios y elimina duplicados."""
        title, text = (title or "").strip(), (text or "").strip()
        if not title:
            raise ValueError("El título es obligatorio.")
        if not text:
            raise ValueError("El texto del artículo es obligatorio.")
        # {...} con un set elimina repetidos; sorted los deja en orden alfabético
        categorias = sorted({c.strip() for c in (categorias or []) if c.strip()})
        etiquetas = sorted({t.strip() for t in (etiquetas or []) if t.strip()})
        return title, text, categorias, etiquetas

    def create(self, title, text, autor_email, categorias=None, etiquetas=None) -> str:
        """CREATE: crea un artículo con su autor, categorías y etiquetas. Devuelve su id."""
        title, text, categorias, etiquetas = self._limpiar(title, text, categorias, etiquetas)
        article_id = siguiente_id(self.db, "Article", "art", 1)      # ej. 'art-003'
        stmts = [(
            # Busca al autor, crea el artículo y los une con la relación PUBLICO.
            # Si el autor no existe, el MATCH no encuentra nada y no se crea nada.
            """MATCH (u:User {email: $autor})
               CREATE (a:Article {id: $id, title: $title, date: $date, text: $text})
               CREATE (u)-[:PUBLICO]->(a)
               RETURN a.id AS id""",
            {"autor": autor_email, "id": article_id, "title": title,
             "date": date.today().isoformat(), "text": text}     # fecha de hoy como '2026-11-24'
        )] + self._relaciones(article_id, categorias, etiquetas)
        # Todo en una sola transacción. El primer resultado vacío = el autor no existía.
        if not self.db.write_many(stmts)[0]:
            raise ValueError("El autor no existe.")
        return article_id

    def list(self, texto: str = "") -> list[dict]:
        """READ: lista artículos con autor, categorías y etiquetas. Si se da ``texto``, filtra por título o contenido."""
        filas = self.db.read(
            # WHERE: si $q está vacío no filtra; si no, busca el texto en título o contenido (sin importar mayúsculas)
            # collect(DISTINCT ...) agrupa varios valores en una lista (todas las categorías de un artículo)
            # Se hace en dos pasos (WITH) para que categorías y etiquetas no se multipliquen entre sí.
            """MATCH (a:Article)
               WHERE $q = '' OR toLower(a.title) CONTAINS toLower($q)
                            OR toLower(a.text) CONTAINS toLower($q)
               OPTIONAL MATCH (u:User)-[:PUBLICO]->(a)
               OPTIONAL MATCH (a)-[:PERTENECE_A]->(c:Category)
               WITH a, u, collect(DISTINCT c.name) AS categorias
               OPTIONAL MATCH (a)-[:TIENE_ETIQUETA]->(t:Tag)
               WITH a, u, categorias, collect(DISTINCT t.name) AS etiquetas
               RETURN a.id AS id, a.title AS title, a.text AS text, a.date AS date,
                      coalesce(u.email, '') AS autor, categorias, etiquetas
               ORDER BY a.date DESC, a.id DESC""",
            {"q": (texto or "").strip()})
        for f in filas:      # collect() no garantiza orden: se ordena para que la tabla se vea siempre igual
            f["categorias"], f["etiquetas"] = sorted(f["categorias"]), sorted(f["etiquetas"])
        return filas

    def update(self, article_id, title, text, categorias=None, etiquetas=None) -> None:
        """UPDATE: cambia título, texto, categorías y etiquetas. El autor y la fecha NO cambian."""
        title, text, categorias, etiquetas = self._limpiar(title, text, categorias, etiquetas)
        stmts = [(
            "MATCH (a:Article {id: $id}) SET a.title = $title, a.text = $text RETURN a.id AS id",
            {"id": article_id, "title": title, "text": text}
        )] + self._relaciones(article_id, categorias, etiquetas)
        if not self.db.write_many(stmts)[0]:       # resultado vacío = ese artículo ya no existe
            raise ValueError("El artículo ya no existe.")

    def delete(self, article_id: str) -> None:
        """DELETE: elimina el artículo y sus comentarios (categorías, etiquetas y usuarios se conservan)."""
        self.db.write(
            """MATCH (a:Article {id: $id})
               OPTIONAL MATCH (a)-[:TIENE_COMENTARIO]->(c:Comment)
               DETACH DELETE c, a""",
            {"id": article_id})

    def choices(self) -> list[dict]:
        """Lista ligera (solo id y título) para llenar las listas desplegables de la pestaña Comentarios."""
        return self.db.read("MATCH (a:Article) RETURN a.id AS id, a.title AS title "
                            "ORDER BY a.date DESC, a.id DESC")


class TaxonomyService:
    """CRUD genérico para :Category y :Tag. Los dos tienen la misma forma (name único + url),
    así que se programa una sola vez y se usa para ambos.

    ``label`` y ``url_prefix`` son constantes internas (no vienen del usuario),
    por eso es seguro insertar ``label`` en la consulta con f-string.
    """

    def __init__(self, db: Neo4jConnection, label: str, url_prefix: str, humano: str):
        # label: 'Category' o 'Tag'; url_prefix: '/categorias/' o '/tags/'; humano: texto para los mensajes
        self.db, self.label, self.url_prefix, self.humano = db, label, url_prefix, humano

    def _existe(self, name: str) -> bool:
        """¿Ya hay una categoría/etiqueta con ese nombre?"""
        return bool(self.db.read(
            f"MATCH (n:{self.label} {{name: $n}}) RETURN n.name AS name", {"n": name}))

    def names(self) -> list[str]:
        """Solo los nombres, en orden alfabético (para la lista de categorías del formulario de artículos)."""
        # OJO: el alias NO puede llamarse "n" porque taparía al nodo n en el ORDER BY
        rows = self.db.read(f"MATCH (n:{self.label}) RETURN n.name AS name ORDER BY toLower(n.name)")
        return [r["name"] for r in rows]

    def list(self) -> list[dict]:
        """READ: lista nombre, url y cuántos artículos usan cada categoría/etiqueta."""
        # Una categoría se une con PERTENECE_A y una etiqueta con TIENE_ETIQUETA; se aceptan ambas
        # (para una Category solo coincidirá la primera, y para una Tag la segunda).
        return self.db.read(
            f"""MATCH (n:{self.label})
                OPTIONAL MATCH (a:Article)-[:PERTENECE_A|TIENE_ETIQUETA]->(n)
                RETURN n.name AS name, coalesce(n.url, '') AS url, count(DISTINCT a) AS articulos
                ORDER BY toLower(n.name)""")

    def create(self, name: str) -> None:
        """CREATE: crea una categoría/etiqueta; la url se genera sola a partir del nombre."""
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre es obligatorio.")
        if self._existe(name):
            raise ValueError(f"Ya existe {self.humano} con ese nombre.")
        self.db.write(f"CREATE (n:{self.label} {{name: $n, url: $url}})",
                      {"n": name, "url": self.url_prefix + slugify(name)})

    def update(self, anterior: str, nuevo: str) -> None:
        """UPDATE: renombra y recalcula la url."""
        nuevo = (nuevo or "").strip()
        if not nuevo:
            raise ValueError("El nombre es obligatorio.")
        if nuevo != anterior and self._existe(nuevo):
            raise ValueError(f"Ya existe {self.humano} con ese nombre.")
        self.db.write(f"MATCH (n:{self.label} {{name: $old}}) SET n.name = $new, n.url = $url",
                      {"old": anterior, "new": nuevo, "url": self.url_prefix + slugify(nuevo)})

    def delete(self, name: str) -> None:
        """DELETE: elimina el nodo y sus relaciones (los artículos NO se borran)."""
        self.db.write(f"MATCH (n:{self.label} {{name: $n}}) DETACH DELETE n", {"n": name})


class CommentService:
    """Todo lo relacionado con comentarios (nodos :Comment). Su texto vive en la propiedad ``name``."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    def create(self, article_id: str, autor_email: str, texto: str) -> None:
        """CREATE: crea un comentario y lo conecta con su artículo y su autor."""
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("El comentario no puede estar vacío.")
        cid = siguiente_id(self.db, "Comment", "cmt", 101)        # ej. 'cmt-104'
        res = self.db.write(
            # Busca el artículo y el usuario, crea el comentario y lo une a ambos
            """MATCH (a:Article {id: $aid}), (u:User {email: $autor})
               CREATE (cm:Comment {id: $id, name: $texto, url: $url})
               CREATE (u)-[:ESCRIBIO]->(cm)
               CREATE (a)-[:TIENE_COMENTARIO]->(cm)
               RETURN cm.id AS id""",
            {"aid": article_id, "autor": autor_email, "id": cid, "texto": texto,
             "url": f"/articulos/{article_id}#{cid}"})
        if not res:        # no se creó nada: el artículo o el autor ya no existen
            raise ValueError("El artículo o el autor ya no existen.")

    def list(self, article_id: str | None = None) -> list[dict]:
        """READ: lista comentarios con su autor y artículo. Si se da article_id, solo los de ese artículo."""
        return self.db.read(
            # $aid IS NULL OR ... : si no se pasa artículo, trae todos; si se pasa, filtra
            """MATCH (a:Article)-[:TIENE_COMENTARIO]->(cm:Comment)
               WHERE $aid IS NULL OR a.id = $aid
               OPTIONAL MATCH (u:User)-[:ESCRIBIO]->(cm)
               RETURN cm.id AS id, cm.name AS texto, coalesce(u.email, '') AS autor,
                      a.id AS article_id, a.title AS articulo
               ORDER BY cm.id DESC""",
            {"aid": article_id})

    def update(self, comment_id: str, texto: str) -> None:
        """UPDATE: cambia el texto del comentario."""
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("El comentario no puede estar vacío.")
        self.db.write("MATCH (cm:Comment {id: $id}) SET cm.name = $texto",
                      {"id": comment_id, "texto": texto})

    def delete(self, comment_id: str) -> None:
        """DELETE: elimina el comentario y sus relaciones."""
        self.db.write("MATCH (cm:Comment {id: $id}) DETACH DELETE cm", {"id": comment_id})


class Services:
    """Agrupa todos los servicios en un solo objeto. Es lo que recibe la interfaz gráfica:
    services.articles.create(...), services.users.list(), services.comments.delete(...), etc."""

    def __init__(self, db: Neo4jConnection):
        self.users = UserService(db)
        self.articles = ArticleService(db)
        # El mismo TaxonomyService sirve para las dos, solo cambian el label y el prefijo de url
        self.categories = TaxonomyService(db, "Category", "/categorias/", "una categoría")
        self.tags = TaxonomyService(db, "Tag", "/tags/", "una etiqueta")
        self.comments = CommentService(db)