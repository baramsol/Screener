# screener_data.py - MA 10/20/50/100/150/200 전부 미리 계산 (FAST 모드 없음)
# 실행: python screener_data.py
# 결과: data.json (MA 6종 + 재무 + 기술지표 전부)
# 추가: 스마트 업데이트 + ADH-VCP (ETF 없음, 원본 Naver 방식 유지)

import pandas as pd, requests, time, math, os, json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
MARKETS = ["KOSPI", "KOSDAQ"]
MAX_PER_MARKET = 9999
MIN_PRICE = 1000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://m.stock.naver.com/"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ---------- 스마트 업데이트 ----------
def is_market_closed():
    now = datetime.now()
    if now.weekday() >= 5:  # 토/일
        return True
    return now.hour >= 16

def needs_update():
    if not os.path.exists("data.json"):
        return True, "data.json 없음 -> 처음부터 받기"
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        return True, "data.json 깨짐 -> 처음부터 받기"
    updated_raw = str(j.get("updated", ""))
    updated = updated_raw[:10]  # "2026-11-17 06:49" -> "2026-11-17"
    today = datetime.now().strftime("%Y-%m-%d")
    if updated == today and is_market_closed():
        return False, f"이미 오늘({today}) 데이터임 -> 스킵"
    if updated == today and not is_market_closed():
        return True, "오늘 데이터지만 장 중이라 갱신 필요"
    return True, f"오래된 데이터({updated_raw}) -> 갱신 필요"

# ---------- ADH-VCP (Pine Script 그대로) ----------
def calc_adh(df):
    out = {'adh_depth': None, 'adh_contractions': 0, 'adh_last_c_pct': None,
           'adh_dist_line': None, 'adh_coil_range': None, 'adh_vdu': False,
           'adh_base_age': None, 'adh_sl': None, 'adh_trendline': None}
    if df is None or len(df) < 60:
        return out
    try:
        highs = df["High"].values; lows = df["Low"].values
        closes = df["Close"].values; vols = df["Volume"].values
    except Exception:
        return out
    n = len(df); look = 21
    h1_idx = int((n - look) + highs[n - look:].argmax())
    h1 = float(highs[h1_idx]); base_low = float(lows[h1_idx:].min())
    depth = (h1 - base_low) / h1 * 100 if h1 else 999
    out['adh_depth'] = round(float(depth), 2)
    out['adh_base_age'] = int(n - 1 - h1_idx)
    if depth > 35:
        out['adh_dist_line'] = round(float((h1 - closes[-1]) / h1 * 100), 2)
        return out
    pivots = []
    for i in range(3, n - 3):
        if highs[i] == max(highs[i-3:i+4]) and highs[i] < h1 and highs[i] > base_low and i > h1_idx:
            pivots.append((i, float(highs[i])))
    pivots = [p for j, p in enumerate(pivots) if j == 0 or p[1] != pivots[j-1][1]]
    contractions = 0; last_c_pct = None; last_c_low = None
    c1 = (h1 - base_low) / h1 * 100
    if c1 > 0:
        contractions = 1; last_c_pct = c1; last_c_low = base_low
    for k, (p_idx, p_price) in enumerate(pivots):
        end = pivots[k+1][0] if k + 1 < len(pivots) else n
        if end <= p_idx: continue
        seg_low = float(lows[p_idx:end].min())
        if seg_low < p_price:
            c_pct = (p_price - seg_low) / p_price * 100
            if c_pct > 0:
                contractions += 1; last_c_pct = c_pct; last_c_low = seg_low
    out['adh_contractions'] = int(contractions)
    out['adh_last_c_pct'] = round(float(last_c_pct), 2) if last_c_pct is not None else None
    if pivots:
        px_idx, px_price = pivots[-1]
        trendline = h1 + (px_price - h1) / (px_idx - h1_idx) * ((n - 1) - h1_idx) if px_idx != h1_idx else h1
    else:
        trendline = h1
    out['adh_trendline'] = round(float(trendline), 1)
    close = float(closes[-1])
    out['adh_dist_line'] = round(float((trendline - close) / trendline * 100), 2) if trendline else None
    coil_hi = float(highs[-5:].max()); coil_lo = float(lows[-5:].min())
    out['adh_coil_range'] = round(float((coil_hi - coil_lo) / close * 100), 2) if close else None
    vol_low50 = float(vols[-50:].min())
    out['adh_vdu'] = bool(float(vols[-1]) <= vol_low50 * 1.10)
    sl = last_c_low if last_c_low is not None else base_low
    if sl is not None:
        if (close - sl) / close * 100 > 8.0: sl = close * 0.92
        out['adh_sl'] = round(float(sl), 1)
    return out

