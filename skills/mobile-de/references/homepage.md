# Homepage Search Form

URL: `https://www.mobile.de`

## Search Form Elements

Find elements by their stable `id` attribute using `browser-use state`, then use the element index.

| Field | Stable ID | Command | Notes |
|---|---|---|---|
| Make | `id=qs-select-make` | `select` | ~189 options. Use exact name: "BMW", "Mercedes-Benz", "Audi", "Tesla" |
| Model | `id=qs-select-model` | `select` | **UNRELIABLE** — appears after make selection but `select` command doesn't trigger React state. Set model on results page instead (see SKILL.md Known Issue). |
| Registration from | `id=qs-select-1st-registration-from` | `input` | Year: "2020", "2025" |
| Mileage up to | `id=qs-select-mileage-up-to` | `input` | Number without dots: "50000" |
| Price up to | `id=qs-select-price-up-to` | `input` | Number without dots: "30000" |
| Location | `id=geolocation-autosuggest` | `input` + `click` | See autocomplete workflow below |
| Payment: Buy | `button[value=purchase]` | `click` | "Kaufen" — selected by default |
| Payment: Lease | `button[value=leasing]` | `click` | "Leasen" |
| Electric only | `input[value=ELECTRICITY]` | `click` | Checkbox |
| Search button | text matching `Angebote` | `click` | Shows live result count |

## Vehicle Category Tabs

Above the search form. Default is Car.

| Tab | Stable ID |
|---|---|
| Car | `id=tab-Car` |
| Motorbike | `id=tab-Motorbike` |
| EBike | `id=tab-EBike` |
| Motorhome | `id=tab-Motorhome` |
| Truck | `id=tab-Truck` |

## Location Autocomplete Workflow

The location field has autocomplete that requires selecting from a dropdown:

1. `browser-use input <location-idx> "München"` — type the city name
2. Wait ~1 second for suggestions to load
3. `browser-use state` — look for `li[role=option]` elements inside `div#react-autowhatever-geolocation-autosuggest`
4. Suggestions look like: "München, Bayern", "München-Flughafen, Bayern", etc.
5. `browser-use click <first-option-idx>` — select the desired city

Default search radius after selecting a city: **100 km**. To change it, adjust on the results page (see results.md).

## AI Search (Beta)

There's also a text input for natural-language search (labeled "KI-Suche. Nur für Autos."). It accepts queries like "VW ID.4 bis 35.000 € und 50.000 km". Find it by looking for `input[type=text]` near the "Beta" label. The submit button is `button[aria-label=Suchen][type=submit]`.
