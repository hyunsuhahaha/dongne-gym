"""Find which facility corporations run the shared "fmcs" reservation platform.

Input:  data/org_domains.json   {기관명: [host, ...]}  (from 클린아이 지방공기업 설립현황 + web search)
Output: data/sources.json       [{org, base, company_path, centers}]  for every host whose
        lecture REST API answers, plus a list of hosts that do not.
"""
import concurrent.futures
import json
import pathlib
import ssl
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
# several public-sector servers still need old ciphers and legacy renegotiation (e.g. yeyak.gys.or.kr)
CTX.set_ciphers("DEFAULT:@SECLEVEL=0")
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)        # several public-sector hosts serve broken chains
HEADERS = {"User-Agent": "Mozilla/5.0 (dongne-gym collector)", "X-Requested-With": "XMLHttpRequest"}
# older installs answer GET, newer ones (2025~) only POST
COMPANY_CALLS = [("/rest/common/lecture_company", "GET"), ("/rest/common/company?type=L", "GET"), ("/rest/common/company", "POST")]


def get_json(url, form=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe(org, host):
    for scheme in ("https", "http"):
        base = f"{scheme}://{host}"
        for path, method in COMPANY_CALLS:
            try:
                data = get_json(base + path) if method == "GET" else get_json(base + path.split("?")[0], {"type": "L"})
            except Exception:
                continue
            if isinstance(data, list) and data and isinstance(data[0], dict):
                centers = [{"code": c.get("comcd") or c.get("company_code"),
                            "name": c.get("comnm") or c.get("company_name")} for c in data]
                return {"org": org, "base": base, "company_path": path, "method": method, "centers": centers}
    return None


def main():
    orgs = json.loads((ROOT / "data" / "org_domains.json").read_text(encoding="utf-8"))
    jobs = [(org, host) for org, hosts in orgs.items() for host in hosts]
    fp = ROOT / "data" / "fingerprints.json"
    if fp.exists():      # sub-domains seen while fingerprinting (sports.*, yeyak.* ...)
        for r in json.loads(fp.read_text(encoding="utf-8")):
            host = r["final"].split("//")[1].split("/")[0] if r.get("final") else r["host"]
            jobs.append((r["org"], host))
    jobs = sorted(set(jobs))
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
