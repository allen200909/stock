import pandas as pd
import numpy as np

def aggregate_daily_features(df: pd.DataFrame) -> dict:
    total_volume = df['volume'].sum()
    burst_data = df[df['is_burst']]
    burst_count = len(burst_data)
    burst_share = burst_data['volume'].sum() / total_volume if total_volume > 0 else 0
    
    return {
        'burst_count': burst_count,
        'burst_share': burst_share,
    }