# Mean-Reversion FX Trading Bot

A Python-based algorithmic trading system for spot FX, built on the OANDA v20 API. The strategy trades short-term mean reversion in price relative to a rolling simple moving average, using a Student's t-distribution fit to standardize deviations into a comparable z-score-like signal across instruments.

## Methodology

For each instrument, the bot:

1. Pulls a rolling window of completed M15 candles (bid and ask close prices separately).
2. Computes each price series' distance from its own rolling 60-bar SMA.
3. Fits a Student's t-distribution to the historical distribution of that distance, then scores the most recent value against the fitted distribution (`t_score`).
4. Enters a position when the t-score crosses an extreme threshold and exits when it reverts back toward a looser threshold.

## Position sizing

Order size is fixed-notional in USD terms per trade. Because OANDA's `units` field represents units of the pair's **base currency**, sizing logic branches depending on whether USD is the base or quote currency for a given pair, so that every trade represents a consistent USD notional regardless of which side of the pair USD sits on.

## Instruments

Currently trades a fixed basket of major USD pairs: EUR/USD, GBP/USD, AUD/USD, USD/CAD, USD/JPY, USD/CHF.

## Infrastructure

- Runs continuously on a scheduling loop synchronized to candle close boundaries (no mid-candle evaluation).
- Retry logic with exponential backoff around all API calls to handle transient network/API failures without crashing.
- Position state is reconciled against OANDA's actual open positions rather than tracked purely in local memory, to avoid drift from rejected or partially-executed orders.
- Designed to run persistently (e.g., via `tmux`) on lightweight hardware such as a Raspberry Pi5.

## Stack

Python, `pandas`, `scipy.stats`, `oandapyV20`.

## Status

Actively developed against an OANDA practice (paper trading) account. Not investment advice; provided as-is for research and educational purposes.

## Disclaimer

This project is for educational and research purposes only. Trading foreign exchange carries substantial risk of loss and is not suitable for all investors. Nothing in this repository constitutes financial advice. Use at your own risk.