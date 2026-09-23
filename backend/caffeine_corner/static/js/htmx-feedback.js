// Tells staff when an admin action that saves something fails — instead of
// failing silently.
//
// HTMX drops 4xx/5xx responses on the floor: nothing is swapped in and nothing
// is shown. So a rejected save (bad input) or a status toggle that hit an
// expired session just looked like a button that doesn't work.
//
// Only requests that change data get a toast (not GET): a background/read
// request failing shouldn't pop a message up on its own.
//
// Guarded by tests/test_online_shop/test_admin_scripts.py (FeedbackScriptGuardTests).
(function () {
  var TOAST_ID = 'htmx-feedback-toast'
  var hideTimer

  function toast() {
    var el = document.getElementById(TOAST_ID)
    if (el) return el
    el = document.createElement('div')
    el.id = TOAST_ID
    el.setAttribute('role', 'alert')
    el.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:99999;max-width:340px;padding:12px 16px;' +
      'border-radius:8px;font-size:14px;font-weight:500;line-height:1.4;box-shadow:0 4px 14px rgba(0,0,0,.18);display:none'
    document.body.appendChild(el)
    return el
  }

  function show(message) {
    var el = toast()
    var dark = document.documentElement.classList.contains('dark')
    el.style.background = dark ? '#3b1414' : '#fef3f2'
    el.style.color = dark ? '#fecdca' : '#b42318'
    el.style.border = '1px solid ' + (dark ? '#7a271a' : '#fecdca')
    el.textContent = message        // set as plain text, never as markup — it comes from a server response
    el.style.display = 'block'
    clearTimeout(hideTimer)
    hideTimer = setTimeout(function () { el.style.display = 'none' }, 5000)
  }

  function messageFor(xhr) {
    var text = (xhr.responseText || '').trim()
    // A short, tag-free body is a message written for people ("Enter a quantity
    // first."); anything else is an error page and would only confuse.
    if (text && text.length <= 200 && text.indexOf('<') === -1) return text
    if (xhr.status === 403) return 'Your session changed. Reload the page and try again.'
    if (xhr.status >= 500) return 'Something went wrong on the server. Reload the page to see the current state.'
    return 'That could not be saved. Reload the page and try again.'
  }

  function isRead(event) {
    var config = event.detail.requestConfig || {}
    return String(config.verb || '').toLowerCase() === 'get'
  }

  document.addEventListener('htmx:responseError', function (event) {
    if (!isRead(event)) show(messageFor(event.detail.xhr))
  })

  document.addEventListener('htmx:sendError', function (event) {
    if (!isRead(event)) show('Could not reach the server. Check the connection and try again.')
  })

  // Once the session has expired, an HTMX request is answered with a redirect
  // to the login page. The browser follows it, and HTMX would then swap that
  // whole page into a table cell — wiping the widget out and leaving a
  // half-broken page. Take the person to the real login page instead, and
  // bring them back to where they were afterwards.
  var LOGIN_PATH = /\/login\/?$/
  document.addEventListener('htmx:beforeSwap', function (event) {
    var xhr = event.detail.xhr
    if (!xhr || !xhr.responseURL) return
    var answeredBy = new URL(xhr.responseURL, window.location.href)
    if (LOGIN_PATH.test(answeredBy.pathname) && !LOGIN_PATH.test(window.location.pathname)) {
      event.detail.shouldSwap = false
      window.location.assign(answeredBy.pathname + '?next=' + encodeURIComponent(window.location.pathname + window.location.search))
    }
  })
})()
