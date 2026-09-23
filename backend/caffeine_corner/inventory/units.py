"""
Small metric-unit conversion helper for inventory & recipe quantities.

Ingredient.unit (a recipe's "how much of this inventory item goes into one
drink") and Inventory.unit (what the stock itself is tracked in) are both
free-text — nothing stops a recipe being written in "ml" while the matching
stock is tracked in "L". Without conversion, a recipe calling for "200 ml" of
milk tracked in "L" would take 200 *liters* off the shelf per drink instead
of 0.2 — see online_shop.signals, the only place ingredient quantities are
turned into stock movements.

Scope is deliberately small — the two metric pairs this shop actually deals
in (volume: L/mL, weight: kg/g) — not a general units-of-measure system. A
unit this module doesn't recognize (count-style ones like "pcs", "pack",
"box") is left exactly alone, the same as the app's behavior before this
existed.
"""
from decimal import Decimal

# Each family: canonical unit -> how many of it makes up the family's base unit.
_VOLUME = {'ml': Decimal('1'), 'l': Decimal('1000')}   # base: ml
_WEIGHT = {'g': Decimal('1'), 'kg': Decimal('1000')}   # base: g
_FAMILIES = {'volume': _VOLUME, 'weight': _WEIGHT}

_ALIASES = {
    'ml': 'ml', 'milliliter': 'ml', 'milliliters': 'ml', 'millilitre': 'ml', 'millilitres': 'ml',
    'l': 'l', 'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l',
    'g': 'g', 'gram': 'g', 'grams': 'g',
    'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
}


def normalize(unit):
    """'L' / ' Liters ' / 'Litre' -> 'l'. Anything this module doesn't recognize comes back just lowercased and stripped."""
    key = (unit or '').strip().lower()
    return _ALIASES.get(key, key)


def family_of(unit):
    """'volume', 'weight', or None if `unit` isn't one this module recognizes."""
    key = normalize(unit)
    for label, family in _FAMILIES.items():
        if key in family:
            return label
    return None


def convertible(from_unit, to_unit):
    """Whether convert() can actually turn one into the other — both recognized, and the same family."""
    label = family_of(from_unit)
    return label is not None and label == family_of(to_unit)


def convert(quantity, from_unit, to_unit):
    """
    `quantity` (expressed in `from_unit`) converted to `to_unit`. Units are
    matched case/plural/spelling-insensitively (see normalize()).

    If the two units aren't both recognized members of the same family —
    including either one being something this module doesn't know, like
    "pcs" — the quantity comes back unchanged: there's nothing safe to
    convert, so it's left exactly as given rather than guessed at.
    """
    quantity = Decimal(quantity)
    a, b = normalize(from_unit), normalize(to_unit)
    if a == b:
        return quantity
    if not convertible(from_unit, to_unit):
        return quantity
    family = _FAMILIES[family_of(from_unit)]
    return quantity * family[a] / family[b]
