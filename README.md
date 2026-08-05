# DeepTutor — AI-Powered GraphRAG Learning Platform

**DeepTutor** is a modern, AI-powered tutor application built with a **FastAPI + GraphRAG** backend (local Ollama LLM + ChromaDB vector search + knowledge graph) and an interactive **React + Vite** frontend.

---

## 🌟 Key Features

- 🧠 **GraphRAG AI Tutor**: Interactive chat with local Ollama LLM backed by document vector embeddings + Knowledge Graph context.
- 📊 **Interactive Knowledge Graph Visualizer**: Canvas-based 2D force-directed graph with drag, zoom, pan, and entity detail inspection.
- 🎮 **AI Quiz Engine**: Custom topic selection (Entire PDF or specific concept), variable difficulty, answer feedback, explanations, and streak multipliers (no lives scheme).
- 🎴 **Smart Flashcards**: 3D flippable study cards with Text-To-Speech audio pronunciation, hint reveal, keyboard shortcuts (`Space`, `Arrow` keys), and deck grid view.
- 📅 **AI Study Roadmap Engine**: Upload document material + set target completion/exam date. Calculates days remaining and constructs a structured day-by-day study schedule with interactive progress checklists.
- 📈 **Real-Time Progress Analytics**: Database-backed metrics tracking chat sessions, average quiz scores, topics studied, active day streaks, and learning calendars.
- 📱 **Left Sidebar Navigation**: Responsive layout with quick tutor ask bar and profile management.

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** & `npm`
- **Ollama** running locally (`ollama serve`) with `llama3.2` or model configured in backend.

### 1. Backend Setup

```bash
cd backend
start.bat
```
*Or manually:*
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 🛠️ Technology Stack

- **Frontend**: React 19, TypeScript, Vite, TailwindCSS v4, Framer Motion, Recharts, Lucide Icons.
- **Backend**: FastAPI, SQLAlchemy, SQLite, ChromaDB, Ollama Python Client, NetworkX.
