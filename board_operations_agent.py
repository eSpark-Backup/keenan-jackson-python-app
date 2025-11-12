"""
Board Operations Agent - Complete Implementation
Square Trivia Platform Autonomous Board Creation System
Version 1.0.0
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import hmac

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration & Constants
# ============================================================================

class PriceTier(Enum):
    """Available price tiers for boards"""
    TIER_25 = 25
    TIER_50 = 50
    TIER_100 = 100
    TIER_250 = 250
    TIER_500 = 500
    TIER_1000 = 1000

class Sport(Enum):
    """Supported sports leagues"""
    NFL = "NFL"
    NBA = "NBA"
    NCAAF = "NCAAF"
    NCAAB = "NCAAB"

class ProposalStatus(Enum):
    """Proposal evaluation status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"

# Platform Constants
SQUARES_PER_BOARD = 50
MAX_PLAYERS_PER_SQUARE = 2
MAX_PARTICIPANTS = 100  # 50 squares x 2 players
RESTRICTED_STATES = ["AZ", "TN", "MD", "LA", "WA", "SC", "MT", "ID", "VT", "CT", "RI"]

# Decision Cycle Configuration
DECISION_CYCLE_HOURS = 2
LOOKAHEAD_DAYS = 7
MAX_PROPOSALS_PER_CYCLE = 50
TOP_K_PROPOSALS = 5

# Model Configuration
FEATURE_COUNT = 38
CONFIDENCE_THRESHOLD = 0.65
MIN_EXPECTED_FILL_RATE = 0.40

# ============================================================================
# Reach Mode Configuration
# ============================================================================

REACH_RULES = {
    "base_reach": {
        "social_buzz": 0.65, 
        "event_intensity": 0.60, 
        "alpha": 0.50, 
        "bias_50": 1.30, 
        "bias_100": 1.60, 
        "min_fill": 0.75
    },
    "hype_surge": {
        "social_buzz": 0.80, 
        "fill_rate": 0.80, 
        "alpha": 0.70, 
        "bias_50": 1.40, 
        "bias_100": 1.80, 
        "extra_premium_boards": 1
    },
    "recovery": {
        "fill_rate": 0.65, 
        "time_to_fill": 6.0, 
        "alpha": 0.20, 
        "bias_reset": 1.00, 
        "min_fill": 0.90
    },
    "ops_cooldown": {
        "ops_load": 0.70, 
        "alpha": 0.20
    },
    "reach_balance": {
        "lower": 0.30, 
        "upper": 0.45, 
        "adjustment": 0.10
    },
    "quiet_hours": {
        "start": 23, 
        "end": 7, 
        "alpha": 0.10
    }
}

# Reach Mode Environment Configuration
REACH_ENABLED = os.environ.get('REACH_ENABLED', 'true').lower() == 'true'
REACH_DEFAULT_ALPHA = float(os.environ.get('REACH_DEFAULT_ALPHA', '0.2'))
REACH_OVERRIDE_MODE = os.environ.get('REACH_OVERRIDE_MODE', '')

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Team:
    """Team information"""
    name: str
    sport: Sport
    fan_count: int = 0
    notifiable_fans: int = 0
    historical_conversion_rate: float = 0.0

@dataclass
class Game:
    """Game/sporting event information"""
    game_id: str
    sport: Sport
    home_team: Team
    away_team: Team
    start_time: datetime
    broadcast_network: str = ""
    rivalry_score: float = 0.0
    importance_score: float = 0.0

@dataclass
class BoardConfig:
    """Board configuration proposal"""
    price_tier: PriceTier
    num_boards: int
    drop_time_offset_minutes: int  # Minutes before game
    difficulty_level: str = "steady"
    
    @property
    def capacity_potential(self) -> float:
        """Calculate total capacity potential (normalized)"""
        return MAX_PARTICIPANTS * self.num_boards
    
    @property
    def efficiency_score(self) -> float:
        """Calculate efficiency score based on tier and capacity"""
        tier_weight = 1.0 / (1 + (self.price_tier.value / 100))
        return self.capacity_potential * tier_weight

@dataclass
class Prediction:
    """Model predictions for a board configuration"""
    fill_rate: float
    time_to_fill_minutes: float
    efficiency_score: float  # Replaced revenue
    utilization_rate: float  # Replaced margin
    repeat_entry_likelihood: float
    confidence: float

@dataclass
class Proposal:
    """Complete board proposal"""
    proposal_id: str
    game: Game
    config: BoardConfig
    predictions: Prediction
    score: float
    created_at: datetime
    features: Dict[str, float]
    reach_meta: Optional[Dict[str, Any]] = None  # Reach Mode metadata
    final_score: float = 0.0  # Score after Reach Mode adjustments
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'proposal_id': self.proposal_id,
            'game_id': self.game.game_id,
            'sport': self.game.sport.value,
            'home_team': self.game.home_team.name,
            'away_team': self.game.away_team.name,
            'start_time': self.game.start_time.isoformat(),
            'price_tier': self.config.price_tier.value,
            'num_boards': self.config.num_boards,
            'drop_time_offset': self.config.drop_time_offset_minutes,
            'predicted_fill_rate': self.predictions.fill_rate,
            'efficiency_score': self.predictions.efficiency_score,
            'confidence': self.predictions.confidence,
            'score': self.score,
            'final_score': self.final_score,
            'reach_meta': self.reach_meta
        }

