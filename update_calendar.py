
import os
import sys
import requests
import pytz

from datetime import datetime, timedelta
from icalendar import Calendar, Event


# ============================================================
# 1. 설정
# ============================================================

NX = int(os.environ.get('KMA_NX', 60))
NY = int(os.environ.get('KMA_NY', 127))

LOCATION_NAME = os.environ.get('LOCATION_NAME', '내 위치')
REG_ID_TEMP = os.environ.get('REG_ID_TEMP', '11B10101')
REG_ID_LAND = os.environ.get('REG_ID_LAND', '11B00000')

API_KEY = os.environ['KMA_API_KEY']


# ============================================================
# 2. 날씨 아이콘
# ============================================================

def get_weather_info(sky, pty):
    sky = str(sky)
    pty = str(pty)

    if pty == '1':
        return "🌧️", "비"
    if pty == '2':
        return "🌨️", "비/눈(진눈깨비)"
    if pty == '3':
        return "❄️", "눈"
    if pty == '4':
        return "☔", "소나기"
    if pty == '5':
        return "💧", "빗방울"
    if pty == '6':
        return "🌨️", "빗방울/눈날림"
    if pty == '7':
        return "❄️", "눈날림"

    if sky == '1':
        return "☀️", "맑음"
    if sky == '3':
        return "⛅", "구름많음"
    if sky == '4':
        return "☁️", "흐림"

    return "🌡️", "정보없음"


def get_mid_emoji(wf):
    if not wf:
        return "🌡️"

    wf = wf.replace(" ", "")

    if '소나기' in wf:
        return "☔"
    if '비' in wf:
        return "🌧️"
    if '눈' in wf or '진눈깨비' in wf:
        return "🌨️"
    if '구름많음' in wf:
        return "⛅"
    if '흐림' in wf:
        return "☁️"
    if '맑음' in wf:
        return "☀️"

    return "☀️"


# ============================================================
# 3. 기상청 API 호출
# ============================================================

def fetch_api(url, retries=1, timeout=10):

    safe_url = url.split('&authKey=')[0] + '&authKey=***'

    for attempt in range(1, retries + 1):

        try:
            res = requests.get(url, timeout=timeout)

            if res.status_code != 200:
                print(
                    f"[API FAIL] attempt={attempt}/{retries} "
                    f"status={res.status_code} "
                    f"url={safe_url} "
                    f"body={res.text[:300]}"
                )
                continue

            data = res.json()

            response = data.get('response', {})
            header = response.get('header', {})

            result_code = header.get('resultCode')

            if result_code == '00':
                return data

            result_msg = header.get('resultMsg')

            print(
                f"[API FAIL] attempt={attempt}/{retries} "
                f"resultCode={result_code} "
                f"resultMsg={result_msg} "
                f"url={safe_url}"
            )

        except Exception as e:

            print(
                f"[API EXCEPTION] attempt={attempt}/{retries} "
                f"{type(e).__name__}: {e} "
                f"url={safe_url}"
            )

    print(f"[API GIVEUP] {retries}회 시도 모두 실패 url={safe_url}")

    return None


# ============================================================
# 4. 단기예보 발표 시각 계산
# ============================================================

def get_base_datetime(now):

    release_hours = [2, 5, 8, 11, 14, 17, 20, 23]

    effective_now = now - timedelta(minutes=10)

    valid = [
        h for h in release_hours
        if h <= effective_now.hour
    ]

    if valid:

        base_h = max(valid)

        return (
            effective_now.strftime('%Y%m%d'),
            f"{base_h:02d}00"
        )

    else:

        prev = effective_now - timedelta(days=1)

        return (
            prev.strftime('%Y%m%d'),
            "2300"
        )


# ============================================================
# 5. 중기예보 발표 시각 후보
# ============================================================

def get_tmfc_candidates(now):

    candidates = []

    effective_now = now - timedelta(minutes=30)

    if effective_now.hour < 6:

        c1 = (
            effective_now - timedelta(days=1)
        ).replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0
        )

        c2 = (
            effective_now - timedelta(days=2)
        ).replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0
        )

    elif effective_now.hour < 18:

        c1 = effective_now.replace(
            hour=6,
            minute=0,
            second=0,
            microsecond=0
        )

        c2 = (
            effective_now - timedelta(days=1)
        ).replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0
        )

    else:

        c1 = effective_now.replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0
        )

        c2 = effective_now.replace(
            hour=6,
            minute=0,
            second=0,
            microsecond=0
        )

    candidates.append(c1)
    candidates.append(c2)

    return candidates


