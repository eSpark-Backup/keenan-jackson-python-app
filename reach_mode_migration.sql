-- Reach Mode Database Migration
-- Version: 1.1.0
-- Description: Add Reach Mode tracking columns to existing tables

-- ============================================================================
-- Proposals Table Updates (additive)
-- ============================================================================

ALTER TABLE board_agent.proposals 
ADD COLUMN IF NOT EXISTS reach_meta JSONB,
ADD COLUMN IF NOT EXISTS reach_mode BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS price_bias_applied BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS final_score DECIMAL(5,4);

COMMENT ON COLUMN board_agent.proposals.reach_meta IS 'Reach Mode metadata including mode, alpha, biases, and metrics';
COMMENT ON COLUMN board_agent.proposals.reach_mode IS 'Whether Reach Mode was active for this proposal';
COMMENT ON COLUMN board_agent.proposals.price_bias_applied IS 'Whether price tier bias was applied';
COMMENT ON COLUMN board_agent.proposals.final_score IS 'Final score after Reach Mode adjustments';

-- Create index for reach mode analysis
CREATE INDEX IF NOT EXISTS idx_proposals_reach_mode 
ON board_agent.proposals(reach_mode) 
WHERE reach_mode = TRUE;

-- ============================================================================
-- Decision Cycles Table Updates (additive)
-- ============================================================================

ALTER TABLE board_agent.decision_cycles
ADD COLUMN IF NOT EXISTS reach_mode_cycles INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS avg_alpha_used DECIMAL(4,3),
ADD COLUMN IF NOT EXISTS avg_social_buzz DECIMAL(4,3),
ADD COLUMN IF NOT EXISTS avg_event_intensity DECIMAL(4,3),
ADD COLUMN IF NOT EXISTS avg_ops_load DECIMAL(4,3),
ADD COLUMN IF NOT EXISTS reach_ratio DECIMAL(4,3),
ADD COLUMN IF NOT EXISTS reach_mode_distribution JSONB;

COMMENT ON COLUMN board_agent.decision_cycles.reach_mode_cycles IS 'Number of cycles with Reach Mode active';
COMMENT ON COLUMN board_agent.decision_cycles.avg_alpha_used IS 'Average alpha value used in this cycle';
COMMENT ON COLUMN board_agent.decision_cycles.avg_social_buzz IS 'Average social buzz metric';
COMMENT ON COLUMN board_agent.decision_cycles.avg_event_intensity IS 'Average event intensity metric';
COMMENT ON COLUMN board_agent.decision_cycles.avg_ops_load IS 'Average operational load';
COMMENT ON COLUMN board_agent.decision_cycles.reach_ratio IS 'Ratio of GMV from premium tiers';
COMMENT ON COLUMN board_agent.decision_cycles.reach_mode_distribution IS 'Distribution of modes used in cycle';

-- ============================================================================
-- Board Outcomes Table Updates (additive)
-- ============================================================================

ALTER TABLE board_agent.board_outcomes
ADD COLUMN IF NOT EXISTS premium_flag BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reach_mode_at_creation VARCHAR(32),
ADD COLUMN IF NOT EXISTS alpha_at_creation DECIMAL(4,3);

COMMENT ON COLUMN board_agent.board_outcomes.premium_flag IS 'True for $50+ tier boards';
COMMENT ON COLUMN board_agent.board_outcomes.reach_mode_at_creation IS 'Reach Mode when board was created';
COMMENT ON COLUMN board_agent.board_outcomes.alpha_at_creation IS 'Alpha value when board was created';

-- Update premium_flag for existing records based on proposals table
UPDATE board_agent.board_outcomes bo
SET premium_flag = (p.price_tier >= 50)
FROM board_agent.proposals p
WHERE bo.proposal_id = p.proposal_id
AND bo.premium_flag IS NULL;

-- ============================================================================
-- New Reach Mode Analytics Views
-- ============================================================================

