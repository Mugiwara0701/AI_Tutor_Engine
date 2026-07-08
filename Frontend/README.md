# Frontend Dashboard

## Overview

The Frontend Dashboard is the web application for the AI Tutor Engine. It provides an intuitive interface for interacting with the platform, allowing users to manage projects, upload educational resources, monitor processing workflows, and access generated learning content.

The application is built using React and Vite with a focus on performance, scalability, and a modern user experience.

---

## Responsibilities

The frontend is responsible for:

- User Authentication Interface
- Dashboard
- Project Management
- PDF Upload
- Pipeline Execution Interface
- Real-Time Progress Monitoring
- Generated Content Preview
- Download Management
- User Profile & Settings
- Notifications

---

## Planned Features

### Authentication

- Login
- Registration
- Forgot Password
- User Profile

---

### Dashboard

- Overview Dashboard
- Recent Projects
- Processing Status
- Activity Feed
- Quick Actions

---

### Project Management

- Create Project
- View Projects
- Edit Project
- Delete Project
- Search & Filter

---

### Book Management

- Upload PDF
- Manage Uploaded Books
- Chapter Selection
- Metadata Display

---

### Pipeline Interface

Provide an interface to:

- Start Processing
- Pause (planned)
- Resume (planned)
- Cancel Processing
- View Processing History

---

### Monitoring

- Live Progress
- Current Processing Stage
- Status Indicators
- Error Messages
- Processing Logs

---

### Content Preview

Preview generated outputs including:

- Knowledge Graph
- Master JSON
- Generated Prompts
- Videos
- Audio
- Assets

---

### Downloads

Download generated files including:

- JSON
- ZIP Packages
- Videos
- Audio
- Other Generated Assets

---

### User Settings

- Profile
- Password
- Preferences
- Theme (Planned)

---

## Technology Stack

- React
- Vite
- TypeScript (Planned)
- Tailwind CSS
- React Router
- Axios
- Zustand / Redux (TBD)
- TanStack Query (Planned)
- Framer Motion

---

## Planned Folder Structure

```text
frontend/
│
├── public/
│
├── src/
│   ├── assets/
│   ├── components/
│   ├── features/
│   ├── hooks/
│   ├── layouts/
│   ├── pages/
│   ├── routes/
│   ├── services/
│   ├── store/
│   ├── styles/
│   ├── types/
│   ├── utils/
│   ├── App.tsx
│   └── main.tsx
│
├── package.json
├── vite.config.js
└── README.md
```

---

## Design Goals

- Clean and modern interface
- Responsive design
- High performance
- Reusable components
- Scalable architecture
- Accessibility
- Consistent user experience

---

## Development Status

🚧 Under Development

---

## Future Enhancements

- Dark / Light Theme
- Multi-language Support
- Progressive Web App (PWA)
- Offline Support
- Desktop Application
- Notification Center
- Advanced Analytics
- AI Assistant Integration
