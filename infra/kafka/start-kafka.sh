#!/bin/sh
set -eu

ready_file=/tmp/utask-kafka-ready
rm -f "$ready_file"
kafka_pid=
preparation_pid=
cleanup() {
  status=$?
  trap - EXIT TERM INT
  rm -f "$ready_file"
  if [ -n "$preparation_pid" ]; then
    kill -TERM "$preparation_pid" 2>/dev/null || :
    wait "$preparation_pid" 2>/dev/null || :
  fi
  if [ -n "$kafka_pid" ]; then
    kill -TERM "$kafka_pid" 2>/dev/null || :
    wait "$kafka_pid" 2>/dev/null || :
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

/etc/kafka/docker/run &
kafka_pid=$!
attempt=0
until timeout 5 /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1; do
  if ! kill -0 "$kafka_pid" 2>/dev/null; then
    wait "$kafka_pid" && exit 1 || exit "$?"
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 10 ]; then
    echo 'Kafka did not become ready for topic preparation.' >&2
    exit 1
  fi
  sleep 1
done

for topic in "$WORK_KAFKA_TOPIC" "$CLASSROOM_KAFKA_TOPIC" "$CLASSROOM_WORK_KAFKA_DLQ_TOPIC" "$WORK_CLASSROOM_KAFKA_DLQ_TOPIC" "${WORK_IDENTITY_KAFKA_TOPIC:-utask.identity.events}" utask.work.profile.dlq utask.integration.events "${WORK_INTEGRATION_DLQ_TOPIC:-utask.work.integration.dlq}"; do
  timeout 15 /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --create --if-not-exists --partitions 1 --replication-factor 1 --topic "$topic" &
  preparation_pid=$!
  wait "$preparation_pid"
  preparation_pid=
done
kill -0 "$kafka_pid"
touch "$ready_file"
wait "$kafka_pid"
