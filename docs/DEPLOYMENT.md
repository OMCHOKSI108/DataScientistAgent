# Deployment Guide

## Quick Start

### Prerequisites
- Docker installed
- `.env` file with API keys (Gemini, Supabase)
- Port 8080 available (or use `--port` flag)

### One-Command Deployment

**Windows (PowerShell):**
```powershell
.\docker-build-run.ps1
```

**Linux/Mac (Bash):**
```bash
chmod +x docker-build-run.sh
./docker-build-run.sh
```

Both scripts:
- ✅ Check prerequisites (.env file, Docker)
- ✅ Build optimized Docker image
- ✅ Stop any existing containers
- ✅ Run the application with volume mounts
- ✅ Display access URLs

## Access Points

Once running, the application is available at:

| Component | URL |
|-----------|-----|
| **Chat UI** | http://localhost:8080/chat.html |
| **Login** | http://localhost:8080/ |
| **API Docs** | http://localhost:8080/docs |
| **Health Check** | http://localhost:8080/api/health |

## Environment Variables

Create `.env` in the project root:

```ini
GROQ_API_KEY=your-groq-api-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

> **Note:** The SECRET_KEY and LOG_LEVEL are optional and have sensible defaults.

## Docker Details

### Image Name
`data-analyst-agent:latest` (with timestamped backups)

### Volume Mounts
- `/app/uploads` - User uploaded files
- `/app/logs` - Application logs (JSON structured)
- `/app/backend/faiss_index` - Vector database

### Port Mapping
Default: `localhost:8080:8080`

Custom port: `./docker-build-run.ps1 --port 9000`

## Operations

### Build Only
```powershell
.\docker-build-run.ps1 --build-only
```

### Run Only (Skip build)
```powershell
.\docker-build-run.ps1 --run-only
```

### View Logs
```bash
docker logs -f <container-id>
```

### Stop Container
```bash
docker stop <container-id>
```

### Inspect Health
```bash
curl http://localhost:8080/api/health | jq
```

## Production Checklist

- [ ] .env file configured with production keys
- [ ] Firewall rules allow port 8080 access
- [ ] Sufficient disk space for uploads and logs
- [ ] Docker resource limits configured (memory/CPU)
- [ ] Monitoring/alerting set up
- [ ] Backup strategy for uploads and FAISS index
- [ ] API key rotation schedule
- [ ] Log retention policy configured

## Troubleshooting

### Port Already in Use
```powershell
# Use different port
.\docker-build-run.ps1 --port 9000
```

### Docker Build Fails
```bash
# Check Docker daemon
docker ps

# Clear build cache
docker system prune

# Rebuild
.\docker-build-run.ps1 --build-only
```

### Application Won't Start
```bash
# Check logs
docker logs <container-id>

# Verify .env file
cat .env

# Check dependencies
curl http://localhost:8080/api/health
```

### High Memory Usage
```bash
# Monitor container
docker stats <container-id>

# Reduce log level
# In .env: LOG_LEVEL=WARNING
```

## Scaling

### Multiple Instances
For horizontal scaling, consider:
- Load balancer (nginx, HAProxy)
- Shared volume for FAISS index
- Centralized logging (ELK stack)
- Session storage (Redis instead of in-memory cache)

### Performance Optimization
- Use SSD for uploads directory
- Configure FAISS with GPU support (if available)
- Increase rate limiting for production
- Enable HTTP/2 with reverse proxy

## Security

- ✅ All user inputs validated
- ✅ Error messages sanitized
- ✅ Authentication required for all APIs
- ✅ File upload restrictions (type, size)
- ✅ Code execution safely sandboxed with timeouts
- ✅ Rate limiting enabled per user/IP
- ✅ Structured logging for audit trail

## Monitoring

The application provides:
- `/api/health` - Full health check with dependencies
- `/api/health/ready` - Kubernetes readiness probe
- Structured JSON logs with request IDs
- Performance metrics (latency, error rates)
- Rate limit headers in responses

### Sample Health Check Response
```json
{
  "status": "healthy",
  "app": "Autonomous Data Scientist Agent",
  "version": "0.1.0",
  "dependencies": {
    "rag_service": true,
    "uploads_dir": true
  }
}
```

## Maintenance

### Regular Tasks
- Monitor logs for errors
- Check disk usage
- Review rate limit metrics
- Backup uploads and FAISS index
- Update dependencies monthly

### Cleanup
```bash
# Remove old Docker images
docker image prune -a

# Cleanup old logs
# Configure in LOG_LEVEL or manual cleanup
```

---

**Author:** OMCHOKSKI  
**Repository:** https://github.com/OMCHOKSKI108/agentic-rag-data-analyst
