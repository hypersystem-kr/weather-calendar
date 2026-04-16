import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [1. 설정] ---
NX = int(os.environ.get('KMA_NX', 60))
NY = int(os.environ.get('KMA_NY', 127))
LOCATION_NAME = os.environ.get('LOCATION_NAME', '내 위치')
REG_ID_TEMP = os.environ.get('REG_ID_TEMP', '11B10101')
REG_ID_LAND = os.environ.get('REG_ID_LAND', '11B00000')
API_KEY = os.environ['KMA_API_KEY']

def get_weather_info(sky, pty):
    sky, pty = str(sky), str(pty)
    if pty == '1': return "🌧️", "비"
    if pty == '2': return "🌨️", "비/눈(진눈깨비)"
    if pty == '3': return "❄️", "눈"
    if pty == '4': return "☔", "소나기"
    if pty == '5': return "💧", "빗방울"
    if pty == '6': return "🌨️", "빗방울/눈날림"
    if pty == '7': return "❄️", "눈날림"
    if sky == '1': return "☀️", "맑음"
    if sky == '3': return "⛅", "구름많음"
    if sky == '4': return "☁️", "흐림"
    return "🌡️", "정보없음"

def get_mid_emoji(wf):
    if not wf: return "🌡️"
    wf = wf.replace(" ", "")
    if '소나기' in wf: return "☔"
    if '비' in wf: return "🌧️"
    if '눈' in wf or '진눈깨비' in wf: return "🌨️"
    if '구름많음' in wf: return "⛅"
    if '흐림' in wf: return "☁️"
    if '맑음' in wf: return "☀️"
    return "☀️"

def fetch_api(url):
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get('response', {}).get('header', {}).get('resultCode') == '00':
                return data
        return None
    except:
        return None

def get_base_datetime(now):
    """
    단기예보 발표 시각: 02, 05, 08, 11, 14, 17, 20, 23시
    안전하게 10분 지연 후 데이터를 가져옴.
    """
    release_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    effective_now = now - timedelta(minutes=10)
    valid = [h for h in release_hours if h <= effective_now.hour]
    if valid:
        base_h = max(valid)
        return effective_now.strftime('%Y%m%d'), f"{base_h:02d}00"
    else:
        prev = effective_now - timedelta(days=1)
        return prev.strftime('%Y%m%d'), "2300"