@dataclass
class BoardOutcome:
    """Actual board performance metrics"""
    board_id: str
    proposal_id: str
    actual_fill_rate: float
    efficiency_achieved: float  # Replaced actual_revenue
    time_to_fill_minutes: float
    repeat_entry_rate: float
    notification_sent: bool
    predicted_fill_rate: float

# ============================================================================
# Data Ingestion Service
# ============================================================================

class DataIngestionService:
    """Collects and aggregates data from various sources"""
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # 1 hour
        
    async def collect_data(self) -> Dict[str, Any]:
        """Collect all data sources for decision cycle"""
        logger.info("Collecting data from all sources...")
        
        data = {
            'platform_telemetry': await self.get_platform_telemetry(),
            'user_preferences': await self.get_user_preferences(),
            'upcoming_games': await self.get_sports_schedule(),
            'social_signals': await self.get_social_buzz(),
            'historical_performance': await self.get_historical_data()
        }
        
        logger.info(f"Data collection complete. Found {len(data['upcoming_games'])} games")
        return data
    
    async def get_platform_telemetry(self) -> Dict:
        """Get current platform metrics"""
        # Simulate database query
        return {
            'active_users': 15000,
            'daily_active_users': 3200,
            'current_boards': 12,
            'average_fill_rate': 0.73,
            'board_efficiency': 0.68,
            'capacity_utilization': 0.75
        }
    
    async def get_user_preferences(self) -> List[Dict]:
        """Query user favorite team data"""
        # Check cache first
        cache_key = 'user_preferences'
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                return cached_data
        
        # Simulate database query for fan distribution
        preferences = [
            {'sport': 'NFL', 'team': 'Kansas City Chiefs', 'fan_count': 1250, 'notifiable': 980},
            {'sport': 'NFL', 'team': 'Buffalo Bills', 'fan_count': 890, 'notifiable': 720},
            {'sport': 'NFL', 'team': 'Dallas Cowboys', 'fan_count': 2100, 'notifiable': 1890},
            {'sport': 'NFL', 'team': 'Green Bay Packers', 'fan_count': 1670, 'notifiable': 1450},
            {'sport': 'NBA', 'team': 'Los Angeles Lakers', 'fan_count': 2340, 'notifiable': 2100},
            {'sport': 'NBA', 'team': 'Boston Celtics', 'fan_count': 1120, 'notifiable': 980},
            {'sport': 'NCAAF', 'team': 'Alabama', 'fan_count': 890, 'notifiable': 750},
            {'sport': 'NCAAF', 'team': 'Ohio State', 'fan_count': 1230, 'notifiable': 1100},
        ]
        
        # Cache the result
        self.cache[cache_key] = (preferences, datetime.now())
        return preferences
    
    async def get_sports_schedule(self) -> List[Game]:
        """Get upcoming games from sports APIs"""
        # Simulate API call to ESPN or sports data provider
        upcoming_games = []
        
        # Generate sample games for next 7 days
        base_time = datetime.now() + timedelta(hours=24)
        
        games_data = [
            ('NFL', 'Kansas City Chiefs', 'Buffalo Bills', 72, 'CBS', 0.9, 0.85),
            ('NFL', 'Dallas Cowboys', 'Green Bay Packers', 96, 'FOX', 0.85, 0.90),
            ('NBA', 'Los Angeles Lakers', 'Boston Celtics', 48, 'ESPN', 0.95, 0.88),
            ('NCAAF', 'Alabama', 'Ohio State', 120, 'ABC', 0.88, 0.92),
        ]
        
        for sport, home, away, hours, network, rivalry, importance in games_data:
            game_time = base_time + timedelta(hours=hours)
            
            # Get fan counts from preferences
            prefs = await self.get_user_preferences()
            home_fans = next((p['fan_count'] for p in prefs if p['team'] == home), 100)
            away_fans = next((p['fan_count'] for p in prefs if p['team'] == away), 100)
            home_notifiable = next((p['notifiable'] for p in prefs if p['team'] == home), 50)
            away_notifiable = next((p['notifiable'] for p in prefs if p['team'] == away), 50)
            
            game = Game(
                game_id=f"{sport}_{home.replace(' ', '')}_{away.replace(' ', '')}_{game_time.strftime('%Y%m%d')}",
                sport=Sport[sport],
                home_team=Team(home, Sport[sport], home_fans, home_notifiable, 0.42),
                away_team=Team(away, Sport[sport], away_fans, away_notifiable, 0.38),
                start_time=game_time,
                broadcast_network=network,
                rivalry_score=rivalry,
                importance_score=importance
            )
            upcoming_games.append(game)
        
        return upcoming_games
    
    async def get_social_buzz(self) -> Dict[str, float]:
        """Aggregate social media signals"""
        # Simulate social media API aggregation
        return {
            'NFL_trending_score': 0.78,
            'NBA_trending_score': 0.65,
            'NCAAF_trending_score': 0.82,
            'NCAAB_trending_score': 0.45
        }
    
    async def get_reach_metrics(self) -> Dict[str, float]:
        """Get metrics for Reach Mode evaluation"""
        # Simulate gathering metrics from various sources
        telemetry = await self.get_platform_telemetry()
        social = await self.get_social_buzz()
        
        # Calculate average social buzz across all sports
        social_scores = [v for k, v in social.items() if k.endswith('_trending_score')]
        avg_social_buzz = sum(social_scores) / len(social_scores) if social_scores else 0.5
        
        # Get fill rate for last 24 hours (simulated)
        fill_rate_24h = telemetry.get('average_fill_rate', 0.73)
        
        # Simulate other metrics
        metrics = {
            'social_buzz': avg_social_buzz,
            'fill_rate_24h': fill_rate_24h,
            'avg_time_to_fill': 3.5,  # hours (simulated)
            'reach_ratio': 0.35,  # Percentage of GMV from $50+ tiers
            'event_intensity': 0.65,  # Based on upcoming game importance
            'ops_load': 0.45,  # Operational load metric
            'now_local_hour': datetime.now().hour
        }
        
        return metrics
    
    async def get_historical_data(self) -> List[BoardOutcome]:
        """Get historical board performance data"""
        # Simulate historical data retrieval
        historical = []
        
        for i in range(20):  # Last 20 boards
            outcome = BoardOutcome(
                board_id=f"board_{i}",
                proposal_id=f"prop_{i}",
                actual_fill_rate=0.65 + (i * 0.01),
                efficiency_achieved=0.70 + (i * 0.015),
                time_to_fill_minutes=25 - (i * 0.5),
                repeat_entry_rate=0.30 + (i * 0.005),
                notification_sent=i % 2 == 0,
                predicted_fill_rate=0.70 + (i * 0.008)
            )
            historical.append(outcome)
        
        return historical

