#!/bin/bash
# Docker 없이 Homebrew MySQL 8.0 두 대 + Grafana 로 실습 환경 띄우기
# 사용: ./native.sh up | down
set -euo pipefail
LAB="$(cd "$(dirname "$0")" && pwd)"
BREW=$(brew --prefix)                 # Apple Silicon /opt/homebrew · Intel /usr/local
MYSQL=$BREW/opt/mysql@8.0/bin
[ -x "$MYSQL/mysqld" ] || { echo "mysql@8.0 이 없습니다 → brew install mysql@8.0 grafana"; exit 1; }
DATA="$LAB/.data"

start_db() {  # name port
  local name=$1 port=$2 dir="$DATA/$1"
  if [ ! -d "$dir/mysql" ]; then
    mkdir -p "$dir"
    "$MYSQL/mysqld" --no-defaults --initialize-insecure --datadir="$dir" --user="$(whoami)" >/dev/null 2>&1
    local fresh=1
  fi
  "$MYSQL/mysqld" --no-defaults --datadir="$dir" --port="$port" --socket="/tmp/lab-$name.sock" \
    --mysqlx=OFF --pid-file="$dir/mysqld.pid" --log-error="$dir/error.log" \
    --slow-query-log=1 --long-query-time=0.5 --slow-query-log-file="$dir/slow.log" \
    --performance-schema=ON --performance-schema-consumer-events-statements-history-long=ON \
    --event-scheduler=ON --innodb-buffer-pool-size=512M --bind-address=127.0.0.1 &
  for i in $(seq 1 60); do "$MYSQL/mysqladmin" --socket="/tmp/lab-$name.sock" -uroot ping >/dev/null 2>&1 && break; sleep 1; done
  if [ "${fresh:-0}" = 1 ]; then
    echo "[$name] 초기 데이터 적재 중 (주문 200만 건, 1~3분)"
    for f in "$LAB"/mysql/init/*.sql; do "$MYSQL/mysql" --default-character-set=utf8mb4 --socket="/tmp/lab-$name.sock" -uroot < "$f"; done
    "$MYSQL/mysql" --socket="/tmp/lab-$name.sock" -uroot -e \
      "ALTER USER 'root'@'localhost' IDENTIFIED BY 'lab-root-pw'; CREATE USER 'root'@'127.0.0.1' IDENTIFIED BY 'lab-root-pw'; GRANT ALL ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;"
  fi
  echo "[$name] 127.0.0.1:$port 준비 완료"
}

case "${1:-up}" in
  up)
    start_db shop-db 3306
    start_db order-db 3307
    mkdir -p "$DATA/grafana/prov/datasources" "$DATA/grafana/prov/dashboards"
    sed 's#shop-db:3306#127.0.0.1:3306#' "$LAB/grafana/provisioning/datasources/mysql.yml" > "$DATA/grafana/prov/datasources/mysql.yml"
    sed "s#/var/lib/grafana/dashboards#$LAB/grafana/dashboards#" "$LAB/grafana/provisioning/dashboards/lab.yml" > "$DATA/grafana/prov/dashboards/lab.yml"
    GF_PATHS_PROVISIONING="$DATA/grafana/prov" GF_PATHS_DATA="$DATA/grafana/data" GF_PATHS_LOGS="$DATA/grafana/logs" \
    GF_AUTH_ANONYMOUS_ENABLED=true GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer GF_SERVER_HTTP_ADDR=127.0.0.1 \
      $BREW/opt/grafana/bin/grafana server --homepath $BREW/opt/grafana/share/grafana \
      > "$DATA/grafana.out" 2>&1 &
    echo "Grafana http://127.0.0.1:3000"
    ;;
  down)
    for n in shop-db order-db; do
      [ -f "$DATA/$n/mysqld.pid" ] && "$MYSQL/mysqladmin" --socket="/tmp/lab-$n.sock" -uroot -plab-root-pw shutdown 2>/dev/null || true
    done
    pkill -f "grafana server --homepath $BREW/opt/grafana" || true
    ;;
esac
