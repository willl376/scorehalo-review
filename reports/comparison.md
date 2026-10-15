# ScoreHalo engine comparison

Generated: 2026-10-15 09:00:54

Engines: homr, audiveris

Pages: 4


## Per-page structure

| page | engine | ok | parts | measures | notes | pitched | secs |
|---|---|---|---|---|---|---|---|
| page-030 | homr | yes | 1 | 14 | 164 | 158 |  |
| page-030 | audiveris | yes | 2 | 11 | 155 | 144 |  |
| page-031 | homr | yes | 2 | 10 | 209 | 201 |  |
| page-031 | audiveris | yes | 2 | 10 | 209 | 206 |  |
| page-032 | homr | yes | 2 | 10 | 204 | 194 |  |
| page-032 | audiveris | yes | 2 | 10 | 188 | 185 |  |
| page-033 | homr | yes | 2 | 9 | 154 | 139 |  |
| page-033 | audiveris | yes | 2 | 12 | 188 | 175 |  |

## Cross-engine agreement

_pitch-class cosine_ and _signature Jaccard_ are 0..1 (1 = identical);
_measure/note ratio_ is min/max (1 = same count).

| page | homr vs audiveris |
|---|---|
| page-030 | pc=0.99 sig=0.62 m=0.79 n=0.91 |
| page-031 | pc=0.99 sig=0.72 m=1.00 n=0.98 |
| page-032 | pc=0.99 sig=0.64 m=1.00 n=0.95 |
| page-033 | pc=0.99 sig=0.56 m=0.75 n=0.79 |

## Aggregate

- **homr vs audiveris**: mean pitch-class cosine `0.993`, signature Jaccard `0.638`, measure ratio `0.884`, note ratio `0.909` over 4 page(s).

## Harmonic analysis (music21)

Each engine's output reduced to a key + a Roman-numeral histogram over its
chordified vertical sonorities (theory-aware, complements the metrics above).

| page | engine | key | conf | moments | consonance | top figures |
|---|---|---|---|---|---|---|
| page-030 | homr | A major | 0.804 | 97 | 0.722 | i:13, v:8, I6:8, i5:7 |
| page-030 | audiveris | A major | 0.901 | 83 | 0.753 | i:11, v:9, I:6, iii:5 |
| page-031 | homr | D major | 0.759 | 92 | 0.297 | V:10, I532:9, IV72:4, v:4 |
| page-031 | audiveris | A major | 0.874 | 92 | 0.188 | vi42:7, iii:6, iv6b432:5, I:4 |
| page-032 | homr | A major | 0.86 | 98 | 0.295 | IV:13, i:6, IV532:5, V:5 |
| page-032 | audiveris | A major | 0.892 | 97 | 0.232 | IV:12, vi42:6, III7#3:4, I:4 |
| page-033 | homr | D major | 0.754 | 81 | 0.284 | V:13, iii752:6, v:5, vi7:4 |
| page-033 | audiveris | D major | 0.808 | 99 | 0.491 | v:11, V:8, v5:6, #ivøb76b5b3b2:5 |

### Theory-aware agreement

| page | homr vs audiveris |
|---|---|
| page-030 | fig=0.89 key=yes con=0.97 mom=0.86 |
| page-031 | fig=0.17 key=no con=0.89 mom=1.00 |
| page-032 | fig=0.76 key=yes con=0.94 mom=0.99 |
| page-033 | fig=0.67 key=yes con=0.79 mom=0.82 |

## Reading this report

- Both engines emitting **valid** MusicXML does not mean they agree; the
  agreement block is the signal.
- High pitch-class cosine + high signature Jaccard => the engines heard the
  same music even if part/measure segmentation differed.
- Low signature Jaccard with high pitch-class cosine => same harmony, but
  different note durations/voicing -- proofread before trusting.

- _figure cosine_ / _key match_ / _consonance closeness_ are theory-aware
  (music21): the same harmony reduced to Roman numerals should look alike
  even when the two engines disagree on notation details.

