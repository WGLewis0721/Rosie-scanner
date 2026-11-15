"""Offline tests for the added vertical; no live feeds, keys or trading."""
from datetime import timedelta

from rosie_advisor import (prepare_history, fit_calibrator, kalshi_match,
                           evaluate, read_books, _odds)
from market_scan import Market
from nba_odds import Game
from market_scan import now_utc


def game():
    start=(now_utc()+timedelta(hours=4)).isoformat()
    return Game("1",start,"Cleveland Cavaliers","Dallas Mavericks",
                120,-142,.433,.567,"DraftKings","https://espn.com/game")


def test_calibration_fails_closed_without_history():
    obj=fit_calibrator([])
    assert obj["mode"]=="bookmaker_only"
    assert not obj["validated"]


def test_evaluate_never_issues_buy_without_history_or_second_book():
    g=game()
    out=evaluate([g],[],[],{},1000)
    assert len(out["recommendations"])==2
    assert all(x["status"]=="PASS" and x["conditional_stake_cap"]==0 for x in out["recommendations"])


def test_history_rejects_duplicate_and_future():
    past=(now_utc()-timedelta(days=5)).date().isoformat()
    row={"game_id":"1","date":past,"home":"Cleveland Cavaliers",
         "away":"Dallas Mavericks","home_ml":"120","away_ml":"-142",
         "winner":"Dallas Mavericks","source_url":"https://www.espn.com"}
    data=prepare_history([row,row,dict(row,game_id="2",date="2099-01-01")])
    assert len(data)==1 and data[0]["y"]==0


def test_espn_odds_parser_prefers_close():
    raw={"moneyline":{"home":{"close":{"odds":"-150"},"current":{"odds":"+200"}},
                     "away":{"close":{"odds":"+130"}}}}
    assert _odds(raw)==(-150,130)


def test_kalshi_match_needs_exact_event_date_and_matchup():
    g=game()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    date=datetime.fromisoformat(g.start).astimezone(ZoneInfo("America/New_York")).strftime("%y%b%d").upper()
    m=Market("Kalshi",f"KXNBAGAME-{date}DALCLE-CLE","Cleveland wins",
             "Cleveland","No",g.start,"https://kalshi.com")
    assert kalshi_match(m,g)=={"Cleveland Cavaliers":"A","Dallas Mavericks":"B"}
    bad=Market("Kalshi",f"KXNBAGAME-{date}DALBOS-CLE","Cleveland wins",
               "Cleveland","No",g.start,"https://kalshi.com")
    assert not kalshi_match(bad,g)
