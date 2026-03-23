# Search Results Page

URL pattern: `https://suchen.mobile.de/fahrzeuge/search.html?...`

## Page Layout

- **Header:** breadcrumb "Startseite > Meine Pkw-Suche > N Angebote"
- **Result count:** heading "N Angebote" (e.g. "20.002 Angebote")
- **Active filters:** tag chips below heading, each with `button[aria-label=Entfernen]` to remove
- **Left sidebar:** filter controls
- **Main area:** listing cards
- **Sorting:** dropdown near top of results ("Standard-Sortierung")

## Sidebar Filters

Each filter has a pattern: `span[aria-label="X ändern"]` to open/edit.

| Filter | aria-label pattern | Label ID |
|---|---|---|
| Condition | `Fahrzeugzustand ändern` | `id=condition-filter-label` |
| Make/Model | `Marke, Modell, Variante ändern` | `id=make-model-filter-label` — **use this to set model** (homepage model dropdown is unreliable) |
| Location | `Standort ändern` | `id=location-filter-label` |
| Fuel type | `Kraftstoffart ändern` | `id=fuel-type-filter-label` |
| Power | `Leistung ändern` | `id=power-filter-label` |
| Categories | `Fahrzeugtyp ändern` | `id=categories-filter-label` |
| EV filters | EV-specific | `id=ev-filter-label` |
| Transmission | `Getriebe ändern` | `id=transmission-filter-label` |

## Dialog Buttons Pattern

All filter dialogs (model, location, advanced) end with the same button pair:
- `<button>` with text "Abbrechen" (cancel)
- `<button>` with text "N\nAngebote" (apply — always the LAST `<button>` in the dialog)

To find the apply button index:
```bash
browser-use state 2>&1 | sed -n '/Abbrechen/,+3p'
# The <button> after "Abbrechen" is the apply button
```

## Setting Model (Workaround)

The homepage model dropdown is unreliable. Set the model from the results page instead:

1. Click `span[aria-label="Marke, Modell, Variante ändern"]` to open dialog
2. Dialog shows: Marke dropdown (`select[id=make-incl-0]`) and Modell dropdown (`select[id=model-incl-0]`)
3. Make should already be set. Use `browser-use select <model-idx> "GLC"` on the model dropdown
4. Find the apply button (see Dialog Buttons Pattern above)
5. Click the apply button

**Price filter:** two inputs with `aria-label=von` and `aria-label=bis` (from/to)
**Mileage filter:** two inputs with `aria-label=von` and `aria-label=bis`
**Search button in sidebar:** button with text "N Angebote"

## Color Filter (Außenfarbe)

Scroll down in the sidebar to find "Außenfarbe" section. Colors are `label[title=X]` elements:

Schwarz, Beige, Grau, Braun, Weiß, Orange, Blau, Gelb, Rot, Grün, Silber, Gold, Violett

Below the color labels, "Matt" and "Metallic" appear as finish sub-options (plain text, not `label[title=X]` elements).

Click a `label[title=X]` to toggle that color filter.

**Alternative:** Open "Weitere Filter" → click "Exterieur" tab → same color labels available.

## Weitere Filter (Advanced)

Button labeled "Weitere Filter" opens an expanded filter panel with tabs:

| Tab | Content |
|---|---|
| Basisdaten | Category (Limousine, Kombi, SUV...), seats, doors, payment |
| Technische Daten | Power, fuel, transmission, drivetrain, emissions |
| Exterieur | Außenfarbe (color), trailer coupling, parking assist |
| Innenausstattung | Interior color, material, features |
| Angebotsdaten | Dealer type, warranty, delivery |

Navigate tabs by finding `a[id=navLink-basicData]`, `a[id=navLink-technicalData]`, `a[id=navLink-exteriorFeatures]`, etc.

## Location Radius

To change the search radius:

1. Click `span[aria-label="Standort ändern"]`
2. A dialog appears with: Land (country), Ort/PLZ (city), Umkreis (radius)
3. Find the Umkreis input (labeled "Umkreis"), clear it, type new value: "200"
4. Click the search button in the dialog (button with text "N Angebote")

Default radius: 100 km. Options: 10, 20, 50, 100, 200, any.

## Listing Cards

Each listing is wrapped in an `<a>` tag (link). **Listings open in a new tab.**

Card content (as text in state output):
- Make + Model name
- Variant/trim description
- Price (e.g. "22.500 €")
- Monthly insurance (e.g. "Versicherung ab 11,36 € mtl.")
- Mileage (e.g. "97.000 km")
- Fuel type (e.g. "Benzin", "Diesel", "Elektro")
- Registration (e.g. "EZ 02/2017")
- Power (e.g. "180 kW (245 PS)")
- Dealer info
- `button[aria-label=Parken]` — bookmark/save listing
- `Kontakt` link — contact dealer

### Finding Listing Links

Listing `<a>` elements appear immediately before the car name and price text. The first listings appear after `div#saveSearchBarContainer`.

To find clickable listing links:
```bash
# Find <a> elements near prices (listings)
browser-use state 2>&1 | grep -n "€" | head -5          # get line numbers of prices
browser-use state 2>&1 | sed -n 'Np'                     # replace N with ~5 lines before the price line

# Or grep backwards from a price to find the parent <a>
browser-use state 2>&1 | grep -B5 "17.990 €" | grep "<a"
```

The `<a>` element index is what you click to open the listing. Scroll down first if listings aren't visible (`browser-use scroll down --amount 600`).

**To open a listing:** click the `<a>` element, then `browser-use switch 1` to view the new tab.

## Pagination

Results use infinite scroll — scroll down to load more listings.
