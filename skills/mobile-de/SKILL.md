---
name: mobile-de
description: >
  Navigate mobile.de car marketplace using browser-use CLI. Use when the user asks
  to search for cars, find vehicles, browse car listings, or interact with mobile.de.
  Covers the full lifecycle: search with filters (make, model, year, price, location,
  color), browse result listings, and extract details from individual car pages.
  Triggers on: mobile.de, car search, Fahrzeugsuche, find a car, Autokauf,
  vehicle search, Gebrauchtwagen, auto kaufen, Autos finden.
---

# mobile.de Car Search

Navigate mobile.de using browser-use CLI. Element indices change every page load — find elements by **stable identifiers** (id, aria-label, role) via `browser-use state`.

## Working with State Output

`browser-use state` output is typically 200-400 lines. Always pipe through grep to find elements:

```bash
browser-use state 2>&1 | grep "id=qs-select"       # find form fields by stable ID
browser-use state 2>&1 | grep "€"                    # find prices / listing cards
browser-use state 2>&1 | grep "button.*aria-label"    # find named buttons
browser-use state 2>&1 | grep -B3 "TARGET_TEXT"       # find parent elements (e.g. <a> wrapping a listing)
browser-use state 2>&1 | grep "Angebote" | tail -1    # find search/apply buttons
```

## Prerequisites

- browser-use CLI working (`browser-use doctor`)
- Use `--headed` — headless gets blocked by mobile.de
- If blocked ("Access denied"), use `--profile "Default"` for real Chrome with cookies

## Quick Search

```bash
browser-use --headed open https://www.mobile.de
browser-use state                              # check for consent dialog
# If dialog#mde-consent-modal-dialog present: click "Einverstanden" button
browser-use state                              # get search form
browser-use select <idx> "BMW"                 # id=qs-select-make
browser-use input <idx> "30000"                # id=qs-select-price-up-to
browser-use click <idx>                        # button with text "N Angebote"
# Then refine model on results page (see Known Issue below)
```

## Known Issue: Model Dropdown

The model dropdown (`id=qs-select-model`) on the homepage is a shadow DOM custom select.
`browser-use select` reports success but **does not reliably trigger the React state update**
— the model filter silently fails to apply.

**Workaround — set model from the results page:**
1. Search with make only (skip model on homepage)
2. On results page, click `span[aria-label="Marke, Modell, Variante ändern"]`
3. In the dialog, find `select[id=model-incl-0]` and use `browser-use select` on it
4. Click the dialog's apply button (button with the result count number)

**Alternative — use URL parameters directly:**
```bash
browser-use open "https://suchen.mobile.de/fahrzeuge/search.html?ms=3500%3B%3B21%3B&p=%3A30000&s=Car&vc=Car"
```

Common URL parameters:

| Param | Meaning | Example |
|-------|---------|---------|
| `ms=` | Make;Model;Variant (encoded IDs, `;` = `%3B`) | `ms=3500%3B%3B21%3B` = BMW 3er |
| `p=` | Price range (min:max) | `p=%3A30000` = up to 30k |
| `ml=` | Mileage range | `ml=%3A100000` = up to 100k km |
| `fr=` | Registration from year | `fr=2020%3A` = from 2020 |
| `s=Car` | Vehicle type | Always `Car` for cars |
| `vc=Car` | Vehicle class | Always `Car` for cars |

IDs are opaque and change — always discover them by doing a manual search, then copying the `ms=` value from the results page URL. Do not guess IDs.

## Consent Dialog

First visit without cookies shows a blocking consent dialog. Not shown if the browser daemon already visited mobile.de in this session (cookies persist across commands).

- **Detect:** `dialog` with `id=mde-consent-modal-dialog` in state
- **Dismiss:** click button with text "Einverstanden"
- **Skip:** not shown with `--profile` mode (existing cookies) or if daemon already has mobile.de cookies from a previous command

## Anti-Detection

mobile.de has aggressive bot detection. On "Access denied":
1. `browser-use close`
2. Retry: `browser-use --profile "Default" --headed open https://www.mobile.de`
3. Or: `browser-use --no-stealth --headed open https://www.mobile.de`

## Listing Navigation

Listings open in **new tabs**. After clicking a listing link:
- `browser-use switch 1` to view the detail page
- `browser-use close-tab` to return to results

## Page References

- **Search form:** [references/homepage.md](references/homepage.md) — filter IDs, location autocomplete
- **Results page:** [references/results.md](references/results.md) — sidebar filters, color, radius, listing cards
- **Detail page:** [references/listing.md](references/listing.md) — specs, gallery, dealer info
