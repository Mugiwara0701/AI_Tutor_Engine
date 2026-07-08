├── backend/ # FastAPI Dashboard Backend
│ ├── app/
│ │ ├── api/
│ │ │ ├── v1/
│ │ │ │ ├── auth.py
│ │ │ │ ├── users.py
│ │ │ │ ├── projects.py
│ │ │ │ ├── chapters.py
│ │ │ │ ├── pipeline.py # Endpoints that call Controller
│ │ │ │ └── generation.py
│ │ │ │
│ │ │ └── router.py
│ │ │
│ │ ├── core/
│ │ │ ├── config.py
│ │ │ ├── security.py
│ │ │ ├── logging.py
│ │ │ └── settings.py
│ │ │
│ │ ├── database/
│ │ │ ├── connection.py
│ │ │ ├── models/
│ │ │ └── migrations/
│ │ │
│ │ ├── schemas/
│ │ ├── services/
│ │ ├── utils/
│ │ └── main.py
│ │
│ ├── tests/
│ ├── requirements.txt
│ └── README.md
