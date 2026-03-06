"""Personal collection endpoints — add catalog cards to a user's collection."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from api.routers.auth import get_current_user

router = APIRouter()

GRADES = ["Raw", "PSA 1", "PSA 2", "PSA 3", "PSA 4", "PSA 5", "PSA 6",
          "PSA 7", "PSA 8", "PSA 9", "PSA 10", "BGS 8", "BGS 8.5",
          "BGS 9", "BGS 9.5", "BGS 10", "SGC 9", "SGC 10"]


class AddToCollection(BaseModel):
    card_catalog_id: int
    grade:           str  = "Raw"
    quantity:        int  = 1
    cost_basis:      Optional[float] = None
    purchase_date:   Optional[str]   = None   # YYYY-MM-DD
    notes:           str  = ""


class UpdateCollection(BaseModel):
    grade:         Optional[str]   = None
    quantity:      Optional[int]   = None
    cost_basis:    Optional[float] = None
    purchase_date: Optional[str]   = None
    notes:         Optional[str]   = None


@router.get("")
def list_collection(user: str = Depends(get_current_user)):
    """Return the current user's full collection, joined with catalog + market prices."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                col.id,
                col.card_catalog_id,
                col.grade,
                col.quantity,
                col.cost_basis,
                col.purchase_date,
                col.notes,
                col.created_at,
                -- Card catalog fields
                cc.sport,
                cc.year,
                cc.brand,
                cc.set_name,
                cc.card_number,
                cc.player_name,
                cc.team,
                cc.variant,
                cc.print_run,
                cc.is_rookie,
                cc.is_parallel,
                -- Market price (if scraped)
                mp.fair_value,
                mp.trend,
                mp.confidence,
                mp.num_sales,
                mp.scraped_at
            FROM collection col
            JOIN card_catalog cc ON cc.id = col.card_catalog_id
            LEFT JOIN market_prices mp ON mp.card_catalog_id = col.card_catalog_id
            WHERE col.user_id = %s
            ORDER BY col.created_at DESC
        """, [user])
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    items = []
    for row in rows:
        r = dict(zip(cols, row))
        if r.get("fair_value") is not None:
            r["fair_value"] = float(r["fair_value"])
        if r.get("cost_basis") is not None:
            r["cost_basis"] = float(r["cost_basis"])
        if r.get("purchase_date"):
            r["purchase_date"] = r["purchase_date"].isoformat()
        if r.get("scraped_at"):
            r["scraped_at"] = r["scraped_at"].isoformat()
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        items.append(r)

    total_value = sum(
        (r["fair_value"] or 0) * (r["quantity"] or 1) for r in items
    )
    total_cost = sum(
        (r["cost_basis"] or 0) * (r["quantity"] or 1)
        for r in items if r["cost_basis"] is not None
    )

    return {
        "items":       items,
        "total_cards": sum(r["quantity"] or 1 for r in items),
        "total_value": round(total_value, 2),
        "total_cost":  round(total_cost, 2),
    }


@router.post("", status_code=201)
def add_to_collection(body: AddToCollection, user: str = Depends(get_current_user)):
    """Add a card from the catalog to the user's collection."""
    with get_db() as conn:
        cur = conn.cursor()

        # Verify the card exists
        cur.execute("SELECT id FROM card_catalog WHERE id = %s", [body.card_catalog_id])
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Card not found in catalog")

        try:
            cur.execute("""
                INSERT INTO collection
                    (user_id, card_catalog_id, grade, quantity, cost_basis, purchase_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, card_catalog_id, grade) DO UPDATE
                    SET quantity      = collection.quantity + EXCLUDED.quantity,
                        cost_basis    = COALESCE(EXCLUDED.cost_basis, collection.cost_basis),
                        purchase_date = COALESCE(EXCLUDED.purchase_date, collection.purchase_date),
                        notes         = CASE WHEN EXCLUDED.notes != '' THEN EXCLUDED.notes
                                             ELSE collection.notes END,
                        updated_at    = NOW()
                RETURNING id
            """, [
                user,
                body.card_catalog_id,
                body.grade,
                body.quantity,
                body.cost_basis,
                body.purchase_date or None,
                body.notes,
            ])
            row_id = cur.fetchone()[0]
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    return {"id": row_id, "status": "added"}


@router.patch("/{item_id}")
def update_collection_item(
    item_id: int,
    body: UpdateCollection,
    user: str = Depends(get_current_user),
):
    """Update grade, quantity, cost_basis, purchase_date, or notes for a collection item."""
    sets = []
    params = []

    if body.grade is not None:
        sets.append("grade = %s")
        params.append(body.grade)
    if body.quantity is not None:
        sets.append("quantity = %s")
        params.append(body.quantity)
    if body.cost_basis is not None:
        sets.append("cost_basis = %s")
        params.append(body.cost_basis)
    if body.purchase_date is not None:
        sets.append("purchase_date = %s")
        params.append(body.purchase_date or None)
    if body.notes is not None:
        sets.append("notes = %s")
        params.append(body.notes)

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets.append("updated_at = NOW()")
    params.extend([item_id, user])

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE collection SET {', '.join(sets)} WHERE id = %s AND user_id = %s",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        conn.commit()

    return {"status": "updated"}


@router.delete("/{item_id}", status_code=204)
def remove_from_collection(item_id: int, user: str = Depends(get_current_user)):
    """Remove a card from the user's collection."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM collection WHERE id = %s AND user_id = %s",
            [item_id, user],
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        conn.commit()


@router.get("/owned-ids")
def owned_catalog_ids(user: str = Depends(get_current_user)):
    """Return the set of card_catalog_ids owned by this user (for catalog badge rendering)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT card_catalog_id FROM collection WHERE user_id = %s",
            [user],
        )
        ids = [r[0] for r in cur.fetchall()]
    return {"owned_ids": ids}


@router.get("/grades")
def list_grades():
    """Return the supported grade options."""
    return {"grades": GRADES}
