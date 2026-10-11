"""用 fastembed (ONNX) 生成真实 embedding 并写入 Qdrant - 含江西各地矿床扩展数据"""

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "geo_documents"

DOCUMENTS = [
    {
        "id": 1,
        "title": "宜春钽铌矿床地质特征及成矿规律研究",
        "doc_type": "研究报告",
        "mine_area": "宜春钽铌矿",
        "content": "宜春钽铌矿位于江西省宜春市，是世界最大的钽铌矿床之一。矿床产于燕山期花岗伟晶岩中，主要矿物为锂云母、铌铁矿、钽铁矿。钠长石化和云英岩化是主要蚀变类型，锂云母含量与钠长石化程度正相关。",
    },
    {
        "id": 2,
        "title": "花桥锂矿资源储量核实报告",
        "doc_type": "储量报告",
        "mine_area": "花桥锂矿",
        "content": "花桥锂矿位于宜春市袁州区花桥镇，矿体赋存于花岗伟晶岩脉中。Li2O平均品位1.2%，探明资源量超50万吨。矿体走向北东，倾向南东，倾角30-45度。主要工业矿物为锂云母，伴生铌钽可综合回收。",
    },
    {
        "id": 3,
        "title": "九岭地区锂矿成矿预测与靶区圈定",
        "doc_type": "科研论文",
        "mine_area": "九岭锂矿",
        "content": "九岭地区位于宜春市西北部，是近年来新发现的锂矿集中区。成矿与燕山期花岗岩侵入活动密切相关，花岗伟晶岩型锂矿为主要矿床类型。通过化探异常圈定和遥感解译，预测了3处找矿靶区，其中2处已验证见矿。",
    },
    {
        "id": 4,
        "title": "赣南钨矿成矿规律与找矿方向",
        "doc_type": "科研论文",
        "mine_area": "赣南地区",
        "content": "赣南地区是中国最重要的钨矿集中区，以石英脉型黑钨矿为主。成矿与燕山期花岗岩关系密切，云英岩化和硅化是主要蚀变。钨矿脉常伴生锡、铋、钼等矿产。找矿标志包括云英岩化带、石英脉群和地球化学W-Sn-Bi组合异常。",
    },
    {
        "id": 5,
        "title": "锂云母提取碳酸锂工艺研究",
        "doc_type": "技术报告",
        "mine_area": "宜春地区",
        "content": "锂云母是宜春地区锂资源的主要赋存形式。硫酸盐焙烧法是目前最成熟的锂云母提锂工艺，锂回收率可达85%以上。工艺流程包括：矿石破碎→焙烧→浸出→净化→沉锂。钠长石化蚀变程度直接影响锂云母品位和提锂效率。",
    },
    {
        "id": 6,
        "title": "江西铌钽矿床类型及分布特征",
        "doc_type": "综述报告",
        "mine_area": "江西省",
        "content": "江西省铌钽矿床主要分布在宜春、赣州等地，以花岗伟晶岩型和花岗岩风化壳型为主。宜春钽铌矿是国内最大的钽矿产地，铌钽矿物主要为铌铁矿-钽铁矿系列。矿石中铌钽品位与钠长石化程度正相关，强钠长石化带铌钽品位最高。",
    },
    # === 江西各地矿床扩展数据 ===
    {
        "id": 7,
        "title": "德兴斑岩铜矿田地质特征及成矿模式",
        "doc_type": "研究报告",
        "mine_area": "德兴铜矿",
        "content": "德兴铜矿田由铜厂、富家坞、朱砂红三个大型斑岩铜矿床组成，铜金属储量900万吨，伴生金215吨，伴生钼30万吨。矿体赋存于花岗闪长斑岩与千枚岩接触带，矿石平均含Cu0.45%、Au0.2g/t。围岩蚀变呈同心环状分带：钾化带→石英绢英岩化带→青磐岩化带。成矿时代170Ma，与燕山期花岗闪长斑岩侵入密切相关。",
    },
    {
        "id": 8,
        "title": "大余西华山钨矿床地质特征",
        "doc_type": "勘查报告",
        "mine_area": "大余西华山钨矿",
        "content": "西华山钨矿是中国首个发现的钨矿床(1907年)，曾是世界最大钨矿产地，有世界钨都之称。矿床类型为石英脉型黑钨矿，赋存于燕山期花岗岩与寒武系浅变质岩接触带。主要矿物为黑钨矿，伴生锡、铋、钼、铍、铌钽等。成矿深度4-5km，属典型内生热液矿床。目前保有储量不足，已进入资源枯竭阶段。",
    },
    {
        "id": 9,
        "title": "贵溪冷水坑银多金属矿田地质特征",
        "doc_type": "储量报告",
        "mine_area": "贵溪冷水坑银矿",
        "content": "冷水坑矿田是亚洲规模最大的银矿产地，探明银储量9400吨、铅152.83万吨、锌218.82万吨。矿田由银路岭、鲍家、银珠山等斑岩型矿床和下鲍家层控叠生型矿床组成。围岩蚀变有绿泥石化、黄铁绢英岩化、绢云母化和硅化。矿石类型以辉银矿-方铅矿-闪锌矿组合为主。",
    },
    {
        "id": 10,
        "title": "龙南离子吸附型重稀土矿床特征",
        "doc_type": "科研论文",
        "mine_area": "龙南稀土矿",
        "content": "龙南稀土矿是世界上规模最大的离子吸附型重稀土矿床，钇族稀土探明储量占全国第一位。矿床类型为花岗岩风化壳离子吸附型，具有易开采、易提取、放射比度低的优点。矿床主要赋存于燕山期花岗岩风化壳中，重稀土元素(Y、Dy、Ho、Er等)在风化过程中被粘土矿物吸附富集。中东有石油，中国有稀土，稀土在赣南。",
    },
    {
        "id": 11,
        "title": "浮梁朱溪超大型钨矿发现及意义",
        "doc_type": "科研论文",
        "mine_area": "浮梁朱溪钨矿",
        "content": "2016年浮梁朱溪外围探明三氧化钨资源量286万吨，成为新的世界最大钨矿，资源量是大湖塘钨矿的2.7倍。后续勘查新增57.85万吨，总资源量达344.33万吨。矿床类型以矽卡岩型白钨矿为主，伴生铜22.5万吨、银1165吨。主矿体沿走向和倾向均未控制至边界，深部资源潜力巨大。",
    },
    {
        "id": 12,
        "title": "德兴金山金矿田地质特征",
        "doc_type": "勘查报告",
        "mine_area": "德兴金山金矿",
        "content": "金山金矿田是江南规模最大的黄金产地，探明金资源储量202.5吨。矿田由金山特大型金矿、西蒋大型金矿、石坞大型金矿等十余处矿床组成。矿床类型为造山型金矿，矿体赋存于新元古代双桥山群浅变质岩中的韧性剪切带。成矿时代约840Ma，成矿流体为富CO2变质流体。金平均品位5.7g/t，最高可达数十g/t。",
    },
    {
        "id": 13,
        "title": "武宁大湖塘钨矿田地质特征",
        "doc_type": "勘查报告",
        "mine_area": "武宁大湖塘钨矿",
        "content": "2012年大湖塘发现当时世界上最大的钨矿床，钨资源储量约百万吨。矿床位于赣西北九岭成矿亚带，矿床类型以细脉浸染型白钨矿为主，与燕山期花岗岩关系密切。矿体赋存于花岗闪长斑岩与元古界变质砂岩接触带，WO3平均品位0.26%。深部资源潜力巨大，是赣北钨矿三足鼎立格局的重要支柱。",
    },
]


