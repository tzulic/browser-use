# mobile.de Navigation Skill

**Date**: 2026-03-23
**Status**: Approved
**Scope**: Companion skill to browser-use CLI that maps mobile.de's page structure for efficient car search

## Problem

Agents using browser-use CLI on mobile.de waste time rediscovering the page structure — element IDs, filter locations, consent handling, listing navigation patterns. Each session starts from scratch with trial-and-error.

## Solution

A pure-reference skill (no scripts) that documents mobile.de's stable element identifiers, page layouts, and step-by-step workflows. The agent reads the reference material and uses browser-use CLI commands against known patterns.

## Structure

```
mobile-de/
├── SKILL.md
└── references/
    ├── homepage.md
    ├── results.md
    └── listing.md
```

## SKILL.md Content

### Frontmatter

```yaml
name: mobile-de
description: >
  Navigate mobile.de car marketplace using browser-use CLI. Use when the user asks
  to search for cars, find vehicles, browse car listings, or interact with mobile.de.
  Covers the full lifecycle: search with filters (make, model, year, price, location,
  color), browse result listings, and extract details from individual car pages.
  Triggers on: mobile.de, car search, Fahrzeugsuche, find a car, Autokauf,
  vehicle search, Gebrauchtwagen.
```

### Body

Quick-start workflow (5 commands), consent handling, anti-detection notes, and pointers to the three reference files for each page type.

**Key content:**

1. **Prerequisites**: browser-use CLI installed, `--headed` recommended (headless can get blocked)
2. **Consent handling**: check for `dialog#mde-consent-modal-dialog`, click button containing "Einverstanden"
3. **Anti-detection notes**: stealth mode may get blocked on mobile.de (their detection is aggressive). If "Access denied" appears, retry with `--no-stealth --headed` or use `--profile` with a real Chrome profile.
4. **Quick search workflow**:
   - `browser-use --headed open https://www.mobile.de`
   - `browser-use state` → check for consent dialog
   - `browser-use select <make-idx> "BMW"` (find via `id=qs-select-make`)
   - Set other filters by their stable IDs
   - Click search button (find by text matching `Angebote`)
5. **Reference pointers**: homepage.md for search form, results.md for results page, listing.md for detail pages

## references/homepage.md Content

The search form element map:

| Field | Stable identifier | Command | Notes |
|---|---|---|---|
| Make | `id=qs-select-make` | `select` | 189 options, use `select` command with exact make name |
| Model | `id=qs-select-model` | `select` | Appears after make selection, options depend on make |
| First registration | `id=qs-select-1st-registration-from` | `input` | Year, e.g. "2020" |
| Mileage | `id=qs-select-mileage-up-to` | `input` | Number, e.g. "50000" |
| Price | `id=qs-select-price-up-to` | `input` | Number, e.g. "30000" |
| Location | `id=geolocation-autosuggest` | `input` then `click` | Type city, wait for autocomplete `li[role=option]` suggestions, click first match |
| Payment type | `button[value=purchase]` / `button[value=leasing]` | `click` | Kaufen or Leasen |
| Electric only | `input[value=ELECTRICITY]` | `click` | Checkbox |
| Search button | text matching `/^\d.*Angebote$/` | `click` | Shows result count |
| Vehicle tabs | `button[id=tab-Car]`, `tab-Motorbike`, `tab-EBike`, `tab-Motorhome`, `tab-Truck` | `click` | Vehicle category |

**Location autocomplete workflow:**
1. `browser-use input <idx> "München"`
2. Wait 1s for suggestions to appear
3. `browser-use state` → find `li[role=option]` elements under `div#react-autowhatever-geolocation-autosuggest`
4. `browser-use click <first-option-idx>` to select "München, Bayern"

**Consent dialog:**
- Check: look for `dialog#mde-consent-modal-dialog` in state output
- Dismiss: find button with text "Einverstanden", click it
- Note: does not appear if cookies are preserved (e.g., `--profile` mode)

## references/results.md Content

**Page structure:**
- Breadcrumb: "Startseite > Meine Pkw-Suche > N Angebote"
- Result count heading: "N Make Model Angebote"
- Active filter tags below heading with X buttons (`button[aria-label=Entfernen]`) to remove

**Sidebar filters** (left side):
- Each filter section has `span[aria-label="X ändern"]` to edit
- Key filters: Fahrzeugzustand, Marke/Modell/Variante, Zahlungsart, Preis, Erstzulassung, Kilometerstand, Standort, Kraftstoffart, Leistung, Fahrzeugtyp, Getriebe, Außenfarbe
- "Weitere Filter" button opens advanced filter panel with tabs: Basisdaten, Technische Daten, Exterieur, Innenausstattung, Angebotsdaten

**Color filter:**
- Location: under "Außenfarbe" in sidebar (scroll down), or under Exterieur tab in Weitere Filter
- Elements: `label[title=Schwarz]`, `label[title=Weiß]`, `label[title=Blau]`, etc.

**Location radius:**
- Click `span[aria-label="Standort ändern"]` to open dialog
- Dialog has: Land dropdown, Ort input, Umkreis input (default 100 km)
- Change Umkreis value and click search button in dialog

**Listing cards:**
- Each listing is an `<a>` element (anchor/link) — listings open in a **new tab**
- After clicking a listing, use `browser-use switch 1` (or higher tab index) to switch to the detail tab
- Card content: make/model name, price (€), mileage (km), fuel type, registration date, dealer info
- "Parken" button (`button[aria-label=Parken]`) to save/bookmark

**Pagination:** scroll down to load more results (infinite scroll pattern)

## references/listing.md Content

**Navigation:**
- Listings open in a new tab from search results
- "Zurück zu den Suchergebnissen" link (`a[aria-label="Zurück zu den Suchergebnissen"]`) at top
- Close tab with `browser-use close-tab` to return to results

**Image gallery:**
- `article` element containing images (`img[alt="Make Model"]`)
- Navigation: `button[aria-label=Zurück]` (prev), `button[aria-label=Nächste]` (next)
- Thumbnail buttons: `button[aria-label="Nächste N"]` for each image
- "Alle Bilder" button to view all, "Vergrößern" to zoom

**Key specs** (visible at top of page as icon+text pairs):
- Kilometerstand: e.g. "97.000 km"
- Leistung: e.g. "126 kW (171 PS)"
- Kraftstoffart: e.g. "Benzin"
- Getriebe: e.g. "Automatik"
- Erstzulassung: e.g. "11/1986"

**Technical data table** (structured key-value pairs):
- Fahrzeugzustand, Kategorie, Herkunft, Kilometerstand, Hubraum, Leistung, Antriebsart, Kraftstoffart, Sitzplätze, Türen, Getriebe, Schadstoffklasse

**Additional sections:**
- Farbe: exterior color (e.g. "Grau")
- Innenausstattung: interior material
- Ausstattung: feature list (ABS, etc.)
- Price: prominent, e.g. "22.500 €"
- Dealer/seller info: name, rating, location

**Extracting data:**
Use `browser-use get text <idx>` for specific elements, or `browser-use state` to get the full page text. The detail page is mostly plain text — specs can be extracted by parsing the state output for key-value patterns (label followed by value on next line).

## What the Skill Does NOT Include

- Scripts or automation code (pure reference)
- Hardcoded element indices (they change between page loads)
- Account/login workflows
- Saved search management
- Price alert setup
