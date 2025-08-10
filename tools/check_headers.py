#!/usr/bin/env python3
"""
A/B Test Header Checker
Phase 2 - Step 9

Sample Kafka messages and check A/B variant distribution
"""
import argparse
import sys
from collections import defaultdict
from kafka import KafkaConsumer
import json
import time

def check_ab_headers(bootstrap_server, topic, sample_size):
    """Check A/B test header distribution"""
    
    print(f"Sampling {sample_size} messages from topic '{topic}'...")
    
    # Initialize consumer
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[bootstrap_server],
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest',
        group_id=f'header_check_{int(time.time())}'
    )
    
    # Track variants
    variant_counts = defaultdict(int)
    total_messages = 0
    messages_with_headers = 0
    
    try:
        for message in consumer:
            total_messages += 1
            
            # Check headers
            if message.headers:
                headers_dict = {k.decode(): v.decode() for k, v in message.headers}
                
                if 'ab_variant' in headers_dict:
                    variant = headers_dict['ab_variant']
                    variant_counts[variant] += 1
                    messages_with_headers += 1
                
                # Also check for fraud score if present
                if 'fraud_score' in headers_dict:
                    print(f"Found fraud score: {headers_dict['fraud_score']}")
            
            # Stop when we reach sample size
            if total_messages >= sample_size:
                break
                
            # Progress indicator
            if total_messages % 1000 == 0:
                print(f"Processed {total_messages} messages...")
    
    except KeyboardInterrupt:
        print("\nSampling interrupted by user")
    
    finally:
        consumer.close()
    
    # Report results
    print(f"\n📊 A/B Test Header Analysis")
    print(f"=" * 40)
    print(f"Total messages sampled: {total_messages}")
    print(f"Messages with headers: {messages_with_headers}")
    print(f"Header rate: {messages_with_headers/total_messages*100:.1f}%")
    
    if variant_counts:
        print(f"\nVariant distribution:")
        for variant, count in variant_counts.items():
            percentage = count / messages_with_headers * 100
            print(f"  {variant}: {count} ({percentage:.1f}%)")
        
        # Check if canary rate is in expected range (9-11%)
        canary_rate = variant_counts.get('canary', 0) / messages_with_headers * 100
        if 9 <= canary_rate <= 11:
            print(f"✅ Canary rate {canary_rate:.1f}% is within target range (9-11%)")
            return True
        else:
            print(f"⚠️  Canary rate {canary_rate:.1f}% is outside target range (9-11%)")
            return False
    else:
        print("❌ No A/B variant headers found")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Check A/B test header distribution')
    parser.add_argument('--bootstrap-server', default='localhost:9092', 
                       help='Kafka bootstrap server')
    parser.add_argument('--topic', default='transactions',
                       help='Kafka topic to sample')
    parser.add_argument('--sample', type=int, default=10000,
                       help='Number of messages to sample')
    
    args = parser.parse_args()
    
    success = check_ab_headers(args.bootstrap_server, args.topic, args.sample)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()