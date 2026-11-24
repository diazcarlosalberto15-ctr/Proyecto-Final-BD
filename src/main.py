"""main.py — INTERFAZ GRÁFICA del blog (tkinter).

¿Para qué sirve este archivo?
    Dibuja las ventanas y conecta cada botón con la función correspondiente de
    blog_db.py. NO contiene consultas Cypher: toda la base de datos está en blog_db.py.

Cómo ejecutarlo (desde la raíz del repositorio):   python src/main.py

Flujo de la aplicación:
    1. Conecta a Neo4j (si falla, ofrece reintentar)
    2. Muestra el LOGIN (correo + contraseña)
    3. Abre la ventana principal con pestañas, cada una con su CRUD:
         Artículos | Categorías | Etiquetas | Comentarios | Usuarios (solo admin)

Contenido, en este orden:
    - UTILIDADES DE INTERFAZ  (funciones que se reutilizan en todas las pestañas)
    - LOGIN                   (pantalla de inicio de sesión)
    - ArticlesTab             (pestaña de artículos)
    - TaxonomyTab             (pestañas de categorías y etiquetas, misma pantalla)
    - CommentsTab             (pestaña de comentarios)
    - UsersTab                (pestaña de usuarios, solo admin)
    - App y run()             (ventana principal y arranque del programa)
"""
import functools                         # para crear el decorador @guarded
import tkinter as tk                     # librería de ventanas incluida en Python
from tkinter import messagebox, ttk      # messagebox = ventanas de aviso; ttk = widgets con mejor aspecto

# Tipos de error de Neo4j, para mostrar mensajes claros en lugar de que el programa se cierre
from neo4j.exceptions import ConstraintError, Neo4jError, ServiceUnavailable, SessionExpired

# Todo lo que necesita de la capa de datos
from blog_db import ENV_PATH, ROLES, Neo4jConnection, Services, load_settings


# =========================================================================== #
# UTILIDADES DE INTERFAZ
# =========================================================================== #
def guarded(method):
    """DECORADOR de seguridad para los botones.

    Se pone @guarded encima de una función que responde a un botón. Si esa función falla
    (error de validación, base apagada, etc.), en lugar de cerrar la aplicación muestra
    una ventana de aviso con el motivo. Si hay error, la función devuelve None.
    """
    @functools.wraps(method)             # conserva el nombre y la documentación de la función original
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)           # intenta ejecutar la función normalmente
        except ValueError as e:                            # errores de validación (los lanza blog_db.py)
            messagebox.showwarning("Revisa los datos", str(e), parent=self)
        except ConstraintError:                            # violaría una restricción de unicidad
            messagebox.showwarning("Duplicado", "Ya existe un registro con esos datos.", parent=self)
        except (ServiceUnavailable, SessionExpired):       # Neo4j se apagó o se perdió la conexión
            messagebox.showerror("Conexión", "Se perdió la conexión con Neo4j. "
                                 "Verifica que la base esté encendida.", parent=self)
        except Neo4jError as e:                            # cualquier otro error de Neo4j
            messagebox.showerror("Error de Neo4j", e.message or str(e), parent=self)
        except Exception as e:                             # último recurso: cualquier otro error
            messagebox.showerror("Error inesperado", f"{type(e).__name__}: {e}", parent=self)
        return None
    return wrapper


def make_tree(parent, columns, height=8):
    """Crea una TABLA (Treeview) con barra de desplazamiento.

    ``columns`` es una lista de (id_columna, encabezado, ancho_en_pixeles).
    Devuelve la tabla para poder llenarla después.
    """
    frame = ttk.Frame(parent)                              # contenedor de la tabla + su scrollbar
    frame.pack(fill="both", expand=True, pady=6)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                        height=height, selectmode="browse")    # browse = solo se puede elegir una fila
    for cid, heading, width in columns:
        tree.heading(cid, text=heading)                    # título de la columna
        tree.column(cid, width=width, anchor="w")          # ancho y alineación a la izquierda
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)              # conecta la tabla con su barra
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return tree


def button_bar(parent, buttons):
    """Crea una fila de botones. ``buttons`` es una lista de (texto, función_que_se_ejecuta)."""
    bar = ttk.Frame(parent)
    bar.pack(fill="x", pady=(8, 0))
    for text, command in buttons:
        ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))


