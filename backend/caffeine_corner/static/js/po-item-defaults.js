// Purchase Order form (inventory.PurchaseOrderAdmin): once staff pick an item on
// a line, fill in what they would otherwise have to look up and type:
//
//   - Cost per unit  ← the item's cost (overwritten: it belongs to the item just picked)
//   - Order qty      ← the item's usual reorder quantity (only if still empty — never
//                      clobbers a number someone already typed)
//
// and keep the read-only "Line total" column live as quantity / cost change (it is
// computed server-side once at page load, so without this it stays stuck).
//
// Same pattern as orderitem-price.js: django.jQuery + delegated events, because the
// Item field is a select2 autocomplete (only its jQuery 'change' fires reliably),
// and delegation also covers lines added later with "Add another Item".
//
// Scoped to the PO's lines: that inline's form prefix is "items" and its item
// field is "inventory" — Order items also use the prefix "items", but with a
// "product" field, so this never touches them.
document.addEventListener('DOMContentLoaded', function () {
  var $ = window.django && window.django.jQuery
  if (!$) return

  var ITEM = 'select[name^="items-"][name$="-inventory"]'
  var QTY = 'input[name^="items-"][name$="-quantity_ordered"]'
  var COST = 'input[name^="items-"][name$="-unit_cost"]'

  function peso(n) {
    return '₱' + n.toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  function updateTotal($row) {
    var qty = parseFloat($row.find(QTY).val())
    var cost = parseFloat($row.find(COST).val())
    var $cell = $row.find('.field-line_total .readonly')
    if (!$cell.length) return
    $cell.text(qty > 0 && cost >= 0 && !isNaN(qty) && !isNaN(cost) ? peso(qty * cost) : '—')
  }

  $(document).on('change', ITEM, function () {
    var $row = $(this).closest('tr')
    var id = $(this).val()
    if (!id) return

    fetch('/admin/inventory/' + encodeURIComponent(id) + '/po-defaults/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) { return res.ok ? res.json() : null })
      .then(function (data) {
        if (!data) return
        $row.find(COST).val(data.unit_cost)
        var $qty = $row.find(QTY)
        if (!$qty.val() && data.quantity) $qty.val(data.quantity)
        updateTotal($row)
      })
      .catch(function () {})
  })

  // 'input' (not just 'change') so it updates on every keystroke.
  $(document).on('input', QTY + ', ' + COST, function () {
    updateTotal($(this).closest('tr'))
  })
})