# ============================================================================
# Feature Engineering Pipeline
# ============================================================================

class FeatureEngineer:
    """Extract and engineer features for ML model"""
    
    def __init__(self):
        self.total_active_users = 15000  # From platform telemetry
        
    def extract_features(self, game: Game, platform_state: Dict) -> Dict[str, float]:
        """Extract all 38 engineered features"""
        features = {}
        
        # User preference features (10)
        features.update(self._extract_user_features(game))
        
        # Game characteristics (8)
        features.update(self._extract_game_features(game))
        
        # Temporal features (8)
        features.update(self._extract_temporal_features(game))
        
        # Historical performance (8)
        features.update(self._extract_historical_features(game))
        
        # Platform state features (4)
        features.update(self._extract_platform_features(platform_state))
        
        return self._normalize_features(features)
    
    def _extract_user_features(self, game: Game) -> Dict[str, float]:
        """Extract user-base interest features"""
        home_fans = game.home_team.fan_count
        away_fans = game.away_team.fan_count
        total_interest = home_fans + away_fans
        
        return {
            'home_team_fan_count': float(home_fans),
            'away_team_fan_count': float(away_fans),
            'combined_interest_pct': total_interest / self.total_active_users,
            'fan_size_ratio': max(home_fans, away_fans) / max(1, min(home_fans, away_fans)),
            'notification_eligible_count': float(game.home_team.notifiable_fans + game.away_team.notifiable_fans),
            'user_base_concentration': self._calculate_herfindahl_index(game),
            'historical_team_conversion_home': game.home_team.historical_conversion_rate,
            'historical_team_conversion_away': game.away_team.historical_conversion_rate,
            'regional_overlap_score': 0.65,  # Simplified
            'multi_sport_fan_overlap': 0.45  # Simplified
        }
    
    def _extract_game_features(self, game: Game) -> Dict[str, float]:
        """Extract game-specific features"""
        return {
            'sport_type': float(list(Sport).index(game.sport)),
            'rivalry_score': game.rivalry_score,
            'importance_score': game.importance_score,
            'primetime_game': float(game.start_time.hour >= 20),
            'weekend_game': float(game.start_time.weekday() >= 5),
            'playoff_game': 0.0,  # Would need season context
            'division_game': float(game.rivalry_score > 0.8),
            'broadcast_reach_score': self._get_broadcast_score(game.broadcast_network)
        }
    
    def _extract_temporal_features(self, game: Game) -> Dict[str, float]:
        """Extract time-based features"""
        hours_until_game = (game.start_time - datetime.now()).total_seconds() / 3600
        
        return {
            'hours_until_game': hours_until_game,
            'day_of_week': float(game.start_time.weekday()),
            'hour_of_day': float(game.start_time.hour),
            'competing_events_count': 2.0,  # Simplified
            'seasonal_factor': self._get_seasonal_factor(game.start_time),
            'days_since_last_similar_game': 7.0,  # Simplified
            'momentum_score': 0.72,  # Simplified
            'recency_weighted_performance': 0.68  # Simplified
        }
    
    def _extract_historical_features(self, game: Game) -> Dict[str, float]:
        """Extract historical performance features"""
        return {
            'avg_fill_rate_this_matchup': 0.75,
            'avg_fill_rate_this_sport': 0.72,
            'avg_fill_rate_this_timeslot': 0.70,
            'avg_time_to_fill_similar': 22.5,
            'repeat_rate_this_matchup': 0.35,
            'notification_conversion_rate': 0.42,
            'historical_efficiency_score': 0.68,
            'variance_in_outcomes': 0.15
        }
    
    def _extract_platform_features(self, platform_state: Dict) -> Dict[str, float]:
        """Extract current platform state features"""
        return {
            'current_active_boards': float(platform_state.get('current_boards', 0)),
            'platform_efficiency_score': platform_state.get('board_efficiency', 0.5),
            'recent_fill_rate_trend': 0.03,  # Simplified trend
            'user_growth_rate': 0.12  # Simplified
        }
    
    def _calculate_herfindahl_index(self, game: Game) -> float:
        """Calculate market concentration index"""
        total = game.home_team.fan_count + game.away_team.fan_count
        if total == 0:
            return 0.0
        
        home_share = (game.home_team.fan_count / total) ** 2
        away_share = (game.away_team.fan_count / total) ** 2
        return home_share + away_share
    
    def _get_broadcast_score(self, network: str) -> float:
        """Score broadcast reach"""
        scores = {
            'ESPN': 0.9,
            'FOX': 0.85,
            'CBS': 0.85,
            'NBC': 0.85,
            'ABC': 0.88,
            'TNT': 0.75,
            'NBATV': 0.60,
            'NFLN': 0.70
        }
        return scores.get(network, 0.5)
    
    def _get_seasonal_factor(self, date: datetime) -> float:
        """Calculate seasonal adjustment factor"""
        month = date.month
        # Peak months for sports betting
        peak_months = [9, 10, 11, 12, 1, 2, 3]
        return 1.2 if month in peak_months else 0.8
    
    def _normalize_features(self, features: Dict[str, float]) -> Dict[str, float]:
        """Normalize features to [0, 1] range"""
        # Simplified normalization - in production would use saved scalers
        normalized = {}
        for key, value in features.items():
            if 'count' in key or 'participants' in key:
                # Scale large values
                normalized[key] = min(1.0, value / 10000)
            elif 'rate' in key or 'score' in key or 'pct' in key:
                # Already in [0, 1] range
                normalized[key] = value
            else:
                # Generic normalization
                normalized[key] = min(1.0, max(0.0, value / 100))
        
        return normalized