def parse_int(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    try:
        s = str(v).replace(",", "").replace("원", "").replace(" ", "").strip()
        if s == "" or s == "-":
            return 0
        return int(float(s))
    except:
        return 0

def parse_float(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).replace(",", "").replace("%", "").replace("원", "").replace(" ", "").strip()
        if s == "" or s == "-":
            return 0.0
        return float(s)
    except:
        return 0.0

# ---------- ETF / ETN / 리츠 / 스팩 제외 ----------
# 전에는 이름에 단어가 들어가면 빼는 방식이라 새 브랜드가 다 샜음.
# 이제는 브랜드 접두어 + 포함 키워드 2단계로 나눔.
# BNK처럼 진짜 주식을 빼버리던 과한 키워드는 뺐음.
ETF_PREFIXES = [
    "TIGER", "KODEX", "RISE", "KBSTAR", "ARIRANG", "ACE", "HANARO", "SOL",
    "KINDEX", "KOSEF", "TREX", "PLUS", "TIMEFOLIO", "KoAct", "KOACT",
    "1Q", "WOORI", "HANA", "SHINHAN", "MIRAE", "MIRAEASSET",
    "NH-", "DAISHIN", "FOCUS", "MASTER", "HK", "KIWOOM", "BETA",
    "VALUE", "PULSE", "BULLS", "BEARS", "TIGER ", "KODEX ",
]
ETF_CONTAINS = [
    "ETF", "ETN", "리츠", "REITS", "스팩", "SPAC",
    "인버스", "레버리지", "KOFR", "머니마켓", "CD금리", "국고채",
    "채권", "달러", "미국배당", "다우존스", "S&P", "나스닥",
    "선물", "인버스", "곱버스",
]
def is_etf_name(name):
    if not name:
        return True
    n = str(name).strip()
    # 1. 브랜드 접두어: 이름이 ETF 브랜드로 시작하면 ETF
    for p in ETF_PREFIXES:
        if n.startswith(p):
            return True
    # 2. 포함 키워드: 이름 안에 ETF/ETN/리츠 등이 있으면 ETF
    for k in ETF_CONTAINS:
        if k in n:
            return True
    return False

def get_list():
    out = []
    for market in MARKETS:
        cnt = 0
        for page in range(1, 30):
            try:
                url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100"
                r = SESSION.get(url, timeout=15)
                r.raise_for_status()
                data = r.json()
                stocks = data.get("stocks", [])
                if not stocks and isinstance(data.get("result"), dict):
                    stocks = data["result"].get("stocks", [])
                if not stocks:
                    break
                for s in stocks:
                    code = s.get("itemCode") or s.get("code")
                    name = s.get("stockName") or s.get("name")
                    if not code or not name:
                        continue
                    # 1차: 이름으로 ETF 제외
                    if is_etf_name(name):
                        continue
                    mcap = parse_int(s.get("marketValue") or s.get("marketCap") or 0)
                    out.append((str(code).zfill(6), name, market, mcap))
                    cnt += 1
                    if cnt >= MAX_PER_MARKET:
                        break
                if cnt >= MAX_PER_MARKET or len(stocks) < 100:
                    break
            except Exception as e:
                print(f"  {market} {page} 실패: {e}")
                break
        print(f"  {market}: {cnt}개")
    return out

def fetch_fundamental(code):
    cache_file = os.path.join(CACHE_DIR, f"fund_{code}.json")
    if os.path.exists(cache_file):
        try:
            if datetime.fromtimestamp(os.path.getmtime(cache_file)).strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d"):
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
    try:
        url = f"https://api.stock.naver.com/stock/{code}/basic"
        r = SESSION.get(url, timeout=8)
        basic = r.json() if r.status_code == 200 else {}
        url2 = f"https://api.stock.naver.com/stock/{code}/finance/quarter"
        r2 = SESSION.get(url2, timeout=8)
        fin = r2.json() if r2.status_code == 200 else {}
        eps = 0; per = 0; pbr = 0; roe = 0; sector = ""; mcap2 = 0
        try:
            if isinstance(basic, dict):
                eps = parse_float(basic.get("eps", 0))
                per = parse_float(basic.get("per", 0))
                pbr = parse_float(basic.get("pbr", 0))
                roe = parse_float(basic.get("roe", 0))
                sector = basic.get("industryName", "") or basic.get("sector", "") or ""
                mcap2 = parse_int(basic.get("marketValue", 0) or basic.get("marketCap", 0) or 0)
        except:
            pass
        eps_growth = 0; sales_growth = 0
        try:
            rows = []
            if isinstance(fin, dict):
                rows = fin.get("financeInfo", []) or fin.get("data", []) or []
            elif isinstance(fin, list):
                rows = fin
            if len(rows) >= 5:
                def getf(row, *keys):
                    for k in keys:
                        if k in row and row[k] is not None:
                            return parse_float(row[k])
                    return 0
                cur_eps = getf(rows[0], "eps", "EPS", "netProfit")
                prev_eps = getf(rows[4], "eps", "EPS", "netProfit")
                if prev_eps != 0:
                    eps_growth = (cur_eps - prev_eps) / abs(prev_eps) * 100
                cur_rev = getf(rows[0], "revenue", "sales", "Revenue")
                prev_rev = getf(rows[4], "revenue", "sales", "Revenue")
                if prev_rev != 0:
                    sales_growth = (cur_rev - prev_rev) / abs(prev_rev) * 100
        except:
            pass
        result = {"eps": round(eps,1), "per": round(per,2), "pbr": round(pbr,2), "roe": round(roe,1),
                "eps_growth": round(float(eps_growth),1), "sales_growth": round(float(sales_growth),1),
                "sector": sector, "mcap_api": parse_int(mcap2)}
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except:
            pass
        return result
    except:
        return {"eps": 0, "per": 0, "pbr": 0, "roe": 0, "eps_growth": 0, "sales_growth": 0, "sector": "", "mcap_api": 0}

def fetch_price(code):
    cache_file = os.path.join(CACHE_DIR, f"{code}.csv")
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file)
            if len(df) > 0:
                last = str(df["localDateTime"].iloc[-1])[:10].replace("-", "")
                if last == datetime.now().strftime("%Y%m%d"):
                    return df
        except:
            pass
    try:
        end = datetime.now(); start = end - timedelta(days=400)
        url = f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start.strftime('%Y%m%d')}0000&endDateTime={end.strftime('%Y%m%d')}2359"
        r = SESSION.get(url, timeout=15)
        data = r.json()
        if not data:
            return None
        df = pd.DataFrame(data)
        df.to_csv(cache_file, index=False, encoding="utf-8-sig")
        return df
    except:
        return None

