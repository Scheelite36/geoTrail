from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import psycopg2
from psycopg2.extras import RealDictCursor

QDRANT_HOST = "qdrant"
QDRANT_PORT = 6333
COLLECTION_NAME = "geo_documents"

DB_CONFIG = {
    "host": "geo-postgres",
    "port": 5432,
    "dbname": "geology",
    "user": "geo",
    "password": "geo123",
}


def main():
    print("Loading model...")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    print("Connecting to Qdrant...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    vector_size = model.get_sentence_embedding_dimension()
    print(f"Vector dimension: {vector_size}")

    if client.collection_exists(COLLECTION_NAME):
        print("Collection exists, recreating...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorsConfig(
            size=vector_size, distance=models.Distance.COSINE
        ),
    )
    print("Collection created.")

    print("Loading geo documents from PostGIS...")
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT id, title, doc_type, mine_area, content FROM geo_document")
    docs = cur.fetchall()
    cur.close()
    conn.close()
    print(f"Loaded {len(docs)} documents.")

    print("Encoding and uploading vectors...")
    points = []
    for doc in docs:
        text = f"{doc['title']} {doc['content']}"
        vector = model.encode(text).tolist()
        points.append(
            models.PointStruct(
                id=doc["id"],
                vector=vector,
                payload={
                    "title": doc["title"],
                    "doc_type": doc["doc_type"],
                    "mine_area": doc["mine_area"],
                    "content": doc["content"][:200],
                },
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Uploaded {len(points)} vectors to Qdrant.")

    test_queries = ["宜春锂矿成矿条件", "钽铌矿蚀变特征", "花桥矿区储量"]
    for q in test_queries:
        qv = model.encode(q).tolist()
        results = client.search(
            collection_name=COLLECTION_NAME, query_vector=qv, limit=2
        )
        print(f"\nQuery: '{q}'")
        for r in results:
            print(f"  -> {r.payload['title']} (score={r.score:.3f})")

    print("\nDone! Vector search is ready.")


if __name__ == "__main__":
    main()
