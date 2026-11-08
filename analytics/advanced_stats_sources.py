"""Reviewed constants snapshot; no automated third-party scraping or guessed IDs."""
CONSTANTS_SOURCE = 'https://www.fangraphs.com/tools/guts?type=cn'
REVIEWED_AT = '2026-11-04'
# Published precision, completed seasons only. BB, HBP, 1B, 2B, 3B, HR, cFIP.
CONSTANTS = {
    2020: (.699, .728, .883, 1.238, 1.558, 1.979, 3.191),
    2021: (.692, .722, .879, 1.242, 1.568, 2.007, 3.170),
    2022: (.689, .720, .884, 1.261, 1.601, 2.072, 3.112),
    2023: (.696, .726, .883, 1.244, 1.569, 2.004, 3.255),
    2024: (.689, .720, .882, 1.254, 1.590, 2.050, 3.166),
    2025: (.691, .722, .882, 1.252, 1.584, 2.037, 3.135),
}


def seasonal_constants(season):
    return CONSTANTS.get(int(season))
