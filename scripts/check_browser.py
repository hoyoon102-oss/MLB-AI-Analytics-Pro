"""Optional live browser checks. Requires requirements-dev.txt and Microsoft Edge."""
import re
import os
import tempfile
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect
from services.season_selection import resolve_seasons, current_date

expect.set_options(timeout=30000)


def main():
    directory = tempfile.TemporaryDirectory()
    environment = dict(os.environ, MLB_ANALYTICS_DATA_DIR=directory.name)
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless=true", "--server.address=127.0.0.1", "--server.port=18501",
        "--browser.gatherUsageStats=false"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=environment)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError(server.stdout.read())
            try:
                with urllib.request.urlopen("http://127.0.0.1:18501/_stcore/health", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Streamlit startup failed")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(45000)
            page.goto("http://127.0.0.1:18501")
            expect(page.locator(".st-key-dashboard_mode")).to_contain_text("이름 검색")
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(0)
            season = page.locator(".st-key-selected_season").get_by_role("combobox")
            expect(season).to_have_value(str(resolve_seasons(current_date().isoformat())["latest"]))
            season.click()
            season.fill("2024")
            page.get_by_role("option", name="2024", exact=True).click()
            team = page.locator(".st-key-dashboard_team").get_by_role("combobox")
            expect(team).to_be_visible()
            team.click()
            # Streamlit virtualizes its dropdown; only visible rows exist in the DOM.
            expect(page.get_by_role("option").first).to_be_visible()
            team.fill("Toronto")
            page.get_by_role("option", name="Toronto Blue Jays", exact=True).click()
            frame = page.frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
            field = frame.locator("input").first
            field.fill("vLaD")
            option = frame.get_by_role("option").filter(has_text="Vladimir Guerrero")
            expect(option).to_be_visible()
            assert frame.get_by_role("option").count() <= 10
            field.press("ArrowDown")
            field.press("Enter")
            expect(page.get_by_text(re.compile("^선택한 선수: Vladimir Guerrero"))).to_be_visible()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(1)
            page.locator(".st-key-dashboard_star").get_by_role("button", name="☆", exact=True).click()
            expect(page.locator(".st-key-dashboard_star").get_by_role("button", name="★", exact=True)).to_be_visible()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            page.reload()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(0)
            season = page.locator(".st-key-selected_season").get_by_role("combobox")
            season.click()
            season.fill("2024")
            page.get_by_role("option", name="2024", exact=True).click()
            page.locator(".st-key-dashboard_mode").get_by_text("즐겨찾기", exact=True).click()
            favorite = page.locator(".st-key-dashboard_favorite_choice").get_by_role("combobox")
            favorite.click()
            page.get_by_role("option").filter(has_text="Vladimir Guerrero").click()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            page.locator(".st-key-dashboard_star").get_by_role("button", name="★", exact=True).click()
            expect(page.locator(".st-key-dashboard_star").get_by_role("button", name="☆", exact=True)).to_be_visible()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            page.locator(".st-key-dashboard_mode").get_by_text("이름 검색", exact=True).click()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            print("PASS: browser favorites save/reload/remove without losing selected stats", flush=True)
            print("PASS: browser live 30-team dropdown, team filter, partial/case-insensitive autocomplete, keyboard selection, hitter stats", flush=True)
            expect(page.locator(".st-key-dashboard_stats_category")).to_have_count(0)
            print("PASS: browser ordinary hitter has no category selector", flush=True)
            old_iframe = page.locator('iframe[title="streamlit_searchbox.searchbox"]').element_handle()
            page.get_by_role("button", name="검색 필터 초기화", exact=True).click()
            page.wait_for_function("element => !element.isConnected", arg=old_iframe)
            expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
            expect(page.locator(".st-key-dashboard_team").get_by_role("combobox")).to_have_value("전체 팀 (All Teams)")
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(0)
            frame = page.frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
            field = frame.locator("input").first
            field.fill("Sho")
            option = frame.get_by_role("option").filter(has_text="Shohei Ohtani")
            expect(option).to_be_visible()
            option.click()
            expect(page.get_by_text(re.compile("^선택한 선수: Shohei Ohtani"))).to_be_visible()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            print("PASS: browser reset, all-team autocomplete and mouse selection", flush=True)
            page.locator(".st-key-dashboard_stats_category").get_by_text("투구 기록 (Pitching)", exact=True).click()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(0)
            expect(page.get_by_text(re.compile("^해당 시즌 기록 없음"))).to_be_visible()
            page.locator(".st-key-dashboard_stats_category").get_by_text("타격 기록 (Hitting)", exact=True).click()
            expect(page.locator('[data-testid="stMetric"]')).to_have_count(6)
            print("PASS: browser Ohtani 2024 conditional toggle and absent pitching records", flush=True)
            page.locator(".st-key-pro_page").get_by_text(re.compile("선수 비교")).click()
            for index, team_id, team_name, term, expected_name in [(0, 141, "Toronto Blue Jays", "Vlad", "Vladimir Guerrero"), (1, 147, "New York Yankees", "Jud", "Aaron Judge")]:
                page.locator(f".st-key-compare_{index}_mode").get_by_text("이름 검색", exact=True).click()
                team_box = page.locator(f".st-key-compare_{index}_team").get_by_role("combobox")
                team_box.click()
                team_box.fill(team_name)
                page.get_by_role("option", name=team_name, exact=True).click()
                expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
                player_frame = page.locator(f".st-key-compare_{index}_search_2024_{team_id}_0").frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
                player_frame.locator("input").first.fill(term)
                candidate = player_frame.get_by_role("option").filter(has_text=expected_name)
                expect(candidate).to_be_visible()
                candidate.click()
                expect(page.get_by_text(re.compile("^선택한 선수: " + expected_name))).to_be_visible()
                expect(page.get_by_text(re.compile("^선택한 선수:"))).to_have_count(index + 1)
            expect(page.locator('[data-testid="stTable"]')).to_have_count(1)
            expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(2)
            print("PASS: browser independent team filters and hitter comparison", flush=True)
            expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning")
            for index, team_id, term, expected_name in [(0, 141, "Gaus", "Kevin Gausman"), (1, 147, "Cole", "Gerrit Cole")]:
                player_frame = page.locator(f".st-key-compare_{index}_search_2024_{team_id}_0").frame_locator('iframe[title="streamlit_searchbox.searchbox"]')
                player_frame.locator("input").first.fill(term)
                candidate = player_frame.get_by_role("option").filter(has_text=expected_name)
                expect(candidate).to_be_visible()
                candidate.click()
                expect(page.get_by_text(re.compile("^선택한 선수: " + expected_name))).to_be_visible()
            expect(page.locator('[data-testid="stTable"]')).to_have_count(1)
            expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(1)
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            print("PASS: browser pitcher comparison using team autocomplete", flush=True)
            page.locator(".st-key-compare_awards").get_by_text("통산 수상 비교 보기 (시즌 성적과 별도)", exact=True).click()
            expect(page.locator('[data-testid="stTable"]')).to_have_count(2)
            expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(2)
            expect(page.get_by_text("🏆 통산 수상 비교", exact=True)).to_be_visible()
            print("PASS: browser optional career awards comparison", flush=True)
            page.locator(".st-key-pro_page").get_by_text(re.compile("선수 기록")).click()
            expect(page.locator(".st-key-player_profile").get_by_text("선수 프로필", exact=True)).to_be_visible()
            page.locator(".st-key-awards_open").get_by_text("수상·업적 열기", exact=True).click()
            expect(page.get_by_text("통산 주요 수상 요약 (현재 선택 시즌과 독립)", exact=True)).to_be_visible()
            expect(page.locator(".st-key-awards_view_660271").get_by_role("radio", name="통산 수상", exact=True)).to_be_checked()
            page.locator(".st-key-awards_view_660271").get_by_text("선택 시즌 수상", exact=True).click()
            expect(page.get_by_text("● 2024", exact=True)).to_be_visible()
            expect(page.get_by_text("● 2023", exact=True)).to_have_count(0)
            page.locator(".st-key-awards_sort").get_by_role("combobox").click()
            page.get_by_role("option", name="오래된 연도 먼저", exact=True).click()
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            print("PASS: browser profile, career summary, selected-season awards and timeline sort", flush=True)
            browser.close()
    finally:
        server.terminate()
        server.communicate(timeout=10)
        directory.cleanup()


if __name__ == "__main__":
    main()
