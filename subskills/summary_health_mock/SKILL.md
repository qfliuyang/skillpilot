# Summary Health Mock

## Description
Mock skill for testing SkillPilot runtime. Generates health analysis reports.

## Required Outputs
- `reports/summary_health.txt` - Overall design health summary
- `reports/timing_health.txt` - Timing health analysis

## Debug Hints
1. Check if report files were generated in `reports/`
2. Verify pseudo session processed the request successfully
3. Review `session/innovus.stdout.log` for execution details

## Version
0.1.0
