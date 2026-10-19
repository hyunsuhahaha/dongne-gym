"""Find which facility corporations run the shared "fmcs" reservation platform.

Input:  data/org_domains.json   {기관명: [host, ...]}  (from 클린아이 지방공기업 설립현황 + web search)
Output: data/sources.json       [{org, base, company_path, centers}]  for every host whose
        lecture REST API answers, plus a list of hosts that do not.
"""
import concurrent.futures
import json
import pathlib
import ssl
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE        # several public-sector hosts serve broken chains
HEADERS = {"User-Agent": "Mozilla/5.0 (dongne-gym collector)", "X-Requested-With": "XMLHttpRequest"}
COMPANY_PATHS = ["/rest/common/lecture_company", "/rest/common/company?type=L"]


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe(org, host):
    for scheme in ("https", "http"):
        base = f"{scheme}://{host}"
        for path in COMPANY_PATHS:
            try:
                data = get_json(base + path)
            except Exception:
                continue
            if isinstance(data, list) and data and isinstance(data[0], dict):
                centers = [{"code": c.get("comcd") or c.get("company_code"),
                            "name": c.get("comnm") or c.get("company_name")} for c in data]
                return {"org": org, "base": base, "company_path": path, "centers": centers}
    return None


def main():
    orgs = json.loads((ROOT / "data" / "org_domains.json").read_text(encoding="utf-8"))
    jobs = [(org, host) for org, hosts in orgs.items() for host in hosts]
    with concurrent.futures.ThreadPoolExecutor(24) as ex:
        results = list(ex.map(lambda j: probe(*j), jobs))
    found, seen = [], set()
    for r in results:
        if r and r["base"] not in seen:
            seen.add(r["base"]); found.append(r)
    covered = {r["org"] for r in found}
    (ROOT / "data" / "sources.json").write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in found:
        print(f"{r['org']:<24} {r['base']:<40} centers {len(r['centers'])}")
    print(f"\n{len(covered)} of {len(orgs)} corporations answer the fmcs lecture API")
    print("not found:", ", ".join(o for o in orgs if o not in covered))


if __name__ == "__main__":
    main()
