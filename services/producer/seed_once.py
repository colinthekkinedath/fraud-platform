#!/usr/bin/env python3
# Simple one-time seed script for initial data
import os, json, uuid, random, time
from kafka import KafkaProducer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC = "transactions"
NUM_MESSAGES = 100

print(f"Seeding {NUM_MESSAGES} messages to topic '{TOPIC}'...")

producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP],
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    key_serializer=lambda k: str(k).encode('utf-8')
)

def generate_transaction():
    user_id = random.randint(1, 1000)
    is_fraud = random.random() < 0.002
    amount = round(random.lognormvariate(3, 0.8) * (random.uniform(2.5,8) if is_fraud else 1), 2)
    
    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id": user_id,
        "merchant_id": f"merchant_{random.randint(1, 500)}",
        "amount": amount,
        "currency": "USD",
        "timestamp": int(time.time() * 1000),
        "location_lat": round(random.uniform(25.0, 49.0), 6),
        "location_lon": round(random.uniform(-125.0, -66.0), 6),
        "channel": random.choice(["card_present", "ecom", "atm"]),
        "device_id": f"device_{random.randint(1, 10000)}",
        "is_fraud_label": is_fraud,
        "schema_version": "v1"
    }

try:
    for i in range(NUM_MESSAGES):
        transaction = generate_transaction()
        key = str(transaction["user_id"])
        
        producer.send(TOPIC, key=key, value=transaction)
        
        if i % 20 == 0:
            print(f"Sent {i + 1}/{NUM_MESSAGES} messages...")
    
    producer.flush()
    print(f"Successfully sent {NUM_MESSAGES} seed transactions!")
    
except Exception as e:
    print(f"Error seeding data: {e}")
    exit(1)