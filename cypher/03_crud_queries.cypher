// =================================================================
// 03_crud_queries.cypher
// Operaciones CRUD (Create, Read, Update, Delete) para el Blog
// =================================================================

// -----------------------------------------------------------------
// 1. CREATE (Crear nodos y relaciones)
// -----------------------------------------------------------------

// Crear un nuevo usuario
CREATE (u:User {email: 'diego@example.com', name: 'Diego Ramírez'});

// Crear un nuevo artículo con su autor, categoría y etiqueta vinculados
MATCH (u:User {email: 'edgar@example.com'})
MATCH (c:Category {name: 'Bases de Datos'})
MATCH (t:Tag {name: 'Cypher'})
CREATE (a:Article {
    id: 'art-003',
    title: 'Consultas Avanzadas en Cypher',
    date: '2026-11-23',
    text: 'Aprende a realizar recorridos complejos sobre el grafo...'
})
CREATE (u)-[:PUBLICO]->(a)
CREATE (a)-[:PERTENECE_A]->(c)
CREATE (a)-[:TIENE_ETIQUETA]->(t);

// Agregar un nuevo comentario a un artículo y vincularlo con su autor
MATCH (u:User {email: 'diego@example.com'})
MATCH (a:Article {id: 'art-003'})
CREATE (cm:Comment {
    id: 'cmt-104',
    name: 'Gran artículo sobre Cypher',
    url: '/articulos/art-003#cmt-104'
})
CREATE (u)-[:ESCRIBIO]->(cm)
CREATE (a)-[:TIENE_COMENTARIO]->(cm);


// -----------------------------------------------------------------
// 2. READ (Consultas de Lectura)
// -----------------------------------------------------------------

// Consultar un usuario por su correo
MATCH (u:User {email: 'edgar@example.com'})
RETURN u;

// Listar todos los artículos publicados con el nombre de su autor
MATCH (u:User)-[:PUBLICO]->(a:Article)
RETURN u.name AS Autor, a.title AS Titulo, a.date AS Fecha;

// Consultar un artículo específico con todas sus etiquetas y categorías asignadas
MATCH (a:Article {id: 'art-001'})-[:TIENE_ETIQUETA]->(t:Tag)
MATCH (a)-[:PERTENECE_A]->(c:Category)
RETURN a.title AS Titulo,
       collect(DISTINCT t.name) AS Etiquetas,
       collect(DISTINCT c.name) AS Categorias;


// -----------------------------------------------------------------
// 3. UPDATE (Actualizaciones)
// -----------------------------------------------------------------

// Actualizar el título y el texto de un artículo existente
MATCH (a:Article {id: 'art-001'})
SET a.title = 'Introducción Avanzada a Neo4j',
    a.text = 'Texto actualizado del artículo con nuevos detalles técnicos...'
RETURN a;

// Asignar una nueva etiqueta a un artículo existente
MATCH (a:Article {id: 'art-002'})
MERGE (t:Tag {name: 'Docker', url: '/tags/docker'})
MERGE (a)-[:TIENE_ETIQUETA]->(t);


// -----------------------------------------------------------------
// 4. DELETE (Eliminaciones)
// -----------------------------------------------------------------

// Eliminar un comentario específico y sus relaciones asociadas
MATCH (cm:Comment {id: 'cmt-102'})
DETACH DELETE cm;

// Desvincular una etiqueta de un artículo sin borrar el nodo de la etiqueta
MATCH (a:Article {id: 'art-001'})-[r:TIENE_ETIQUETA]->(t:Tag {name: 'NoSQL'})
DELETE r;