def fila(form, row, etiqueta, widget):
    """Coloca en el formulario una fila: [etiqueta a la izquierda] + [campo a la derecha]."""
    ttk.Label(form, text=etiqueta).grid(row=row, column=0, sticky="ne", padx=(0, 8), pady=3)
    widget.grid(row=row, column=1, sticky="ew", pady=3)


def seleccionada(tree, filas: dict):
    """Devuelve los datos de la fila que el usuario seleccionó en la tabla (o None si no hay ninguna).

    ``filas`` es un diccionario {id_de_fila: datos}; el id de cada fila de la tabla es la llave.
    """
    sel = tree.selection()
    return filas.get(sel[0]) if sel else None


# =========================================================================== #
# LOGIN
# =========================================================================== #
class LoginFrame(ttk.Frame):
    """Pantalla de inicio de sesión: pide correo y contraseña.

    Si NINGÚN usuario tiene contraseña todavía (primera vez), se transforma en el
    formulario de "primera configuración" para crear al administrador.
    """

    def __init__(self, parent, services, on_success, first_run=False):
        super().__init__(parent, padding=28)
        self.services = services
        self.on_success = on_success        # función que se llama al iniciar sesión bien (abre la ventana principal)
        self.first_run = first_run          # True = modo "primera configuración"
        # Variables de tkinter: guardan lo que el usuario escribe en cada campo
        self.email = tk.StringVar()
        self.name = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()

        # --- Título ---
        ttk.Label(self, text="Blog · Panel de administración",
                  font=("Helvetica", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 4))
        subtitulo = ("Primera configuración: crea el administrador" if first_run else "Iniciar sesión")
        ttk.Label(self, text=subtitulo, font=("Helvetica", 11)).grid(row=1, column=0, columnspan=2)
        r = 2                               # número de la siguiente fila libre en la cuadrícula
        if first_run:
            ttk.Label(self, wraplength=340, foreground="#555", justify="center",
                      text="Ningún usuario tiene contraseña aún. Puedes usar el correo de un "
                           "usuario existente (ej. carlos@example.com) o uno nuevo."
                      ).grid(row=r, column=0, columnspan=2, pady=(6, 10)); r += 1
        else:
            ttk.Label(self).grid(row=r, column=0); r += 1       # espacio en blanco

        # --- Campos del formulario (algunos solo aparecen en la primera configuración) ---
        self.email_entry = self._campo("Correo:", self.email, r); r += 1
        if first_run:
            self._campo("Nombre:", self.name, r); r += 1
        self._campo("Contraseña:", self.password, r, secreto=True); r += 1
        if first_run:
            self._campo("Confirmar:", self.confirm, r, secreto=True); r += 1

        # Etiqueta roja donde se muestran los errores ("contraseña incorrecta", etc.)
        self.msg = ttk.Label(self, text="", foreground="#b00020")
        self.msg.grid(row=r, column=0, columnspan=2, pady=(8, 0)); r += 1
        ttk.Button(self, text="Crear y entrar" if first_run else "Ingresar", command=self._submit
                   ).grid(row=r, column=0, columnspan=2, pady=(12, 0), sticky="ew")

        self.bind_all("<Return>", self._submit)             # la tecla Enter también envía el formulario
        self.email_entry.focus_set()                        # el cursor empieza en el campo de correo

    def _campo(self, etiqueta, variable, r, secreto=False):
        """Crea una fila 'etiqueta + campo de texto'. Si secreto=True, muestra puntos en vez de letras."""
        ttk.Label(self, text=etiqueta).grid(row=r, column=0, sticky="e", padx=(0, 8), pady=4)
        entry = ttk.Entry(self, textvariable=variable, width=30, show="•" if secreto else "")
        entry.grid(row=r, column=1, pady=4)
        return entry

    def destroy(self):
        """Al cerrar esta pantalla, la tecla Enter deja de enviar el login (si no, seguiría activa)."""
        self.unbind_all("<Return>")
        super().destroy()

    @guarded
    def _submit(self, _event=None):
        """Se ejecuta al presionar 'Ingresar' o Enter."""
        email, password = self.email.get().strip().lower(), self.password.get()
        if not email or not password:
            self.msg.config(text="Escribe correo y contraseña.")
            return
        if self.first_run:
            # Primera vez: primero se crea/configura al administrador y luego se inicia sesión con él
            if password != self.confirm.get():
                raise ValueError("Las contraseñas no coinciden.")
            self.services.users.setup_first_admin(email, self.name.get(), password)

        user = self.services.users.authenticate(email, password)    # compara contra el hash guardado en Neo4j
        if user is None:
            self.password.set("")                                    # limpia la contraseña escrita
            self.msg.config(text="Correo o contraseña incorrectos.")
            return
        self.on_success(user)                                        # abre la ventana principal


