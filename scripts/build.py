"""Build the static site from data/lectures.json.

site/dist/
  index.html                         지역·종목 고르기, 지금 자리 있는 강좌
  r/<region>/index.html              시군구: 센터·종목별 요금 요약, 전체 강좌
  r/<region>/<sport>/index.html      시군구 × 종목 ("노원구 수영 강습")
  c/<center-id>/index.html           센터 한 곳
  s/<sport>/index.html               종목: 지역별 비교
  about/index.html                   출처·갱신·주의
  data/lectures.json, sitemap.xml, robots.txt, llms.txt
"""
import collections
import datetime
import html
import json
import os
import pathlib
import urllib.parse
import re
import shutil
import statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "dist"
# published on GitHub Pages under /dongne-gym/; set DONGNE_SITE_URL=http://localhost:8010 for a local preview
SITE_URL = os.environ.get("DONGNE_SITE_URL", "https://hyunsuhahaha.github.io/dongne-gym").rstrip("/")
BASE = urllib.parse.urlparse(SITE_URL).path.rstrip("/")
NAME = "동네운동"

# 종목: (slug, label, pattern over category + subcategory + name). First match wins.
SPORTS = [
    ("aqua", "아쿠아로빅", r"아쿠아"),
    ("swim", "수영", r"수영|영법|자유형|배영|평영|접영|마스터즈|수중"),
    ("pilates", "필라테스", r"필라테스"),
    ("yoga", "요가", r"요가"),
    ("gym", "헬스", r"헬스|웨이트|피트니스|헬스장|PT|체력단련"),
    ("gx", "스피닝·서킷·GX", r"스피닝|사이클|서킷|순환운동|바디펌프|크로스핏|G\.?X|타바타|인터벌|프롭"),
    ("dance", "댄스·에어로빅", r"댄스|줌바|에어로빅|라인|방송|K-?POP|재즈|탭|살사|밸리|벨리|무용|라틴|모던|워킹"),
    ("badminton", "배드민턴", r"배드민턴"),
    ("tabletennis", "탁구", r"탁구"),
    ("tennis", "테니스·피클볼", r"테니스|피클볼"),
    ("squash", "스쿼시", r"스쿼시"),
    ("golf", "골프", r"골프"),
    ("climbing", "클라이밍", r"클라이밍"),
    ("skate", "스케이트", r"스케이트|빙상|인라인"),
    ("taekwondo", "태권도·무술", r"태권도|주짓수|유도|검도|합기도|복싱|킥복싱|무에타이|격투"),
    ("ballet", "발레", r"발레"),
    ("ballgame", "축구·농구·배구", r"축구|풋살|농구|배구|족구|피구"),
    ("kidspe", "어린이 체육", r"유아체육|어린이체육|키즈|줄넘기|놀이체육|아동체육|체능단|방과후"),
    ("stretch", "스트레칭·건강체조", r"스트레칭|체조|건강|기공|태극권|체형|교정|자세|폼롤러|소도구|국선도|단전"),
    ("culture", "문화·교양", r"문화|미술|음악|노래|악기|어학|영어|서예|공예|요리|바둑|컴퓨터|민요|장구|기타|우쿨렐레|드로잉|피아노|언어|독서|논술|코딩|성악|꽃꽂이|도예|수채화|스케치|유화|파스텔|일본어|중국어|캘리|하모니카|난타|사물놀이|팝송|합창|플루트|바이올린|첼로|사진|뜨개|퀼트|한지|민화|서양화|한국화|그림|인문|글쓰기"),
]
OTHER = ("etc", "기타 운동", None)
SPORT_LABEL = {s: l for s, l, _ in SPORTS} | {OTHER[0]: OTHER[1]}


def classify(l):
    text = " ".join(filter(None, [l["category"], l["subcategory"], l["name"]]))
    for slug, _label, pat in SPORTS:
        if re.search(pat, text, re.I):
            return slug
    return OTHER[0]


AUDIENCES = ["성인", "어르신", "청소년", "어린이"]
LESSON_EXCLUDE = re.compile(r"자유수영|자유이용|일일|자유입장")


