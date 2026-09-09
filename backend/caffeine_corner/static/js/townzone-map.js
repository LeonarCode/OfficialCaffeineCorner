// Interactive Leaflet map for TownZone's "Map Center" admin fields.
// Injects a map above the center_latitude/center_longitude inputs — click
// (or drag the marker) to set the coordinates instead of typing them by hand.
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
    'Click the map (or drag the pin) to set the zone center — the fields below update automatically.</p>'
  formRows.parentNode.insertBefore(wrap, formRows)

  var startLat  = parseFloat(latInput.value)
  var startLng  = parseFloat(lngInput.value)
  var hasPoint  = !isNaN(startLat) && !isNaN(startLng)
  var center    = hasPoint ? [startLat, startLng] : DEFAULT_CENTER

  var map = L.map('townzone-map').setView(center, hasPoint ? 15 : DEFAULT_ZOOM)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map)

  var marker = L.marker(center, { draggable: true })
  if (hasPoint) marker.addTo(map)

  function setPoint(lat, lng, panTo) {
    latInput.value = lat.toFixed(7)
    lngInput.value = lng.toFixed(7)
    marker.setLatLng([lat, lng])
    if (!map.hasLayer(marker)) marker.addTo(map)
    if (panTo) map.panTo([lat, lng])
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
