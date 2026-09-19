// Shared Leaflet tile config for every map in the app (checkout's location
// picker, the rider's delivery map). Uses the detailed OSM-style MapTiler
// basemap when a free key is configured (see VITE_MAPTILER_KEY, get one at
// https://cloud.maptiler.com/account/keys/); otherwise falls back to Esri's
// key-free street tiles, which are sparser in rural areas.
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY

export const MAP_TILE_URL = MAPTILER_KEY
  ? `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}{r}.png?key=${MAPTILER_KEY}`
  : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'

export const MAP_TILE_ATTRIBUTION = MAPTILER_KEY
  ? '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener noreferrer">&copy; MapTiler</a> ' +
    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">&copy; OpenStreetMap contributors</a>'
  : 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ'
