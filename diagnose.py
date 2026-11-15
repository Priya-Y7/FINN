"""Tries several ways of calling NSE and BSE and prints what each returns. Run: python diagnose.py"""
import requests
from curl_cffi import requests as cr

NSE_HOME = "https://www.nseindia.com/"
NSE_API = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=SBIN&from_date=01-11-2026&to_date=15-11-2026"
BSE_API = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&subcategory=-1"
           "&strPrevDate=20261101&strToDate=20261115&strSearch=P&strscrip=500112&strType=C")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

def show(label, fn):
    try:
        r = fn()
        body = r.text[:140].replace("\n", " ")
        print(f"{r.status_code}  {label}  | {body}")
    except Exception as e:
        print(f"ERR  {label}  | {type(e).__name__}: {str(e)[:120]}")

print("--- Your network / IP as the sites see it")
show("ipinfo", lambda: requests.get("https://ipinfo.io/json", timeout=15))
print("--- NSE homepage")
show("requests + Mac UA", lambda: requests.get(NSE_HOME, headers={"User-Agent": UA}, timeout=20))
for imp in ["chrome", "chrome124", "safari", "firefox"]:
    show(f"curl_cffi {imp}", lambda imp=imp: cr.get(NSE_HOME, impersonate=imp, timeout=20))
print("--- NSE API after visiting homepage")
for imp in ["chrome", "safari"]:
    def go(imp=imp):
        s = cr.Session(impersonate=imp); s.get(NSE_HOME, timeout=20)
        return s.get(NSE_API, headers={"Accept": "application/json, text/plain, */*", "Referer": NSE_HOME + "companies-listing/corporate-filings-announcements"}, timeout=20)
    show(f"curl_cffi {imp}", go)
print("--- BSE API")
H = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/"}
show("requests + Mac UA", lambda: requests.get(BSE_API, headers={**H, "User-Agent": UA}, timeout=20))
for imp in ["chrome", "safari", "firefox"]:
    show(f"curl_cffi {imp}", lambda imp=imp: cr.get(BSE_API, impersonate=imp, headers=H, timeout=20))