# =========================================================================== #
# PESTAÑA: ARTÍCULOS
# =========================================================================== #
class ArticlesTab(ttk.Frame):
    """Pestaña de artículos: tabla arriba, formulario abajo, botones al final.

    Patrón de todas las pestañas: al hacer clic en una fila de la tabla, sus datos pasan
    al formulario; los botones Crear/Actualizar/Eliminar actúan sobre lo que hay en él.
    """

    def __init__(self, parent, services, user):
        super().__init__(parent, padding=10)
        self.s, self.user = services, user          # self.s = servicios de blog_db; self.user = quien inició sesión
        self._rows: dict[str, dict] = {}            # {id_artículo: datos} de lo que muestra la tabla
        self._cat_names: list[str] = []             # nombres de categorías, en el mismo orden que la lista del formulario

        # --- Barra de búsqueda ---
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        self.q = tk.StringVar()
        ttk.Label(barra, text="Buscar:").pack(side="left")
        entrada = ttk.Entry(barra, textvariable=self.q, width=40)
        entrada.pack(side="left", padx=6)
        entrada.bind("<Return>", lambda _e: self.refresh())     # Enter también busca
        ttk.Button(barra, text="Buscar", command=self.refresh).pack(side="left")
        ttk.Button(barra, text="Limpiar", command=self._limpiar_busqueda).pack(side="left", padx=6)

        # --- Tabla de artículos ---
        self.tree = make_tree(self, [("title", "Título", 250), ("autor", "Autor", 150),
                                     ("categorias", "Categorías", 210), ("etiquetas", "Etiquetas", 170),
                                     ("date", "Fecha", 80)], height=7)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)   # al elegir una fila, llena el formulario

        # --- Formulario ---
        form = ttk.Frame(self)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)                       # la columna de campos se estira con la ventana
        self.title = tk.StringVar()
        self.etiquetas = tk.StringVar()
        fila(form, 0, "Título:", ttk.Entry(form, textvariable=self.title))
        # Un artículo puede tener VARIAS categorías -> lista de selección múltiple (Ctrl+clic)
        cats = ttk.Frame(form)
        self.cat_list = tk.Listbox(cats, selectmode="multiple", height=3, exportselection=False)
        sb = ttk.Scrollbar(cats, orient="vertical", command=self.cat_list.yview)
        self.cat_list.configure(yscrollcommand=sb.set)
        self.cat_list.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        fila(form, 1, "Categorías (Ctrl+clic\npara varias):", cats)
        fila(form, 2, "Etiquetas (separadas\npor coma):", ttk.Entry(form, textvariable=self.etiquetas))
        self.text = tk.Text(form, height=5, wrap="word")        # cuadro de texto grande para el contenido
        fila(form, 3, "Texto:", self.text)

        button_bar(self, [("Nuevo", self._limpiar_form), ("Crear", self.crear),
                          ("Actualizar", self.actualizar), ("Eliminar", self.eliminar)])
        self.refresh()                                          # carga los datos al abrir la pestaña

    # -- utilidades ----------------------------------------------------------
    def _limpiar_busqueda(self):
        """Borra el texto de búsqueda y vuelve a mostrar todos los artículos."""
        self.q.set("")
        self.refresh()

    def _limpiar_form(self):
        """Vacía el formulario y quita la selección de la tabla (botón 'Nuevo')."""
        self.tree.selection_remove(*self.tree.selection())
        self.title.set(""); self.etiquetas.set("")
        self.cat_list.selection_clear(0, "end")
        self.text.delete("1.0", "end")

    def _puede_modificar(self, art) -> bool:
        """Regla de permisos: el admin puede con todo; un autor solo con sus propios artículos."""
        return self.user["rol"] == "admin" or art["autor"] == self.user["email"]

    def _datos_form(self) -> dict:
        """Lee lo que hay en el formulario y lo devuelve listo para pasárselo a blog_db."""
        return dict(title=self.title.get(), text=self.text.get("1.0", "end"),
                    # curselection() da las posiciones marcadas; _cat_names las convierte en nombres
                    categorias=[self._cat_names[i] for i in self.cat_list.curselection()],
                    etiquetas=self.etiquetas.get().split(","))      # "a, b" -> ["a", " b"] (blog_db las limpia)

    def _on_select(self, _event=None):
        """Al elegir una fila de la tabla, copia sus datos al formulario para poder editarlos."""
        art = seleccionada(self.tree, self._rows)
        if not art:
            return
        self.title.set(art["title"])
        self.etiquetas.set(", ".join(art["etiquetas"]))
        self.text.delete("1.0", "end")
        self.text.insert("1.0", art["text"] or "")
        self.cat_list.selection_clear(0, "end")
        for i, nombre in enumerate(self._cat_names):            # marca las categorías que tiene el artículo
            if nombre in art["categorias"]:
                self.cat_list.selection_set(i)

    def _cargar_categorias(self):
        """Recarga la lista de categorías del formulario conservando lo que estaba marcado."""
        marcadas = {self._cat_names[i] for i in self.cat_list.curselection()}
        self._cat_names = self.s.categories.names()             # pide los nombres a Neo4j
        self.cat_list.delete(0, "end")
        for i, nombre in enumerate(self._cat_names):
            self.cat_list.insert("end", nombre)
            if nombre in marcadas:
                self.cat_list.selection_set(i)

    # -- CRUD ----------------------------------------------------------------
    @guarded
    def refresh(self):
        """READ: pide los artículos a Neo4j y rellena la tabla (también se usa para buscar)."""
        arts = self.s.articles.list(self.q.get())
        self._rows = {a["id"]: a for a in arts}
        self.tree.delete(*self.tree.get_children())             # vacía la tabla
        for a in arts:
            # iid = a["id"]: el id del artículo identifica la fila (así luego se sabe cuál se eligió)
            self.tree.insert("", "end", iid=a["id"], values=(
                a["title"], a["autor"], ", ".join(a["categorias"]), ", ".join(a["etiquetas"]), a["date"]))
        self._cargar_categorias()

    @guarded
    def crear(self):
        """CREATE: crea un artículo con lo escrito en el formulario; el autor es quien tiene la sesión."""
        self.s.articles.create(autor_email=self.user["email"], **self._datos_form())
        self._limpiar_form()
        self.refresh()
        messagebox.showinfo("Listo", "Artículo creado.", parent=self)

    @guarded
    def actualizar(self):
        """UPDATE: guarda los cambios del formulario en el artículo seleccionado."""
        art = seleccionada(self.tree, self._rows)
        if not art:
            raise ValueError("Selecciona un artículo de la tabla.")
        if not self._puede_modificar(art):
            raise ValueError("Solo puedes modificar tus propios artículos.")
        self.s.articles.update(art["id"], **self._datos_form())
        self.refresh()
        messagebox.showinfo("Listo", "Artículo actualizado.", parent=self)

    @guarded
    def eliminar(self):
        """DELETE: elimina el artículo seleccionado (con confirmación) y sus comentarios."""
        art = seleccionada(self.tree, self._rows)
        if not art:
            raise ValueError("Selecciona un artículo de la tabla.")
        if not self._puede_modificar(art):
            raise ValueError("Solo puedes eliminar tus propios artículos.")
        if messagebox.askyesno("Confirmar", f"¿Eliminar «{art['title']}» y sus comentarios?", parent=self):
            self.s.articles.delete(art["id"])
            self._limpiar_form()
            self.refresh()


