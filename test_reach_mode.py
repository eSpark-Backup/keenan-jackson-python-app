"""
Reach Mode Tests for Board Operations Agent
Testing Reach Mode evaluation, scoring adjustments, and integration
"""

import asyncio
import pytest
from datetime import datetime
from typing import Dict

# Import Reach Mode components
from board_operations_agent import (
    ProposalGenerator,
    BoardOperationsAgent,
    PriceTier,
    BoardConfig,
    Prediction,
    Proposal,
    Game,
    Team,
    Sport,
    REACH_RULES
)

# ============================================================================
# Unit Tests - Reach Mode Evaluation
# ============================================================================

class TestReachModeEvaluation:
    """Test Reach Mode evaluation logic"""
    
    def test_hype_surge_detection(self):
        """Test hype surge mode triggers correctly"""
        generator = ProposalGenerator()
        
        # High social buzz should trigger hype surge
        metrics = {
            'social_buzz': 0.85,
            'fill_rate_24h': 0.70,
            'event_intensity': 0.60,
            'ops_load': 0.40,
            'avg_time_to_fill': 3.0,
            'reach_ratio': 0.35
        }
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "hype_surge"
        
        # High fill rate should also trigger hype surge
        metrics['social_buzz'] = 0.70
        metrics['fill_rate_24h'] = 0.82
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "hype_surge"
    
    def test_base_reach_detection(self):
        """Test base reach mode triggers correctly"""
        generator = ProposalGenerator()
        
        metrics = {
            'social_buzz': 0.68,
            'fill_rate_24h': 0.72,
            'event_intensity': 0.65,
            'ops_load': 0.40,
            'avg_time_to_fill': 3.0,
            'reach_ratio': 0.35
        }
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "base_reach"
    
    def test_recovery_mode_detection(self):
        """Test recovery mode triggers correctly"""
        generator = ProposalGenerator()
        
        # Low fill rate should trigger recovery
        metrics = {
            'social_buzz': 0.50,
            'fill_rate_24h': 0.60,
            'event_intensity': 0.50,
            'ops_load': 0.40,
            'avg_time_to_fill': 4.0,
            'reach_ratio': 0.30
        }
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "recovery"
        
        # High time to fill should also trigger recovery
        metrics['fill_rate_24h'] = 0.70
        metrics['avg_time_to_fill'] = 7.0
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "recovery"
    
    def test_ops_cooldown_detection(self):
        """Test ops cooldown mode triggers correctly"""
        generator = ProposalGenerator()
        
        metrics = {
            'social_buzz': 0.60,
            'fill_rate_24h': 0.70,
            'event_intensity': 0.50,
            'ops_load': 0.75,  # High ops load
            'avg_time_to_fill': 3.0,
            'reach_ratio': 0.35
        }
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "ops_cooldown"
    
    def test_quiet_hours_detection(self):
        """Test quiet hours mode triggers correctly"""
        generator = ProposalGenerator()
        
        # Test late night hour
        metrics = {
            'social_buzz': 0.60,
            'fill_rate_24h': 0.70,
            'event_intensity': 0.50,
            'ops_load': 0.40,
            'avg_time_to_fill': 3.0,
            'reach_ratio': 0.35,
            'now_local_hour': 23
        }
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "quiet_hours"
        
        # Test early morning hour
        metrics['now_local_hour'] = 4
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "quiet_hours"
        
        # Test normal hour
        metrics['now_local_hour'] = 14
        
        mode = generator.evaluate_reach_mode(metrics)
        assert mode == "default"

# ============================================================================
# Unit Tests - Reach Mode Scoring
# ============================================================================

