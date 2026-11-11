import pandas as pd

def join_daily_vlr_mbv(daily_vlr: pd.DataFrame, mbv_features: pd.DataFrame) -> pd.DataFrame:
    # Joining daily B0 VLR features with MBV features
    return pd.merge(daily_vlr, mbv_features, on=['symbol', 'trade_date'], how='left')
