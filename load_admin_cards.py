"""
Load the admin card collection into the database (or CSV for local dev).

Usage:
    python load_admin_cards.py --dry-run        # print list, no changes
    python load_admin_cards.py --csv            # write data/admin/card_prices_summary.csv
    python load_admin_cards.py                  # load into PostgreSQL (requires DATABASE_URL)
"""

import sys, os, csv

CARDS = [
    "2018-19 Upper Deck Parkhurst - [Base] #331 - Rookies - Elias Pettersson",
    "2019-20 Upper Deck Parkhurst - [Base] #317 - Rookies - Noah Dobson",
    "2019-20 Upper Deck Parkhurst - [Base] #320 - Rookies - Jack Hughes",
    "2020-21 O-Pee-Chee Platinum - [Base] - Rainbow #157 - Marquee Rookies - Thomas Harley",
    "2020-21 O-Pee-Chee Platinum - Retro #R-59 - Rookies - Brandon Hagel",
    "2020-21 Upper Deck - [Base] - Photo Variation #419 - Auston Matthews [Poor to Fair]",
    "2021-22 O-Pee-Chee Platinum - [Base] - Rainbow Color Wheel #284 - Marquee Rookies - Seth Jarvis",
    "2021-22 Upper Deck Fleer Ultra - [Base] - Blue Foil #100 - Connor McDavid [Passed Pre-Grade Review] #243/399",
    "2022-23 O-Pee-Chee Platinum - [Base] - Aquamarine #239 - Marquee Rookies - Noah Cates #15/149",
    "2022-23 Skybox Metal Universe - Hardware #HW-4 - Nazem Kadri",
    "2022-23 Upper Deck Extended Series - [Base] #705 - Young Guns - Jonatan Berggren",
    "2022-23 Upper Deck Fleer Ultra - 30th Anniversary #A-10 - Felix Potvin",
    "2022-23 Upper Deck Synergy - Cranked Up - Purple #CU-SC - Sidney Crosby #70/99",
    "2022-23 Upper Deck Synergy - Light Up The Night #LN-CP - Carey Price #754/899",
    "2023 Upper Deck All-Sports Game Dated Moments - [Base] #66 - (Dec. 26, 2023) - Macklin Celebrini Scores First Goal of the 2024 World Junior Championship",
    "2023-24 O-Pee-Chee Platinum - [Base] - Arctic Freeze #177 - Nazem Kadri #44/99",
    "2023-24 O-Pee-Chee Platinum - [Base] - Cosmic #256 - Marquee Rookies - John Beecher #58/65",
    "2023-24 O-Pee-Chee Platinum - [Base] - Emerald Surge #14 - Jake Sanderson #1/10",
    "2023-24 O-Pee-Chee Platinum - [Base] - Emerald Surge #53 - Nick Suzuki [PSA 10 GEM MT] #10/10",
    "2023-24 O-Pee-Chee Platinum - [Base] - NHL Shield Variations #203 - Marquee Rookies - Adam Fantilli [PSA 10 GEM MT]",
    "2023-24 O-Pee-Chee Platinum - [Base] - Pond Hockey Variants #202 - Marquee Rookies - Logan Cooley [PSA 10 GEM MT]",
    "2023-24 O-Pee-Chee Platinum - [Base] - Pond Hockey Variants #203 - Marquee Rookies - Adam Fantilli [PSA 10 GEM MT]",
    "2023-24 O-Pee-Chee Platinum - [Base] - Pond Hockey Variants #205 - Marquee Rookies - Matthew Knies",
    "2023-24 O-Pee-Chee Platinum - [Base] - Rainbow Color Wheel #201 - Marquee Rookies - Connor Bedard",
    "2023-24 O-Pee-Chee Platinum - [Base] - Rainbow Color Wheel #224 - Marquee Rookies - Mason Lohrei",
    "2023-24 O-Pee-Chee Platinum - [Base] - Red Prism #201 - Marquee Rookies - Connor Bedard [PSA 9 MINT] #70/199",
    "2023-24 O-Pee-Chee Platinum - [Base] - Red Prism #281 - Marquee Rookies - Hardy Haman Aktell #109/199",
    "2023-24 O-Pee-Chee Platinum - [Base] - Red Prism #293 - Marquee Rookies - Leo Carlsson [PSA 10 GEM MT] #53/199",
    "2023-24 O-Pee-Chee Platinum - [Base] - Violet Pixels #201 - Marquee Rookies - Connor Bedard [PSA 10 GEM MT] #260/299",
    "2023-24 O-Pee-Chee Platinum - [Base] - Violet Pixels #236 - Marquee Rookies - Connor Zary [Passed Pre-Grade Review] #168/299",
    "2023-24 O-Pee-Chee Platinum - [Base] - Violet Pixels #53 - Nick Suzuki #116/299",
    "2023-24 O-Pee-Chee Platinum - Photo Driven - Red Pixel #PD-6 - Auston Matthews [PSA 10 GEM MT] #75/85",
    "2023-24 O-Pee-Chee Platinum - Retro #R-100 - Rookie - Connor Bedard",
    "2023-24 O-Pee-Chee Platinum - Rookie Autographs - Rainbow #R-HT - Henry Thrun",
    "2023-24 Upper Deck Allure - [Base] - Blue Line Auto Jersey #114 - Rookies - Leo Carlsson #28/35",
    "2023-24 Upper Deck Allure - [Base] - Hypnosis #124 - Rookies - Matthew Kessel [Passed Pre-Grade Review]",
    "2023-24 Upper Deck Allure - Color Flow - Orange Yellow Spectrum #CF-16 - Connor Bedard [PSA 10 GEM MT] #125/199",
    "2023-24 Upper Deck Extended Series - [Base] #724 - Young Guns - Dennis Hildeby",
    "2023-24 Upper Deck Fleer Ultra - 2053-54 Fleer Ultra #U-38 - Connor McDavid",
    "2023-24 Upper Deck Parkhurst - Prominent Prospects #PP-CB - Connor Bedard [Passed Pre-Grade Review]",
    "2023-24 Upper Deck Parkhurst - Prominent Prospects #PP-KN - Matthew Knies",
    "2023-24 Upper Deck Parkhurst - Prominent Prospects - Blue #PP-MA - Matthew Kessel [Passed Pre-Grade Review] #24/25",
    "2023-24 Upper Deck Parkhurst - Prominent Prospects - Purple #PP-BF - Brock Faber [Passed Pre-Grade Review] #15/99",
    "2023-24 Upper Deck Series 1 - [Base] #201 - Young Guns - Matthew Coronato",
    "2023-24 Upper Deck Series 1 - [Base] #213 - Young Guns - Will Cuylle",
    "2023-24 Upper Deck Series 1 - [Base] #221 - Young Guns - Luke Evangelista",
    "2023-24 Upper Deck Series 1 - [Base] #228 - Young Guns - Simon Edvinsson",
    "2023-24 Upper Deck Series 1 - [Base] #241 - Young Guns - Marco Kasper",
    "2023-24 Upper Deck Series 1 - [Base] #248 - Young Guns - Luke Hughes [PSA 9 MINT]",
    "2023-24 Upper Deck Series 1 - [Base] - Deluxe #144 - Tomas Hertl #1/250",
    "2023-24 Upper Deck Series 1 - [Base] - Outburst Silver #44 - Mikko Rantanen",
    "2023-24 Upper Deck Series 1 - UD Canvas #C103 - Young Guns - Matthew Knies [PSA 9 MINT]",
    "2023-24 Upper Deck Series 2 - [Base] #451 - Young Guns - Connor Bedard [PSA 9 MINT]",
    "2023-24 Upper Deck Series 2 - [Base] #456 - Young Guns - Jackson LaCombe",
    "2023-24 Upper Deck Series 2 - [Base] #492 - Young Guns - Dmitri Voronkov",
    "2023-24 Upper Deck Series 2 - [Base] #500 - Young Guns Checklist - Connor Bedard, Leo Carlsson",
    "2023-24 Upper Deck Synergy - Synergistic Duos Star-Legend - Green #SD-8 - Auston Matthews, Doug Gilmour #179/399",
    "2024 Fleer Scooby Doo - S-S-Scared S-S-Sketches #SKT - Ryan Finley",
    "2024 Upper Deck - UD Retro Rookies #RR-10 - Corey Conners",
    "2024 Upper Deck PWHL 1st Edition - [Base] #51 - Young Guns - Sarah Nurse",
    "2024 Upper Deck PWHL 1st Edition - [Base] #52 - Young Guns - Grace Zumwinkle",
    "2024 Upper Deck PWHL 1st Edition - [Base] #54 - Young Guns - Alex Carpenter",
    "2024 Upper Deck PWHL 1st Edition - [Base] #55 - Young Guns - Brianne Jenner",
    "2024 Upper Deck PWHL 1st Edition - [Base] #60 - Young Guns - Ann-Renee Desbiens",
    "2024 Upper Deck PWHL 1st Edition - [Base] #61 - Young Guns - Taylor Heise [PSA 8 NM-MT]",
    "2024 Upper Deck PWHL 1st Edition - [Base] #63 - Young Guns - Natalie Spooner",
    "2024 Upper Deck PWHL 1st Edition - [Base] #65 - Young Guns - Marie-Philip Poulin",
    "2024 Upper Deck PWHL 1st Edition - [Base] #67 - Young Guns - Gabbie Hughes",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Deluxe #59 - Young Guns - Emma Maltais [PSA 9 MINT] #48/250",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Exclusives #3 - Elaine Chuli #68/100",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Exclusives #7 - Maddie Rooney #72/100",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Exclusives #15 - Akane Shiga #15/100",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Exclusives #31 - Samantha Cogan #43/100",
    "2024 Upper Deck PWHL 1st Edition - [Base] - Outburst #56 - Young Guns - Alina Muller",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-2 - Marie-Philip Poulin",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-8 - Loren Gabel",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-10 - Emily Clark",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-11 - Jocelyne Larocque",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-12 - Rebecca Leslie",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-13 - Jamie Lee Rattray",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-15 - Chloe Aurard",
    "2024 Upper Deck PWHL 1st Edition - Dazzlers #DZ-19 - Aerin Frankel",
    "2024 Upper Deck PWHL 1st Edition - UD Portraits #P-2 - Marie-Philip Poulin",
    "2024 Upper Deck PWHL 1st Edition - UD Portraits - Gold #P-2 - Marie-Philip Poulin [PSA 10 GEM MT] #82/299",
    "2024 Upper Deck Team Canada Juniors - [Base] - Jersey #24 - Liam Greentree",
    "2024 Upper Deck Team Canada Juniors - [Base] - Signatures #139 - Program of Excellence - Liam Greentree",
    "2024-25 4 Nations Face-Off - Game Dated Moments #2 - (Feb. 12, 2025) - Crosby Dishes out Three Assists as Canada Tops Sweden at the 4 Nations Face-Off",
    "2024-25 4 Nations Face-Off - Game Dated Moments - Silver #2 - (Feb. 12, 2025) - Crosby Dishes out Three Assists as Canada Tops Sweden at the 4 Nations Face-Off",
    "2024-25 4 Nations Face-Off - Game Dated Moments - Silver #20 - (Feb. 20, 2025) - McDavid Scores in Overtime, Lifts Canada to Win Over U.S. in the 4 Nations Face-Off Championship Game",
    "2024-25 O-Pee-Chee Platinum - [Base] - Arctic Freeze #263 - Marquee Rookies - Macklin Celebrini #1/99",
    "2024-25 O-Pee-Chee Platinum - [Base] - Rainbow #206 - Marquee Rookies - Frank Nazar",
    "2024-25 O-Pee-Chee Platinum - [Base] - Rainbow #278 - Marquee Rookies - Will Smith",
    "2024-25 O-Pee-Chee Platinum - [Base] - Rainbow #300 - Marquee Rookies - Sebastian Cossa",
    "2024-25 O-Pee-Chee Platinum - [Base] - Red Prism #263 - Marquee Rookies - Macklin Celebrini #2/199",
    "2024-25 O-Pee-Chee Platinum - [Base] - Seismic Gold #46 - Lucas Raymond #20/50",
    "2024-25 O-Pee-Chee Platinum - [Base] - Violet Pixels #273 - Marquee Rookies - Ivan Ivan #292/299",
    "2024-25 O-Pee-Chee Platinum - [Base] - Violet Pixels #281 - Marquee Rookies - Jonathan Lekkerimaki #2/299",
    "2024-25 O-Pee-Chee Platinum - [Base] - Violet Pixels #300 - Marquee Rookies - Sebastian Cossa #48/299",
    "2024-25 O-Pee-Chee Platinum - O-Pee-Chee Premier #OP8 - Connor Bedard",
    "2024-25 O-Pee-Chee Platinum - Retro - Blue Luster #R82 - Rookies - Shakir Mukhamadullin #92/100",
    "2024-25 O-Pee-Chee Platinum - Rookie Autographs - Red Prism #R-LB - Lian Bichsel #21/30",
    "2024-25 Skybox Metal Universe - 2013 Retro #RT-2 - Cutter Gauthier",
    "2024-25 Skybox Metal Universe - Dawning #2 DW - Macklin Celebrini",
    "2024-25 Skybox Metal Universe - [Base] - Autographs #121 - Rookies - Rutger McGroarty",
    "2024-25 Upper Deck Credentials - [Base] - Autographs #145 - Debut Ticket Access - Collin Graf #163/199",
    "2024-25 Upper Deck Credentials - Acetate Debut Ticket Access #DTAA-RM - Rutger McGroarty #128/199",
    "2024-25 Upper Deck Credentials - Retro Ticket Access Auto Rookies #RTAR-CG - SP - Cutter Gauthier",
    "2024-25 Upper Deck Extended Series - [Base] #701 - Young Guns - Will Smith",
    "2024-25 Upper Deck Extended Series - UD Canvas #C369 - Young Guns - Lian Bichsel",
    "2024-25 Upper Deck Fleer Ultra - [Base] - Blue Foil #64 - Leo Carlsson #65/399",
    "2024-25 Upper Deck Fleer Ultra - [Base] - Silver Foil #204 - Rookies - Lane Hutson",
    "2024-25 Upper Deck Fleer Ultra - Ultra Team #UT 15 OF 40 - Matvei Michkov",
    "2024-25 Upper Deck Game Dated Moments - Rookie of the Month #R-1 - October - Matvei Michkov",
    "2024-25 Upper Deck PWHL - [Base] - Outburst #52 - Young Guns - Noora Tulus",
    "2024-25 Upper Deck Series 1 - [Base] #208 - Young Guns - Bradly Nadeau",
    "2024-25 Upper Deck Series 1 - [Base] #216 - Young Guns - Matt Rempe",
    "2024-25 Upper Deck Series 1 - [Base] #227 - Young Guns - Frank Nazar",
    "2024-25 Upper Deck Series 1 - [Base] #233 - Young Guns - Josh Doan",
    "2024-25 Upper Deck Series 1 - [Base] #244 - Young Guns - Logan Stankoven",
    "2024-25 Upper Deck Series 1 - UD Canvas #C-117 - Young Guns - Frank Nazar",
    "2024-25 Upper Deck Series 1 - UD Canvas #C-117 - Young Guns - Frank Nazar",
    "2024-25 Upper Deck Series 1 - Young Guns Renewed #YGR-21 - Carey Price",
    "2024-25 Upper Deck Series 2 - [Base] #451 - Young Guns - Macklin Celebrini [PSA 8 NM-MT]",
    "2024-25 Upper Deck Series 2 - [Base] #461 - Young Guns - Oliver Kapanen",
    "2024-25 Upper Deck Series 2 - [Base] #473 - Young Guns - Devin Cooley",
    "2024-25 Upper Deck Series 2 - [Base] #474 - Young Guns - Rutger McGroarty",
    "2024-25 Upper Deck Series 2 - [Base] #478 - Young Guns - Conor Geekie",
    "2024-25 Upper Deck Series 2 - [Base] #492 - Young Guns - Matvei Michkov",
    "2024-25 Upper Deck Series 2 - [Base] #492 - Young Guns - Matvei Michkov [PSA 7 NM]",
    "2024-25 Upper Deck Series 2 - [Base] #497 - Young Guns - Logan Mailloux, Lane Hutson",
    "2024-25 Upper Deck Series 2 - [Base] #498 - Young Guns - Olen Zellweger, Cutter Gauthier",
    "2024-25 Upper Deck Series 2 - [Base] #499 - Young Guns - Macklin Celebrini, Will Smith",
    "2024-25 Upper Deck Series 2 - [Base] #500 - Young Guns Checklist - Macklin Celebrini, Matvei Michkov",
    "2024-25 Upper Deck Series 2 - [Base] - Deluxe #454 - Young Guns - Brandon Scanlin #218/250",
    "2024-25 Upper Deck Series 2 - [Base] - Deluxe #493 - Young Guns - Brandon Bussi #199/250",
    "2024-25 Upper Deck Series 2 - [Base] - Outburst #461 - Young Guns - Oliver Kapanen",
    "2024-25 Upper Deck Series 2 - [Base] - Outburst #463 - Young Guns - Maxim Tsyplakov",
    "2024-25 Upper Deck Series 2 - [Base] - Outburst #380 - Sidney Crosby",
    "2024-25 Upper Deck Series 2 - [Base] - Silver Foil #313 - Leon Draisaitl",
    "2024-25 Upper Deck Series 2 - Day with the Cup #DC10 - Anton Lundell",
    "2024-25 Upper Deck Series 2 - UD Canvas #C161 - Joseph Woll [PSA 10 GEM MT]",
    "2024-25 Upper Deck Series 2 - UD Canvas #C172 - Patrick Kane",
    "2024-25 Upper Deck Series 2 - UD Canvas #C215 - Young Guns - Jackson Blake",
    "2024-25 Upper Deck Series 2 - UD Canvas #C221 - Young Guns - Adam Klapka",
    "2024-25 Upper Deck Series 2 - UD Canvas #C241 - Retired - Gordie Howe",
    "2024-25 Upper Deck Series 2 - UD Canvas #C256 - Program of Excellence - Olen Zellweger",
    "2024-25 Upper Deck Series 2 - UD Canvas - Black & White #C257 - Program of Excellence - Joshua Roy",
    "2024-25 Upper Deck Series 2 - UD Portraits #P37 - Macklin Celebrini",
    "2024-25 Upper Deck Series 2 - Young Guns Renewed #201.3 - Connor McDavid [PSA 9 MINT]",
    "2024-25 Upper Deck UD Rookie Debut - [Base] #9 - Lane Hutson",
    "2025 Upper Deck DC x NHL Crossover - [Base] #1 - Wayne Gretzky",
    "2025 Upper Deck DC x NHL Crossover - [Base] - Canvas Achievement #3 - Superman",
    "2025 Upper Deck DC x NHL Crossover - [Base] - Gold #4 - Superman and Krypto",
    "2025 Upper Deck DC x NHL Crossover - [Base] - Silver #4 - Superman and Krypto",
    "2025 Upper Deck GR8 Moments - [Base] #GR-1 - (Oct. 5, 2005) - Alex Ovechkin Scores Twice in Debut",
    "2025 Upper Deck GR8 Moments - [Base] - Blue #GR-7 - (Dec. 13, 2022) - Alex Ovechkin Scores 800th Goal",
    "2025 Upper Deck GR8 Moments - [Base] - Photo Variant Achievement #GR-8V - (Apr. 6, 2025) - Alex Ovechkin Breaks NHL Goals Record",
    "2025 Upper Deck GR8 Moments - [Base] - Red #GR-2 - (Oct. 12, 2007) - Alex Ovechkin Scores 100th Goal",
    "2025 Upper Deck GR8 Moments - [Base] - Red #GR-4 - (Jan. 21, 2010) - Alex Ovechkin Reaches 250 Goals",
    "2025 Upper Deck GR8 Moments - [Base] - Red #GR-6 - (Jun. 7, 2018) - Alex Ovechkin Lifts Stanley Cup",
    "2025 Upper Deck GR8 Moments - [Base] - Red #GR-8 - (Apr. 6, 2025) - Alex Ovechkin Breaks NHL Goals Record",
    "2025 Upper Deck Team Canada Juniors - [Base] - Auto Patch #12 - Keaton Verhoeff #128/150",
    "2025 Upper Deck Team Canada Juniors - [Base] - Jersey #85 - Pride of the Program - Gavin McKenna",
    "2025 Upper Deck Team Canada Juniors - [Base] - Outburst #42 - Alex Huang",
    "2025 Upper Deck Team Canada Juniors - [Base] - Red Foil #12 - Keaton Verhoeff",
    "2025 Upper Deck Team Canada Juniors - License to Ice #LI-23 - Chloe Primerano",
    "2025 Upper Deck Team Canada Juniors - Team Canada FX #FX-24 - Chloe Primerano",
    "2025-26 Upper Deck Series 1 - [Base] #201 - Young Guns - Artyom Levshunov",
    "2025-26 Upper Deck Series 1 - [Base] #202 - Young Guns - Gabe Perreault",
    "2025-26 Upper Deck Series 1 - [Base] #207 - Young Guns - Jimmy Snuggerud",
    "2025-26 Upper Deck Series 1 - [Base] #226 - Young Guns - Dalibor Dvorsky",
    "2025-26 Upper Deck Series 1 - [Base] #248 - Young Guns - Sam Rinzel",
    "2025-26 Upper Deck Series 1 - [Base] - Deluxe #236 - Young Guns - Zayne Parekh #106/250",
    "2025-26 Upper Deck Series 1 - Bootlegs #BL-18 - Artyom Levshunov",
    "2025-26 Upper Deck Series 1 - Dazzlers - Blue #DZ-39 - Lane Hutson",
    "2025-26 Upper Deck Series 1 - Encore #E-36 - Ivan Demidov",
]

