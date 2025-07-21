#!/bin/bash

echo "Waiting for Kafka to be ready..."

# Wait for Kafka to be responsive
until docker exec fraud-platform-kafka-1 kafka-topics --bootstrap-server localhost:9092 --list >/dev/null 2>&1; do
  echo "Kafka is not ready yet, waiting..."
  sleep 2
done

# Create the transactions topic if it doesn't exist
echo "Creating transactions topic..."
docker exec fraud-platform-kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic transactions --partitions 3 --replication-factor 1 --if-not-exists

echo "Kafka is ready!"