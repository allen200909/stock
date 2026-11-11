import pytest
import pandas as pd
import numpy as np
from mbv.features import detect_bursts

def test_burst_detection():
    data = pd.DataFrame({
        'volume': [100, 500, 100],
        'ts': pd.to_datetime(['2026-01-01 09:30', '2026-01-01 09:31', '2026-01-01 09:32'])
    })
    baseline = pd.Series([100, 100, 100], index=[pd.Timestamp('09:30:00').time(), pd.Timestamp('09:31:00').time(), pd.Timestamp('09:32:00').time()])
    df = detect_bursts(data, baseline, threshold=2.5)
    assert df['is_burst'].tolist() == [False, True, False]
