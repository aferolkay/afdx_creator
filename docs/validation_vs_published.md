# Validation against published results

The `realisticNetwork` project reproduces a published avionics message set (30 virtual links,
14 end systems, 5 switches). This records how the generated simulation compares with the
worst-case end-to-end delays published for that network — the strongest end-to-end evidence
that the generator produces a faithful model.

**Result: 28 of 30 links fall within the published analytical bound**, at
0.69–1.02x of it (median 0.84x). A simulated
maximum sitting somewhat below a worst-case bound is exactly the expected relationship.

## Settings used

Taken from the source, not from this tool's defaults:

| Setting | Value |
|---|---|
| Technological delay, end system | 40 us (tx and rx) |
| Technological delay, switch | 140 us |
| Frame overhead | payload + 55 B (47 B AFDX header + 8 B preamble/SFD) |
| Link rate | 100 Mbps |
| Simulated duration | 20 s |

## Methodology notes

- **Logger paths are excluded.** End system E9 is a data logger receiving 24 of the 30 links. The
  source states logger-bound traffic is not system-critical and excludes those paths from its
  delay evaluation; this comparison does the same. Including them changes the picture completely —
  E9's port carries ~40% utilisation and dominates every worst case.
- **Multicast links are compared at their non-logger destination**, which is the one the source
  reports.
- **Offsets are all zero here.** The source literature is about offset scheduling, so its published
  averages likely assume a specific offset assignment. This is the most likely reason the means
  here run uniformly lower (~0.68x) while the maxima line up well.

## Per-link comparison (microseconds)

| VL | Dest | Pattern | My mean | My max | Pub. sim avg | Pub. sim max | Pub. bound | max ratio | Within bound |
|---|---|---|---|---|---|---|---|---|---|
| 0x1 | E2 | sporadic | 400.4 | 620.2 | 675 | 797 | 798 | 0.78 | yes |
| 0x2 | E3 | sporadic | 409.5 | 698.1 | 684 | 797 | 798 | 0.88 | yes |
| 0x3 | E3 | sporadic | 402.0 | 640.7 | 676 | 797 | 798 | 0.80 | yes |
| 0x4 | E2 | sporadic | 406.8 | 700.1 | 680 | 797 | 798 | 0.88 | yes |
| 0x5 | E8 | sporadic | 434.7 | 743.6 | 785 | 861 | 861 | 0.86 | yes |
| 0x6 | E8 | sporadic | 433.6 | 752.7 | 786 | 861 | 861 | 0.87 | yes |
| 0x7 | E2 | sporadic | 502.0 | 713.6 | 721 | 998 | 998 | 0.71 | yes |
| 0x8 | E3 | sporadic | 503.9 | 712.9 | 735 | 998 | 998 | 0.71 | yes |
| 0x9 | E4 | periodic | 237.1 | 424.6 | 455 | 477 | 477 | 0.89 | yes |
| 0xA | E5 | periodic | 237.6 | 453.3 | 455 | 477 | 477 | 0.95 | yes |
| 0xB | E12 | periodic | 469.5 | 566.2 | 565 | 818 | 819 | 0.69 | yes |
| 0xC | E13 | periodic | 469.6 | 566.1 | 587 | 818 | 819 | 0.69 | yes |
| 0xD | E13 | periodic | 1123.5 | 1369.5 | 1287 | 1658 | 1658 | 0.83 | yes |
| 0xE | E12 | periodic | 1123.2 | 1334.0 | 1269 | 1658 | 1658 | 0.80 | yes |
| 0x10 | E2 | sporadic | 999.4 | 1203.8 | 1238 | 1448 | 1449 | 0.83 | yes |
| 0x11 | E3 | sporadic | 999.6 | 1219.1 | 1240 | 1448 | 1449 | 0.84 | yes |
| 0x12 | E2 | sporadic | 999.5 | 1284.5 | 1232 | 1448 | 1449 | 0.89 | yes |
| 0x13 | E3 | sporadic | 999.6 | 1245.8 | 1235 | 1448 | 1449 | 0.86 | yes |
| 0x14 | E2 | periodic | 573.8 | 919.3 | 929 | 1215 | 1222 | 0.76 | yes |
| 0x15 | E3 | periodic | 577.4 | 931.9 | 927 | 1215 | 1222 | 0.77 | yes |
| 0x16 | E3 | periodic | 560.0 | 885.7 | 918 | 1215 | 1222 | 0.73 | yes |
| 0x17 | E2 | periodic | 579.9 | 936.0 | 922 | 1215 | 1222 | 0.77 | yes |
| 0x18 | E0 | periodic | 604.8 | 900.5 | 883 | 1149 | 1149 | 0.78 | yes |
| 0x19 | E1 | periodic | 605.6 | 875.8 | 908 | 1149 | 1149 | 0.76 | yes |
| 0x20 | E0 | sporadic | 444.7 | 640.9 | 661 | 651 | 652 | 0.98 | yes |
| 0x21 | E0 | sporadic | 444.4 | 596.4 | 651 | 651 | 652 | 0.92 | yes |
| 0x22 | E0 | sporadic | 444.8 | 663.3 | 647 | 651 | 652 | 1.02 | **no** |
| 0x30 | E1 | sporadic | 444.5 | 614.4 | 660 | 651 | 652 | 0.94 | yes |
| 0x31 | E1 | sporadic | 444.7 | 619.5 | 649 | 651 | 652 | 0.95 | yes |
| 0x32 | E1 | sporadic | 445.0 | 663.3 | 647 | 651 | 652 | 1.02 | **no** |

## The two links that exceed

`0x22` and `0x32` land ~1.7% above the bound. Both are video links specified as **sporadic**
(gap drawn from 1.6–5 ms), whereas the published analysis assumes **strictly periodic** sources —
its own future-work section names sporadic traffic as an open extension. Three sporadic streams
sharing an output port can align in ways a periodic analysis does not model, so a small overshoot
on exactly those links is expected rather than a discrepancy.

## Reproducing this

Open the `realisticNetwork` project and press **Generate & Validate**, then run for longer to
gather statistics:

```sh
cd output/realisticNetwork
<simulator> -n .:<afdx>/src:<queueinglib> -u Cmdenv -c realisticNetwork -r 0 \
    --sim-time-limit=20s realisticNetwork.ini
```

Delay vectors are recorded per virtual link (`E2ELatency_VL*`) and per receiving end system
(`LatencyAt#ES*_VL*`); the per-receiver ones are what this comparison uses.
