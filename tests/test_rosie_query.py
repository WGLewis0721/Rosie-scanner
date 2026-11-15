"""No-network coverage of Rosie's single-game Q&A API."""
from datetime import date

import pytest
from rosie_query import parse_question, ask_game


def fake_report(day, history, books, bankroll):
    return {
        "generated_at":"2026-11-14T18:00:00+00:00",
        "model":{"mode":"bookmaker_only","validated":False},
        "feed_errors":[],
        "recommendations":[
            {"game":"Dallas Mavericks @ Cleveland Cavaliers",
             "team":"Cleveland Cavaliers","status":"PASS",
             "estimated_probability":.44,"bookmaker_count":1,
             "best_verified_contract":None,"conditional_stake_cap":0.,
             "reasons":["Only one source"],
             "platform_quotes":{
                 "Kalshi":{"best":None,"max_buy_price_for_5pt_edge":.36},
                 "Polymarket":{"best":None,"max_buy_price_for_5pt_edge":.36}}},
            {"game":"Dallas Mavericks @ Cleveland Cavaliers",
             "team":"Dallas Mavericks","status":"PASS",
             "estimated_probability":.56,"bookmaker_count":1,
             "best_verified_contract":None,"conditional_stake_cap":0.,
             "reasons":["Only one source"],
             "platform_quotes":{
                 "Kalshi":{"best":None,"max_buy_price_for_5pt_edge":.48},
                 "Polymarket":{"best":None,"max_buy_price_for_5pt_edge":.48}}},
            {"game":"Brooklyn Nets @ Memphis Grizzlies",
             "team":"Memphis Grizzlies","status":"PASS",
             "estimated_probability":.58,"bookmaker_count":1,
             "best_verified_contract":None,"conditional_stake_cap":0.,
             "reasons":["Only one source"],"platform_quotes":{}}
        ]
    }


def test_natural_language_aliases_and_dates():
    day,teams=parse_question("Cavs vs Mavs tonight",today=date(2026,11,14))
    assert day=="20261114"
    assert set(teams)=={"Cleveland Cavaliers","Dallas Mavericks"}
    day,teams=parse_question("Dallas tomorrow",today=date(2026,11,14))
    assert day=="20261115" and teams==["Dallas Mavericks"]
    day,teams=parse_question("Mavericks 2026-11-16",today=date(2026,11,14))
    assert day=="20261116"
    day,teams=parse_question("NBA tonight",today=date(2026,11,14))
    assert day=="20261114" and teams==[]


def test_unknown_input_does_not_scan():
    with pytest.raises(ValueError):
        parse_question("What is a goblin?")


def test_asks_game_not_entire_slate_and_passes_when_no_quotes():
    result=ask_game("Cavs vs Mavs tonight",bankroll=500,
                    report_provider=fake_report)
    assert result["status"]=="PASS"
    assert result["stake_usd"]==0
    assert len(result["recommendations"])==2
    assert len(result["platform_comparisons"])==4
    assert all(q["ask"] is None for q in result["platform_comparisons"])
    assert all(not q["verified"] for q in result["platform_comparisons"])
    assert all(q["max_buy_price_for_5pt_edge"] is not None for q in result["platform_comparisons"])


def test_missing_requested_match_is_explicit_pass():
    result=ask_game("Cavs vs Celtics tonight",report_provider=fake_report)
    assert result["status"]=="PASS" and not result["recommendations"]
    assert result["available_games"]


def test_review_requires_verified_venue_and_retains_other_venue_unknown():
    def producer(*args):
        obj=fake_report(*args)
        row=obj["recommendations"][1]
        row["status"]="REVIEW"
        row["conditional_stake_cap"]=5.0
        quote={"platform":"Kalshi","market_id":"KXNBAGAME-TEST","side":"A",
               "ask":.43,"edge":.09,"url":"https://kalshi.com/markets"}
        row["best_verified_contract"]=quote
        row["platform_quotes"]["Kalshi"]["best"]=quote
        obj["model"]["validated"]=True
        return obj
    result=ask_game("Mavs tonight",bankroll=500,report_provider=producer)
    assert result["status"]=="REVIEW" and result["stake_usd"]==5
    assert result["platform_comparisons"][0]["platform"]=="Kalshi"
    assert any(q["platform"]=="Polymarket" and q["ask"] is None
               for q in result["platform_comparisons"])
