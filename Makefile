bootstrap-local: build up wait-topics seed
build:          ## build local docker images
	docker compose -f docker-compose.local.yml build
up:             ## start local stack
	docker compose -f docker-compose.local.yml up -d
down:
	docker compose -f docker-compose.local.yml down -v
wait-topics:
	./scripts/wait_for_kafka.sh
seed:
	python services/producer/seed_once.py
lint:
	rufflehog --fail || true