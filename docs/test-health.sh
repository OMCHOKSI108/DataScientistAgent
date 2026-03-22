#!/bin/bash
# Basic health check script for the Data Scientist Agent

echo "🔍 Running basic health checks..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running"
    exit 1
fi

# Check if container is running
if ! docker ps | grep -q "agentic-analyst"; then
    echo "❌ Container 'agentic-analyst' is not running"
    exit 1
fi

# Check health endpoint
echo "⏳ Testing health endpoint..."
if curl -s -f http://localhost:8080/api/health > /dev/null; then
    echo "✅ Health endpoint is responding"
else
    echo "❌ Health endpoint is not responding"
    exit 1
fi

# Check main pages
echo "⏳ Testing main pages..."
for page in "/" "/signup.html" "/chat.html"; do
    if curl -s -f -I http://localhost:8080$page | grep -q "200 OK"; then
        echo "✅ $page is accessible"
    else
        echo "❌ $page is not accessible"
        exit 1
    fi
done

echo "🎉 All basic checks passed!"
echo "🌐 Application is running at: http://localhost:8080"