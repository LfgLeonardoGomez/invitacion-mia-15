"""Panel checks with a deterministic mock API; no real key/data and no build."""

import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.serve_frontend import create_server


def inspect(browser, width, height):
    server = create_server(0, api_base="http://127.0.0.1:8000")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce" if width == 320 else "no-preference")
    page = context.new_page()
    page.add_init_script("""window.testClipboard = []; window.testClipboardDenied = false;
      Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async value => {
        if (window.testClipboardDenied) throw Error('clipboard denied');
        window.testClipboard.push(value);
      }}});""")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    families = [
        {"id": "first", "familyName": "Familia Primera", "seats": 4, "active": True, "rsvp": {"attending": True, "guestCount": 3}},
        {"id": "second", "familyName": "Familia Segunda", "seats": 2, "active": True, "rsvp": {"attending": False, "guestCount": 0}},
        {"id": "third", "familyName": "Familia Pendiente", "seats": 3, "active": True, "rsvp": None},
    ] + [{"id": str(i), "familyName": f"Familia {i:02}", "seats": 1, "active": True, "rsvp": None} for i in range(20)]
    families[3]["familyName"] = "Familia <img src=x onerror=alert(1)>"
    wishes = [{"id": "wish", "familyName": "Familia Primera", "author": "<img src=x onerror=alert(1)>", "message": "<script>not HTML</script>", "createdAt": "2026-10-26T10:00:00Z"}]
    requests = []
    held = []
    flags = {"hold_confirmed": False, "hold_search": False, "hold_link": False, "link_unavailable": False, "unauthorized": False, "authenticated": False, "logout_fail": False}
    held_links = []
    links = {item['id']: 'a' * 43 for item in families}
    links['third'] = None
    csrf = "C" * 43
    searches = []
    sections = {"eventUtcOffset": "-03:00", "contact": {"whatsappNumber": "5491141675124"}, "bankTransfer": {"holder": "Prueba", "bank": "Prueba", "alias": "alias.prueba", "accountNumber": "", "illustrative": True}}

    def fulfill(route, data, status=200, headers=None):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data), headers={"Access-Control-Allow-Origin": base, "Access-Control-Allow-Credentials": "true", **(headers or {})})

    def session_data():
        return {"authenticated": True, "csrfToken": csrf, "expiresAt": "2099-01-01T00:00:00Z"}

    def handle(route):
        request = route.request
        parts = urlsplit(request.url)
        query = parse_qs(parts.query)
        path = parts.path.removeprefix("/api/admin")
        requests.append((request.method, path))
        if request.method == "OPTIONS":
            fulfill(route, {}, headers={"Access-Control-Allow-Headers": "Authorization, X-CSRF-Token, Content-Type", "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS"})
            return
        if path == "/session" and request.method == "POST":
            assert request.headers.get("authorization") == "Bearer " + "A" * 40
            flags["authenticated"] = True
            fulfill(route, session_data(), headers={"Set-Cookie": "mia_admin_session=opaque-session; Path=/api/admin; HttpOnly; SameSite=Strict"})
            return
        assert request.headers.get("authorization") is None, "Only the initial login may send the original key"
        if flags["unauthorized"] or not flags["authenticated"]:
            fulfill(route, {"detail": "Unauthorized"}, 401)
        elif path == "/session" and request.method == "GET":
            assert "mia_admin_session=opaque-session" in (request.header_value("cookie") or "")
            fulfill(route, session_data())
        elif path == "/session" and request.method == "DELETE":
            assert request.headers.get("x-csrf-token") == csrf
            if flags["logout_fail"]:
                route.abort("failed")
            else:
                flags["authenticated"] = False
                fulfill(route, {"authenticated": False}, headers={"Set-Cookie": "mia_admin_session=; Path=/api/admin; Max-Age=0; HttpOnly; SameSite=Strict"})
        elif path == "/summary":
            active = [item for item in families if item["active"]]
            fulfill(route, {"totalInvitations": len(families), "activeInvitations": len(active), "confirmedInvitations": sum(bool(item["rsvp"] and item["rsvp"]["attending"]) for item in active), "declinedInvitations": sum(bool(item["rsvp"] and not item["rsvp"]["attending"]) for item in active), "pendingInvitations": sum(item["rsvp"] is None for item in active), "confirmedGuests": sum(item["rsvp"]["guestCount"] for item in active if item["rsvp"]), "reservedSeats": sum(item["seats"] for item in active), "totalWishes": len(wishes)})
        elif path == "/sections":
            if request.method == "PUT":
                assert request.headers.get("x-csrf-token") == csrf
                sections.update(request.post_data_json)
            fulfill(route, sections)
        elif path == "/invitations" and request.method == "POST":
            assert request.headers.get("x-csrf-token") == csrf
            body = request.post_data_json
            item = {"id": "new", **body, "active": True, "rsvp": None}
            families.insert(0, item)
            links['new'] = 'b' * 43
            fulfill(route, {**item, "token": "b" * 43, "invitationPath": "/?invitation=" + "b" * 43}, 201)
        elif path == "/invitations":
            state = query.get("status", ["all"])[0]
            text = query.get("q", [""])[0].lower()
            searches.append(("guests", text))
            if text == "primera" and flags["hold_search"]:
                held.append(route)
                return
            if state == "confirmed" and flags["hold_confirmed"]:
                held.append(route)
                return
            result = list(families)
            if state == 'active':
                result = [item for item in result if item['active']]
            elif state == 'inactive':
                result = [item for item in result if not item['active']]
            elif state != "all":
                result = [item for item in result if item["active"] and ((state == "pending" and not item["rsvp"]) or (state == "confirmed" and item["rsvp"] and item["rsvp"]["attending"]) or (state == "declined" and item["rsvp"] and not item["rsvp"]["attending"]))]
            result = [item for item in result if text in item["familyName"].lower()]
            offset = int(query.get("offset", [0])[0])
            limit = int(query.get("limit", [20])[0])
            fulfill(route, result[offset:offset + limit])
        elif path.endswith('/link') and request.method == 'GET':
            identifier = path.split('/')[-2]
            if flags['hold_link']:
                held_links.append(route)
            elif flags['link_unavailable']:
                fulfill(route, {'detail': 'private server configuration'}, 503)
            elif links.get(identifier) is None:
                fulfill(route, {'detail': 'Legacy unrecoverable'}, 409)
            else:
                fulfill(route, {'id': identifier, 'token': links[identifier], 'invitationPath': '/?invitation=' + links[identifier]})
        elif path.endswith("/rotate-token"):
            assert request.headers.get("x-csrf-token") == csrf
            links[path.split('/')[-2]] = 'c' * 43
            fulfill(route, {"id": "new", "token": "c" * 43})
        elif path.startswith("/invitations/") and request.method == "PATCH":
            assert request.headers.get("x-csrf-token") == csrf
            item = next(item for item in families if item["id"] == path.split("/")[-1])
            body = request.post_data_json
            if item["rsvp"] and body.get("seats", item["seats"]) < item["rsvp"]["guestCount"]:
                fulfill(route, {"detail": "Conflict"}, 409)
            else:
                item.update(body)
                fulfill(route, item)
        elif path == "/wishes":
            text = query.get("q", [""])[0].lower()
            searches.append(("wishes", text))
            fulfill(route, [wish for wish in wishes if text in (wish["author"] + wish["message"]).lower()])
        else:
            fulfill(route, {"detail": "Not found"}, 404)

    page.route("http://127.0.0.1:8000/api/admin/**", handle)
    try:
        page.goto(base + "/admin.html", wait_until="networkidle")
        assert requests == [("GET", "/session")]
        page.locator("#admin-key").fill("A" * 40)
        page.locator("#login-submit").click()
        page.locator(".guest-row").first.wait_for()
        page.locator('#bank-submit').wait_for(state='visible')
        page.wait_for_function("!document.getElementById('bank-submit').disabled")
        assert 'ilustrativos' in page.locator('#bank-status').inner_text()
        page.locator('#bank-holder').fill('Mia Aylen Torres')
        page.locator('#bank-name').fill('Mercado Pago')
        page.locator('#bank-alias').fill('mia.aylen.torres67')
        page.locator('#bank-submit').click()
        page.wait_for_function("document.getElementById('bank-status').textContent.includes('Datos guardados')")
        assert sections['bankTransfer']['alias'] == 'mia.aylen.torres67'
        assert sections['bankTransfer']['illustrative'] is False
        assert sections['contact']['whatsappNumber'] == '5491141675124'
        page.locator('#bank-enabled').uncheck()
        page.locator('#bank-submit').click()
        page.wait_for_function("document.getElementById('bank-status').textContent.includes('ocultos')")
        assert sections['bankTransfer'] is None
        assert page.locator("#admin-key").input_value() == ""
        assert any(cookie["name"] == "mia_admin_session" and cookie["httpOnly"] for cookie in context.cookies())
        assert page.locator(".guest-row").count() == 20
        assert page.locator('.summary-item').first.locator('[data-summary="reservedSeats"]').inner_text() == '29'
        assert page.locator(".wish-copy").inner_text() == "<script>not HTML</script>"
        assert page.locator("#wishes-list script, #wishes-list img").count() == 0
        assert page.evaluate("localStorage.length + sessionStorage.length") == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.reload(wait_until="networkidle")
        page.locator(".guest-row").first.wait_for()
        assert requests.count(("POST", "/session")) == 1, "Reload must restore the cookie, not ask for or resend the key"
        assert page.locator("#login-panel").is_hidden()
        output = Path(tempfile.gettempdir()) / "mia-admin-review"
        output.mkdir(exist_ok=True)
        assert page.locator('article.guest-card').count() == 20
        assert page.locator('.guest-card.is-open').count() == 0
        assert page.locator('.guest-card .guest-actions button').first.is_hidden()
        assert page.locator('#guests-list img').count() == 0
        assert page.locator('.guest-name').nth(3).text_content() == "Familia <img src=x onerror=alert(1)>"
        title = page.locator('.guest-name').first
        original_title = title.text_content()
        title.evaluate("element => {element.textContent='familia gómez de la cruz';}")
        assert title.inner_text() == 'Familia Gómez De La Cruz'
        title.evaluate('(element,value) => {element.textContent=value;}', original_title)
        assert page.locator('.guest-meta').first.evaluate('element => getComputedStyle(element).textAlign') == 'center'
        assert page.locator('.guest-card').first.locator('.guest-state').is_visible()
        columns = page.locator('#guests-list').evaluate("element => getComputedStyle(element).gridTemplateColumns.split(' ').length")
        assert columns == (2 if width > 1100 else 1)
        summary = page.locator('.guest-summary').first
        summary.scroll_into_view_if_needed()
        summary.focus()
        assert summary.evaluate("element => getComputedStyle(element).outlineStyle !== 'none'")
        page.keyboard.press('Enter')
        assert page.locator('.guest-card').first.evaluate("element => element.classList.contains('is-open')")
        assert summary.get_attribute('aria-expanded') == 'true'
        assert page.get_by_role('button', name='Editar Familia Primera', exact=True).is_visible()
        assert page.get_by_role('button', name='Cerrar opciones de Familia Primera', exact=True).evaluate('element => element === document.activeElement')
        assert page.locator('.guest-front').first.evaluate('element => element.inert')
        page.locator('.guest-card').first.screenshot(path=str(output / f'family-card-{width}x{height}-open.png'))
        page.keyboard.press('Space')
        assert not page.locator('.guest-card').first.evaluate("element => element.classList.contains('is-open')")
        assert summary.evaluate('element => element === document.activeElement')
        assert page.locator('.guest-actions').first.evaluate('element => element.inert')
        page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement.classList.contains('guest-summary')"), 'Closed actions must not receive keyboard focus'
        summary.focus()
        geometry = """() => ({scrollY, cards:[...document.querySelectorAll('.guest-card')].slice(0,3).map(card => {const box=card.getBoundingClientRect();return {top:box.top+scrollY,height:box.height};})})"""
        baseline = page.evaluate(geometry)

        def assert_no_reflow():
            current = page.evaluate(geometry)
            assert abs(current['scrollY'] - baseline['scrollY']) < 1, (width, baseline, current)
            for previous, present in zip(baseline['cards'], current['cards']):
                assert abs(previous['top'] - present['top']) < 1 and abs(previous['height'] - present['height']) < 1, (width, baseline, current)

        box = summary.bounding_box()
        page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
        assert_no_reflow()
        page.wait_for_timeout(80)
        assert_no_reflow()
        assert page.locator('.guest-rotator').first.evaluate("element => getComputedStyle(element).transform === 'none'") == (width == 320)
        page.wait_for_timeout(180)
        assert_no_reflow()
        page.locator('.guest-copy-status').first.evaluate("element => {element.textContent = 'Error largo para probar el área interna. '.repeat(80);}")
        assert_no_reflow()
        assert page.locator('.guest-copy-status').first.evaluate('element => element.scrollHeight > element.clientHeight')
        page.locator('.guest-copy-status').first.evaluate("element => {element.textContent='';}")
        page.locator('.guest-rotator').first.evaluate('async element => {await Promise.all(element.getAnimations().map(animation => animation.finished));}')
        close_box = page.get_by_role('button', name='Cerrar opciones de Familia Primera', exact=True).bounding_box()
        # A real pointer click must not inherit locator.click's automatic scrolling
        # while an ancestor is rotated in 3D.
        page.mouse.click(close_box['x'] + close_box['width']/2, close_box['y'] + close_box['height']/2)
        assert_no_reflow()
        page.wait_for_timeout(80)
        assert_no_reflow()
        page.wait_for_timeout(180)
        assert_no_reflow()
        page.locator('.guest-rotator').first.evaluate('async element => {await Promise.all(element.getAnimations().map(animation => animation.finished));}')
        assert_no_reflow()
        box = summary.bounding_box()
        page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
        page.keyboard.press('Escape')
        assert summary.evaluate('element => element === document.activeElement')
        assert_no_reflow()
        summary.click()
        page.locator('.guest-summary').nth(1).click()
        assert not page.locator('.guest-card').first.evaluate("element => element.classList.contains('is-open')")
        assert page.locator('.guest-card.is-open').count() == 1
        page.get_by_role('button', name='Cerrar opciones de Familia Segunda', exact=True).click()
        page.locator('.guest-card').first.screenshot(path=str(output / f'family-card-{width}x{height}-closed.png'))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / f"admin-{width}x{height}.png"), full_page=True)
        page.locator("#guests-next").click()
        page.wait_for_function("document.getElementById('guests-page').textContent === 'Página 2'")
        assert page.locator(".guest-row").count() == 3
        page.locator("#guest-search").fill("Se")
        page.locator("#guest-search").fill("Segu")
        page.locator("#guest-search").fill("Segunda")
        page.wait_for_function("document.querySelectorAll('.guest-row').length === 1 && document.querySelector('.guest-name').textContent === 'Familia Segunda'")
        assert page.locator("#guests-page").inner_text() == "Página 1"
        assert searches.count(("guests", "segunda")) == 1
        flags["hold_search"] = True
        page.locator("#guest-search").fill("Primera")
        page.wait_for_timeout(350)
        assert held
        page.locator("#guest-search").fill("Segunda")
        for route in held:
            fulfill(route, [families[0]])
        held.clear()
        flags["hold_search"] = False
        page.wait_for_timeout(80)
        assert page.locator(".guest-name").inner_text() == "Familia Segunda", "Typing must invalidate responses immediately, before the debounce ends"
        page.wait_for_timeout(300)
        page.locator("#guest-search").fill("")
        page.wait_for_function("document.querySelectorAll('.guest-row').length === 20")
        page.locator("#wish-search").fill("sin-coincidencias")
        page.wait_for_function("document.querySelectorAll('.wish-card').length === 0")
        page.locator("#wish-search").fill("script")
        page.wait_for_function("document.querySelectorAll('.wish-card').length === 1")
        assert ("wishes", "script") in searches
        page.locator("#wish-search").fill("")
        page.locator('[data-filter="declined"]').click()
        page.wait_for_function("document.querySelectorAll('.guest-row').length === 1")
        assert page.locator(".guest-name").inner_text() == "Familia Segunda"
        assert page.locator("#guests-page").inner_text() == "Página 1"
        flags["hold_confirmed"] = True
        page.locator('[data-filter="confirmed"]').click()
        page.wait_for_timeout(80)
        page.locator('[data-filter="declined"]').click()
        page.wait_for_function("document.querySelector('.guest-name')?.textContent === 'Familia Segunda'")
        for route in held:
            fulfill(route, [families[0]])
        held.clear()
        flags["hold_confirmed"] = False
        page.wait_for_timeout(80)
        assert page.locator(".guest-name").inner_text() == "Familia Segunda", "Stale responses must not overwrite the latest filter"

        page.locator("#family-name").fill("Familia Nueva")
        page.locator("#family-seats").fill("4")
        page.locator("#create-submit").click()
        page.wait_for_function("document.getElementById('create-status').textContent.startsWith('Invitación creada')")
        assert page.locator('#link-dialog, #invitation-link').count() == 0
        assert 'b' * 43 not in page.content()
        page.locator('[data-filter="active"]').click()
        page.wait_for_function("document.querySelector('.guest-name')?.textContent === 'Familia Nueva'")
        page.locator('.guest-summary').first.click()
        page.get_by_role('button', name='Copiar enlace de Familia Nueva', exact=True).click()
        page.wait_for_function("document.querySelector('.guest-card .guest-copy-status').textContent.startsWith('Enlace copiado')")
        copied = page.evaluate('window.testClipboard.at(-1)')
        assert copied == base + '/?invitation=' + 'b' * 43
        assert copied not in page.content() and 'b' * 43 not in page.content()
        assert page.evaluate('localStorage.length + sessionStorage.length') == 0
        page.reload(wait_until='networkidle')
        page.locator('.guest-summary').first.click()
        page.get_by_role('button', name='Copiar enlace de Familia Nueva', exact=True).click()
        page.wait_for_function('window.testClipboard.length === 1')
        assert page.evaluate('window.testClipboard[0]') == copied
        page.evaluate('window.testClipboardDenied = true')
        page.get_by_role('button', name='Copiar enlace de Familia Nueva', exact=True).click()
        page.wait_for_function("document.querySelector('.guest-copy-status').textContent.includes('No pudimos copiar')")
        assert len(page.evaluate('window.testClipboard')) == 1
        assert copied not in page.content() and 'b' * 43 not in page.content()
        page.evaluate('window.testClipboardDenied = false')
        flags['link_unavailable'] = True
        page.get_by_role('button', name='Copiar enlace de Familia Nueva', exact=True).click()
        page.wait_for_function("document.querySelector('.guest-copy-status').textContent.includes('configuración del servidor')")
        assert 'private server configuration' not in page.content()
        flags['link_unavailable'] = False
        legacy = page.locator('.guest-card').filter(has=page.locator('.guest-name', has_text='Familia Pendiente'))
        legacy.locator('.guest-summary').click()
        rotations_before = sum(path.endswith('/rotate-token') for _, path in requests)
        page.get_by_role('button', name='Copiar enlace de Familia Pendiente', exact=True).click()
        page.wait_for_function("[...document.querySelectorAll('.guest-copy-status')].some(el => el.textContent.includes('enlace anterior no se puede recuperar'))")
        assert sum(path.endswith('/rotate-token') for _, path in requests) == rotations_before
        page.locator('.guest-summary').first.click()
        page.get_by_role("button", name="Regenerar enlace de Familia Nueva", exact=True).click()
        page.locator("#confirm-accept").click()
        page.wait_for_function("document.getElementById('dashboard-status').textContent.startsWith('Enlace regenerado')")
        assert page.locator('.guest-copy-status').first.text_content().startswith('Enlace regenerado')
        assert page.locator('#link-dialog, #invitation-link').count() == 0
        assert 'c' * 43 not in page.content()
        assert page.locator('.guest-summary').first.get_attribute('aria-expanded') == 'false'
        page.locator('.guest-summary').first.click()
        page.get_by_role('button', name='Copiar enlace de Familia Nueva', exact=True).click()
        page.wait_for_function("window.testClipboard.at(-1)?.endsWith('c'.repeat(43))")
        assert page.evaluate('window.testClipboard.at(-1)') == base + '/?invitation=' + 'c' * 43
        page.get_by_role("button", name="Desactivar Familia Nueva", exact=True).click()
        page.locator("#confirm-accept").click()
        page.wait_for_function("![...document.querySelectorAll('.guest-card .guest-name')].some(el=>el.textContent==='Familia Nueva')")
        page.locator('[data-filter="inactive"]').click()
        page.wait_for_function("document.querySelector('.guest-card .guest-state')?.textContent === 'Desactivada'")
        page.locator('.guest-summary').first.click()
        page.get_by_role("button", name="Activar Familia Nueva", exact=True).wait_for()
        assert page.locator(".guest-row").first.locator(".guest-state").text_content() == "Desactivada"
        page.get_by_role('button', name='Activar Familia Nueva', exact=True).click()
        page.locator('#confirm-accept').click()
        page.wait_for_function("document.querySelectorAll('.guest-card').length===0")
        page.locator('[data-filter="active"]').click()
        page.wait_for_function("[...document.querySelectorAll('.guest-card .guest-name')].some(el=>el.textContent==='Familia Nueva')")
        page.locator('.guest-card').filter(has=page.locator('.guest-name', has_text='Familia Primera')).locator('.guest-summary').click()
        page.get_by_role("button", name="Editar Familia Primera", exact=True).click()
        page.locator("#edit-seats").fill("1")
        page.locator("#edit-submit").click()
        page.wait_for_function("document.getElementById('edit-status').textContent.includes('cantidad confirmada')")
        assert page.locator("#edit-dialog").evaluate("el => el.open")
        assert page.locator('.guest-card.is-open').count() == 0
        page.locator('[data-close="edit-dialog"]').click()
        page.wait_for_function("document.activeElement.classList.contains('guest-summary')")
        page.locator('.guest-card').filter(has=page.locator('.guest-name', has_text='Familia Primera')).locator('.guest-summary').click()
        flags['hold_link'] = True
        before_writes = page.evaluate('window.testClipboard.length')
        page.get_by_role('button', name='Copiar enlace de Familia Primera', exact=True).click()
        page.wait_for_timeout(100)
        assert held_links
        page.keyboard.press('Escape')
        for route in held_links:
            fulfill(route, {'id': 'first', 'token': 'a' * 43, 'invitationPath': '/?invitation=' + 'a' * 43})
        held_links.clear()
        flags['hold_link'] = False
        page.wait_for_timeout(100)
        assert page.evaluate('window.testClipboard.length') == before_writes, 'Closing the card must invalidate a pending copy'
        page.locator('.guest-card').filter(has=page.locator('.guest-name', has_text='Familia Primera')).locator('.guest-summary').click()
        flags['hold_link'] = True
        before_writes = page.evaluate('window.testClipboard.length')
        page.get_by_role('button', name='Copiar enlace de Familia Primera', exact=True).click()
        page.wait_for_timeout(100)
        assert held_links
        assert page.get_by_role('button', name='Copiar enlace de Familia Primera', exact=True).is_disabled()
        page.locator("#logout").click()
        page.wait_for_function("!document.getElementById('login-panel').hidden && document.getElementById('login-status').textContent === ''")
        for route in held_links:
            fulfill(route, {'id': 'first', 'token': 'a' * 43, 'invitationPath': '/?invitation=' + 'a' * 43})
        held_links.clear()
        flags['hold_link'] = False
        page.wait_for_timeout(100)
        assert page.evaluate('window.testClipboard.length') == before_writes, 'A late link response must not copy after logout'
        assert page.locator("#dashboard").is_hidden()
        assert page.locator("#wishes-list").inner_text() == ""
        assert page.locator("#guests-list").inner_text() == ""
        assert page.locator("#confirm-copy").inner_text() == ""
        assert "Familia Primera" not in page.content()
        assert page.evaluate("sessionStorage.length") == 0
        page.reload(wait_until="networkidle")
        assert page.locator("#dashboard").is_hidden(), "A completed logout must stay logged out after reload"
        page.locator("#admin-key").fill("A" * 40)
        page.locator("#login-submit").click()
        page.locator(".guest-row").first.wait_for()
        flags["logout_fail"] = True
        page.locator("#logout").click()
        page.wait_for_function("document.getElementById('login-status').textContent.includes('no pudimos verificar')")
        assert page.locator("#dashboard").is_hidden()
        assert page.locator("#logout-retry").is_visible()
        assert page.evaluate("sessionStorage.getItem('mia.admin.logoutPending')") == "1"
        before = len(requests)
        page.reload(wait_until="networkidle")
        assert len(requests) == before, "An uncertain logout must not silently restore the private session"
        assert page.locator("#dashboard").is_hidden()
        flags["logout_fail"] = False
        page.locator("#logout-retry").click()
        page.wait_for_function("document.getElementById('login-status').textContent === ''")
        assert page.evaluate("sessionStorage.length") == 0
        page.locator("#admin-key").fill("A" * 40)
        page.locator("#login-submit").click()
        page.locator(".guest-row").first.wait_for()
        flags["unauthorized"] = True
        page.locator("#refresh").click()
        page.wait_for_function("!document.getElementById('login-panel').hidden")
        assert page.locator("#guests-list").inner_text() == ""
        assert page.locator("#admin-key").input_value() == ""
        assert not errors, errors
        return {"viewport": [width, height], "passed": True, "requests": len(requests)}
    finally:
        context.close()
        server.shutdown()
        server.server_close()


def inspect_unconfigured(browser):
    server = create_server(0)
    Thread(target=server.serve_forever, daemon=True).start()
    page = browser.new_page()
    requests = []
    page.on("request", lambda request: requests.append(request.url) if "/api/" in request.url else None)
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}/admin.html", wait_until="networkidle")
        assert page.locator("#config-notice").is_visible()
        assert page.locator("#login-submit").is_disabled()
        assert not requests
    finally:
        page.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            inspect_unconfigured(browser)
            results = [inspect(browser, width, height) for width, height in [(320, 568), (390, 844), (1440, 900)]]
            print(json.dumps({"checks": results, "config_fail_closed": True}))
        finally:
            browser.close()
