# Architecture

```text
Browser (anonymous)
  ├─ GET /                      Static HTML/CSS/JS
  ├─ GET /api/v1/airports       Airport autocomplete data
  └─ GET /api/v1/destinations   Search result with fares + availability view
                    │
                    ▼
             FastAPI application
  ┌──────────────────────────────────────────────┐
  │ Search service                              │
  │  - schedule date/day filtering              │
  │  - fare period matching                     │
  │  - facility-fee estimate                    │
  │  - sort/filter                              │
  ├──────────────────────────────────────────────┤
  │ Availability service                        │
  │ EXACT_SKYMATE > GENERAL_CURRENT >            │
  │ GENERAL_D1 > PREDICTED > UNKNOWN             │
  │  - TTL expiration                           │
  │  - explainable rule-based estimate          │
  └──────────────────────────────────────────────┘
                    │
                    ▼
                  SQLite
  airports / routes / schedules / fares /
  availability_observations / dataset_meta
```

## Production replacement points

1. Replace SQLite with PostgreSQL without changing the public response schema.
2. Implement approved availability connectors that write normalized observations.
3. Permit `EXACT_SKYMATE` only when the upstream source directly identifies the target fare product.
4. Add an authenticated admin UI; public users remain anonymous.
5. Use a job runner and monitoring for data freshness and connector failures.

## Availability provider contract

Every connector must produce:

- `flight_no`
- `flight_date`
- `cabin_class`
- `fare_product` when applicable
- `status`
- `source_type`
- `source_label`
- `observed_at`
- `expires_at`

A general-seat source must never emit `EXACT_SKYMATE`.
