"""Price metrics from section 5.3. Pure functions, no database, easy to test.

    r_t  = (P_t - P_t-1) / P_t-1 x 100
    VR_t = V_t / mean(V over the previous N days, excluding today)
    z_t  = (r_t - mean of previous N returns) / standard deviation of previous N returns

Sample standard deviation (n-1) is used. The window excludes today so a spike cannot dilute itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_metrics(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """df needs columns: date, close, volume. Returns a copy sorted by date with ret_pct, vol_ratio, z_ret."""
    out = df.sort_values("date").reset_index(drop=True).copy()
    out["ret_pct"] = out["close"].pct_change() * 100

    prev_vol_mean = out["volume"].shift(1).rolling(window, min_periods=window).mean()
    out["vol_ratio"] = np.where(prev_vol_mean > 0, out["volume"] / prev_vol_mean, np.nan)

    prev_ret = out["ret_pct"].shift(1)
    mean = prev_ret.rolling(window, min_periods=window).mean()
    std = prev_ret.rolling(window, min_periods=window).std(ddof=1)
    out["z_ret"] = np.where(std > 0, (out["ret_pct"] - mean) / std, np.nan)
    return out
