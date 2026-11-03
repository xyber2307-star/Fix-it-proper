# Fix It Proper scoring

How issues are ranked and how the optional score is computed. The code
lives in `backend/app/analyzers/scoring.py`; this doc mirrors it.

## Ranking

Issues from the SEO analyzer, the PageSpeed analyzer, and the
YouTube analyzer are merged into one list. When two issues share a
rule id, the first one wins: SEO issues come first, then PageSpeed,
then YouTube. Video pages run the YouTube checklist only; the web
analyzers are skipped for them.

Each issue gets a rank score:

```
rank_score = severity_weight * confidence
```

Severity weights: high 3, medium 2, low 1. Confidence comes from the
analyzer that raised the issue and ranges from 0 to 1.

Higher rank_score ranks first. Ties break in this order:

1. Ease of fix, easier first (see table below, 1 is quickest).
2. Rule id, alphabetical, so the output is deterministic.

The first issue gets impact_rank 1, the next 2, and so on.

Example: a medium issue with confidence 1.0 scores 2.0 and
outranks a high issue with confidence 0.5 at 1.5. Exact float
comparison decides; nothing is rounded before sorting.

## Rule table

Ease scale: 1 is quick (add or remove a tag), 2 is moderate (write
copy, edit many tags), 3 is involved (infrastructure or schema work).

| Rule id | Severity | Ease |
| --- | --- | --- |
| seo-title-missing | high | 1 |
| seo-title-empty | high | 1 |
| seo-title-length | low | 2 |
| seo-title-duplicate-h1 | low | 2 |
| seo-meta-description-missing | high | 2 |
| seo-meta-description-length | medium | 2 |
| seo-h1-missing | high | 2 |
| seo-h1-multiple | medium | 1 |
| seo-heading-order | low | 2 |
| seo-canonical-missing | medium | 1 |
| seo-canonical-host | medium | 1 |
| seo-robots-noindex | high | 1 |
| seo-img-alt | medium | 2 |
| seo-img-dimensions | low | 2 |
| seo-og-title | medium | 1 |
| seo-og-description | medium | 2 |
| seo-og-image | medium | 1 |
| seo-twitter-card | low | 1 |
| seo-viewport | high | 1 |
| seo-lang | low | 1 |
| seo-link-empty-text | low | 2 |
| seo-link-bad-href | medium | 2 |
| seo-structured-data-missing | medium | 3 |
| seo-jsonld-invalid | medium | 2 |
| seo-robots-txt | low | 2 |
| seo-sitemap | low | 2 |
| seo-https | high | 3 |
| seo-mixed-content | medium | 2 |
| pagespeed-lcp | high/medium | 3 |
| pagespeed-cls | high/medium | 2 |
| pagespeed-responsiveness | high/medium | 3 |
| pagespeed-byte-weight | high/medium | 3 |
| pagespeed-audit-* | high/medium | 2 |
| youtube-title-missing | high | 1 |
| youtube-title-empty | high | 2 |
| youtube-title-length | low | 2 |
| youtube-description-missing | medium | 2 |
| youtube-description-hook | low | 2 |
| youtube-cta-missing | low | 1 |
| youtube-links-missing | low | 1 |
| youtube-chapters-missing | low | 2 |
| youtube-thumbnail-missing | medium | 1 |
| youtube-captions-missing | low | 2 |

PageSpeed severities come from the audit score: below 0.5 is high,
below 0.9 is medium, the rest pass. PageSpeed audit ids vary per
report, so they share the default ease of 2. Any unknown rule id
also uses ease 2.

## Score

The score is optional and secondary to the ranked list. It starts at
100 and subtracts a fixed penalty per issue by severity:

```
value = max(0, 100 - (10 * highs + 5 * mediums + 2 * lows))
```

The score is null unless data_quality is "full". YouTube issues
use the same penalties. Video pages report "full" unless the
transcript could not be verified, which drops them to "partial".

The response carries formula_version "v1.0" and three components so
the UI can replay the math exactly:

- high_issues: value is total high deduction, weight is 0.10
- medium_issues: value is total medium deduction, weight is 0.05
- low_issues: value is total low deduction, weight is 0.02

Per-issue penalty equals weight times 100. Score equals 100 minus the
sum of component values, floored at 0.

Example: 2 high, 1 medium, 1 low gives deductions 20, 5, and 2, so
the score is 100 - 27 = 73.

## Limitations

The report lists a limitation string for each gap: PageSpeed
limitations pass through unchanged, and unverified crawl files add
"robots.txt status could not be verified." and "sitemap.xml status
could not be verified." as needed. Every YouTube report adds
"YouTube results are checklist based and not a performance
forecast.", plus "Transcript availability could not be verified."
when the transcript fetch fails.