-- View for Reach Mode performance analysis
CREATE OR REPLACE VIEW board_agent.v_reach_mode_performance AS
SELECT 
    DATE(bo.created_at) as date,
    bo.reach_mode_at_creation as mode,
    COUNT(*) as boards_created,
    AVG(bo.actual_fill_rate) as avg_fill_rate,
    AVG(bo.actual_efficiency) as avg_efficiency,
    AVG(bo.time_to_fill_minutes) as avg_time_to_fill,
    AVG(bo.alpha_at_creation) as avg_alpha,
    SUM(CASE WHEN bo.premium_flag THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) as premium_ratio
FROM board_agent.board_outcomes bo
WHERE bo.reach_mode_at_creation IS NOT NULL
GROUP BY DATE(bo.created_at), bo.reach_mode_at_creation
ORDER BY date DESC, mode;

-- View for Reach Mode distribution over time
CREATE OR REPLACE VIEW board_agent.v_reach_mode_distribution AS
SELECT 
    dc.cycle_id,
    dc.start_time,
    dc.reach_mode_cycles,
    dc.avg_alpha_used,
    dc.reach_ratio,
    dc.avg_social_buzz,
    dc.avg_event_intensity,
    dc.avg_ops_load,
    dc.proposals_generated,
    dc.proposals_approved,
    dc.avg_predicted_fill_rate
FROM board_agent.decision_cycles dc
WHERE dc.reach_mode_cycles > 0
ORDER BY dc.start_time DESC;

-- View for premium tier performance
CREATE OR REPLACE VIEW board_agent.v_premium_tier_analysis AS
SELECT 
    p.price_tier,
    p.reach_meta->>'mode' as reach_mode,
    COUNT(*) as proposal_count,
    AVG((p.reach_meta->>'alpha')::DECIMAL) as avg_alpha,
    AVG(p.predicted_fill_rate) as avg_predicted_fill,
    AVG(p.confidence_score) as avg_confidence,
    AVG(p.final_score) as avg_final_score,
    SUM(CASE WHEN p.governor_status = 'approved' THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) as approval_rate
FROM board_agent.proposals p
WHERE p.reach_meta IS NOT NULL
AND p.price_tier IN (50, 100)
GROUP BY p.price_tier, p.reach_meta->>'mode'
ORDER BY p.price_tier, reach_mode;

-- ============================================================================
-- Reach Mode Tracking Table (new)
-- ============================================================================

CREATE TABLE IF NOT EXISTS board_agent.reach_mode_history (
    id SERIAL PRIMARY KEY,
    cycle_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mode VARCHAR(32) NOT NULL,
    alpha DECIMAL(4,3) NOT NULL,
    social_buzz DECIMAL(4,3),
    event_intensity DECIMAL(4,3),
    ops_load DECIMAL(4,3),
    fill_rate_24h DECIMAL(4,3),
    avg_time_to_fill DECIMAL(10,2),
    reach_ratio DECIMAL(4,3),
    bias_50 DECIMAL(4,2),
    bias_100 DECIMAL(4,2),
    extra_premium_boards INTEGER DEFAULT 0,
    proposals_affected INTEGER DEFAULT 0,
    
    FOREIGN KEY (cycle_id) REFERENCES board_agent.decision_cycles(cycle_id),
    INDEX idx_reach_history_timestamp (timestamp DESC),
    INDEX idx_reach_history_mode (mode)
);

COMMENT ON TABLE board_agent.reach_mode_history IS 'Historical record of Reach Mode activations and parameters';

-- ============================================================================
-- Functions for Reach Mode Analytics
-- ============================================================================

-- Function to calculate reach ratio for a given time period
CREATE OR REPLACE FUNCTION board_agent.calculate_reach_ratio(
    p_start_date TIMESTAMP,
    p_end_date TIMESTAMP
) RETURNS DECIMAL AS $$
DECLARE
    v_total_gmv DECIMAL;
    v_premium_gmv DECIMAL;
    v_ratio DECIMAL;
