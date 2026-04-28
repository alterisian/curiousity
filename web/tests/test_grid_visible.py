import os
import time
import json
from playwright.sync_api import sync_playwright


def test_grid_shows_nodes():
    url = os.environ.get('CURIO_UI', 'http://localhost:8000/index.html')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        # wait for activity to populate
        page.wait_for_timeout(1500)
        # check that at least one node element exists
        nodes = page.query_selector_all('.node')
        assert len(nodes) > 0, 'No .node elements found on the page'
        # ensure nodes are positioned within their quadrants (have left/top set)
        for n in nodes[:5]:
            style = n.evaluate('(el) => { return {left: el.style.left, top: el.style.top, width: el.offsetWidth, height: el.offsetHeight} }')
            assert style['left'] != '' and style['top'] != '', f'Node has no position: {style}'
        browser.close()