# =========================================================================== #
# PESTAÑA: CATEGORÍAS / ETIQUETAS (misma pantalla, distinto servicio)
# =========================================================================== #
class TaxonomyTab(ttk.Frame):
    """Pestaña para categorías o etiquetas. Como ambas son iguales (nombre + url), se usa la misma
    clase dos veces; solo cambia el servicio (``service``) y el texto (``singular``)."""

    def __init__(self, parent, services, user, service, singular: str):
        super().__init__(parent, padding=10)
        self.service, self.singular = service, singular
        self._rows: dict[str, dict] = {}

        self.tree = make_tree(self, [("name", singular.capitalize(), 260), ("url", "URL", 320),
                                     ("articulos", "Artículos", 80)])
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(self)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.name = tk.StringVar()
        fila(form, 0, "Nombre:", ttk.Entry(form, textvariable=self.name))
        ttk.Label(form, text="La URL se genera automáticamente a partir del nombre.",
                  foreground="#666").grid(row=1, column=1, sticky="w")

        button_bar(self, [("Nuevo", self._limpiar), ("Crear", self.crear),
                          ("Actualizar", self.actualizar), ("Eliminar", self.eliminar)])
        self.refresh()

    def _limpiar(self):
        """Vacía el formulario y quita la selección (botón 'Nuevo')."""
        self.tree.selection_remove(*self.tree.selection())
        self.name.set("")

    def _on_select(self, _event=None):
        """Al elegir una fila, copia su nombre al formulario."""
        f = seleccionada(self.tree, self._rows)
        if f:
            self.name.set(f["name"])

    @guarded
    def refresh(self):
        """READ: carga la tabla desde Neo4j (nombre, url y cuántos artículos la usan)."""
        filas = self.service.list()
        self._rows = {f["name"]: f for f in filas}
        self.tree.delete(*self.tree.get_children())
        for f in filas:
            self.tree.insert("", "end", iid=f["name"], values=(f["name"], f["url"], f["articulos"]))

    @guarded
    def crear(self):
        """CREATE: crea una categoría/etiqueta nueva."""
        self.service.create(self.name.get())
        self._limpiar(); self.refresh()

    @guarded
    def actualizar(self):
        """UPDATE: renombra la categoría/etiqueta seleccionada."""
        f = seleccionada(self.tree, self._rows)
        if not f:
            raise ValueError(f"Selecciona {self.singular} de la tabla.")
        self.service.update(f["name"], self.name.get())
        self.refresh()

    @guarded
    def eliminar(self):
        """DELETE: elimina la categoría/etiqueta seleccionada (los artículos no se borran)."""
        f = seleccionada(self.tree, self._rows)
        if not f:
            raise ValueError(f"Selecciona {self.singular} de la tabla.")
        if messagebox.askyesno("Confirmar", f"¿Eliminar «{f['name']}»? Los artículos no se borran.", parent=self):
            self.service.delete(f["name"])
            self._limpiar(); self.refresh()


