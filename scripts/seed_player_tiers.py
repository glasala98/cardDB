#!/usr/bin/env python3 -u
"""
Seed the players table with S and A tier players.

S-tier (+50): GOATs, generational icons, market movers.
              Any card of these players gets a meaningful score boost.
A-tier (+30): Active superstars, Hall of Famers, elite rookies.

B and C tiers are defaults — no seeding needed.
Cards with no players table entry score 0 for player dimension.

Usage:
    python scripts/seed_player_tiers.py           # upsert all players
    python scripts/seed_player_tiers.py --dry-run # print counts only
"""

import os, sys, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass
from db import get_db

# ── Player tier definitions ───────────────────────────────────────────────────
# Format: (player_name, sport, tier, notes)
# sport = 'ALL' for players who appear across multiple sports (rare).
# Names must match card_catalog.player_name exactly — use the form
# as it appears on cards ("Ken Griffey Jr." not "Ken Griffey Jr").

PLAYERS = [

    # ── NHL — S tier ──────────────────────────────────────────────────────────
    ("Wayne Gretzky",      "NHL", "S", "GOAT"),
    ("Mario Lemieux",      "NHL", "S", "GOAT"),
    ("Gordie Howe",        "NHL", "S", "GOAT vintage"),
    ("Bobby Orr",          "NHL", "S", "GOAT vintage"),
    ("Sidney Crosby",      "NHL", "S", "Active GOAT"),
    ("Connor McDavid",     "NHL", "S", "Current GOAT"),
    ("Alex Ovechkin",      "NHL", "S", "Goal-scoring GOAT"),

    # ── NHL — A tier ──────────────────────────────────────────────────────────
    ("Connor Bedard",      "NHL", "A", "2023 #1 pick, generational rookie"),
    ("Auston Matthews",    "NHL", "A", "Top active scorer"),
    ("Nathan MacKinnon",   "NHL", "A", "Elite centre"),
    ("Nikita Kucherov",    "NHL", "A", "Elite winger"),
    ("David Pastrnak",     "NHL", "A", "Elite winger"),
    ("Cale Makar",         "NHL", "A", "Elite defenceman"),
    ("Erik Karlsson",      "NHL", "A", "Elite defenceman"),
    ("Patrick Roy",        "NHL", "A", "GOAT goalie"),
    ("Martin Brodeur",     "NHL", "A", "Wins record goalie"),
    ("Jaromir Jagr",       "NHL", "A", "All-time great winger"),
    ("Mark Messier",       "NHL", "A", "6x Cup winner"),
    ("Steve Yzerman",      "NHL", "A", "Red Wings icon"),
    ("Joe Sakic",          "NHL", "A", "HOF centre"),
    ("Brendan Shanahan",   "NHL", "A", "HOF winger"),
    ("Peter Forsberg",     "NHL", "A", "HOF centre"),
    ("Teemu Selanne",      "NHL", "A", "HOF winger"),

    # ── NBA — S tier ──────────────────────────────────────────────────────────
    ("Michael Jordan",     "NBA", "S", "GOAT"),
    ("LeBron James",       "NBA", "S", "GOAT contender, active"),
    ("Kobe Bryant",        "NBA", "S", "GOAT, massive collector base"),
    ("Magic Johnson",      "NBA", "S", "Showtime GOAT"),
    ("Larry Bird",         "NBA", "S", "Celtics GOAT"),
    ("Kareem Abdul-Jabbar","NBA", "S", "All-time scoring record"),
    ("Shaquille O'Neal",   "NBA", "S", "Dominant big, huge RC market"),
    ("Victor Wembanyama",  "NBA", "S", "Generational rookie 2023"),

    # ── NBA — A tier ──────────────────────────────────────────────────────────
    ("Stephen Curry",      "NBA", "A", "3-point GOAT, active"),
    ("Kevin Durant",       "NBA", "A", "Elite scorer, active"),
    ("Giannis Antetokounmpo","NBA","A","2x MVP, active"),
    ("Luka Doncic",        "NBA", "A", "Elite PG, active"),
    ("Jayson Tatum",       "NBA", "A", "2024 Champion"),
    ("Nikola Jokic",       "NBA", "A", "3x MVP, active"),
    ("Ja Morant",          "NBA", "A", "High-demand star"),
    ("Anthony Edwards",    "NBA", "A", "Rising star"),
    ("Chet Holmgren",      "NBA", "A", "Top 2022 pick"),
    ("Paolo Banchero",     "NBA", "A", "2022 #1 pick"),
    ("Wilt Chamberlain",   "NBA", "A", "All-time great"),
    ("Bill Russell",       "NBA", "A", "11x Champion"),
    ("Charles Barkley",    "NBA", "A", "HOF, massive fanbase"),
    ("Allen Iverson",      "NBA", "A", "HOF, huge collector base"),
    ("Tim Duncan",         "NBA", "A", "5x Champion, HOF"),
    ("Dirk Nowitzki",      "NBA", "A", "HOF, international appeal"),
    ("Dwyane Wade",        "NBA", "A", "HOF, Heat icon"),
    ("Chris Paul",         "NBA", "A", "HOF-bound PG"),
    ("Russell Westbrook",  "NBA", "A", "Triple-double record"),
    ("Zion Williamson",    "NBA", "A", "2019 #1 pick"),

    # ── NFL — S tier ──────────────────────────────────────────────────────────
    ("Tom Brady",          "NFL", "S", "GOAT, 7x SB"),
    ("Patrick Mahomes",    "NFL", "S", "Active GOAT, 3x SB"),
    ("Joe Montana",        "NFL", "S", "4x SB GOAT"),
    ("Jerry Rice",         "NFL", "S", "GOAT WR"),
    ("Walter Payton",      "NFL", "S", "GOAT RB"),
    ("Lawrence Taylor",    "NFL", "S", "GOAT LB"),

    # ── NFL — A tier ──────────────────────────────────────────────────────────
    ("Josh Allen",         "NFL", "A", "Elite QB, active"),
    ("Justin Herbert",     "NFL", "A", "Elite QB, active"),
    ("Joe Burrow",         "NFL", "A", "Elite QB, active"),
    ("Lamar Jackson",      "NFL", "A", "2x MVP, active"),
    ("Jalen Hurts",        "NFL", "A", "Elite QB, active"),
    ("Caleb Williams",     "NFL", "A", "2024 #1 pick"),
    ("Drake Maye",         "NFL", "A", "2024 top pick"),
    ("Travis Kelce",       "NFL", "A", "GOAT TE, Taylor Swift effect"),
    ("Justin Jefferson",   "NFL", "A", "Elite WR"),
    ("Ja'Marr Chase",      "NFL", "A", "Elite WR"),
    ("CeeDee Lamb",        "NFL", "A", "Elite WR"),
    ("Brock Purdy",        "NFL", "A", "Super Bowl QB"),
    ("Peyton Manning",     "NFL", "A", "2x SB, HOF"),
    ("Brett Favre",        "NFL", "A", "HOF QB"),
    ("John Elway",         "NFL", "A", "2x SB, HOF"),
    ("Barry Sanders",      "NFL", "A", "HOF RB, huge collector base"),
    ("Emmitt Smith",       "NFL", "A", "All-time rushing record"),
    ("Deion Sanders",      "NFL", "A", "Prime Time, 2-sport star"),
    ("Dan Marino",         "NFL", "A", "HOF QB"),
    ("Jim Brown",          "NFL", "A", "Greatest RB ever"),
    ("Randy Moss",         "NFL", "A", "HOF WR"),

    # ── MLB — S tier ──────────────────────────────────────────────────────────
    ("Babe Ruth",          "MLB", "S", "GOAT, pre-war icon"),
    ("Mickey Mantle",      "MLB", "S", "GOAT vintage, highest-value RC"),
    ("Ken Griffey Jr.",    "MLB", "S", "GOAT modern era, iconic RC"),
    ("Mike Trout",         "MLB", "S", "Active GOAT, most valuable modern RC"),
    ("Shohei Ohtani",      "MLB", "S", "2-way GOAT, $700M contract"),

    # ── MLB — A tier ──────────────────────────────────────────────────────────
    ("Derek Jeter",        "MLB", "A", "Yankees icon, HOF"),
    ("Willie Mays",        "MLB", "A", "All-time great CF"),
    ("Hank Aaron",         "MLB", "A", "HR record holder (pre-Bonds)"),
    ("Ted Williams",       "MLB", "A", "Last .400 hitter"),
    ("Ty Cobb",            "MLB", "A", "Pre-war icon"),
    ("Juan Soto",          "MLB", "A", "Elite OF, active"),
    ("Ronald Acuna Jr.",   "MLB", "A", "40-70 season, active"),
    ("Bryce Harper",       "MLB", "A", "2x MVP, active"),
    ("Mookie Betts",       "MLB", "A", "Elite OF, active"),
    ("Elly De La Cruz",    "MLB", "A", "Exciting 2023 rookie"),
    ("Jackson Holliday",   "MLB", "A", "2024 top prospect"),
    ("Paul Skenes",        "MLB", "A", "2024 #1 pick, pitcher"),
    ("Julio Rodriguez",    "MLB", "A", "Elite OF, active"),
    ("Gunnar Henderson",   "MLB", "A", "Elite SS, active"),
    ("Pete Alonso",        "MLB", "A", "HR leader, active"),
    ("Randy Johnson",      "MLB", "A", "HOF pitcher"),
    ("Greg Maddux",        "MLB", "A", "HOF pitcher"),
    ("Cal Ripken Jr.",     "MLB", "A", "Iron Man, HOF"),
    ("Nolan Ryan",         "MLB", "A", "K record, HOF"),
    ("Roger Clemens",      "MLB", "A", "7 Cy Youngs"),
    ("Barry Bonds",        "MLB", "A", "HR record, polarising but high demand"),
    ("Frank Thomas",       "MLB", "A", "Big Hurt, HOF"),

    # ── Golf ─────────────────────────────────────────────────────────────────
    ("Tiger Woods",        "Golf", "S", "Golf GOAT, most valuable golf RC"),
    ("Jack Nicklaus",      "Golf", "S", "18 majors, all-time record"),
    ("Rory McIlroy",       "Golf", "A", "4 majors, current world #1 contender"),
    ("Scottie Scheffler",  "Golf", "A", "Current world #1, 2x Masters"),
    ("Jon Rahm",           "Golf", "A", "US Open + Masters winner"),
    ("Jordan Spieth",      "Golf", "A", "3 majors, popular in hobby"),
    ("Bryson DeChambeau",  "Golf", "A", "US Open winner, LIV Golf"),
    ("Phil Mickelson",     "Golf", "A", "6 majors, Lefty fanbase"),
    ("Justin Thomas",      "Golf", "A", "2x PGA Champion"),
    ("Xander Schauffele",  "Golf", "A", "2024 Masters + PGA winner"),
    ("Nelly Korda",        "Golf", "A", "World #1 women's, Olympic gold"),
    ("Collin Morikawa",    "Golf", "A", "2 majors, top modern player"),
    ("Viktor Hovland",     "Golf", "A", "FedEx Cup, European star"),

    # ── Soccer / Football ─────────────────────────────────────────────────────
    ("Lionel Messi",       "Soccer", "S", "GOAT, 8 Ballon d'Or, World Cup winner"),
    ("Cristiano Ronaldo",  "Soccer", "S", "GOAT contender, 5x Ballon d'Or"),
    ("Pelé",               "Soccer", "S", "3x World Cup, all-time legend"),
    ("Diego Maradona",     "Soccer", "S", "1986 World Cup GOAT"),
    ("Kylian Mbappé",      "Soccer", "S", "World Cup winner, current GOAT successor"),
    ("Erling Haaland",     "Soccer", "A", "Most prolific current striker"),
    ("Vinicius Jr.",       "Soccer", "A", "UCL winner, Ballon d'Or contender"),
    ("Jude Bellingham",    "Soccer", "A", "Generational young star"),
    ("Lamine Yamal",       "Soccer", "A", "Euro 2024 winner, generational prospect"),
    ("Pedri",              "Soccer", "A", "Elite Barcelona midfielder"),
    ("Rodri",              "Soccer", "A", "2024 Ballon d'Or winner"),
    ("Mohamed Salah",      "Soccer", "A", "Liverpool icon, huge collector base"),
    ("Neymar Jr.",         "Soccer", "A", "Massive collector base globally"),
    ("Kevin De Bruyne",    "Soccer", "A", "Best midfielder of his era"),
    ("Ronaldinho",         "Soccer", "A", "2x Ballon d'Or, beloved in hobby"),
    ("Zinedine Zidane",    "Soccer", "A", "World Cup + UCL legend"),
    ("Thierry Henry",      "Soccer", "A", "Arsenal icon, French GOAT"),

    # ── Cross-sport ───────────────────────────────────────────────────────────
    ("Deion Sanders",      "ALL",    "A", "2-sport star NFL/MLB"),
    ("Bo Jackson",         "ALL",    "A", "2-sport icon NFL/MLB"),
]


