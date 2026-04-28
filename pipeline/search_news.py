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
from datetime import datetime
from pathlib import Path

import requests

# ── 환경변수 ──
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

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
        "engine": "brave",     # 규제/사고는 전체 웹이 효과적
        "keywords": [
            "배터리 화재 물류 규정",
            "위험물 운송 규정 변경",
            "리튬배터리 보관 인허가",
            "위험물 취급 관리규정 강화",
            "물류센터 화재 안전 규제",
        ],
    },
    "지정학_리스크": {
        "engine": "brave",     # 뉴스 속보는 전체 웹이 빠름
        "keywords": [
            "미중 관세 물류 영향",
            "수출 규제 반도체 배터리",
            "글로벌 무역 분쟁 공급망",
        ],
    },
    "운임_유가": {
        "engine": "brave",    # 전문 사이트에 정확한 데이터
        "keywords": [
            "해상운임 동향",
            "항공운임 변동 물류",
            "국제유가 물류비 영향",
        ],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Google Custom Search API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def google_search(query: str, num_results: int = 3) -> list[dict]:
    """Google CSE로 지정 사이트 내 검색"""
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        print("  ⚠️ Google CSE 키 미설정 → 스킵")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": num_results,
        "sort": "date",
        "dateRestrict": "d3",       # 최근 3일
        "lr": "lang_ko|lang_en",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"  🔍 Google CSE 응답: {resp.text[:300]}")
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("items", []):
            articles.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("pagemap", {})
                             .get("metatags", [{}])[0]
                             .get("article:published_time", ""),
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
    """Brave Search로 전체 웹 검색"""
    if not BRAVE_API_KEY:
        print("  ⚠️ Brave API 키 미설정 → 스킵")
        return []

    url = "https://api.search.brave.com/res/v1/news/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": num_results,
        "freshness": "pd",          # 최근 24시간 (pd=past day)
        "search_lang": "ko",
        "country": "KR",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("results", []):
            articles.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "date": item.get("age", ""),
                "search_engine": "brave",
            })
        return articles

    except requests.RequestException as e:
        print(f"  ❌ Brave 검색 실패 [{query}]: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 검색 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_themed_search() -> list[dict]:
    """모든 테마에 대해 지정된 엔진으로 검색 수행"""
    all_results = []
    google_count = 0
    brave_count = 0

    for theme, config in SEARCH_THEMES.items():
        engine = config["engine"]
        keywords = config["keywords"]
        print(f"\n{'='*50}")
        print(f"🔎 테마: {theme} (엔진: {engine})")

        for keyword in keywords:
            results = []

            # Google CSE 검색
            if engine in ("google", "both"):
                print(f"  🔵 Google CSE → '{keyword}'")
                g_results = google_search(keyword, num_results=3)
                google_count += 1
                results.extend(g_results)
                print(f"     {len(g_results)}건")

            # Brave Search 검색
            if engine in ("brave", "both"):
                print(f"  🟠 Brave     → '{keyword}'")
                b_results = brave_search(keyword, num_results=3)
                brave_count += 1
                results.extend(b_results)
                print(f"     {len(b_results)}건")

            # 메타데이터 추가
            for r in results:
                r["source"] = f"search_{theme}"
                r["search_keyword"] = keyword
                r["theme"] = theme
                r["crawled_at"] = datetime.now().isoformat()

            all_results.extend(results)

    print(f"\n{'='*50}")
    print(f"📊 검색 완료:")
    print(f"   Google CSE : {google_count}회 사용 (일일 한도 100회)")
    print(f"   Brave      : {brave_count}회 사용 (월간 한도 2,000회)")
    print(f"   총 결과    : {len(all_results)}건")

    return all_results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # API 키 상태 출력
    print("🔑 API 키 상태:")
    print(f"   Google CSE : {'✅ 설정됨' if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID else '❌ 미설정'}")
    print(f"   Brave      : {'✅ 설정됨' if BRAVE_API_KEY else '❌ 미설정'}")

    if not GOOGLE_CSE_API_KEY and not BRAVE_API_KEY:
        print("\n❌ 검색 API 키가 하나도 설정되지 않았습니다.")
        print("   GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID 또는 BRAVE_API_KEY를 설정하세요.")
        # 빈 결과 저장 (파이프라인이 멈추지 않도록)
        with open(OUTPUT_DIR / "raw_search.json", "w") as f:
            json.dump([], f)
        return

    articles = run_themed_search()

    output_path = OUTPUT_DIR / "raw_search.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n📦 총 {len(articles)}건 검색 완료 → {output_path}")


if __name__ == "__main__":
    main()
