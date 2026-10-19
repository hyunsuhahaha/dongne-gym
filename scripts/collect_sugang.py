"""Collector for the second reservation platform ("문화/체육 수강시스템", Spring + CSRF).

Seen at 강동구도시관리공단 (sugang.igangdong.or.kr) and 송파구체육문화회관 (www.esongpa.or.kr).
The public 프로그램안내 page asks POST /data/lecture/list for every program of a center and sport,
whatever the registration window: name, days/time, target, capacity, web sign-ups, and the price
items (saleAmt with monthCnt, so a 3-month price is never mistaken for a monthly one).

Writes data/lectures_sugang.json in the same row format as collect.py.
"""
import datetime
import http.cookiejar
import json
import pathlib
import re
import ssl
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITES = [
    {"org": "강동구도시관리공단", "base": "https://sugang.igangdong.or.kr", "home": "/?gdfmcIntro=true"},
    # 송파구체육문화회관 (www.esongpa.or.kr) runs the same front end but lists programs as a static table: not collected yet
]
PAUSE = 0.6
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE


class Session:
    def __init__(self, base, home):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                              urllib.request.HTTPSHandler(context=CTX))
        self.op.addheaders = [("User-Agent", "Mozilla/5.0 (dongne-gym collector)")]
        page = self.op.open(base + home, timeout=30).read().decode("utf-8", "replace")
        self.token = re.search(r'name="_csrf" content="([^"]+)"', page).group(1)
        self.header = re.search(r'name="_csrf_header" content="([^"]+)"', page).group(1)

    def post(self, path, form):
        req = urllib.request.Request(self.base + path, data=urllib.parse.urlencode(form).encode(),
                                     headers={self.header: self.token, "X-Requested-With": "XMLHttpRequest",
                                              "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        with self.op.open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))


def monthly_price(items):
    """Pick the shortest-term price; return (fee, all fees, months)."""
    priced = [(i.get("monthCnt") or 1, i.get("saleAmt") or i.get("costAmt") or 0) for i in items or []]
    priced = [(m, a) for m, a in priced if a]
    if not priced:
        return None, [], None
    priced.sort()
    return priced[0][1], [a for _, a in priced], priced[0][0]


def row(site, r):
    fee, fees, months = monthly_price(r.get("programItem"))
    capacity = r.get("webCapa") or r.get("capa") or None
    enrolled = r.get("webUser")
    target = r.get("classObj") or next((i.get("adultGubn") for i in r.get("programItem") or [] if i.get("adultGubn")), "")
    return {
        "org": site["org"], "operator": site.get("operator", site["org"]),
        "center": r.get("comnm"), "center_code": r.get("comcd"), "source": site["base"], "id": r.get("classCd"),
        "category": r.get("sportsCdNm"), "subcategory": r.get("msportsCdNm"),
        "name": (r.get("classNm") or "").strip(), "days": (r.get("trainDayNm") or "").replace(",", ""),
        "start": r.get("trainStimeNm"), "end": r.get("trainEtimeNm"), "target": (target or "").strip(),
        "fee": fee, "fees": fees, "months": months,
        "capacity": capacity, "enrolled": enrolled,
        "seats_left": (capacity - enrolled) if capacity and enrolled is not None else None,
        "status": None, "receive_kind": None,
    }


def collect(site):
    s = Session(site["base"], site["home"])
    out = []
    for n in range(1, 31):
        comcd = f"{n:02d}"
        try:
            sports = s.post("/data/getSportsInfo", {"COMCD": comcd})
        except Exception:
            continue
        time.sleep(PAUSE)
        for sp in sports or []:
            try:
                data = s.post("/data/lecture/list", {"sportsCd": sp["CD"], "comcd": comcd, "pageIndex": 1, "pageSize": 1000, "startRow": 0})
            except Exception as e:
                print(f"  {site['org']} {comcd}/{sp.get('CD_NM')}: {type(e).__name__}")
                continue
            out += [row(site, r) for r in data.get("resultList") or [] if r.get("webDisplay", "Y") == "Y"]
            time.sleep(PAUSE)
    return out


def main():
    lectures = []
    for site in SITES:
        got = collect(site)
        print(f"{site['org']:<20} {len(got):>5} lectures, centers {len({g['center'] for g in got})}")
        lectures += got
    doc = {"collected": datetime.datetime.now().isoformat(timespec="minutes"), "lectures": lectures}
    (ROOT / "data" / "lectures_sugang.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print("total", len(lectures))


if __name__ == "__main__":
    main()
