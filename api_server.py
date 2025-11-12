"""
Board Operations Agent - FastAPI Server
RESTful API for agent interactions
"""

from fastapi import FastAPI, HTTPException, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import asyncio
import logging
import os
import jwt
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from contextlib import asynccontextmanager

# Import agent components
from board_operations_agent import (
    BoardOperationsAgent,
    ProposalGenerator,
    GovernorClient,
    LearningService,
    BoardOutcome,
    HealthCheck
)

# ============================================================================
# Configuration
# ============================================================================

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'development-secret-key')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# CORS Configuration
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

# ============================================================================
# Metrics
# ============================================================================

# Prometheus metrics
proposal_counter = Counter('proposals_generated_total', 'Total proposals generated')
approval_counter = Counter('proposals_approved_total', 'Total proposals approved')
rejection_counter = Counter('proposals_rejected_total', 'Total proposals rejected')
api_request_counter = Counter('api_requests_total', 'Total API requests', ['endpoint', 'method', 'status'])
api_latency_histogram = Histogram('api_request_duration_seconds', 'API request latency', ['endpoint'])
current_fill_rate = Gauge('current_average_fill_rate', 'Current average board fill rate')
model_confidence = Gauge('model_confidence_average', 'Average model confidence score')

# Reach Mode metrics
reach_current_alpha = Gauge('reach_current_alpha', 'Current Reach Mode alpha value')
reach_current_mode = Gauge('reach_current_mode', 'Current Reach Mode', ['mode'])
reach_ratio = Gauge('reach_ratio', 'Ratio of GMV from premium tiers')
reach_social_buzz = Gauge('reach_social_buzz', 'Social buzz metric')
reach_event_intensity = Gauge('reach_event_intensity', 'Event intensity metric')
reach_ops_load = Gauge('reach_ops_load', 'Operational load metric')
reach_fill_rate_24h = Gauge('reach_fill_rate_24h', 'Fill rate over last 24 hours')
reach_extra_premium_boards = Counter('reach_extra_premium_boards_total', 'Extra premium boards created')

# ============================================================================
# Data Models
# ============================================================================

class ProposalRequest(BaseModel):
    """Request model for manual proposal generation"""
    game_ids: Optional[List[str]] = Field(None, description="Specific games to analyze")
    max_proposals: int = Field(50, description="Maximum proposals to generate")
    min_confidence: float = Field(0.65, description="Minimum confidence threshold")

class ProposalResponse(BaseModel):
    """Response model for proposals"""
    proposals: List[Dict[str, Any]]
    count: int
    timestamp: datetime
    decision_cycle_id: str

class BoardOutcomeRequest(BaseModel):
    """Request model for recording board outcomes"""
    board_id: str
    proposal_id: str
    actual_fill_rate: float
    efficiency_achieved: float
    time_to_fill_minutes: float
    repeat_entry_rate: float
    notification_sent: bool
    predicted_fill_rate: float

class RetrainRequest(BaseModel):
    """Request model for model retraining"""
    use_recent_data: bool = Field(True, description="Use only recent data for retraining")
    lookback_days: int = Field(30, description="Days of historical data to use")
    
class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    uptime_seconds: float
    timestamp: datetime
    last_cycle: Optional[datetime]
    proposals_today: int
    
class MetricsResponse(BaseModel):
    """Metrics response"""
    proposals_generated: int
    approval_rate: float
    average_fill_rate: float
    average_confidence: float
    efficiency_score: float
    active_boards: int

# ============================================================================
# Authentication
# ============================================================================

security = HTTPBearer()

def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

# ============================================================================
# Application Lifespan
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting Board Operations Agent API Server...")
    
    # Initialize agent
    app.state.agent = BoardOperationsAgent()
    app.state.health_check = HealthCheck(app.state.agent)
    app.state.last_cycle = None
    app.state.proposals_today = 0
    
    # Start background task for decision cycles
    app.state.cycle_task = asyncio.create_task(run_decision_cycles(app))
    
    logger.info("API Server started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Board Operations Agent API Server...")
    
    # Cancel background task
    app.state.cycle_task.cancel()
    try:
        await app.state.cycle_task
    except asyncio.CancelledError:
        pass
    
    # Stop agent
    await app.state.agent.stop()
    
    logger.info("API Server shutdown complete")

# ============================================================================
# Background Tasks
# ============================================================================

