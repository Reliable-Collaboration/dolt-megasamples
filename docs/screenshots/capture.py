"""Take the README's screenshots from the running stack, so they can be retaken after any change.

  make screenshots

runs this inside the Playwright image (browsers included) on the host's network, because the
Workbench's page calls its API at the address the host publishes (127.0.0.1:9002):

  docker run --rm --network host -v "$PWD/docs/screenshots:/out" \\
      mcr.microsoft.com/playwright/python:v1.49.1-noble sh -c \\
      "pip install -q --break-system-packages playwright==1.49.1 && python3 /out/capture.py"

Three pictures: the console index tall enough to show the consoles, the connection help and the
first databases; Dolt Workbench on the Dolt read-only connection, the part of the stack that shows
what makes a Dolt engine a Dolt engine; CloudBeaver with the same connection opened down to
sakila's `film` table on its Data tab. The consoles are driven through their own markup, which is
why the selectors are specific to the pinned image versions. Every screenshot is 1440 px wide at
1x; nothing in them is staged.
"""
import os, time

from playwright.sync_api import sync_playwright

OUT = "/out"
HOST = os.environ.get("STACK_HOST", "127.0.0.1")
PORTS = {"console": 8090, "cloudbeaver": 8094, "workbench": 8095}

with sync_playwright() as p:
    browser = p.chromium.launch()

    # the console index
    ctx = browser.new_context(viewport={"width": 1440, "height": 1500}, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(f"http://{HOST}:{PORTS['console']}/", wait_until="networkidle")
    time.sleep(1)
    page.screenshot(path=f"{OUT}/landing.png")
    ctx.close()

    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

    # Dolt Workbench: the saved read-only connection to Dolt, then the database it opens
    page = ctx.new_page()
    page.goto(f"http://{HOST}:{PORTS['workbench']}/", wait_until="networkidle")
    time.sleep(8)
    page.get_by_text("dolt-megasamples (read-only)", exact=True).first.click()
    time.sleep(10)
    print("workbench:", page.url)
    page.screenshot(path=f"{OUT}/workbench.png")

    # CloudBeaver: Dolt (read-only) > Databases > sakila > Tables > film, Data tab
    page = ctx.new_page()
    page.goto(f"http://{HOST}:{PORTS['cloudbeaver']}/", wait_until="networkidle")
    time.sleep(5)

    def expand(text, wait=6):
        node = page.locator('[data-tree-node-control="true"]').filter(has=page.get_by_text(text, exact=True)).first
        node.locator('[title="Expand"]').first.click()
        time.sleep(wait)

    expand("dolt-megasamples (read-only)", 8)
    expand("Databases")
    expand("sakila")
    expand("Tables")
    page.locator('[data-tree-node-control="true"]').filter(has=page.get_by_text("film", exact=True)).first.dblclick()
    time.sleep(10)
    tab = page.get_by_role("tab", name="Data").first
    if tab.count():
        tab.click()
        time.sleep(5)
    page.screenshot(path=f"{OUT}/cloudbeaver.png")
    browser.close()