# ============================================================================
# Prediction Model
# ============================================================================

class BoardOptimizationModel:
    """ML model for board configuration optimization"""
    
    def __init__(self):
        self.action_space = self._define_action_space()
        self.model_weights = self._initialize_weights()
        
    def _define_action_space(self) -> Dict:
        """Define possible board configurations"""
        return {
            'price_tiers': list(PriceTier),
            'num_boards': [1, 2, 3, 4],
            'drop_time_offsets': [30, 45, 60, 90],  # minutes before game
            'difficulty_levels': ['steady']
        }
    
    def _initialize_weights(self) -> Dict[str, float]:
        """Initialize model weights (simplified)"""
        # In production, load from trained model
        return {
            'user_interest': 0.25,
            'timing': 0.20,
            'competition': 0.15,
            'historical': 0.20,
            'platform': 0.10,
            'game_importance': 0.10
        }
    
    def predict(self, features: Dict[str, float], k: int = TOP_K_PROPOSALS) -> List[Dict]:
        """Generate top-k board proposals"""
        candidates = self._generate_candidates(features)
        scored_candidates = []
        
        for candidate in candidates:
            score = self._score_candidate(features, candidate)
            confidence = self._calculate_confidence(features, candidate)
            
            if confidence >= CONFIDENCE_THRESHOLD:
                predictions = self._predict_outcomes(features, candidate)
                
                if predictions.fill_rate >= MIN_EXPECTED_FILL_RATE:
                    scored_candidates.append({
                        'config': candidate,
                        'score': score,
                        'confidence': confidence,
                        'predictions': predictions
                    })
        
        # Sort by score and return top-k
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)
        return scored_candidates[:k]
    
    def _generate_candidates(self, features: Dict[str, float]) -> List[BoardConfig]:
        """Generate all possible board configurations"""
        candidates = []
        
        for tier in self.action_space['price_tiers']:
            for num_boards in self.action_space['num_boards']:
                for offset in self.action_space['drop_time_offsets']:
                    config = BoardConfig(
                        price_tier=tier,
                        num_boards=num_boards,
                        drop_time_offset_minutes=offset,
                        difficulty_level='steady'
                    )
                    candidates.append(config)
        
        return candidates
    
    def _score_candidate(self, features: Dict[str, float], config: BoardConfig) -> float:
        """Score a board configuration"""
        # Simplified scoring function
        base_score = 0.0
        
        # User interest component
        user_interest = features.get('combined_interest_pct', 0) * features.get('notification_eligible_count', 0) / 1000
        base_score += user_interest * self.model_weights['user_interest']
        
        # Timing component
        hours_until = features.get('hours_until_game', 168)
        timing_score = 1.0 / (1 + abs(hours_until - config.drop_time_offset_minutes / 60))
        base_score += timing_score * self.model_weights['timing']
        
        # Price tier adjustment
        tier_multiplier = {
            PriceTier.TIER_25: 1.2,
            PriceTier.TIER_50: 1.1,
            PriceTier.TIER_100: 1.0,
            PriceTier.TIER_250: 0.9,
            PriceTier.TIER_500: 0.8,
            PriceTier.TIER_1000: 0.7
        }
        base_score *= tier_multiplier.get(config.price_tier, 1.0)
        
        # Game importance
        importance = features.get('importance_score', 0.5) * features.get('rivalry_score', 0.5)
        base_score += importance * self.model_weights['game_importance']
        
        return min(1.0, max(0.0, base_score))
    
    def _calculate_confidence(self, features: Dict[str, float], config: BoardConfig) -> float:
        """Calculate prediction confidence"""
        # Simplified confidence calculation
        confidence = 0.5
        
        # Higher confidence for more fan interest
        if features.get('combined_interest_pct', 0) > 0.1:
            confidence += 0.2
        
        # Higher confidence for primetime games
        if features.get('primetime_game', 0) > 0:
            confidence += 0.15
        
        # Higher confidence for lower price tiers
        if config.price_tier.value <= 100:
            confidence += 0.15
        
        return min(1.0, confidence)
    
    def _predict_outcomes(self, features: Dict[str, float], config: BoardConfig) -> Prediction:
        """Predict board performance metrics"""
        # Simplified prediction logic
        base_fill = 0.5
        
        # Adjust based on features
        interest_adjustment = features.get('combined_interest_pct', 0) * 2
        price_adjustment = (100 / config.price_tier.value) * 0.2
        timing_adjustment = 0.1 if config.drop_time_offset_minutes <= 60 else -0.05
        
        fill_rate = min(0.95, max(0.2, base_fill + interest_adjustment + price_adjustment + timing_adjustment))
        
        # Calculate other metrics based on fill rate
        time_to_fill = 120 * (1 - fill_rate) + 10  # Minutes
        efficiency_score = fill_rate * config.efficiency_score
        utilization_rate = fill_rate * 0.85  # Simplified
        repeat_likelihood = fill_rate * 0.5  # Simplified
        
        return Prediction(
            fill_rate=fill_rate,
            time_to_fill_minutes=time_to_fill,
            efficiency_score=efficiency_score,
            utilization_rate=utilization_rate,
            repeat_entry_likelihood=repeat_likelihood,
            confidence=self._calculate_confidence(features, config)
        )

