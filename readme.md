# AI Tutor Engine

> An end-to-end AI-powered educational content generation platform that transforms textbooks into structured, interactive, and multimedia learning experiences.

---

# Overview

AI Tutor Engine is a modular AI platform designed to automate the complete educational content generation workflow. Starting from textbook PDFs, the system extracts educational knowledge, builds a structured learning representation, generates teaching content, produces multimedia assets, and creates complete learning packages.

The platform is designed around independent pipelines orchestrated by a central controller, making it scalable, maintainable, and extensible.

---

# Project Objectives

The AI Tutor Engine aims to:

- Extract structured educational knowledge from textbooks
- Build standardized educational knowledge representations
- Generate high-quality AI prompts for content creation
- Produce educational assets and packaged outputs
- Generate multimedia learning content
- Support multilingual speech synthesis and transcription
- Provide a modern dashboard for managing the entire workflow

---

# System Architecture

```text
                          Frontend Dashboard
                                 │
                                 ▼
                     FastAPI Dashboard Backend
                                 │
                                 ▼
                      Pipeline Controller
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
 Phase 1                  Phase 2                 Phase 3
 Book Extraction          Master JSON            Prompt Builder
        │                        │                        │
        └──────────────┬─────────┴──────────────┬─────────┘
                       ▼                        ▼
                  Phase 4                 Phase 5
                 ZIP Builder         Video Generator
                       │
                       ▼
                  Phase 6
                 STT / TTS
```

---

# Repository Structure

```text
AI_TUTOR_ENGINE/
│
├── frontend/              # React + Vite Dashboard
├── backend/               # FastAPI Backend
├── pipelines/             # AI Processing Pipelines
└── controller/            # Pipeline Orchestrator
```

---

# Project Components

## Frontend

The frontend provides the user interface for interacting with the platform.

Features include:

- Authentication
- Dashboard
- Project Management
- Book Upload
- Pipeline Monitoring
- Generated Content Preview
- Downloads
- User Settings

Technology:

- React
- Vite
- Tailwind CSS
- TypeScript (Planned)

---

## Backend

The backend is developed using **FastAPI** and serves as the application's API layer.

Responsibilities include:

- Authentication
- Project Management
- Database Operations
- File Management
- WebSocket Communication
- API Services
- User Management
- Calling the Pipeline Controller

---

## Controller

The Controller is the orchestration layer of the platform.

Responsibilities:

- Pipeline Registration
- Pipeline Scheduling
- Dependency Management
- Job Execution
- Queue Management
- Status Tracking
- Logging
- Error Handling

The backend communicates only with the Controller.

---

# AI Pipelines

The processing workflow consists of six independent pipelines.

---

## Phase 1 – Book Extraction

Input:

- Educational PDF Books

Output:

- Structured Educational Knowledge
- Topics
- Figures
- Tables
- Equations
- Educational Metadata

---

## Phase 2 – Master JSON

Generates the canonical educational representation used throughout the platform.

Output:

- Master JSON
- Learning Graph
- Metadata
- Educational Relationships

---

## Phase 3 – Prompt Builder

Creates optimized AI prompts from the Master JSON for downstream generation tasks.

Output:

- Structured Prompt Packages
- Prompt Templates
- Generation Instructions

---

## Phase 4 – ZIP Builder

Packages prompts, assets, manifests, and metadata into distributable bundles.

Output:

- ZIP Packages
- Asset Manifests
- Generation Bundles

---

## Phase 5 – Video Generator

Generates multimedia educational content.

Output:

- Educational Videos
- Animations
- Visual Assets
- Presentation Materials

---

## Phase 6 – STT / TTS

Processes speech generation and recognition.

Output:

- Narration
- Audio
- Subtitles
- Speech Recognition
- Multilingual Voice Assets

---

# Processing Workflow

```text
Educational Book (PDF)
          │
          ▼
Book Extraction
          │
          ▼
Master JSON
          │
          ▼
Prompt Builder
          │
          ▼
ZIP Builder
          │
          ▼
Video Generator
          │
          ▼
STT / TTS
          │
          ▼
Final Educational Package
```

---

# Technology Stack

## Frontend

- React
- Vite
- Tailwind CSS
- TypeScript (Planned)

## Backend

- FastAPI
- Python
- SQLAlchemy (Planned)
- Alembic (Planned)
- WebSockets

## AI

- Qwen Models
- Vision Language Models (VLM)
- Large Language Models (LLM)

## Data Processing

- PyMuPDF
- OCR
- OpenCV
- FFmpeg

---

# Current Development Status

| Component                 | Status                |
| ------------------------- | --------------------- |
| Frontend Dashboard        | 🚧 In Development     |
| FastAPI Backend           | 🚧 In Development     |
| Controller                | 🚧 Planned            |
| Phase 1 – Book Extraction | 🚧 Active Development |
| Phase 2 – Master JSON     | 📋 Planned            |
| Phase 3 – Prompt Builder  | 📋 Planned            |
| Phase 4 – ZIP Builder     | 📋 Planned            |
| Phase 5 – Video Generator | 📋 Planned            |
| Phase 6 – STT / TTS       | 📋 Planned            |

---

# Design Principles

- Modular Architecture
- Independent Pipelines
- Reusable Components
- Scalable Design
- High Maintainability
- Clean Separation of Concerns
- Extensible AI Framework

---

# Future Roadmap

- Distributed Pipeline Execution
- Multi-GPU Processing
- Cloud Deployment
- Multi-language Support
- AI Tutor Chat Interface
- Assessment Generation
- Adaptive Learning
- LMS Integration
- API for Third-Party Integrations

---

# License

This project is currently under active development.

License information will be added before the first public release.
