"""Shows where INFY's documents come from and whether each downloads. Run: python check_docs.py [TICKER]"""
import sys, time
from backend.pull.docs import pick_documents
from backend import db
from backend.sources.http import get

t = (sys.argv[1] if len(sys.argv) > 1 else "INFY").upper()
with db.session() as conn:
    n = conn.execute("SELECT COUNT(*) FROM documents WHERE ticker=?", (t,)).fetchone()[0]
    print(f"{n} documents known for {t}")
    picked = pick_documents(conn, t)
for kind, docs in picked.items():
    for d in docs:
        t0 = time.time()
        try:
            r = get(d["url"])
            print(f"OK    {kind:14} {len(r.content)/1e6:6.1f} MB  {time.time()-t0:5.1f}s  {d['url'][:90]}")
        except Exception as e:
            print(f"FAIL  {kind:14} {time.time()-t0:5.1f}s  {d['url'][:90]}  -> {str(e)[:80]}")
