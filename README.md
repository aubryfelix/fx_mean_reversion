# fx_mean_reversion
Mean-reversion model on spot FX majors. Fits a t-distribution to the historical distribution of the distance between a 60-bar rolling mean and close price, scoring the most recent value against the distribution. Order size is fixed-notional in USD terms per trade.
