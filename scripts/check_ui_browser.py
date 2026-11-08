"""Real Edge screenshots and layout checks; isolated favorites, no AI generation."""
import argparse
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
    parser.add_argument("--generate", action="store_true", help="설치된 모델로 실제 AI 보고서도 생성")
    args = parser.parse_args()
    output = Path("ui-preview")
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        environment = dict(os.environ, MLB_ANALYTICS_DATA_DIR=directory)
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless=true", "--server.address=127.0.0.1", "--server.port=18505"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
        try:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("Streamlit exited before startup")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18505/_stcore/health", timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError("Startup timed out")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(45000)
                expect.set_options(timeout=45000)
                page.goto("http://127.0.0.1:18505")
                expect(page.locator(".st-key-dashboard_team")).to_be_visible()
                expect(page.locator(".st-key-dashboard_position")).to_be_visible()
                expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                assert page.locator(".pro-status").inner_text() == "AI 꺼짐"
                page.screenshot(path=str(output / "home-1440.png"), full_page=True)
                # Real player data, selected through the existing season-aware autocomplete.
                season = page.locator(".st-key-selected_season").get_by_role("combobox")
                season.click()
                season.fill("2024")
                page.get_by_role("option", name="2024", exact=True).click()
                expect(page.locator(".st-key-dashboard_search_2024_0_0")).to_be_visible()
                expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                frame = page.locator(".st-key-dashboard_search_2024_0_0").frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
                frame.locator("input").first.fill("Sho")
                frame.get_by_role("option").filter(has_text="Shohei Ohtani").click()
                expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
                page.locator(".st-key-pro_page").get_by_text(re.compile("선수 기록")).click()
                expect(page.locator(".st-key-player_profile")).to_be_visible()
                expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                for width, height in [(1440, 1000), (1366, 900), (768, 1024), (390, 844)]:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(450)
                    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
                    assert not overflow, (width, "page horizontal overflow")
                    page.screenshot(path=str(output / f"player-{width}.png"), full_page=True)
                    page.locator(".st-key-player_profile").scroll_into_view_if_needed()
                    page.screenshot(path=str(output / f"profile-{width}.png"))
                    page.locator(".st-key-kpi_hitting_avg").scroll_into_view_if_needed()
                    page.screenshot(path=str(output / f"stats-{width}.png"))
                    print("PASS: real player UI, viewport", width, "no page overflow", flush=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.locator(".st-key-pro_page").get_by_text(re.compile("수상 경력")).click()
                expect(page.get_by_text("연도별 수상 타임라인", exact=True)).to_be_visible()
                page.screenshot(path=str(output / "awards-1440.png"), full_page=True)
                page.locator(".st-key-pro_page").get_by_text(re.compile("AI 분석$")).click()
                expect(page.get_by_text("왼쪽의 로컬 AI 사용을 켜고 모델 목록을 확인하세요.")).to_be_visible()
                page.locator(".st-key-ai_enabled").get_by_text("로컬 AI 사용", exact=True).click()
                page.get_by_role("button", name="모델 목록 새로고침", exact=True).click()
                expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                page.screenshot(path=str(output / "ai-1440.png"), full_page=True)
                expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                print("PASS: awards navigation, selected player retained, real Ollama status check", flush=True)
                if args.generate:
                    if page.locator(".st-key-ai_model").count() == 0:
                        print("SKIP: real AI report; no local model available", flush=True)
                    else:
                        page.get_by_role("button", name="AI 분석 자료 준비 / 새로고침", exact=True).click()
                        expect(page.locator(".st-key-ai_scout_generate")).to_be_visible()
                        page.locator(".st-key-ai_scout_generate").get_by_role("button").click()
                        expect(page.get_by_text(re.compile("^생성 모델:"))).to_be_visible(timeout=360000)
                        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                        page.get_by_text(re.compile("^생성 모델:")).scroll_into_view_if_needed()
                        page.screenshot(path=str(output / "ai-report-1440.png"))
                        print("PASS: real Ollama scouting report generated through the UI", flush=True)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
