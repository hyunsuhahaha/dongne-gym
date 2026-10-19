# 동네운동

사이트: https://hyunsuhahaha.github.io/dongne-gym/

구민체육센터·시민체육센터의 강좌 요금과 남은 자리를 지역·종목별로 비교하는 정적 사이트입니다.
공공 체육시설은 사설보다 훨씬 싸지만(수영 강습 월 2~6만 원대), 정보가 공단마다 따로 있어
"우리 동네에서 제일 싼 수영 강습은 어디고 자리가 있나"를 한 번에 알 수 없습니다.

## 데이터

- 기관 목록: 클린아이 「지방공기업 설립현황」(2026.6.30 기준)의 시설·도시관리공단과 도시공사 118곳
  → `data/orgs.txt`, 홈페이지 도메인 `data/org_domains.json`
- 수집: 공단 예약 사이트가 누구나 보도록 공개한 강좌 목록. 로그인·예약·결제는 하지 않고,
  하루 한 번 요청 사이 간격을 두고 읽습니다. 강사 이름은 저장하지 않습니다.
- 현재 26개 지역, 센터 156곳, 강좌 약 13,300개 (2026.10.20)
  - fmcs 예약 플랫폼(`/rest/lecture/list`, GET 또는 POST): 25개 기관 (`data/sources.json`, `scripts/collect.py`)
  - "문화/체육 수강시스템"(Spring, CSRF): 강동구. 요금 항목에 이용 개월 수가 있어 월 요금이 정확합니다 (`scripts/collect_sugang.py`)
  - 정적 HTML 표: 성남도시개발공사 5개 센터. 병합 셀을 풀어 시간대별로 읽고, 남은 자리는 공개되지 않습니다 (`scripts/collect_html.py`)
- 일부 주소는 공단이 아니라 재단·구청이 운영합니다(`data/host_operators.json`). 출처는 실제 운영 기관으로 표시합니다.
- 정원과 등록 인원으로 남은 자리를 계산합니다. 등록 인원을 공개하지 않는 기관(항상 0으로 내보냄)은 자리 표시를 끕니다.

## 실행

```
python scripts/discover.py   # 공단별 강좌 API 응답 여부 → data/sources.json
python scripts/collect.py    # fmcs 플랫폼 강좌 수집 → data/lectures.json
python scripts/collect_sugang.py  # "문화/체육 수강시스템" 플랫폼(강동 등) → data/lectures_sugang.json
python scripts/collect_html.py    # 정적 표로 공개하는 곳(성남 등) → data/lectures_html.json
python scripts/build.py      # 정적 사이트 → site/dist/
DONGNE_SITE_URL=http://localhost:8010 python scripts/build.py   # 로컬 미리보기용(하위 경로 없이)
python -m http.server 8010 -d site/dist
```

## 페이지

- `/r/<지역>/` 지역별 종목 요약, `/r/<지역>/<종목>/` 지역×종목(대상별 표, FAQ)
- `/c/<센터>/` 센터별 전체 강좌, `/s/<종목>/` 종목별 지역 비교
- `/about/` 출처, `/data/lectures.json`, `sitemap.xml`, `llms.txt`

## 배포

main에 푸시하면 GitHub Actions가 커밋된 `data/*.json`으로 사이트를 만들어 GitHub Pages에 올립니다.
수집은 국내 회선에서 돌리고(`scripts/refresh.py`) 결과 데이터를 커밋합니다.
