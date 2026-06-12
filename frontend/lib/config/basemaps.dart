/// Selectable basemaps. The default (Voyager) is muted so the twisty-road
/// overlay pops; the others trade that for stronger road-vs-land contrast.
class Basemap {
  final String name;
  final String urlTemplate;
  final List<String> subdomains; // empty when the URL has no {s}
  final List<String> attributions;
  final int maxZoom;

  const Basemap(
    this.name,
    this.urlTemplate, {
    this.subdomains = const [],
    this.attributions = const [],
    this.maxZoom = 19,
  });
}

const kBasemaps = <Basemap>[
  Basemap(
    'Voyager',
    'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
    subdomains: ['a', 'b', 'c', 'd'],
    attributions: ['OpenStreetMap contributors', 'CARTO'],
    maxZoom: 20,
  ),
  Basemap(
    'OSM Standard',
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attributions: ['OpenStreetMap contributors'],
  ),
  // Esri tiles serve as .../{z}/{y}/{x} — note the y/x order.
  Basemap(
    'Topo',
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    attributions: ['Esri', 'OpenStreetMap contributors'],
  ),
  Basemap(
    'Streets',
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attributions: ['Esri'],
  ),
];