def audience(target, name=""):
    t, n = re.sub(r"\s", "", target or ""), name or ""
    adult = re.search(r"성인|누구나|전체|모든|남녀|남여|일반|노인|임산부|(중학|중학생|고등|고등학생|청소년|중고생?)\s*이상|1[3-9]\s*세\s*이상", t)
    if re.search(r"어르신|시니어|실버|노인", t + n) and not re.search(r"청소년|중고|어린이|초등", t):
        return "어르신"
    if not adult:
        if re.search(r"초등|초\s*\d|유아|유치|미취학|어린이|키즈|[3-9]\s*세|\d+\s*~\s*1[0-3]\s*세|\d{2}년생", t):
            return "어린이"
        if re.search(r"중고|중학|고등|청소년", t):
            return "청소년"
        if re.search(r"어린이|유아|키즈|초등|아동", n):
            return "어린이"
    return "성인"


def won(n):
    return f"{n:,}원" if n else "-"


def esc(s):
    return html.escape(str(s or ""), quote=True)


MONTHLY_MAX = 500000      # 학기·연간 단위 프로그램(유아체능단 등)은 월 요금 통계에서 뺀다


def median(xs):
    xs = [x for x in xs if x and x < MONTHLY_MAX]
    return int(statistics.median(xs)) if xs else None


# ---------------------------------------------------------------- page shell
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a66;--line:#e6e3dc;--card:#fff;--acc:#1f6f5c;--acc-bg:#e7f2ee;--warn:#9a5b00;--warn-bg:#fdf1de;--full:#9b2c2c;--full-bg:#fbe9e9}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#a3a19a;--line:#2c2b28;--card:#1c1c1a;--acc:#6cc3a8;--acc-bg:#16302a;--warn:#f0b35a;--warn-bg:#33270f;--full:#f08a8a;--full-bg:#3a1a1a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR","Malgun Gothic",sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:980px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line);background:var(--card)}header.top .wrap{display:flex;gap:16px;align-items:center;height:56px}
.brand{font-weight:800;font-size:18px;color:var(--fg)}.brand span{color:var(--acc)}
nav.top a{color:var(--mut);font-size:14px;margin-right:12px}
h1{font-size:26px;line-height:1.35;margin:28px 0 8px}h2{font-size:19px;margin:32px 0 10px}
.lead{color:var(--mut);margin:0 0 16px}
.crumb{font-size:13px;color:var(--mut);margin-top:16px}.crumb a{color:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.card b{display:block;font-size:15px}.card .big{font-size:20px;font-weight:700;margin-top:4px}.card small{color:var(--mut)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 4px}.chips a{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:4px 12px;font-size:14px;color:var(--fg)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mut);font-weight:600;font-size:13px;background:var(--bg)}
td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:12px;border-radius:6px;padding:1px 7px;white-space:nowrap}
.ok{background:var(--acc-bg);color:var(--acc)}.wait{background:var(--bg);color:var(--mut);border:1px solid var(--line)}.few{background:var(--warn-bg);color:var(--warn)}.full{background:var(--full-bg);color:var(--full)}
.note{font-size:13px;color:var(--mut);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:16px 0}
.faq dt{font-weight:700;margin-top:12px}.faq dd{margin:4px 0 0;color:var(--fg)}
footer{border-top:1px solid var(--line);margin-top:48px;padding:20px 0 40px;color:var(--mut);font-size:13px}
.scroll{overflow-x:auto}
.sm-only{display:none;font-size:13px}
@media (max-width:640px){h1{font-size:22px}.hide-sm{display:none}.sm-only{display:inline}th,td{padding:8px 6px}}
"""


def page(title, desc, path, body, crumbs=(), jsonld=None):
    canon = SITE_URL + path
    crumb_html = ""
    if crumbs:
        crumb_html = '<div class="crumb">' + " › ".join(
            f'<a href="{esc(u)}">{esc(t)}</a>' if u else esc(t) for t, u in crumbs) + "</div>"
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld, ensure_ascii=False) + "</script>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canon)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website"><meta property="og:locale" content="ko_KR">
<style>{CSS}</style>{ld}</head><body>
<header class="top"><div class="wrap"><a class="brand" href="/">동네<span>운동</span></a>
<nav class="top"><a href="/s/swim/">수영</a><a href="/s/pilates/">필라테스</a><a href="/s/gym/">헬스</a><a href="/about/">출처</a></nav></div></header>
<main class="wrap">{crumb_html}{body}</main>
<footer><div class="wrap">구민체육센터·시설관리공단이 공개한 강좌 정보를 모아 보여줍니다. 수강료와 정원은 {esc(COLLECTED)} 기준이며, 실제 접수·결제는 각 공단 예약 사이트에서 합니다. <a href="/about/">출처와 주의사항</a></div></footer>
</body></html>"""


