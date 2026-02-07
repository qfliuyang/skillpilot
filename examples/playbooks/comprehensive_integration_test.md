# Comprehensive Integration Test

## Test Name
comprehensive_integration_test

## Skills
### runner_test
1. Execute basic playbook
   - Action: skillpilot_cli_main_run
   - Args: --playbook examples/playbooks/integration_test.md --skills-dir examples/skills

2. Validate session structure
   - Action: skillpilot_cli_runner_tail
   - Args: --session-dir sessions/session_*

3. Collect and validate results
   - Action: Read result files, check outputs
   - Verify all 7 acceptance criteria met

## Defaults
- timeout_s: 120
- cancel_policy: ctrl_c
- fail_fast: false
- session_mode: shared
```