def main():
    print("Loading BAAI/bge-small-zh-v1.5 embedding model (fastembed/ONNX)...")
    model = TextEmbedding("BAAI/bge-small-zh-v1.5")

    dim = None
    test_emb = list(model.embed(["test"]))
    dim = len(test_emb[0])
    print(f"  Model loaded. Vector dimension: {dim}")

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, prefer_grpc=True)

    print("Creating Qdrant collection...")
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=dim,
            distance=models.Distance.COSINE,
        ),
    )
    print("  Collection created")

    print(f"Encoding {len(DOCUMENTS)} documents...")

    texts = [f"{doc['title']} {doc['content']}" for doc in DOCUMENTS]
    vectors = list(model.embed(texts))
    print(f"  Encoded {len(vectors)} vectors")

    print("Uploading to Qdrant...")
    points = []
    for i, doc in enumerate(DOCUMENTS):
        points.append(
            models.PointStruct(
                id=doc["id"],
                vector=vectors[i].tolist(),
                payload={
                    "title": doc["title"],
                    "doc_type": doc["doc_type"],
                    "mine_area": doc["mine_area"],
                    "content": doc["content"][:200],
                },
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"  Uploaded {len(points)} vectors")

    print("\nVerification - test semantic searches:")
    test_queries = [
        "宜春锂矿成矿条件",
        "怎么从锂云母里提锂",
        "钨矿找矿标志",
        "铌钽矿品位影响因素",
        "江西最大的铜矿在哪里",
        "稀土矿是什么类型",
        "世界最大钨矿",
    ]
    for q in test_queries:
        qv = list(model.embed([q]))[0].tolist()
        results = client.search(
            collection_name=COLLECTION_NAME, query_vector=qv, limit=3
        )
        print(f"\n  Q: '{q}'")
        for r in results:
            print(f"    -> {r.payload['title']} (score={r.score:.4f})")

    info = client.get_collection(COLLECTION_NAME)
    print(f"\nTotal points in Qdrant: {info.points_count}")
    print("Done! Semantic search is ready with real embeddings.")


if __name__ == "__main__":
    main()