# Deduplicate while preserving order
seen = set()
cards = []
for name in CARDS:
    if name not in seen:
        seen.add(name)
        cards.append(name)


CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "admin", "card_prices_summary.csv")
CSV_COLS = ["Card Name", "Fair Value", "Trend", "Top 3 Prices", "Median (All)",
            "Min", "Max", "Num Sales", "Tags", "Cost Basis", "Purchase Date"]


def run_dry():
    for i, name in enumerate(cards, 1):
        print(f"  {i:3}. {name}")


def run_csv():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for name in cards:
            w.writerow({"Card Name": name, "Fair Value": "$0.00", "Trend": "no data",
                        "Top 3 Prices": "", "Median (All)": "$0.00", "Min": "$0.00",
                        "Max": "$0.00", "Num Sales": "0", "Tags": "",
                        "Cost Basis": "$0.00", "Purchase Date": ""})
    print(f"Wrote {len(cards)} cards to {CSV_PATH}")
    print("Run: python daily_scrape.py --user admin")


def run_db():
    from db import get_db
    from psycopg2.extras import execute_values

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cards WHERE user_id = 'admin' AND (archived = FALSE OR archived IS NULL)"
            )
            print(f"Deleted {cur.rowcount} existing cards")
            execute_values(cur, """
                INSERT INTO cards (user_id, card_name)
                VALUES %s
                ON CONFLICT (user_id, card_name) DO NOTHING
            """, [("admin", name) for name in cards])
            print(f"Inserted {len(cards)} cards")
    print("Done. Run: python daily_scrape.py --user admin")


if __name__ == "__main__":
    print(f"Cards to load: {len(cards)}")
    if "--dry-run" in sys.argv:
        run_dry()
    elif "--csv" in sys.argv:
        run_csv()
    else:
        run_db()
