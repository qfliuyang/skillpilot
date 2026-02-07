# Timing Analysis

**Inputs:**
- report_file: timing_report.txt
- worst_paths: 10
- total_paths: 100

**Steps:**
1. Generate timing report
   - Action: poke::report_timing
   - Args: -out "timing_report.txt" -worst 10 -paths 100
   - Timeout: 30s

2. Check slack violations
   - Action: poke::report_constraints
   - Args: -out "constraints_report.txt"
   - Timeout: 30s