def seed(dry_run: bool):
    upserted = 0
    skipped  = 0

    with get_db() as conn:
        with conn.cursor() as cur:
            for player_name, sport, tier, notes in PLAYERS:
                if dry_run:
                    cur.execute(
                        "SELECT id FROM players WHERE player_name = %s AND sport = %s",
                        (player_name, sport)
                    )
                    exists = cur.fetchone()
                    action = "UPDATE" if exists else "INSERT"
                    print(f"  [{action}] {tier}  {sport:<4}  {player_name}")
                    upserted += 1
                else:
                    cur.execute("""
                        INSERT INTO players (player_name, sport, player_tier, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (player_name, sport)
                        DO UPDATE SET
                            player_tier = EXCLUDED.player_tier,
                            notes       = EXCLUDED.notes,
                            updated_at  = NOW()
                    """, (player_name, sport, tier, notes))
                    upserted += 1

        if not dry_run:
            conn.commit()

    return upserted


def main():
    parser = argparse.ArgumentParser(description="Seed player tiers")
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    prefix = "DRY RUN — " if args.dry_run else ""
    print(f"{prefix}Seeding player tiers ({len(PLAYERS)} players)...")

    n = seed(args.dry_run)

    s_count = sum(1 for p in PLAYERS if p[2] == 'S')
    a_count = sum(1 for p in PLAYERS if p[2] == 'A')
    print(f"\n  S-tier: {s_count} players (+50 score each)")
    print(f"  A-tier: {a_count} players (+30 score each)")
    print(f"  Total upserted: {n}")

    if not args.dry_run:
        print()
        print("  Player tiers written. trg_rescore_on_player will have re-scored")
        print("  all matching cards automatically via the DB trigger.")
        print()
        print("  Run assign_catalog_tiers.py --all to score any cards added")
        print("  before this migration (trigger only fires on new inserts/updates).")


if __name__ == '__main__':
    main()
