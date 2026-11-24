"""blog_db.py — Capa de datos del blog (Neo4j).

Contiene, en este orden:
  1. Configuración (lee .env / variables de entorno)
  2. Conexión a Neo4j (única clase que usa el driver)
  3. Manejo de contraseñas (hash PBKDF2 + sal)
  4. Servicios CRUD en Cypher: usuarios, artículos, categorías/etiquetas, comentarios

Modelo de grafo (el definido en cypher/01..04):
  (:User {email, name})                      + password_hash, salt, rol  (agregados por la app para el login)
  (:Article {id, title, date, text})
  (:Category {name, url})   (:Tag {name, url})
  (:Comment {id, name, url})                 'name' guarda el TEXTO del comentario

  (:User)-[:PUBLICO]->(:Article)
  (:Article)-[:PERTENECE_A]->(:Category)       (un artículo puede tener varias categorías)
  (:Article)-[:TIENE_ETIQUETA]->(:Tag)
  (:Article)-[:TIENE_COMENTARIO]->(:Comment)<-[:ESCRIBIO]-(:User)

Todas las consultas usan PARÁMETROS ($param); nunca se concatena texto del usuario
dentro de Cypher, para evitar inyección.
"""
from __future__ import annotations  # los métodos list() de las clases no deben tapar al tipo list[...]

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:          # python-dotenv es opcional: si falta se usan las variables del sistema
    load_dotenv = None

# =========================================================================== #
# 1. CONFIGURACIÓN
# =========================================================================== #
ROOT_DIR = Path(__file__).resolve().parents[1]      # .../Proyecto Final BD/
ENV_PATH = ROOT_DIR / ".env"


@dataclass(frozen=True)
class Settings:
    """Parámetros de conexión a Neo4j."""
    uri: str
    user: str
    password: str
    database: str


def load_settings() -> Settings:
    """Lee la configuración desde el archivo .env (raíz del repo) o el entorno."""
    if load_dotenv is not None:
        load_dotenv(ENV_PATH)
    return Settings(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        # Se aceptan ambos nombres: NEO4J_USER y NEO4J_USERNAME (el que usa AuraDB)
        user=os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j",
        password=os.getenv("NEO4J_PASSWORD", ""),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )


# =========================================================================== #
# 2. CONEXIÓN
# =========================================================================== #
# Mismas restricciones/índices que cypher/01_schema_constraints.cypher (con IF NOT EXISTS
# son idempotentes: si ya se ejecutó ese script, no pasa nada).
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT constraint_user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE",
    "CREATE CONSTRAINT constraint_article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_tag_name IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT constraint_category_name IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE",
    "CREATE INDEX index_article_title IF NOT EXISTS FOR (a:Article) ON (a.title)",
    "CREATE INDEX index_article_date IF NOT EXISTS FOR (a:Article) ON (a.date)",
]


class Neo4jConnection:
    """Envuelve el driver de Neo4j con métodos simples de lectura/escritura."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._driver = None

    def connect(self) -> None:
        """Abre el driver y verifica que el servidor responde y las credenciales son válidas."""
        self._driver = GraphDatabase.driver(
            self.settings.uri, auth=(self.settings.user, self.settings.password))
        self._driver.verify_connectivity()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def ensure_schema(self) -> None:
        with self._driver.session(database=self.settings.database) as session:
            for statement in SCHEMA_STATEMENTS:
                session.run(statement).consume()

    def read(self, query: str, params: dict | None = None) -> list[dict]:
        """Consulta de solo lectura -> lista de diccionarios."""
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_read(lambda tx: tx.run(query, params or {}).data())

    def write(self, query: str, params: dict | None = None) -> list[dict]:
        """Una sentencia de escritura en su propia transacción."""
        return self.write_many([(query, params or {})])[0]

    def write_many(self, statements: list[tuple[str, dict]]) -> list[list[dict]]:
        """Varias sentencias en UNA transacción (todo o nada)."""
        def work(tx):
            return [tx.run(query, params).data() for query, params in statements]
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_write(work)


# =========================================================================== #
# 3. CONTRASEÑAS
# =========================================================================== #
# Nunca se guarda la contraseña: solo un hash PBKDF2-SHA256 con sal aleatoria por usuario.
ITERATIONS = 200_000


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Devuelve (hash_hex, salt_hex). Si no se pasa sal, genera una nueva."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Compara contra el hash guardado en tiempo constante."""
    calculado, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(calculado, hash_hex)


