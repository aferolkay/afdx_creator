# Vendored frontend libraries

These are committed to the repo deliberately: this machine has no Node/npm, and may be offline.
Nothing here is fetched at runtime — `index.html` loads these local files with plain `<script>` tags.

Fetched: 2026-08-08

| File | Package | Version | License | Source URL |
|---|---|---|---|---|
| `cytoscape.min.js` | cytoscape | 3.34.0 | MIT | https://unpkg.com/cytoscape@3.34.0/dist/cytoscape.min.js |
| `cytoscape-edgehandles.js` | cytoscape-edgehandles | 4.0.1 | MIT | https://unpkg.com/cytoscape-edgehandles@4.0.1/cytoscape-edgehandles.js |
| `lodash.min.js` | lodash | 4.17.21 | MIT | https://unpkg.com/lodash@4.17.21/lodash.min.js |
| `tabulator.min.js` | tabulator-tables | 6.5.2 | MIT | https://unpkg.com/tabulator-tables@6.5.2/dist/js/tabulator.min.js |
| `tabulator.min.css` | tabulator-tables | 6.5.2 | MIT | https://unpkg.com/tabulator-tables@6.5.2/dist/css/tabulator.min.css |

## Why lodash is here

`cytoscape-edgehandles` is a webpack UMD bundle with *external* dependencies. Its browser branch is:

```js
root["cytoscapeEdgehandles"] = factory(root["_"]["memoize"], root["_"]["throttle"]);
```

So it requires a global `_` exposing `memoize` and `throttle` to exist **before** it loads. Without
it you get `Cannot read properties of undefined (reading 'memoize')` at load time.

**Script load order in `index.html` therefore matters and must not be reordered:**

1. `lodash.min.js` (defines `window._`)
2. `cytoscape.min.js`
3. `cytoscape-edgehandles.js`
4. `tabulator.min.js`

## Upgrading

Re-download from the URL above, update the version/date in this table, and re-check that the
edgehandles UMD wrapper still expects the same globals (it has changed shape between major versions).
