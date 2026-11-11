import pandas as pd
import numpy as np

def compute_tod_baseline(df: pd.DataFrame, lookback_days=20) -> pd.DataFrame:
    # Logic to compute median volume for each minute/slot
    # Group by minute/slot and compute median volume across history
    # Placeholder implementation
    return df.groupby(df['ts'].dt.time)['volume'].median()
