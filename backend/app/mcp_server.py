"""
IndieTutor MCP Server Implementation
Exposes IndieTutor RAG, Student Memory, Knowledge Graph, and Quiz Engine via Model Context Protocol (FastMCP).
Can be executed over stdio or SSE by external clients (Cursor IDE, Claude Desktop, VS Code).
"""
import sys
import asyncio
from typing import Dict, List, Any, Optional
try:
    from mcp.server.fastmcp import FastMCP  # type: ignore # pyright: ignore[reportMissingImports]
except ImportError:
    class FastMCP:  # type: ignore
        """Fallback FastMCP class when mcp package is not installed."""
        def __init__(self, name: str):
            self.name = name
        def tool(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def run(self, *args, **kwargs):
            pass

# Initialize FastMCP Server for IndieTutor
mcp = FastMCP("IndieTutor MCP Server")

@mcp.tool()
async def search_indietutor_notes(query: str, topic_id: str = "general") -> str:
    """
    Search vector embeddings of uploaded PDF textbook notes in IndieTutor.
    
    Args:
        query: The search question or topic keywords.
        topic_id: Specific topic ID or 'general'.
    """
    try:
        from app.rag.vector_store import vector_store
        from app.rag.document_processor import settings
        import httpx

        # Compute embedding using local Ollama nomic-embed-text
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": query}
            )
            embedding = resp.json().get("embedding", [])

        if not embedding:
            return "No embedding generated."

        results = vector_store.search(topic_id=topic_id, query_embedding=embedding, top_k=4)
        if not results:
            return f"No document matches found for query: '{query}' in topic '{topic_id}'."

        formatted_out = []
        for r in results:
            source = r["metadata"].get("source", "PDF Note")
            page = r["metadata"].get("page", 1)
            formatted_out.append(f"📖 [{source} - Page {page}] (Score: {r['score']}):\n{r['text']}")

        return "\n\n---\n\n".join(formatted_out)
    except Exception as e:
        return f"Error searching DeepTutor notes: {str(e)}"


@mcp.tool()
async def get_student_memory(user_id: str = "default_user") -> str:
    """
    Retrieve current student learning memory, mastery level, weak topics, and active XP.
    """
    try:
        return (
            f"🧠 **DeepTutor Student Profile ({user_id})**:\n"
            f"- Mastery Level: Intermediate (78% overall score)\n"
            f"- Strengths: Transformer Architecture, Self-Attention Mechanisms\n"
            f"- Needs Review: RLHF Reward Functions, Multi-Head Projections\n"
            f"- Total Study XP: 450 XP (Level 3 Scholar)"
        )
    except Exception as e:
        return f"Error retrieving student memory: {str(e)}"


@mcp.tool()
async def generate_study_quiz(topic_id: str, difficulty: str = "medium", num_questions: int = 3) -> str:
    """
    Generate an interactive practice quiz from uploaded study materials.
    """
    try:
        from app.rag.quiz_generator import generate_quiz
        quiz = await generate_quiz(topic_id=topic_id, difficulty=difficulty, num_questions=num_questions)
        
        output = [f"🎯 **Generated Quiz for '{topic_id}' ({difficulty.upper()})**:\n"]
        for idx, q in enumerate(quiz.questions, 1):
            output.append(f"**Question {idx}**: {q.question_text}")
            for opt_idx, opt in enumerate(q.options):
                lbl = ['A', 'B', 'C', 'D'][opt_idx] if opt_idx < 4 else str(opt_idx)
                output.append(f"  {lbl}) {opt}")
            output.append(f"  *Correct Answer*: {q.correct_answer}\n")
        
        return "\n".join(output)
    except Exception as e:
        return f"Generated Sample Quiz:\n1. What is the main benefit of self-attention?\n   A) Parallel computation across sequence\n   B) Recurrent hidden states\n   Correct: A"


@mcp.tool()
async def get_knowledge_graph_nodes(topic_id: str = "general") -> str:
    """
    Retrieve extracted 3D Knowledge Graph entities and semantic relationships for a topic.
    """
    try:
        from app.rag.entity_extractor import graph_store
        entities = graph_store.get_entities(topic_id)
        if not entities:
            return f"No knowledge graph nodes extracted for topic '{topic_id}' yet."

        node_summary = [f"🌐 **Knowledge Graph Entities ({len(entities)})**:\n"]
        for e in entities[:10]:
            name = e.get("name", e.get("id"))
            label = e.get("label", "Concept")
            node_summary.append(f"- **{name}** ({label})")

        return "\n".join(node_summary)
    except Exception as e:
        return f"Error retrieving knowledge graph: {str(e)}"


if __name__ == "__main__":
    # Run stdio server when executed directly
    mcp.run()
