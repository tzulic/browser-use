# Listing Detail Page

URL pattern: `https://suchen.mobile.de/fahrzeuge/details.html?id=...`

## Navigation

- Listings open in a **new tab** from search results
- `browser-use switch 1` to view detail tab after clicking a listing
- `a[aria-label="Zurück zu den Suchergebnissen"]` link at top to go back
- `browser-use close-tab` to close and return to results tab

## Image Gallery

Inside an `<article>` element at the top:

- Images: `img[alt="Make Model"]` (e.g. `img[alt="BMW 325"]`)
- Previous: `button[aria-label=Zurück]`
- Next: `button[aria-label=Nächste]`
- Thumbnails: `button[aria-label="Nächste N"]` for image N
- View all: `button[aria-label="Alle Bilder"]`
- Zoom: `button[aria-label="Vergrößern"]`
- Image count shown as plain text (e.g. "20")

## Key Specs (Top Section)

Displayed as icon + text pairs near the top. Read from `browser-use state` output:

| Spec | Example | German label |
|---|---|---|
| Mileage | 97.000 km | Kilometerstand |
| Power | 126 kW (171 PS) | Leistung |
| Fuel | Benzin | Kraftstoffart |
| Transmission | Automatik | Getriebe |
| Registration | 11/1986 | Erstzulassung |
| Owners | 2 | Fahrzeughalter |

## Technical Data Table

Below the key specs, a detailed table of key-value pairs. In `browser-use state` output these appear as consecutive lines — label on one line, value on the next:

```
Fahrzeugzustand
Gebrauchtfahrzeug
Kategorie
Limousine
Herkunft
Deutsche Ausführung
Kilometerstand
97.000 km
Hubraum
2.476 cm³
Leistung
126 kW (171 PS)
Antriebsart
Verbrennungsmotor
Kraftstoffart
Benzin
Anzahl Sitzplätze
5
Anzahl der Türen
4/5
Getriebe
Automatik
Schadstoffklasse
Euro2
```

For electric vehicles, additional fields: Batteriekapazität, Reichweite, Ladedauer.

## Color & Interior

Below technical data:
- **Farbe:** exterior color (e.g. "Grau", "Schwarz")
- **Innenausstattung:** interior material/color

## Equipment (Ausstattung)

Feature list as text items (ABS, Klimaanlage, Navigationssystem, etc.)

## Price

Prominent price display: e.g. "22.500 €"

May include:
- Monthly estimate (e.g. "235 € mtl.")
- "Ohne Bewertung" / price rating badge
- `span[aria-label="Ohne Bewertung"]` or similar rating element

## Dealer/Seller Info

- Dealer name and rating (stars)
- Location
- `Kontakt` button — contact dealer
- `Parken` button (`button[aria-label=Parken]`) — save/bookmark

## Extracting Data

Use `browser-use state` to get the full page text. The detail page is mostly plain text — parse key-value patterns (label line followed by value line) from the state output. For specific elements, use `browser-use get text <idx>`.
