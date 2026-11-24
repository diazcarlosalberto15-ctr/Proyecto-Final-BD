// =================================================================
// 04_graph_traversals.cypher
// Consultas avanzadas de recorrido entre relaciones del Grafo
// =================================================================

// 1. Recorrido de Comentarios y Autores
// Obtener los comentarios de un artículo junto con los datos del usuario que los redactó
MATCH (a:Article {id: 'art-001'})-[:TIENE_COMENTARIO]->(cm:Comment)<-[:ESCRIBIO]-(u:User)
RETURN a.title AS Articulo,
       cm.name AS Comentario,
       u.name AS AutorComentario,
       u.email AS EmailAutor;


// 2. Recomendación por Coincidencia de Etiquetas (Multihop)
// Buscar artículos recomendados que compartan etiquetas con un artículo dado
MATCH (a1:Article {id: 'art-001'})-[:TIENE_ETIQUETA]->(t:Tag)<-[:TIENE_ETIQUETA]-(a2:Article)
WHERE a1 <> a2
RETURN a2.title AS ArticuloRecomendado,
       count(t) AS EtiquetasEnComun,
       collect(t.name) AS Etiquetas
ORDER BY EtiquetasEnComun DESC;


// 3. Historial Completo de Actividad de un Usuario
// Obtener los artículos que ha publicado un usuario y los comentarios que ha realizado en otros artículos
MATCH (u:User {email: 'edgar@example.com'})
OPTIONAL MATCH (u)-[:PUBLICO]->(a:Article)
OPTIONAL MATCH (u)-[:ESCRIBIO]->(cm:Comment)<-[:TIENE_COMENTARIO]-(artComentado:Article)
RETURN u.name AS Usuario,
       collect(DISTINCT a.title) AS ArticulosPublicados,
       collect(DISTINCT {comentario: cm.name, articulo: artComentado.title}) AS ComentariosRealizados;


// 4. Filtrado Cruzado por Categoría y Etiqueta
// Encontrar artículos que pertenezcan a una categoría específica y tengan una etiqueta concreta, listando a su autor
MATCH (cat:Category {name: 'Tecnología'})<-[:PERTENECE_A]-(a:Article)-[:TIENE_ETIQUETA]->(t:Tag {name: 'Neo4j'})
MATCH (u:User)-[:PUBLICO]->(a)
RETURN a.title AS Titulo,
       a.date AS FechaPublicacion,
       u.name AS Autor;