# =========================================================================== #
# PESTAÑA: COMENTARIOS
# =========================================================================== #
class CommentsTab(ttk.Frame):
    """Pestaña de comentarios, con un filtro para ver los de un solo artículo."""
    TODOS = "(Todos los artículos)"             # opción del filtro para no filtrar

    def __init__(self, parent, services, user):
        super().__init__(parent, padding=10)
        self.s, self.user = services, user
        self._rows: dict[str, dict] = {}
        self._arts: dict[str, str] = {}         # {texto que se ve en la lista: id del artículo}

        # --- Filtro por artículo ---
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Filtrar por artículo:").pack(side="left")
        self.filtro = tk.StringVar(value=self.TODOS)
        self.filtro_combo = ttk.Combobox(barra, textvariable=self.filtro, state="readonly", width=55)
        self.filtro_combo.pack(side="left", padx=6)
        self.filtro_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())   # al elegir, recarga la tabla

        self.tree = make_tree(self, [("articulo", "Artículo", 260), ("autor", "Autor", 150),
                                     ("texto", "Comentario", 380)])
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- Formulario: a qué artículo pertenece + el texto ---
        form = ttk.Frame(self)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.art_sel = tk.StringVar()
        self.art_combo = ttk.Combobox(form, textvariable=self.art_sel, state="readonly")
        fila(form, 0, "Artículo:", self.art_combo)
        self.texto = tk.Text(form, height=4, wrap="word")
        fila(form, 1, "Comentario:", self.texto)

        button_bar(self, [("Nuevo", self._limpiar), ("Crear", self.crear),
                          ("Actualizar", self.actualizar), ("Eliminar", self.eliminar)])
        self.refresh()

    def _limpiar(self):
        """Vacía el texto y quita la selección (botón 'Nuevo')."""
        self.tree.selection_remove(*self.tree.selection())
        self.texto.delete("1.0", "end")

    def _puede_modificar(self, c) -> bool:
        """El admin puede con todo; un autor solo con sus propios comentarios."""
        return self.user["rol"] == "admin" or c["autor"] == self.user["email"]

    def _on_select(self, _event=None):
        """Al elegir un comentario, copia su texto y su artículo al formulario."""
        c = seleccionada(self.tree, self._rows)
        if not c:
            return
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", c["texto"] or "")
        for etiqueta, aid in self._arts.items():            # busca el artículo en la lista desplegable
            if aid == c["article_id"]:
                self.art_sel.set(etiqueta)

    @guarded
    def refresh(self):
        """READ: recarga las listas de artículos y la tabla de comentarios (respetando el filtro)."""
        # Cada opción se ve como "Título  [art-001]"; el diccionario guarda a qué id corresponde
        self._arts = {f"{a['title']}  [{a['id']}]": a["id"] for a in self.s.articles.choices()}
        self.art_combo["values"] = list(self._arts)
        self.filtro_combo["values"] = [self.TODOS] + list(self._arts)
        filtro = self.filtro.get()
        if filtro != self.TODOS and filtro not in self._arts:    # el artículo filtrado ya no existe
            self.filtro.set(self.TODOS); filtro = self.TODOS
        filas = self.s.comments.list(None if filtro == self.TODOS else self._arts[filtro])
        self._rows = {f["id"]: f for f in filas}
        self.tree.delete(*self.tree.get_children())
        for f in filas:
            self.tree.insert("", "end", iid=f["id"], values=(
                f["articulo"], f["autor"], (f["texto"] or "").replace("\n", " ")))

    @guarded
    def crear(self):
        """CREATE: agrega un comentario al artículo elegido, con el usuario de la sesión como autor."""
        if self.art_sel.get() not in self._arts:
            raise ValueError("Elige el artículo que quieres comentar.")
        self.s.comments.create(self._arts[self.art_sel.get()], self.user["email"], self.texto.get("1.0", "end"))
        self._limpiar(); self.refresh()

    @guarded
    def actualizar(self):
        """UPDATE: cambia el texto del comentario seleccionado."""
        c = seleccionada(self.tree, self._rows)
        if not c:
            raise ValueError("Selecciona un comentario de la tabla.")
        if not self._puede_modificar(c):
            raise ValueError("Solo puedes modificar tus propios comentarios.")
        self.s.comments.update(c["id"], self.texto.get("1.0", "end"))
        self.refresh()

    @guarded
    def eliminar(self):
        """DELETE: elimina el comentario seleccionado (con confirmación)."""
        c = seleccionada(self.tree, self._rows)
        if not c:
            raise ValueError("Selecciona un comentario de la tabla.")
        if not self._puede_modificar(c):
            raise ValueError("Solo puedes eliminar tus propios comentarios.")
        if messagebox.askyesno("Confirmar", "¿Eliminar este comentario?", parent=self):
            self.s.comments.delete(c["id"])
            self._limpiar(); self.refresh()