async def run_decision_cycles(app):
    """Run periodic decision cycles"""
    cycle_hours = int(os.environ.get('DECISION_CYCLE_HOURS', 2))
    
    while True:
        try:
            logger.info("Running scheduled decision cycle")
            
            # Run cycle
            await app.state.agent.run_decision_cycle()
            
            # Update state
            app.state.last_cycle = datetime.now()
            app.state.proposals_today += 1
            
            # Update metrics
            proposal_counter.inc()
            
            logger.info("Decision cycle completed successfully")
            
            # Wait for next cycle
            await asyncio.sleep(cycle_hours * 3600)
            
        except asyncio.CancelledError:
            logger.info("Decision cycle task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in decision cycle: {e}")
            # Wait before retry
            await asyncio.sleep(300)  # 5 minutes

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Board Operations Agent API",
    description="Autonomous board creation and optimization for Square Trivia",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "service": "Board Operations Agent",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    api_request_counter.labels(endpoint="health", method="GET", status=200).inc()
    
    health = await app.state.health_check.get_health()
    
    return HealthResponse(
        status=health['status'],
        uptime_seconds=health['uptime_seconds'],
        timestamp=datetime.now(),
        last_cycle=app.state.last_cycle,
        proposals_today=app.state.proposals_today
    )

@app.post("/proposals/generate", 
         response_model=ProposalResponse,
         dependencies=[Depends(verify_token)],
         tags=["Proposals"])
