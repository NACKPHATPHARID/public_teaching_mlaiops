# Lab 4 post-mortem

What fired: The drift alert for temp_c (PSI 0.39, limit 0.14). The job flagged it at 17:15, and the incident opened at 17:18, 16 min after I started the injection at 17:01.

True cause: My own injected +6 shift in temp_c (mean 79.6 to 85.6). Schema and null rate were unchanged and all 3000 rows were valid, so the pipeline was not broken.

Retrain, roll back, or no action: No action. The producer is fine, so there is nothing to fix or roll back, and retraining on the shifted data would bake the offset into the model.

What this would have cost if unnoticed for a week: Scores would run about 14% higher on average (0.119 to 0.135). Latency and errors stay green, so the SLOs would not show it.

How to prevent or detect it faster: Run the job every 5 minutes. A range check on the producer would not catch a +6 shift.
