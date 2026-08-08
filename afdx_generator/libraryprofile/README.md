# The library profile — what it can and cannot absorb

The `afdx` OMNeT++ library this generator targets is unversioned and can change under you. This
directory exists so that when it does, you have one obvious place to look.

**But there is a real limit, and it matters:**

> `profile.py` isolates **renames**. It does not isolate **restructures**.

## Rename here (edit `profile.py`, change nothing else)

If the library renames a thing but keeps the same shape, it's a one-line edit here:

| Change in the library | Fix |
|---|---|
| `ethPortA` → `ethPort0` | `Gates.end_system_port_a` |
| `noOfPorts` → `portCount` | `ModuleParams.switch_port_count` |
| `BAG` → `bagInterval` | `MarshallParams.bag` |
| `afdx.EndSystem` → `afdx.ES` | `NedTypes.end_system` |
| route table uses `;` instead of `,` between ports | `RouteTableFormat.port_separator` |
| route tables named `.cfg` instead of `.txt` | `RouteTableFormat.file_suffix` |

## Restructure there (edit the Jinja templates in `../codegen/templates/`)

If the library changes *shape*, no amount of renaming helps — the generated code has to be built
differently, and that lives in the templates:

- **A third redundancy plane**, or dropping A/B redundancy. The two-plane mirroring is a structural
  assumption baked into `codegen/wiring.py` and `network.ned.j2`.
- **`ethPort[noOfPorts]` stopping being a gate vector** (e.g. becoming individually-named gates).
  The profile can rename the vector; it cannot turn one gate vector into many gates.
- **A new mandatory submodule** inside `EndSystem` or `Switch` that needs wiring or parameters.
- **The route-table format gaining real structure** — e.g. nested blocks or a per-VL priority
  column. `RouteTableFormat` describes a flat `key : {ports}` line; a different grammar needs
  `route_table.txt.j2` rewritten.
- **Frames being policed somewhere other than every switch port**, which would invalidate the
  `sigma` margin reasoning in `trafficmath/rho_sigma.py`.

## Things the library does *not* dictate (our conventions, safe to change)

These live in `profile.py` too, but they're ours, not the library's — the library only requires
that the `.ned` and the `.ini` agree with each other, and they do because both read these fields:

- `end_system_vector_name` (`ES`), `switch_plane_a_vector_name` (`SwitchA`), `..._b_...` (`SwitchB`)
- The mapping of a VL to its index in `messageSource[]` / `afdxMarshall[]`
  (defined once in `codegen/context.py` — ascending VL id among VLs sharing a source)

## Constants that cannot be read from the library at all

`phy_overhead_bits = 160` is hard-coded in the library's `TrafficPolicy.cc` as `20 * 8` with no NED
parameter exposing it. It is mirrored in `GeneralSettings.phy_overhead_bits` so it is visible and
editable in the UI. **If that C++ constant ever changes, nothing will tell you** — every `rho`/
`sigma` suggestion will simply be quietly wrong, and the symptom would be unexplained
`TOKEN_INSUFFICIENT` drops in the validation run.

## How to re-verify after a library upgrade

1. Skim `AFDX-master/afdx/src/*.ned` for the type, gate and parameter names in `profile.py`.
2. Re-read `TrafficPolicy.cc` for `phyOverhead_bit`.
3. Re-read `VLRouter.cc` for the route-table grammar (the comment/`:`/`{}`/`,` handling).
4. Run the test suite, then run a real validation generation — the end-to-end simulator run is the
   only check that catches semantic drift rather than merely syntactic drift.