class TestReachModeScoring:
    """Test Reach Mode scoring adjustments"""
    
    def test_alpha_blending(self):
        """Test alpha blending of efficiency and utilization"""
        generator = ProposalGenerator()
        
        # Create test proposal
        game = Game(
            game_id="test_game",
            sport=Sport.NFL,
            home_team=Team("Home", Sport.NFL),
            away_team=Team("Away", Sport.NFL),
            start_time=datetime.now()
        )
        
        config = BoardConfig(
            price_tier=PriceTier.TIER_50,
            num_boards=1,
            drop_time_offset_minutes=60
        )
        
        predictions = Prediction(
            fill_rate=0.75,
            time_to_fill_minutes=25.0,
            efficiency_score=0.80,
            utilization_rate=0.60,
            repeat_entry_likelihood=0.35,
            confidence=0.75
        )
        
        proposal = Proposal(
            proposal_id="test_prop",
            game=game,
            config=config,
            predictions=predictions,
            score=0.70,
            created_at=datetime.now(),
            features={}
        )
        
        # Test with different alpha values
        proposals = [proposal]
        metrics = {'social_buzz': 0.70, 'event_intensity': 0.65}
        
        # Base reach mode (alpha=0.50)
        proposals_adjusted = generator.apply_reach_mode(proposals, "base_reach", metrics)
        
        # Final score should be blend of efficiency (0.80) and utilization (0.60)
        # With alpha=0.50: (0.5 * 0.80 + 0.5 * 0.60) * bias_50
        expected = (0.5 * 0.80 + 0.5 * 0.60) * 1.30  # bias_50 = 1.30
        assert abs(proposals_adjusted[0].final_score - expected) < 0.01
    
    def test_tier_bias_application(self):
        """Test price tier bias application"""
        generator = ProposalGenerator()
        
        # Create proposals for different tiers
        proposals = []
        for tier in [PriceTier.TIER_25, PriceTier.TIER_50, PriceTier.TIER_100]:
            game = Game(
                game_id=f"test_game_{tier.value}",
                sport=Sport.NFL,
                home_team=Team("Home", Sport.NFL),
                away_team=Team("Away", Sport.NFL),
                start_time=datetime.now()
            )
            
            config = BoardConfig(
                price_tier=tier,
                num_boards=1,
                drop_time_offset_minutes=60
            )
            
            predictions = Prediction(
                fill_rate=0.75,
                time_to_fill_minutes=25.0,
                efficiency_score=0.70,
                utilization_rate=0.70,
                repeat_entry_likelihood=0.35,
                confidence=0.75
            )
            
            proposal = Proposal(
                proposal_id=f"test_prop_{tier.value}",
                game=game,
                config=config,
                predictions=predictions,
                score=0.70,
                created_at=datetime.now(),
                features={}
            )
            proposals.append(proposal)
        
        # Apply hype surge mode
        metrics = {'social_buzz': 0.82}
        proposals_adjusted = generator.apply_reach_mode(proposals, "hype_surge", metrics)
        
        # Check biases were applied correctly
        # TIER_25 should have no bias (1.0)
        # TIER_50 should have bias_50 (1.40)
        # TIER_100 should have bias_100 (1.80)
        
        tier_25_score = next(p.final_score for p in proposals_adjusted if p.config.price_tier == PriceTier.TIER_25)
        tier_50_score = next(p.final_score for p in proposals_adjusted if p.config.price_tier == PriceTier.TIER_50)
        tier_100_score = next(p.final_score for p in proposals_adjusted if p.config.price_tier == PriceTier.TIER_100)
        
        # TIER_100 should have highest score due to bias
        assert tier_100_score > tier_50_score > tier_25_score
    
    def test_min_fill_adjustment(self):
        """Test minimum fill rate adjustment for premium tiers"""
        generator = ProposalGenerator()
        
        # Create proposal with fill rate below normal threshold
        game = Game(
            game_id="test_game",
            sport=Sport.NFL,
            home_team=Team("Home", Sport.NFL),
            away_team=Team("Away", Sport.NFL),
            start_time=datetime.now()
        )
        
        config = BoardConfig(
            price_tier=PriceTier.TIER_100,
            num_boards=1,
            drop_time_offset_minutes=60
        )
        
        predictions = Prediction(
            fill_rate=0.35,  # Below MIN_EXPECTED_FILL_RATE (0.40)
            time_to_fill_minutes=40.0,
            efficiency_score=0.60,
            utilization_rate=0.55,
            repeat_entry_likelihood=0.30,
            confidence=0.70
        )
        
        proposal = Proposal(
            proposal_id="test_prop",
            game=game,
            config=config,
            predictions=predictions,
            score=0.60,
            created_at=datetime.now(),
            features={}
        )
        
        # Apply base reach mode with min_fill
        proposals = [proposal]
        metrics = {'social_buzz': 0.68, 'event_intensity': 0.65}
        
        # min_fill in base_reach is 0.75
        # So 0.75 * 0.40 = 0.30 minimum acceptable
        # Our fill rate is 0.35, which is above 0.30, so should get small penalty
        proposals_adjusted = generator.apply_reach_mode(proposals, "base_reach", metrics)
        
        # Check that proposal wasn't filtered out but got penalty
        assert len(proposals_adjusted) == 1
        assert proposals_adjusted[0].final_score > 0

