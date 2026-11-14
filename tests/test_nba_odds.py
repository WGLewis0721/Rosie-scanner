from datetime import timedelta
from nba_odds import american, parse_nba, match_team_sides, board, target_ask, day_central
from market_scan import Market, now_utc

def future(hours=4):
    return (now_utc()+timedelta(hours=hours)).isoformat()

def fixture():
    return {"events":[{"id":"123","date":future(),"status":{"type":{"state":"pre"}},
     "competitions":[{"competitors":[
       {"homeAway":"home","team":{"displayName":"Cleveland Cavaliers"}},
       {"homeAway":"away","team":{"displayName":"Dallas Mavericks"}}],
      "odds":[{"provider":{"name":"DraftKings","id":"100"},"moneyline":{
       "home":{"close":{"odds":"+110"}},"away":{"close":{"odds":"-130"}}}}]}]}]}

def example_market(**kwargs):
    args=dict(platform="Polymarket",market_id="10",title="Dallas Mavericks vs Cleveland Cavaliers",
      outcome_a="Dallas Mavericks",outcome_b="Cleveland Cavaliers",close_at=future(5),
      url="https://polymarket.com/event/test",volume=5000,liquidity=5000,
      ask_a=.52,bid_a=.51,ask_b=.49,bid_b=.48,
      ask_size_a=20,ask_size_b=20,quote_status="orderbook")
    args.update(kwargs)
    return Market(**args)

def test_public_espn_moneyline_structure():
    games=parse_nba(fixture())
    assert len(games)==1
    assert games[0].away=="Dallas Mavericks"
    assert .5 < games[0].fair_away < .6
    assert abs(games[0].fair_home+games[0].fair_away-1)<1e-8

def test_real_odds_parsing_and_conservative_targets():
    assert american("−120")==-120
    assert american("+115")==115
    assert american("off")==None
    assert target_ask(.60,"Kalshi")<.55
    assert target_ask(.60,"Polymarket")<.55

def test_strict_moneyline_market_matching_and_net_edge():
    g=parse_nba(fixture())[0]
    m=example_market()
    assert match_team_sides(m,g)=={"Dallas Mavericks":"A","Cleveland Cavaliers":"B"}
    results=board([g],[m])
    assert len(results)==2
    assert any(r["ask"]==.52 for r in results)

def test_no_props_or_stale_inplay_as_moneyline():
    g=parse_nba(fixture())[0]
    m=example_market(title="Dallas Mavericks points vs Cleveland Cavaliers")
    assert match_team_sides(m,g)=={}
    row=fixture()["events"][0]
    row["status"]["type"]["state"]="in"
    assert parse_nba({"events":[row]})==[]

def test_indicative_gamma_prices_do_not_count_as_validated_edges():
    g=parse_nba(fixture())[0]
    m=example_market(ask_a=None,ask_b=None,indicative_a=.35,
                     indicative_b=.65,quote_status="indicative")
    assert not any(r["supported"] for r in board([g],[m]))
    assert not any(r["ask"] is not None for r in board([g],[m]))

def test_market_wrong_date_is_not_eligible():
    g=parse_nba(fixture())[0]
    m=example_market(close_at=future(130))
    assert match_team_sides(m,g)=={}

def test_empty_games_is_safe():
    assert board([],[])==[]
    assert parse_nba({"events":[]})==[]
