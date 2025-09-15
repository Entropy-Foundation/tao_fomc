# FOMC Multi-Server Setup

This document describes the multi-server implementation of the FOMC interest rate extraction and BLS signing system.

## Overview

Instead of running a single web server, this setup runs **4 independent web servers**, each with:
- Its own BLS private key
- Independent text processing
- Unique BLS signatures for the same input
- Same rate extraction results (when working correctly)

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Server 1      │    │   Server 2      │    │   Server 3      │    │   Server 4      │
│   Port: 8001    │    │   Port: 8002    │    │   Port: 8003    │    │   Port: 8004    │
│   BLS Key: K1   │    │   BLS Key: K2   │    │   BLS Key: K3   │    │   BLS Key: K4   │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         └───────────────────────┼───────────────────────┼───────────────────────┘
                                 │                       │
                         ┌───────▼───────────────────────▼───────┐
                         │        Same Input Text               │
                         │   "Fed raises rates by 25bp"        │
                         └─────────────────────────────────────┘
                                 │
                         ┌───────▼───────┐
                         │ Same Output:  │
                         │ rate_change=25│
                         │ Different     │
                         │ Signatures    │
                         └───────────────┘
```

## Files Structure

### Core Files
- `multi_web_api.py` - Multi-server web API implementation
- `network_config.py` - Network configuration management
- `setup_keys.py` - BLS key generation for all servers
- `run_multi_servers.py` - Server orchestration script
- `deploy_multi_servers.sh` - Deployment automation script
- `test_multi_servers.py` - Comprehensive testing suite

### Configuration Files
- `network_config.json` - Server network configuration (auto-generated)
- `keys/server_N.env` - Individual server environment files (auto-generated)
- `keys/bls_private_keys.json` - Key reference file (auto-generated)

### Legacy Files (still functional)
- `web_api.py` - Original single-server implementation
- `env.template` - Environment template (updated with multi-server info)

## Quick Start

### 1. Setup and Deploy (Automated)
```bash
# Full automated deployment
./deploy_multi_servers.sh

# Or step by step:
./deploy_multi_servers.sh setup    # Setup only
./deploy_multi_servers.sh start    # Start servers only
```

### 2. Manual Setup (if needed)
```bash
# Generate keys and configuration
python3 setup_keys.py

# Start all servers
python3 run_multi_servers.py

# Test the setup
python3 test_multi_servers.py
```

### 3. Health Check
```bash
# Check server health
./deploy_multi_servers.sh health
# or
python3 run_multi_servers.py health
```

## API Endpoints

Each server runs independently on its own port:

### Server URLs
- **Server 1**: http://127.0.0.1:8001
- **Server 2**: http://127.0.0.1:8002  
- **Server 3**: http://127.0.0.1:8003
- **Server 4**: http://127.0.0.1:8004

### Endpoints (same for all servers)
- `GET /` - Server information
- `GET /health` - Health check
- `POST /extract` - Extract rate and sign with BLS

### Example API Usage

```bash
# Test Server 1
curl -X POST http://127.0.0.1:8001/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "The Fed raised rates by 25 basis points"}'

# Test Server 2 (same input, different signature)
curl -X POST http://127.0.0.1:8002/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "The Fed raised rates by 25 basis points"}'
```

### Expected Response Format
```json
{
  "rate_change": 25,
  "bls_signature": "a1b2c3d4e5f6...",
  "server_id": 1
}
```

## Key Features

### 1. Independent Processing
- Each server processes text independently
- Same LLM extraction logic
- Same rate detection results
- Different BLS signatures due to different private keys

### 2. Fault Tolerance
- If one server fails, others continue working
- No single point of failure
- Easy to restart individual servers

### 3. Load Distribution
- Requests can be distributed across servers
- Each server handles its own load
- Horizontal scaling capability

### 4. Security
- Each server has its own BLS private key
- Keys are stored in separate environment files
- No shared cryptographic material

## Configuration

### Network Configuration (`network_config.json`)
```json
{
  "servers": [
    {"id": 1, "host": "127.0.0.1", "port": 8001},
    {"id": 2, "host": "127.0.0.1", "port": 8002},
    {"id": 3, "host": "127.0.0.1", "port": 8003},
    {"id": 4, "host": "127.0.0.1", "port": 8004}
  ]
}
```

### Server Environment Files (`keys/server_N.env`)
```bash
# BLS private key for server_1
BLS_PRIVATE_KEY=a1b2c3d4e5f6789...
```

## Testing

### Automated Testing
```bash
# Run comprehensive test suite
python3 test_multi_servers.py
```

### Manual Testing
```bash
# Test individual server
curl http://127.0.0.1:8001/health

# Test rate extraction
curl -X POST http://127.0.0.1:8001/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Fed cuts rates by 50bp"}'
```

### Test Scenarios
1. **Health Check** - All servers respond to health checks
2. **Rate Increase** - All servers detect rate increases correctly
3. **Rate Decrease** - All servers detect rate decreases correctly  
4. **No Change** - All servers handle no-change scenarios
5. **Signature Uniqueness** - Each server produces different signatures
6. **Consistency** - All servers produce same rate extraction results

## Troubleshooting

### Common Issues

#### 1. Port Already in Use
```bash
# Check what's using the ports
lsof -i :8001
lsof -i :8002
lsof -i :8003
lsof -i :8004

# Kill processes if needed
kill -9 <PID>
```

#### 2. Missing Dependencies
```bash
# Install required packages
pip3 install fastapi uvicorn py-ecc requests pydantic aptos-sdk
```

#### 3. BLS Key Issues
```bash
# Regenerate keys
python3 setup_keys.py

# Check key files exist
ls -la keys/
```

#### 4. Server Not Starting
```bash
# Check logs for specific server
python3 multi_web_api.py 1  # Start server 1 manually

# Check network configuration
cat network_config.json
```

### Log Analysis
Each server logs with its server ID prefix:
```
[Server 1] INFO - Server 1 initialized on 127.0.0.1:8001
[Server 2] INFO - Server 2 initialized on 127.0.0.1:8002
```

## Migration from Single Server

### Backward Compatibility
- Original `web_api.py` still works
- Original `.env` file still supported
- No breaking changes to existing functionality

### Migration Steps
1. Keep existing single server running
2. Deploy multi-server setup on different ports
3. Test multi-server functionality
4. Gradually migrate traffic
5. Decommission single server when ready

## Production Deployment

### Security Considerations
- Use different hosts for each server in production
- Secure BLS private keys properly
- Use HTTPS in production
- Implement proper firewall rules
- Monitor server health continuously

### Scaling
- Can run servers on different machines
- Update `network_config.json` with actual IP addresses
- Use load balancer for request distribution
- Monitor resource usage per server

### Monitoring
- Health check endpoints for monitoring
- Log aggregation across servers
- Performance metrics per server
- Alert on server failures

## Development

### Adding More Servers
1. Update `setup_keys.py` to generate more keys
2. Update `network_config.py` default configuration
3. Update `deploy_multi_servers.sh` validation
4. Update tests in `test_multi_servers.py`

### Customization
- Modify server ports in `network_config.json`
- Change server hosts for distributed deployment
- Customize logging and monitoring
- Add additional API endpoints

## Support

For issues or questions:
1. Check this README
2. Run the test suite: `python3 test_multi_servers.py`
3. Check server logs for error messages
4. Verify all prerequisites are installed
5. Ensure all key files are properly generated

---

**Note**: This multi-server setup is designed to provide redundancy and load distribution while maintaining the same core functionality as the original single-server implementation.