const KEY = 'rv_cards'
const MAX = 12

export function pushRecentlyViewed(card) {
  if (!card?.id) return
  try {
    const entry = {
      id: card.id,
      player_name: card.player_name,
      year: card.year,
      set_name: card.set_name,
      variant: card.variant,
      sport: card.sport,
      fair_value: card.fair_value,
    }
    const existing = getRecentlyViewed().filter(c => c.id !== card.id)
    const next = [entry, ...existing].slice(0, MAX)
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch { /* storage unavailable */ }
}

export function getRecentlyViewed() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]')
  } catch { return [] }
}
