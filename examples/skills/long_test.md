# Long Test

**Inputs:**
- duration: 2s

**Steps:**
1. Quick operation
   - Action: poke::report_timing
   - Args: -out "quick_report.txt"
   - Timeout: 10s

2. Slow operation
   - Action: poke::long_operation
   - Args: -out "long_report.txt" -duration 2
   - Timeout: 5s