# =========================================================================== #
# PESTAÑA: USUARIOS (solo administradores)
# =========================================================================== #
class UsersTab(ttk.Frame):
    """Pestaña para administrar usuarios: crearlos, cambiar su rol y asignarles contraseña.
    Solo se muestra si el usuario con la sesión abierta es admin."""

    def __init__(self, parent, services, user):
        super().__init__(parent, padding=10)
        self.s, self.user = services, user
        self._rows: dict[str, dict] = {}

        self.tree = make_tree(self, [("email", "Correo", 220), ("name", "Nombre", 200), ("rol", "Rol", 80),
                                     ("acceso", "Puede entrar", 90), ("articulos", "Artículos", 70)])
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(self)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.email, self.name = tk.StringVar(), tk.StringVar()
        self.rol, self.password = tk.StringVar(value="autor"), tk.StringVar()
        self.email_entry = ttk.Entry(form, textvariable=self.email)
        fila(form, 0, "Correo:", self.email_entry)
        fila(form, 1, "Nombre:", ttk.Entry(form, textvariable=self.name))
        fila(form, 2, "Rol:", ttk.Combobox(form, textvariable=self.rol, values=ROLES, state="readonly"))
        fila(form, 3, "Contraseña:", ttk.Entry(form, textvariable=self.password, show="•"))
        ttk.Label(form, foreground="#666",
                  text="Sin contraseña el usuario no puede iniciar sesión. Al editar, déjala vacía para no cambiarla."
                  ).grid(row=4, column=1, sticky="w")

        button_bar(self, [("Nuevo", self._limpiar), ("Crear", self.crear),
                          ("Actualizar", self.actualizar), ("Eliminar", self.eliminar)])
        self.refresh()

    def _limpiar(self):
        """Vacía el formulario y vuelve a habilitar el campo de correo (botón 'Nuevo')."""
        self.tree.selection_remove(*self.tree.selection())
        self.email.set(""); self.name.set(""); self.password.set(""); self.rol.set("autor")
        self.email_entry.state(["!disabled"])

    def _on_select(self, _event=None):
        """Al elegir un usuario, copia sus datos al formulario."""
        f = seleccionada(self.tree, self._rows)
        if f:
            self.email.set(f["email"]); self.name.set(f["name"]); self.rol.set(f["rol"]); self.password.set("")
            self.email_entry.state(["disabled"])        # el correo es la llave del usuario: no se puede renombrar

    @guarded
    def refresh(self):
        """READ: carga la tabla de usuarios desde Neo4j."""
        filas = self.s.users.list()
        self._rows = {f["email"]: f for f in filas}
        self.tree.delete(*self.tree.get_children())
        for f in filas:
            self.tree.insert("", "end", iid=f["email"], values=(
                f["email"], f["name"], f["rol"], "Sí" if f["acceso"] else "No", f["articulos"]))

    @guarded
    def crear(self):
        """CREATE: crea un usuario. Sin contraseña queda 'sin acceso' (solo figura como autor)."""
        self.s.users.create(self.email.get(), self.name.get(), self.password.get(), self.rol.get())
        self._limpiar(); self.refresh()

    @guarded
    def actualizar(self):
        """UPDATE: cambia nombre/rol del usuario seleccionado; la contraseña solo si se escribió una."""
        f = seleccionada(self.tree, self._rows)
        if not f:
            raise ValueError("Selecciona un usuario de la tabla.")
        self.s.users.update(f["email"], self.name.get(), self.rol.get(), self.password.get() or None)
        self.refresh()

    @guarded
    def eliminar(self):
        """DELETE: elimina al usuario seleccionado y los comentarios que escribió."""
        f = seleccionada(self.tree, self._rows)
        if not f:
            raise ValueError("Selecciona un usuario de la tabla.")
        if f["email"] == self.user["email"]:
            raise ValueError("No puedes eliminar tu propio usuario mientras tienes la sesión abierta.")
        if messagebox.askyesno("Confirmar", f"¿Eliminar a «{f['email']}» y los comentarios que escribió?", parent=self):
            self.s.users.delete(f["email"])
            self._limpiar(); self.refresh()


