import subprocess, pathlib, sys, time
from playwright.sync_api import sync_playwright
BASE="https://dronav2.onrender.com"; OUT=pathlib.Path("/tmp/shots2")
def pw(a): return subprocess.run(["security","find-generic-password","-a",a,"-s","DRONA","-w"],capture_output=True,text=True).stdout.strip()
def sign_in(p, acct, admin):
    ctx=p.chromium.launch().new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
    pg=ctx.new_page(); pg.goto(f"{BASE}/login/", wait_until="domcontentloaded", timeout=120000)
    pg.wait_for_timeout(1000)
    if admin: pg.click("button.login-tab >> text='Admin / Management'"); pg.wait_for_timeout(600)
    pg.fill("form:visible input[name='employee_id']", acct)
    pg.fill("form:visible input[name='password']", pw(acct))
    pg.click("form:visible button[type=submit], form:visible input[type=submit]")
    pg.wait_for_load_state("domcontentloaded", timeout=120000); pg.wait_for_timeout(900)
    return ctx, pg
RESULTS=[]
def snap(ctx,pg,folder,name,path,note=""):
    f=OUT/folder/f"{name}.png"; f.parent.mkdir(parents=True, exist_ok=True)
    try:
        r=pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=120000); pg.wait_for_timeout(1500)
        pg.screenshot(path=str(f))
        RESULTS.append((folder,name,r.status if r else 0,pg.url.replace(BASE,''),note))
        print(f"[{folder}] {name:<30} {r.status} {pg.url.replace(BASE,'')}", flush=True)
    except Exception as e:
        RESULTS.append((folder,name,"ERR","",str(e)[:60])); print(f"[{folder}] {name:<30} ERR {str(e)[:50]}", flush=True)
    time.sleep(0.4)

with sync_playwright() as p:
    # ---------- ANONYMOUS ----------
    ctx=p.chromium.launch().new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
    pg=ctx.new_page()
    snap(ctx,pg,"01-public","01-login","/login/","both role tabs")
    snap(ctx,pg,"01-public","02-register","/register/","self-signup")
    snap(ctx,pg,"01-public","03-password-reset","/password-reset/","request reset link")
    snap(ctx,pg,"01-public","04-404-error","/no-such-page/","custom error page")
    # verify page is public (masked)
    snap(ctx,pg,"01-public","05-certificate-verify-public","/verify/SRMS-CERT-2026-02052A00/","public, surname masked")
    ctx.close()

    # ---------- STAFF ----------
    ctx,pg = sign_in(p,"EMP001",False)
    if "/login/" in pg.url: print("STAFF LOGIN FAILED")
    else:
        snap(ctx,pg,"02-staff","01-dashboard","/","stats + my courses + available")
        snap(ctx,pg,"02-staff","02-profile","/profile/","personal details + prefs")
        snap(ctx,pg,"02-staff","03-certificates","/certificates/","earned certificates")
        snap(ctx,pg,"02-staff","04-training-calendar","/training-calendar/","sessions")
        snap(ctx,pg,"02-staff","05-course-detail","/courses/9/","modules + lessons + ticks")
        snap(ctx,pg,"02-staff","06-lesson-video","/lessons/43/","video player + resume")
        snap(ctx,pg,"02-staff","07-lesson-2","/lessons/44/","second lesson")
        snap(ctx,pg,"02-staff","08-quiz","/quizzes/course/9/","assessment")
        # hindi
        pg.goto(f"{BASE}/language/toggle/", wait_until="domcontentloaded", timeout=120000); pg.wait_for_timeout(600)
        snap(ctx,pg,"03-hindi","01-dashboard-hi","/","bilingual UI")
        snap(ctx,pg,"03-hindi","02-course-detail-hi","/courses/9/","content _hi fields")
        snap(ctx,pg,"03-hindi","03-certificates-hi","/certificates/","")
        pg.goto(f"{BASE}/language/toggle/", wait_until="domcontentloaded", timeout=120000); pg.wait_for_timeout(600)
    ctx.close()

    # ---------- HOD ----------
    ctx,pg = sign_in(p,"HOD_IT",True)
    if "/login/" in pg.url: print("HOD LOGIN FAILED")
    else:
        snap(ctx,pg,"04-hod","01-hr-dashboard","/analytics/","dept analytics")
        snap(ctx,pg,"04-hod","02-watch-progress","/analytics/watch-progress/","staff x lessons")
        snap(ctx,pg,"04-hod","03-management-console","/manage/","console home")
        snap(ctx,pg,"04-hod","04-mgmt-courses","/manage/courses/","course list")
        snap(ctx,pg,"04-hod","05-mgmt-course-detail","/manage/courses/1/","edit surface")
        snap(ctx,pg,"04-hod","06-mgmt-bulk-enroll","/manage/enroll/","department enrol")
        snap(ctx,pg,"04-hod","07-mgmt-assign-staff","/manage/enroll/assign/","per-student assign")
        snap(ctx,pg,"04-hod","08-mgmt-sessions","/manage/sessions/","scheduled sessions")
        snap(ctx,pg,"04-hod","09-mgmt-session-new","/manage/sessions/new/","create session")
        snap(ctx,pg,"04-hod","10-mgmt-staff-import","/manage/staff/import/","import roster")
        snap(ctx,pg,"04-hod","11-ai-quiz-generator","/quizzes/ai-generate/","Gemini generation")
    ctx.close()

    # ---------- ADMIN ----------
    ctx,pg = sign_in(p,"ADMIN001",True)
    if "/login/" in pg.url: print("ADMIN LOGIN FAILED")
    else:
        snap(ctx,pg,"05-admin","01-management-console","/manage/","")
        snap(ctx,pg,"05-admin","02-certificate-directory","/certificates/","admin sees all + filters")
        snap(ctx,pg,"05-admin","03-hr-dashboard","/analytics/","all departments")
        snap(ctx,pg,"05-admin","04-watch-progress","/analytics/watch-progress/","")
        snap(ctx,pg,"05-admin","05-mgmt-create-user","/manage/users/create/","provision HOD/staff")
        snap(ctx,pg,"05-admin","06-mgmt-course-new","/manage/courses/new/","create course")
        snap(ctx,pg,"05-admin","07-mgmt-course-edit","/manage/courses/1/edit/","edit course")
        snap(ctx,pg,"05-admin","08-mgmt-module-edit","/modules/1/edit/","edit module")
        snap(ctx,pg,"05-admin","09-mgmt-lesson-new","/manage/modules/1/lessons/new/","upload lesson")
        snap(ctx,pg,"05-admin","10-django-admin","/admin/","django admin")
    ctx.close()

print("\n=== FAILURES ===")
f=[r for r in RESULTS if r[2] not in (200,)]
print(f if f else "none")
