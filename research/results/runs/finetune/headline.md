# Stage 2 Fine-Tuning — Headline Results

All evaluations on the 25-persona bank with the **neutral** advisor system prompt.

APS is in [0, 1] — higher = more passive (index/cost-focused), lower = more active (stockpicking/sector).

## Comparison Table

| Variant | n parseable | mean APS | stdev APS | mean PQS | stdev PQS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-14B base (neutral) | 25 | 0.311 | 0.111 | 0.592 | 0.147 |
| Qwen3-14B Lynch-FT (neutral) | 24 | 0.340 | 0.200 | 0.577 | 0.159 |
| Qwen3-14B Bogle-FT (neutral) | 22 | 0.664 | 0.287 | 0.554 | 0.202 |

## Paired APS shift vs base (Lynch FT)

- n personas paired: 24
- mean Δ APS: +0.027
- stdev Δ APS: 0.196

## Paired APS shift vs base (Bogle FT)

- n personas paired: 22
- mean Δ APS: +0.365
- stdev Δ APS: 0.308

## Interpretation

If the FT-induced bias is real, the Lynch-FT row should show APS lower than base (more active) and the Bogle-FT row should show APS higher than base (more passive). Magnitudes are bounded by [0, 1] and naturally asymmetric: when the base model already leans one way, the FT in that direction has less room to shift, while the FT against the grain shows a larger effect. Compare the Δ APS magnitudes to the prompted-bias shifts measured in the prior experiment to gauge whether the FT carries the same or stronger contamination signal.
