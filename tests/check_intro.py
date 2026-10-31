"""Intro browser checks; run directly with Python + Playwright (no build needed)."""

import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = (Path(__file__).resolve().parents[1] / "index.html").as_uri()
OUTPUT = Path(tempfile.gettempdir()) / "mia-intro-review"
OUTPUT.mkdir(exist_ok=True)

SAMPLE = """() => {
  const image = document.querySelector('.entrance__image').getBoundingClientRect();
  const lights = [...document.querySelectorAll('[data-lantern-x]')].map(light => {
    const rect = light.getBoundingClientRect();
    return {
      errorX: Math.abs(rect.x + rect.width / 2 - (image.x + image.width * Number(light.dataset.lanternX))),
      errorY: Math.abs(rect.y + rect.height / 2 - (image.y + image.height * Number(light.dataset.lanternY))),
      opacity: Number(getComputedStyle(light).opacity),
    };
  });
  return {
    image: {left: image.left, top: image.top, right: image.right, bottom: image.bottom},
    lights,
    invitationOpacity: Number(getComputedStyle(document.getElementById('invitation')).opacity),
    camera: getComputedStyle(document.getElementById('entrance-artwork')).transform,
  };
}"""


def inspect_viewport(browser, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    page.wait_for_function("document.querySelector('.entrance__image').naturalWidth === 941")
    assert page.locator("#entrance").inner_text().strip().casefold() == "ingresar"
    assert page.locator("#entrance img").count() == 1
    assert page.locator("#enter-button svg").count() == 2
    assert page.locator("#enter-button").evaluate("el => { const s = getComputedStyle(el); return s.borderTopWidth === '0px' && s.backgroundColor === 'rgba(0, 0, 0, 0)' && s.boxShadow === 'none'; }")
    assert page.locator("#music-toggle").is_hidden()
    assert page.locator("#background-music").evaluate("audio => audio.paused && audio.currentTime === 0")
    page.screenshot(path=str(OUTPUT / f"{width}x{height}-start.png"))
    page.locator("#enter-button").click()
    page.evaluate("""() => {
      const targets = [
        document.getElementById('entrance-artwork'),
        ...document.querySelectorAll('[data-lantern-x]'),
        document.querySelector('.entrance__shade'),
        document.querySelector('.entrance__footer'),
        document.getElementById('invitation'),
      ];
      window.introTestAnimations = targets.flatMap(target => target.getAnimations());
      window.introTestAnimations.forEach(animation => animation.pause());
    }""")
    # Pausing can resolve startTime to null, so sample geometry rather than a wall-clock delay.
    samples = []
    for progress in [0, .25, .5, .7, .85, .98]:
        page.evaluate("time => introTestAnimations.forEach(animation => animation.currentTime = time)", progress * 3500)
        sample = page.evaluate(SAMPLE)
        assert page.locator(".hero-enter, .reveal-item").evaluate_all("elements => elements.every(el => Number(getComputedStyle(el).opacity) === 0)"), "Only the empty background should emerge during the intro"
        rect = sample["image"]
        assert rect["left"] <= .5 and rect["top"] <= .5, (width, height, progress, rect)
        assert rect["right"] >= width - .5 and rect["bottom"] >= height - .5, (width, height, progress, rect)
        assert all(light["errorX"] < 1 and light["errorY"] < 1 for light in sample["lights"]), sample
        samples.append(sample)
        if width == 390 and progress in [.5, .7, .85]:
            page.screenshot(path=str(OUTPUT / f"{width}x{height}-{progress}.png"))
    assert samples[1]["lights"][0]["opacity"] > 0, "Light must grow during early camera movement"
    assert all(a["lights"][0]["opacity"] <= b["lights"][0]["opacity"] for a, b in zip(samples, samples[1:]))
    assert 0 < samples[4]["invitationOpacity"] < 1, "Reveal must overlap the still-moving camera"
    assert samples[4]["camera"] != samples[5]["camera"], "Camera must keep moving during reveal"
    page.evaluate("introTestAnimations.forEach(animation => animation.finish())")
    page.wait_for_function("document.getElementById('entrance').hidden")
    assert page.locator("#invitation").is_visible()
    assert page.evaluate("document.activeElement.id") == "invitation"
    assert page.locator("#music-toggle").is_visible()
    assert page.locator(".invite-shell").count() == 0
    assert page.locator(".invite-hero").evaluate("el => { const s = getComputedStyle(el); return s.borderTopWidth === '0px' && s.backgroundColor === 'rgba(0, 0, 0, 0)' && s.boxShadow === 'none'; }")
    assert page.locator(".date-line").inner_text() == "26 · Diciembre · 2026"
    assert page.locator('[data-event="dressCode"]').inner_text() == 'Elegante Sport'
    assert page.locator('#contact-section .section-copy').inner_text() == 'Comunicate con mi mamá'
    assert page.locator('#contact-whatsapp span').text_content() == 'Escribir por Whatsapp'
    assert page.locator(".date-separator").count() == 2
    assert page.locator(".date-line").evaluate("el => getComputedStyle(el).fontWeight") == '400'
    assert page.locator(".eyebrow, .date-line").evaluate_all("elements => elements.every(el => getComputedStyle(el).color.endsWith('0.72)'))")
    assert page.locator("#music-toggle").evaluate("el => el.closest('.invite-hero') !== null && getComputedStyle(el).position !== 'fixed'")
    assert page.locator(".invite-hero__name").evaluate("el => parseFloat(getComputedStyle(el).fontSize) >= 94")
    tiara_width = page.locator(".invite-hero .tiara-wrap").bounding_box()["width"]
    assert abs(tiara_width - min(148, width * .36)) < 1, "Keep the tiara size"
    assert page.locator(".invitation__ambient").evaluate("el => getComputedStyle(el).position === 'fixed'")
    assert page.locator(".invitation__ambient .floating-lantern").count() == 8
    lighting = page.locator(".floating-lantern").evaluate_all(r"""elements => elements.map(el => {
      const halo = getComputedStyle(el, '::before');
      const flame = getComputedStyle(el, '::after');
      const alphas = value => [...value.matchAll(/rgba\([^)]*,\s*([\d.]+)\)/g)].map(match => Number(match[1]));
      return {
        width: parseFloat(getComputedStyle(el).width),
        haloSize: parseFloat(halo.width),
        haloAlpha: alphas(halo.backgroundImage)[0],
        flameAlpha: alphas(flame.backgroundColor)[0],
      };
    }).sort((a, b) => a.width - b.width)""")
    for small, large in zip(lighting, lighting[1:]):
        if small['width'] == large['width']:
            assert small['haloAlpha'] == large['haloAlpha']
            continue
        assert small['haloSize'] < large['haloSize']
        assert small['haloAlpha'] < large['haloAlpha']
        assert small['flameAlpha'] < large['flameAlpha']
    assert lighting[-1]['haloAlpha'] > lighting[0]['haloAlpha'] * 2
    assert page.locator(".detail-card").first.evaluate(r"""el => {
      const style = getComputedStyle(el);
      const alphas = [...style.backgroundImage.matchAll(/rgba\([^)]*,\s*([\d.]+)\)/g)].map(match => Number(match[1]));
      return style.borderTopLeftRadius.startsWith('46%') && alphas.length >= 3 && alphas.every(alpha => alpha < .6);
    }"""), "Reference-style cards need an arched top and translucent fill"
    page.evaluate("""() => {
      const targets = [...document.querySelectorAll('.hero-enter')];
      window.contentTestAnimations = targets.flatMap(target => target.getAnimations());
      window.contentTestAnimations.forEach(animation => animation.pause());
    }""")
    content_samples = []
    assert page.locator('[data-hero-enter="tiara"]').evaluate("el => el.getAnimations()[0].effect.getTiming().duration") == 1100
    for milliseconds in [0, 150, 450, 800, 1200, 2300]:
        page.evaluate("time => contentTestAnimations.forEach(animation => animation.currentTime = time)", milliseconds)
        opacities = page.locator(".hero-enter").evaluate_all("elements => elements.map(el => Number(getComputedStyle(el).opacity))")
        content_samples.append(opacities)
        if width == 390:
            page.screenshot(path=str(OUTPUT / f"{width}x{height}-content-{milliseconds}.png"))
    assert all(opacity == 0 for opacity in content_samples[1]), "Keep a short empty-background pause"
    assert content_samples[2][0] > 0 and all(opacity == 0 for opacity in content_samples[2][1:]), "Tiara should appear first"
    assert content_samples[3][0] > 0 and content_samples[3][1] > 0 and content_samples[3][3] == 0, "Name should follow the softer tiara fade before the data"
    assert all(opacity == 1 for opacity in content_samples[-1])
    page.evaluate("contentTestAnimations.forEach(animation => animation.finish())")
    page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
    date = page.locator(".date-line").bounding_box()
    player = page.locator("#music-player").bounding_box()
    hero_footer = page.locator('.hero-footer').bounding_box()
    hero_rect = page.locator('.invite-hero').bounding_box()
    scroll_cue = page.locator('.scroll-cue').bounding_box()
    assert player["y"] - date["y"] - date["height"] >= 51.5, "Separate the secondary player from the identity"
    assert abs(player['y'] - hero_footer['y']) < 1
    assert 23 < hero_rect['y'] + hero_rect['height'] - (scroll_cue['y'] + scroll_cue['height']) < 25, 'Anchor the player/scroll group at the foot of the hero in normal flow'
    assert page.locator('.music-control').evaluate("el => getComputedStyle(el).boxShadow") == 'none', 'Do not give the secondary player a glowing focal treatment'
    name_width = page.locator(".invite-hero__name").bounding_box()["width"]
    assert name_width >= tiara_width, "Mia should balance the unchanged tiara without stretching glyphs"
    name = page.locator(".invite-hero__name").bounding_box()
    hero = page.locator(".invite-hero").bounding_box()
    optical_shift = (hero['x'] + hero['width'] / 2) - (name['x'] + name['width'] / 2)
    assert 4 < optical_shift < 8, "Apply the small leftward optical correction"
    assert page.locator(".detail-card").last.evaluate("el => Number(getComputedStyle(el).opacity)") == 0, "Offscreen sections must not reveal on a timer"
    if width == 390:
        page.screenshot(path=str(OUTPUT / f"{width}x{height}-revealed.png"))
    soft_reveals_checked = 0
    for index in range(page.locator(".reveal-item").count()):
        section = page.locator(".reveal-item").nth(index)
        assert section.evaluate("el => !['fixed', 'sticky'].includes(getComputedStyle(el).position)")
        section.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'instant'})")
        page.wait_for_function("index => Boolean(document.querySelectorAll('.reveal-item')[index].dataset.revealState)", arg=index)
        if section.get_attribute("data-reveal-state") == 'revealing':
            softness = section.evaluate("""el => {
              const animations = el.getAnimations({subtree: true});
              animations.forEach(animation => { animation.pause(); animation.currentTime = 500; });
              const content = el.children.length ? [...el.children].filter(child => !child.classList.contains('card-gem')) : [el];
              return {
                duration: animations[0].effect.getTiming().duration,
                opacity: Number(getComputedStyle(el).opacity),
                contentFilters: content.map(child => getComputedStyle(child).filter),
                isCard: el.classList.contains('detail-card'),
                cardFilter: getComputedStyle(el).filter,
              };
            }""")
            assert softness['duration'] == 1200
            assert 0 < softness['opacity'] < 1
            assert any(value.startswith('blur(') and value != 'blur(0px)' for value in softness['contentFilters'])
            assert not softness['isCard'] or softness['cardFilter'] == 'none', "Do not blur card surfaces and frames"
            section.evaluate("el => el.getAnimations({subtree: true}).forEach(animation => animation.finish())")
            soft_reveals_checked += 1
        page.wait_for_function("index => document.querySelectorAll('.reveal-item')[index].dataset.revealState === 'revealed'", arg=index)
        assert section.evaluate("el => Number(getComputedStyle(el).opacity)") == 1
        assert section.evaluate("el => [el, ...el.querySelectorAll('*')].filter(child => !child.classList.contains('card-gem')).every(child => getComputedStyle(child).filter === 'none')")
        if width == 390 and index == 1:
            page.screenshot(path=str(OUTPUT / f"{width}x{height}-cards.png"))
    page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")
    closing = page.locator('.closing-section__title').bounding_box()
    signature = page.locator('#event-footer').bounding_box()
    castle = page.locator('.castle-crop').bounding_box()
    assert closing['y'] >= 8, 'The final viewport must include Te espero, not just the castle'
    assert closing['y'] + closing['height'] < signature['y'] < castle['y']
    assert castle['y'] + castle['height'] <= height + 1, 'Keep the cropped castle and final signature together in the viewport'
    assert page.locator('.closing-section__title, #event-footer, #castle-scene').evaluate_all("els => els.every(el => el.closest('.invitation-closing'))")
    page.screenshot(path=str(OUTPUT / f'{width}x{height}-compact-closing.png'))
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    assert page.locator(".reveal-item").evaluate_all("elements => elements.every(el => el.dataset.revealState === 'revealed' && el.getAnimations().length === 0)"), "Scroll reveals should run only once"
    assert not errors, errors
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Sections must fit without horizontal scrolling'
    assert soft_reveals_checked > 0
    page.close()
    return {"viewport": f"{width}x{height}", "intro_samples": len(samples), "content_samples": len(content_samples), "scroll_reveal": True, "passed": True}


