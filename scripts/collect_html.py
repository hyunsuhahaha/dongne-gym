"""Collector for corporations that publish their programs as static HTML tables.

Each program sits under a heading ("수영(수영장, 진도 수료 및 기간 수료)") followed by a table
whose cells span rows (대상 | 시간 | 요일 | 정원 | 이용료). The table is expanded into a grid,
then every time slot becomes one row. Fee cells are free text such as
"일 반 주4회 48,000원 주5회 54,000원 청소년 주4회 40,000원": every amount is kept, and the
first one (general rate, fewest sessions) is the comparable monthly fee.

No enrollment is published on these pages, so seats_left stays unknown.
Writes data/lectures_html.json.
"""
import datetime
import html
import json
import pathlib
import re
import ssl
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
PAUSE = 0.8

SITES = [
    {"org": "성남도시개발공사", "base": "https://spo.isdc.co.kr", "pages": {
        "ggp_programGuide.do": "금곡공원국민체육센터", "sns_programGuide.do": "성남종합운동장",
        "pgs_programGuide.do": "판교스포츠센터", "spo_programGuide.do": "평생스포츠센터",
        "tan_programGuide.do": "탄천종합운동장"}},
]

TIME = re.compile(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})")
AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,7})\s*원")
DAYS = re.compile(r"[월화수목금토일](?:[\s,·/()]*[월화수목금토일])*")


def text(cell):
    cell = re.sub(r"<br\s*/?>", "\n", cell, flags=re.I)
    return "\n".join(" ".join(l.split()) for l in html.unescape(re.sub(r"<[^>]+>", " ", cell)).split("\n") if l.strip())


def grid(table_html):
    """Expand rowspan/colspan into a list of rows of cell texts."""
    rows, pending = [], {}          # pending[col] = (text, rows_left)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        cells = re.findall(r"<t([dh])([^>]*)>(.*?)</t[dh]>", tr, re.S)
        row, col, it = [], 0, iter(cells)
        while True:
            if col in pending:
                t, left = pending[col]
                row.append(t)
                pending[col] = (t, left - 1)
                if left - 1 == 0:
                    del pending[col]
                col += 1
                continue
            nxt = next(it, None)
            if nxt is None:
                if any(c in pending for c in range(col, col + 10)):
                    col += 1
                    continue
                break
            _tag, attrs, inner = nxt
            span = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
            cspan = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
            t = text(inner)
            for _ in range(cspan):
                row.append(t)
                if span > 1:
                    pending[col] = (t, span - 1)
                col += 1
        rows.append(row)
    return rows


def parse_page(site, center, page):
    out = []
    # split at headings; each heading names the program of the tables that follow
    parts = re.split(r"<h[3-5][^>]*>(.*?)</h[3-5]>", page, flags=re.S)
    heading = ""
    for i, part in enumerate(parts):
        if i % 2 == 1:
            heading = text(part)
            continue
        for table in re.findall(r"<table[^>]*>.*?</table>", part, re.S):
            g = grid(table)
            if not g:
                continue
            head = [h.replace(" ", "") for h in g[0]]
            col = lambda *names: next((j for j, h in enumerate(head) for n in names if n in h), None)
            c_time, c_fee = col("시간"), col("이용료", "수강료", "요금", "회비")
            if c_time is None or c_fee is None:
                continue
            c_target, c_days, c_cap = col("대상", "구분"), col("요일"), col("정원")
            for r in g[1:]:
                if len(r) <= max(c_time, c_fee):
                    continue
                m = TIME.search(r[c_time])
                fees = [int(a.replace(",", "")) for a in AMOUNT.findall(r[c_fee])]
                if not m or not fees or max(fees) < 10000:     # 1회 이용료(탁구 2,500원 등)는 월 강습이 아니다
                    continue
                days_txt = r[c_days] if c_days is not None and c_days < len(r) else r[c_fee]
                days = (DAYS.search(days_txt.split("\n")[0]) or DAYS.search(days_txt) or [""])[0]
                cap = re.search(r"(\d+)\s*명", r[c_cap]) if c_cap is not None and c_cap < len(r) else None
                name = re.split(r"[(\[【]", heading)[0].strip() or "강좌"
                target = (r[c_target].replace("\n", " ") if c_target is not None and c_target < len(r) else "")
                out.append({
                    "org": site["org"], "operator": site["org"], "center": center, "center_code": center,
                    "source": site["base"], "id": None, "category": name, "subcategory": None,
                    "name": f"{name} {m.group(1)}", "days": re.sub(r"[\s,·/()]", "", days),
                    "start": m.group(1), "end": m.group(2), "target": target,
                    "fee": fees[0], "fees": fees, "months": 1,
                    "capacity": int(cap.group(1)) if cap else None, "enrolled": None, "seats_left": None,
                    "status": None, "receive_kind": None,
                })
    return out


def main():
    lectures = []
    for site in SITES:
        for path, center in site["pages"].items():
            req = urllib.request.Request(f"{site['base']}/{path}", headers={"User-Agent": "Mozilla/5.0 (dongne-gym collector)"})
            page = urllib.request.urlopen(req, timeout=30, context=CTX).read().decode("utf-8", "replace")
            got = parse_page(site, center, page)
            print(f"{site['org']} {center:<14} {len(got):>4}")
            lectures += got
            time.sleep(PAUSE)
    doc = {"collected": datetime.datetime.now().isoformat(timespec="minutes"), "lectures": lectures}
    (ROOT / "data" / "lectures_html.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print("total", len(lectures))


if __name__ == "__main__":
    main()