# =========================================================================== #
# VENTANA PRINCIPAL Y ARRANQUE
# =========================================================================== #
class App(tk.Tk):
    """La ventana de la aplicación. Alterna entre dos pantallas: el login y la ventana principal."""

    def __init__(self, db: Neo4jConnection, services: Services):
        super().__init__()
        self.db, self.services = db, services
        self.title("Blog · Neo4j")                          # texto de la barra de título
        try:
            ttk.Style(self).theme_use("clam")               # tema visual más moderno
        except tk.TclError:
            pass                                            # si el tema no existe, usa el de por defecto
        self.show_login()                                   # empieza en la pantalla de login

    def _vaciar(self):
        """Borra todo lo que hay en la ventana para poder dibujar otra pantalla."""
        for hijo in self.winfo_children():
            hijo.destroy()

    def _centrar(self, ancho, alto):
        """Fija el tamaño de la ventana y la coloca centrada en la pantalla."""
        x = (self.winfo_screenwidth() - ancho) // 2
        y = (self.winfo_screenheight() - alto) // 3
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    @guarded
    def show_login(self):
        """Muestra la pantalla de login (también se usa al presionar 'Cerrar sesión')."""
        self._vaciar()
        self.resizable(False, False)                        # el login tiene tamaño fijo
        self._centrar(460, 400)
        # Si nadie tiene contraseña todavía, el login pasa a ser "primera configuración"
        primera_vez = self.services.users.count_with_password() == 0
        LoginFrame(self, self.services, self.show_main, first_run=primera_vez).pack(expand=True)

    def show_main(self, user: dict):
        """Muestra la ventana principal con las pestañas. Se llama cuando el login es correcto."""
        self._vaciar()
        self.resizable(True, True)
        self._centrar(1000, 740)
        self.minsize(880, 620)

        # --- Cabecera: quién tiene la sesión + botón de cerrar sesión ---
        cabecera = ttk.Frame(self, padding=(10, 8))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text=f"Sesión: {user['name']} · {user['email']} ({user['rol']})",
                  font=("Helvetica", 11, "bold")).pack(side="left")
        ttk.Button(cabecera, text="Cerrar sesión", command=self.show_login).pack(side="right")

        # --- Pestañas ---
        s = self.services
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        notebook.add(ArticlesTab(notebook, s, user), text="Artículos")
        notebook.add(TaxonomyTab(notebook, s, user, s.categories, "categoría"), text="Categorías")
        notebook.add(TaxonomyTab(notebook, s, user, s.tags, "etiqueta"), text="Etiquetas")
        notebook.add(CommentsTab(notebook, s, user), text="Comentarios")
        if user["rol"] == "admin":                          # solo el administrador gestiona usuarios
            notebook.add(UsersTab(notebook, s, user), text="Usuarios")

        # Al cambiar de pestaña se recargan sus datos (así, por ejemplo, una categoría recién
        # creada aparece de inmediato en el formulario de artículos)
        notebook.bind("<<NotebookTabChanged>>",
                      lambda _e: notebook.nametowidget(notebook.select()).refresh())
        # Barra inferior: a qué base de datos se está conectado
        ttk.Label(self, text=f"Conectado a {self.db.settings.uri} · base «{self.db.settings.database}»",
                  foreground="#666").pack(side="bottom", anchor="w", padx=10, pady=4)


