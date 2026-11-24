// =================================================================
// 01_schema_constraints.cypher
// Restricciones de Unicidad e Índices para el Blog en Neo4j
// =================================================================

// -----------------------------------------------------------------
// 1. RESTRICCIONES DE UNICIDAD (Uniqueness Constraints)
// Garantizan la integridad de datos evitando llaves primarias duplicadas
// -----------------------------------------------------------------

// Evita que existan dos usuarios con el mismo correo electrónico
CREATE CONSTRAINT constraint_user_email IF NOT EXISTS
FOR (u:User) REQUIRE u.email IS UNIQUE;

// Asegura un identificador único para cada artículo publicado
CREATE CONSTRAINT constraint_article_id IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;

// Asegura un identificador único para cada comentario del blog
CREATE CONSTRAINT constraint_comment_id IF NOT EXISTS
FOR (c:Comment) REQUIRE c.id IS UNIQUE;

// Evita duplicados en el nombre de las etiquetas (Tags)
CREATE CONSTRAINT constraint_tag_name IF NOT EXISTS
FOR (t:Tag) REQUIRE t.name IS UNIQUE;

// Evita duplicados en el nombre de las categorías
CREATE CONSTRAINT constraint_category_name IF NOT EXISTS
FOR (cat:Category) REQUIRE cat.name IS UNIQUE;


// -----------------------------------------------------------------
// 2. ÍNDICES DE BÚSQUEDA (Range Indexes)
// Optimizan la velocidad de consulta en propiedades frecuentemente filtradas
// -----------------------------------------------------------------

// Índice de búsqueda rápida por el título del artículo
CREATE INDEX index_article_title IF NOT EXISTS
FOR (a:Article) ON (a.title);

// Índice para agilizar ordenamientos y filtros por fecha de publicación
CREATE INDEX index_article_date IF NOT EXISTS
FOR (a:Article) ON (a.date);
