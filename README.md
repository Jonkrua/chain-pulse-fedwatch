# Chain Pulse FedWatch collector

Dedicated public collector for the user's dashboard; no private dashboard files or API keys.

Visits the official CME Chinese FedWatch parent page with ordinary Chromium,
then reads its QuikStrike Current views. Does not spoof headers, bypass verification,
or compute a substitute probability model.

The parser requires a matching meeting date, explicit current range, source timestamp,
complete NOW probabilities, near-100% sums and consistency with the summary.
Source time (America/Chicago) and collection time are distinct. A successful new read
does not make an old source quote current.

Run tests: `python -m unittest discover -p 'test_*.py'`.
Run collector with Playwright 1.55.0 and its Chromium installed: `python collector.py`.
Output is written only after all meetings pass validation.

Deployment state: manual verification only until a validated cloud run succeeds.
The intended cadence is every half-hour; GitHub scheduled runs may be delayed.
