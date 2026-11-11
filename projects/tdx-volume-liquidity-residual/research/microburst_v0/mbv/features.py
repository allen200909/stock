import pandas as pd
import numpy as np

def detect_bursts(df: pd.DataFrame, baseline: pd.Series, threshold=2.5) -> pd.DataFrame:
    # df expected to have 'volume' and 'ts'. baseline indexed by time.
    df['relative_volume'] = df['volume'] / df['ts'].dt.time.map(baseline)
    df['is_burst'] = df['relative_volume'] >= threshold
    return df
