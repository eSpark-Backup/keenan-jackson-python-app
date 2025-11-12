# Reach Mode Verification Checklist

## 🚀 Quick Start Verification

### 1. Database Migration

```bash
# Apply the Reach Mode migration
psql -U agent -d squaretrivia -f reach_mode_migration.sql

# Verify new columns exist
psql -U agent -d squaretrivia -c "
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'board_agent' 
AND table_name = 'proposals' 
AND column_name IN ('reach_meta', 'reach_mode', 'price_bias_applied', 'final_score');
"
```

### 2. Environment Configuration

```bash
# Add to .env or export
export REACH_ENABLED=true
export REACH_DEFAULT_ALPHA=0.2
export REACH_OVERRIDE_MODE=""

# Verify configuration loaded
python -c "
from board_operations_agent import REACH_ENABLED, REACH_DEFAULT_ALPHA
print(f'Reach Enabled: {REACH_ENABLED}')
print(f'Default Alpha: {REACH_DEFAULT_ALPHA}')
"
```

### 3. Run Tests

```bash
# Run Reach Mode specific tests
pytest test_reach_mode.py -v

# Run integration test with existing tests
pytest test_board_operations_agent.py test_reach_mode.py -v
```

### 4. Start Agent with Reach Mode

```bash
# Start the agent
python board_operations_agent.py

# In another terminal, start the API server
python api_server.py
```

### 5. Verify API Endpoints

```bash
# Get Reach Mode status
curl http://localhost:8080/reach/status

# Expected response:
# {
#   "mode": "default",
#   "alpha": 0.2,
#   "reach_ratio": 0.35,
#   "social_buzz": 0.65,
#   "event_intensity": 0.60,
#   "ops_load": 0.45,
#   "fill_rate_24h": 0.73,
#   "avg_time_to_fill": 3.5
# }

# Test override (requires auth token)
TOKEN=$(curl -X POST http://localhost:8080/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123" | jq -r '.access_token')

curl -X POST http://localhost:8080/reach/override \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "hype_surge", "alpha": 0.7}'
```

### 6. Verify Prometheus Metrics

```bash
# Check metrics endpoint
curl http://localhost:8080/metrics | grep reach_

# Expected metrics:
# reach_current_alpha 0.2
# reach_current_mode{mode="default"} 1
# reach_ratio 0.35
# reach_social_buzz 0.65
# reach_event_intensity 0.60
# reach_ops_load 0.45
# reach_fill_rate_24h 0.73
```

### 7. Import Grafana Dashboard

```bash
# Import grafana-dashboard-reach.json through Grafana UI
# Or via API:
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @grafana-dashboard-reach.json
```

## 📊 Functional Verification

### Mode Transitions

- [ ] Default mode active when no conditions met
- [ ] Hype Surge triggers at 80% social buzz or fill rate
- [ ] Base Reach triggers at 65% buzz + 60% event intensity
- [ ] Recovery triggers at <65% fill or >6hr fill time
- [ ] Ops Cooldown triggers at >70% ops load
- [ ] Quiet Hours triggers 11PM-7AM

### Scoring Adjustments

- [ ] Alpha blending working (efficiency vs utilization)
- [ ] $50 tier gets 1.3x-1.4x bias in reach modes
- [ ] $100 tier gets 1.6x-1.8x bias in reach modes
- [ ] Min fill tolerance adjusted for premium tiers

### Data Persistence

- [ ] Proposals contain reach_meta JSON
- [ ] Decision cycles track avg_alpha_used
- [ ] Board outcomes record reach_mode_at_creation
- [ ] Reach history table populating

### Balance Control

- [ ] Reach ratio calculated correctly
- [ ] Alpha adjusts up when ratio <0.30 (3 days)
- [ ] Alpha adjusts down when ratio >0.45 (3 days)
- [ ] Adjustments capped at 0.1-0.9 range

## 🔍 Monitoring Verification

### Logs

Check for Reach Mode log entries:

```bash
docker logs board-agent | grep "\[ReachMode\]"

# Expected format:
# [ReachMode] mode=base_reach alpha=0.50 buzz=0.68 event=0.65 ops=0.45 fill24h=0.72 ttf=3.0 reachRatio=0.38
# [ReachMode] Applying mode=base_reach alpha=0.50 bias50=1.30 bias100=1.60
```

### Database Queries

```sql
-- Check proposals with Reach Mode
SELECT 
    proposal_id,
    price_tier,
    reach_meta->>'mode' as mode,
    reach_meta->>'alpha' as alpha,
    final_score
FROM board_agent.proposals
WHERE reach_meta IS NOT NULL
ORDER BY created_at DESC
LIMIT 10;

-- Check Reach Mode distribution
SELECT 
    reach_meta->>'mode' as mode,
    COUNT(*) as count,
    AVG(predicted_fill_rate) as avg_fill,
    AVG(final_score) as avg_score
FROM board_agent.proposals
WHERE reach_meta IS NOT NULL
GROUP BY reach_meta->>'mode';

-- Check premium tier performance
SELECT * FROM board_agent.v_premium_tier_analysis;

-- Check reach history
SELECT * FROM board_agent.reach_mode_history
ORDER BY timestamp DESC
LIMIT 20;
```

## ✅ Success Criteria

1. **Mode Detection**: Agent correctly identifies and applies appropriate Reach Mode
2. **Score Adjustment**: Premium tiers receive appropriate bias in reach modes
3. **Data Persistence**: All reach metadata properly stored in database
4. **API Functionality**: /reach/status and /reach/override endpoints working
5. **Metrics Export**: Prometheus metrics updating correctly
6. **Dashboard Visibility**: Grafana showing mode, alpha, and key metrics
7. **No Breaking Changes**: Existing functionality still works
8. **Performance**: Decision cycle still completes within timeout

## 🐛 Troubleshooting

### Reach Mode Not Activating

- Check REACH_ENABLED environment variable
- Verify metrics thresholds in business_rules.json
- Check agent logs for evaluation results

### Metrics Not Updating

- Verify Prometheus scraping configuration
- Check metric registration in api_server.py
- Ensure generate_proposals is being called

### Database Errors

- Run migration script
- Check column types match code expectations
- Verify JSONB operations are supported

### Override Not Working

- Check authentication token is valid
- Verify REACH_OVERRIDE_MODE is being set globally
- Check agent is reading override on next cycle

## 📝 Notes

- Reach Mode is evaluation-only; Governor still has final say
- Alpha adjustments are gradual (0.1 per 3-day period)
- Premium bias only applies in specific modes
- All changes are additive - no existing functionality removed
