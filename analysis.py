import pandas as pd
import numpy as np
import requests

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(data, short_window=12, long_window=26, signal_window=9):
    short_ema = data['Close'].ewm(span=short_window, adjust=False).mean()
    long_ema = data['Close'].ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def calculate_bollinger_bands(data, window=20, num_std=2):
    sma = data['Close'].rolling(window=window).mean()
    std = data['Close'].rolling(window=window).std()
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    return upper_band, lower_band

def calculate_adx(df, period=14):
    df = df.copy()
    df['high_low'] = df['High'] - df['Low']
    df['high_close'] = np.abs(df['High'] - df['Close'].shift())
    df['low_close'] = np.abs(df['Low'] - df['Close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    
    df['up_move'] = df['High'] - df['High'].shift()
    df['down_move'] = df['Low'].shift() - df['Low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    df['atr'] = df['tr'].rolling(window=period).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(window=period).mean() / df['atr'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(window=period).mean() / df['atr'])
    df['dx'] = 100 * np.abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['adx'] = df['dx'].rolling(window=period).mean()
    return df['adx']

def get_patterns(df):
    patterns = []
    # Simplified Candle Patterns
    c = df['Close'].iloc[-1]
    o = df['Open'].iloc[-1]
    h = df['High'].iloc[-1]
    l = df['Low'].iloc[-1]
    pc = df['Close'].iloc[-2]
    po = df['Open'].iloc[-2]
    
    # Hammer
    body = abs(c - o)
    lower_wick = min(c, o) - l
    upper_wick = h - max(c, o)
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        patterns.append("Hammer")
        
    # Bullish Engulfing
    if pc < po and c > o and c > po and o < pc:
        patterns.append("Bullish Engulfing")
        
    # Bearish Engulfing
    if pc > po and c < o and c < po and o > pc:
        patterns.append("Bearish Engulfing")
        
    return patterns

def fetch_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=2)
        data = res.json()
        return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except Exception:
        return 50, "Neutral"

def get_sentiment_impact(symbol):
    # Simplified news sentiment (usually would use an external API like NewsAPI or CryptoPanic)
    # Placeholder for crypto-related news impact
    if "-" in symbol: # Crypto detection
        return 5 # Slight positive bias for demo purposes
    return 0

def backtest_strategy(df, system_id):
    """
    Simulates the strategy on past data to calculate a 'Win Rate'.
    A Win is defined as a 2% gain before a 1% loss (simplified).
    """
    wins = 0
    total = 0
    
    # We'll check the last 100 points for backtesting (if available)
    lookback = min(len(df) - 20, 100)
    for i in range(20, len(df) - 10):
        temp_df = df.iloc[:i+1]
        hist_curr = temp_df.iloc[-1]
        hist_prev = temp_df.iloc[-2]
        hist_v_sma = temp_df['Volume'].rolling(window=20).mean().iloc[-1]
        
        triggered = False
        if system_id == 1: # Trend
            if hist_curr['Close'] > hist_curr['SMA200'] and hist_curr['SMA20'] > hist_curr['SMA50'] and \
               hist_curr['MACD'] > hist_curr['MACD_Sig'] and hist_prev['MACD'] <= hist_prev['MACD_Sig']:
                triggered = True
        elif system_id == 2: # Reversal
            pats = get_patterns(temp_df)
            if ("Bullish Engulfing" in pats or "Hammer" in pats) and hist_curr['RSI'] > 30:
                triggered = True
        elif system_id == 3: # Breakout
            res = temp_df['Close'].rolling(window=20).max().iloc[-2]
            if hist_curr['Close'] > res and hist_curr['Volume'] > hist_v_sma * 1.5:
                triggered = True
                
        if triggered:
            total += 1
            # Check next 10 bars for profit
            entry_price = hist_curr['Close']
            future_prices = df['Close'].iloc[i+1 : i+11]
            if not future_prices.empty:
                max_future = future_prices.max()
                min_future = future_prices.min()
                if (max_future - entry_price) / entry_price >= 0.02: # 2% profit target
                    wins += 1
                # elif (min_future - entry_price) / entry_price <= -0.01: # 1% stop loss
                #     pass
                    
    return round((wins / total * 100), 1) if total > 0 else 0

def calculate_supertrend(df, period=10, multiplier=3):
    """
    SuperTrend indicator for trend identification.
    """
    df = df.copy()
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # Calculate ATR
    df['tr'] = np.maximum(high - low, 
                          np.maximum(abs(high - close.shift()), 
                                     abs(low - close.shift())))
    atr = df['tr'].rolling(window=period).mean()
    
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    # Final Upper and Lower Bands
    final_upperband = upperband.copy()
    final_lowerband = lowerband.copy()
    supertrend = pd.Series(index=df.index, data=0.0)
    
    for i in range(1, len(df)):
        if close.iloc[i-1] > final_upperband.iloc[i-1]:
            final_upperband.iloc[i] = min(upperband.iloc[i], final_upperband.iloc[i-1])
        else:
            final_upperband.iloc[i] = upperband.iloc[i]
            
        if close.iloc[i-1] < final_lowerband.iloc[i-1]:
            final_lowerband.iloc[i] = max(lowerband.iloc[i], final_lowerband.iloc[i-1])
        else:
            final_lowerband.iloc[i] = lowerband.iloc[i]
            
        # Current SuperTrend direction
        if supertrend.iloc[i-1] == final_upperband.iloc[i-1]:
            supertrend.iloc[i] = final_upperband.iloc[i] if close.iloc[i] <= final_upperband.iloc[i] else final_lowerband.iloc[i]
        else:
            supertrend.iloc[i] = final_lowerband.iloc[i] if close.iloc[i] >= final_lowerband.iloc[i] else final_upperband.iloc[i]

    return supertrend

def get_vsa_signals(df):
    """
    Volume Spread Analysis basics.
    """
    curr = df.iloc[-1]
    vol_sma = df['Volume'].rolling(window=20).mean().iloc[-1]
    spread = curr['High'] - curr['Low']
    avg_spread = (df['High'] - df['Low']).rolling(window=20).mean().iloc[-1]
    
    signals = []
    # 1. Effort No Result (Potential Reversal)
    if curr['Volume'] > vol_sma * 1.5 and spread < avg_spread * 0.8:
        signals.append("Effort No Result (Zirve/Dip olabilir)")
    # 2. Climax Volume (Trend Exhaustion)
    if curr['Volume'] > vol_sma * 3:
        signals.append("Climax Volume (Dönüş Yakın)")
        
    return signals

def get_signals(df, symbol=""):
    # Fix: Ensure we have enough data
    if len(df) < 30:
        return {"signal": "VERİ BEKLENİYOR", "color": "#f1c40f", "message": "Hesaplama için en az 30 mum gerekli.", "confidence": 0, "insight": ""}

    df = df.copy()
    
    # 1. Technical Indicators (Adaptive)
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA_Trend'] = df['Close'].rolling(window=min(200, len(df)-1)).mean()
    df['RSI'] = calculate_rsi(df)
    df['ADX'] = calculate_adx(df)
    macd, macd_sig = calculate_macd(df)
    df['MACD'] = macd
    df['MACD_Sig'] = macd_sig
    df['SuperTrend'] = calculate_supertrend(df)
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    vol_sma = df['Volume'].rolling(window=20).mean().iloc[-1]
    patterns = get_patterns(df)
    vsa = get_vsa_signals(df)
    
    # Base score (starts at 0)
    score = 0
    
    # --- DYNAMIC BASE SCORING ---
    # Price vs SMA50 (Primary Trend)
    if curr['Close'] > curr['SMA50']: score += 10
    else: score -= 10
    
    # SuperTrend Confirmation (+15)
    if curr['Close'] > curr['SuperTrend']: score += 15
    else: score -= 15
    
    # RSI Momentum
    if curr['RSI'] > prev['RSI'] and curr['RSI'] < 60: score += 5
    elif curr['RSI'] < prev['RSI'] and curr['RSI'] > 40: score -= 5
    
    # Volume Confirmation
    if curr['Volume'] > vol_sma: score += 10
    
    systems_triggered = []
    win_rates = []

    # --- ADVANCED SYSTEMS ---
    # System 1: Trend Following
    if curr['Close'] > curr['SMA_Trend'] and curr['SMA20'] > curr['SMA50'] and \
       curr['MACD'] > curr['MACD_Sig'] and prev['MACD'] <= prev['MACD_Sig']:
        score += 30
        wr = backtest_strategy(df, 1)
        win_rates.append(wr)
        systems_triggered.append(f"Trend Takip (WR: %{wr})")

    # System 2: Reversal
    if ("Bullish Engulfing" in patterns or "Hammer" in patterns) and \
       curr['RSI'] > 30 and prev['RSI'] <= 30:
        score += 35
        wr = backtest_strategy(df, 2)
        win_rates.append(wr)
        systems_triggered.append(f"Dönüş (WR: %{wr})")

    # System 3: Breakout
    resistance = df['Close'].rolling(window=min(20, len(df)-1)).max().iloc[-2]
    if curr['Close'] > resistance and curr['Volume'] > vol_sma * 1.3 and curr['ADX'] > 20:
        score += 30
        wr = backtest_strategy(df, 3)
        win_rates.append(wr)
        systems_triggered.append(f"Kırılım (WR: %{wr})")

    # SAT System logic
    if curr['SMA20'] < curr['SMA50'] and curr['MACD'] < curr['MACD_Sig'] and \
       curr['RSI'] < 70 and prev['RSI'] >= 70:
        score -= 40
        systems_triggered.append("Trend Sonu (SAT)")

    # Sentiment (News Impact)
    sentiment = get_sentiment_impact(symbol)
    score += sentiment

    # Final Scaling: Roughly -80 to +80 mapped to 0-100
    normalized_score = max(0, min(100, int(((score + 80) / 160) * 100)))
    
    avg_win_rate = round(sum(win_rates)/len(win_rates), 1) if win_rates else 0

    if normalized_score >= 70: signal, color = "GÜÇLÜ AL", "#2ecc71"
    elif 55 <= normalized_score < 70: signal, color = "AL", "#27ae60"
    elif 40 < normalized_score < 55: signal, color = "TUT/BEKLE", "#f1c40f"
    elif 25 < normalized_score <= 40: signal, color = "SAT", "#e67e22"
    else: signal, color = "GÜÇLÜ SAT", "#e74c3c"

    message = ", ".join(systems_triggered) if systems_triggered else "Fırsat kollanıyor."
    if vsa: message += f" | VSA: {', '.join(vsa)}"
    
    insight = f"ADX: {round(curr['ADX'],1)} | Trend: {'YUKARI' if curr['Close'] > curr['SuperTrend'] else 'AŞAĞI'}"
    if avg_win_rate > 0: insight += f" | Başarı: %{avg_win_rate}"

    return {
        "signal": signal,
        "color": color,
        "message": message,
        "confidence": normalized_score,
        "insight": insight,
        "win_rate": avg_win_rate,
        "rsi": round(curr['RSI'], 2),
        "sma50": round(curr['SMA50'] if not pd.isna(curr['SMA50']) else 0, 2),
        "price": round(curr['Close'], 2)
    }
