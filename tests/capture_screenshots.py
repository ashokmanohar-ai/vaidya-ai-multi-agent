"""Capture deterministic offline UI previews. Not proof of running Flask/graph HTTP flow."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
CSS=(ROOT/'static'/'style.css').read_text(encoding='utf8')
OUT=ROOT/'screenshots';OUT.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1500,'height':950},device_scale_factor=1)
    for page_name in ['login','dashboard','new_report','review','admin']:
        html=(ROOT/'ui_previews'/(page_name+'.html')).read_text(encoding='utf8')
        html=html.replace('<link rel="stylesheet" href="/static/style.css">',f'<style>{CSS}</style>')
        page.set_content(html,wait_until='domcontentloaded')
        page.screenshot(path=str(OUT/(page_name+'.png')),full_page=True)
        assert page.locator('h1').count()>=1,page_name
        if page_name=='review':
            assert page.get_by_text('LangGraph execution trace').count()==1
        if page_name=='admin':
            assert page.locator('h2').filter(has_text='LangGraph multi-agent execution').count()>=1
        print('visual render:',page_name)
    browser.close()
