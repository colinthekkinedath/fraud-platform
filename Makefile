bootstrap-local: up wait-topics seed
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