BEGIN
    -- Calculate total GMV (using efficiency as proxy)
    SELECT 
        COALESCE(SUM(bo.actual_efficiency * p.price_tier), 0)
    INTO v_total_gmv
    FROM board_agent.board_outcomes bo
    JOIN board_agent.proposals p ON bo.proposal_id = p.proposal_id
    WHERE bo.created_at BETWEEN p_start_date AND p_end_date;
    
    -- Calculate premium GMV ($50+)
    SELECT 
        COALESCE(SUM(bo.actual_efficiency * p.price_tier), 0)
    INTO v_premium_gmv
    FROM board_agent.board_outcomes bo
    JOIN board_agent.proposals p ON bo.proposal_id = p.proposal_id
    WHERE bo.created_at BETWEEN p_start_date AND p_end_date
    AND p.price_tier >= 50;
    
    -- Calculate ratio
    IF v_total_gmv > 0 THEN
        v_ratio := v_premium_gmv / v_total_gmv;
    ELSE
        v_ratio := 0;
    END IF;
    
    RETURN ROUND(v_ratio, 3);
END;
$$ LANGUAGE plpgsql;

-- Function to get mode distribution for a cycle
CREATE OR REPLACE FUNCTION board_agent.get_mode_distribution(
    p_cycle_id VARCHAR(255)
) RETURNS JSONB AS $$
DECLARE
    v_distribution JSONB;
BEGIN
    SELECT 
        jsonb_object_agg(
            COALESCE(p.reach_meta->>'mode', 'default'),
            count(*)
        )
    INTO v_distribution
    FROM board_agent.proposals p
    WHERE p.decision_cycle_id = p_cycle_id
    AND p.reach_meta IS NOT NULL
    GROUP BY p.reach_meta->>'mode';
    
    RETURN COALESCE(v_distribution, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Triggers for Automatic Updates
-- ============================================================================

-- Trigger to update premium_flag automatically
CREATE OR REPLACE FUNCTION board_agent.set_premium_flag() RETURNS TRIGGER AS $$
BEGIN
    -- Set premium_flag based on price tier from proposals
    SELECT (p.price_tier >= 50) 
    INTO NEW.premium_flag
    FROM board_agent.proposals p
    WHERE p.proposal_id = NEW.proposal_id;
    
    -- Set reach mode info from proposal
    SELECT 
        p.reach_meta->>'mode',
        (p.reach_meta->>'alpha')::DECIMAL
    INTO 
        NEW.reach_mode_at_creation,
        NEW.alpha_at_creation
    FROM board_agent.proposals p
    WHERE p.proposal_id = NEW.proposal_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_premium_flag
BEFORE INSERT ON board_agent.board_outcomes
FOR EACH ROW
EXECUTE FUNCTION board_agent.set_premium_flag();

-- ============================================================================
-- Permissions
-- ============================================================================

-- Grant permissions on new objects to existing role
GRANT ALL PRIVILEGES ON board_agent.reach_mode_history TO board_agent_role;
GRANT ALL PRIVILEGES ON board_agent.v_reach_mode_performance TO board_agent_role;
GRANT ALL PRIVILEGES ON board_agent.v_reach_mode_distribution TO board_agent_role;
GRANT ALL PRIVILEGES ON board_agent.v_premium_tier_analysis TO board_agent_role;
GRANT EXECUTE ON FUNCTION board_agent.calculate_reach_ratio TO board_agent_role;
GRANT EXECUTE ON FUNCTION board_agent.get_mode_distribution TO board_agent_role;

-- ============================================================================
-- Initial Data for Testing
-- ============================================================================

-- Insert sample reach mode history for testing
INSERT INTO board_agent.reach_mode_history (
    cycle_id, mode, alpha, social_buzz, event_intensity, 
    ops_load, fill_rate_24h, avg_time_to_fill, reach_ratio
)
VALUES 
    (NULL, 'default', 0.20, 0.45, 0.50, 0.30, 0.70, 3.5, 0.32),
    (NULL, 'base_reach', 0.50, 0.68, 0.65, 0.40, 0.72, 3.0, 0.38),
    (NULL, 'hype_surge', 0.70, 0.82, 0.75, 0.45, 0.85, 2.0, 0.42)
ON CONFLICT DO NOTHING;