async def generate_proposals(request: ProposalRequest):
    """Manually generate proposals"""
    with api_latency_histogram.labels(endpoint="proposals_generate").time():
        api_request_counter.labels(endpoint="proposals_generate", method="POST", status=200).inc()
        
        try:
            # Generate proposals
            generator = ProposalGenerator()
            proposals = await generator.generate_proposals()
            
            # Filter by confidence if specified
            if request.min_confidence > 0:
                proposals = [
                    p for p in proposals 
                    if p.predictions.confidence >= request.min_confidence
                ]
            
            # Limit number of proposals
            proposals = proposals[:request.max_proposals]
            
            # Update metrics
            proposal_counter.inc(len(proposals))
            avg_confidence = sum(p.predictions.confidence for p in proposals) / len(proposals) if proposals else 0
            model_confidence.set(avg_confidence)
            
            # Update Reach Mode metrics
            if hasattr(generator, 'current_metrics'):
                metrics = generator.current_metrics
                reach_current_alpha.set(generator.current_alpha)
                reach_ratio.set(metrics.get('reach_ratio', 0))
                reach_social_buzz.set(metrics.get('social_buzz', 0))
                reach_event_intensity.set(metrics.get('event_intensity', 0))
                reach_ops_load.set(metrics.get('ops_load', 0))
                reach_fill_rate_24h.set(metrics.get('fill_rate_24h', 0))
                
                # Set mode gauge
                for mode in ['default', 'base_reach', 'hype_surge', 'recovery', 'ops_cooldown', 'quiet_hours']:
                    reach_current_mode.labels(mode=mode).set(1 if generator.current_mode == mode else 0)
            
            # Format response
            return ProposalResponse(
                proposals=[p.to_dict() for p in proposals],
                count=len(proposals),
                timestamp=datetime.now(),
                decision_cycle_id=f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            
        except Exception as e:
            api_request_counter.labels(endpoint="proposals_generate", method="POST", status=500).inc()
            logger.error(f"Error generating proposals: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/proposals/submit",
         dependencies=[Depends(verify_token)],
         tags=["Proposals"])
async def submit_to_governor(proposal_ids: List[str]):
    """Submit proposals to Governor for approval"""
    api_request_counter.labels(endpoint="proposals_submit", method="POST", status=200).inc()
    
    try:
        # Get proposals (would fetch from database in production)
        # For now, generate new ones
        generator = ProposalGenerator()
        proposals = await generator.generate_proposals()
        
        # Submit to Governor
        governor = GovernorClient()
        response = await governor.submit_proposals(proposals)
        
        # Update metrics
        approval_counter.inc(response['summary']['approved'])
        rejection_counter.inc(response['summary']['rejected'])
        
        return response
        
    except Exception as e:
        api_request_counter.labels(endpoint="proposals_submit", method="POST", status=500).inc()
        logger.error(f"Error submitting proposals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/outcomes/record",
         dependencies=[Depends(verify_token)],
         tags=["Outcomes"])
async def record_outcome(outcome: BoardOutcomeRequest):
    """Record board outcome for learning"""
    api_request_counter.labels(endpoint="outcomes_record", method="POST", status=200).inc()
    
    try:
        # Create BoardOutcome object
        board_outcome = BoardOutcome(
            board_id=outcome.board_id,
            proposal_id=outcome.proposal_id,
            actual_fill_rate=outcome.actual_fill_rate,
            efficiency_achieved=outcome.efficiency_achieved,
            time_to_fill_minutes=outcome.time_to_fill_minutes,
            repeat_entry_rate=outcome.repeat_entry_rate,
            notification_sent=outcome.notification_sent,
            predicted_fill_rate=outcome.predicted_fill_rate
        )
        
        # Record outcome
        learning = LearningService()
        await learning.record_outcome(board_outcome)
        
        # Update metrics
        current_fill_rate.set(outcome.actual_fill_rate)
        
        return {"status": "success", "message": "Outcome recorded"}
        
    except Exception as e:
        api_request_counter.labels(endpoint="outcomes_record", method="POST", status=500).inc()
        logger.error(f"Error recording outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/model/retrain",
         dependencies=[Depends(verify_token)],
         tags=["Model"])
async def retrain_model(request: RetrainRequest):
    """Trigger model retraining"""
    api_request_counter.labels(endpoint="model_retrain", method="POST", status=200).inc()
    
    try:
        # Trigger retraining (simplified for demo)
        learning = LearningService()
        await learning.update_model()
        
        return {
            "status": "success",
            "message": "Model retraining initiated",
            "parameters": {
                "use_recent_data": request.use_recent_data,
                "lookback_days": request.lookback_days
            }
        }
        
    except Exception as e:
        api_request_counter.labels(endpoint="model_retrain", method="POST", status=500).inc()
        logger.error(f"Error retraining model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Get Prometheus metrics"""
    api_request_counter.labels(endpoint="metrics", method="GET", status=200).inc()
    
    # Return Prometheus formatted metrics
    return generate_latest()

@app.get("/metrics/summary", response_model=MetricsResponse, tags=["Monitoring"])
async def get_metrics_summary():
    """Get summarized metrics"""
    api_request_counter.labels(endpoint="metrics_summary", method="GET", status=200).inc()
    
    # Calculate summary metrics (simplified for demo)
    return MetricsResponse(
        proposals_generated=100,  # Would query from database
        approval_rate=0.75,
        average_fill_rate=0.72,
        average_confidence=0.78,
        efficiency_score=0.82,
        active_boards=12
    )

@app.post("/cycle/trigger",
         dependencies=[Depends(verify_token)],
         tags=["Control"])
async def trigger_cycle():
    """Manually trigger a decision cycle"""
    api_request_counter.labels(endpoint="cycle_trigger", method="POST", status=200).inc()
    
    try:
        # Run decision cycle
        await app.state.agent.run_decision_cycle()
        
        # Update state
        app.state.last_cycle = datetime.now()
        app.state.proposals_today += 1
        
        return {
            "status": "success",
            "message": "Decision cycle triggered",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        api_request_counter.labels(endpoint="cycle_trigger", method="POST", status=500).inc()
        logger.error(f"Error triggering cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/token", tags=["Authentication"])
async def login(username: str, password: str):
    """Generate access token (simplified for demo)"""
    # In production, verify credentials against database
    if username == "admin" and password == "admin123":  # Demo only!
        access_token = create_access_token(data={"sub": username})
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

# ============================================================================
# Reach Mode Endpoints
# ============================================================================

@app.get("/reach/status", tags=["Reach Mode"])
async def reach_status():
    """Get current Reach Mode status"""
    api_request_counter.labels(endpoint="reach_status", method="GET", status=200).inc()
    
    return {
        "mode": app.state.agent.current_mode,
        "alpha": app.state.agent.current_alpha,
        "reach_ratio": app.state.agent.current_metrics.get("reach_ratio"),
        "social_buzz": app.state.agent.current_metrics.get("social_buzz"),
        "event_intensity": app.state.agent.current_metrics.get("event_intensity"),
        "ops_load": app.state.agent.current_metrics.get("ops_load"),
        "fill_rate_24h": app.state.agent.current_metrics.get("fill_rate_24h"),
        "avg_time_to_fill": app.state.agent.current_metrics.get("avg_time_to_fill"),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/reach/override",
         dependencies=[Depends(verify_token)],
         tags=["Reach Mode"])
async def reach_override(mode: Optional[str] = None, alpha: Optional[float] = None):
    """Override Reach Mode settings (admin only)"""
    api_request_counter.labels(endpoint="reach_override", method="POST", status=200).inc()
    
    override_config = {}
    if mode:
        override_config['mode'] = mode
    if alpha is not None:
        override_config['alpha'] = alpha
    
    app.state.agent.set_reach_override(override_config)
    
    return {
        "status": "success",
        "override_applied": override_config,
        "current_mode": app.state.agent.current_mode,
        "current_alpha": app.state.agent.current_alpha
    }

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    api_request_counter.labels(
        endpoint=request.url.path,
        method=request.method,
        status=exc.status_code
    ).inc()
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    api_request_counter.labels(
        endpoint=request.url.path,
        method=request.method,
        status=500
    ).inc()
    
    logger.error(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=True
    )
