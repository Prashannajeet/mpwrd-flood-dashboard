# Nita AI River Flow TensorFlow Model

Place the trained Nita AI TensorFlow river-flow model in this folder to enable live model inference in the MPWRD dashboard.

Supported model locations:

- `river_flow_model.keras`
- `river_flow_model.h5`
- `saved_model/`

Optional metadata file:

`model_metadata.json`

```json
{
  "model_name": "Nita AI River Flow Forecast",
  "target": "predicted_discharge_cumecs",
  "features": [
    "water_level_m",
    "danger_gap_m",
    "wl_delta_m",
    "glofas_flow_cms",
    "grrr_flow_cms",
    "lead_day"
  ],
  "input_mean": {},
  "input_std": {}
}
```

If no TensorFlow model is present, the dashboard uses the transparent Nita AI fallback ensemble and still writes forecast rows to the application database.
