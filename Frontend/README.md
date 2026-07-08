# AI Tutor — Frontend

React + Tailwind CSS frontend for the AI-powered educational content
management platform.

## Structure

This project follows a **feature-based** architecture. Each phase from the
original spec lives under `src/features/<feature-name>/` with its own
`pages/`, `components/`, `hooks/`, and mock `data/`.

- `src/layouts` — persistent shell (Sidebar + Navbar) and auth layout
- `src/components/ui` — shared design-system primitives (StatusBadge,
  DataTable, MetricCard, etc.)
- `src/features` — one folder per phase/page (auth, library, topics,
  learning-graph, sub-topic-order, prompt-studio, zip-manager,
  pipeline-monitor, storage-explorer, analytics, global-search)
- `src/lib/mockApiClient.js` — simulated API layer; swap for real
  endpoints later without touching feature code
- `src/context` — Auth, Theme, and Sidebar state

## Getting started

```bash
npm install
npm run dev
```

## Build order

Phases are built in the same order as the original spec (Auth → Layout →
Library → Topic Detail → Learning Graph → Sub Topic Order → Prompt Studio
→ ZIP Manager → Pipeline Monitor → Storage Explorer → Analytics → Global
Search), with shared UI components built first in Phase 1–2.
