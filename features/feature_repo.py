from feast import Entity, Field, FeatureView, FileSource, ValueType
from feast.types import Float32, Int64
from datetime import timedelta

# Define user entity
user = Entity(name="user_id", value_type=ValueType.STRING)

# Define offline source
offline_src = FileSource(
    path="s3://fraud-features/offline",
    timestamp_field="event_time",
    created_timestamp_column="created_at",
)

# Define feature view for transaction aggregations
txn_agg_1h_24h = FeatureView(
    name="txn_agg_1h_24h",
    entities=[user],
    ttl=timedelta(days=14),
    schema=[
        Field(name="t_minus_1h_txn_ct", dtype=Int64),
        Field(name="t_minus_1h_amt_sum", dtype=Float32),
        Field(name="t_minus_24h_amt_mean", dtype=Float32),
        Field(name="t_minus_24h_txn_ct", dtype=Int64),
        Field(name="device_7d_txn_ct", dtype=Int64),
        Field(name="current_amount", dtype=Float32),
    ],
    online=True,
    source=offline_src,
)