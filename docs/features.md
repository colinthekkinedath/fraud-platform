# Feature Engineering Documentation

This document describes the feature engineering pipeline implemented for the fraud detection platform.

## Feature Categories

### 1. Offline Features (Batch Processed)

These features are computed daily from historical transaction data and stored as Parquet files partitioned by date.

#### Time-Windowed Aggregations

| Feature Name | Description | Window | Type |
|--------------|-------------|---------|------|
| `t_minus_1h_txn_ct` | Transaction count in the past 1 hour | 1 hour | Int64 |
| `t_minus_1h_amt_sum` | Total amount transacted in past 1 hour | 1 hour | Float32 |
| `t_minus_24h_amt_mean` | Average transaction amount in past 24 hours | 24 hours | Float32 |
| `t_minus_24h_txn_ct` | Transaction count in past 24 hours | 24 hours | Int64 |
| `device_7d_txn_ct` | Device usage count in past 7 days | 7 days | Int64 |

#### Current Transaction Features

| Feature Name | Description | Type |
|--------------|-------------|------|
| `current_amount` | Amount of current transaction | Float32 |
| `current_channel` | Channel of current transaction | String |
| `is_fraud_label` | Ground truth fraud label | Boolean |

### 2. Streaming Features (Real-time)

These features are computed in real-time from the transaction stream using Faust and stored in Redis.

#### Velocity Features

| Feature Name | Description | Window | Type |
|--------------|-------------|---------|------|
| `velocity_1m_txn_ct` | Transaction count in past 1 minute | 60 seconds | Int |
| `amt_sum_5m` | Amount sum in past 5 minutes | 5 minutes | Float |
| `session_len` | Length of current user session | Session | Float |

Session is defined as continuous activity with max 20-minute inactivity gap.

### 3. Derived Features (On-Demand)

These features are computed on-demand during feature retrieval using Feast's OnDemandFeatureView.

| Feature Name | Description | Formula |
|--------------|-------------|---------|
| `normalized_amount` | Current amount normalized by user average | `current_amount / (t_minus_24h_amt_mean + ε)` |
| `velocity_ratio` | Ratio of 1h to 24h transaction rate | `t_minus_1h_txn_ct / (t_minus_24h_txn_ct / 24 + ε)` |
| `amount_vs_24h_avg` | Relative amount vs 24h average | `(current_amount - t_minus_24h_amt_mean) / (t_minus_24h_amt_mean + ε)` |

Where ε = 1e-6 to prevent division by zero.

## Data Pipeline

### Offline Feature Pipeline

1. **Source**: Raw transaction JSON files in S3 (`s3://fraud-raw/topics/transactions/`)
2. **Processing**: Daily batch job (`jobs/build_offline_features.py`)
3. **Output**: Parquet files partitioned by date (`s3://fraud-features/offline/dt=YYYY-MM-DD/`)

### Streaming Feature Pipeline

1. **Source**: Kafka topic `transactions`
2. **Processing**: Faust streaming app (`services/features_stream/app.py`)
3. **Output**: Redis hash keys (`user:<user_id>`)

### Feature Store Integration

- **Feast Registry**: `data/feast/registry.db`
- **Online Store**: Redis (`redis:6379/0`)
- **Offline Store**: S3 Parquet files (`s3://fraud-features/offline`)

## Usage

### Training Pipeline

```python
# Extract features for training
features = extract_features_for_training(start_date, end_date)
X = features[feature_columns]
y = features['is_fraud_label']
```

### Online Inference

```python
from feast import FeatureStore

fs = FeatureStore(repo_path="features")
features = fs.get_online_features(
    features=["fraud_features_v1"],
    entity_rows=[{"user_id": "user_123"}]
)
```

## Monitoring

### Offline Features
- Daily feature freshness checks
- Feature drift monitoring
- Data quality validation

### Streaming Features
- Processing latency metrics
- Redis write success rate
- Active session count

### Metrics Endpoints
- Offline processing: Airflow DAG metrics
- Streaming processing: `http://features-stream:8002/metrics`
- Feature store health: `http://features-stream:8002/health`

## Quality Gates

### Data Quality
- Non-null feature percentage > 95%
- Feature value range validation
- Temporal consistency checks

### Performance
- Offline processing: < 1 hour for daily batch
- Streaming latency: < 100ms p95
- Online retrieval: < 10ms p95

### Model Performance
- Training AUC target: ≥ 0.95
- Feature importance stability
- Prediction drift monitoring