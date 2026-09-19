// Interactive Leaflet map for TownZone's "Map Center" admin fields.
// Injects a map above the center_latitude/center_longitude inputs — click
// (or drag the marker) to set the coordinates instead of typing them by hand.

// document.currentScript is only valid while this file is first executing —
// have to grab the MapTiler key + auto-save URL (passed as query params on
// this very <script src>, see TownZoneAdminForm.media) up here, not inside
// the DOMContentLoaded callback below.
var MAPTILER_KEY, SAVE_URL
;(function () {
  try {
    var src = document.currentScript && document.currentScript.src
    if (!src) return
    var params = new URL(src).searchParams
    MAPTILER_KEY = params.get('maptiler_key') || ''
    SAVE_URL = params.get('save_url') || ''
  } catch (e) {
    MAPTILER_KEY = ''
    SAVE_URL = ''
  }
})()

function getCsrfToken() {
  var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

document.addEventListener('DOMContentLoaded', function () {
  var latInput = document.getElementById('id_center_latitude')
  var lngInput = document.getElementById('id_center_longitude')
  if (!latInput || !lngInput || typeof L === 'undefined') return

  var formRows = latInput.closest('.form-rows') || latInput.closest('fieldset')
  if (!formRows || !formRows.parentNode) return

  // Garcia Hernandez, Bohol — approximate town center, used when a zone
  // doesn't have coordinates set yet.
  var DEFAULT_CENTER = [9.9096, 124.2823]
  var DEFAULT_ZOOM = 13

  var wrap = document.createElement('div')
  wrap.style.marginBottom = '16px'
  wrap.innerHTML =
    '<div id="townzone-map" style="height:340px;border-radius:8px;overflow:hidden;border:1px solid #e5e5e5;"></div>' +
    '<p style="font-size:12px;color:#8a8a8a;margin-top:6px;">' +
    'Click the map (or drag the pin) to set the zone center — the fields below update automatically.</p>' +
    '<p id="townzone-save-status" style="font-size:12px;margin-top:2px;min-height:15px;"></p>'
  formRows.parentNode.insertBefore(wrap, formRows)
  var saveStatus = wrap.querySelector('#townzone-save-status')

  var startLat  = parseFloat(latInput.value)
  var startLng  = parseFloat(lngInput.value)
  var hasPoint  = !isNaN(startLat) && !isNaN(startLng)
  var center    = hasPoint ? [startLat, startLng] : DEFAULT_CENTER

  var map = L.map('townzone-map').setView(center, hasPoint ? 15 : DEFAULT_ZOOM)

  // Detailed OSM-style basemap when a free MapTiler key is configured
  // (see MAPTILER_KEY in settings.py); otherwise fall back to Esri's
  // key-free street tiles, which are sparser in rural areas.
  if (MAPTILER_KEY) {
    L.tileLayer('https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}{r}.png?key=' + MAPTILER_KEY, {
      attribution: '<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a> ' +
        '<a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>',
      maxZoom: 20,
      detectRetina: true,
    }).addTo(map)
  } else {
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ',
      maxZoom: 19,
    }).addTo(map)
  }

  var marker = L.marker(center, { draggable: true })
  if (hasPoint) marker.addTo(map)

  // Auto-saves straight to the TownZone row (change form only — see
  // TownZoneAdminForm.media) so pinning a zone center doesn't need the
  // admin to also click the page's own Save button.
  function autoSaveCenter(lat, lng) {
    if (!SAVE_URL || !saveStatus) return
    saveStatus.style.color = '#8a8a8a'
    saveStatus.textContent = 'Saving...'
    fetch(SAVE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': getCsrfToken(),
      },
      body: 'lat=' + encodeURIComponent(lat) + '&lng=' + encodeURIComponent(lng),
    })
      .then(function (res) {
        saveStatus.style.color = res.ok ? '#3a8f5a' : '#c0392b'
        saveStatus.textContent = res.ok ? '✓ Center saved' : 'Could not save — try again'
      })
      .catch(function () {
        saveStatus.style.color = '#c0392b'
        saveStatus.textContent = 'Could not save — check your connection'
      })
  }

  function setPoint(lat, lng, panTo) {
    latInput.value = lat.toFixed(7)
    lngInput.value = lng.toFixed(7)
    marker.setLatLng([lat, lng])
    if (!map.hasLayer(marker)) marker.addTo(map)
    if (panTo) map.panTo([lat, lng])
    autoSaveCenter(lat, lng)
  }

  map.on('click', function (e) {
    setPoint(e.latlng.lat, e.latlng.lng, false)
  })

  marker.on('dragend', function () {
    var pos = marker.getLatLng()
    setPoint(pos.lat, pos.lng, false)
  })

  // Typing coordinates by hand still works and keeps the marker in sync.
  function syncFromInputs() {
    var lat = parseFloat(latInput.value)
    var lng = parseFloat(lngInput.value)
    if (!isNaN(lat) && !isNaN(lng)) setPoint(lat, lng, true)
  }
  latInput.addEventListener('change', syncFromInputs)
  lngInput.addEventListener('change', syncFromInputs)

  // Guard against 0-height rendering if the fieldset was briefly hidden
  // (e.g. tabbed layout) when the map first initialized.
  setTimeout(function () { map.invalidateSize() }, 200)
})
