# services/producer/app.py
import os, time, uuid, random, json
from confluent_kafka import Producer
from prometheus_client import start_http_server, Counter, Histogram

TARGET_TPS = int(os.getenv("TARGET_TPS", "500"))
SEED = int(os.getenv("RNG_SEED", "42"))
random.seed(SEED)

messages_sent = Counter("producer_messages_sent_total","Total messages sent")
send_latency = Histogram("producer_send_latency_seconds","Produce latency (s)")
send_errors = Counter("producer_send_errors_total","Produce errors")

conf = {"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP","kafka:9092")}

p = Producer(conf)

def gen():
    is_fraud = random.random() < 0.002
    amount = round(random.lognormvariate(3, 0.8) * (random.uniform(2.5,8) if is_fraud else 1), 2)
    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id": f"user_{random.randint(1,100000)}",
        "merchant_id": f"m_{random.randint(1,5000)}",
        "amount": amount,
        "currency": "USD",
        "timestamp": int(time.time()*1000),
        "device_id": f"dev_{random.randint(1,200000)}",
        "location_lat": 37.77 + random.uniform(-0.1,0.1),
        "location_lon": -122.41 + random.uniform(-0.1,0.1),
        "channel": random.choices(["card_present","ecom","atm"], [0.6,0.35,0.05])[0],
        "is_fraud_label": is_fraud,
        "schema_version": 1
    }

def delivery(err, msg):
    if err:
        send_errors.inc()

def main():
    start_http_server(8001)
    interval = 1.0 / TARGET_TPS
    while True:
        payload = gen()
        start = time.perf_counter()
        p.produce("transactions",
                  key=payload["user_id"],
                  value=json.dumps(payload),
                  callback=delivery)
        p.poll(0)
        send_latency.observe(time.perf_counter() - start)
        messages_sent.inc()
        time.sleep(interval)

if __name__ == "__main__":
    main()