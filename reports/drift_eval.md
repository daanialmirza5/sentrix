# Drift benchmark (synthetic)

Synthetic drift benchmark (not production accuracy). 10-action windows; 20 enrollment, 40 benign, 60 drift windows (bank-detail read share 0->0.59).

Calibrated h = **10.0** (k = 0.5), chosen on seeds 0-9 only.

| Set | Detector | Benign false-alarm rate | Detection rate | Median delay (windows) |
|---|---|---|---|---|
| calibration, h=5 | frozen | 0.3 | 1.0 | 11.0 |
| calibration, h=5 | rolling | 0.4 | 1.0 | 14.5 |
| held-out, h=5 | frozen | 0.1 | 1.0 | 9.0 |
| held-out, h=5 | rolling | 0.133 | 1.0 | 11.0 |
| held-out, h=10.0 | frozen | 0.067 | 1.0 | 13.0 |
| held-out, h=10.0 | rolling | 0.067 | 1.0 | 17.5 |
