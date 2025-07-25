#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Callie Caller Web Interface${NC}"

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo -e "${RED}❌ Error: This script must be run from the callie-caller root directory${NC}"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n${BLUE}🛑 Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Start the backend with web UI support
echo -e "${GREEN}✅ Starting backend API server...${NC}"
USE_WEB_UI=true python main.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ npm is not installed. Please install Node.js and npm first.${NC}"
    kill $BACKEND_PID
    exit 1
fi

# Install frontend dependencies if needed
if [ ! -d "web/frontend/node_modules" ]; then
    echo -e "${GREEN}📦 Installing frontend dependencies...${NC}"
    cd web/frontend
    npm install
    cd ../..
fi

# Start the frontend development server
echo -e "${GREEN}✅ Starting frontend development server...${NC}"
cd web/frontend
npm run dev &
FRONTEND_PID=$!
cd ../..

echo -e "${GREEN}✨ Web interface is starting...${NC}"
echo -e "${BLUE}📡 Backend API: http://localhost:8080${NC}"
echo -e "${BLUE}🌐 Frontend UI: http://localhost:3000${NC}"
echo -e "${BLUE}Press Ctrl+C to stop${NC}"

# Wait for processes
wait $BACKEND_PID
wait $FRONTEND_PID 