# ============================================================================
# Proposal Generator
# ============================================================================

class ProposalGenerator:
    """Generate and rank board proposals"""
    
    def __init__(self):
        self.model = BoardOptimizationModel()
        self.feature_engineer = FeatureEngineer()
        self.data_service = DataIngestionService()
        self.current_mode = "default"
        self.current_alpha = REACH_DEFAULT_ALPHA
        self.current_metrics = {}
        self.reach_history = []  # Track reach ratio over time
        
    def evaluate_reach_mode(self, metrics: Dict[str, float]) -> str:
        """Evaluate which Reach Mode to activate based on metrics"""
        # Check for override first
        if REACH_OVERRIDE_MODE:
            return REACH_OVERRIDE_MODE
            
        # Check conditions in priority order
        if metrics.get("social_buzz", 0) >= 0.80 or metrics.get("fill_rate_24h", 0) >= 0.80:
            return "hype_surge"
        if metrics.get("social_buzz", 0) >= 0.65 and metrics.get("event_intensity", 0) >= 0.60:
            return "base_reach"
        if metrics.get("fill_rate_24h", 1) < 0.65 or metrics.get("avg_time_to_fill", 0) > 6.0:
            return "recovery"
        if metrics.get("ops_load", 0) > 0.70:
            return "ops_cooldown"
        
        hour = metrics.get("now_local_hour")
        if hour is not None and (hour >= 23 or hour < 7):
            return "quiet_hours"
            
        return "default"
    
    def apply_reach_mode(self, proposals: List[Proposal], mode: str, metrics: Dict[str, float]) -> List[Proposal]:
        """Apply Reach Mode adjustments to proposals"""
        if not REACH_ENABLED:
            return proposals
            
        cfg = REACH_RULES.get(mode, {})
        alpha = cfg.get("alpha", REACH_DEFAULT_ALPHA)
        bias_50 = cfg.get("bias_50", 1.00)
        bias_100 = cfg.get("bias_100", 1.00)
        min_fill = cfg.get("min_fill")
        
        # Store current state
        self.current_alpha = alpha
        
        logger.info(f"[ReachMode] Applying mode={mode} alpha={alpha:.2f} bias50={bias_50:.2f} bias100={bias_100:.2f}")
        
        for proposal in proposals:
            # Calculate final score with alpha blending
            eff = proposal.predictions.efficiency_score
            # Use utilization_rate as a proxy for revenue/margin
            rev = proposal.predictions.utilization_rate
            
            proposal.final_score = (1 - alpha) * eff + alpha * rev
            
            # Apply tier biases
            if proposal.config.price_tier == PriceTier.TIER_50:
                proposal.final_score *= bias_50
            elif proposal.config.price_tier == PriceTier.TIER_100:
                proposal.final_score *= bias_100
            
            # Apply min_fill adjustment if specified
            if min_fill and proposal.config.price_tier.value >= 50:
                # Slightly relax fill rate requirement for premium tiers
                if proposal.predictions.fill_rate < MIN_EXPECTED_FILL_RATE:
                    if proposal.predictions.fill_rate >= min_fill * MIN_EXPECTED_FILL_RATE:
                        proposal.final_score *= 0.9  # Small penalty instead of filtering
            
            # Store reach metadata
            proposal.reach_meta = {
                "mode": mode,
                "alpha": alpha,
                "bias_50": bias_50,
                "bias_100": bias_100,
                "min_fill": min_fill,
                "metrics": {k: v for k, v in metrics.items() if k != 'now_local_hour'}
            }
        
        # Sort by final score
        proposals.sort(key=lambda x: x.final_score, reverse=True)
        
        # Add exploration bias for premium tiers in reach modes
        if mode in ("base_reach", "hype_surge"):
            # Boost premium tier proposals in selection
            extra_premium = cfg.get("extra_premium_boards", 0)
            if extra_premium > 0:
                premium_proposals = [p for p in proposals if p.config.price_tier.value >= 50]
                # Move some premium proposals higher in ranking
                for i in range(min(extra_premium, len(premium_proposals))):
                    if premium_proposals[i] not in proposals[:5]:
                        proposals.remove(premium_proposals[i])
                        proposals.insert(min(5 + i, len(proposals)), premium_proposals[i])
        
        return proposals
    
    def update_reach_balance(self, reach_ratio: float):
        """Update alpha based on reach ratio balance"""
        self.reach_history.append(reach_ratio)
        
        # Keep only last 3 days of history (36 cycles at 2-hour intervals)
        if len(self.reach_history) > 36:
            self.reach_history = self.reach_history[-36:]
        
        # Check for consistent imbalance
        if len(self.reach_history) >= 36:
            avg_ratio = sum(self.reach_history) / len(self.reach_history)
            balance_cfg = REACH_RULES.get("reach_balance", {})
            
            if avg_ratio < balance_cfg.get("lower", 0.30):
                # Too low - increase alpha to promote premium
                self.current_alpha = min(0.9, self.current_alpha + balance_cfg.get("adjustment", 0.10))
                logger.info(f"[ReachMode] Adjusting alpha UP to {self.current_alpha:.2f} (ratio={avg_ratio:.2f})")
            elif avg_ratio > balance_cfg.get("upper", 0.45):
                # Too high - decrease alpha
                self.current_alpha = max(0.1, self.current_alpha - balance_cfg.get("adjustment", 0.10))
                logger.info(f"[ReachMode] Adjusting alpha DOWN to {self.current_alpha:.2f} (ratio={avg_ratio:.2f})")
    
    async def generate_proposals(self) -> List[Proposal]:
        """Main decision cycle - generate ranked proposals"""
        logger.info("Starting proposal generation cycle...")
        
        # Collect current data
        data = await self.data_service.collect_data()
        
        # Get Reach Mode metrics
        reach_metrics = await self.data_service.get_reach_metrics()
        self.current_metrics = reach_metrics
        
        # Evaluate Reach Mode
        self.current_mode = self.evaluate_reach_mode(reach_metrics)
        
        # Log Reach Mode status
        logger.info(
            f"[ReachMode] mode={self.current_mode} alpha={self.current_alpha:.2f} "
            f"buzz={reach_metrics.get('social_buzz', 0):.2f} "
            f"event={reach_metrics.get('event_intensity', 0):.2f} "
            f"ops={reach_metrics.get('ops_load', 0):.2f} "
            f"fill24h={reach_metrics.get('fill_rate_24h', 0):.2f} "
            f"ttf={reach_metrics.get('avg_time_to_fill', 0):.1f} "
            f"reachRatio={reach_metrics.get('reach_ratio', 0):.2f}"
        )
        
        # Get upcoming games to consider
        games = self._filter_relevant_games(data['upcoming_games'])
        logger.info(f"Analyzing {len(games)} relevant games")
        
        # Generate proposals for each game
        all_proposals = []
        
        for game in games:
            # Extract features
            features = self.feature_engineer.extract_features(game, data['platform_telemetry'])
            
            # Generate predictions
            game_proposals = self.model.predict(features, k=3)
            
            # Format proposals
            for prop in game_proposals:
                proposal = self._format_proposal(game, prop, features)
                all_proposals.append(proposal)
        
        # Apply Reach Mode adjustments
        all_proposals = self.apply_reach_mode(all_proposals, self.current_mode, reach_metrics)
        
        # Update reach balance if needed
        self.update_reach_balance(reach_metrics.get('reach_ratio', 0.35))
        
        # Return top proposals
        top_proposals = all_proposals[:MAX_PROPOSALS_PER_CYCLE]
        logger.info(f"Generated {len(top_proposals)} proposals with Reach Mode: {self.current_mode}")
        
        return top_proposals
    
    def _filter_relevant_games(self, games: List[Game]) -> List[Game]:
        """Filter games within lookahead window"""
        cutoff = datetime.now() + timedelta(days=LOOKAHEAD_DAYS)
        return [g for g in games if g.start_time <= cutoff]
    
    def _format_proposal(self, game: Game, prediction: Dict, features: Dict[str, float]) -> Proposal:
        """Format proposal for submission"""
        proposal_id = self._generate_proposal_id(game, prediction['config'])
        
        return Proposal(
            proposal_id=proposal_id,
            game=game,
            config=prediction['config'],
            predictions=prediction['predictions'],
            score=prediction['score'],
            created_at=datetime.now(),
            features=features
        )
    
    def _generate_proposal_id(self, game: Game, config: BoardConfig) -> str:
        """Generate unique proposal ID"""
        components = f"{game.game_id}_{config.price_tier.value}_{config.num_boards}_{datetime.now().isoformat()}"
        return hashlib.sha256(components.encode()).hexdigest()[:16]

