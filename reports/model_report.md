# Model report (Phase 4)

Universe: starters, [2021, 2022, 2023, 2024] train / 2025 calibrate.
Evaluation: second half of 2025 (21,609 batter-games, base rate 0.615).

## Scoreboard

| model | log_loss | brier | auc | n | top5_hit_rate | top10_hit_rate |
|---|---|---|---|---|---|---|
| gbm_raw | 0.6594 | 0.2334 | 0.5705 | 21609 | 0.7596 | 0.7191 |
| structural_cal | 0.6594 | 0.2334 | 0.5704 | 21609 | 0.7416 | 0.7393 |
| structural_raw | 0.6599 | 0.2337 | 0.5714 | 21609 | 0.7393 | 0.7247 |
| logistic | 0.6602 | 0.2338 | 0.5667 | 21609 | 0.7483 | 0.7124 |
| gbm_cal | 0.6605 | 0.2336 | 0.5698 | 21609 | 0.7551 | 0.7157 |
| eb_pa | 0.6650 | 0.2361 | 0.5562 | 21609 | 0.7281 | 0.7045 |
| league | 0.6665 | 0.2368 | 0.5000 | 21609 | 0.6202 | 0.5989 |

**Winner: `structural_cal`** — registered as `mlb_hits_hit_model` v1 (alias `production`).

## Gates

PASS — beats the EB baseline on log loss + Brier; calibration held.

## Per-tier log loss (winner vs EB baseline)

| dimension | level | n | base_rate | logloss_winner | logloss_eb_pa |
|---|---|---|---|---|---|
| quality | Q1 weakest | 5403 | 0.5604 | 0.6812 | 0.6904 |
| quality | Q2 | 5402 | 0.6048 | 0.6672 | 0.6728 |
| quality | Q3 | 5402 | 0.6270 | 0.6559 | 0.6605 |
| quality | Q4 strongest | 5402 | 0.6675 | 0.6333 | 0.6362 |
| pa_band | <3.5 | 6374 | 0.5660 | 0.6812 | 0.6915 |
| pa_band | 3.5-4.2 | 9464 | 0.6221 | 0.6576 | 0.6605 |
| pa_band | >4.2 | 5735 | 0.6586 | 0.6379 | 0.6423 |
