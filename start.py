"""One command to run FINN locally:  python start.py

Starts the API (port 8000) and the web app (port 3000). On first run, tries live data; if the
sources are unreachable it loads the frozen snapshot or clearly-labelled SAMPLE data so the app is still usable.
"""
import os, shutil, signal, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
os.chdir(ROOT)


def prepare_data() -> None:
    from backend import db
    db.init_db()
    with db.session() as conn:
        has_prices = conn.execute("SELECT COUNT(*) c FROM prices").fetchone()["c"] > 0
        has_ann = conn.execute("SELECT COUNT(*) c FROM announcements").fetchone()["c"] > 0
    if not has_prices:
        print("First run: trying live data...")
        try:
            from backend.pipeline import ingest_prices
            ingest_prices.run()
            has_prices = True
        except Exception as exc:  # noqa: BLE001
            print("  live prices unavailable:", exc)
            from backend import snapshot_store
            if snapshot_store.load():
                print("  loaded the frozen snapshot from data/snapshot.db.")
                return
            print("  loading SAMPLE data instead (shown with a banner in the app).")
            from backend.pipeline import sample_data
            sample_data.generate(force=True)
            return
    if not has_ann:
        try:
            from backend.pipeline import ingest_announcements
            ingest_announcements.run()
        except Exception as exc:  # noqa: BLE001
            print("  announcements unavailable (the app still works without them):", exc)
    try:
        from backend.push import alerts, process
        process.run()
        alerts.evaluate()
    except Exception as exc:  # noqa: BLE001
        print("  processing step failed:", exc)


def main() -> None:
    if not shutil.which("npm"):
        sys.exit("Node.js is not installed. Install the LTS version from https://nodejs.org, "
                 "open a NEW terminal window, and run python3 start.py again.")
    prepare_data()
    web = ROOT / "web"
    if not (web / "node_modules").exists():
        print("Installing web packages (first run only, about a minute)...")
        subprocess.check_call(["npm", "install"], cwd=web)
    os.environ.setdefault("FINN_AUTO_REFRESH", "1")
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api.main:app", "--port", "8000"]),
        subprocess.Popen(["npm", "run", "dev"], cwd=web),
    ]
    print("\nFINN is starting: open http://localhost:3000  (API: http://localhost:8000/docs)\n")

    def stop(*_):
        for p in procs:
            p.terminate()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    for p in procs:
        p.wait()


if __name__ == "__main__":
    main()