# ============================================================================
# Governor Client (API Interface)
# ============================================================================

class GovernorClient:
    """Interface to Governor compliance service"""
    
    def __init__(self, api_url: str = "http://governor-api:8001"):
        self.api_url = api_url
        self.api_key = os.environ.get('GOVERNOR_API_KEY', 'test-key')
        
    async def submit_proposals(self, proposals: List[Proposal]) -> Dict:
        """Submit proposals to Governor for evaluation"""
        logger.info(f"Submitting {len(proposals)} proposals to Governor")
        
        # Format proposals for API
        payload = {
            'request_id': self._generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'proposals': [p.to_dict() for p in proposals]
        }
        
        # Add authentication
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Simulate API call (in production, use aiohttp)
        response = await self._simulate_governor_response(payload)
        
        logger.info(f"Governor response: {response['summary']}")
        return response
    
    async def _simulate_governor_response(self, payload: Dict) -> Dict:
        """Simulate Governor API response"""
        decisions = []
        
        for proposal in payload['proposals']:
            # Simulate compliance checks
            decision = {
                'proposal_id': proposal['proposal_id'],
                'status': self._evaluate_proposal(proposal),
                'reasons': [],
                'modifications': {}
            }
            
            # Add rejection reasons if applicable
            if decision['status'] == ProposalStatus.REJECTED.value:
                decision['reasons'].append('Exceeds risk threshold')
            elif decision['status'] == ProposalStatus.MODIFIED.value:
                decision['modifications'] = {
                    'num_boards': max(1, proposal['num_boards'] - 1)
                }
                decision['reasons'].append('Reduced board count for risk management')
            
            decisions.append(decision)
        
        # Summary statistics
        approved = sum(1 for d in decisions if d['status'] == ProposalStatus.APPROVED.value)
        rejected = sum(1 for d in decisions if d['status'] == ProposalStatus.REJECTED.value)
        modified = sum(1 for d in decisions if d['status'] == ProposalStatus.MODIFIED.value)
        
        return {
            'request_id': payload['request_id'],
            'decisions': decisions,
            'summary': {
                'total': len(decisions),
                'approved': approved,
                'rejected': rejected,
                'modified': modified
            }
        }
    
    def _evaluate_proposal(self, proposal: Dict) -> str:
        """Simulate compliance evaluation"""
        # Simple rules-based evaluation
        if proposal['price_tier'] > 500 and proposal['num_boards'] > 2:
            return ProposalStatus.REJECTED.value
        elif proposal['predicted_fill_rate'] < 0.4:
            return ProposalStatus.REJECTED.value
        elif proposal['num_boards'] > 3:
            return ProposalStatus.MODIFIED.value
        else:
            return ProposalStatus.APPROVED.value
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        return hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:12]

