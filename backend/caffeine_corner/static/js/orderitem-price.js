// Order Items inline (OrderAdmin, add form only — see OrderItemInline):
//
// 1. Fills in the per-unit Price as soon as staff pick a Product (or
//    Variant), instead of them having to look it up and type it in by hand.
// 2. Recomputes the readonly Subtotal column live as Quantity/Price change
//    — it's a plain display field (see OrderItemInline.get_subtotal),
//    computed server-side once at page load and never again on its own, so
//    without this it just sits stuck on "—" while staff type.
//
// Uses django.jQuery + delegated events (not plain addEventListener) on
// purpose: the Product field is a select2 autocomplete widget, whose real
// <select> is hidden and swapped by select2's own UI — only select2's own
// 'change' trigger (via jQuery) fires reliably for it. Delegation from
// `document` also means rows added later via "Add another Order Item"
// (cloned client-side, after this script already ran) are covered without
// re-binding anything.
document.addEventListener('DOMContentLoaded', function () {
  var $ = window.django && window.django.jQuery
  if (!$) return

  function updateSubtotal($row) {
    var qty = parseFloat($row.find('input[name$="-quantity"]').val())
    var price = parseFloat($row.find('input[name$="-price"]').val())
    var $cell = $row.find('.field-get_subtotal .readonly')
    if (!$cell.length) return
    $cell.text(qty > 0 && price >= 0 && !isNaN(qty) && !isNaN(price) ? '₱' + (qty * price).toFixed(2) : '—')
  }

  $(document).on('change', 'select[name$="-product"], select[name$="-variant"]', function () {
    var $row = $(this).closest('tr')
    var productId = $row.find('select[name$="-product"]').val()
    var variantId = $row.find('select[name$="-variant"]').val()
    var $price = $row.find('input[name$="-price"]')
    if (!productId || !$price.length) return

    var url = '/admin/products/' + encodeURIComponent(productId) + '/price/'
    if (variantId) url += '?variant=' + encodeURIComponent(variantId)

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) { return res.ok ? res.json() : null })
      .then(function (data) {
        if (data) {
          $price.val(data.price)
          updateSubtotal($row)
        }
      })
      .catch(function () {})
  })

  // 'input' (not just 'change') so it updates on every keystroke, not only
  // once the field loses focus.
  $(document).on('input', 'input[name$="-quantity"], input[name$="-price"]', function () {
    updateSubtotal($(this).closest('tr'))
  })
})
