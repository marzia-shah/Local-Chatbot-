# Smart Launcher System Documentation

## Overview
The AI Document Chatbot includes a smart launcher system that automatically handles port conflicts and ensures smooth startup of all required services.

## Available Launchers

### Windows
- **`start_chatbot_smart.bat`** - Enhanced smart launcher with automatic port conflict resolution
- **`fix_ports_enhanced.bat`** - Standalone port conflict resolver

### Linux/macOS
- **`start_chatbot_smart.sh`** - Enhanced smart launcher with automatic port conflict resolution
- **`fix_ports_enhanced.sh`** - Standalone port conflict resolver

## Features

### Automatic Port Conflict Resolution
The smart launchers automatically check and resolve conflicts on the following ports:
- **Port 11434** - Ollama AI service
- **Port 8003** - FastAPI application (primary)
- **Port 8002** - FastAPI fallback port
- **Port 5000** - Flask fallback port

### Service Health Monitoring
- Verifies Ollama service is running and accessible
- Checks if main.py exists before attempting to start
- Validates virtual environment availability
- Provides detailed error messages and troubleshooting tips

### Enhanced Error Handling
- Graceful handling of missing dependencies
- Clear error messages with actionable solutions
- Automatic fallback to system Python if virtual environment is not found
- Exit codes for integration with other scripts

## Usage

### Windows
```batch
# Start the chatbot with smart launcher
start_chatbot_smart.bat

# Or resolve port conflicts only
fix_ports_enhanced.bat
```

### Linux/macOS
```bash
# Make scripts executable (first time only)
chmod +x start_chatbot_smart.sh
chmod +x fix_ports_enhanced.sh

# Start the chatbot with smart launcher
./start_chatbot_smart.sh

# Or resolve port conflicts only
./fix_ports_enhanced.sh
```

## Smart Launcher Process Flow

### 1. Port Conflict Resolution (Step 1/4)
- Scans for processes using ports 11434, 8002, 8003, and 5000
- Terminates conflicting processes
- Waits for ports to be released

### 2. Service Preparation (Step 2/4)
- Waits 5 seconds for complete port release
- Prepares environment for service startup

### 3. Environment Setup (Step 3/4)
- Detects and activates virtual environment (`venv` or `.venv`)
- Falls back to system Python if no virtual environment found
- Starts Ollama service in background
- Monitors Ollama startup with timeout (20 seconds)

### 4. Application Launch (Step 4/4)
- Validates main.py exists
- Starts FastAPI application
- Provides success confirmation with access URL

## Troubleshooting

### Common Issues and Solutions

#### Port Still in Use
If ports remain occupied after running the smart launcher:
1. Run the enhanced port resolver: `fix_ports_enhanced.bat/.sh`
2. Wait 30 seconds and try again
3. Manually check for persistent processes: `netstat -ano | find ":8003"` (Windows) or `lsof -i :8003` (Linux/macOS)

#### Virtual Environment Not Found
The smart launcher will automatically use system Python, but for optimal performance:
1. Create a virtual environment: `python -m venv venv`
2. Activate it and install dependencies: `pip install -r requirements.txt`

#### Ollama Service Issues
If Ollama fails to start:
1. Ensure Ollama is installed: `ollama --version`
2. Try manual start: `ollama serve`
3. Check firewall settings for port 11434

#### Application Startup Errors
If the FastAPI application fails to start:
1. Verify all dependencies are installed: `pip install -r requirements.txt`
2. Check Python version compatibility (3.8+)
3. Ensure main.py is in the current directory
4. Review error messages for specific issues

## Configuration

### Port Configuration
The application uses port 8003 by default. To change this:
1. Edit `main.py` and modify the uvicorn.run() call
2. Update the smart launcher scripts to check the new port
3. Update any firewall rules or proxy configurations

### Virtual Environment Paths
The smart launcher checks for virtual environments in this order:
1. `venv/` (Windows: `venv\Scripts\activate.bat`, Linux/macOS: `venv/bin/activate`)
2. `.venv/` (Windows: `.venv\Scripts\activate.bat`, Linux/macOS: `.venv/bin/activate`)
3. System Python (fallback)

## Integration with Other Tools

### CI/CD Integration
The smart launcher returns appropriate exit codes:
- **0** - Success
- **1** - Error (missing files, startup failure, etc.)

### Monitoring Integration
The launcher provides structured output that can be parsed by monitoring tools:
- Progress indicators: `[1/4]`, `[2/4]`, etc.
- Status symbols: `✓` (success), `⚠` (warning), `❌` (error)
- Color-coded output (Linux/macOS)

## Security Considerations

### Process Termination
The smart launcher forcefully terminates processes on required ports. Ensure:
- No critical services are running on ports 8002, 8003, 11434, or 5000
- Regular backups of important data
- Proper shutdown procedures for other applications

### Network Security
- The application binds to all interfaces (0.0.0.0) for accessibility
- Consider firewall rules for production deployments
- Use HTTPS in production environments

## Performance Optimization

### Startup Time
- Virtual environment activation: ~1-2 seconds
- Port conflict resolution: ~3-5 seconds
- Ollama service startup: ~5-15 seconds
- FastAPI application startup: ~2-5 seconds
- **Total typical startup time: 10-25 seconds**

### Resource Usage
- Memory: ~200-500MB (depending on loaded models)
- CPU: Moderate during startup, low during idle
- Disk: Minimal I/O after initial startup

## Advanced Usage

### Custom Environment Variables
Set these before running the smart launcher:
```bash
export OLLAMA_HOST=0.0.0.0:11434  # Custom Ollama host
export PYTHONPATH=/path/to/custom/modules  # Custom Python path
```

### Debug Mode
For detailed debugging, modify the launcher scripts to add verbose output:
- Windows: Add `echo` statements before each major operation
- Linux/macOS: Add `set -x` at the beginning for command tracing

### Automated Deployment
For automated deployments, use the smart launcher in scripts:
```bash
#!/bin/bash
cd /path/to/chatbot
./start_chatbot_smart.sh
if [ $? -eq 0 ]; then
    echo "Chatbot started successfully"
else
    echo "Failed to start chatbot"
    exit 1
fi
```

## Version History

### v2.0 (Current)
- Enhanced port conflict resolution
- Improved error handling and user feedback
- Support for multiple virtual environment locations
- Comprehensive health checking
- Structured progress reporting

### v1.0 (Previous)
- Basic port conflict resolution
- Simple Ollama and FastAPI startup
- Limited error handling

## Support

For issues with the smart launcher system:
1. Check the troubleshooting section above
2. Review application logs for specific error messages
3. Ensure all prerequisites are installed
4. Test individual components (Ollama, Python, dependencies)

The smart launcher system is designed to provide a seamless startup experience while handling common deployment challenges automatically.