def inspect_reduced_motion(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page.goto(URL, wait_until="networkidle")
    page.locator("#enter-button").click()
    assert page.locator("#enter-button").is_disabled()
    assert page.locator("#entrance-artwork").evaluate("el => el.getAnimations().length") == 0
    page.wait_for_function("document.getElementById('entrance').hidden", timeout=2000)
    assert page.evaluate("document.activeElement.id") == "invitation"
    assert page.locator(".reveal-item").evaluate_all("elements => elements.every(el => el.dataset.revealState === 'revealed')")
    page.close()
    return {"reduced_motion": True, "passed": True}


def inspect_music(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    audio_requests = []
    errors = []
    page.on('request', lambda request: audio_requests.append(request.url) if '.mp3' in request.url else None)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until="networkidle")
    assert not audio_requests, 'Do not download audio before Ingresar'
    assert page.locator('#music-player').is_hidden()
    page.locator("#enter-button").click()
    page.wait_for_function("document.getElementById('background-music').currentTime > .1")
    page.wait_for_function("document.getElementById('entrance').hidden")
    assert page.locator("#background-music").evaluate("audio => audio.duration > 263 && audio.duration < 265 && audio.volume <= .55")
    assert page.locator('#music-position').inner_text() == '1 / 3'
    assert page.locator('#background-music').evaluate('audio => !audio.loop')
    assert all('mia-soundtrack.mp3' in url for url in audio_requests), 'Only the selected song should load'
    for selector in ['#music-previous', '#music-next']:
        rect = page.locator(selector).bounding_box()
        assert rect['width'] >= 44 and rect['height'] >= 44
    assert page.locator('.music-transport button').evaluate_all('buttons => buttons.map(button => button.id)') == ['music-previous', 'music-toggle', 'music-next']
    previous = page.locator('#music-previous').bounding_box()
    play = page.locator('#music-toggle').bounding_box()
    following = page.locator('#music-next').bounding_box()
    assert 0 <= play['x'] - (previous['x'] + previous['width']) <= 2
    assert 0 <= following['x'] - (play['x'] + play['width']) <= 2
    page.get_by_role('button', name='Canción siguiente', exact=True).click()
    page.wait_for_function("document.getElementById('background-music').src.includes('mia-my-one-and-only-love.mp3') && document.getElementById('background-music').currentTime > .1")
    assert page.locator('#music-track-title').inner_text() == 'My One And Only Love'
    assert page.locator('#music-position').inner_text() == '2 / 3'
    assert page.locator('#background-music').evaluate('audio => audio.duration > 181 && audio.duration < 183')
    assert not any('mia-understand.mp3' in url for url in audio_requests)
    page.locator('#music-player').screenshot(path=str(OUTPUT / 'playlist-player.png'))
    page.get_by_role("button", name="Pausar música").click()
    assert page.locator("#background-music").evaluate("audio => audio.paused")
    page.get_by_role('button', name='Canción siguiente', exact=True).click()
    assert page.locator('#music-position').inner_text() == '3 / 3'
    assert page.locator('#background-music').evaluate('audio => audio.paused'), 'Keep pause when navigating a paused playlist'
    page.get_by_role("button", name="Reproducir música").click()
    page.wait_for_function("document.getElementById('background-music').currentTime > .1")
    assert page.locator('#background-music').evaluate('audio => audio.duration > 149 && audio.duration < 151')
    page.evaluate("document.getElementById('background-music').currentTime = document.getElementById('background-music').duration - .08")
    page.wait_for_function("document.getElementById('music-position').textContent === '1 / 3' && document.getElementById('background-music').currentTime > .1")
    page.get_by_role('button', name='Canción anterior', exact=True).click()
    page.wait_for_function("document.getElementById('music-position').textContent === '3 / 3' && document.getElementById('background-music').currentTime > .1")
    page.evaluate("() => {for (let i = 0; i < 5; i++) document.getElementById('music-next').click();}")
    page.wait_for_function("document.getElementById('music-position').textContent === '2 / 3' && document.getElementById('background-music').currentTime > .1")
    assert page.locator('#music-status').is_hidden(), 'Rapid skips must not show stale play/load errors'
    page.evaluate("() => {const audio = document.getElementById('background-music'); audio.src = './assets/does-not-exist-test-only.mp3'; audio.load();}")
    page.wait_for_function("!document.getElementById('music-status').hidden")
    assert page.locator('#music-status').inner_text().startswith('No pudimos')
    page.get_by_role('button', name='Canción siguiente', exact=True).click()
    page.get_by_role('button', name='Reproducir música', exact=True).click()
    page.wait_for_function("document.getElementById('background-music').currentTime > .1")
    assert page.locator('#music-position').inner_text() == '3 / 3'
    assert page.locator('#music-status').is_hidden()
    assert not errors, errors
    page.close()
    return {"playlist_real_audio_lazy_load_navigation_pause_wrap_rapid_skip_and_error_recovery": True, "passed": True}


def inspect_touch_feedback(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=3, reduced_motion='reduce')
    page.goto(URL, wait_until='networkidle')
    assert page.evaluate("matchMedia('(pointer: coarse)').matches")
    assert page.locator('#enter-button').evaluate("el => getComputedStyle(el).webkitTapHighlightColor") == 'rgba(0, 0, 0, 0)'
    page.locator('#enter-button').tap()
    page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
    assert page.locator('button, a, summary, label, input, textarea').evaluate_all("els => els.every(el => getComputedStyle(el).webkitTapHighlightColor === 'rgba(0, 0, 0, 0)')"), 'No native blue mobile tap overlays'
    next_button = page.locator('#music-next')
    next_button.scroll_into_view_if_needed()
    rect = next_button.bounding_box()
    touch = page.context.new_cdp_session(page)
    touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': rect['x'] + rect['width']/2, 'y': rect['y'] + rect['height']/2}]})
    page.wait_for_function("document.getElementById('music-next').classList.contains('is-touch-pressed')")
    page.wait_for_function("getComputedStyle(document.getElementById('music-next')).backgroundColor === 'rgba(197, 156, 104, 0.1)'")
    page.locator('#music-player').screenshot(path=str(OUTPUT / 'mobile-warm-press.png'))
    touch.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    page.wait_for_function("!document.getElementById('music-next').classList.contains('is-touch-pressed') && getComputedStyle(document.getElementById('music-next')).backgroundColor === 'rgba(0, 0, 0, 0)'")
    assert next_button.evaluate("el => !el.matches(':focus-visible') && getComputedStyle(el).outlineStyle === 'none'")
    position_before_cancel = page.locator('#music-position').inner_text()
    touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': rect['x'] + rect['width']/2, 'y': rect['y'] + rect['height']/2}]})
    page.wait_for_function("document.getElementById('music-next').classList.contains('is-touch-pressed')")
    touch.send('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []})
    page.wait_for_function("!document.querySelector('.is-touch-pressed')")
    assert page.locator('#music-position').inner_text() == position_before_cancel, 'A cancelled swipe must not click the player or leave a pressed state'
    page.get_by_role('radio', name='Sí, vamos a estar', exact=True).tap()
    page.get_by_role('radio', name='2 personas', exact=True).tap()
    assert page.get_by_role('radio', name='2 personas', exact=True).is_checked()
    assert page.get_by_role('radio', name='2 personas', exact=True).evaluate("el => !el.matches(':focus-visible') && getComputedStyle(el.nextElementSibling).outlineStyle === 'none'")
    page.locator('#transfer-open').tap()
    assert page.locator('#transfer-dialog').evaluate('el => el.open')
    page.locator('#transfer-close').tap()
    assert page.locator('#transfer-dialog').is_hidden()
    page.close()

    keyboard = browser.new_page(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
    keyboard.goto(URL, wait_until='networkidle')
    keyboard.keyboard.press('Tab')
    assert keyboard.evaluate("document.activeElement.id === 'enter-button' && document.activeElement.matches(':focus-visible')")
    assert keyboard.locator('#enter-button').evaluate("el => {const s=getComputedStyle(el); return s.outlineStyle === 'solid' && s.outlineWidth === '2px' && s.outlineColor === 'rgb(229, 201, 149)';}")
    keyboard.keyboard.press('Enter')
    keyboard.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
    keyboard.keyboard.press('Tab')
    assert keyboard.evaluate("document.activeElement.id === 'music-previous' && document.activeElement.matches(':focus-visible')")
    assert keyboard.locator('#music-previous').evaluate("el => getComputedStyle(el).outlineColor") == 'rgb(229, 201, 149)'
    keyboard.locator('#music-player').screenshot(path=str(OUTPUT / 'keyboard-gold-focus.png'))
    keyboard.close()
    return {'mobile_transparent_tap_warm_press_and_keyboard_gold_focus': True, 'passed': True}


def inspect_gift_modal(browser):
    for width, height in [(320, 568), (390, 844), (844, 390), (1440, 900)]:
        mobile = width < 600
        page = browser.new_page(viewport={'width': width, 'height': height}, is_mobile=mobile, has_touch=mobile, reduced_motion='reduce')
        page.goto(URL, wait_until='networkidle')
        page.locator('#enter-button').click()
        page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
        button = page.locator('#transfer-open')
        button.scroll_into_view_if_needed()
        gift_height = page.locator('.gifts-section').bounding_box()['height']
        scroll_before = page.evaluate('scrollY')
        button.click()
        modal = page.locator('#transfer-dialog')
        assert modal.evaluate("el => el.open && el.matches(':modal')")
        assert page.evaluate("document.activeElement.id === 'transfer-close'")
        assert page.evaluate("document.body.style.overflow === 'hidden'")
        assert page.locator('.gifts-section').bounding_box()['height'] == gift_height, 'Do not expand the invitation beneath the modal'
        rect = modal.bounding_box()
        assert rect['x'] >= 15 and rect['y'] >= 19
        assert rect['x'] + rect['width'] <= width - 15 and rect['y'] + rect['height'] <= height - 19
        assert modal.evaluate("el => getComputedStyle(el).backdropFilter === 'blur(12px)' && getComputedStyle(el).opacity === '1'")
        if width in [320, 390, 844]:
            page.screenshot(path=str(OUTPUT / f'gift-modal-{width}x{height}.png'))
        page.locator('#transfer-holder').click()
        assert modal.evaluate('el => el.open'), 'Clicking content must not close the modal'
        if not mobile:
            page.mouse.move(rect['x'] + 18, rect['y'] + 18)
            page.mouse.down()
            page.mouse.move(4, 4)
            page.mouse.up()
            assert modal.evaluate('el => el.open'), 'Dragging from content to the backdrop is not a dismissal click'
        for _ in range(8):
            page.keyboard.press('Tab')
            # The browser's own chrome may receive focus; underlying page controls may not.
            assert page.evaluate("document.activeElement.closest('#transfer-dialog') !== null || (document.activeElement === document.body && !document.hasFocus())"), 'Native modal must not focus the underlying invitation'
        page.keyboard.press('Escape')
        assert modal.is_hidden()
        page.wait_for_function("document.body.style.overflow !== 'hidden' && document.activeElement.id === 'transfer-open'")
        assert abs(page.evaluate('scrollY') - scroll_before) < 2
        button.click()
        if mobile:
            page.touchscreen.tap(4, 4)
        else:
            page.mouse.click(4, 4)
        assert modal.is_hidden(), 'A click that starts on the backdrop closes the modal'
        button.click()
        page.locator('#transfer-close').click()
        assert modal.is_hidden()
        page.wait_for_function("document.body.style.overflow !== 'hidden'")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.close()
    return {'translucent_gift_modal_bounds_focus_escape_backdrop_and_scroll_restore': True, 'passed': True}


def inspect_contact_and_castle(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until='networkidle')
    page.locator('#enter-button').click()
    page.evaluate("document.getAnimations().filter(a => a.effect.target.closest('#entrance') || a.effect.target.id === 'invitation').forEach(a => a.finish())")
    page.wait_for_function("document.getElementById('entrance').hidden")
    assert page.locator('#castle-scene').evaluate("el => !el.classList.contains('is-active')")
    assert page.locator('.castle-lantern').evaluate_all("els => els.every(el => getComputedStyle(el).animationPlayState === 'paused')")
    link = page.locator('#contact-whatsapp')
    href = link.get_attribute('href')
    assert href.startswith('https://wa.me/5491141675124?text=')
    assert 'invitation=' not in href and 'Gomez' not in href
    assert link.get_attribute('rel') == 'noopener noreferrer'
    assert link.get_attribute('aria-label') == 'Contactar a la mamá de Mia por WhatsApp'
    page.locator('#contact-section').scroll_into_view_if_needed()
    page.wait_for_function("document.getElementById('contact-section').dataset.revealState === 'revealed'")
    page.screenshot(path=str(OUTPUT / 'contact-preview.png'))
    page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")
    page.wait_for_function("document.getElementById('castle-scene').classList.contains('is-active')")
    page.wait_for_function("getComputedStyle(document.querySelector('.ambient-lanterns')).opacity === '0'")
    page.wait_for_function("document.querySelector('.castle-image').naturalWidth === 941")
    assert page.locator('.castle-image').get_attribute('src') == page.locator('.entrance__image').get_attribute('src'), 'Reuse the original artwork without altering the intro asset'
    assert page.locator('.castle-image').evaluate("img => img.naturalHeight === 1672 && getComputedStyle(img).filter.includes('brightness(0.68)')")
    assert page.locator('.castle-crop').evaluate("el => getComputedStyle(el).overflow === 'hidden' && getComputedStyle(el).maskImage.includes('castle-photo-mask') && el.clientWidth <= 380"), 'Show a bounded, softly masked castle crop, never the entire photo'
    framing = page.locator('.castle-image').evaluate("""img => {
      const image = img.getBoundingClientRect();
      const crop = img.parentElement.getBoundingClientRect();
      const scale = image.width / img.naturalWidth;
      return { x: (crop.x - image.x) / scale, y: (crop.y - image.y) / scale, width: crop.width / scale, height: crop.height / scale };
    }""")
    assert abs(framing['x'] - 125) < 1 and abs(framing['y'] - 360) < 1
    assert abs(framing['width'] - 425) < 1 and abs(framing['height'] - 480) < 1, 'Trim 140px of the lower village without shrinking or squeezing the towers'
    page.screenshot(path=str(OUTPUT / 'castle-footer.png'))
    start = page.locator('.castle-lantern').evaluate_all("""els => els.map(el => {
      const animation = el.getAnimations()[0];
      animation.pause();
      // Remove the seeded CSS phase before sampling; negative currentTime is a
      // before-active phase in Chromium even when the CSS delay is negative.
      animation.effect.updateTiming({delay: 0});
      animation.currentTime = 0;
      const rect = el.getBoundingClientRect();
      const image = document.querySelector('.castle-crop').getBoundingClientRect();
      return {x: rect.x + rect.width / 2, y: rect.y, imageX: image.x, imageRight: image.right, imageY: image.y, imageBottom: image.bottom, height: image.height};
    })""")
    assert len(start) == 8
    assert all(lamp['imageX'] < lamp['x'] < lamp['imageRight'] and .74 < (lamp['y'] - lamp['imageY']) / lamp['height'] < .84 for lamp in start), 'Keep each launch behind the same terraces after trimming the base'
    middle = page.locator('.castle-lantern').evaluate_all("""els => els.map(el => {
      const animation = el.getAnimations()[0];
      const timing = animation.effect.getTiming();
      animation.currentTime = timing.delay + timing.duration * .5;
      return el.getBoundingClientRect().y;
    })""")
    assert all(lamp['y'] - y > 200 for lamp, y in zip(start, middle)), 'Lanterns must rise from their origin, not spawn at an unrelated viewport point'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    page.wait_for_function("document.getElementById('invitation').dataset.castleVisible === 'false'")
    assert not errors, errors
    page.close()
    return {"contact_link_and_castle_launch_geometry": True, "passed": True}


def inspect_extra_sections(browser):
    # A visitor overseas must see the same countdown as a visitor in Argentina.
    counters = []
    for zone in ['America/Argentina/Buenos_Aires', 'Pacific/Auckland']:
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce", timezone_id=zone)
        api_requests = []
        page.on("request", lambda request: api_requests.append(request.url) if "/api/" in request.url else None)
        page.add_init_script("window.testNow = Date.parse('2026-12-25T23:30:00Z'); Date.now = () => window.testNow;")
        page.goto(URL, wait_until="networkidle")
        page.locator("#enter-button").click()
        page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
        counters.append(page.locator('[data-countdown]').all_text_contents())
        assert counters[-1] == ['01', '00', '00', '00']
        page.evaluate('window.testNow += 1000')
        page.wait_for_function("document.querySelector('[data-countdown=seconds]').textContent === '59'")
        assert page.locator('[data-countdown]').all_text_contents() == ['00', '23', '59', '59']
        assert page.locator('#transfer-open').is_visible()
        assert page.locator('#transfer-pending').is_hidden()
        assert not page.locator('#transfer-dialog').evaluate('el => el.open')
        page.locator('#transfer-open').click()
        assert page.locator('#transfer-fields input').count() == 3
        assert page.locator('#transfer-holder').input_value() == 'Mia Aylen Torres'
        assert page.locator('#transfer-bank').input_value() == 'Mercado Pago'
        assert page.locator('#transfer-alias').input_value() == 'mia.aylen.torres67'
        assert page.locator('#transfer-accountNumber').count() == 0
        assert page.locator('#transfer-disclaimer').is_hidden()
        assert page.get_by_role('button', name='Copiar Alias', exact=True).is_enabled()
        if zone == 'America/Argentina/Buenos_Aires':
            page.screenshot(path=str(OUTPUT / 'gifts-translucent-modal.png'))
        page.locator('#transfer-close').click()
        assert 'prueba' not in page.locator('.rsvp-card').inner_text().lower()
        assert 'prueba' not in page.locator('.wishes-section').inner_text().lower()
        assert page.locator('.countdown-section.detail-card, .gifts-section.detail-card, .wishes-section.detail-card').count() == 0

        page.locator('#wish-author').fill('Ana')
        page.locator('#wish-message').fill('Que se cumplan todos tus sueños, Mia. ¡Te queremos!')
        page.locator('#wish-submit').click()
        page.wait_for_function("document.getElementById('wish-status').textContent.includes('Gracias por tu deseo')")
        assert page.locator('#wish-preview-author').inner_text() == 'Ana'
        assert page.locator('#wish-author').input_value() == ''
        assert page.locator('#wish-message').input_value() == ''
        assert page.locator('#wish-length').inner_text() == '0 / 600'
        if zone == 'America/Argentina/Buenos_Aires':
            page.screenshot(path=str(OUTPUT / 'extra-sections-full.png'), full_page=True)
            page.locator('.countdown-section').screenshot(path=str(OUTPUT / 'countdown.png'))
            page.locator('.gifts-section').screenshot(path=str(OUTPUT / 'gifts-collapsed.png'))
            page.locator('.wishes-section').screenshot(path=str(OUTPUT / 'wishes-preview.png'))

        page.locator('#wish-author').fill('Ana')
        page.locator('#wish-message').fill('<img src=x onerror=alert(1)>')
        page.locator('#wish-submit').click()
        page.wait_for_function("document.getElementById('wish-preview-message').textContent.startsWith('<img')")
        assert page.locator('#wish-preview img').count() == 0
        page.locator('#wish-author').fill('Ana')
        page.locator('#wish-message').fill('   ')
        page.locator('#wish-submit').click()
        assert not page.locator('#wish-message').evaluate('input => input.checkValidity()')
        assert page.evaluate("InvitationData.load().then(data => data.wish.message)") == '<img src=x onerror=alert(1)>'
        assert page.locator('#wish-message').get_attribute('maxlength') == '600'

        # Synthetic values only inside the test page, never stored in the mock data.
        page.evaluate("""async () => {
          Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async value => {window.copied = value;}}});
          const data = await InvitationData.load();
          data.sections.bankTransfer = {holder: '<img src=x>', bank: 'Banco de prueba', alias: 'solo.prueba', accountNumber: '0000000000000000000000'};
          renderInvitation(data);
        }""")
        page.locator('#transfer-open').click()
        page.get_by_role('button', name='Copiar Alias', exact=True).click()
        assert page.evaluate('window.copied') == 'solo.prueba'
        assert page.locator('#transfer-status').inner_text() == 'Alias copiado.'
        assert page.locator('#transfer-fields img').count() == 0
        assert page.locator('#transfer-holder').input_value() == '<img src=x>'
        page.evaluate("() => {navigator.clipboard.writeText = async () => {throw Error('denied');};}")
        page.get_by_role('button', name='Copiar CBU / CVU', exact=True).click()
        page.wait_for_function("document.getElementById('transfer-status').textContent.includes('manualmente')")
        assert page.locator('#transfer-accountNumber').evaluate('input => input.selectionEnd - input.selectionStart') == 22
        page.evaluate("""async () => {
          window.testNow = Date.parse('2026-12-26T23:30:01Z');
          const data = await InvitationData.load();
          data.sections.bankTransfer = null;
          renderInvitation(data);
        }""")
        assert page.locator('[data-countdown]').all_text_contents() == ['00', '00', '00', '00']
        assert page.locator('#countdown-heading').inner_text() == '¡Llegó el gran día!'
        assert page.locator('#transfer-open').is_hidden()
        assert page.locator('#transfer-dialog').is_hidden()
        assert page.locator('#transfer-fields input').count() == 0
        assert not api_requests
        page.reload(wait_until='networkidle')
        assert page.evaluate("InvitationData.load().then(data => data.wish)") is None
        page.close()
    assert counters[0] == counters[1]
    return {"countdown_timezone_and_expiry_gifts_copy_and_mock_wishes": True, "passed": True}


def inspect_mock_form(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    api_requests = []
    page.on("request", lambda request: api_requests.append(request.url) if "/api/" in request.url else None)
    page.goto(URL, wait_until="networkidle")
    page.locator("#enter-button").click()
    page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
    assert page.locator("#family-title").inner_text() == "Familia Gomez"
    assert page.locator("#reserved-seats").inner_text() == "3 lugares"
    assert page.locator('.family-welcome .eyebrow').text_content() == 'En mi noche especial…'
    assert page.locator('.family-welcome__copy').inner_text() == 'Reservamos 3 lugares para compartir este momento juntos.'
    assert page.locator(".celebration-card").count() == 1
    assert page.locator(".dress-section.detail-card").count() == 0
    page.screenshot(path=str(OUTPUT / 'sections-full.png'), full_page=True)
    page.get_by_role("radio", name="Sí, vamos a estar").check()
    assert page.locator('#guest-count-choices input').count() == 3
    assert page.locator('#rsvp-form input[type=number]').count() == 0
    assert page.locator('#rsvp-submit').is_disabled()
    page.get_by_role('radio', name='3 personas', exact=True).check()
    page.locator("#rsvp-submit").click()
    page.wait_for_function("document.getElementById('rsvp-status').textContent.includes('Elegiste asistir con 3 personas')")
    assert 'prueba' not in page.locator('.rsvp-card').inner_text().lower()
    page.screenshot(path=str(OUTPUT / 'rsvp-preview.png'))
    assert page.evaluate("InvitationData.load().then(data => data.rsvp.guestCount)") == 3
    assert page.get_by_role('radio', name='4 personas', exact=True).count() == 0
    page.evaluate("""() => {
      document.querySelector('input[name=guestCount]:checked').value = '999';
      document.getElementById('rsvp-form').requestSubmit();
    }""")
    page.wait_for_function("document.getElementById('rsvp-status').textContent.includes('hasta 3')")
    assert page.evaluate("InvitationData.load().then(data => data.rsvp.guestCount)") == 3
    page.get_by_role("radio", name="No podremos ir").check()
    assert page.locator("#guest-count-field").is_hidden()
    page.locator("#rsvp-submit").click()
    page.wait_for_function("InvitationData.load().then(data => data.rsvp.attending === false && data.rsvp.guestCount === 0)")
    page.evaluate("""async () => {
      const data = await InvitationData.load();
      data.invitation.seats = 4;
      data.rsvp = null;
      renderInvitation(data);
    }""")
    page.get_by_role('radio', name='Sí, vamos a estar').check()
    assert page.locator('#guest-count-choices input').evaluate_all('inputs => inputs.map(input => input.value)') == ['1', '2', '3', '4']
    page.get_by_role('radio', name='1 persona', exact=True).focus()
    page.keyboard.press('ArrowRight')
    assert page.get_by_role('radio', name='2 personas', exact=True).is_checked()
    page.evaluate("""async () => {
      const data = await InvitationData.load();
      data.invitation.seats = 1;
      data.rsvp = {attending: true, guestCount: 1};
      renderInvitation(data);
    }""")
    assert page.locator('#reserved-seats').inner_text() == '1 lugar'
    assert page.locator('#guest-count-choices input').count() == 1
    assert page.get_by_role('radio', name='1 persona', exact=True).is_checked()
    page.evaluate("""async () => {
      const data = await InvitationData.load();
      data.event.venueName = '<img src=x onerror=alert(1)>';
      renderInvitation(data);
    }""")
    assert page.locator('[data-event="venueName"]').inner_text() == '<img src=x onerror=alert(1)>'
    assert page.locator('[data-event="venueName"] img').count() == 0
    assert not api_requests, "Preview must not send a real RSVP or require the backend"
    page.close()
    return {"mock_data_form_limits_and_safe_rendering": True, "passed": True}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
        results = [inspect_viewport(browser, width, height) for width, height in [(390, 844), (360, 640), (320, 568), (430, 932), (844, 390), (1440, 900)]]
        results.append(inspect_reduced_motion(browser))
        results.append(inspect_music(browser))
        results.append(inspect_touch_feedback(browser))
        results.append(inspect_gift_modal(browser))
        results.append(inspect_mock_form(browser))
        results.append(inspect_extra_sections(browser))
        results.append(inspect_contact_and_castle(browser))
        print(json.dumps({"checks": results, "screenshots": str(OUTPUT)}, indent=2))
    finally:
        browser.close()
