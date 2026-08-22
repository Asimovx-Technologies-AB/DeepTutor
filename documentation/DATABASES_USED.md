# 🗄️ Databases Used in DeepTutor (Simple Guide)

This document explains all the databases and storage systems used in **DeepTutor** in simple, beginner-friendly terms.

---

## 📊 Quick Overview Table

| Database / Storage | Type | What It Stores | Where It Runs |
| :--- | :--- | :--- | :--- |
| **1. PostgreSQL (Neon DB)** | Relational DB (SQL) | Users, Passwords, Chat History, Quizzes, Flashcards, Notes, Progress | Cloud (Neon Serverless Postgres) *(or local SQLite)* |
| **2. Pinecone** | Vector Database | Math & Science textbook chunk embeddings for semantic AI search | Cloud (Pinecone Vector Index) *(fallback: FAISS / Chroma)* |
| **3. LightRAG (JSON-KV)** | Knowledge Graph Store | Subject entities, concepts, relationships, and study graph triplets | Local Disk (`./lightrag_data`) |
| **4. AWS S3** | Cloud Object Storage | Raw PDF textbooks and uploaded student study material files | Cloud (AWS S3 Bucket: `deeptutor-documents-storage`) |
| **5. Search & VLM Cache** | Key-Value / Disk Cache | Verified Google/Serper diagram images & Gemini Vision transcriptions | Local Disk (`./image_search_cache`, `./vlm_cache`) |

---

## 1. 🐘 PostgreSQL (Main App Database)
* **What is it?** The core structured relational database.
* **Why we use it:** It keeps all student accounts and study data safe, organized, and connected with foreign keys.
* **What it stores:**
  - 👤 **Users:** Email, hashed passwords, full names, account roles.
  - 💬 **Chat Sessions & Messages:** All student questions, AI tutor responses, and sources.
  - 📄 **Documents Metadata:** File names, upload dates, page counts, processing status.
  - 🎯 **Quizzes & Flashcards:** Questions, options, student test scores, mastered cards.
  - 🏆 **Leaderboards & Progress:** XP points, study streaks, completion percentages.
* **Configuration:** `.env` $\rightarrow$ `DATABASE_URL=postgresql://...`

---

## 2. 🌲 Pinecone (Vector Database)
* **What is it?** A specialized database for AI similarity search.
* **Why we use it:** Traditional databases search for exact words (like Ctrl+F). Pinecone searches by **meaning/context** (Semantic Search).
* **How it works:**
  1. Textbooks are split into small readable chunks (350–650 words).
  2. Gemini converts each chunk into numbers called an **Embedding Vector**.
  3. When a student asks *"How does water evaporate?"*, Pinecone finds the closest textbook passages in $<10\text{ms}$.
* **Fallback Options:** Local **FAISS (HNSW)** or **ChromaDB**.
* **Configuration:** `.env` $\rightarrow$ `VECTOR_STORE_BACKEND=pinecone`

---

## 3. 🕸️ LightRAG / Graph Store (Knowledge Graph)
* **What is it?** A network graph database of connected concepts.
* **Why we use it:** To connect related ideas across different textbook chapters.
* **What it stores:**
  - **Entities:** *Photosynthesis*, *Chlorophyll*, *Sunlight*, *Glucose*.
  - **Relationships:** *(Chlorophyll $\rightarrow$ absorbs $\rightarrow$ Sunlight)*, *(Photosynthesis $\rightarrow$ produces $\rightarrow$ Glucose)*.
* **Storage Location:** `./lightrag_data/` and `./graph_data/`

---

## 4. ☁️ AWS S3 (Cloud File Storage)
* **What is it?** Secure cloud bucket storage for large files.
* **Why we use it:** Databases should not store massive 50MB–500MB PDF files directly. S3 stores the actual PDF file, while PostgreSQL stores the link/URL to it.
* **What it stores:**
  - Kerala SCERT Class 10 Textbooks (Math, Physics, Chemistry).
  - Student-uploaded PDF study notes and exam papers.
* **Configuration:** `.env` $\rightarrow$ `AWS_S3_BUCKET_NAME=deeptutor-documents-storage`

---

## 5. ⚡ Disk & Memory Caches
* **What is it?** High-speed local caches to prevent repeated API calls and save money.
* **What it stores:**
  - **`image_search_cache/`**: AI-verified diagram images from Serper.dev so the same topic doesn't re-bill Google search API.
  - **`vlm_cache/`**: Extracted formulas and diagram descriptions from Gemini Flash Vision.
  - **`Query Cache`**: Frequently asked questions returned instantly with 0ms latency.

---

## 🔄 How They All Work Together (Step-by-Step)

```
Student asks: "Explain Support Vector Machines with diagram"
 │
 ├── 1. PostgreSQL ──────────► Saves the student's question into chat history.
 │
 ├── 2. Pinecone Vector DB ──► Finds top 4 relevant passages from the ML textbook.
 │
 ├── 3. Knowledge Graph ─────► Finds connected entities (Margin, Hyperplane, Kernel).
 │
 ├── 4. Serper + Gemini VLM ─► Searches & verifies clean educational diagrams.
 │
 └── 5. AI Tutor (Gemini) ───► Combines everything into an easy step-by-step lesson with diagram!
```
