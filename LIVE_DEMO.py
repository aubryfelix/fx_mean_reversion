import time
import numpy as np
import pandas as pd
from collections import deque
from scipy import stats
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.positions as positions
import oandapyV20.endpoints.accounts as accounts
from datetime import datetime, timedelta, timezone

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  OANDA CLIENT
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

OANDA_API_KEY    = ""
OANDA_ACCOUNT_ID = ""
OANDA_ENV        = "practice"
client = oandapyV20.API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  STRATEGY PARAMS
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

INSTRUMENTS = ["EUR_USD", "USD_CAD", "USD_JPY", "GBP_USD", "USD_CHF", "AUD_USD"]
GRANULARITY = "M15"
SMA_LENGTH = 60
T_THRESHOLD_ENTRY = 2.0
T_THRESHOLD_EXIT = 1.0
GRANULARITY_MINUTES = 15
BOUNDARY_BUFFER_SECONDS = 1

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  FETCH CONFIG
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def sleep_until_next_candle_close(granularity_minutes: int = GRANULARITY_MINUTES, buffer_seconds: int = BOUNDARY_BUFFER_SECONDS):

  now = datetime.now(timezone.utc)
  minutes_past_boundary = now.minute % granularity_minutes
  current_boundary = now.replace(second=0, microsecond=0) - timedelta(minutes=minutes_past_boundary)
  next_boundary = current_boundary + timedelta(minutes=granularity_minutes)
  target = next_boundary + timedelta(seconds=buffer_seconds)

  sleep_seconds = (target - now).total_seconds()
  if sleep_seconds > 0:
    time.sleep(sleep_seconds)

def fetch_completed_candle(client, instrument, granularity, max_retries=5, retry_delay=1.0):
    for attempt in range(max_retries):
        req = instruments.InstrumentsCandles(
            instrument=instrument,
            params={'price': 'BA', 'granularity': granularity, 'count': 2}
        )
        try:
            resp = client.request(req)
        except oandapyV20.exceptions.V20Error as e:
            print(f'[RETRY-ERROR] {instrument} attempt {attempt}: {e}')
            time.sleep(retry_delay * (2 ** attempt))
            continue

        completed = [c for c in resp['candles'] if c['complete']]
        if completed:
            return completed[-1]

        time.sleep(retry_delay * (2 ** attempt))

    return None

def fetch_signal_candles(client, instrument, granularity, count=5000, max_retries=5, retry_delay=1.0):
    for attempt in range(max_retries):
        req = instruments.InstrumentsCandles(
            instrument=instrument,
            params={'price': 'BA', 'granularity': granularity, 'count': count}
        )
        try:
            return client.request(req)
        except oandapyV20.exceptions.V20Error as e:
            print(f'[RETRY-ERROR] {instrument} attempt {attempt}: {e}')
            time.sleep(retry_delay * (2 ** attempt))
        except Exception as e:
            print(f'[UNEXPECTED-ERROR] {instrument} attempt {attempt}: {e}')
            time.sleep(retry_delay * (2 ** attempt))
    return None

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  EXECUTION
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def active_positions(client, account_id):
    req = positions.OpenPositions(accountID=account_id)
    resp = client.request(req)
    open_positions = resp['positions']

    net_long = []
    net_short = []

    for p in open_positions:
        instrument = p['instrument']
        long_units = float(p['long']['units'])
        short_units = float(p['short']['units'])

        if long_units > 0:
            net_long.append(instrument)
        if short_units < 0:
            net_short.append(instrument)

    return net_long, net_short

def marketorder(instrument, side, close):

  if instrument[:3] == 'USD':
    units = 100000 if side == "buy" else -100000
  else:
    units = round(100000/close) if side == "buy" else -round(100000/close)

  order_body = {
    "order": {
      "units": units,
      "instrument": instrument,
      "timeInForce": "FOK",
      "type": "MARKET",
      "positionFill": "DEFAULT"
    }
  }
  req  = orders.OrderCreate(OANDA_ACCOUNT_ID, data=order_body)
  
  try:
    resp = client.request(req)
  except Exception as e:
    print(f"{instrument} failed: {e}")
    return False
  if "orderFillTransaction" in resp:
    print(f"{instrument} filled: {resp['orderFillTransaction']['price']}")
    return True
  elif "orderCancelTransaction" in resp:
    print(f"{instrument} CANCELLED: {resp['orderCancelTransaction']['reason']}")
    return False
  else:
    print(f"{instrument} unexpected response: {resp}")
    return False

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  T-STAT MAINLOOP
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

NET_LONG, NET_SHORT = active_positions(client, OANDA_ACCOUNT_ID)

print(f'[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] AWAITING M15 CLOSE — NET LONG: {NET_LONG} — NET SHORT: {NET_SHORT}')

sleep_until_next_candle_close()

while True:
    print(f'{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] BOT ACTIVE — NET LONG: {NET_LONG} — NET SHORT: {NET_SHORT}')
    for instrument in INSTRUMENTS:
        # FETCH BID & ASK
        resp = fetch_signal_candles(client, instrument, GRANULARITY)
        if resp is None:
          print(f'[SKIP] {instrument} — could not fetch candles after retries')
          continue
        candles = [c for c in resp['candles'] if c['complete']]
        closes_bid = [float(c['bid']['c']) for c in candles]
        closes_ask = [float(c['ask']['c']) for c in candles]
        arr_bid = pd.Series(closes_bid)
        arr_ask = pd.Series(closes_ask)
        # COMPUTE DISTANCE FROM SMA
        sma_dist_bid = arr_bid - arr_bid.rolling(SMA_LENGTH).mean()
        sma_dist_ask = arr_ask - arr_ask.rolling(SMA_LENGTH).mean()

        if len(sma_dist_bid) > SMA_LENGTH and len(sma_dist_ask) > SMA_LENGTH:
            # COMPUTE T FOR BID AND ASK
            df_bid, loc_bid, scale_bid = stats.t.fit(sma_dist_bid.dropna())
            t_score_bid = (sma_dist_bid.iloc[-1] - loc_bid) / scale_bid
            df_ask, loc_ask, scale_ask = stats.t.fit(sma_dist_ask.dropna())
            t_score_ask = (sma_dist_ask.iloc[-1] - loc_ask) / scale_ask

            # ENTRY LOGIC
            if instrument not in NET_LONG and instrument not in NET_SHORT:
                if t_score_bid > T_THRESHOLD_ENTRY and t_score_ask > T_THRESHOLD_EXIT:
                    if marketorder(instrument, side="sell", close=arr_bid.iloc[-1]):
                        NET_SHORT.append(instrument)

                elif t_score_ask < -T_THRESHOLD_ENTRY and t_score_bid < -T_THRESHOLD_EXIT:
                    if marketorder(instrument, side="buy", close=arr_ask.iloc[-1]):
                        NET_LONG.append(instrument)

            # EXIT LOGIC
            if instrument in NET_LONG and t_score_bid > -T_THRESHOLD_EXIT:
                if marketorder(instrument, side="sell", close=arr_bid.iloc[-1]):
                    NET_LONG.remove(instrument)
            
            if instrument in NET_SHORT and t_score_ask < T_THRESHOLD_EXIT:
                if marketorder(instrument, side="buy", close=arr_ask.iloc[-1]):
                    NET_SHORT.remove(instrument)

    sleep_until_next_candle_close()