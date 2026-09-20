// Keeps Django's CSRF token fresh on every admin POST — plain forms and HTMX.
//
// Django rotates the csrftoken cookie on every login. A page that was already
// open when that happened (another tab, or the browser's Back button after a
// login) still holds the *old* token in its hidden form field, so saving it
// failed with "403 CSRF token from POST incorrect" — even though the browser
// is logged in and holds a perfectly good new cookie. Reading the token from
// the cookie at submit time, instead of trusting whatever the page rendered,
// makes those stale pages work again.
//
// Unfold already ships HTMX on every admin page (unfold/js/htmx/htmx.js), and
// HTMX requests bypass the {% csrf_token %} field, so they need the token
// attached too. Standard pattern, see:
// https://docs.djangoproject.com/en/stable/howto/csrf/#using-csrf-protection-with-ajax
//
// The listeners are on `document`, not `document.body` — this script is
// loaded in <head> (see UNFOLD["SCRIPTS"]), which runs before <body> exists
// yet, so `document.body` is still null at this point. Both events bubble
// (submit is caught in the capture phase) all the way up to `document`.
//
// Guarded by tests/test_online_shop/test_admin_scripts.py (AdminLoginAndCsrfTests,
// CsrfScriptGuardTests) and, in a real browser, by
// tests/test_online_shop/test_stale_csrf_browser.py — if you touch this file,
// run those.
(function () {
  function csrfCookie() {
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)
    return match ? decodeURIComponent(match[1]) : null
  }

  function refreshTokens(form) {
    var token = csrfCookie()
    if (!token || !form || !form.querySelectorAll) return
    var fields = form.querySelectorAll('input[name="csrfmiddlewaretoken"]')
    for (var i = 0; i < fields.length; i++) fields[i].value = token
  }

  document.addEventListener('htmx:configRequest', function (event) {
    var token = csrfCookie()
    if (!token) return
    event.detail.headers['X-CSRFToken'] = token
    // HTMX also folds in every named field of the enclosing form — on the
    // Orders list that includes the changelist form's own csrfmiddlewaretoken,
    // and Django checks that POST field *before* the header, so a stale one
    // would sink the request no matter what the header says. Overwrite it
    // with the fresh value. (Never on GET: it would end up in the URL.)
    if (event.detail.verb !== 'get') event.detail.parameters['csrfmiddlewaretoken'] = token
  })

  // Clicking a submit button / pressing Enter fires a `submit` event…
  document.addEventListener('submit', function (event) { refreshTokens(event.target) }, true)

  // …but form.submit() called from a script does not, so wrap that too —
  // otherwise any code (ours, or a future Unfold upgrade) that submits a form
  // that way would bring the stale-token 403 right back.
  var nativeSubmit = HTMLFormElement.prototype.submit
  HTMLFormElement.prototype.submit = function () {
    refreshTokens(this)
    return nativeSubmit.apply(this, arguments)
  }
})()
