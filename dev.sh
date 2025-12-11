#!/bin/bash
# Development helper script for agent_multitool

set -e

echo "🚀 Agent_Multitool Development Helper"
echo "======================================"

# Configuration
PROJECT_NAME="agent-multitool"
CONTAINER_NAME="${PROJECT_NAME}-dev"
TESTER_NAME="${PROJECT_NAME}-tester"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Build and start the application
start_dev() {
    log_info "Starting development environment..."
    
    # Create logs directory
    mkdir -p logs
    
    # Build and start
    docker-compose -f docker-compose.yml up -d agent-multitool
    
    # Wait for container to be ready
    log_info "Waiting for agent_multitool to be ready..."
    sleep 10
    
    if docker-compose -f docker-compose.yml ps agent-multitool | grep -q "Up"; then
        log_success "agent_multitool is running!"
        show_status
    else
        log_error "Failed to start agent_multitool"
        docker-compose -f docker-compose.yml logs agent-multitool
        exit 1
    fi
}

# Stop the application
stop_dev() {
    log_info "Stopping development environment..."
    docker-compose -f docker-compose.yml down
    log_success "Development environment stopped"
}

# Show status
show_status() {
    log_info "Container Status:"
    docker-compose -f docker-compose.yml ps
    
    echo ""
    log_info "Service Endpoints:"
    echo "  🌐 Main API: http://localhost:1417"
    echo "  📊 Health: http://localhost:1417/api/health"
    echo "  📚 Documentation: http://localhost:1417/docs"
    echo "  🛠️  API Tools: http://localhost:1417/api/tools"
    echo "  🔌 MCP Server: http://localhost:1417/mcp"
}

# Test the application
test_api() {
    log_info "Testing API endpoints..."
    
    # Test health
    echo "🏥 Testing health endpoint:"
    if curl -s http://localhost:1417/api/health | jq . > /dev/null 2>&1; then
        log_success "Health endpoint OK"
        curl -s http://localhost:1417/api/health | jq .
    else
        log_error "Health endpoint failed"
    fi
    
    echo ""
    echo "🛠️  Testing tools endpoint:"
    if curl -s http://localhost:1417/api/tools | jq . > /dev/null 2>&1; then
        log_success "Tools endpoint OK"
        TOOLS_COUNT=$(curl -s http://localhost:1417/api/tools | jq -r .total_tools)
        echo "Found $TOOLS_COUNT tools across $(curl -s http://localhost:1417/api/tools | jq -r .servers) servers"
    else
        log_error "Tools endpoint failed"
    fi
    
    echo ""
    echo "📝 Testing router endpoint (streaming):"
    echo 'curl -X POST http://localhost:1417/api/router -H "Content-Type: application/json" -d "{\"input\":\"Hello world\",\"stream\":true}"'
}

# View logs
show_logs() {
    log_info "Showing logs from agent_multitool:"
    docker-compose -f docker-compose.yml logs -f agent-multitool
}

# Execute commands in container
exec_container() {
    if [ -z "$1" ]; then
        log_info "Opening bash shell in container:"
        docker exec -it $CONTAINER_NAME bash
    else
        log_info "Executing in container: $@"
        docker exec -it $CONTAINER_NAME "$@"
    fi
}

# Test MCP functionality
test_mcp() {
    log_info "Testing MCP functionality..."
    
    # Test MCP initialization
    echo "🔌 Testing MCP initialization:"
    curl -s -X POST http://localhost:1417/mcp \
      -H "Content-Type: application/json" \
      -d '{"method":"initialize","id":1}' | jq .
    
    echo ""
    echo "🛠️  Testing MCP tools list:"
    curl -s -X POST http://localhost:1417/mcp \
      -H "Content-Type: application/json" \
      -d '{"method":"tools/list","id":2}' | jq .
}

# Clean up
cleanup() {
    log_info "Cleaning up..."
    stop_dev
    docker system prune -f
    log_success "Cleanup complete"
}

# Show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start     - Start development environment"
    echo "  stop      - Stop development environment"
    echo "  status    - Show container status"
    echo "  test      - Test API endpoints"
    echo "  test-mcp  - Test MCP functionality"
    echo "  logs      - Show application logs"
    echo "  exec [cmd] - Execute command in container (default: bash)"
    echo "  cleanup   - Stop and clean up"
    echo "  help      - Show this help"
}

# Main script logic
case "${1:-start}" in
    start)
        check_docker
        start_dev
        ;;
    stop)
        stop_dev
        ;;
    status)
        show_status
        ;;
    test)
        test_api
        ;;
    test-mcp)
        test_mcp
        ;;
    logs)
        show_logs
        ;;
    exec)
        shift
        exec_container "$@"
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        log_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac
