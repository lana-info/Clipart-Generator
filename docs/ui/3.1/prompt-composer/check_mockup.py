from pathlib import Path
import json
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1120,'height':780},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((root/'mockup.html').as_uri())
    states=page.locator('#screen option').evaluate_all('(els)=>els.map(e=>e.value)')
    report=[]
    for state in states:
        page.select_option('#screen',state)
        page.screenshot(path=str(root/(state+'-1120x780.png')))
        dims=page.evaluate('({body:document.body.scrollWidth,width:innerWidth,height:document.body.scrollHeight})')
        assert dims['body']<=1120,(state,dims)
        assert dims['height']==780,(state,dims)
        report.append({'state':state,'dimensions':dims})
    page.select_option('#screen','library')
    page.fill('#search','чашка')
    assert page.locator('.saved:not(.hidden)').count()==1
    page.fill('#search','')
    page.select_option('#filter','reels')
    assert page.locator('.saved:not(.hidden)').count()==3
    page.click('#only-favorites')
    assert page.locator('.saved:not(.hidden)').count()==1
    page.select_option('#screen','scene')
    page.select_option('#screen','results')
    assert page.locator('[data-variant]').count()==7
    first=page.locator('#prompt-text').inner_text()
    page.click('[data-variant="2"]')
    assert page.locator('#prompt-text').inner_text()!=first
    page.click('[data-lang="ru"]')
    assert 'Чашка' in page.locator('#prompt-text').inner_text()
    page.select_option('#screen','subject')
    page.locator('[data-lock]').first.click()
    assert page.locator('[data-lock]').first.inner_text()=='Закрепить'
    page.select_option('#screen','save')
    page.get_by_role('button',name='Заменить исходный…').click()
    assert page.get_by_role('dialog',name='Заменить «Чашка у окна»?').is_visible()
    page.get_by_role('button',name='Подтвердить замену').click()
    assert page.locator('#search').is_visible()
    page.select_option('#screen','partial')
    assert page.locator('[data-variant]').count()==3
    page.get_by_role('button',name='Принять вариант').click()
    assert page.locator('[data-variant]').count()==7
    page.goto((root/'mockup.html').as_uri()+'?state=reels')
    page.get_by_role('button',name='Получить 7 вариантов').click()
    assert 'One continuous vertical' in page.locator('#prompt-text').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    page.select_option('#screen','templates')
    page.screenshot(path=str(root/'narrow-390.png'),full_page=True)
    assert page.evaluate('document.body.scrollWidth')<=390
    assert not errors,errors
    (root/'mockup-checks.json').write_text(json.dumps({'viewport':'1120x780','states':report,'interaction_checks':['library search','type filter','favorites','seven variants','variant detail','RU toggle','lock toggle','replace confirmation','partial AI result','accept AI','Reels direct open'],'page_errors':errors,'narrow_width':390,'kind':'HTML mockup only; no application/runtime/API checks'},ensure_ascii=False,indent=2)+'\n')
    print(f'PASS: {len(states)} states at 1120x780, eleven interaction checks, no JS errors; narrow layout 390px.')
    browser.close()