# ============================================================================
# Reward Calculator
# ============================================================================

def calculate_reward(outcome: BoardOutcome) -> float:
    """Calculate reward for reinforcement learning"""
    # Efficiency component (40% weight)
    efficiency_reward = outcome.efficiency_achieved * 100
    
    # Fill rate component (30% weight)
    fill_reward = outcome.actual_fill_rate * 1000 if outcome.actual_fill_rate > 0.6 else 0
    
    # Speed component (15% weight)
    speed_reward = max(0, 300 - outcome.time_to_fill_minutes * 10)
    
    # Repeat engagement (15% weight)
    engagement_reward = outcome.repeat_entry_rate * 500
    
    # Prediction accuracy bonus
    accuracy = 1 - abs(outcome.predicted_fill_rate - outcome.actual_fill_rate)
    accuracy_bonus = accuracy * 200
    
    total_reward = (
        efficiency_reward * 0.4 +
        fill_reward * 0.3 +
        speed_reward * 0.15 +
        engagement_reward * 0.15 +
        accuracy_bonus
    )
    
    return max(0, total_reward)

# ============================================================================
# Learning Service
# ============================================================================

class LearningService:
    """Update model based on outcomes"""
    
    def __init__(self):
        self.outcome_buffer = []
        self.update_threshold = 10  # Update after 10 outcomes
        
    async def record_outcome(self, outcome: BoardOutcome):
        """Record board outcome for learning"""
        self.outcome_buffer.append(outcome)
        
        if len(self.outcome_buffer) >= self.update_threshold:
            await self.update_model()
            self.outcome_buffer = []
    
    async def update_model(self):
        """Update model weights based on outcomes"""
        logger.info(f"Updating model with {len(self.outcome_buffer)} outcomes")
        
        # Calculate rewards
        rewards = [calculate_reward(outcome) for outcome in self.outcome_buffer]
        avg_reward = sum(rewards) / len(rewards)
        
        logger.info(f"Average reward: {avg_reward:.2f}")
        
        # In production, this would trigger model retraining
        # For now, just log the performance
        for outcome, reward in zip(self.outcome_buffer, rewards):
            prediction_error = abs(outcome.predicted_fill_rate - outcome.actual_fill_rate)
            logger.debug(f"Board {outcome.board_id}: Reward={reward:.2f}, Error={prediction_error:.3f}")

