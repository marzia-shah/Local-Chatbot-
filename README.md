Lotte Chemical AI Document Assistant

A powerful, locally-hosted AI chatbot for document-based question answering, specifically designed for Lotte Chemical's document processing needs.

Features
-  Multi-format Support: PDF and Word document processing
-  Local AI: Powered by Ollama for complete privacy
- Smart Search: Semantic search with FAISS vector indexing
-  Conversational AI: Natural language question answering
-  Monitoring: Built-in health checks and performance metrics
-  Secure: Fully offline operation, no data leaves your system
-  Company-specific: Pre-configured with Lotte Chemical information
-  Auto-Conflict Resolution: Smart port conflict handling

Quick Start

Windows
1. Run setup: Double-click `setup.bat` as Administrator
2. Start chatbot: Double-click `start_chatbot_smart.bat` (recommended) or `start_chatbot.bat`
3. Open browser: Go to http://localhost:8002

Linux/macOS
1. Run setup: `chmod +x *.sh && ./setup.sh`
2. Start chatbot: `./start_chatbot_smart.sh` (recommended) or `./start_chatbot.sh`
3. Open browser: Go to http://localhost:8002

Having Port Conflicts?
If you see "port already in use" errors:
- Windows: Run `fix_ports.bat` then try again
- Linux/macOS: Run `./fix_ports.sh` then try again
- Or use: The smart launchers (`*_smart.*`) automatically handle conflicts!

Prerequisites

- Python 3.8+
- 8GB RAM (16GB recommended)
- 10GB free disk space
- Internet connection (for initial setup)

Manual Installation

See `INSTALLATION_GUIDE.md` for detailed step-by-step instructions.

API Endpoints

- Main App: http://localhost:8002
- Health Check: http://localhost:8002/health
- Metrics: http://localhost:8002/metrics
- Chat API: POST http://localhost:8002/chat
- Upload API: POST http://localhost:8002/upload

Configuration

The chatbot works out-of-the-box but can be customized:

- Port: Change in `main.py` (default: 8002)
- AI Model: Modify `DEFAULT_MODEL` in `main.py`
- Chunk Size: Adjust `CHUNK_SIZE` for document processing
- Upload Limits: Configure `MAX_FILE_SIZE`

Project Structure


chatbot/
├── main.py                      # Main application
├── requirements.txt             # Dependencies
├── setup.bat/.sh               # Automated setup
├── start_chatbot.bat/.sh       # Basic start scripts
├── start_chatbot_smart.bat/.sh # Smart start scripts (recommended)
├── fix_ports.bat/.sh           # Port conflict resolvers
├── PORT_CONFLICT_RESOLVER.md   # Detailed conflict resolution guide
├── utils/                      # Utility modules
├── templates/                  # Web interface
├── uploads/                    # Document storage
└── logs/                       # Application logs
```

Usage

1. Upload Documents: Use the web interface to upload PDF/Word files
2. Ask Questions: Type questions about your documents
3. Get Answers: Receive AI-powered responses with source references
4. Monitor System: Check health and metrics endpoints

Security

- All processing happens locally
- No data sent to external servers
- Documents stored securely on your system
- SQLite database for chat history

Troubleshooting

Common Issues:

Port Conflicts: 
- Use `fix_ports.bat` (Windows) or `./fix_ports.sh` (Linux/macOS)
- Or use the smart launchers that auto-resolve conflicts

Ollama not found: Install from https://ollama.ai

Memory issues: Use smaller AI models

Permission errors: Run as administrator/sudo

See `PORT_CONFLICT_RESOLVER.md` for detailed port conflict resolution.
See `INSTALLATION_GUIDE.md` for other troubleshooting.

Monitoring

The chatbot includes comprehensive monitoring:

- Health Checks: Database, disk space, memory, Ollama status
- Performance Metrics: Response times, request counts, error rates
- Logging: Detailed logs for debugging and analysis

 Updates

To update the chatbot:
1. Replace files with new versions
2. Run `pip install -r requirements.txt --upgrade`
3. Restart the service

Support

For technical support:
1. Check the logs in `logs/chatbot.log`
2. Verify system requirements
3. Ensure Ollama is running
4. Review the installation guide
5. For port conflicts, see `PORT_CONFLICT_RESOLVER.md`

---

**🏢 Built for Lotte Chemical - Secure, Local, and Powerful AI Document Processing**