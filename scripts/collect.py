"""Collect every public lecture from the corporations found by discover.py.

Reads only the public lecture lists (no login, no booking) once, slowly, and keeps the
fields a visitor needs: where, what, when, for whom, how much, and how full.
Instructor names are dropped: they are personal data and nobody chooses a pool by them.

Output: data/lectures.json
"""
import datetime
import json
import pathlib
import re
import ssl
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (dongne-gym collector)", "X-Requested-With": "XMLHttpRequest"}
PAGE = 200
PAUSE = 0.6          # seconds between requests to one host


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fees(raw):
    """'51,600/154,800' -> [51600, 154800]; the first is the shortest term (usually one month)."""
    return [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", str(raw or "")) if int(x.replace(",", "")) > 0]


def num(v):
    s = str(v or "").replace(",", "").strip()
    return int(s) if s.isdigit() else None


def lecture(src, center, r):
    capacity, enrolled = num(r.get("capa")), num(r.get("reg_person"))
    f = fees(r.get("course_fee"))
    return {
        "org": src["org"], "center": r.get("comnm") or center["name"], "center_code": center["code"],
        "source": src["base"], "id": r.get("class_cd"),
        "category": (r.get("category1") or "").strip() or None, "subcategory": (r.get("category2") or "").strip() or None,
        "name": (r.get("class_nm") or "").strip(),
        "days": (r.get("train_day_nm") or "").strip(),
        "start": r.get("train_stime"), "end": r.get("train_etime"),
        "target": (r.get("target_age_name") or "").strip(),
        "fee": f[0] if f else None, "fees": f,
        "capacity": capacity, "enrolled": enrolled,
        "seats_left": (capacity - enrolled) if capacity and enrolled is not None else None,
    }


def collect(src):
    out = []
    for center in src["centers"]:
        page = 1
        while True:
            url = (f"{src['base']}/rest/lecture/list?company_code={center['code']}&mem_no=&search_type=&category_cd="
                   f"&category_level=9&class_nm=&train_day=&adult_gubn=&lecturer_nm=&page={page}&page_size={PAGE}")
            try:
                rows = get_json(url)
            except Exception as e:
                print(f"  {src['org']} {center['name']} p{page}: {type(e).__name__}")
                break
            out += [lecture(src, center, r) for r in rows if isinstance(r, dict)]
            if len(rows) < PAGE:
                break
            page += 1
            time.sleep(PAUSE)
        time.sleep(PAUSE)
    return out


def main():
    sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    lectures = []
    for src in sources:
        got = collect(src)
        print(f"{src['org']:<20} {len(got):>5} lectures")
        lectures += got
    junk = re.compile(r"테스트|점검용|신청하지\s*마세요")
    lectures = [l for l in lectures if not junk.search(l["name"]) and not junk.search(l["category"] or "")]
    doc = {"collected": datetime.datetime.now().isoformat(timespec="minutes"), "lectures": lectures}
    (ROOT / "data" / "lectures.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"total {len(lectures)}")


if __name__ == "__main__":
    main()
