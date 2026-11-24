CREATE (c1:Category {name: 'Tecnología', url: '/categorias/tecnologia'})
CREATE (c2:Category {name: 'Bases de Datos', url: '/categorias/bases-de-datos'})
CREATE (c3:Category {name: 'Programación', url: '/categorias/programacion'})

CREATE (t1:Tag {name: 'Neo4j', url: '/tags/neo4j'})
CREATE (t2:Tag {name: 'Python', url: '/tags/python'})
CREATE (t3:Tag {name: 'NoSQL', url: '/tags/nosql'})
CREATE (t4:Tag {name: 'Cypher', url: '/tags/cypher'})

CREATE (u1:User {email: 'edgar@example.com', name: 'Edgar Gutiérrez'})
CREATE (u2:User {email: 'carlos@example.com', name: 'Carlos Díaz'})
CREATE (u3:User {email: 'emilio@example.com', name: 'Emilio Gallardo'})

CREATE (a1:Article {id: 'art-001', title: 'Introducción a Bases de Datos de Grafos con Neo4j', date: '2026-11-20', text: 'Las bases de datos de grafos...'})
CREATE (a2:Article {id: 'art-002', title: 'Integración de Python con Neo4j Drivers', date: '2026-11-22', text: 'En este artículo exploramos...'})

CREATE (cm1:Comment {id: 'cmt-101', name: 'Excelente explicación', url: '/articulos/art-001#cmt-101'})
CREATE (cm2:Comment {id: 'cmt-102', name: '¿Cómo afecta el rendimiento?', url: '/articulos/art-001#cmt-102'})
CREATE (cm3:Comment {id: 'cmt-103', name: 'Muy útil el código', url: '/articulos/art-002#cmt-103'})

CREATE (u1)-[:PUBLICO]->(a1)
CREATE (u2)-[:PUBLICO]->(a2)

CREATE (a1)-[:PERTENECE_A]->(c1)
CREATE (a1)-[:PERTENECE_A]->(c2)
CREATE (a2)-[:PERTENECE_A]->(c1)
CREATE (a2)-[:PERTENECE_A]->(c3)

CREATE (a1)-[:TIENE_ETIQUETA]->(t1)
CREATE (a1)-[:TIENE_ETIQUETA]->(t3)
CREATE (a1)-[:TIENE_ETIQUETA]->(t4)
CREATE (a2)-[:TIENE_ETIQUETA]->(t1)
CREATE (a2)-[:TIENE_ETIQUETA]->(t2)

CREATE (a1)-[:TIENE_COMENTARIO]->(cm1)
CREATE (u2)-[:ESCRIBIO]->(cm1)

CREATE (a1)-[:TIENE_COMENTARIO]->(cm2)
CREATE (u3)-[:ESCRIBIO]->(cm2)

CREATE (a2)-[:TIENE_COMENTARIO]->(cm3)
CREATE (u1)-[:ESCRIBIO]->(cm3);
