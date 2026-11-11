from typing import TypedDict, Optional
from dataclasses import dataclass

@dataclass
class MinuteBar:
    symbol: str
    ts: str # ISO format or standardized
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None
    
@dataclass
class DailyFeature:
    symbol: str
    trade_date: str
    burst_count: int
    burst_share: float
    peak_ratio: float
    burst_dominance: float
    burst_concentration: float
    burst_direction_agreement: float
    feature_status: str # 'OK', 'INSUFFICIENT_HISTORY', etc.