OPEN_STATUS = {"R", "RW"}          # 공단 예약 화면의 "접수하기"
STATUS_TAG = {"W": ("wait", "접수 전"), "E": ("full", "접수종료"), "RR": ("wait", "재등록 기간")}


def is_open(l):
    """Can a newcomer sign up right now? Status 접수중 and, where enrollment is published, a free seat."""
    if l.get("status") not in OPEN_STATUS:
        return False
    return l["seats_left"] is None or l["seats_left"] > 0


def seats_tag(l):
    st = l.get("status")
    if st in STATUS_TAG:
        cls, text = STATUS_TAG[st]
        return f'<span class="tag {cls}">{text}</span>'
    left, cap = l["seats_left"], l["capacity"]
    if left is None or not cap:
        return '<span class="tag ok">접수중</span>' if st in OPEN_STATUS else ""
    if left <= 0:
        return '<span class="tag full">마감</span>'
    if left <= max(2, cap // 10):
        return f'<span class="tag few">{left}자리</span>'
    return f'<span class="tag ok">{left}자리</span>'


def lecture_table(ls, show_center=True):
    rows = []
    for l in sorted(ls, key=lambda l: (l["fee"] or 10**9, l["start"] or "")):
        extra = "" if len(l["fees"]) < 2 else f'<br><small>{" / ".join(won(f) for f in l["fees"][1:])}</small>'
        center = f'<td class="hide-sm"><a href="/c/{esc(l["cid"])}/">{esc(l["center"])}</a></td>' if show_center else ""
        inline = f'<br><a class="sm-only" href="/c/{esc(l["cid"])}/">{esc(l["center"])}</a>' if show_center else ""
        rows.append(f'<tr>{center}<td>{esc(l["name"])}<br><small>{esc(l["target"])}</small>{inline}</td>'
                    f'<td>{esc(l["days"])}<br><small>{esc(l["start"])}~{esc(l["end"])}</small></td>'
                    f'<td class="num">{won(l["fee"])}{extra}</td><td>{seats_tag(l)}</td></tr>')
    head = ('<th class="hide-sm">센터</th>' if show_center else "") + "<th>강좌</th><th>요일·시간</th><th>수강료</th><th>자리</th>"
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def summary_cards(groups, link):
    cards = []
    for key, ls in groups:
        fs = [l["fee"] for l in ls if l["fee"] and l["fee"] < MONTHLY_MAX]
        if not fs:
            continue
        open_n = sum(1 for l in ls if is_open(l))
        seat_txt = f" · 지금 신청 가능 {open_n}개" if open_n else ""
        cards.append(f'<a class="card" href="{esc(link(key))}"><b>{esc(SPORT_LABEL.get(key, key))}</b>'
                     f'<div class="big">월 {won(median(fs))}</div><small>중간값 · 최저 {won(min(fs))} · 강좌 {len(ls)}개{seat_txt}</small></a>')
    return '<div class="cards">' + "".join(cards) + "</div>"


def faq(qa):
    body = '<dl class="faq">' + "".join(f"<dt>{esc(q)}</dt><dd>{esc(a)}</dd>" for q, a in qa) + "</dl>"
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
    return body, ld


def write(path, text):
    p = OUT / path.strip("/") / "index.html" if not path.endswith(".xml") and not path.endswith(".txt") else OUT / path.strip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix == ".html" and BASE:            # root-relative links must live under the project path
        text = text.replace('href="/', f'href="{BASE}/')
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- build
def main():
    global COLLECTED
    doc = json.loads((ROOT / "data" / "lectures.json").read_text(encoding="utf-8"))
    for extra in ("lectures_sugang.json", "lectures_html.json"):          # other platforms' collectors
        p = ROOT / "data" / extra
        if p.exists():
            doc["lectures"] += json.loads(p.read_text(encoding="utf-8"))["lectures"]
    meta = json.loads((ROOT / "data" / "orgs_meta.json").read_text(encoding="utf-8"))
    COLLECTED = doc["collected"].replace("T", " ")
    date_label = doc["collected"][:10]
    # per-day free-swim slots ("10월 20일(화) / 1부", "일일입장") are tickets, not monthly classes
    daily = re.compile(r"\d{1,2}\s*월\s*\d{1,2}\s*일|일일\s*(입장|이용|권)|1일\s*이용")
    not_class = re.compile(r"사물함|락커|라커|주차")      # lockers and parking are sold in the same lists
    lectures = [l for l in doc["lectures"] if l["org"] in meta and l["fee"] and not daily.search(l["name"]) and not not_class.search(l["name"])]
    for l in lectures:
        l["name"] = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(l["name"])).split())
        m = meta[l["org"]]
        l.setdefault("operator", l["org"])
        l["region"], l["region_name"] = m["slug"], f'{m["sido"]} {m["sigungu"]}'
        l["sigungu"] = m["sigungu"]
        l["sport"] = classify(l)
        l["aud"] = audience(l["target"], l["name"])
        l["cid"] = f'{m["slug"]}-{l["center_code"]}'.lower()

    # some corporations publish capacity but always report 0 enrolled: their "seats left" means nothing
    for org in {l["org"] for l in lectures}:
        ls = [l for l in lectures if l["org"] == org]
        if sum(1 for l in ls if l["enrolled"] == 0) > 0.8 * len(ls):
            for l in ls:
                l["seats_left"] = None
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    urls = []

    by_region = collections.defaultdict(list)
    for l in lectures:
        by_region[l["region"]].append(l)
    by_sport = collections.defaultdict(list)
    for l in lectures:
        by_sport[l["sport"]].append(l)

    # region pages
    for region, ls in by_region.items():
        rname, sg = ls[0]["region_name"], ls[0]["sigungu"]
        sports = sorted(collections.Counter(l["sport"] for l in ls).items(), key=lambda kv: (kv[0] == "etc", -kv[1]))
        centers = sorted({(l["cid"], l["center"]) for l in ls}, key=lambda c: c[1])
        groups = [(s, [l for l in ls if l["sport"] == s]) for s, _ in sports]
        swim = [l["fee"] for l in ls if l["sport"] == "swim" and l["aud"] == "성인"]
        qa = [(f"{sg} 공공 체육시설 강좌는 한 달에 얼마인가요?",
               f"{date_label} 기준 {sg} 구립·시립 체육시설 강좌 {len(ls)}개의 월 수강료 중간값은 {won(median([l['fee'] for l in ls]))}입니다."),
              (f"{sg}에서 지금 신청할 자리가 남은 강좌가 있나요?",
               (f"{date_label} 기준 접수 중이면서 자리가 남은 강좌는 {sum(1 for l in ls if is_open(l))}개입니다. 대부분의 센터는 매달 정해진 기간(재등록 뒤 신규 접수)에만 받으니, 접수 일정은 공단 예약 사이트에서 확인하세요."
                if any(l.get("status") or l["seats_left"] is not None for l in ls) else
                f"{sg} 운영 기관은 접수 현황(남은 자리)을 공개하지 않습니다. 매달 재등록 뒤 신규 접수 기간에 공단 사이트나 현장에서 확인하세요."))]
        if swim:
            qa.insert(1, (f"{sg} 성인 수영 강습비는 얼마인가요?", f"성인 수영 강습 {len(swim)}개의 월 수강료는 {won(min(swim))}~{won(max(swim))}, 중간값 {won(median(swim))}입니다."))
        faq_html, faq_ld = faq(qa)
        body = (f"<h1>{esc(sg)} 공공 체육시설 강좌 요금과 빈자리</h1>"
                f'<p class="lead">{esc(rname)}의 구민체육센터·문화센터 {len(centers)}곳, 강좌 {len(ls)}개를 한 번에 비교합니다. {esc(date_label)} 기준.</p>'
                f"<h2>종목별 월 수강료</h2>{summary_cards(groups, lambda s: f'/r/{region}/{s}/')}"
                f"<h2>센터</h2><div class=\"chips\">" + "".join(f'<a href="/c/{esc(c)}/">{esc(n)}</a>' for c, n in centers) + "</div>"
                f"<h2>자주 묻는 질문</h2>{faq_html}"
                f'<p class="note">자리 수는 공단이 공개한 정원과 등록 인원으로 계산한 값입니다. 재등록 기간·추첨 강좌는 실제 접수와 다를 수 있습니다.</p>')
        write(f"/r/{region}/", page(f"{sg} 공공 체육 강좌 요금·빈자리 비교 ({date_label[:7]}) | {NAME}",
                                    f"{rname} 구민체육센터 강좌 {len(ls)}개의 수강료와 남은 자리를 종목별로 비교합니다.",
                                    f"/r/{region}/", body, [("홈", "/"), (rname, None)], faq_ld))
        urls.append(f"/r/{region}/")
        for s, sl in groups:
            fs = [l["fee"] for l in sl if l["fee"] < MONTHLY_MAX] or [l["fee"] for l in sl]
            label = SPORT_LABEL[s]
            open_n = sum(1 for l in sl if is_open(l))
            sections, qa = [], []
            for aud in AUDIENCES:
                al = [l for l in sl if l["aud"] == aud]
                if not al:
                    continue
                afs = [l["fee"] for l in al if l["fee"] < MONTHLY_MAX] or [l["fee"] for l in al]
                cheapest = min(al, key=lambda l: l["fee"])
                sections.append(f"<h2>{aud} · {len(al)}개 · 월 {won(min(afs))}~{won(max(afs))} · 중간값 {won(median(afs))}</h2>{lecture_table(al)}")
                qa.append((f"{sg} {aud} {label} 강습은 한 달에 얼마인가요?",
                           f"{date_label} 기준 {sg} 공공 체육시설 {aud} 대상 {label} 강좌 {len(al)}개의 월 수강료는 {won(min(afs))}~{won(max(afs))}, 중간값은 {won(median(afs))}입니다. "
                           f"가장 저렴한 강좌는 {cheapest['center']}의 '{cheapest['name']}'({cheapest['days']} {cheapest['start']}~{cheapest['end']}, 월 {won(cheapest['fee'])})입니다."))
            qa.append((f"지금 신청할 수 있는 {label} 강좌가 있나요?", f"{date_label} 기준 {len(sl)}개 중 {open_n}개가 접수 중이면서 자리가 남아 있습니다. 나머지는 접수 전이거나 마감·재등록 기간입니다."))
            faq_html, faq_ld = faq(qa)
            body = (f"<h1>{esc(sg)} {esc(label)} 강습 가격과 빈자리</h1>"
                    f'<p class="lead">{esc(rname)} 공공 체육시설의 {esc(label)} 강좌 {len(sl)}개 · 지금 신청 가능 {open_n}개 · {esc(date_label)} 기준. 대상별로 나눠 비교합니다.</p>'
                    + "".join(sections) + f"<h2>자주 묻는 질문</h2>{faq_html}")
            write(f"/r/{region}/{s}/", page(f"{sg} {label} 강습 가격 비교 - 구민체육센터 {len(sl)}개 강좌 | {NAME}",
                                            f"{rname} {label} 강좌 {len(sl)}개: 월 {won(min(fs))}~{won(max(fs))}, 중간값 {won(median(fs))}. 성인·어린이 대상별 요금과 남은 자리.",
                                            f"/r/{region}/{s}/", body, [("홈", "/"), (rname, f"/r/{region}/"), (label, None)], faq_ld))
            urls.append(f"/r/{region}/{s}/")

    # center pages
    by_center = collections.defaultdict(list)
    for l in lectures:
        by_center[l["cid"]].append(l)
    for cid, ls in by_center.items():
        c = ls[0]
        groups = sorted(collections.Counter(l["sport"] for l in ls).items(), key=lambda kv: -kv[1])
        body = (f"<h1>{esc(c['center'])} 강좌·수강료</h1>"
                f'<p class="lead">{esc(c["region_name"])} · {esc(c.get("operator") or c["org"])} 운영 · 강좌 {len(ls)}개 · <a href="{esc(c["source"])}" rel="nofollow">공단 예약 사이트</a></p>'
                + "".join(f"<h2>{esc(SPORT_LABEL[s])}</h2>{lecture_table([l for l in ls if l['sport'] == s], show_center=False)}" for s, _ in groups))
        write(f"/c/{cid}/", page(f"{c['center']} 수강료·강좌 시간표 ({c['region_name']}) | {NAME}",
                                 f"{c['center']} 강좌 {len(ls)}개의 수강료, 요일·시간, 남은 자리.",
                                 f"/c/{cid}/", body, [("홈", "/"), (c["region_name"], f"/r/{c['region']}/"), (c["center"], None)]))
        urls.append(f"/c/{cid}/")

    # sport pages
    for s, ls in by_sport.items():
        label = SPORT_LABEL[s]
        rows = []
        for region, rl in sorted(((r, [l for l in ls if l["region"] == r]) for r in by_region), key=lambda x: median([l["fee"] for l in x[1]]) or 10**9):
            if not rl:
                continue
            fs = [l["fee"] for l in rl if l["fee"] < MONTHLY_MAX] or [l["fee"] for l in rl]
            rows.append(f'<tr><td><a href="/r/{region}/{s}/">{esc(rl[0]["region_name"])}</a></td><td class="num">{len(rl)}</td>'
                        f'<td class="num">{won(min(fs))}</td><td class="num">{won(median(fs))}</td><td class="num hide-sm">{won(max(fs))}</td></tr>')
        body = (f"<h1>{esc(label)} 공공 강좌 요금 지역별 비교</h1>"
                f'<p class="lead">구민·시민 체육센터 {esc(label)} 강좌 {len(ls)}개 · {esc(date_label)} 기준 · 중간값이 낮은 지역부터</p>'
                f'<div class="scroll"><table><thead><tr><th>지역</th><th>강좌</th><th>최저</th><th>중간값</th><th class="hide-sm">최고</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        write(f"/s/{s}/", page(f"{label} 공공 강습 요금 지역별 비교 ({date_label[:7]}) | {NAME}",
                               f"구민체육센터 {label} 강좌 {len(ls)}개의 월 수강료를 지역별로 비교합니다.",
                               f"/s/{s}/", body, [("홈", "/"), (label, None)]))
        urls.append(f"/s/{s}/")

    # home
    region_links = "".join(f'<a href="/r/{r}/">{esc(ls[0]["region_name"])}</a>' for r, ls in sorted(by_region.items(), key=lambda kv: kv[1][0]["region_name"]))
    sport_links = "".join(f'<a href="/s/{s}/">{esc(SPORT_LABEL[s])}</a>' for s, _ in sorted(collections.Counter(l["sport"] for l in lectures).items(), key=lambda kv: -kv[1]))
    open_swim = sorted([l for l in lectures if l["sport"] == "swim" and is_open(l) and l["aud"] == "성인" and not LESSON_EXCLUDE.search(l["name"])], key=lambda l: l["fee"])[:12]
    body = ("<h1>우리 동네 구민체육센터, 한 달에 얼마?</h1>"
            f'<p class="lead">시설관리공단·도시공사가 공개한 공공 체육시설 강좌 {len(lectures):,}개의 수강료와 남은 자리를 모았습니다. 사설보다 훨씬 싼 동네 수영·필라테스·헬스를 찾아보세요. {esc(date_label)} 기준.</p>'
            f'<h2>지역</h2><div class="chips">{region_links}</div><h2>종목</h2><div class="chips">{sport_links}</div>'
            f"<h2>지금 신청할 수 있는 저렴한 성인 수영 강습</h2>{lecture_table(open_swim)}")
    write("/", page(f"{NAME} - 구민체육센터 강좌 요금·빈자리 비교", "공공 체육시설 수영·필라테스·헬스 강좌의 수강료와 남은 자리를 지역별로 비교합니다.", "/", body,
                    jsonld={"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE_URL}))
    urls.append("/")

    # about
    ops = collections.Counter((l.get("operator") or l["org"], l["region_name"]) for l in lectures)
    src_rows = "".join(f'<tr><td>{esc(o)}</td><td>{esc(r)}</td><td class="num">{n:,}</td></tr>' for (o, r), n in sorted(ops.items(), key=lambda kv: kv[0][1]))
    body = ("<h1>출처와 주의사항</h1>"
            "<p>이 사이트는 각 지역 시설관리공단·도시공사가 누구나 볼 수 있게 공개한 강좌 목록(강좌명, 요일·시간, 대상, 수강료, 정원, 등록 인원)을 하루 한 번 읽어 정리합니다. "
            "강사 이름 같은 개인 정보는 저장하지 않으며, 예약이나 결제 기능은 없습니다.</p>"
            f'<p class="note">수강료는 공단이 표시한 금액입니다. "51,600 / 154,800"처럼 여러 금액이 있으면 앞의 금액(보통 1개월)을 기준으로 비교합니다. 할인·입회비·재등록 규칙은 센터마다 다르니 신청 전에 공단 사이트에서 확인하세요. 마지막 수집: {esc(COLLECTED)}</p>'
            f'<h2>수집 기관</h2><div class="scroll"><table><thead><tr><th>기관</th><th>지역</th><th>강좌</th></tr></thead><tbody>{src_rows}</tbody></table></div>')
    write("/about/", page(f"출처와 주의사항 | {NAME}", "동네운동이 보여주는 강좌 요금 데이터의 출처와 갱신 방식", "/about/", body,
                          [("홈", "/"), ("출처", None)],
                          {"@context": "https://schema.org", "@type": "Dataset", "name": "공공 체육시설 강좌 수강료·정원", "dateModified": date_label,
                           "description": "시설관리공단·도시공사 공개 강좌 목록에서 모은 수강료, 요일·시간, 정원, 등록 인원", "url": SITE_URL + "/about/"}))
    urls.append("/about/")

    # machine-readable copies
    (OUT / "data").mkdir(exist_ok=True)
    public = [{k: l[k] for k in ("region_name", "operator", "center", "sport", "name", "days", "start", "end", "target", "fee", "fees", "capacity", "enrolled", "seats_left")} for l in lectures]
    (OUT / "data" / "lectures.json").write_text(json.dumps({"collected": doc["collected"], "lectures": public}, ensure_ascii=False), encoding="utf-8")
    today = datetime.date.today().isoformat()
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{esc(SITE_URL + u)}</loc><lastmod>{today}</lastmod></url>" for u in urls) + "</urlset>")
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    write("/llms.txt", f"# {NAME}\n> 한국 구민·시민 체육센터(시설관리공단·도시공사) 공공 강좌의 월 수강료, 요일·시간, 정원과 남은 자리를 지역·종목별로 정리한 사이트. 마지막 수집 {COLLECTED}.\n\n"
          "- 지역별: /r/<지역>/ , 지역×종목: /r/<지역>/<종목>/ (예: /r/seoul-nowon/swim/)\n- 종목별 지역 비교: /s/<종목>/\n- 전체 데이터(JSON): /data/lectures.json\n- 출처: /about/\n")
    print(f"pages {len(urls)}, lectures {len(lectures)}, regions {len(by_region)}, centers {len(by_center)}")
    print(collections.Counter(l["sport"] for l in lectures).most_common())


COLLECTED = ""

if __name__ == "__main__":
    main()
