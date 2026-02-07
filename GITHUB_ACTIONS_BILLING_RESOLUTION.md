# GitHub Actions Billing Failure - Resolution Guide

## Issue Summary

**Error Message:**
> "The job was not started because recent account payments have failed or your spending limit needs to be increased."

**Date:** 2026-02-07
**Scope:** Affects ALL GitHub Actions workflows across ardenone organization
**Priority:** P0 - Critical

## Affected Workflows and Repositories

### 1. ardenone/ardenone-cluster
- **Workflow:** `.github/workflows/parallel-container-build.yml`
- **Failed Runs:**
  - 21776326640: `fix(bd-2si): Fix settlement value`
  - 21776314629: `chore: update mcp-openai-search`
  - 21776302320: `feat(mcp-gfz): Release v0.1.9`

- **Blocked Deployments:**
  - mcp-gfz v0.1.9 release
  - Settlement value fixes
  - mcp-openai-search updates

### 2. ardenone/botburrow-hub
- **Workflow:** Docker build and deployment
- **Failed Runs:** 21782031004, 21782019157, 21782019153
- **Impact:** Home page 500 error fix (commit 5a688b1) cannot be deployed
- **Site:** https://botburrow.ardenone.com

### 3. Related Beads
- `bd-138`: This bead (mcp-gfz v0.1.9 blocked)
- `bd-y2xq`: Botburrow-hub deployment blocked
- `bd-u3p`: Botburrow-hub deployment blocked
- `bd-2je`: Botburrow-hub deployment blocked
- `bd-2yt`: ardenone-cluster builds blocked

## Root Cause

This is a **GitHub account-level billing issue**. Common causes:

1. **Payment method failure** (expired card, insufficient funds)
2. **Spending limit set to $0** (default for new accounts)
3. **Monthly spending limit reached**
4. **Account suspension** due to billing issues

**Key Insight:** When spending limit is $0, NO Actions jobs run - even for free tier usage.

## Resolution Steps (Choose One)

### Option A: Fix GitHub Billing (Recommended)

**Step 1: Visit Billing Settings**

```
Organization: https://github.com/organizations/ardenone/settings/billing
OR Personal: https://github.com/settings/billing
```

**Step 2: Update Payment Method**

1. Click **"Billing and plans"**
2. Go to **"Payment information"**
3. Check credit card:
   - Is it expired?
   - Does it allow international charges? (GitHub is Ireland-based)
   - Is there sufficient credit limit?

**Step 3: Increase Spending Limit**

1. Go to **"Billing and plans"** → **"Cost management"**
2. Find **"Actions spending limit"**
3. Change from `$0` to at least `$50` or higher
4. Click **"Update limit"**

**Note:** GitHub Actions has a free tier (2000 minutes/month). Setting a limit > $0 allows free usage without charges until limit is exceeded.

**Step 4: Verify Account Status**

- Check for outstanding invoices
- Resolve any payment failures
- Ensure account is in good standing

**Step 5: Test Workflow**

```bash
# Make a trivial commit to trigger workflow
cd /home/coder/ardenone-cluster
echo "# test" >> README.md
git add . && git commit -m "test: trigger workflow after billing fix"
git push origin main
```

Verify at: https://github.com/ardenone/ardenone-cluster/actions

### Option B: Manual Docker Build (Fastest Immediate Fix)

For critical deployments that cannot wait:

```bash
# Example: Build mcp-gfz manually
cd /path/to/mcp-gfz
docker build -t <registry>/mcp-gfz:0.1.9 -t <registry>/mcp-gfz:latest .
docker login -u <username>
docker push <registry>/mcp-gfz:0.1.9
docker push <registry>/mcp-gfz:latest
```

### Option C: Use Alternative CI/CD

- **Self-hosted runners:** No GitHub Actions minutes usage
- **GitLab CI:** Free for public repos
- **CircleCI:** Free tier available

## Prevention Strategies

### 1. Set Spending Alerts

```
https://github.com/organizations/ardenone/settings/billing
```

Configure email alerts at:
- 50% of spending limit
- 75% of spending limit
- 90% of spending limit

### 2. Monitor Usage Regularly

Check Actions usage at:
```
https://github.com/organizations/ardenone/settings/billing/actions
```

### 3. Consider Self-Hosted Runners

For heavy Docker builds, self-hosted runners:
- Reduce GitHub Actions minutes usage
- Provide faster builds (local registry caching)
- Lower long-term costs

## Verification

**After Billing Fix:**

✅ Workflow runs appear in Actions tab
✅ Jobs show "queued" then "running" status
✅ Workflow logs are accessible
✅ Docker images build and push successfully

**Check Specific Workflows:**

- ardenone-cluster: https://github.com/ardenone/ardenone-cluster/actions
- botburrow-hub: https://github.com/ardenone/botburrow-hub/actions

## Related Documentation

- `/home/coder/ardenone-cluster/GITHUB_ACTIONS_BILLING_ISSUE.md` - Kalshi shadow monitor investigation
- GitHub Community: [Unable to run GitHub Actions due to billing issues](https://github.com/orgs/community/discussions/179496)
- GitHub Community: [How do you increase the spending limit](https://github.com/orgs/community/discussions/177759)

## Bead Cleanup

After resolution, close related beads:

```bash
# Close this bead
br close bd-138 --reason "GitHub Actions billing resolved, workflows running"

# Close duplicate billing beads
br close bd-y2xq --reason "Duplicate - resolved by bd-138"
br close bd-u3p --reason "Duplicate - resolved by bd-138"
br close bd-2je --reason "Duplicate - resolved by bd-138"
br close bd-2yt --reason "Duplicate - resolved by bd-138"
```

---

**Created:** 2026-02-07
**Bead:** bd-138
**Last Updated:** 2026-02-07
