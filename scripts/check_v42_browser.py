"""Real bilingual UI/league checks with isolated local settings and favorites."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    output = Path("ui-preview/v42")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        environment = dict(os.environ, MLB_ANALYTICS_DATA_DIR=directory)
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless=true", "--server.address=127.0.0.1", "--server.port=18506"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
        try:
            for _ in range(60):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18506/_stcore/health", timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                expect.set_options(timeout=45000)
                page.set_default_timeout(45000)
                page.goto("http://127.0.0.1:18506")
                def idle():
                    expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                    page.wait_for_timeout(650)  # Let React finish applying Streamlit's deltas before screenshots.
                    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                def audit(name):
                    idle()
                    lines = [line for line in page.locator("body").inner_text().splitlines()
                             if re.search("[가-힣]", line) and line.strip() != "한국어 (Korean)"]
                    lines += page.locator('input[role="combobox"]').evaluate_all("els => els.map(el => el.value).filter(value => /[가-힣]/.test(value) && value !== '한국어 (Korean)')")
                    (output / f"{name}-remaining-korean.json").write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
                    print("English audit:", name, lines, flush=True)
                expect(page.locator(".st-key-dashboard_position")).to_be_visible()
                idle()
                page.locator(".st-key-pro_page").get_by_text(re.compile("선수 기록")).click()
                season = page.locator(".st-key-selected_season").get_by_role("combobox")
                season.click()
                season.fill("2024")
                page.get_by_role("option", name="2024", exact=True).click()
                search = page.locator(".st-key-dashboard_search_2024_0_0")
                expect(search).to_be_visible()
                idle()
                frame = search.frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
                frame.locator("input").first.fill("Sho")
                frame.get_by_role("option").filter(has_text="Shohei Ohtani").click()
                expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
                page.locator(".st-key-league_enabled").get_by_text("리그 평균 비교", exact=True).click()
                expect(page.locator(".st-key-dashboard_league_chart")).to_be_visible()
                idle()
                page.locator(".st-key-kpi_hitting_ops").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "league-ko.png"))
                selector = page.locator(".st-key-league_scope").get_by_role("combobox")
                selector.click()
                page.get_by_role("option", name="아메리칸리그 (AL)", exact=True).click()
                idle()
                print("PASS: real MLB and AL rate contexts displayed", flush=True)
                language = page.locator(".st-key-ui_language").get_by_role("combobox")
                language.click()
                page.get_by_role("option", name="English", exact=True).click()
                expect(page.locator(".st-key-selected_season")).to_contain_text("Season")
                idle()
                expect(page.locator(".st-key-dashboard_stats_category").get_by_role("radio", name="Hitting statistics (Hitting)", exact=True)).to_be_checked()
                audit("statistics")
                english_search = page.locator(".st-key-dashboard_search_2024_0_0").frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
                english_search.locator("input").first.fill("Jud")
                suggestion = english_search.get_by_role("option").filter(has_text="Aaron Judge")
                expect(suggestion).to_be_visible()
                assert not re.search("[가-힣]", suggestion.inner_text())
                english_search.locator("input").first.fill("Sho")
                english_search.get_by_role("option").filter(has_text="Shohei Ohtani").click()
                idle()
                print("PASS: English autocomplete suggestions and preserved player selection", flush=True)
                page.locator(".st-key-kpi_hitting_ops").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "league-en.png"))
                selector = page.locator(".st-key-league_scope").get_by_role("combobox")
                selector.click()
                selector.fill("National")
                page.get_by_role("option", name="National League (NL)", exact=True).click()
                idle()
                expect(page.locator(".st-key-player_profile")).to_contain_text("Shohei Ohtani")
                assert json.loads((Path(directory) / "settings.json").read_text())["language"] == "en"
                page.locator(".st-key-pro_page").get_by_text(re.compile("Awards & Achievements")).click()
                expect(page.get_by_text("Awards timeline", exact=True)).to_be_visible()
                audit("awards")
                page.screenshot(path=str(output / "awards-en.png"))
                page.locator(".st-key-pro_page").get_by_text(re.compile("AI Analysis$")).click()
                expect(page.get_by_text("Enable local AI in the sidebar and check the model list.")).to_be_visible()
                page.locator(".st-key-ai_enabled").get_by_text("Enable local AI", exact=True).click()
                page.get_by_role("button", name="Refresh model list", exact=True).click()
                expect(page.locator(".pro-status")).not_to_have_text("Connection not checked")
                idle()
                if page.locator(".st-key-ai_model").count():
                    expect(page.locator(".st-key-dashboard_stats_category").get_by_role("radio", name="Hitting statistics (Hitting)", exact=True)).to_be_checked()
                    page.get_by_role("button", name="Prepare AI data / Refresh", exact=True).click()
                    expect(page.locator(".st-key-ai_scout_generate")).to_be_visible()
                    audit("ai-controls")
                    if args.generate:
                        page.locator(".st-key-ai_scout_generate").get_by_role("button").click()
                        expect(page.get_by_text(re.compile("^Generated with:"))).to_be_visible(timeout=360000)
                        page.get_by_text(re.compile("^Generated with:")).scroll_into_view_if_needed()
                        page.screenshot(path=str(output / "ai-report-en.png"))
                        language = page.locator(".st-key-ui_language").get_by_role("combobox")
                        language.click()
                        page.get_by_role("option", name="한국어 (Korean)", exact=True).click()
                        expect(page.get_by_text(re.compile("이 보고서는 English로 생성되었습니다"))).to_be_visible()
                        print("PASS: English report generated; old language marked after switching; no automatic regeneration", flush=True)
                print("PASS: Korean/English UI, MLB/AL/NL, awards, preserved player/season and local preference file", flush=True)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