def conectar(db: Neo4jConnection) -> bool:
    """Conecta a Neo4j y prepara las restricciones. Si falla, deja reintentar.

    Devuelve True si logró conectar, o False si el usuario decide cancelar.
    """
    while True:
        try:
            db.connect()
            db.ensure_schema()
            return True
        except Exception as e:        # credenciales mal, servidor apagado, URI incorrecta...
            if not messagebox.askretrycancel(
                    "No se pudo conectar a Neo4j",
                    f"{type(e).__name__}: {e}\n\n"
                    f"Revisa que Neo4j esté encendido y los datos del archivo:\n{ENV_PATH}"):
                return False


def run():
    """FUNCIÓN PRINCIPAL: es lo que se ejecuta al correr `python src/main.py`."""
    db = Neo4jConnection(load_settings())       # 1) lee el .env y prepara la conexión
    sondeo = tk.Tk()                            # ventana invisible, solo para poder mostrar avisos de error
    sondeo.withdraw()
    conectado = conectar(db)                    # 2) intenta conectar a Neo4j
    sondeo.destroy()
    if not conectado:
        return                                  # el usuario canceló: se cierra sin abrir nada
    try:
        App(db, Services(db)).mainloop()        # 3) abre la ventana; mainloop() la mantiene abierta
    finally:
        db.close()                              # 4) al cerrar la ventana, cierra la conexión


if __name__ == "__main__":      # esto solo se cumple si se ejecuta este archivo directamente
    run()