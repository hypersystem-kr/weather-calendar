import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [설정] ---
NX = int(os.environ['KMA_NX'])
NY = int(os.environ['KMA_NY'])
LOCATION_NAME = os.environ['LOCATION_NAME']
REG_ID_TEMP = os.environ['REG_ID_TEMP']
REG_ID_LAND = os.environ['REG_ID_LAND']
API_KEY = os.environ['KMA_API_KEY']

def get_weather_info(sky, pty):
    sky, pty = str(sky), str(pty)
    if pty != '0':
        if pty in ['1', '4', '5']: return "🌧️", "비/소나기"
        if pty in ['2', '6']: return "🌨️", "비/눈"
        if pty in ['3', '7']: return "❄️", "눈"
        return "🌧️", "강수"
    if sky == '1': return "☀️", "맑음"
    if sky == '3': return "⛅", "구름많음"
    if sky == '4': return "☁️", "흐림"
    return "🌡️", "정보없음"

def get_mid_emoji(wf):
    if not wf: return "🌡️"
    wf = wf.replace(" ", "")
    if '비' in wf or '소나기' in wf: return "🌧️"
    if '눈' in wf or '진눈깨비' in wf: return "🌨️"
    if '구름많음' in wf: return "⛅"
    if '흐림' in wf: return "☁️"
    if '맑음' in wf: return "☀️"
    return "☀️"

def fetch_api(url):
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200: return res.json()
    except: return None
    return None

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    update_ts = now.strftime('%Y-%m-%d %H:%M:%S')
    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # --- [1. 단기 예보 수집] ---
    base_date = now.strftime('%Y%m%d')
    base_h = max([h for h in [2, 5, 8, 11, 14, 17, 20, 23] if h <= now.hour], default=2)
    base_time = f"{base_h:02d}00"
    url_short = f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?dataType=JSON&base_date={base_date}&base_time={base_time}&nx={NX}&ny={NY}&numOfRows=1000&authKey={API_KEY}"
    
    forecast_map = {}
    short_res = fetch_api(url_short)
    if short_res and 'response' in short_res and 'body' in short_res['response']:
        items = short_res['response']['body']['items']['item']
        for it in items:
            d, t, cat, val = it['fcstDate'], it['fcstTime'], it['category'], it['fcstValue']
            if d not in forecast_map: forecast_map[d] = {}
            if t not in forecast_map[d]: forecast_map[d][t] = {}
            forecast_map[d][t][cat] = val

    # 단기 예보 일정을 생성한 날짜들을 저장 (중기 예보와 겹침 방지)
    processed_dates = set()

    for d_str in sorted(forecast_map.keys()):
        day_data = forecast_map[d_str]
        tmps = [float(day_data[t]['TMP']) for t in day_data if 'TMP' in day_data[t]]
        if not tmps: continue
        
        t_min, t_max = int(min(tmps)), int(max(tmps))
        rep_t = '1200' if '1200' in day_data else sorted(day_data.keys())[0]
        rep_emoji, _ = get_weather_info(day_data[rep_t].get('SKY','1'), day_data[rep_t].get('PTY','0'))
        
        event = Event()
        event.add('summary', f"{rep_emoji} {t_min}°C/{t_max}°C")
        event.add('location', LOCATION_NAME)
        
        desc = []
        last_info = None
        for h in range(24):
            t_str = f"{h:02d}00"
            if t_str in day_data: last_info = day_data[t_str]
            if last_info:
                emoji, wf_str = get_weather_info(last_info['SKY'], last_info['PTY'])
                temp, reh, wsd, pty, pop = last_info['TMP'], last_info.get('REH','-'), last_info.get('WSD','-'), last_info.get('PTY','0'), last_info.get('POP','0')
                pop_prefix = f"☔{pop}% " if pty != '0' else ""
                desc.append(f"[{t_str[:2]}시] {emoji} {wf_str} {temp}°C ({pop_prefix}💧{reh}%, 🚩{wsd}m/s)")
        
        desc.append(f"\n최종 업데이트: {update_ts} (KST)")
        event.add('description', "\n".join(desc))
        event_date = datetime.strptime(d_str, '%Y%m%d').date()
        event.add('dtstart', event_date); event.add('dtend', event_date + timedelta(days=1))
        event.add('uid', f"{d_str}@short_summary")
        cal.add_component(event)
        processed_dates.add(d_str)

    # --- [2. 중기 예보 수집] ---
    tm_fc = now.strftime('%Y%m%d') + ("0600" if now.hour < 12 else "1800")
    url_mid_temp = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc}&authKey={API_KEY}"
    url_mid_land = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc}&authKey={API_KEY}"
    
    t_res, l_res = fetch_api(url_mid_temp), fetch_api(url_mid_land)
    if t_res and l_res and 'response' in t_res and 'response' in l_res:
        try:
            t_items = t_res['response']['body']['items']['item'][0]
            l_items = l_res['response']['body']['items']['item'][0]
            
            # 3일 후부터 10일 후까지 전체를 훑음
            for i in range(3, 11):
                d_target_dt = now + timedelta(days=i)
                d_target_str = d_target_dt.strftime('%Y%m%d')
                
                # 이미 단기 예보로 처리된 날짜는 건너뜀 (중복 방지)
                if d_target_str in processed_dates:
                    continue

                t_min = t_items.get(f'taMin{i}')
                t_max = t_items.get(f'taMax{i}')
                
                # 기온 데이터가 없으면(None) 출력하지 않음
                if t_min is None or t_max is None:
                    continue

                event = Event()
                mid_desc = []
                if i <= 7:
                    wf_am, wf_pm = l_items.get(f'wf{i}Am'), l_items.get(f'wf{i}Pm')
                    rn_am, rn_pm = l_items.get(f'rnSt{i}Am'), l_items.get(f'rnSt{i}Pm')
                    wf_rep = wf_pm if wf_pm else wf_am
                    if not wf_rep: continue # 날씨 정보 없으면 패스
                    mid_desc.append(f"[오전] {get_mid_emoji(wf_am)} {wf_am} (☔{rn_am}%)")
                    mid_desc.append(f"[오후] {get_mid_emoji(wf_pm)} {wf_pm} (☔{rn_pm}%)")
                else:
                    wf_rep = l_items.get(f'wf{i}')
                    rn_st = l_items.get(f'rnSt{i}')
                    if not wf_rep: continue # 날씨 정보 없으면 패스
                    mid_desc.append(f"[종일] {get_mid_emoji(wf_rep)} {wf_rep} (☔{rn_st}%)")

                event.add('summary', f"{get_mid_emoji(wf_rep)} {wf_rep} {t_min}/{t_max}°C")
                event.add('location', LOCATION_NAME)
                mid_desc.append(f"\n최종 업데이트: {update_ts} (KST)")
                event.add('description', "\n".join(mid_desc))
                
                event_date = d_target_dt.date()
                event.add('dtstart', event_date); event.add('dtend', event_date + timedelta(days=1))
                event.add('uid', f"{d_target_str}@mid")
                cal.add_component(event)
        except Exception as e:
            print(f"중기 예보 에러: {e}")

    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    main()
