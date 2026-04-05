import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [설정] GitHub Secrets에서 값을 가져옵니다. ---
NX = int(os.environ.get('KMA_NX', 60))
NY = int(os.environ.get('KMA_NY', 127))
LOCATION_NAME = os.environ.get('LOCATION_NAME', '우리집')
REG_ID_TEMP = os.environ.get('REG_ID_TEMP', '11B10101')
REG_ID_LAND = os.environ.get('REG_ID_LAND', '11B00000')
API_KEY = os.environ.get('KMA_API_KEY')

def get_weather_info(sky, pty):
    """단기 예보(SKY, PTY 조합) 기상청 코드 100% 반영"""
    sky, pty = str(sky), str(pty)
    # 강수 정보가 있는 경우 (PTY)
    if pty != '0':
        if pty in ['1', '4', '5']: return "🌧️", "비/소나기"
        if pty in ['2', '6']: return "🌨️", "비/눈"
        if pty in ['3', '7']: return "❄️", "눈"
        return "🌧️", "강수"
    # 강수 정보가 없는 경우 (SKY)
    if sky == '1': return "☀️", "맑음"
    if sky == '3': return "⛅", "구름많음"
    if sky == '4': return "☁️", "흐림"
    return "🌡️", "정보없음"

def get_mid_emoji(wf):
    """중기 예보(문자열 wf) 기상청 공식 문구 대응"""
    if not wf: return "🌡️"
    if '비' in wf or '소나기' in wf or '적심' in wf: return "🌧️"
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
    cal = Calendar()
    cal.add('X-WR-CALNAME', f'기상청 날씨 ({LOCATION_NAME})')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # --- [1. 단기 예보 수집 (오늘~3일 상세)] ---
    base_date = now.strftime('%Y%m%d')
    # 발표 시간 보정 (기상청 단기예보 발표 시간: 02, 05, 08, 11, 14, 17, 20, 23)
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

    # --- [2. 단기 예보 조립 (매 시간 상세 정보)] ---
    short_limit = (now + timedelta(days=3)).strftime('%Y%m%d')
    for d_str in sorted(forecast_map.keys()):
        if d_str > short_limit: continue
        
        for t_str in sorted(forecast_map[d_str].keys()):
            data = forecast_map[d_str][t_str]
            if 'SKY' in data and 'TMP' in data:
                event = Event()
                emoji, wf_str = get_weather_info(data['SKY'], data['PTY'])
                temp = data['TMP']
                reh = data.get('REH', '-') # 습도
                wsd = data.get('WSD', '-') # 풍속
                pty = data.get('PTY', '0')
                pop = data.get('POP', '0') # 강수확률
                
                # 규칙: 비/눈(PTY > 0) 올 때만 강수확률 표시
                pop_str = f" ☔{pop}%" if pty != '0' else ""
                
                # SUMMARY: [이모지] [날씨상태] [기온]°C [강수확률] 습도[습도]% 풍속[풍속]m/s
                event.add('summary', f"{emoji} {wf_str} {temp}°C{pop_str} 습도{reh}% 풍속{wsd}m/s")
                
                # 시간 설정 (1시간 단위)
                start_time = seoul_tz.localize(datetime.strptime(f"{d_str}{t_str}", '%Y%m%d%H%M'))
                event.add('dtstart', start_time)
                event.add('dtend', start_time + timedelta(hours=1))
                event.add('uid', f"{d_str}{t_str}@short")
                cal.add_component(event)

    # --- [3. 중기 예보 수집 (4일~10일 요약)] ---
    tm_fc = now.strftime('%Y%m%d') + ("0600" if now.hour < 12 else "1800")
    url_mid_temp = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc}&authKey={API_KEY}"
    url_mid_land = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc}&authKey={API_KEY}"
    
    t_res, l_res = fetch_api(url_mid_temp), fetch_api(url_mid_land)
    if t_res and l_res:
        try:
            t_items = t_res['response']['body']['items']['item'][0]
            l_items = l_res['response']['body']['items']['item'][0]
            for i in range(4, 11):
                d_target = (now + timedelta(days=i)).strftime('%Y%m%d')
                event = Event()
                
                # 중기 예보는 오전/오후 중 오후 날씨를 대표값으로 사용
                wf = l_items.get(f'wf{i}Pm') or l_items.get(f'wf{i}') or ""
                t_min = t_items.get(f'taMin{i}')
                t_max = t_items.get(f'taMax{i}')
                
                event.add('summary', f"{get_mid_emoji(wf)} {wf} {t_min}/{t_max}°C")
                event.add('dtstart', (now + timedelta(days=i)).date())
                event.add('dtend', (now + timedelta(days=i+1)).date())
                event.add('uid', f"{d_target}@mid")
                cal.add_component(event)
        except: pass

    # --- [4. 파일 저장] ---
    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    main()
