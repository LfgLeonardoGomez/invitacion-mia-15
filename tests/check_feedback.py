"""Submission feedback browser checks, mocked saves only; no build or live guest data."""

import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(tempfile.gettempdir()) / 'mia-feedback-review'
OUTPUT.mkdir(exist_ok=True)


def check(browser, width, height, reduced):
    page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce' if reduced else 'no-preference')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('https://fonts.googleapis.com/**', lambda route: route.abort())
    page.route('https://fonts.gstatic.com/**', lambda route: route.abort())
    page.goto((ROOT / 'index.html').as_uri(), wait_until='networkidle')
    page.locator('#enter-button').click()
    page.wait_for_function("document.getElementById('invitation').dataset.contentState === 'ready'")
    page.evaluate("""() => {
      const original = window.InvitationData;
      window.InvitationData = Object.freeze({...original, mode: 'api',
        saveWish: answer => new Promise((resolve, reject) => {
          window.finishWish = () => resolve({id:'test-wish', ...answer});
          window.rejectWish = () => reject(Error('No pudimos guardar el deseo. Intentá nuevamente.'));
        }),
        saveRsvp: async answer => ({...answer,updatedAt:'2026-10-27T00:00:00Z'}),
      });
    }""")
    page.locator('#wish-author').fill('Ana')
    page.locator('#wish-message').fill('Una noche hermosa para vos')
    page.locator('#wish-submit').click()
    assert page.locator('#wish-submit').is_disabled()
    assert page.locator('#wish-author').input_value() == 'Ana'
    assert page.locator('#form-feedback').is_hidden(), 'Must not celebrate before save resolves'
    page.evaluate('finishWish()')
    page.wait_for_function("document.getElementById('wish-message').value === ''")
    assert page.locator('#wish-author').input_value() == ''
    assert page.locator('#wish-length').inner_text() == '0 / 600'
    assert page.locator('#wish-preview-message').inner_text() == 'Una noche hermosa para vos'
    assert page.locator('#wish-preview-author').inner_text() == 'Ana'
    assert page.locator('#wish-status').get_attribute('data-result') == 'success'
    assert page.locator('#wish-status').get_attribute('aria-live') == 'off'
    assert page.locator('#form-feedback-message').inner_text() == 'Mia ya recibió tu mensaje 💕'
    assert page.locator('#feedback-announcement').get_attribute('aria-live') == 'polite'
    page.wait_for_function("document.getElementById('feedback-announcement').textContent.includes('Mia')")
    assert page.locator('#form-feedback').evaluate("el => getComputedStyle(el).pointerEvents") == 'none'
    samples = page.locator('.form-feedback__flight').evaluate("""el => {
      const animation = el.getAnimations()[0]; animation.pause();
      const sample = time => { animation.currentTime=time; return getComputedStyle(el).transform; };
      return [sample(0),sample(1100)];
    }""")
    assert (samples[0] == samples[1]) == reduced, (samples, reduced)
    timing = page.locator('.form-feedback__flight').evaluate("""el => {
      const animation = el.getAnimations()[0], effect = animation.effect;
      const frames = effect.getKeyframes(), total = effect.getTiming().duration;
      const fade = frames[1].offset * total;
      const opacity = time => { animation.currentTime = time; return Number(getComputedStyle(el).opacity); };
      const entrance = [.12,.25,.5,.75].map(phase => opacity(fade * phase));
      const exit = [.12,.25,.5,.75].map(phase => opacity(total - fade + fade * phase));
      animation.currentTime = 1100;
      return {easing: effect.getTiming().easing, fade, exitDuration: total * (1-frames[2].offset), entrance, exit};
    }""")
    assert timing['easing'] == 'linear', 'A global easing must not squeeze entrance time and stretch the exit'
    assert abs(timing['fade'] - (360 if reduced else 1000)) < 1
    assert abs(timing['fade'] - timing['exitDuration']) < 1
    assert timing['entrance'][0] < .1, 'Opacity should emerge gradually, not pop in'
    assert .4 < timing['entrance'][2] < .6
    assert all(abs(a + b - 1) < .02 for a, b in zip(timing['entrance'], timing['exit']))
    bounds = page.locator('#form-feedback').bounding_box()
    assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= width
    assert 0 <= bounds['y'] and bounds['y'] + bounds['height'] <= height
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(OUTPUT / f'{width}x{height}-wish.png'))
    page.evaluate('InvitationFeedback.clear()')

    page.locator('#wish-author').fill('Beto')
    page.locator('#wish-message').fill('No perder este texto')
    page.locator('#wish-submit').click()
    page.evaluate('rejectWish()')
    page.wait_for_function("document.getElementById('wish-status').dataset.result === 'error'")
    assert page.locator('#wish-author').input_value() == 'Beto'
    assert page.locator('#wish-message').input_value() == 'No perder este texto'
    assert not page.locator('#wish-submit').is_disabled()
    assert page.locator('#form-feedback').get_attribute('data-kind') == 'error'
    assert page.locator('.form-feedback__lantern').is_hidden()
    assert page.locator('#wish-preview-message').inner_text() == 'Una noche hermosa para vos'
    page.evaluate('InvitationFeedback.clear()')

    page.get_by_role('radio', name='Sí, vamos a estar').check()
    page.get_by_role('radio', name='2 personas', exact=True).check()
    page.locator('#rsvp-submit').click()
    page.wait_for_function("document.getElementById('form-feedback-message').textContent.includes('te esperamos')")
    assert page.locator('#rsvp-status').get_attribute('data-result') == 'success'
    assert page.locator('#rsvp-status').inner_text().endswith('Tu respuesta quedó guardada. ¡Gracias!')
    assert page.locator('.form-feedback__lantern').is_visible()
    page.get_by_role('radio', name='No podremos ir').check()
    page.locator('#rsvp-submit').click()
    page.wait_for_function("document.getElementById('form-feedback-message').textContent.includes('avisarnos')")
    assert 'te esperamos' not in page.locator('#form-feedback-message').inner_text()
    assert page.locator('#form-feedback').count() == 1
    assert page.locator('.form-feedback__flight').evaluate('el => el.getAnimations().length') == 1
    page.evaluate("""() => document.querySelector('.form-feedback__flight').getAnimations().forEach(a => a.finish())""")
    page.wait_for_function("document.getElementById('form-feedback').hidden", timeout=6000)
    assert page.locator('#rsvp-status').inner_text(), 'Inline result persists after the lamp leaves'
    assert not errors, errors
    page.close()
    return {'viewport': [width, height], 'reduced_motion': reduced, 'save_reset_and_errors': True, 'feedback': True}


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        results = [check(browser, 390, 844, False), check(browser, 320, 568, True)]
        print(json.dumps({'checks': results, 'screenshots': str(OUTPUT)}))
    finally:
        browser.close()