# ============================================================
# 6. 기존 ICS 캐시 읽기
# ============================================================

def load_cached_events(ics_path):

    cache = {}

    if not os.path.exists(ics_path):
        return cache

    try:

        with open(ics_path, 'rb') as f:
            cal = Calendar.from_ical(f.read())

        for component in cal.walk():

            if component.name == 'VEVENT':

                dtstart = component.get('dtstart')

                if dtstart:

                    d = dtstart.dt

                    if hasattr(d, 'strftime'):

                        d_str = d.strftime('%Y%m%d')

                        cache[d_str] = component.to_ical()

    except Exception as e:

        print(f"[CACHE ERROR] {type(e).__name__}: {e}")

    return cache


def event_from_cache(raw_ical):

    try:

        wrapped = (
            b"BEGIN:VCALENDAR\r\n"
            b"VERSION:2.0\r\n"
            + raw_ical
            + b"\r\nEND:VCALENDAR"
        )

        cal = Calendar.from_ical(wrapped)

        for component in cal.walk():

            if component.name == 'VEVENT':
                return component

    except Exception as e:

        print(f"[CACHE PARSE ERROR] {type(e).__name__}: {e}")

    return None


# ============================================================
# 7. 메인 실행
# ============================================================

def main():

    seoul_tz = pytz.timezone('Asia/Seoul')

    now = datetime.now(seoul_tz)

    today_str = now.strftime('%Y%m%d')

    update_ts = now.strftime('%Y-%m-%d %H:%M:%S')

    today_dt = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    # --------------------------------------------------------
    # 기존 예보 기간 유지: 변경하지 않음
    # --------------------------------------------------------

    short_end_str = (
        today_dt + timedelta(days=3)
    ).strftime('%Y%m%d')

    mid_start_dt = today_dt + timedelta(days=4)

    mid_end_dt = today_dt + timedelta(days=10)

    print("=" * 60)
    print("[실행 시작]")
    print("현재 시간:", now.strftime('%Y-%m-%d %H:%M:%S'))
    print("위치:", LOCATION_NAME)
    print("단기 예보 종료:", short_end_str)
    print("중기 예보 시작:", mid_start_dt.strftime('%Y%m%d'))
    print("중기 예보 종료:", mid_end_dt.strftime('%Y%m%d'))
    print("=" * 60)

    cal = Calendar()

    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    processed_dates = set()

    api_fallback_occurred = False

    cached_events = load_cached_events('weather.ics')

    print("캐시된 날짜들:", sorted(cached_events.keys()))


    # ========================================================
    # 8. 단기 예보: D+0 ~ D+3
    # ========================================================

    base_date, base_time = get_base_datetime(now)

    print(
        f"[단기예보] 요청 base_date={base_date} "
        f"base_time={base_time}"
    )

    url_short = (
        "https://apihub.kma.go.kr/api/typ02/openApi/"
        "VilageFcstInfoService_2.0/getVilageFcst"
        f"?dataType=JSON"
        f"&base_date={base_date}"
        f"&base_time={base_time}"
        f"&nx={NX}"
        f"&ny={NY}"
        f"&numOfRows=1000"
        f"&authKey={API_KEY}"
    )

    forecast_map = {}

    short_res = fetch_api(url_short)

    if short_res is None:

        print("[단기예보] API 실패 -> 캐시 재사용 예정")

        api_fallback_occurred = True

    else:

        try:

            items = (
                short_res['response']['body']['items']['item']
            )

            for it in items:

                d = it['fcstDate']
                t = it['fcstTime']
                cat = it['category']
                val = it['fcstValue']

                if d not in forecast_map:
                    forecast_map[d] = {}

                if t not in forecast_map[d]:
                    forecast_map[d][t] = {}

                forecast_map[d][t][cat] = val

        except Exception as e:

            print(
                f"[단기예보] 데이터 파싱 실패: "
                f"{type(e).__name__}: {e}"
            )

            api_fallback_occurred = True


    cache = {
        'TMP': '15',
        'SKY': '1',
        'PTY': '0',
        'REH': '50',
        'WSD': '1.0',
        'POP': '0'
    }

    for d_str in sorted(forecast_map.keys()):

        if d_str < today_str or d_str > short_end_str:
            continue

        day_data = forecast_map[d_str]

        tmps = [
            float(day_data[t]['TMP'])
            for t in day_data
            if 'TMP' in day_data[t]
        ]

        if not tmps:
            continue

        t_min = int(min(tmps))
        t_max = int(max(tmps))

        rep_t = (
            '1200'
            if '1200' in day_data
            else sorted(day_data.keys())[0]
        )

        rep_emoji, _ = get_weather_info(
            day_data[rep_t].get('SKY', cache['SKY']),
            day_data[rep_t].get('PTY', cache['PTY'])
        )

        desc = []

        has_future_data = False

        for h in range(24):

            t_str = f"{h:02d}00"

            event_time = seoul_tz.localize(
                datetime.strptime(
                    f"{d_str}{t_str}",
                    '%Y%m%d%H%M'
                )
            )

            if t_str in day_data:

                for cat in cache.keys():

                    if cat in day_data[t_str]:
                        cache[cat] = day_data[t_str][cat]

            if event_time >= now:

                emoji, wf_str = get_weather_info(
                    cache['SKY'],
                    cache['PTY']
                )

                details = []

                if cache['PTY'] != '0':
                    details.append(f"☔{cache['POP']}%")

                details.append(f"💧{cache['REH']}%")
                details.append(f"🚩{cache['WSD']}m/s")

                desc.append(
                    f"[{t_str[:2]}시] {emoji} {wf_str} "
                    f"{cache['TMP']}°C "
                    f"({' '.join(details)})"
                )

                has_future_data = True

        if not has_future_data:
            continue

        event = Event()

        event.add(
            'summary',
            f"{rep_emoji} {t_min}°C/{t_max}°C"
        )

        event.add('location', LOCATION_NAME)

        desc.append(
            f"\n최종 업데이트: {update_ts} (KST)"
        )

        event.add('description', "\n".join(desc))

        event.add(
            'dtstart',
            datetime.strptime(
                d_str,
                '%Y%m%d'
            ).date()
        )

        event.add(
            'dtend',
            datetime.strptime(
                d_str,
                '%Y%m%d'
            ).date() + timedelta(days=1)
        )

        event.add('uid', f"{d_str}@short_summary")

        cal.add_component(event)

        processed_dates.add(d_str)

        print(f"[단기예보 생성] {d_str}")


    # --------------------------------------------------------
    # 단기 API 실패 시 기존 캐시 재사용
    # --------------------------------------------------------

    for delta in range(4):

        d_str = (
            today_dt + timedelta(days=delta)
        ).strftime('%Y%m%d')

        if (
            d_str not in processed_dates
            and d_str in cached_events
        ):

            event = event_from_cache(
                cached_events[d_str]
            )

            if event:

                cal.add_component(event)

                processed_dates.add(d_str)

                print(f"[단기 캐시 재사용] {d_str}")


    # ========================================================
    # 9. 중기 예보: D+4 ~ D+10
    # ========================================================

    tmfc_candidates = get_tmfc_candidates(now)

    t_res = None
    l_res = None
    tm_fc_dt = None

    for candidate in tmfc_candidates:

        tm_fc_str = candidate.strftime('%Y%m%d%H%M')

        print(f"[중기예보] 요청 tmFc={tm_fc_str}")

        url_mid_temp = (
            "https://apihub.kma.go.kr/api/typ02/openApi/"
            "MidFcstInfoService/getMidTa"
            f"?dataType=JSON"
            f"&regId={REG_ID_TEMP}"
            f"&tmFc={tm_fc_str}"
            f"&authKey={API_KEY}"
        )

        url_mid_land = (
            "https://apihub.kma.go.kr/api/typ02/openApi/"
            "MidFcstInfoService/getMidLandFcst"
            f"?dataType=JSON"
            f"&regId={REG_ID_LAND}"
            f"&tmFc={tm_fc_str}"
            f"&authKey={API_KEY}"
        )

        t_try = fetch_api(url_mid_temp)

        if t_try is None:

            print(
                f"[중기예보] tmFc={tm_fc_str} "
                "온도 API 실패 -> 다음 후보"
            )

            continue

        l_try = fetch_api(url_mid_land)

        if t_try and l_try:

            t_res = t_try
            l_res = l_try
            tm_fc_dt = candidate

            print(f"[중기예보] 사용 후보: {tm_fc_str}")

            break


    if tm_fc_dt is None:

        print(
            "[중기예보] 모든 후보 실패 -> 캐시 재사용 예정"
        )

        api_fallback_occurred = True


    t_items = None
    l_items = None

    if t_res and l_res and tm_fc_dt:

        try:

            t_items = (
                t_res['response']['body']['items']['item'][0]
            )

            l_items = (
                l_res['response']['body']['items']['item'][0]
            )

        except Exception as e:

            print(
                f"[중기예보] 파싱 실패: "
                f"{type(e).__name__}: {e}"
            )

            api_fallback_occurred = True


    # --------------------------------------------------------
    # D+4 ~ D+10 순서대로 생성
    # --------------------------------------------------------

    cur_dt = mid_start_dt

    while cur_dt <= mid_end_dt:

        d_str = cur_dt.strftime('%Y%m%d')

        event = None

        # 1순위: 새 중기 데이터

        if t_items and l_items and tm_fc_dt:

            field_i = (
                cur_dt.date() - tm_fc_dt.date()
            ).days

            t_min = t_items.get(f'taMin{field_i}')
            t_max = t_items.get(f'taMax{field_i}')

            wf_rep = (
                l_items.get(f'wf{field_i}Pm')
                if field_i <= 7
                else l_items.get(f'wf{field_i}')
            )

            if (
                t_min is not None
                and t_max is not None
                and wf_rep is not None
            ):

                mid_desc = []

                if field_i <= 7:

                    wf_am = l_items.get(f'wf{field_i}Am')
                    wf_pm = l_items.get(f'wf{field_i}Pm')

                    rn_am = l_items.get(f'rnSt{field_i}Am')
                    rn_pm = l_items.get(f'rnSt{field_i}Pm')

                    mid_desc.append(
                        f"[오전] {get_mid_emoji(wf_am)} "
                        f"{wf_am} (☔{rn_am}%)"
                    )

                    mid_desc.append(
                        f"[오후] {get_mid_emoji(wf_pm)} "
                        f"{wf_pm} (☔{rn_pm}%)"
                    )

                else:

                    wf_val = l_items.get(f'wf{field_i}')
                    rn_st = l_items.get(f'rnSt{field_i}')

                    mid_desc.append(
                        f"[종일] {get_mid_emoji(wf_val)} "
                        f"{wf_val} (☔{rn_st}%)"
                    )

                mid_desc.append(
                    f"\n최종 업데이트: {update_ts} (KST)"
                )

                event = Event()

                event.add(
                    'summary',
                    f"{get_mid_emoji(wf_rep)} "
                    f"{t_min}/{t_max}°C"
                )

                event.add('location', LOCATION_NAME)

                event.add(
                    'description',
                    "\n".join(mid_desc)
                )

                event.add('dtstart', cur_dt.date())

                event.add(
                    'dtend',
                    (cur_dt + timedelta(days=1)).date()
                )

                event.add('uid', f"{d_str}@mid")


        # 2순위: 기존 캐시 재사용

        if event is None and d_str in cached_events:

            event = event_from_cache(
                cached_events[d_str]
            )

            if event:
                print(f"[중기 캐시 재사용] {d_str}")


        if event is not None:

            cal.add_component(event)

            processed_dates.add(d_str)

            print(f"[중기예보 생성] {d_str}")

        else:

            print(f"[예보 누락] {d_str}")

            api_fallback_occurred = True

        cur_dt += timedelta(days=1)


    # ========================================================
    # 10. 결과 확인 및 ICS 저장
    # ========================================================

    print("=" * 60)

    print(
        "최종 processed_dates:",
        sorted(processed_dates)
    )

    print(
        "생성된 일정 개수:",
        len(processed_dates)
    )

    print(
        "API fallback 발생:",
        api_fallback_occurred
    )

    print("=" * 60)


    if not processed_dates:

        print("[ERROR] 생성된 날씨 일정이 없습니다.")

        sys.exit(1)


    # ICS 파일 생성

    with open('weather.ics', 'wb') as f:

        f.write(cal.to_ical())


    print("[ICS 저장 완료] weather.ics")


    # ========================================================
    # 11. 최종 성공 / 실패 판정
    # ========================================================

    if api_fallback_occurred:

        print(
            "[결과] 일부 예보를 API에서 가져오지 못했습니다. "
            "캐시 데이터가 사용되었거나 예보가 누락되었습니다."
        )

        sys.exit(1)

    else:

        print(
            "[결과] 모든 예보를 정상적으로 갱신했습니다."
        )

        sys.exit(0)


if __name__ == "__main__":

    main()
