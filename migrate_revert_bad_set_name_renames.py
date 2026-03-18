"""
migrate_revert_bad_set_name_renames.py — Revert incorrect set name renames from
migrate_clean_set_names.py where the broad 'cards?' regex stripped legitimate
product names like 'Wild Card', 'Q Card', 'Power Card', 'GWG Card'.

Safe to re-run.
"""
import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

# (current_wrong_name, correct_original_name)
REVERTS = [
    ("1990 U.S. Oil Milwaukee Brewers Pin with",   "1990 U.S. Oil Milwaukee Brewers Pin with Card"),
    ("1991-92 Wild",                               "1991-92 Wild Card"),
    ("1991 Q",                                     "1991 Q Card"),
    ("1991 Wild",                                  "1991 Wild Card"),
    ("1992 Wild",                                  "1992 Wild Card"),
    ("1993 Wild",                                  "1993 Wild Card"),
    ("1997 Taiwan Major League Power",             "1997 Taiwan Major League Power Card"),
    ("2009 Yomiuri Giants Giants Winning Game (GWG)", "2009 Yomiuri Giants Giants Winning Game (GWG) Card"),
    ("2010 Yomiuri Giants Giants Winning Game (GWG)", "2010 Yomiuri Giants Giants Winning Game (GWG) Card"),
    ("2013 Yomiuri Giants Giants Winning Game (GWG)", "2013 Yomiuri Giants Giants Winning Game (GWG) Card"),
]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    try:
        for wrong, correct in REVERTS:
            cur.execute(
                "UPDATE card_catalog SET set_name = %s WHERE set_name = %s",
                (correct, wrong),
            )
            n = cur.rowcount
            if n:
                print(f"  Reverted {n:>5} rows: '{wrong}' → '{correct}'")
            else:
                print(f"  (no rows) '{wrong}' — already correct or not found")
        conn.commit()
        print("Done.")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
