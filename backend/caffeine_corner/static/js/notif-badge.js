// Live unread-notification count next to "Notifications" in the sidebar.
// Unfold's own nav "badge" option runs values through django.utils.functional.lazy()
// before the template prints them, which re-casts our HTML to a plain str
// and escapes it — no way to get hx-* attributes through that path. Doing
// it by hand here instead: poll a small JSON endpoint and paint a plain
// badge, which also sidesteps needing a page reload to see new counts.
document.addEventListener('DOMContentLoaded', function () {
  var link = document.querySelector('#nav-sidebar-apps a[href$="/online_shop/notification/"]')
  if (!link) return

  link.style.display = 'flex'
  link.style.alignItems = 'center'

  var badge = document.createElement('span')
  badge.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;' +
    'margin-left:auto;padding:0 5px;border-radius:9999px;background:#dc2626;color:#fff;' +
    'font-size:10px;font-weight:700;line-height:1;'
  badge.hidden = true
  link.appendChild(badge)

  function refresh() {
    fetch('/admin/notifications/unread-count/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) { return res.ok ? res.json() : null })
      .then(function (data) {
        if (!data) return
        badge.hidden = data.count === 0
        badge.textContent = data.count > 99 ? '99+' : String(data.count)
      })
      .catch(function () {})
  }

  refresh()
  setInterval(refresh, 20000)
})
