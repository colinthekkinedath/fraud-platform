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

# Phase 2 targets
bootstrap-phase2: build-phase2 up create-bucket setup-connector wait-for-services feast-setup
build-phase2:     ## build phase 2 docker images
	docker compose -f docker-compose.local.yml build producer features-stream

wait-for-services:  ## wait for Redis, MLflow, Airflow to be ready
	@echo "Waiting for services to be ready..."
	@until docker exec fraud-platform-redis-1 redis-cli ping >/dev/null 2>&1; do \
		echo "Waiting for Redis..."; \
		sleep 2; \
	done
	@until curl -s http://localhost:5000/health >/dev/null 2>&1; do \
		echo "Waiting for MLflow..."; \
		sleep 3; \
	done
	@until curl -s http://localhost:8080/health >/dev/null 2>&1; do \
		echo "Waiting for Airflow..."; \
		sleep 3; \
	done
	@echo "All services ready!"

feast-setup:        ## initialize Feast feature store
	docker run --rm --network fraud-platform_default \
		-v $(PWD)/features:/app \
		-w /app \
		python:3.11-slim sh -c "pip install -q feast==0.34.1 && feast apply"

build-features:     ## run offline feature building
	docker run --rm --network fraud-platform_default \
		-v $(PWD)/jobs:/app \
		-w /app \
		python:3.11-slim sh -c "pip install -q -r requirements.txt && python build_offline_features.py"

test-features:      ## test feature store connectivity
	docker run --rm --network fraud-platform_default \
		-v $(PWD)/tools:/app -v $(PWD)/features:/features \
		-w /app \
		python:3.11-slim sh -c "pip install -q feast==0.34.1 redis && python feature_probe.py"

check-ab-headers:   ## check A/B test header distribution
	docker run --rm --network fraud-platform_default \
		-v $(PWD)/tools:/app \
		-w /app \
		python:3.11-slim sh -c "pip install -q kafka-python && python check_headers.py --sample 1000"

trigger-training:   ## manually trigger Airflow training DAG
	curl -X POST "http://localhost:8080/api/v1/dags/fraud_train_register/dagRuns" \
		-H "Content-Type: application/json" \
		-u admin:admin \
		-d '{"conf":{}}'

lint:
	rufflehog --fail || true