"""
Business Intelligence Assistant - Orchestration Engine
Coordinates RAG retrieval with MCP tool execution
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("business-assistant")


class BusinessAssistant:
    """
    Main orchestration class that combines RAG with MCP tools
    to provide intelligent business insights.
    """
    
    def __init__(self):
        """Initialize the Business Intelligence Assistant."""
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.chroma_path = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
        
        # Initialize components
        self.embeddings = OpenAIEmbeddings(api_key=self.openai_key)
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            api_key=self.openai_key
        )
        
        # Vector store (will be loaded when documents are ingested)
        self.vectorstore = None
        
        # MCP tool handlers (imported from existing servers)
        self.mcp_tools = self._initialize_mcp_tools()
        
        # Conversation context
        self.context_history = []
        
        logger.info("Business Intelligence Assistant initialized")
    
    def _initialize_mcp_tools(self) -> Dict[str, Any]:
        """
        Initialize connections to MCP tool servers.
        Returns a dictionary of available tools.
        """
        tools = {
            "hubspot": {
                "available": bool(os.getenv("HUBSPOT_ACCESS_TOKEN")),
                "tools": [
                    "create_contact",
                    "search_contacts", 
                    "get_contact",
                    "update_contact",
                    "create_deal"
                ]
            },
            "weather": {
                "available": bool(os.getenv("WEATHER_API_KEY")),
                "tools": [
                    "get_current_weather",
                    "get_forecast",
                    "get_weather_alerts",
                    "compare_locations",
                    "get_weather_by_coords"
                ]
            },
            "database": {
                "available": True,  # SQLite is always available
                "tools": [
                    "create_note",
                    "get_all_notes",
                    "get_note_by_id",
                    "update_note",
                    "delete_note",
                    "search_notes"
                ]
            }
        }
        
        available_tools = [
            category for category, info in tools.items() 
            if info["available"]
        ]
        logger.info(f"Available MCP tool categories: {available_tools}")
        
        return tools
    
    def load_knowledge_base(self, document_directory: str) -> None:
        """
        Load documents into the vector database for RAG.
        
        Args:
            document_directory: Path to directory containing documents
        """
        from langchain_community.document_loaders import DirectoryLoader, TextLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        logger.info(f"Loading documents from {document_directory}")
        
        # Load text documents
        try:
            loader = DirectoryLoader(
                document_directory,
                glob="**/*.txt",
                loader_cls=TextLoader
            )
            documents = loader.load()
        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            documents = []
        
        if not documents:
            logger.warning("No documents found!")
            return
        
        # Chunk documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = text_splitter.split_documents(documents)
        
        logger.info(f"Created {len(chunks)} chunks from {len(documents)} documents")
        
        # Create vector store
        self.vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=self.chroma_path
        )
        
        logger.info("Knowledge base loaded successfully")
    
    def _select_tools(self, query: str) -> list[str]:
        """
        Intelligently select which tools to use based on the query.
        
        Args:
            query: User's question/request
            
        Returns:
            List of tool categories to use
        """
        query_lower = query.lower()
        selected_tools = []
        
        # Always use RAG for knowledge retrieval
        if self.vectorstore:
            selected_tools.append("rag")
        
        # HubSpot CRM keywords
        crm_keywords = [
            "contact", "customer", "deal", "crm", "company",
            "lead", "prospect", "account", "sales"
        ]
        if any(keyword in query_lower for keyword in crm_keywords):
            if self.mcp_tools["hubspot"]["available"]:
                selected_tools.append("hubspot")
        
        # Weather keywords
        weather_keywords = [
            "weather", "temperature", "forecast", "climate",
            "location", "city", "region"
        ]
        if any(keyword in query_lower for keyword in weather_keywords):
            if self.mcp_tools["weather"]["available"]:
                selected_tools.append("weather")
        
        # Database keywords (for logging/retrieval)
        db_keywords = [
            "note", "save", "log", "record", "history",
            "previous", "past", "stored"
        ]
        if any(keyword in query_lower for keyword in db_keywords):
            selected_tools.append("database")
        
        logger.info(f"Selected tools for query: {selected_tools}")
        return selected_tools
    
    def _retrieve_from_rag(self, query: str, k: int = 3) -> list[Dict[str, Any]]:
        """
        Retrieve relevant documents from the knowledge base.
        
        Args:
            query: Search query
            k: Number of results to retrieve
            
        Returns:
            List of relevant documents
        """
        if not self.vectorstore:
            logger.warning("Vector store not initialized")
            return []
        
        try:
            docs = self.vectorstore.similarity_search(query, k=k)
            results = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": doc.metadata.get("source", "unknown")
                }
                for doc in docs
            ]
            logger.info(f"Retrieved {len(results)} documents from RAG")
            return results
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return []
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Main orchestration method. Processes a user query by:
        1. Selecting appropriate tools
        2. Retrieving information from RAG
        3. Calling relevant MCP tools
        4. Synthesizing results with LLM
        
        Args:
            query: User's question or request
            
        Returns:
            Dict containing the response and metadata
        """
        logger.info(f"Processing query: {query}")
        start_time = datetime.now()
        
        # Step 1: Select tools
        selected_tools = self._select_tools(query)
        
        # Step 2: Gather information from selected sources
        gathered_info = {
            "query": query,
            "timestamp": start_time.isoformat(),
            "tools_used": selected_tools,
            "results": {}
        }
        
        # RAG retrieval
        if "rag" in selected_tools:
            rag_results = self._retrieve_from_rag(query)
            gathered_info["results"]["rag"] = rag_results
        
        # MCP tool execution (placeholder - will implement specific handlers)
        if "hubspot" in selected_tools:
            gathered_info["results"]["hubspot"] = {
                "status": "available",
                "message": "HubSpot integration ready"
            }
        
        if "weather" in selected_tools:
            gathered_info["results"]["weather"] = {
                "status": "available",
                "message": "Weather integration ready"
            }
        
        if "database" in selected_tools:
            gathered_info["results"]["database"] = {
                "status": "available",
                "message": "Database integration ready"
            }
        
        # Step 3: Synthesize with LLM
        response = await self._synthesize_response(query, gathered_info)
        
        # Step 4: Store in context history
        self.context_history.append({
            "query": query,
            "response": response,
            "tools_used": selected_tools,
            "timestamp": datetime.now().isoformat()
        })
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Query processed in {elapsed:.2f} seconds")
        
        return {
            "query": query,
            "response": response,
            "metadata": {
                "tools_used": selected_tools,
                "processing_time": elapsed,
                "sources": self._extract_sources(gathered_info)
            }
        }
    
    async def _synthesize_response(
        self, 
        query: str, 
        gathered_info: Dict[str, Any]
    ) -> str:
        """
        Use LLM to synthesize information from multiple sources.
        
        Args:
            query: Original user query
            gathered_info: Information gathered from tools
            
        Returns:
            Synthesized response
        """
        # Build context from gathered information
        context_parts = []
        
        # Add RAG results
        if "rag" in gathered_info.get("results", {}):
            rag_results = gathered_info["results"]["rag"]
            if rag_results:
                context_parts.append("=== Knowledge Base Information ===")
                for i, doc in enumerate(rag_results, 1):
                    context_parts.append(f"\nDocument {i}:")
                    context_parts.append(doc["content"][:500])  # Truncate for context
                    context_parts.append(f"Source: {doc['source']}")
        
        # Add MCP tool results
        for tool in ["hubspot", "weather", "database"]:
            if tool in gathered_info.get("results", {}):
                tool_result = gathered_info["results"][tool]
                context_parts.append(f"\n=== {tool.title()} Data ===")
                context_parts.append(json.dumps(tool_result, indent=2))
        
        context = "\n".join(context_parts)
        
        # Create system prompt
        system_prompt = """You are a Business Intelligence Assistant. 
You have access to multiple data sources including:
- Internal knowledge base (documents, case studies, procedures)
- CRM system (customer and deal information)
- Weather data (for context-aware insights)
- Historical notes database

Your task is to synthesize information from these sources to provide 
intelligent, actionable business insights. Be specific, cite sources, 
and provide clear recommendations."""
        
        # Create user message with context
        user_message = f"""Query: {query}

Available Context:
{context}

Please provide a comprehensive response that:
1. Directly answers the question
2. References specific information from the sources
3. Provides actionable insights or recommendations
4. Cites sources clearly"""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            
            response = self.llm.invoke(messages)
            return response.content
        
        except Exception as e:
            logger.error(f"LLM synthesis error: {e}")
            return f"I encountered an error processing your request: {str(e)}"
    
    def _extract_sources(self, gathered_info: Dict[str, Any]) -> list[str]:
        """Extract source citations from gathered information."""
        sources = []
        
        if "rag" in gathered_info.get("results", {}):
            for doc in gathered_info["results"]["rag"]:
                source = doc.get("source", "unknown")
                if source not in sources:
                    sources.append(source)
        
        return sources
    
    def get_conversation_history(self) -> list[Dict[str, Any]]:
        """Return the conversation history."""
        return self.context_history
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.context_history = []
        logger.info("Conversation history cleared")