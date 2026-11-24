// 01_schema_constraints.cypher
CREATE CONSTRAINT constraint_user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE;
CREATE CONSTRAINT constraint_article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT constraint_comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT constraint_tag_name IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT constraint_category_name IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE;

CREATE INDEX index_article_title IF NOT EXISTS FOR (a:Article) ON (a.title);
CREATE INDEX index_article_date IF NOT EXISTS FOR (a:Article) ON (a.date);
