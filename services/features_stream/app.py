#!/usr/bin/env python3
"""
Streaming Velocity/Session Features with Faust
Phase 2 - Step 4

Consumes transaction stream and maintains real-time features in Redis
"""
import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import logging

import faust
import redis.asyncio as redis
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8002"))

# Prometheus metrics
messages_processed = Counter("features_stream_messages_processed_total", "Total messages processed")
processing_latency = Histogram("features_stream_processing_latency_seconds", "Processing latency")
redis_writes = Counter("features_stream_redis_writes_total", "Total Redis writes")
redis_errors = Counter("features_stream_redis_errors_total", "Total Redis errors")
active_sessions = Gauge("features_stream_active_sessions", "Number of active user sessions")

# Faust app
app = faust.App('features_stream', broker=f'kafka://{KAFKA_BOOTSTRAP}')

# Transaction record schema
class Transaction(faust.Record, serializer='json'):
    transaction_id: str
    user_id: str
    merchant_id: str
    amount: float
    currency: str
    timestamp: int
    device_id: str
    location_lat: float
    location_lon: float
    channel: str
    is_fraud_label: bool
    schema_version: int

# Topic
transactions_topic = app.topic('transactions', value_type=Transaction)

# Redis client
redis_client = None

# In-memory state for velocity features
user_velocity_windows = defaultdict(lambda: {
    'txn_1m': deque(),
    'amt_5m': deque(),
    'session_start': None,
    'last_activity': None
})

SESSION_TIMEOUT = 20 * 60  # 20 minutes in seconds

async def get_redis_client():
    """Get async Redis client"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL)
    return redis_client

async def update_velocity_features(user_id: str, transaction: Transaction):
    """Update sliding window velocity features for a user"""
    current_time = transaction.timestamp / 1000  # Convert to seconds
    current_dt = datetime.fromtimestamp(current_time)
    
    user_state = user_velocity_windows[user_id]
    
    # Update last activity
    user_state['last_activity'] = current_time
    
    # Session management
    if (user_state['session_start'] is None or 
        current_time - user_state['last_activity'] > SESSION_TIMEOUT):
        user_state['session_start'] = current_time
        logger.debug(f"Started new session for user {user_id}")
    
    # Add current transaction to windows
    user_state['txn_1m'].append(current_time)
    user_state['amt_5m'].append((current_time, transaction.amount))
    
    # Clean old data from 1-minute transaction window
    cutoff_1m = current_time - 60
    while user_state['txn_1m'] and user_state['txn_1m'][0] < cutoff_1m:
        user_state['txn_1m'].popleft()
    
    # Clean old data from 5-minute amount window
    cutoff_5m = current_time - 300
    while user_state['amt_5m'] and user_state['amt_5m'][0][0] < cutoff_5m:
        user_state['amt_5m'].popleft()
    
    # Compute features
    velocity_1m_txn_ct = len(user_state['txn_1m']) - 1  # Exclude current
    amt_sum_5m = sum(amt for ts, amt in user_state['amt_5m'] if ts < current_time)
    session_len = current_time - user_state['session_start'] if user_state['session_start'] else 0
    
    # Store features in Redis
    await store_features_in_redis(user_id, {
        'velocity_1m_txn_ct': velocity_1m_txn_ct,
        'amt_sum_5m': round(amt_sum_5m, 2),
        'session_len': round(session_len, 2),
        'last_updated': current_time
    })

async def store_features_in_redis(user_id: str, features: dict):
    """Store user features in Redis"""
    try:
        redis_conn = await get_redis_client()
        key = f"user:{user_id}"
        
        # Store as hash
        await redis_conn.hset(key, mapping=features)
        await redis_conn.expire(key, 86400)  # 24 hour TTL
        
        redis_writes.inc()
        logger.debug(f"Stored features for {user_id}: {features}")
        
    except Exception as e:
        redis_errors.inc()
        logger.error(f"Error storing features for {user_id}: {e}")

@app.agent(transactions_topic)
async def process_transactions(transactions):
    """Process transaction stream and update features"""
    async for transaction in transactions:
        start_time = time.perf_counter()
        
        try:
            await update_velocity_features(transaction.user_id, transaction)
            messages_processed.inc()
            
        except Exception as e:
            logger.error(f"Error processing transaction {transaction.transaction_id}: {e}")
        
        finally:
            processing_latency.observe(time.perf_counter() - start_time)

@app.timer(interval=30.0)
async def cleanup_inactive_sessions():
    """Periodically clean up inactive user sessions"""
    current_time = time.time()
    inactive_users = []
    
    for user_id, state in user_velocity_windows.items():
        if (state['last_activity'] and 
            current_time - state['last_activity'] > SESSION_TIMEOUT * 2):
            inactive_users.append(user_id)
    
    for user_id in inactive_users:
        del user_velocity_windows[user_id]
        logger.debug(f"Cleaned up inactive session for user {user_id}")
    
    # Update metrics
    active_sessions.set(len(user_velocity_windows))

@app.page('/metrics')
async def metrics_endpoint(web, request):
    """Expose Prometheus metrics"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return web.Response(
        body=generate_latest(),
        content_type=CONTENT_TYPE_LATEST
    )

@app.page('/health')
async def health_check(web, request):
    """Health check endpoint"""
    try:
        redis_conn = await get_redis_client()
        await redis_conn.ping()
        return web.json({'status': 'healthy', 'redis': 'connected'})
    except Exception as e:
        return web.json({'status': 'unhealthy', 'error': str(e)}, status=500)

if __name__ == '__main__':
    # Start Prometheus metrics server
    start_http_server(METRICS_PORT)
    logger.info(f"Started metrics server on port {METRICS_PORT}")
    
    # Run Faust app
    app.main()