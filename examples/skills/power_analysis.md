# Power Analysis

**Inputs:**
- report_file: power_report.txt
- corner: typical

**Steps:**
1. Generate power report
   - Action: poke::report_power
   - Args: -out "power_report.txt" -corner "typical"
   - Timeout: 30s

2. Verify connectivity
   - Action: poke::test_connectivity
   - Args: -out "connectivity_report.txt"
   - Timeout: 30s
