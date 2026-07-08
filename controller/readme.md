# Pipeline Controller

The Controller is the orchestration layer for the AI Tutor Engine.

Responsibilities:

- Register pipelines
- Execute pipelines
- Manage dependencies
- Track execution status
- Handle retries
- Queue jobs
- Log events
- Return results to the FastAPI backend

The backend communicates only with the Controller. Pipelines do not communicate directly with the backend.

Status: 🚧 Under Development
