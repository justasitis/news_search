"""
테마별 웹검색 - Google CSE + Brave Search 듀얼 엔진
─────────────────────────────────────────────────
[역할 분담]
• Google CSE  → 물류 전문 사이트 지정 검색 (정밀도 높음)
• Brave Search → 전체 웹 검색 (커버리지 높음, SHE/규제 등 비정형 이슈)

[무료 한도]
• Google CSE  : 100건/일
• Brave Search: 2,000건/월 (≈ 66건/일)
─────────────────────────────────────────────────
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 환경변수 ──
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID      = os.environ.get("GOOGLE_CSE_ID", "")
BRAVE_API_KEY      = os.environ.get("BRAVE_API_KEY", "")

OUTPUT_DIR = Path("pipeline/output")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 검색 테마 및 키워드 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# engine: "google" → Google CSE (전문 사이트 내 검색)
#         "brave"  → Brave Search (전체 웹 검색)
#         "both"   → 양쪽 모두 검색

SEARCH_THEMES = {
    "운송지연_항만적체": {
        "engine": "brave",
        "keywords": [
            "글로벌 해운 지연",
            "항만 적체 컨테이너",
            "supply chain disruption logistics",
        ],
    },
    "SHE_규제_위험물": {
        "engine": "brave",
        "keywords": [
            "배터리 화재 물류 규정",
            "위험물 운송 규정 변경",
            "리튬배터리 보관 인허가",
            "위험물 취급 관리규정 강화",
            "물류센터 화재 안전 규제",
        ],
    },
    "지정학_리스크": {
        "engine": "brave",
        "keywords": [
            "미중 관세 물류 영향",
            "수출 규제 반도체 배터리",
            "글로벌 무역 분쟁 공급망",
        ],
    },
    "운임_유가": {
        "engine": "brave",
        "keywords": [
            "해상운임 동향",
            "항공운임 변동 물류",
            "국제유가 물류비 영향",
        ],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTTP 세션 (retry 포함)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def make_session() -> requests.Session:
    """네트워크 불안정에 대비한 retry 세션 생성"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,           # 1s → 2s → 4s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = make_session()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Google Custom Search API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def google_search(query: str, num_results: int = 3) -> list[dict]:
    """Google CSE로 지정 사이트 내 검색"""
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        print("  ⚠️  Google CSE 키 미설정 → 스킵")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx":  GOOGLE_CSE_ID,
        "q":   query,
        "num": num_results,
        "sort": "date",
        "dateRestrict": "d3",       # 최근 3일
        "lr": "lang_ko|lang_en",
    }

    try:
        resp = SESSION.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  🔍 Google CSE 오류 {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("items", []):
            articles.append({
                "title":         item.get("title", ""),
                "url":           item.get("link", ""),
                "snippet":       item.get("snippet", ""),
                "date":          (item.get("pagemap", {})
                                      .get("metatags", [{}])[0]
                                      .get("article:published_time", "")),
                "search_engine": "google_cse",
            })
        return articles

    except requests.RequestException as e:
        print(f"  ❌ Google 검색 실패 [{query}]: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Brave Search API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def brave_search(query: str, num_results: int = 3) -> list[dict]:
    """Brave Search News API로 전체 웹 검색"""
    if not BRAVE_API_KEY:
        print("  ⚠️  Brave API 키 미설정 → 스킵")
        return []

    url = "https://api.search.brave.com/res/v1/news/search"
    headers = {
        "Accept":             "application/json",
        "Accept-Encoding":    "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q":           query,
        "count":       num_results,
        "freshness":   "pd",        # past day (최근 24시간)
        "search_lang": "ko",
        "country":     "KR",
    }

    try:
        resp = SESSION.get(url, headers=headers, params=params, timeout=15)

        # 429 Rate Limit: 잠시 대기 후 재시도
        if resp.status_code == 429:
            print("  ⏳ Brave Rate Limit → 10초 대기 후 재시도")
            time.sleep(10)
            resp = SESSION.get(url, headers=headers, params=params, timeout=15)

        if resp.status_code != 200:
            print(f"  🔍 Brave 오류 {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("results", []):
            # Brave News API 실제 날짜 필드: page_age (ISO 8601) 또는 age (상대시간)
            date_val = item.get("page_age") or item.get("age", "")
            articles.append({
                "title":         item.get("title", ""),
                "url":           item.get("url", ""),
                "snippet":       item.get("description", ""),
                "date":          date_val,
                "search_engine": "brave",
            })
        return articles

    except requests.RequestException as e:
        print(f"  ❌ Brave 검색 실패 [{query}]: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 중복 제거 (URL 기준)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def deduplicate(articles: list[dict]) -> list[dict]:
    """URL 기준 중복 제거 (먼저 나온 것 우선)"""
    seen = set()
    unique = []
    for a in articles:
        url = a.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(a)
    return unique


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 검색 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_themed_search() -> list[dict]:
    """모든 테마에 대해 지정된 엔진으로 검색 수행"""
    all_results = []
    google_count = 0
    brave_count  = 0

    for theme, config in SEARCH_THEMES.items():
        engine   = config["engine"]
        keywords = config["keywords"]
        print(f"\n{'='*50}")
        print(f"🔎 테마: {theme}  (엔진: {engine})")

        for keyword in keywords:
            results = []

            if engine in ("google", "both"):
                print(f"  🔵 Google CSE → '{keyword}'")
                g_results = google_search(keyword, num_results=3)
                google_count += 1
                results.extend(g_results)
                print(f"     {len(g_results)}건")

            if engine in ("brave", "both"):
                print(f"  🟠 Brave      → '{keyword}'")
                b_results = brave_search(keyword, num_results=3)
                brave_count += 1
                results.extend(b_results)
                print(f"     {len(b_results)}건")
                # Brave 무료 플랜 rate limit 방지 (1초 간격)
                time.sleep(1)

            now = datetime.now().isoformat()
            for r in results:
                r["source"]         = f"search_{theme}"
                r["search_keyword"] = keyword
                r["theme"]          = theme
                r["crawled_at"]     = now

            all_results.extend(results)

    # 중복 제거
    before = len(all_results)
    all_results = deduplicate(all_results)
    after  = len(all_results)

    print(f"\n{'='*50}")
    print(f"📊 검색 완료:")
    print(f"   Google CSE : {google_count}회  (일일 한도 100회)")
    print(f"   Brave      : {brave_count}회  (월간 한도 2,000회)")
    print(f"   총 결과    : {before}건  →  중복 제거 후 {after}건")

    return all_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 엔트리포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "raw_search.json"

    # API 키 상태 출력
    print("🔑 API 키 상태:")
    print(f"   Google CSE : {'✅ 설정됨' if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID else '❌ 미설정'}")
    print(f"   Brave      : {'✅ 설정됨' if BRAVE_API_KEY else '❌ 미설정'}")

    # API 키가 전혀 없으면 빈 파일 저장 후 비정상 종료
    if not GOOGLE_CSE_API_KEY and not BRAVE_API_KEY:
        print("\n❌ 검색 API 키가 하나도 설정되지 않았습니다.")
        print("   GitHub Secrets에 BRAVE_API_KEY 를 등록하세요.")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        sys.exit(1)   # Actions에서 워크플로우를 실패로 표시

    articles = run_themed_search()

    # 결과가 0건이면 경고 (실패는 아님 — 뉴스가 없을 수도 있음)
    if not articles:
        print("\n⚠️  검색 결과 0건. API 응답을 확인하세요.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n📦 {len(articles)}건 저장 완료 → {output_path}")


if __name__ == "__main__":
    main()
