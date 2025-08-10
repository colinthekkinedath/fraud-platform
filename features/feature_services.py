from feast import FeatureService, OnDemandFeatureView, Field
from feast.types import Float32
from features.feature_repo import txn_agg_1h_24h, user

# Define on-demand feature view for lightweight transforms
@OnDemandFeatureView(
    sources=[txn_agg_1h_24h],
    schema=[
        Field(name="normalized_amount", dtype=Float32),
        Field(name="velocity_ratio", dtype=Float32),
        Field(name="amount_vs_24h_avg", dtype=Float32),
    ],
)
def derived_features(features_df):
    """Compute lightweight derived features on-demand"""
    df = features_df.copy()
    
    # Normalize current amount by user's 24h average
    df["normalized_amount"] = df["current_amount"] / (df["t_minus_24h_amt_mean"] + 1e-6)
    
    # Velocity ratio (1h vs 24h)
    df["velocity_ratio"] = df["t_minus_1h_txn_ct"] / (df["t_minus_24h_txn_ct"] / 24 + 1e-6)
    
    # Amount comparison to 24h average
    df["amount_vs_24h_avg"] = (df["current_amount"] - df["t_minus_24h_amt_mean"]) / (df["t_minus_24h_amt_mean"] + 1e-6)
    
    return df[["normalized_amount", "velocity_ratio", "amount_vs_24h_avg"]]

# Define feature service combining offline and streaming features
fraud_features_v1 = FeatureService(
    name="fraud_features_v1",
    features=[
        txn_agg_1h_24h,
        derived_features,
    ],
)