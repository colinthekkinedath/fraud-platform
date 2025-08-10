#!/usr/bin/env python3
"""
Feature Probe - Dev Utility
Phase 2 - Step 8

Test Feast online feature retrieval
"""
import time
import sys
import os
from feast import FeatureStore
import pandas as pd

def test_online_features():
    """Test online feature retrieval from Feast"""
    
    # Initialize feature store
    try:
        fs = FeatureStore(repo_path="features")
        print("✅ Feature store initialized")
    except Exception as e:
        print(f"❌ Failed to initialize feature store: {e}")
        return False
    
    # Test feature retrieval
    try:
        start_time = time.perf_counter()
        
        # Request features for a test user
        resp = fs.get_online_features(
            features=[
                "txn_agg_1h_24h:t_minus_1h_txn_ct",
                "txn_agg_1h_24h:t_minus_1h_amt_sum",
                "txn_agg_1h_24h:t_minus_24h_amt_mean",
                "txn_agg_1h_24h:device_7d_txn_ct"
            ],
            entity_rows=[{"user_id": "user_123"}]
        ).to_dict()
        
        latency = (time.perf_counter() - start_time) * 1000  # Convert to ms
        
        print(f"✅ Feature retrieval successful in {latency:.2f}ms")
        print("📊 Retrieved features:")
        for key, values in resp.items():
            if key != 'user_id':
                print(f"   {key}: {values[0] if values else 'None'}")
        
        # Check if latency is acceptable
        if latency < 10:
            print(f"✅ Latency {latency:.2f}ms is acceptable (< 10ms)")
            return True
        else:
            print(f"⚠️  Latency {latency:.2f}ms is high (≥ 10ms)")
            return False
            
    except Exception as e:
        print(f"❌ Feature retrieval failed: {e}")
        return False

def test_streaming_features():
    """Test streaming features from Redis directly"""
    try:
        import redis
        
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Test connection
        r.ping()
        print("✅ Redis connection successful")
        
        # Check for streaming features
        user_key = "user:user_123"
        streaming_features = r.hgetall(user_key)
        
        if streaming_features:
            print("📊 Streaming features:")
            for key, value in streaming_features.items():
                print(f"   {key}: {value}")
            return True
        else:
            print("⚠️  No streaming features found for test user")
            return False
            
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def main():
    """Main probe function"""
    print("🔍 Feature Store Probe")
    print("=" * 50)
    
    # Test online features
    print("\n1. Testing Feast online features...")
    feast_ok = test_online_features()
    
    # Test streaming features  
    print("\n2. Testing streaming features...")
    redis_ok = test_streaming_features()
    
    print("\n" + "=" * 50)
    if feast_ok and redis_ok:
        print("✅ All feature systems operational")
        sys.exit(0)
    else:
        print("❌ Some feature systems have issues")
        sys.exit(1)

if __name__ == "__main__":
    main()