def get_tmfc_candidates(now):
    """중기예보 tmFc 후보 생성 (오전 6시, 오후 18시)"""
    candidates = []
    effective_now = now - timedelta(minutes=30)
    if effective_now.hour < 6:
        c1 = (effective_now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        c2 = (effective_now - timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    elif effective_now.hour < 18:
        c1 = effective_now.replace(hour=6, minute=0, second=0, microsecond=0)
        c2 = (effective_now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        c1 = effective_now.replace(hour=18, minute=0, second=0, microsecond=0)
        c2 = effective_now.replace(hour=6, minute=0, second=0, microsecond=0)
    candidates.append(c1)
    candidates.append(c2)
    return candidates

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    update_ts = now.strftime('%Y-%m-%d %H:%M:%S')

    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # --- [2. 단기 예보] ---
    base_date, base_time = get_base_datetime(now)
    url_short = (
        f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
        f"?dataType=JSON&base_date={base_date}&base_time={base_time}"
        f"&nx={NX}&ny={NY}&numOfRows=1000&authKey={API_KEY}"
    )

    forecast_map = {}
    short_res = fetch_api(url_short)
    processed_dates = set()

    if short_res and 'body' in short_res['response']:
        items = short_res['response']['body']['items']['item']
        for it in items:
            d, t, cat, val = it['fcstDate'], it['fcstTime'], it['category'], it['fcstValue']
            if d not in forecast_map: forecast_map[d] = {}
            if t not in forecast_map[d]: forecast_map[d][t] = {}
            forecast_map[d][t][cat] = val

    cache = {'TMP': '15', 'SKY': '1', 'PTY': '0', 'REH': '50', 'WSD': '1.0', 'POP': '0'}
    short_term_limit = (now + timedelta(days=3)).strftime('%Y%m%d')

    for d_str in sorted(forecast_map.keys()):
        if d_str > short_term_limit: continue
        day_data = forecast_map[d_str]
        tmps = [float(day_data[t]['TMP']) for t in day_data if 'TMP' in day_data[t]]
        if not tmps: continue
        
        t_min, t_max = int(min(tmps)), int(max(tmps))
        rep_t = '1200' if '1200' in day_data else sorted(day_data.keys())[0]
        rep_emoji, _ = get_weather_info(day_data[rep_t].get('SKY', cache['SKY']), day_data[rep_t].get('PTY', cache['PTY']))
        
        desc = []
        # [수정] 현재 시각 이후 필터링을 제거하여 해당 날짜의 전체 예보 데이터를 담음
        for h in range(24):
            t_str = f"{h:02d}00"
            if t_str in day_data:
                for cat in cache.keys():
                    if cat in day_data[t_str]: cache[cat] = day_data[t_str][cat]
                
                emoji, wf_str = get_weather_info(cache['SKY'], cache['PTY'])
                details = []
                if cache['PTY'] != '0':
                    details.append(f"☔{cache['POP']}%")
                details.append(f"💧{cache['REH']}%")
                details.append(f"🚩{cache['WSD']}m/s")
                details_str = " ".join(details)
                desc.append(f"[{t_str[:2]}시] {emoji} {wf_str} {cache['TMP']}°C ({details_str})")

        if not desc: continue

        event = Event()
        event.add('summary', f"{rep_emoji} {t_min}°C/{t_max}°C")
        event.add('location', LOCATION_NAME)
        desc.append(f"\n최종 업데이트: {update_ts} (KST)")
        event.add('description', "\n".join(desc))
        
        event_date = datetime.strptime(d_str, '%Y%m%d').date()
        event.add('dtstart', event_date)
        event.add('dtend', event_date + timedelta(days=1))
        event.add('uid', f"{d_str}@short_summary")
        cal.add_component(event)
        processed_dates.add(d_str)

    # --- [3. 중기 예보] ---
    tmfc_candidates = get_tmfc_candidates(now)
    t_res, l_res, tm_fc_dt = None, None, None
    for candidate in tmfc_candidates:
        tm_fc_str = candidate.strftime('%Y%m%d%H%M')
        url_mid_temp = (
            f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa"
            f"?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc_str}&authKey={API_KEY}"
        )
        url_mid_land = (
            f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst"
            f"?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc_str}&authKey={API_KEY}"
        )
        t_try = fetch_api(url_mid_temp)
        l_try = fetch_api(url_mid_land)
        if t_try and l_try:
            t_res, l_res, tm_fc_dt = t_try, l_try, candidate
            break

    if t_res and l_res and tm_fc_dt:
        try:
            t_items = t_res['response']['body']['items']['item'][0]
            l_items = l_res['response']['body']['items']['item'][0]
        except:
            t_items, l_items = None, None

        if t_items and l_items:
            for i in range(3, 11):
                d_target_dt = tm_fc_dt + timedelta(days=i)
                d_target_str = d_target_dt.strftime('%Y%m%d')
                if d_target_str in processed_dates: continue
                if d_target_str < now.strftime('%Y%m%d'): continue

                t_min = t_items.get(f'taMin{i}')
                t_max = t_items.get(f'taMax{i}')
                wf_rep = l_items.get(f'wf{i}Pm') if i <= 7 else l_items.get(f'wf{i}')
                if t_min is None or t_max is None or wf_rep is None: continue

                event = Event()
                mid_desc = []
                if i <= 7:
                    wf_am, wf_pm = l_items.get(f'wf{i}Am'), l_items.get(f'wf{i}Pm')
                    rn_am, rn_pm = l_items.get(f'rnSt{i}Am'), l_items.get(f'rnSt{i}Pm')
                    mid_desc.append(f"[오전] {get_mid_emoji(wf_am)} {wf_am} (☔{rn_am}%)")
                    mid_desc.append(f"[오후] {get_mid_emoji(wf_pm)} {wf_pm} (☔{rn_pm}%)")
                else:
                    wf_val, rn_st = l_items.get(f'wf{i}'), l_items.get(f'rnSt{i}')
                    mid_desc.append(f"[종일] {get_mid_emoji(wf_val)} {wf_val} (☔{rn_st}%)")

                event.add('summary', f"{get_mid_emoji(wf_rep)} {t_min}/{t_max}°C")
                event.add('location', LOCATION_NAME)
                mid_desc.append(f"\n최종 업데이트: {update_ts} (KST)")
                event.add('description', "\n".join(mid_desc))
                event_date = d_target_dt.date()
                event.add('dtstart', event_date)
                event.add('dtend', event_date + timedelta(days=1))
                event.add('uid', f"{d_target_str}@mid")
                cal.add_component(event)

    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    main()
