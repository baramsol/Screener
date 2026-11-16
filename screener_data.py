# screener_data.py - MA 10/20/50/100/150/200 전부 미리 계산 (FAST 모드 없음)
# 실행: python screener_data.py
# 결과: data.json (MA 6종 + 재무 + 기술지표 전부)

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

def get_list():
    EXCLUDE = ["TIGER","KODEX","RISE","KBSTAR","ARIRANG","ACE","HANARO","SOL","KINDEX","KOSEF","TREX","BNK","ETF","ETN","리츠","스팩","선물","인버스","레버리지","KOFR","머니마켓","CD금리","국고채","채권","달러","미국배당","다우존스","S&P","나스닥"]
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
                    if any(k in name for k in EXCLUDE):
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
    return {
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

if __name__ == "__main__":
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
