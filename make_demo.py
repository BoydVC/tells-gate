"""Render demo.gif: sloppy draft highlighted -> hover a tell -> apply rewrite -> clean. Synthetic text only."""
import io, shutil, subprocess, sys, time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4351
srv = subprocess.Popen([sys.executable, "-m", "tells_gate", "serve", "--port", str(PORT)], cwd=__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
for _ in range(50):
    try:
        __import__("urllib.request").request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1); break
    except Exception:
        time.sleep(0.1)
frames, durs = [], []
def snap(page, ms):
    frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB")); durs.append(ms)
try:
    with sync_playwright() as p:
        chrome = next((c for c in ("/usr/local/bin/google-chrome", "/usr/bin/google-chrome") if Path(c).exists()), None)
        launch = {"args": ["--no-proxy-server", "--no-sandbox", "--disable-dev-shm-usage"]}
        if chrome:
            launch["executable_path"] = chrome
        b = p.chromium.launch(**launch)
        page = b.new_page(viewport={"width": 1100, "height": 620}, device_scale_factor=1)
        page.goto(f"http://127.0.0.1:{PORT}/?text=", wait_until="load"); print(page.url, page.content()[:200], flush=True)
        page.wait_for_timeout(300); snap(page, 600)
        page.click("#sample"); page.wait_for_timeout(600); snap(page, 2200)
        for i in range(0, 6):
            page.hover(f"#hits li:nth-child({i*3+1})"); page.wait_for_timeout(150); snap(page, 700)
        page.mouse.move(5, 5)
        page.hover("#apply"); page.wait_for_timeout(200); snap(page, 700)
        page.click("#apply"); page.wait_for_timeout(700); snap(page, 3200)
        b.close()
finally:
    srv.terminate()
pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
pal[0].save("demo.gif", save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True)
Path("screenshots").mkdir(exist_ok=True)
shutil.copyfile("demo.gif", "screenshots/demo.gif")
frames[1].save("out/demo-sloppy.png"); frames[-1].save("out/demo-clean.png")
print("frames", len(frames))
