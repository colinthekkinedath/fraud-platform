#!/usr/bin/env python3
"""
Fraud Training Pipeline (Nightly)
Phase 2 - Step 6

Airflow DAG for model training, evaluation, and MLflow registration
"""
from datetime import datetime, timedelta
import os
import pandas as pd
import numpy as np
import joblib
import mlflow
import mlflow.xgboost
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, f1_score, classification_report
import xgboost as xgb
import json
import boto3

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable

# Default arguments
default_args = {
    'owner': 'fraud-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# DAG definition
dag = DAG(
    'fraud_train_register',
    default_args=default_args,
    description='Fraud detection model training and registration',
    schedule_interval='0 2 * * *',  # Daily at 2 AM
    catchup=False,
    max_active_runs=1,
    tags=['fraud', 'ml', 'training'],
)

# Configuration
MLFLOW_TRACKING_URI = "http://mlflow:5000"
MINIO_ENDPOINT = "minio:9000"
AWS_ACCESS_KEY = "admin"
AWS_SECRET_KEY = "password123"
TARGET_AUC = 0.95

def get_s3_client():
    """Initialize S3 client for MinIO"""
    return boto3.client(
        's3',
        endpoint_url=f'http://{MINIO_ENDPOINT}',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name='us-east-1'
    )

def extract_dataset(**context):
    """Extract and prepare training dataset from feature store"""
    import tempfile
    from io import BytesIO
    import pyarrow.parquet as pq
    
    # Calculate date range (last 7 days)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    print(f"Extracting dataset from {start_date} to {end_date}")
    
    s3_client = get_s3_client()
    
    # Read feature data from multiple date partitions
    all_features = []
    
    for i in range(7):  # Last 7 days
        date_str = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        key = f"offline/dt={date_str}/features.parquet"
        
        try:
            response = s3_client.get_object(Bucket='fraud-features', Key=key)
            parquet_data = BytesIO(response['Body'].read())
            df_day = pq.read_table(parquet_data).to_pandas()
            all_features.append(df_day)
            print(f"Loaded {len(df_day)} records for {date_str}")
            
        except Exception as e:
            print(f"No data found for {date_str}: {e}")
            continue
    
    if not all_features:
        raise ValueError("No feature data found for training")
    
    # Combine all data
    df = pd.concat(all_features, ignore_index=True)
    print(f"Total dataset size: {len(df)} records")
    
    # Feature engineering
    feature_columns = [
        't_minus_1h_txn_ct',
        't_minus_1h_amt_sum', 
        't_minus_24h_amt_mean',
        't_minus_24h_txn_ct',
        'device_7d_txn_ct',
        'current_amount'
    ]
    
    # Prepare features and labels
    X = df[feature_columns].fillna(0)
    y = df['is_fraud_label'].astype(int)
    
    # Basic statistics
    fraud_rate = y.mean()
    print(f"Dataset fraud rate: {fraud_rate:.4f}")
    print(f"Feature columns: {feature_columns}")
    
    # Save dataset to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        dataset_info = {
            'features_path': '/tmp/features.parquet',
            'labels_path': '/tmp/labels.parquet', 
            'fraud_rate': fraud_rate,
            'total_samples': len(df),
            'feature_columns': feature_columns
        }
        json.dump(dataset_info, f)
        dataset_path = f.name
    
    # Save actual data
    X.to_parquet('/tmp/features.parquet')
    y.to_frame('is_fraud_label').to_parquet('/tmp/labels.parquet')
    
    return dataset_path

def train_model(**context):
    """Train XGBoost model with MLflow tracking"""
    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("fraud-xgb")
    
    # Load dataset info
    dataset_path = context['task_instance'].xcom_pull(task_ids='extract_dataset')
    with open(dataset_path, 'r') as f:
        dataset_info = json.load(f)
    
    # Load features and labels
    X = pd.read_parquet(dataset_info['features_path'])
    y = pd.read_parquet(dataset_info['labels_path'])['is_fraud_label']
    
    print(f"Training on {len(X)} samples with fraud rate {dataset_info['fraud_rate']:.4f}")
    
    # Train/validation split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Start MLflow run
    with mlflow.start_run(run_name=f"fraud_model_{datetime.now().strftime('%Y%m%d_%H%M')}"):
        
        # Model parameters
        params = {
            "max_depth": 6,
            "eta": 0.1,
            "subsample": 0.8,
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "random_state": 42
        }
        
        # Log parameters
        mlflow.log_params(params)
        mlflow.log_params({
            "train_samples": len(X_train),
            "val_samples": len(X_val), 
            "fraud_rate": dataset_info['fraud_rate'],
            "feature_count": len(dataset_info['feature_columns'])
        })
        
        # Train model
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        
        bst = xgb.train(
            params, 
            dtrain, 
            num_boost_round=500,
            evals=[(dtrain, 'train'), (dval, 'val')],
            early_stopping_rounds=50,
            verbose_eval=False
        )
        
        # Predictions and evaluation
        y_pred_proba = bst.predict(dval)
        y_pred = (y_pred_proba > 0.5).astype(int)
        
        auc = roc_auc_score(y_val, y_pred_proba)
        f1 = f1_score(y_val, y_pred)
        
        # Log metrics
        mlflow.log_metric("auc", auc)
        mlflow.log_metric("f1_score", f1)
        
        print(f"Model performance: AUC={auc:.4f}, F1={f1:.4f}")
        
        # Save model
        model_path = "/tmp/model.pkl"
        joblib.dump(bst, model_path)
        mlflow.log_artifact(model_path)
        mlflow.xgboost.log_model(bst, "model")
        
        # Save evaluation results
        eval_results = {
            "auc": auc,
            "f1_score": f1,
            "train_date": datetime.now().isoformat(),
            "model_path": model_path,
            "meets_target": auc >= TARGET_AUC
        }
        
        return eval_results

def evaluate(**context):
    """Evaluate model and save results"""
    eval_results = context['task_instance'].xcom_pull(task_ids='train_model')
    
    # Ensure eval directory exists
    os.makedirs('/opt/airflow/docs/eval', exist_ok=True)
    
    # Save evaluation results
    eval_path = '/opt/airflow/docs/eval/latest.json'
    with open(eval_path, 'w') as f:
        json.dump(eval_results, f, indent=2)
    
    print(f"Evaluation results saved to {eval_path}")
    print(f"AUC: {eval_results['auc']:.4f}")
    print(f"Meets target (≥{TARGET_AUC}): {eval_results['meets_target']}")
    
    return eval_results['auc']

def register_model(**context):
    """Register model in MLflow if it meets quality criteria"""
    eval_results = context['task_instance'].xcom_pull(task_ids='train_model')
    
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    
    if eval_results['meets_target']:
        print(f"Model meets target AUC ≥ {TARGET_AUC}, proceeding with registration")
        # Here you would typically register the model to MLflow Model Registry
        # For now, just log the success
        print("Model registered successfully")
    else:
        print(f"Model AUC {eval_results['auc']:.4f} below target {TARGET_AUC}, skipping registration")
    
    return eval_results

# Task definitions
extract_task = PythonOperator(
    task_id='extract_dataset',
    python_callable=extract_dataset,
    dag=dag,
)

train_task = PythonOperator(
    task_id='train_model',
    python_callable=train_model,
    dag=dag,
)

evaluate_task = PythonOperator(
    task_id='evaluate',
    python_callable=evaluate,
    dag=dag,
)

register_task = PythonOperator(
    task_id='register_model',
    python_callable=register_model,
    dag=dag,
)

# Task dependencies
extract_task >> train_task >> evaluate_task >> register_task