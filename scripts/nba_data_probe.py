"""Keyless NBA odds smoke: reads today's ESPN moneylines, prints compact info."""
from nba_odds import get_nba, day_central

def main():
    day=day_central()
    games=get_nba(day)
    print("Day (Central):",day,"Games with usable future odds:",len(games))
    for g in games:
        print(g.away, "@", g.home, "|", g.provider,
              f"away {g.odds_away:+d} ({g.fair_away:.1%})",
              f"home {g.odds_home:+d} ({g.fair_home:.1%})", "|",g.link)
    print("No keys or wallets used. No odds = no automatic edge claim.")

if __name__=="__main__":
    main()
