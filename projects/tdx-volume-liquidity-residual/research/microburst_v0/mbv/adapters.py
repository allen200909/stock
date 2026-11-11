import pandas as pd
import numpy as np

def load_synthetic_minute_data(filepath: str) -> pd.DataFrame:
    # Simulating data loading
    df = pd.DataFrame({
        'symbol': ['600000.SH'] * 240,
        'ts': pd.date_range('2026-01-01 09:30', periods=240, freq='T'),
        'open': np.random.rand(240),
        'high': np.random.rand(240),
        'low': np.random.rand(240),
        'close': np.random.rand(240),
        'volume': np.random.randint(1000, 10000, 240)
    })
    return df