# ============================================================================
# Main Agent Orchestrator
# ============================================================================

class BoardOperationsAgent:
    """Main agent orchestrator"""
    
    def __init__(self):
        self.proposal_generator = ProposalGenerator()
        self.governor_client = GovernorClient()
        self.learning_service = LearningService()
        self.running = False
        
    @property
    def current_mode(self):
        """Get current Reach Mode"""
        return self.proposal_generator.current_mode
    
    @property
    def current_alpha(self):
        """Get current alpha value"""
        return self.proposal_generator.current_alpha
    
    @property
    def current_metrics(self):
        """Get current reach metrics"""
        return self.proposal_generator.current_metrics
    
    def set_reach_override(self, override_config: Dict):
        """Set Reach Mode override (admin function)"""
        global REACH_OVERRIDE_MODE
        if 'mode' in override_config:
            REACH_OVERRIDE_MODE = override_config['mode']
            logger.info(f"[ReachMode] Override set to mode={REACH_OVERRIDE_MODE}")
        if 'alpha' in override_config:
            self.proposal_generator.current_alpha = override_config['alpha']
            logger.info(f"[ReachMode] Override alpha set to {override_config['alpha']:.2f}")
        
    async def start(self):
        """Start the agent"""
        logger.info("Board Operations Agent starting...")
        self.running = True
        
        while self.running:
            try:
                await self.run_decision_cycle()
                await asyncio.sleep(DECISION_CYCLE_HOURS * 3600)
            except Exception as e:
                logger.error(f"Error in decision cycle: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def run_decision_cycle(self):
        """Execute one complete decision cycle"""
        logger.info("=" * 50)
        logger.info("Starting new decision cycle")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        
        # Generate proposals
        proposals = await self.proposal_generator.generate_proposals()
        logger.info(f"Generated {len(proposals)} proposals")
        
        if not proposals:
            logger.warning("No proposals generated")
            return
        
        # Submit to Governor
        governor_response = await self.governor_client.submit_proposals(proposals)
        
        # Process decisions
        approved_count = governor_response['summary']['approved']
        logger.info(f"Governor approved {approved_count} proposals")
        
        # Log decisions for monitoring
        for decision in governor_response['decisions']:
            if decision['status'] == ProposalStatus.APPROVED.value:
                proposal = next(p for p in proposals if p.proposal_id == decision['proposal_id'])
                logger.info(f"Approved: {proposal.game.home_team.name} vs {proposal.game.away_team.name} - ${proposal.config.price_tier.value}")
        
        logger.info("Decision cycle complete")
        logger.info("=" * 50)
    
    async def stop(self):
        """Stop the agent"""
        logger.info("Board Operations Agent stopping...")
        self.running = False

# ============================================================================
# Health Check & Monitoring
# ============================================================================

class HealthCheck:
    """Health check and monitoring endpoints"""
    
    def __init__(self, agent: BoardOperationsAgent):
        self.agent = agent
        self.start_time = datetime.now()
        
    async def get_health(self) -> Dict:
        """Get health status"""
        return {
            'status': 'healthy' if self.agent.running else 'stopped',
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def get_metrics(self) -> Dict:
        """Get performance metrics"""
        return {
            'proposals_generated': 0,  # Would track in production
            'approval_rate': 0.0,  # Would track in production
            'average_fill_rate': 0.0,  # Would track in production
            'total_efficiency': 0.0  # Would track in production
        }

# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point"""
    # Initialize agent
    agent = BoardOperationsAgent()
    
    # Initialize health check
    health = HealthCheck(agent)
    
    # Start agent
    try:
        # Run a single cycle for demonstration
        await agent.run_decision_cycle()
        
        # In production, would run continuously:
        # await agent.start()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await agent.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await agent.stop()

if __name__ == "__main__":
    # Run the agent
    asyncio.run(main())
