# Superseded run: not the final run

This directory is the **first** final run on the declared 200,013-row scope, made on 2026-10-12/13 with GPT-6 Luna at
effort none, before the golden-50 labels existed. Its memo recommended billing/support.

The final run is [`runs/final-200k-v2`](../final-200k-v2/): the same scope and pipeline, with the enrichment setup the
golden-50 comparison chose (Luna effort low, `label_config` `cfg-52c5333247`). Its memo recommends usability. Why the
setup changed and why the two runs differ: the main [README](../../README.md) ("Models and provenance", "Results") and
[docs/model_choice.md](../../docs/model_choice.md).

This run is kept because its calls are billed project spend ($2.019246, `cost/project_spend.json`) and its evidence
(grading export, checks, recordings, verifier analysis in
[`evals/verification/disagreement_analysis_superseded_effort_none.md`](../../evals/verification/disagreement_analysis_superseded_effort_none.md),
post-run corrections in [`docs/post_run_corrections.md`](../../docs/post_run_corrections.md)) documents how the pipeline
was developed. Its state database is the asset of the GitHub release `final-200k`.
