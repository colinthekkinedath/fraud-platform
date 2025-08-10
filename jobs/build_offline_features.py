#!/usr/bin/env python3
"""
Build Offline Feature Tables (Parquet on Lake)
Phase 2 - Step 1

Reads raw JSON events from S3/MinIO and writes daily-partitioned Parquet aggregates
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import boto3
from io import StringIO
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MinIO/S3 configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "admin")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "password123")
SOURCE_BUCKET = "fraud-raw"
TARGET_BUCKET = "fraud-features"

def get_s3_client():
    """Initialize S3 client for MinIO"""
    return boto3.client(
        's3',
        endpoint_url=f'http://{MINIO_ENDPOINT}',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name='us-east-1'
    )

def read_raw_transactions(s3_client, date_str):
    """Read raw transaction JSON files from S3 for a specific date"""
    transactions = []
    
    try:
        # List objects for the given date
        prefix = f"topics/transactions/partition=0/"  # Kafka Connect format
        response = s3_client.list_objects_v2(Bucket=SOURCE_BUCKET, Prefix=prefix)
        
        if 'Contents' not in response:
            logger.warning(f"No files found for date {date_str}")
            return pd.DataFrame()
        
        for obj in response['Contents']:
            if obj['Key'].endswith('.json'):
                # Read the JSON file
                response = s3_client.get_object(Bucket=SOURCE_BUCKET, Key=obj['Key'])
                content = response['Body'].read().decode('utf-8')
                
                # Parse JSON lines
                for line in content.strip().split('\n'):
                    if line.strip():
                        try:
                            tx = json.loads(line)
                            transactions.append(tx)
                        except json.JSONDecodeError:
                            continue
                            
        logger.info(f"Read {len(transactions)} transactions")
        return pd.DataFrame(transactions)
        
    except Exception as e:
        logger.error(f"Error reading transactions: {e}")
        return pd.DataFrame()

def compute_features(df):
    """Compute time-windowed aggregation features per user_id"""
    if df.empty:
        return pd.DataFrame()
    
    # Convert timestamp to datetime
    df['event_time'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values(['user_id', 'event_time'])
    
    features = []
    
    for user_id, user_df in df.groupby('user_id'):
        user_df = user_df.reset_index(drop=True)
        
        for i, row in user_df.iterrows():
            current_time = row['event_time']
            
            # Define time windows
            window_1h = current_time - timedelta(hours=1)
            window_24h = current_time - timedelta(hours=24)
            window_7d = current_time - timedelta(days=7)
            
            # Filter data for each window
            data_1h = user_df[user_df['event_time'] > window_1h]
            data_24h = user_df[user_df['event_time'] > window_24h]
            data_7d = user_df[user_df['event_time'] > window_7d]
            
            # Compute aggregations
            feature_row = {
                'user_id': user_id,
                'event_time': current_time,
                'created_at': datetime.now(),
                
                # 1-hour window features
                't_minus_1h_txn_ct': len(data_1h) - 1,  # exclude current transaction
                't_minus_1h_amt_sum': data_1h[data_1h['event_time'] < current_time]['amount'].sum(),
                
                # 24-hour window features  
                't_minus_24h_amt_mean': data_24h[data_24h['event_time'] < current_time]['amount'].mean(),
                't_minus_24h_txn_ct': len(data_24h) - 1,
                
                # 7-day device activity
                'device_7d_txn_ct': len(data_7d[
                    (data_7d['device_id'] == row['device_id']) & 
                    (data_7d['event_time'] < current_time)
                ]),
                
                # Current transaction features
                'current_amount': row['amount'],
                'current_channel': row['channel'],
                'is_fraud_label': row['is_fraud_label']
            }
            
            # Handle NaN values
            for key, value in feature_row.items():
                if pd.isna(value):
                    if key.endswith('_ct'):
                        feature_row[key] = 0
                    elif key.endswith('_sum') or key.endswith('_mean'):
                        feature_row[key] = 0.0
            
            features.append(feature_row)
    
    return pd.DataFrame(features)

def write_features_to_s3(s3_client, features_df, date_str):
    """Write features as Parquet to S3 with daily partitioning"""
    if features_df.empty:
        logger.warning("No features to write")
        return False
    
    try:
        # Ensure target bucket exists
        try:
            s3_client.head_bucket(Bucket=TARGET_BUCKET)
        except:
            s3_client.create_bucket(Bucket=TARGET_BUCKET)
            logger.info(f"Created bucket {TARGET_BUCKET}")
        
        # Write as Parquet
        from io import BytesIO
        import pyarrow as pa
        import pyarrow.parquet as pq
        
        # Convert to PyArrow table
        table = pa.Table.from_pandas(features_df)
        
        # Write to buffer
        buffer = BytesIO()
        pq.write_table(table, buffer)
        buffer.seek(0)
        
        # Upload to S3 with partition key
        key = f"offline/dt={date_str}/features.parquet"
        s3_client.put_object(
            Bucket=TARGET_BUCKET,
            Key=key,
            Body=buffer.getvalue(),
            ContentType='application/octet-stream'
        )
        
        logger.info(f"Wrote {len(features_df)} feature records to s3://{TARGET_BUCKET}/{key}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing features: {e}")
        return False

def main():
    """Main function to build offline features for a specific date"""
    # Use yesterday as default date (to allow for data to be written)
    date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    if len(os.sys.argv) > 1:
        date_str = os.sys.argv[1]
    
    logger.info(f"Building offline features for date: {date_str}")
    
    # Initialize S3 client
    s3_client = get_s3_client()
    
    # Read raw transactions
    transactions_df = read_raw_transactions(s3_client, date_str)
    
    if transactions_df.empty:
        logger.warning("No transactions found")
        return
    
    # Compute features
    features_df = compute_features(transactions_df)
    
    # Write features to S3
    success = write_features_to_s3(s3_client, features_df, date_str)
    
    if success:
        logger.info("Feature building completed successfully")
    else:
        logger.error("Feature building failed")

if __name__ == "__main__":
    main()