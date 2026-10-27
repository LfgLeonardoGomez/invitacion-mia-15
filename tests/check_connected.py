"""Real browser + API + temporary SQLite integration. No build, real guest data or deployment.

Run with Python + Playwright; --api-python points to the installed backend venv.
Only disposable credentials/data are generated; services bind loopback and stop on exit.
"""

import argparse
import base64
from contextlib import closing
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sqlite3
import sys
import tempfile
from threading import Thread
import time
from uuid import uuid4

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.serve_frontend import create_server


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-python", default=sys.executable)
    args = parser.parse_args()
    api_port = unused_port()
    key = secrets.token_urlsafe(32)
    frontend = create_server(0, api_base=f"http://127.0.0.1:{api_port}")
    base = f"http://127.0.0.1:{frontend.server_port}"
    thread = Thread(target=frontend.serve_forever, daemon=True)
    thread.start()

    def api(path, *, method="GET", data=None, admin=False):
        connection = HTTPConnection("127.0.0.1", api_port, timeout=5)
        headers = {"Authorization": f"Bearer {key}"} if admin else {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, f"/api{path}", body=None if data is None else json.dumps(data), headers=headers)
            response = connection.getresponse()
            body = response.read()
            assert response.status in {200, 201}, f"API check failed with HTTP {response.status}"
            return json.loads(body)
        finally:
            connection.close()

    try:
        with tempfile.TemporaryDirectory(prefix="mia-connected-") as directory:
            env = {**os.environ, "MIA_DATABASE_PATH": str(Path(directory) / "private.sqlite3"), "MIA_ADMIN_API_KEY": key,
                   "MIA_ALLOWED_ORIGINS": base, "MIA_ENABLE_DOCS": "false",
                   "MIA_LINK_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')}
            command = [args.api_python, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(api_port), "--no-access-log", "--no-proxy-headers"]
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        api("/health")
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("Temporary API failed to start; check --api-python dependencies.")
                        time.sleep(.1)

                pending = api("/admin/invitations", method="POST", data={"familyName": "Familia pendiente", "seats": 2}, admin=True)
                declined = api("/admin/invitations", method="POST", data={"familyName": "Familia no asiste", "seats": 2}, admin=True)
                api(f"/invitations/{declined['token']}/rsvp", method="PUT", data={"attending": False, "guestCount": 0})
                inactive = api('/admin/invitations', method='POST', data={'familyName': 'Familia Desactivada', 'seats': 2}, admin=True)
                api(f"/invitations/{inactive['token']}/rsvp", method='PUT', data={'attending': False, 'guestCount': 0})
                api(f"/admin/invitations/{inactive['id']}", method='PATCH', data={'active': False}, admin=True)

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    errors = []
                    admin = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
                    admin.on("pageerror", lambda error: errors.append(str(error)))
                    admin.add_init_script("Object.defineProperty(navigator, 'clipboard', {configurable:true,value:{writeText:async value=>{window.copiedPrivateLink=value;}}});")
                    admin.goto(f"{base}/admin.html", wait_until="networkidle")
                    admin.locator("#admin-key").fill(key)
                    admin.locator("#login-submit").click()
                    admin.locator("#dashboard").wait_for(state="visible")
                    admin.locator("#guests-list .guest-row").first.wait_for()
                    admin.reload(wait_until="networkidle")
                    admin.locator("#dashboard").wait_for(state="visible")
                    assert admin.locator("#admin-key").input_value() == ""
                    cookie = next(item for item in admin.context.cookies() if item['name'] == 'mia_admin_session')
                    assert cookie['httpOnly'] is True and cookie['sameSite'] == 'Strict'
                    assert cookie['path'].endswith('/api/admin')
                    family_name = "Familia <img src=x onerror=alert(1)>"
                    admin.locator("#family-name").fill(family_name)
                    admin.locator("#family-seats").fill("4")
                    admin.locator("#create-submit").click()
                    family_card = admin.locator('#guests-list .guest-row').filter(has_text=family_name)
                    family_card.wait_for()
                    assert family_card.locator('.guest-actions').is_hidden()
                    family_card.locator('.guest-summary').click()
                    family_card.get_by_role('button', name=f'Copiar enlace de {family_name}', exact=True).click()
                    admin.wait_for_function('Boolean(window.copiedPrivateLink)')
                    link = admin.evaluate('window.copiedPrivateLink')
                    assert link.startswith(f"{base}/?invitation=")
                    assert admin.locator('#invitation-link, #link-dialog').count() == 0
                    assert admin.evaluate('value => !document.body.innerHTML.includes(value)', link)
                    assert admin.locator("#guests-list img").count() == 0
                    admin.reload(wait_until='networkidle')
                    admin.locator('#dashboard').wait_for(state='visible')
                    family_card.locator('.guest-summary').click()
                    family_card.get_by_role('button', name=f'Copiar enlace de {family_name}', exact=True).click()
                    admin.wait_for_function('Boolean(window.copiedPrivateLink)')
                    assert admin.evaluate('window.copiedPrivateLink') == link
                    assert admin.evaluate('value => !document.body.innerHTML.includes(value)', link)

                    guest = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, reduced_motion="reduce")
                    guest.on("pageerror", lambda error: errors.append(str(error)))
                    guest.route("https://fonts.googleapis.com/**", lambda route: route.abort())
                    guest.route("https://fonts.gstatic.com/**", lambda route: route.abort())
                    guest.goto(link, wait_until="networkidle")
                    assert guest.evaluate("InvitationData.mode") == "api"
                    guest.locator("#enter-button").tap()
                    guest.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
                    assert guest.locator("#family-title").inner_text() == family_name
                    assert guest.locator("#guest-count-choices input").count() == 4
                    assert guest.locator("#family-title img").count() == 0
                    guest.get_by_role("radio", name="Sí, vamos a estar").check()
                    guest.get_by_role("radio", name="3 personas", exact=True).check()
                    guest.locator("#rsvp-submit").click()
                    guest.wait_for_function("document.getElementById('rsvp-status').textContent.includes('guardada')")
                    guest.reload(wait_until="networkidle")
                    guest.locator("#enter-button").tap()
                    guest.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
                    assert guest.get_by_role("radio", name="3 personas", exact=True).is_checked()
                    message = "Que tengas una noche hermosa, Mia. <img src=x onerror=alert(1)>"
                    guest.locator("#wish-author").fill("Prima <b>Ana</b>")
                    guest.locator("#wish-message").fill(message)
                    guest.locator("#wish-submit").click()
                    guest.wait_for_function("!document.getElementById('wish-preview').hidden")
                    assert guest.locator("#wish-preview-message").inner_text() == message
                    assert guest.locator("#wish-preview img").count() == 0
                    assert guest.locator("#wish-author").input_value() == ""
                    assert guest.locator("#wish-message").input_value() == ""
                    assert guest.locator("#wish-length").inner_text() == "0 / 600"
                    guest.reload(wait_until="networkidle")
                    assert guest.evaluate("InvitationData.load().then(data => data.wish.message)") == message

                    isolated = api(f"/invitations/{pending['token']}")
                    assert isolated["wish"] is None and isolated["rsvp"] is None
                    admin.locator("#refresh").click()
                    admin.wait_for_function("document.querySelector('[data-summary=confirmedInvitations]').textContent === '1'")
                    assert admin.locator('[data-summary="declinedInvitations"]').inner_text() == "1"
                    assert admin.locator('[data-summary="pendingInvitations"]').inner_text() == "1"
                    assert admin.locator('[data-summary="confirmedGuests"]').inner_text() == "3"
                    assert admin.locator('.summary-item [data-summary="reservedSeats"]').inner_text() == "8"
                    admin.locator("#wishes-list .wish-card").wait_for()
                    assert message in admin.locator("#wishes-list").inner_text()
                    assert admin.locator("#wishes-list img, #wishes-list b").count() == 0
                    # Input alone triggers searches, without submitting either form.
                    admin.locator('#guest-search').fill('Familia pendiente')
                    admin.wait_for_function("document.querySelectorAll('#guests-list .guest-row').length===1 && document.querySelector('#guests-list').textContent.includes('Familia pendiente')")
                    admin.locator('#guest-search').fill('')
                    admin.wait_for_function("document.querySelectorAll('#guests-list .guest-row').length===3")
                    for filter_name, expected in [("confirmed", family_name), ("declined", "Familia no asiste"), ("pending", "Familia pendiente")]:
                        admin.locator(f'[data-filter="{filter_name}"]').click()
                        admin.wait_for_function("expected => {const rows=document.querySelectorAll('#guests-list .guest-row');return rows.length===1 && rows[0].textContent.includes(expected);}", arg=expected)
                    assert admin.evaluate("localStorage.length === 0 && sessionStorage.length === 0")

                    screenshots = Path(tempfile.gettempdir()) / "mia-connected-review"
                    screenshots.mkdir(exist_ok=True)
                    admin.locator('[data-filter="active"]').click()
                    admin.wait_for_function("document.querySelectorAll('#guests-list .guest-row').length === 3")
                    admin.screenshot(path=str(screenshots / "admin-desktop.png"), full_page=True)
                    admin.set_viewport_size({"width": 390, "height": 844})
                    admin.screenshot(path=str(screenshots / "admin-mobile.png"), full_page=True)
                    assert admin.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    admin.locator('[data-filter="inactive"]').click()
                    archived_card = admin.locator('#guests-list .guest-card').filter(has_text='Familia Desactivada')
                    archived_card.wait_for()
                    assert admin.locator('#guests-list .guest-card').count() == 1
                    archived_card.locator('.guest-summary').click()
                    archived_card.get_by_role('button', name='Activar Familia Desactivada', exact=True).click()
                    admin.locator('#confirm-accept').click()
                    admin.wait_for_function("document.querySelectorAll('#guests-list .guest-card').length===0")
                    restored = api(f"/invitations/{inactive['token']}")
                    assert restored['rsvp']['attending'] is False and restored['rsvp']['guestCount'] == 0
                    admin.locator('[data-filter="active"]').click()
                    archived_card.wait_for()
                    archived_card.locator('.guest-summary').click()
                    archived_card.get_by_role('button', name='Desactivar Familia Desactivada', exact=True).click()
                    admin.locator('#confirm-accept').click()
                    archived_card.wait_for(state='detached')
                    assert admin.locator('#guests-list .guest-card').count() == 3
                    admin.locator("#logout").click()
                    assert admin.locator("#dashboard").is_hidden()
                    assert admin.locator("#guests-list").inner_text() == ""
                    assert admin.locator("#wishes-list").inner_text() == ""
                    assert admin.locator("#admin-key").input_value() == ""
                    admin.reload(wait_until="networkidle")
                    admin.locator('#login-panel').wait_for(state='visible')
                    assert admin.locator('#dashboard').is_hidden()

                    admin.locator("#admin-key").fill("x" * 43)
                    admin.locator("#login-submit").click()
                    admin.wait_for_function("document.getElementById('login-status').textContent.includes('no es válida')")
                    assert admin.locator("#dashboard").is_hidden()
                    assert admin.locator("#admin-key").input_value() == ""

                    # Seed nine prior messages in the disposable DB, so the next browser
                    # submission tests the family quota rather than the per-minute IP limit.
                    family_id = guest.evaluate('InvitationData.load().then(data => data.invitation.id)')
                    with closing(sqlite3.connect(Path(directory) / 'private.sqlite3')) as db, db:
                        for _ in range(9):
                            db.execute('INSERT INTO wishes VALUES (?, ?, ?, ?, ?, ?)',
                                       (str(uuid4()), family_id, str(uuid4()), 'Fixture', 'Deseo anterior', '2026-10-27T00:00:00Z'))
                    guest.locator('#enter-button').tap()
                    guest.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
                    guest.locator('#wish-author').fill('No perder nombre')
                    guest.locator('#wish-message').fill('No perder el deseo al alcanzar el límite')
                    guest.locator('#wish-submit').click()
                    guest.wait_for_function("document.getElementById('wish-status').textContent.includes('10 mensajes')")
                    assert guest.locator('#wish-author').input_value() == 'No perder nombre'
                    assert guest.locator('#wish-message').input_value() == 'No perder el deseo al alcanzar el límite'
                    assert guest.locator('#form-feedback').get_attribute('data-kind') == 'error'
                    assert guest.locator('.form-feedback__lantern').is_hidden()

                    bad = browser.new_page(reduced_motion="reduce")
                    bad.on("pageerror", lambda error: errors.append(str(error)))
                    bad.route("https://fonts.googleapis.com/**", lambda route: route.abort())
                    bad.route("https://fonts.gstatic.com/**", lambda route: route.abort())
                    pending_requests = set()
                    bad.on("request", lambda request: pending_requests.add(request.resource_type))
                    bad.on("requestfinished", lambda request: pending_requests.discard(request.resource_type))
                    bad.on("requestfailed", lambda request: pending_requests.discard(request.resource_type))
                    try:
                        bad.goto(f"{base}/?invitation={'A' * 43}", wait_until="networkidle")
                    except Exception:
                        print(json.dumps({"bad_page_pending_resource_types": sorted(pending_requests), "state": bad.evaluate("document.readyState"), "load_error": bad.locator('#invitation-load-status').inner_text()}))
                        raise
                    assert bad.locator("#enter-button").is_disabled()
                    assert bad.locator("#invitation-load-retry").is_visible()
                    assert bad.locator("#invitation").is_hidden() or bad.locator("#invitation").evaluate("el => getComputedStyle(el).opacity === '0'")
                    assert bad.evaluate("InvitationData.mode") == "api"
                    assert not errors, errors
                    browser.close()
                    print(json.dumps({"connected_api_admin_guest": "PASS", "temporary_database": True, "persistence": True, "private_wishes": True, "wish_limit": 10, "filters": ["active", "inactive", "confirmed", "declined", "pending"], "inactive_reactivation_preserves_rsvp": True, "session_refresh": True, "live_search": True, "wish_form_reset": True, "encrypted_link_copy_after_reload": True, "link_never_in_dom": True, "family_people_summary": True, "logout": True, "invalid_link_no_mock": True, "page_errors": 0, "screenshots": str(screenshots)}))
            finally:
                if process.poll() is None:
                    if os.name == 'nt':
                        # The Windows venv launcher may own a separate Python child.
                        # Stop only this test's freshly spawned process tree.
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    else:
                        process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        frontend.shutdown()
        frontend.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
