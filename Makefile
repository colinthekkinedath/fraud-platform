bootstrap-local: build up wait-topics create-bucket setup-connector seed
build:          ## build local docker images
	docker compose -f docker-compose.local.yml build
up:             ## start local stack
	docker compose -f docker-compose.local.yml up -d
down:
	docker compose -f docker-compose.local.yml down -v
wait-topics:
	./scripts/wait_for_kafka.sh
create-bucket:   ## create s3 bucket in minio
	@echo "Creating S3 bucket..."
	@until docker exec fraud-platform-minio-1 mc config host add local http://localhost:9000 admin password123 >/dev/null 2>&1; do \
		echo "Waiting for MinIO to be ready..."; \
		sleep 2; \
	done
	docker exec fraud-platform-minio-1 mc mb local/fraud-raw --ignore-existing
setup-connector:  ## setup kafka connect s3 sink
	@echo "Setting up Kafka Connect S3 sink..."
	@until curl -s http://localhost:8083/connectors | grep -q '\[\]' >/dev/null 2>&1; do \
		echo "Waiting for Kafka Connect to be ready..."; \
		sleep 3; \
	done
	curl -X POST -H "Content-Type: application/json" -d @working-confluent-config.json http://localhost:8083/connectors
seed:
	docker run --rm --network fraud-platform_default -v $(PWD)/services/producer:/app -w /app python:3.12-slim sh -c "pip install -q kafka-python && python seed_once.py"
lint:
	rufflehog --fail || true