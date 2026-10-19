"""Group the not-yet-covered corporations by the reservation software they run.

For each candidate host, fetch the front page (and a few common reservation paths) and pull
out stable traces: script/css path prefixes and known product markers. Hosts sharing a trace
probably share a backend, so one collector can cover them all.
Output: data/fingerprints.json and a ranking printed to stdout.
"""
import collections
import concurrent.futures
import json
import pathlib
import re
import ssl
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (dongne-gym collector)"}
EXTRA_HOST_PREFIXES = ["sports.", "yeyak.", "reserve.", "reservation.", "sugang.", "online.", "booking.", "rsv.", "res.", "sport."]


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=10, context=CTX) as r:
            return r.geturl(), r.read(300000).decode("utf-8", "replace")
    except Exception:
        return None, ""


def traces(html):
    out = set()
    for src in re.findall(r'(?:src|href)=["\']([^"\']+\.(?:js|css))', html, re.I):
        path = re.sub(r"^https?://[^/]+", "", src).split("?")[0]
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            out.add("/" + "/".join(parts[:2]))
    for marker in ["fmcs", "modules_fmcs", "eGovFrame", "egov", "jsessionid", "netfunnel", "WebSquare", "nexacro",
                   "kspo", "rnc", "ksportsfacil", "smartfacil", "uriad", "yeyak", "reserve.do", "lecture", "sugang",
                   "ticketlink", "wordpress", "gnuboard", "xe.js", "rhymix", "kboard", "jsp", ".do\""]:
        if marker.lower() in html.lower():
            out.add("marker:" + marker)
    return out


def probe(org, host):
    rows = []
    hosts = [host]
    bare = re.sub(r"^www\.", "", host)
    hosts += [p + bare for p in EXTRA_HOST_PREFIXES]
    for h in hosts:
        for scheme in ("https", "http"):
            final, html = fetch(f"{scheme}://{h}/")
            if html:
                rows.append({"org": org, "host": h, "final": final, "size": len(html), "traces": sorted(traces(html))})
                break
    return rows


def main():
    orgs = json.loads((ROOT / "data" / "org_domains.json").read_text(encoding="utf-8"))
    covered = {s["org"] for s in json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))}
    jobs = [(o, h) for o, hs in orgs.items() if o not in covered for h in hs]
    with concurrent.futures.ThreadPoolExecutor(32) as ex:
        found = [r for rows in ex.map(lambda j: probe(*j), jobs) for r in rows]
    (ROOT / "data" / "fingerprints.json").write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    count = collections.defaultdict(set)
    for r in found:
        for t in r["traces"]:
            count[t].add(r["org"])
    print(f"{len(found)} live hosts for {len({r['org'] for r in found})} orgs")
    for t, os_ in sorted(count.items(), key=lambda kv: -len(kv[1]))[:45]:
        if len(os_) >= 2:
            print(f"{len(os_):>3}  {t:<45} {', '.join(sorted(os_))[:110]}")


if __name__ == "__main__":
    main()