# =========================================================================== #
# 4. UTILIDADES
# =========================================================================== #
ROLES = ("admin", "autor")


def slugify(texto: str) -> str:
    """'Bases de Datos' -> 'bases-de-datos' (para las propiedades url de Tag/Category)."""
    ascii_ = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-") or "sin-nombre"


def siguiente_id(db: Neo4jConnection, label: str, prefijo: str, inicio: int) -> str:
    """Genera el siguiente id con el formato del seed: 'art-003', 'cmt-104'...

    ``label`` y ``prefijo`` son constantes internas (no vienen del usuario).
    """
    filas = db.read(f"MATCH (n:{label}) RETURN n.id AS id")
    numeros = [int(m.group(1)) for f in filas
               if (m := re.fullmatch(rf"{prefijo}-(\d+)", f["id"] or ""))]
    return f"{prefijo}-{max(numeros, default=inicio - 1) + 1:03d}"


# =========================================================================== #
# 5. SERVICIOS (CRUD)
# =========================================================================== #
class UserService:
    """Usuarios (:User). El correo es la llave y el "usuario" del login."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    def _get(self, email: str) -> dict | None:
        rows = self.db.read(
            """MATCH (u:User {email: $email})
               RETURN u.email AS email, u.name AS name, coalesce(u.rol, 'autor') AS rol,
                      u.password_hash AS password_hash, u.salt AS salt""",
            {"email": email})
        return rows[0] if rows else None

    def _count_admins(self) -> int:
        return self.db.read(
            "MATCH (u:User {rol: 'admin'}) WHERE u.password_hash IS NOT NULL RETURN count(u) AS n")[0]["n"]

    def count_with_password(self) -> int:
        """Usuarios que ya pueden iniciar sesión. Si es 0 -> primera configuración."""
        return self.db.read(
            "MATCH (u:User) WHERE u.password_hash IS NOT NULL RETURN count(u) AS n")[0]["n"]

    @staticmethod
    def _validar(email=None, password=None, rol=None):
        if email is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Escribe un correo válido (ej. carlos@example.com).")
        if password is not None and len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        if rol is not None and rol not in ROLES:
            raise ValueError(f"Rol inválido. Usa: {', '.join(ROLES)}.")

    # -- login ---------------------------------------------------------------
    def authenticate(self, email: str, password: str) -> dict | None:
        """Devuelve {email, name, rol} si las credenciales son correctas; si no, None."""
        row = self._get(email.strip().lower())
        if not row or not row["password_hash"]:
            return None          # no existe, o existe pero aún no tiene contraseña
        if not verify_password(password, row["password_hash"], row["salt"]):
            return None
        return {"email": row["email"], "name": row["name"], "rol": row["rol"]}

    def setup_first_admin(self, email: str, name: str, password: str) -> None:
        """Primera configuración: convierte en administrador a un usuario del seed (o crea uno nuevo).

        Solo se permite mientras NINGÚN usuario tenga contraseña.
        """
        email = email.strip().lower()
        self._validar(email, password)
        if self.count_with_password() > 0:
            raise ValueError("Ya hay usuarios con contraseña; inicia sesión.")
        h, salt = hash_password(password)
        self.db.write(
            """MERGE (u:User {email: $email})
               ON CREATE SET u.name = $name
               SET u.password_hash = $h, u.salt = $salt, u.rol = 'admin'""",
            {"email": email, "name": name.strip() or email.split("@")[0], "h": h, "salt": salt})

    # -- CRUD ----------------------------------------------------------------
    def create(self, email: str, name: str, password: str = "", rol: str = "autor") -> None:
        """Crea un usuario. Sin contraseña queda "sin acceso" (solo figura como autor/comentarista)."""
        email = email.strip().lower()
        self._validar(email, password or None, rol)
        if self._get(email):
            raise ValueError("Ya existe un usuario con ese correo.")
        params = {"email": email, "name": name.strip() or email.split("@")[0], "rol": rol}
        extra = ""
        if password:
            params["h"], params["salt"] = hash_password(password)
            extra = ", password_hash: $h, salt: $salt"
        self.db.write(f"CREATE (u:User {{email: $email, name: $name, rol: $rol{extra}}})", params)

    def list(self) -> list[dict]:
        return self.db.read(
            """MATCH (u:User)
               OPTIONAL MATCH (u)-[:PUBLICO]->(a:Article)
               RETURN u.email AS email, u.name AS name, coalesce(u.rol, 'autor') AS rol,
                      u.password_hash IS NOT NULL AS acceso, count(a) AS articulos
               ORDER BY u.email""")

    def update(self, email: str, name: str, rol: str, password: str | None = None) -> None:
        """Cambia nombre/rol. La contraseña solo se cambia si se entrega una nueva."""
        self._validar(rol=rol)
        actual = self._get(email)
        if actual is None:
            raise ValueError("El usuario no existe.")
        if (actual["rol"] == "admin" and actual["password_hash"] and rol != "admin"
                and self._count_admins() <= 1):
            raise ValueError("Debe existir al menos un administrador.")
        params = {"email": email, "name": name.strip() or email, "rol": rol}
        extra = ""
        if password:
            self._validar(password=password)
            params["h"], params["salt"] = hash_password(password)
            extra = ", u.password_hash = $h, u.salt = $salt"
        self.db.write(
            f"MATCH (u:User {{email: $email}}) SET u.name = $name, u.rol = $rol{extra}", params)

    def delete(self, email: str) -> None:
        """Elimina al usuario y los comentarios que escribió. Sus artículos permanecen."""
        actual = self._get(email)
        if actual is None:
            raise ValueError("El usuario no existe.")
        if actual["rol"] == "admin" and actual["password_hash"] and self._count_admins() <= 1:
            raise ValueError("No puedes eliminar al único administrador.")
        self.db.write(
            """MATCH (u:User {email: $email})
               OPTIONAL MATCH (u)-[:ESCRIBIO]->(c:Comment)
               DETACH DELETE c, u""",
            {"email": email})


class ArticleService:
    """Artículos (:Article) con su autor, categorías y etiquetas."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    @staticmethod
    def _relaciones(article_id: str, categorias: list[str], etiquetas: list[str]) -> list[tuple[str, dict]]:
        """Sentencias que REEMPLAZAN las categorías y etiquetas de un artículo."""
        stmts = [(
            "MATCH (a:Article {id: $id}) "
            "OPTIONAL MATCH (a)-[r:PERTENECE_A|TIENE_ETIQUETA]->() DELETE r",
            {"id": article_id})]
        if categorias:    # solo se vinculan categorías que ya existen
            stmts.append((
                "MATCH (a:Article {id: $id}) UNWIND $cats AS nombre "
                "MATCH (c:Category {name: nombre}) MERGE (a)-[:PERTENECE_A]->(c)",
                {"id": article_id, "cats": categorias}))
        if etiquetas:     # las etiquetas nuevas se crean al vuelo (con su url)
            stmts.append((
                "MATCH (a:Article {id: $id}) UNWIND $tags AS tag "
                "MERGE (t:Tag {name: tag.name}) ON CREATE SET t.url = tag.url "
                "MERGE (a)-[:TIENE_ETIQUETA]->(t)",
                {"id": article_id,
                 "tags": [{"name": t, "url": f"/tags/{slugify(t)}"} for t in etiquetas]}))
        return stmts

    @staticmethod
    def _limpiar(title, text, categorias, etiquetas):
        title, text = (title or "").strip(), (text or "").strip()
        if not title:
            raise ValueError("El título es obligatorio.")
        if not text:
            raise ValueError("El texto del artículo es obligatorio.")
        categorias = sorted({c.strip() for c in (categorias or []) if c.strip()})
        etiquetas = sorted({t.strip() for t in (etiquetas or []) if t.strip()})
        return title, text, categorias, etiquetas

    def create(self, title, text, autor_email, categorias=None, etiquetas=None) -> str:
        title, text, categorias, etiquetas = self._limpiar(title, text, categorias, etiquetas)
        article_id = siguiente_id(self.db, "Article", "art", 1)
        stmts = [(
            """MATCH (u:User {email: $autor})
               CREATE (a:Article {id: $id, title: $title, date: $date, text: $text})
               CREATE (u)-[:PUBLICO]->(a)
               RETURN a.id AS id""",
            {"autor": autor_email, "id": article_id, "title": title,
             "date": date.today().isoformat(), "text": text}
        )] + self._relaciones(article_id, categorias, etiquetas)
        if not self.db.write_many(stmts)[0]:
            raise ValueError("El autor no existe.")
        return article_id

    def list(self, texto: str = "") -> list[dict]:
        """Lista artículos; si se da ``texto`` filtra por título o contenido."""
        filas = self.db.read(
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
        for f in filas:      # collect() no garantiza orden: se ordena para que la tabla sea estable
            f["categorias"], f["etiquetas"] = sorted(f["categorias"]), sorted(f["etiquetas"])
        return filas

    def update(self, article_id, title, text, categorias=None, etiquetas=None) -> None:
        title, text, categorias, etiquetas = self._limpiar(title, text, categorias, etiquetas)
        stmts = [(
            "MATCH (a:Article {id: $id}) SET a.title = $title, a.text = $text RETURN a.id AS id",
            {"id": article_id, "title": title, "text": text}
        )] + self._relaciones(article_id, categorias, etiquetas)
        if not self.db.write_many(stmts)[0]:
            raise ValueError("El artículo ya no existe.")

    def delete(self, article_id: str) -> None:
        """Elimina el artículo y sus comentarios (categorías, etiquetas y usuarios se conservan)."""
        self.db.write(
            """MATCH (a:Article {id: $id})
               OPTIONAL MATCH (a)-[:TIENE_COMENTARIO]->(c:Comment)
               DETACH DELETE c, a""",
            {"id": article_id})

    def choices(self) -> list[dict]:
        """Lista ligera (id, title) para los combos de selección."""
        return self.db.read("MATCH (a:Article) RETURN a.id AS id, a.title AS title "
                            "ORDER BY a.date DESC, a.id DESC")


class TaxonomyService:
    """CRUD genérico para :Category y :Tag (ambos tienen name único y url).

    ``label`` y ``url_prefix`` son constantes internas (no vienen del usuario),
    por eso es seguro insertar ``label`` en la consulta con f-string.
    """

    def __init__(self, db: Neo4jConnection, label: str, url_prefix: str, humano: str):
        self.db, self.label, self.url_prefix, self.humano = db, label, url_prefix, humano

    def _existe(self, name: str) -> bool:
        return bool(self.db.read(
            f"MATCH (n:{self.label} {{name: $n}}) RETURN n.name AS name", {"n": name}))

    def names(self) -> list[str]:
        # OJO: el alias NO puede llamarse "n" porque taparía al nodo en el ORDER BY
        rows = self.db.read(f"MATCH (n:{self.label}) RETURN n.name AS name ORDER BY toLower(n.name)")
        return [r["name"] for r in rows]

    def list(self) -> list[dict]:
        # Categoría y etiqueta se vinculan con relaciones distintas, así que se cuenta con ambas
        return self.db.read(
            f"""MATCH (n:{self.label})
                OPTIONAL MATCH (a:Article)-[:PERTENECE_A|TIENE_ETIQUETA]->(n)
                RETURN n.name AS name, coalesce(n.url, '') AS url, count(DISTINCT a) AS articulos
                ORDER BY toLower(n.name)""")

    def create(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre es obligatorio.")
        if self._existe(name):
            raise ValueError(f"Ya existe {self.humano} con ese nombre.")
        self.db.write(f"CREATE (n:{self.label} {{name: $n, url: $url}})",
                      {"n": name, "url": self.url_prefix + slugify(name)})

    def update(self, anterior: str, nuevo: str) -> None:
        nuevo = (nuevo or "").strip()
        if not nuevo:
            raise ValueError("El nombre es obligatorio.")
        if nuevo != anterior and self._existe(nuevo):
            raise ValueError(f"Ya existe {self.humano} con ese nombre.")
        self.db.write(f"MATCH (n:{self.label} {{name: $old}}) SET n.name = $new, n.url = $url",
                      {"old": anterior, "new": nuevo, "url": self.url_prefix + slugify(nuevo)})

    def delete(self, name: str) -> None:
        """Elimina el nodo y sus relaciones (los artículos NO se borran)."""
        self.db.write(f"MATCH (n:{self.label} {{name: $n}}) DETACH DELETE n", {"n": name})


class CommentService:
    """Comentarios (:Comment). Su texto vive en la propiedad ``name``."""

    def __init__(self, db: Neo4jConnection):
        self.db = db

    def create(self, article_id: str, autor_email: str, texto: str) -> None:
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("El comentario no puede estar vacío.")
        cid = siguiente_id(self.db, "Comment", "cmt", 101)
        res = self.db.write(
            """MATCH (a:Article {id: $aid}), (u:User {email: $autor})
               CREATE (cm:Comment {id: $id, name: $texto, url: $url})
               CREATE (u)-[:ESCRIBIO]->(cm)
               CREATE (a)-[:TIENE_COMENTARIO]->(cm)
               RETURN cm.id AS id""",
            {"aid": article_id, "autor": autor_email, "id": cid, "texto": texto,
             "url": f"/articulos/{article_id}#{cid}"})
        if not res:
            raise ValueError("El artículo o el autor ya no existen.")

    def list(self, article_id: str | None = None) -> list[dict]:
        return self.db.read(
            """MATCH (a:Article)-[:TIENE_COMENTARIO]->(cm:Comment)
               WHERE $aid IS NULL OR a.id = $aid
               OPTIONAL MATCH (u:User)-[:ESCRIBIO]->(cm)
               RETURN cm.id AS id, cm.name AS texto, coalesce(u.email, '') AS autor,
                      a.id AS article_id, a.title AS articulo
               ORDER BY cm.id DESC""",
            {"aid": article_id})

    def update(self, comment_id: str, texto: str) -> None:
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("El comentario no puede estar vacío.")
        self.db.write("MATCH (cm:Comment {id: $id}) SET cm.name = $texto",
                      {"id": comment_id, "texto": texto})

    def delete(self, comment_id: str) -> None:
        self.db.write("MATCH (cm:Comment {id: $id}) DETACH DELETE cm", {"id": comment_id})


class Services:
    """Contenedor con todos los servicios; es lo que recibe la interfaz gráfica."""

    def __init__(self, db: Neo4jConnection):
        self.users = UserService(db)
        self.articles = ArticleService(db)
        self.categories = TaxonomyService(db, "Category", "/categorias/", "una categoría")
        self.tags = TaxonomyService(db, "Tag", "/tags/", "una etiqueta")
        self.comments = CommentService(db)