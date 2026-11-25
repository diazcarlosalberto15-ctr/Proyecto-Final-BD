# Proyecto Final DB - Blog con Neo4j

Aplicación de escritorio para administrar la información de un blog mediante una base de datos de grafos en **Neo4j** y una interfaz desarrollada en **Python**.

## Integrantes

- Emilio Gallardo Medrano - 385530
- Carlos Alberto Díaz Sánchez - 385539
- Edgar Alejandro Gutierrez Carrillo - 385655

**Materia:** Bases de Datos Avanzadas  
**Grupo:** 5K2  
**Universidad:** UACH

## Descripción

El proyecto representa un blog utilizando nodos y relaciones. La aplicación permite administrar artículos, categorías, etiquetas, comentarios y usuarios. La información se almacena en Neo4j y se consulta mediante Cypher desde Python.

## Tecnologías

- Python
- Neo4j Desktop
- Cypher
- Driver oficial de Neo4j para Python (`neo4j`)
- `python-dotenv` para leer la configuración local
- Tkinter para la interfaz gráfica

## Estructura del proyecto

```text
Proyecto-Final-BD/
├── src/
│   ├── main.py            # Interfaz gráfica y flujo de la aplicación
│   └── blog_db.py         # Conexión, consultas y servicios de datos
├── cypher/
│   ├── 01_schema_constraints.cypher
│   ├── 02_seed_data.cypher
│   ├── 03_crud_queries.cypher
│   └── 04_graph_traversals.cypher
├── docs/
│   ├── Evidencia bases de datos neo/
│   └── Reporte_Final_Blog.pdf
├── requirements.txt
├── .gitignore
└── README.md
```

## Modelo de datos

El grafo utiliza los siguientes tipos de nodos:

| Nodo | Información principal |
|---|---|
| `User` | Correo, nombre y datos de acceso/rol gestionados por la aplicación |
| `Article` | Identificador, título, fecha y contenido |
| `Category` | Nombre y URL de la categoría |
| `Tag` | Nombre y URL de la etiqueta |
| `Comment` | Identificador, texto y URL del comentario |

Las relaciones del modelo son:

- `(User)-[:PUBLICO]->(Article)`
- `(Article)-[:PERTENECE_A]->(Category)`
- `(Article)-[:TIENE_ETIQUETA]->(Tag)`
- `(Article)-[:TIENE_COMENTARIO]->(Comment)`
- `(User)-[:ESCRIBIO]->(Comment)`

Un artículo puede estar relacionado con varias categorías y etiquetas. También puede tener varios comentarios, y cada comentario se relaciona con el usuario que lo escribió.

## Funciones de la aplicación

- Inicio de sesión y configuración inicial del administrador.
- Consulta, creación, actualización y eliminación de artículos.
- Administración de categorías y etiquetas.
- Consulta y administración de comentarios.
- Administración de usuarios y roles desde la sesión de administrador.
- Búsqueda de artículos por título o contenido.
- Control de permisos: el administrador puede gestionar los registros; un autor puede modificar sus propios artículos y comentarios.

## Requisitos

- Python 3.10 o posterior.
- Neo4j Desktop instalado.
- Una instancia local de Neo4j iniciada.
- El puerto Bolt de Neo4j disponible (por defecto, `7687`).

## Configuración e instalación en Windows

### 1. Iniciar Neo4j

1. Abre Neo4j Desktop.
2. Inicia la instancia local que utilizará el proyecto.
3. Comprueba que el estado sea **Running**.
4. Ten a la mano el usuario y la contraseña configurados para esa instancia.

La configuración de ejemplo utiliza `neo4j://127.0.0.1:7687` y la base de datos `neo4j`. Si tu instancia utiliza otros datos, actualiza el archivo `.env` para que coincida.

### 2. Crear el archivo `.env`

Crea un archivo llamado `.env` en la carpeta principal del proyecto, al mismo nivel que `requirements.txt`, y agrega tus datos locales:

```env
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=TU_CONTRASENA_DE_NEO4J
NEO4J_DATABASE=neo4j
```

Reemplaza `TU_CONTRASENA_DE_NEO4J` por la contraseña que configuraste en Neo4j Desktop. No compartas este archivo ni lo subas al repositorio. La regla `.env` ya está incluida en `.gitignore`.

### 3. Crear el entorno virtual e instalar dependencias

Abre la carpeta del proyecto en Visual Studio Code. En **Terminal > New Terminal**, ejecuta los siguientes comandos de PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno virtual, ejecuta lo siguiente en esa misma terminal y vuelve a activar el entorno:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. Preparar la base de datos

En Neo4j Desktop, abre **Query** y ejecuta los archivos de la carpeta `cypher` en este orden:

1. `01_schema_constraints.cypher`
2. `02_seed_data.cypher`

El primer archivo crea restricciones e índices. El segundo agrega los datos iniciales de ejemplo.

**Importante:** `02_seed_data.cypher` utiliza instrucciones `CREATE`; ejecútalo una sola vez sobre una base vacía. Si ya cargaste los datos, no lo vuelvas a ejecutar para evitar duplicados.

Los archivos `03_crud_queries.cypher` y `04_graph_traversals.cypher` contienen consultas de ejemplo para operaciones CRUD y recorridos del grafo. Revisa cada sentencia de `03_crud_queries.cypher` antes de ejecutarla, ya que incluye operaciones que crean, actualizan y eliminan datos. Las consultas de `04_graph_traversals.cypher` son de lectura.

### 5. Ejecutar la aplicación

Con Neo4j encendido y el entorno virtual activo, ejecuta desde la carpeta principal:

```powershell
python src/main.py
```

La aplicación se conecta a Neo4j utilizando los valores del archivo `.env`. En la primera ejecución, si todavía no existe un usuario con contraseña, aparecerá la pantalla para configurar el administrador. Después se mostrará la ventana principal con las pestañas disponibles.

## Archivos principales

- **`src/main.py`**: interfaz gráfica, inicio de sesión, pestañas y acciones de usuario.
- **`src/blog_db.py`**: configuración, conexión con Neo4j, ejecución de consultas Cypher, servicios CRUD y validaciones.
- **`cypher/01_schema_constraints.cypher`**: restricciones de unicidad e índices.
- **`cypher/02_seed_data.cypher`**: datos iniciales del blog.
- **`cypher/03_crud_queries.cypher`**: ejemplos de creación, lectura, actualización y eliminación.
- **`cypher/04_graph_traversals.cypher`**: consultas de relaciones, recomendaciones y actividad de usuarios.

## Seguridad y datos de acceso

- Las credenciales de conexión se leen desde `.env`, no se escriben directamente en el código.
- Las consultas de la aplicación utilizan parámetros de Cypher para separar los datos introducidos por el usuario de las instrucciones de consulta.
- Las contraseñas de acceso a la aplicación se almacenan como hash con sal, no como texto plano.
- `.env`, `.venv/` y archivos de caché de Python se excluyen mediante `.gitignore`.

## Evidencias y reporte

La carpeta `docs/Evidencia bases de datos neo/` reúne capturas de Neo4j Desktop, del grafo, de la interfaz y un video de pruebas CRUD. El reporte final se encuentra en `docs/Reporte_Final_Blog.pdf`.