def calc_all(code, name, market, mcap_list, df, kospi_ret, fund):
    # 2차: 이름으로 한 번 더 ETF 제외 — get_list()를 통과한 새 브랜드도 여기서 걸림
    if is_etf_name(name):
        return None
    df = df.dropna(subset=["closePrice"])
    if len(df) < 252:
        return None
    df = df.rename(columns={"closePrice":"Close","highPrice":"High","lowPrice":"Low","accumulatedTradingVolume":"Volume","localDateTime":"Date"})
    close = float(df["Close"].iloc[-1])
    if close < MIN_PRICE or close <= 0:
        return None
    if float(df["High"].max()) <= 0 or float(df["Low"].min()) <= 0:
        return None
    try:
        prev = float(df["Close"].iloc[-2]) or close
    except:
        prev = close
    closes = df["Close"]
    # ★ MA 10/20/50/100/150/200 전부 미리 계산 - SMA + EMA 둘 다
    sma = {}
    ema = {}
    for p in [10, 20, 50, 100, 150, 200]:
        sma[p] = float(closes.rolling(p).mean().iloc[-1])
        ema[p] = float(closes.ewm(span=p, adjust=False).mean().iloc[-1])
    # 200일선 20일 전 (Minervini c4용)
    s200_series = closes.rolling(200).mean()
    sma200_20 = float(s200_series.iloc[-21])
    # 20일 전 MA들도 미리 계산 (추세 확인용)
    sma_20ago = {}
    for p in [10, 20, 50, 100, 150, 200]:
        sma_20ago[p] = float(closes.rolling(p).mean().iloc[-21])
    high52 = float(df["High"].tail(252).max()); low52 = float(df["Low"].tail(252).min())
    if high52 <= 0 or low52 <= 0:
        return None
    vol_avg = float(df["Volume"].rolling(20).mean().iloc[-1]); vol = float(df["Volume"].iloc[-1])
    vol50_avg = float(df["Volume"].rolling(50).mean().iloc[-1])
    _c252 = float(df["Close"].iloc[-252]) or 1
    _c126 = float(df["Close"].iloc[-126]) or 1
    _c63 = float(df["Close"].iloc[-63]) or 1
    _c21 = float(df["Close"].iloc[-21]) or 1
    _c5 = float(df["Close"].iloc[-5]) or 1
    ret1y = (close - _c252)/_c252*100
    ret6m = (close - _c126)/_c126*100
    ret3m = (close - _c63)/_c63*100
    ret1m = (close - _c21)/_c21*100
    ret1w = (close - _c5)/_c5*100
    adr = float(((df["High"]-df["Low"])/df["Close"].replace(0, 1)*100).tail(20).mean())
    vola = float(df["Close"].pct_change().tail(60).std()*100)
    beta = round(vola/1.5, 2) if vola else 1.0
    bb_width = float(df["Close"].tail(20).std()/close*100) if close else 0
    squeeze = bool(bb_width < 2.0)
    # Minervini 8조건 (기본 50/150/200 기준)
    mc = sum([close>sma[150], close>sma[200], sma[150]>sma[200], sma[200]>sma200_20, sma[50]>sma[150]>sma[200], close>sma[50], close>=low52*1.3, close>=high52*0.75])
    stage = 2 if mc==8 else (4 if mc<=3 else 1)
    mcap = mcap_list if mcap_list else fund.get("mcap_api", 0)
    dollar_vol = int(close*vol//100000000)
    result = {
        "name": name, "code": code, "market": market,
        "price": int(close), "change": round((close-prev)/prev*100, 2) if prev else 0,
        "volume": int(vol//100000), "dollar_vol": dollar_vol,
        "vol_ratio": round(vol/vol_avg, 2) if vol_avg else 1.0,
        "vol_50d": round(vol/vol50_avg, 2) if vol50_avg else 1.0,
        # ★ SMA 6종
        "sma10": int(sma[10]), "sma20": int(sma[20]), "sma50": int(sma[50]),
        "sma100": int(sma[100]), "sma150": int(sma[150]), "sma200": int(sma[200]),
        "sma200_up": bool(sma[200]>sma200_20),
        # ★ EMA 6종
        "ema10": int(ema[10]), "ema20": int(ema[20]), "ema50": int(ema[50]),
        "ema100": int(ema[100]), "ema150": int(ema[150]), "ema200": int(ema[200]),
        # ★ 20일 전 SMA (추세 꺾였는지 확인용)
        "sma10_20ago": int(sma_20ago[10]), "sma20_20ago": int(sma_20ago[20]),
        "sma50_20ago": int(sma_20ago[50]), "sma100_20ago": int(sma_20ago[100]),
        "sma150_20ago": int(sma_20ago[150]), "sma200_20ago": int(sma_20ago[200]),
        # ★ 현재가 vs MA (%)
        "vs_sma10": round((close-sma[10])/sma[10]*100, 2) if sma[10] else 0,
        "vs_sma20": round((close-sma[20])/sma[20]*100, 2) if sma[20] else 0,
        "vs_sma50": round((close-sma[50])/sma[50]*100, 2) if sma[50] else 0,
        "vs_sma100": round((close-sma[100])/sma[100]*100, 2) if sma[100] else 0,
        "vs_sma150": round((close-sma[150])/sma[150]*100, 2) if sma[150] else 0,
        "vs_sma200": round((close-sma[200])/sma[200]*100, 2) if sma[200] else 0,
        "vs_ema10": round((close-ema[10])/ema[10]*100, 2) if ema[10] else 0,
        "vs_ema20": round((close-ema[20])/ema[20]*100, 2) if ema[20] else 0,
        "vs_ema50": round((close-ema[50])/ema[50]*100, 2) if ema[50] else 0,
        "vs_ema100": round((close-ema[100])/ema[100]*100, 2) if ema[100] else 0,
        "vs_ema150": round((close-ema[150])/ema[150]*100, 2) if ema[150] else 0,
        "vs_ema200": round((close-ema[200])/ema[200]*100, 2) if ema[200] else 0,
        "high52": int(high52), "low52": int(low52),
        "high_diff": round((close-high52)/high52*100, 1) if high52 else 0, "low_diff": round((close-low52)/low52*100, 1) if low52 else 0,
        "ret1y": round(float(ret1y),1), "ret6m": round(float(ret6m),1), "ret3m": round(float(ret3m),1), "ret1m": round(float(ret1m),1), "ret1w": round(float(ret1w),1),
        "rel_ret": round(float(ret1y-kospi_ret),1),
        "vola": round(vola,2), "adr": round(adr,2), "beta": beta, "bb_width": round(bb_width,2), "squeeze": squeeze,
        "stage": stage,
        "eps": fund.get("eps",0), "per": fund.get("per",0), "pbr": fund.get("pbr",0), "roe": fund.get("roe",0),
        "eps_growth": fund.get("eps_growth",0), "sales_growth": fund.get("sales_growth",0),
        "sector": fund.get("sector",""), "mcap": int(mcap),
        "c1": bool(close>sma[150]), "c2": bool(close>sma[200]), "c3": bool(sma[150]>sma[200]), "c4": bool(sma[200]>sma200_20),
        "c5": bool(sma[50]>sma[150]>sma[200]), "c6": bool(close>sma[50]), "c7": bool(close>=low52*1.3), "c8": bool(close>=high52*0.75),
        "data_days": int(len(df)),
    }
    # ★ ADH-VCP 추가 (원본 로직 안 건드리고, 마지막에 합치기만 함)
    result.update(calc_adh(df))
    return result

if __name__ == "__main__":
    # ★ 스마트 업데이트: 최신이면 바로 스킵
    _need, _reason = needs_update()
    print(_reason)
    if not _need:
        print("최신 데이터라 스킵합니다.")
        exit()
    jobs = get_list()
    print(f"총 {len(jobs)}개 수집 시작 (가격 + 재무)...")
    start = time.time()
    try:
        end = datetime.now(); st = end - timedelta(days=400)
        url = f"https://api.stock.naver.com/chart/domestic/index/KOSPI/day?startDateTime={st.strftime('%Y%m%d')}0000&endDateTime={end.strftime('%Y%m%d')}2359"
        r = SESSION.get(url, timeout=15)
        kdf = pd.DataFrame(r.json()).rename(columns={"closePrice":"Close"})
        _k0 = float(kdf["Close"].iloc[-252]) or 1
        kospi_ret = (float(kdf["Close"].iloc[-1])-_k0)/_k0*100
        print(f"✅ 코스피 1년: {kospi_ret:+.1f}%")
    except Exception as e:
        kospi_ret = 0.0
        print(f"코스피 지수 실패: {e}")
    results = []
    print("1단계: 가격 데이터 수집...")
    price_map = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(fetch_price, code): (code, name, market, mcap) for code, name, market, mcap in jobs}
        done = 0
        for fut in as_completed(futs):
            code, name, market, mcap = futs[fut]
            df = fut.result(); done += 1
            if done % 500 == 0:
                print(f"... 가격 {done}/{len(jobs)} ({time.time()-start:.0f}초)")
            if df is not None:
                price_map[code] = (name, market, mcap, df)
    print(f"✅ 가격 완료: {len(price_map)}개")
    print("2단계: 재무 데이터 수집 (EPS, ROE, PER, 업종) - 30개 병렬...")
    def _do_one(item):
        code, (name, market, mcap, df) = item
        try:
            fund = fetch_fundamental(code)
            calc = calc_all(code, name, market, mcap, df, kospi_ret, fund)
            return calc
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = {ex.submit(_do_one, item): item[0] for item in price_map.items()}
        done = 0
        for fut in as_completed(futs):
            done += 1
            if done % 500 == 0:
                print(f"... 재무 {done}/{len(price_map)} ({time.time()-start:.0f}초)")
            calc = fut.result()
            if calc:
                results.append(calc)
    rs_sorted = sorted(results, key=lambda x: x["rel_ret"])
    n = len(rs_sorted)
    for i, r in enumerate(rs_sorted):
        r["rs"] = int((i+1)/n*99) if n > 0 else 0
    for key, rskey in [("ret1m","rs_1m"), ("ret3m","rs_3m"), ("ret1y","rs_12m")]:
        s = sorted(results, key=lambda x: x[key])
        for i, r in enumerate(s):
            r[rskey] = int((i+1)/len(s)*99) if len(s) > 0 else 0
    out = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "kospi_ret_1y": round(float(kospi_ret),1), "count": len(results), "data": results}
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"✅ 완료: {len(results)}개, {time.time()-start:.0f}초")
    print(f"✅ data.json 저장됨 ({os.path.getsize('data.json')//1024}KB) - MA 10/20/50/100/150/200 전부 포함")
