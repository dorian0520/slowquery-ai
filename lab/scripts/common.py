"""실습 공통 설정: 접속 정보(로컬 실습 전용)와 DB 연결."""
import os
import pymysql

CLUSTERS = {
    "shop-db": {"host": "127.0.0.1", "port": 3306},
    "order-db": {"host": "127.0.0.1", "port": 3307},
}
STORE = "shop-db"  # dba 저장소가 있는 DB


def connect(cluster, user=None, password=None, db=None):
    c = CLUSTERS[cluster]
    return pymysql.connect(
        host=c["host"], port=c["port"],
        user=user or os.environ.get("LAB_USER", "lab_collector"),
        password=password or os.environ.get("LAB_PASSWORD", "lab-collector-pw"),
        database=db, autocommit=True, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
