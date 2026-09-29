import subprocess, pathlib
from playwright.sync_api import sync_playwright
BASE="https://dronav2.onrender.com"; OUT=pathlib.Path("/tmp/shots2/05-admin")
def pw(a): return subprocess.run(["security","find-generic-password","-a",a,"-s","DRONA","-w"],capture_output=True,text=True).stdout.strip()
with sync_playwright() as p:
    ctx=p.chromium.launch().new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
    pg=ctx.new_page(); pg.goto(f"{BASE}/login/", wait_until="domcontentloaded", timeout=120000)
    pg.wait_for_timeout(1000)
    pg.click("button.login-tab >> text='Admin / Management'"); pg.wait_for_timeout(600)
    pg.fill("form:visible input[name='employee_id']","ADMIN001")
    pg.fill("form:visible input[name='password']", pw("ADMIN001"))
    pg.click("form:visible button[type=submit], form:visible input[type=submit]")
    pg.wait_for_load_state("domcontentloaded", timeout=120000); pg.wait_for_timeout(1000)
    for name, path in [("08-mgmt-module-edit","/manage/modules/1/edit/"),
                       ("11-mgmt-lesson-edit","/manage/lessons/1/edit/")]:
        r=pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=120000); pg.wait_for_timeout(1400)
        pg.screenshot(path=str(OUT/f"{name}.png"))
        print(f"{name:<24} {r.status} {pg.url.replace(BASE,'')}", flush=True)
    ctx.close()
