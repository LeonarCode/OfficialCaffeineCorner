import React, { useState, useCallback, useEffect } from 'react'
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MAP_TILE_URL, MAP_TILE_ATTRIBUTION } from '../utils/mapTiles'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const DEFAULT_CENTER = [9.7378, 124.1494]

const ClickHandler = ({ onSelect }) => {
  useMapEvents({
    click(e) {
      onSelect([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}

const RecenterOnLocate = ({ position }) => {
  const map = useMap()
  useEffect(() => {
    if (position) map.setView(position, 16)
  }, [position])
  return null
}

const RecenterOnZone = ({ zoneCenter }) => {
  const map = useMap()
  useEffect(() => {
    if (zoneCenter) {
      map.flyTo(zoneCenter, 14, { duration: 1 })
    }
  }, [zoneCenter])
  return null
}

// Reverse-geocode via OSM Nominatim (same provider as the tile layer below —
// free, no API key). Picks the closest thing to a PH "barangay" out of
// whatever address parts Nominatim returns for that spot.
const reverseGeocode = async ([lat, lng]) => {
  const res = await fetch(
    `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`,
    { headers: { 'Accept-Language': 'en' } }
  )
  if (!res.ok) throw new Error('Reverse geocoding failed')
  const data = await res.json()
  const addr = data.address || {}
  const barangay = addr.village || addr.suburb || addr.neighbourhood || addr.quarter || addr.city_district || addr.hamlet || ''
  const municipality = addr.town || addr.municipality || addr.city || ''
  return [barangay, municipality, 'Bohol'].filter(Boolean).join(', ')
}

const LocationPicker = ({ value, onChange, zone, onAddressDetected }) => {
  const [position, setPosition] = useState(value || null)
  const [locating, setLocating] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [detectedAddress, setDetectedAddress] = useState('')
  const [error, setError] = useState('')

  const zoneCenter = zone?.center_latitude && zone?.center_longitude
    ? [parseFloat(zone.center_latitude), parseFloat(zone.center_longitude)]
    : null

  // I-reset ang pin kapag nagpalit ng zone — mas automatic, iniiwasan ang wrong-zone pins
  useEffect(() => {
    if (zone) {
      setPosition(null)
      onChange(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zone?.id])

  const handleSelect = useCallback((latlng) => {
    setPosition(latlng)
    onChange(latlng)

    // Auto-detect the barangay for this pin and hand it up to the form.
    setDetecting(true)
    setDetectedAddress('')
    reverseGeocode(latlng)
      .then(guess => {
        setDetectedAddress(guess)
        if (guess) onAddressDetected?.(guess)
      })
      .catch(() => {
        // Hindi kritikal — manual pa rin pwede mag-type ng address.
      })
      .finally(() => setDetecting(false))
  }, [onChange, onAddressDetected])

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      setError('Geolocation is not supported by your browser.')
      return
    }
    setLocating(true)
    setError('')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const coords = [pos.coords.latitude, pos.coords.longitude]
        handleSelect(coords)
        setLocating(false)
      },
      () => {
        setError('Unable to get your location. Please pin it manually on the map.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 8000 }
    )
  }

  return (
    <div className='flex flex-col gap-2'>
      <div className='flex items-center justify-between'>
        <p className='text-[#2C1503] text-xs font-semibold uppercase tracking-wide'>
          Pin Your Location <span className='text-red-400'>*</span>
        </p>
        <button
          type='button'
          onClick={handleUseMyLocation}
          disabled={locating}
          className='flex items-center gap-1 text-[#6f4e37] text-xs font-semibold hover:underline disabled:opacity-50'
        >
          {locating ? 'Locating...' : 'Use My Location'}
        </button>
      </div>

      <div className='rounded-xl overflow-hidden border border-gray-200' style={{ height: '260px' }}>
        <MapContainer
          center={position || zoneCenter || DEFAULT_CENTER}
          zoom={position ? 16 : zoneCenter ? 14 : 13}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer url={MAP_TILE_URL} attribution={MAP_TILE_ATTRIBUTION} />
          <ClickHandler onSelect={handleSelect} />
          {position && <Marker position={position} />}
          {position && <RecenterOnLocate position={position} />}
          {!position && zoneCenter && <RecenterOnZone zoneCenter={zoneCenter} />}
        </MapContainer>
      </div>

      {error && <p className='text-red-400 text-xs'>{error}</p>}

      {position ? (
        <div className='flex flex-col gap-0.5'>
          <p className='text-gray-400 text-xs'>
            Pinned at {position[0].toFixed(5)}, {position[1].toFixed(5)}
          </p>
          {detecting ? (
            <p className='text-[#6f4e37] text-xs'>Detecting barangay...</p>
          ) : detectedAddress ? (
            <p className='text-[#6f4e37] text-xs'>
              📍 Detected: <span className='font-semibold'>{detectedAddress}</span> — auto-filled below, feel free to edit.
            </p>
          ) : null}
        </div>
      ) : zoneCenter ? (
        <p className='text-gray-400 text-xs'>
          Showing {zone.name} area. Tap on the map to drop your exact pin.
        </p>
      ) : (
        <p className='text-gray-400 text-xs'>Tap on the map to drop a pin at your delivery location.</p>
      )}
    </div>
  )
}

export default LocationPicker