# ============================================================================
# Unit Tests - Reach Balance
# ============================================================================

class TestReachBalance:
    """Test Reach Mode balance adjustments"""
    
    def test_reach_ratio_adjustment_up(self):
        """Test alpha increases when reach ratio is too low"""
        generator = ProposalGenerator()
        
        # Simulate 36 cycles with low reach ratio
        for _ in range(36):
            generator.update_reach_balance(0.25)  # Below lower threshold (0.30)
        
        # Alpha should have increased
        assert generator.current_alpha > REACH_RULES['reach_balance']['lower']
    
    def test_reach_ratio_adjustment_down(self):
        """Test alpha decreases when reach ratio is too high"""
        generator = ProposalGenerator()
        generator.current_alpha = 0.60  # Start with higher alpha
        
        # Simulate 36 cycles with high reach ratio
        for _ in range(36):
            generator.update_reach_balance(0.50)  # Above upper threshold (0.45)
        
        # Alpha should have decreased
        assert generator.current_alpha < 0.60

# ============================================================================
# Integration Tests
# ============================================================================

class TestReachModeIntegration:
    """Integration tests for Reach Mode"""
    
    @pytest.mark.asyncio
    async def test_full_cycle_with_reach_mode(self):
        """Test complete proposal cycle with Reach Mode"""
        generator = ProposalGenerator()
        
        # Generate proposals
        proposals = await generator.generate_proposals()
        
        # Check that proposals have reach metadata
        assert all(p.reach_meta is not None for p in proposals)
        assert all(p.final_score > 0 for p in proposals)
        
        # Verify mode was evaluated and applied
        assert generator.current_mode in [
            "default", "base_reach", "hype_surge", 
            "recovery", "ops_cooldown", "quiet_hours"
        ]
        
        # Verify reach meta structure
        for proposal in proposals:
            assert 'mode' in proposal.reach_meta
            assert 'alpha' in proposal.reach_meta
            assert 'bias_50' in proposal.reach_meta
            assert 'bias_100' in proposal.reach_meta
    
    @pytest.mark.asyncio
    async def test_agent_reach_mode_properties(self):
        """Test BoardOperationsAgent exposes Reach Mode properties"""
        agent = BoardOperationsAgent()
        
        # Check properties are accessible
        assert hasattr(agent, 'current_mode')
        assert hasattr(agent, 'current_alpha')
        assert hasattr(agent, 'current_metrics')
        
        # Test override function
        agent.set_reach_override({'mode': 'hype_surge', 'alpha': 0.75})
        
        # Note: Override is global, so we need to reset it
        import board_operations_agent
        board_operations_agent.REACH_OVERRIDE_MODE = ''

# ============================================================================
# Performance Tests
# ============================================================================

class TestReachModePerformance:
    """Test Reach Mode performance impact"""
    
    @pytest.mark.asyncio
    async def test_reach_mode_overhead(self):
        """Test that Reach Mode doesn't significantly impact performance"""
        import time
        
        generator = ProposalGenerator()
        
        # Time proposal generation with Reach Mode
        start = time.time()
        proposals = await generator.generate_proposals()
        elapsed = time.time() - start
        
        # Should still complete within reasonable time
        assert elapsed < 35  # Slightly more than original 30s due to Reach Mode
        assert len(proposals) > 0

# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    # Run Reach Mode tests
    pytest.main([__file__, "-v", "--tb=short"])
