# Integration Test Case - Complete E2E Flow

This test verifies the end-to-end flow: Playbook → Skills → Commands → Runner execution → Results → Master aggregation.

**Test Name:** `integration_e2e_test`

**Playbook:** `examples/playbooks/integration_test.md`

```markdown
# Integration E2E Test

**Skills:**
- runner_test
- result_validation

**Defaults:**
- timeout_s: 120
- cancel_policy: ctrl_c
- fail_fast: false
- session_mode: shared
```

**Purpose:**
Run 2 skills (timing_analysis and power_analysis) with 4 commands total, collect all results, verify all acceptance criteria.
```

