"""
Ollama-based AI Engine for Document Q&A
Uses Ollama for reliable local AI model execution
"""

import logging
import requests
import json
from typing import List, Dict, Optional, Tuple
import numpy as np
from pathlib import Path
import time

logger = logging.getLogger(__name__)

class OllamaAIEngine:
    """
    AI Engine powered by Ollama for reliable local model execution
    """
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.embedding_model = "nomic-embed-text"
        self.chat_model = "llama3.2:1b"
        self.qa_model = "llama3.2:1b"
        
        # Lotte Chemical Company Information
        self.company_info = {
            "company_name": "Lotte Chemical",
            "primary_business": "World-class manufacturer and supplier of Purified Terephthalic Acid (PTA) in Pakistan",
            "production_capacity": "500,000 tonnes of PTA annually",
            "established": "1996 (described as 'an engineering marvel')",
            "experience": "About 2 decades in the industry",
            "manufacturing_plant": "Located at Port Qasim, Karachi - state-of-the-art facility",
            "plant_address": "Plot No. EZ/I/P-4, Eastern Industrial Zone, Port Qasim Authority Bin Qasim, Karachi – 75020",
            "city_office": "Al-Tijarah Centre, 14th Floor, 32/1-A, Main Shahrah-e-Faisal, Block 6, P.E.C.H.S, Karachi-75400",
            "phone": "+92-(0)21 3472-6005 / 3472-6010",
            "uan": "+92-(0)21 111 782 111 and +92-(0)21 111 568 782",
            "email": "contact@lottechem.pk",
            "core_focus": "Efficiency, Growth, Sustainability",
            "community_involvement": "Significant contributions to health, education, and disaster relief initiatives",
            "industry_context": "PTA (Purified Terephthalic Acid) is a key raw material used in the production of polyester fibers, films, and PET bottles. LOTTE Chemical Pakistan appears to be the only manufacturer of this chemical in Pakistan, making it a significant player in the country's chemical industry."
        }
        
        # Initialize conversation engine
        try:
            from utils.conversation_engine import ConversationEngine
            self.conversation_engine = ConversationEngine()
        except ImportError:
            logger.warning("Conversation engine not available")
            self.conversation_engine = None
        
        # Check Ollama availability and models
        self._check_ollama_status()
        self._ensure_models_available()
    
    def _check_ollama_status(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info("✅ Ollama is running and accessible")
                return True
            else:
                logger.warning(f"⚠️ Ollama returned status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException:
            # Reduce noise - only log once during initialization
            logger.warning("⚠️ Ollama not accessible - AI features will be limited")
            return False
    
    def _ensure_models_available(self):
        """Ensure required models are available in Ollama"""
        try:
            # Get list of available models
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code != 200:
                logger.warning("Cannot get model list from Ollama - skipping model check")
                return
            
            available_models = [model['name'] for model in response.json().get('models', [])]
            logger.info(f"📋 Available Ollama models: {available_models}")
            
            # Check and pull required models
            required_models = [self.embedding_model, self.chat_model]
            
            for model in required_models:
                if model not in available_models:
                    logger.info(f"📥 Pulling model: {model}")
                    self._pull_model(model)
                else:
                    logger.info(f"✅ Model available: {model}")
        
        except requests.exceptions.RequestException:
            logger.warning("Ollama not accessible - skipping model availability check")
        except Exception as e:
            logger.warning(f"Error checking models: {e}")
    
    def _pull_model(self, model_name: str):
        """Pull a model from Ollama"""
        try:
            logger.info(f"🔄 Downloading {model_name}... This may take a few minutes.")
            
            response = requests.post(
                f"{self.ollama_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=300
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if 'status' in data:
                            if data['status'] == 'success':
                                logger.info(f"✅ Successfully downloaded {model_name}")
                                break
                            elif 'completed' in data and 'total' in data:
                                progress = (data['completed'] / data['total']) * 100
                                logger.info(f"📥 {model_name}: {progress:.1f}% complete")
            else:
                logger.error(f"❌ Failed to pull {model_name}: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
    
    def get_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Get embeddings using Ollama"""
        try:
            embeddings = []
            
            for text in texts:
                response = requests.post(
                    f"{self.ollama_url}/api/embeddings",
                    json={
                        "model": self.embedding_model,
                        "prompt": text
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    embedding = response.json().get('embedding')
                    if embedding:
                        embeddings.append(embedding)
                    else:
                        logger.warning(f"No embedding returned for text: {text[:50]}...")
                        return None
                else:
                    logger.error(f"Embedding request failed: {response.status_code}")
                    return None
            
            if embeddings:
                return np.array(embeddings)
            else:
                return None
        
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            return None
    
    def semantic_search(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """Enhanced semantic search with better document understanding and references"""
        if not documents:
            return []
        
        try:
            # Get query embedding
            query_embedding = self.get_embeddings([query])
            if query_embedding is None:
                logger.warning("Failed to get query embedding, falling back to keyword search")
                return self._enhanced_keyword_search(query, documents, top_k)
            
            # Process documents into chunks with metadata
            all_chunks = []
            chunk_metadata = []
            
            for doc_idx, doc in enumerate(documents):
                content = doc.get('content', '')
                filename = doc.get('filename', 'Unknown')
                
                # Split content into semantic chunks
                chunks = self._create_semantic_chunks(content)
                
                for chunk_idx, chunk in enumerate(chunks):
                    if len(chunk.strip()) > 50:  # Only include substantial chunks
                        all_chunks.append(chunk)
                        
                        # Estimate page number based on chunk position
                        estimated_page = self._estimate_page_number(chunk_idx, len(chunks))
                        
                        chunk_metadata.append({
                            'doc_index': doc_idx,
                            'chunk_index': chunk_idx,
                            'filename': filename,
                            'estimated_page': estimated_page,
                            'chunk_text': chunk,
                            'chunk_length': len(chunk)
                        })
            
            if not all_chunks:
                return []
            
            # Get embeddings for all chunks
            chunk_embeddings = self.get_embeddings(all_chunks)
            
            if chunk_embeddings is None:
                logger.warning("Failed to get chunk embeddings, falling back to keyword search")
                return self._enhanced_keyword_search(query, documents, top_k)
            
            # Calculate similarities
            similarities = np.dot(query_embedding, chunk_embeddings.T)[0]
            
            # Get top results with enhanced scoring
            scored_chunks = []
            for idx, similarity in enumerate(similarities):
                if similarity > 0.1:  # Lower threshold to capture more relevant content
                    metadata = chunk_metadata[idx]
                    
                    # Enhanced scoring considering multiple factors
                    enhanced_score = self._calculate_enhanced_score(
                        similarity, metadata['chunk_text'], query, metadata['chunk_length']
                    )
                    
                    scored_chunks.append({
                        'content': metadata['chunk_text'],
                        'filename': metadata['filename'],
                        'similarity': float(similarity),
                        'enhanced_score': enhanced_score,
                        'page_number': metadata['estimated_page'],
                        'chunk_index': metadata['chunk_index'],
                        'metadata': metadata
                    })
            
            # Sort by enhanced score and return top results
            scored_chunks.sort(key=lambda x: x['enhanced_score'], reverse=True)
            results = scored_chunks[:top_k]
            
            logger.info(f"🔍 Enhanced semantic search found {len(results)} high-quality results")
            return results
        
        except Exception as e:
            logger.error(f"Enhanced semantic search failed: {e}")
            return self._enhanced_keyword_search(query, documents, top_k)
    
    def _keyword_search(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """Fallback keyword-based search"""
        query_words = set(query.lower().split())
        results = []
        
        for doc in documents:
            content_words = set(doc['content'].lower().split())
            overlap = len(query_words.intersection(content_words))
            if overlap > 0:
                score = overlap / len(query_words)
                doc_copy = doc.copy()
                doc_copy['similarity'] = score
                results.append(doc_copy)
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        logger.info(f"🔍 Keyword search found {len(results[:top_k])} results")
        return results[:top_k]
    
    def _enhanced_keyword_search(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """Enhanced keyword-based search with chunking and page references"""
        query_words = set(query.lower().split())
        results = []
        
        for doc in documents:
            content = doc.get('content', '')
            filename = doc.get('filename', 'Unknown')
            
            # Split into chunks for better granularity
            chunks = self._create_semantic_chunks(content)
            
            for chunk_idx, chunk in enumerate(chunks):
                if len(chunk.strip()) > 50:
                    chunk_words = set(chunk.lower().split())
                    overlap = len(query_words.intersection(chunk_words))
                    
                    if overlap > 0:
                        score = overlap / len(query_words)
                        estimated_page = self._estimate_page_number(chunk_idx, len(chunks))
                        
                        results.append({
                            'content': chunk,
                            'filename': filename,
                            'similarity': score,
                            'enhanced_score': score,
                            'page_number': estimated_page,
                            'chunk_index': chunk_idx
                        })
        
        results.sort(key=lambda x: x['enhanced_score'], reverse=True)
        logger.info(f"🔍 Enhanced keyword search found {len(results[:top_k])} results")
        return results[:top_k]
    
    def _create_semantic_chunks(self, text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        """Create semantic chunks that respect sentence boundaries"""
        if not text.strip():
            return []
        
        # Split into sentences
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in '.!?' and len(current_sentence.strip()) > 10:
                sentences.append(current_sentence.strip())
                current_sentence = ""
        
        # Add remaining text as a sentence
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        if not sentences:
            # Fallback to simple chunking
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size-overlap)]
        
        # Group sentences into chunks
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # If adding this sentence would exceed chunk size, start new chunk
            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                
                # Start new chunk with overlap
                if overlap > 0:
                    # Take last few sentences for overlap
                    overlap_sentences = current_chunk.split('.')[-2:]
                    current_chunk = '. '.join(overlap_sentences).strip() + '. ' + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += ' ' + sentence
                else:
                    current_chunk = sentence
        
        # Add the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text]
    
    def _estimate_page_number(self, chunk_index: int, total_chunks: int) -> int:
        """Estimate page number based on chunk position"""
        if total_chunks <= 1:
            return 1
        
        # Assume average of 3-4 chunks per page
        chunks_per_page = 3.5
        estimated_page = max(1, int((chunk_index / chunks_per_page) + 1))
        
        return estimated_page
    
    def _calculate_enhanced_score(self, similarity: float, chunk_text: str, query: str, chunk_length: int) -> float:
        """Calculate enhanced score considering multiple factors"""
        base_score = similarity
        
        # Boost score for exact keyword matches
        query_words = query.lower().split()
        chunk_lower = chunk_text.lower()
        exact_matches = sum(1 for word in query_words if word in chunk_lower)
        keyword_boost = (exact_matches / len(query_words)) * 0.2
        
        # Boost score for optimal chunk length (not too short, not too long)
        length_factor = 1.0
        if 200 <= chunk_length <= 1000:
            length_factor = 1.1
        elif chunk_length < 100:
            length_factor = 0.8
        
        # Boost score for chunks that seem to contain complete thoughts
        completeness_factor = 1.0
        if chunk_text.strip().endswith(('.', '!', '?')):
            completeness_factor = 1.05
        
        enhanced_score = (base_score + keyword_boost) * length_factor * completeness_factor
        
        return min(enhanced_score, 1.0)  # Cap at 1.0
    
    def answer_question(self, question: str, documents: List[Dict] = None) -> Dict:
        """Enhanced answer generation with contextual understanding and document references"""
        try:
            # Handle empty questions
            if not question or len(question.strip()) < 2:
                return {
                    'answer': "I'd love to help! Could you ask me a more specific question? 😊",
                    'sources': [],
                    'confidence': 0.0
                }

            question = question.strip()
            
            # Check if question is about Lotte Chemical company
            if self._is_company_question(question):
                return self._handle_company_question(question)
            
            # Get documents from internal storage if not provided
            if documents is None:
                documents = self._get_all_documents()

            # Handle general conversation
            if not documents or self._is_general_conversation(question):
                return self._handle_general_conversation(question, documents)
            
            # Check if this is a summarization request
            if self._is_summarization_request(question):
                return self._handle_summarization_request(question, documents)
            
            # Enhanced semantic search for relevant documents
            relevant_docs = self.semantic_search(question, documents, top_k=8)
            
            if not relevant_docs:
                return self._handle_no_relevant_info(question, documents)
            
            # Group results by document for better context
            docs_by_file = {}
            for doc in relevant_docs:
                filename = doc.get('filename', 'Unknown')
                if filename not in docs_by_file:
                    docs_by_file[filename] = []
                docs_by_file[filename].append(doc)
            
            # Prepare enhanced context with cross-document understanding
            context_parts = []
            sources = []
            
            # Process top documents for contextual understanding
            for filename, file_docs in list(docs_by_file.items())[:3]:  # Top 3 documents
                # Sort chunks by page number for coherent context
                file_docs.sort(key=lambda x: x.get('page_number', 0))
                
                # Combine related chunks from same document
                combined_content = self._combine_related_chunks(file_docs[:3])
                context_parts.append(f"From {filename}:\n{combined_content}")
                
                # Create source reference with page information
                pages = sorted(set(doc.get('page_number', 1) for doc in file_docs[:3]))
                page_ref = f"p. {pages[0]}" if len(pages) == 1 else f"pp. {pages[0]}-{pages[-1]}"
                
                sources.append({
                    'filename': filename,
                    'pages': pages,
                    'page_reference': page_ref,
                    'similarity': max(doc.get('similarity', 0.0) for doc in file_docs[:3]),
                    'chunk_count': len(file_docs[:3])
                })
            
            # Create comprehensive context
            context = "\n\n".join(context_parts)
            
            # Generate enhanced answer with cross-document analysis
            answer, confidence = self._generate_enhanced_answer(question, context, sources)
            
            # Add document references to the answer
            answer_with_refs = self._add_document_references(answer, sources)
            
            # Enhance with conversation engine if available
            if self.conversation_engine:
                answer_with_refs = self.conversation_engine.get_contextual_response(
                    question, answer_with_refs, confidence, sources
                )
            
            return {
                'answer': answer_with_refs,
                'sources': sources,
                'confidence': confidence,
                'cross_document_analysis': len(docs_by_file) > 1,
                'total_documents_searched': len(documents),
                'relevant_documents_found': len(docs_by_file)
            }
        
        except Exception as e:
            logger.error(f"Error in enhanced answer_question: {e}")
            return {
                'answer': "I apologize, but I encountered an error while processing your question. Please try again! 😊",
                'sources': [],
                'confidence': 0.0
            }
    
    def _generate_ollama_answer(self, question: str, context: str) -> Tuple[str, float]:
        """Generate answer using Ollama chat model"""
        try:
            # Create an enhanced prompt for Q&A
            prompt = f"""You are an intelligent document analysis assistant. Your task is to provide accurate, helpful, and comprehensive answers based on the provided context.

DOCUMENT CONTEXT:
{context}

USER QUESTION: {question}

INSTRUCTIONS:
- Analyze the context thoroughly to understand the full scope of information
- Provide a direct, clear answer that specifically addresses the question
- Include relevant details, facts, and specifics from the context
- If the context contains multiple relevant pieces of information, synthesize them coherently
- Be precise and avoid speculation beyond what's provided
- If the information is incomplete, acknowledge what is known and what might be unclear

PROVIDE YOUR ANSWER:"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.qa_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,  # Balanced temperature for intelligent but focused answers
                        "top_p": 0.95,
                        "top_k": 40,
                        "repeat_penalty": 1.1,
                        "num_ctx": 4096,  # Larger context window
                        "num_predict": 800  # Allow longer, more comprehensive responses
                    }
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip()
                
                if answer:
                    # Estimate confidence based on answer quality
                    confidence = self._estimate_confidence(answer, question, context)
                    return answer, confidence
                else:
                    return "I couldn't generate a proper answer from the available information.", 0.2
            else:
                logger.error(f"Ollama generate request failed: {response.status_code}")
                return self._fallback_answer(question, context)
        
        except Exception as e:
            logger.error(f"Error generating Ollama answer: {e}")
            return self._fallback_answer(question, context)
    
    def _generate_enhanced_answer(self, question: str, context: str, sources: List[Dict]) -> Tuple[str, float]:
        """Generate enhanced answer with cross-document analysis"""
        try:
            # Create enhanced prompt for better contextual understanding
            source_info = ", ".join([
                f"{s.get('filename', 'Unknown')} (Page {s.get('page_number', 1)})" 
                for s in sources if isinstance(s, dict)
            ])
            
            prompt = f"""You are an intelligent AI assistant with expertise in document analysis and information synthesis. Your role is to provide comprehensive, accurate, and insightful answers based on the provided document context.

DOCUMENT CONTEXT:
Sources: {source_info}
Content:
{context}

USER QUESTION: {question}

INSTRUCTIONS FOR RESPONSE:
1. ANALYZE THOROUGHLY: Carefully examine all provided information to understand the full context
2. SYNTHESIZE INTELLIGENTLY: If information spans multiple documents, create a coherent narrative that connects related concepts
3. BE COMPREHENSIVE: Provide detailed answers that fully address the question, including relevant background information
4. CITE SPECIFICALLY: Reference specific details, numbers, dates, names, and facts from the documents
5. ACKNOWLEDGE LIMITATIONS: If information is incomplete or unclear, state what is known and what might be missing
6. PROVIDE INSIGHTS: When appropriate, offer analysis, implications, or connections that help the user understand the significance
7. STRUCTURE CLEARLY: Organize your response logically with clear sections if the answer is complex
8. BE PRECISE: Avoid speculation beyond the provided context, but do explain relationships and implications that are evident

RESPONSE GUIDELINES:
- Start with a direct answer to the main question
- Support with specific evidence from the documents
- Include relevant details that provide complete understanding
- If multiple perspectives exist, present them fairly
- End with any important caveats or additional context

PROVIDE YOUR COMPREHENSIVE ANSWER:"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.qa_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,  # Balanced temperature for intelligent responses
                        "top_p": 0.95,
                        "top_k": 40,
                        "repeat_penalty": 1.1,
                        "num_ctx": 4096,  # Larger context window for complex analysis
                        "num_predict": 1000  # Allow comprehensive responses
                    }
                },
                timeout=90
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip()
                
                if answer:
                    # Enhanced confidence estimation
                    confidence = self._estimate_enhanced_confidence(answer, question, context, sources)
                    return answer, confidence
                else:
                    return "I couldn't generate a proper answer from the available information.", 0.2
            else:
                logger.error(f"Ollama enhanced generate request failed: {response.status_code}")
                return self._fallback_answer(question, context)
        
        except Exception as e:
            logger.error(f"Error generating enhanced Ollama answer: {e}")
            return self._fallback_answer(question, context)
    
    def _combine_related_chunks(self, chunks: List[Dict]) -> str:
        """Combine related chunks from the same document intelligently"""
        if not chunks:
            return ""
        
        if len(chunks) == 1:
            return chunks[0]['content']
        
        # Sort by chunk index to maintain document order
        sorted_chunks = sorted(chunks, key=lambda x: x.get('chunk_index', 0))
        
        combined_text = ""
        for i, chunk in enumerate(sorted_chunks):
            content = chunk['content'].strip()
            
            if i == 0:
                combined_text = content
            else:
                # Check for overlap and avoid duplication
                prev_end = combined_text[-100:].lower() if len(combined_text) > 100 else combined_text.lower()
                curr_start = content[:100].lower() if len(content) > 100 else content.lower()
                
                # Simple overlap detection
                overlap_found = False
                for j in range(min(50, len(prev_end)), 10, -1):
                    if prev_end[-j:] in curr_start:
                        # Remove overlap and combine
                        overlap_pos = curr_start.find(prev_end[-j:])
                        combined_text += " " + content[overlap_pos + j:]
                        overlap_found = True
                        break
                
                if not overlap_found:
                    combined_text += "\n\n" + content
        
        return combined_text
    
    def _add_document_references(self, answer: str, sources: List[Dict]) -> str:
        """Add document references to the answer"""
        if not sources:
            return answer
        
        # Create reference section
        references = []
        for i, source in enumerate(sources, 1):
            if isinstance(source, dict):
                filename = source.get('filename', 'Unknown')
                page_num = source.get('page_number', 1)
                ref = f"[{i}] {filename} (Page {page_num})"
                references.append(ref)
        
        # Add references to answer
        if references:
            ref_section = "\n\n**Sources:**\n" + "\n".join(references)
            return answer + ref_section
        
        return answer
    
    def _estimate_enhanced_confidence(self, answer: str, question: str, context: str, sources: List[Dict]) -> float:
        """Enhanced confidence estimation considering multiple factors"""
        base_confidence = self._estimate_confidence(answer, question, context)
        
        # Boost confidence for multi-document analysis
        if len(sources) > 1:
            base_confidence += 0.1
        
        # Boost confidence for high-similarity sources
        avg_similarity = sum(s.get('similarity', 0) for s in sources) / len(sources)
        if avg_similarity > 0.7:
            base_confidence += 0.1
        elif avg_similarity > 0.5:
            base_confidence += 0.05
        
        # Boost confidence for comprehensive answers
        if len(answer) > 100 and any(word in answer.lower() for word in ['according', 'based on', 'document', 'shows', 'indicates']):
            base_confidence += 0.05
        
        return min(base_confidence, 0.95)  # Cap at 95%
    
    def _fallback_answer(self, question: str, context: str) -> Tuple[str, float]:
        """Fallback answer generation when Ollama is not available"""
        # Simple extractive approach
        sentences = context.split('.')
        question_words = set(question.lower().split())
        
        best_sentence = ""
        best_score = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            
            sentence_words = set(sentence.lower().split())
            overlap = len(question_words.intersection(sentence_words))
            score = overlap / len(question_words) if question_words else 0
            
            if score > best_score:
                best_score = score
                best_sentence = sentence
        
        if best_sentence:
            return f"Based on the documents: {best_sentence}.", min(best_score, 0.7)
        else:
            return "I found some relevant information but couldn't extract a specific answer.", 0.3
    
    def _estimate_confidence(self, answer: str, question: str, context: str) -> float:
        """Estimate confidence in the generated answer"""
        # Simple heuristics for confidence estimation
        confidence = 0.5  # Base confidence
        
        # Check answer length (not too short, not too long)
        if 20 <= len(answer) <= 300:
            confidence += 0.2
        
        # Check if answer contains question keywords
        question_words = set(question.lower().split())
        answer_words = set(answer.lower().split())
        overlap = len(question_words.intersection(answer_words))
        if overlap > 0:
            confidence += min(overlap * 0.1, 0.2)
        
        # Check if answer seems to reference the context
        if any(word in answer.lower() for word in ['according', 'based', 'document', 'text']):
            confidence += 0.1
        
        return min(confidence, 0.95)  # Cap at 95%
    
    def _is_general_conversation(self, question: str) -> bool:
        """Check if this is general conversation rather than document-specific"""
        general_patterns = [
            'hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening',
            'how are you', 'what are you', 'who are you', 'what can you do',
            'help', 'thank you', 'thanks', 'bye', 'goodbye'
        ]
        
        question_lower = question.lower()
        return any(pattern in question_lower for pattern in general_patterns)
    
    def _is_summarization_request(self, question: str) -> bool:
        """Check if question is asking for a summary"""
        summary_patterns = [
            'summarize', 'summarise', 'summary', 'sum up', 'give me a summary',
            'what is this document about', 'overview', 'main points', 'key points',
            'brief', 'outline', 'gist', 'essence', 'recap', 'digest'
        ]
        question_lower = question.lower()
        return any(pattern in question_lower for pattern in summary_patterns)
    
    def _handle_summarization_request(self, question: str, documents: List[Dict]) -> Dict:
        """Handle summarization requests"""
        if not documents:
            return {
                'answer': "I don't have any documents to summarize. Please upload some documents first!",
                'sources': [],
                'confidence': 0.0
            }
        
        # Get unique documents
        unique_docs = {}
        for doc in documents:
            filename = doc.get('filename', 'Unknown')
            if filename not in unique_docs:
                unique_docs[filename] = doc
        
        if len(unique_docs) == 1:
            # Single document summary
            doc = list(unique_docs.values())[0]
            content = doc.get('content', '')
            filename = doc.get('filename', 'Unknown')
            
            # Create summary using first few paragraphs or chunks
            summary_text = self._create_document_summary(content, filename)
            
            return {
                'answer': summary_text,
                'sources': [{'filename': filename, 'similarity': 1.0}],
                'confidence': 0.8
            }
        else:
            # Multiple documents summary
            summaries = []
            sources = []
            
            for filename, doc in list(unique_docs.items())[:5]:  # Limit to 5 docs
                content = doc.get('content', '')
                doc_summary = self._create_document_summary(content, filename, brief=True)
                summaries.append(f"**{filename}:**\n{doc_summary}")
                sources.append({'filename': filename, 'similarity': 1.0})
            
            combined_summary = f"**Summary of {len(unique_docs)} documents:**\n\n" + "\n\n".join(summaries)
            
            if len(unique_docs) > 5:
                combined_summary += f"\n\n*Note: Showing summaries for the first 5 documents. {len(unique_docs) - 5} additional documents are available.*"
            
            return {
                'answer': combined_summary,
                'sources': sources,
                'confidence': 0.75
            }
    
    def _create_document_summary(self, content: str, filename: str, brief: bool = False) -> str:
        """Create a summary of document content"""
        if not content.strip():
            return "This document appears to be empty or contains no readable text."
        
        # Split into sentences and paragraphs
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        if not paragraphs:
            sentences = [s.strip() for s in content.split('.') if s.strip() and len(s.strip()) > 20]
            paragraphs = sentences[:3]  # Take first 3 substantial sentences
        
        if brief:
            # Brief summary for multi-document view
            summary_length = min(2, len(paragraphs))
            summary_parts = paragraphs[:summary_length]
            
            if len(content) > 1000:
                word_count = len(content.split())
                summary_text = ' '.join(summary_parts)[:200] + "..."
                return f"{summary_text}\n\n*Document length: ~{word_count} words*"
            else:
                return ' '.join(summary_parts)
        else:
            # Detailed summary for single document
            summary_length = min(5, len(paragraphs))
            summary_parts = paragraphs[:summary_length]
            
            word_count = len(content.split())
            char_count = len(content)
            
            summary_text = '\n\n'.join(summary_parts)
            
            if len(paragraphs) > summary_length:
                summary_text += "\n\n*[Summary truncated - showing first few sections]*"
            
            summary_text += f"\n\n**Document Statistics:**\n• Word count: ~{word_count}\n• Character count: ~{char_count}\n• Sections: {len(paragraphs)}"
            
            return summary_text
    
    def _is_company_question(self, question: str) -> bool:
        """Check if the question is about Lotte Chemical company"""
        company_keywords = [
            'lotte', 'lotte chemical', 'company', 'business', 'pta', 'terephthalic acid',
            'production', 'capacity', 'established', 'founded', 'location', 'address',
            'contact', 'phone', 'email', 'karachi', 'port qasim', 'manufacturing',
            'plant', 'facility', 'office', 'about us', 'who are you', 'what do you do',
            'core values', 'mission', 'vision', 'sustainability', 'community'
        ]
        
        question_lower = question.lower()
        return any(keyword in question_lower for keyword in company_keywords)
    
    def _handle_company_question(self, question: str) -> Dict:
        """Handle questions about Lotte Chemical company"""
        question_lower = question.lower()
        
        # Determine what aspect of the company the user is asking about
        if any(word in question_lower for word in ['address', 'location', 'where', 'plant', 'facility', 'office']):
            answer = f"""**Lotte Chemical Locations:**

🏭 **Manufacturing Plant**: {self.company_info['manufacturing_plant']}
📍 **Plant Address**: {self.company_info['plant_address']}

🏢 **City Office**: {self.company_info['city_office']}"""
        
        elif any(word in question_lower for word in ['contact', 'phone', 'email', 'call', 'reach']):
            answer = f"""**Contact Information:**

📞 **Phone**: {self.company_info['phone']}
📱 **UAN**: {self.company_info['uan']}
📧 **Email**: {self.company_info['email']}"""
        
        elif any(word in question_lower for word in ['production', 'capacity', 'manufacture', 'pta', 'terephthalic']):
            answer = f"""**Production Information:**

🏭 **Primary Business**: {self.company_info['primary_business']}
📊 **Production Capacity**: {self.company_info['production_capacity']}
🧪 **Industry Context**: {self.company_info['industry_context']}"""
        
        elif any(word in question_lower for word in ['established', 'founded', 'history', 'when', 'experience']):
            answer = f"""**Company History:**

📅 **Established**: {self.company_info['established']}
⏳ **Experience**: {self.company_info['experience']}"""
        
        elif any(word in question_lower for word in ['values', 'mission', 'vision', 'focus', 'sustainability', 'community']):
            answer = f"""**Corporate Values & Community:**

🎯 **Core Focus**: {self.company_info['core_focus']}
🤝 **Community Involvement**: {self.company_info['community_involvement']}"""
        
        elif any(word in question_lower for word in ['about', 'what', 'who', 'company', 'business']):
            answer = f"""**About Lotte Chemical:**

🏢 **Company**: {self.company_info['company_name']}
🏭 **Primary Business**: {self.company_info['primary_business']}
📊 **Production Capacity**: {self.company_info['production_capacity']}
📅 **Established**: {self.company_info['established']}
⏳ **Experience**: {self.company_info['experience']}

🎯 **Core Focus**: {self.company_info['core_focus']}
🤝 **Community Involvement**: {self.company_info['community_involvement']}

📍 **Manufacturing Plant**: {self.company_info['manufacturing_plant']}
📧 **Contact**: {self.company_info['email']}"""
        
        else:
            # General company information
            answer = f"""**Lotte Chemical Overview:**

{self.company_info['company_name']} is a {self.company_info['primary_business']} with a {self.company_info['production_capacity']}. 

Established in {self.company_info['established']}, we have {self.company_info['experience']} and focus on {self.company_info['core_focus']}.

Feel free to ask me specific questions about our locations, contact information, production, or values!"""
        
        return {
            'answer': answer,
            'sources': [{'filename': 'Company Information', 'similarity': 1.0}],
            'confidence': 0.95
        }
    
    def _handle_general_conversation(self, question: str, documents: List[Dict]) -> Dict:
        """Handle general conversation"""
        question_lower = question.lower()
        
        if any(greeting in question_lower for greeting in ['hello', 'hi', 'hey']):
            if documents:
                # Count unique documents in current conversation
                unique_docs = set(doc.get('filename', 'Unknown') for doc in documents)
                doc_count = len(unique_docs)
                answer = f"Hello! 👋 I'm your Lotte Chemical AI Document Assistant. I can see you have {doc_count} document(s) in this conversation. Feel free to ask me questions about them or about Lotte Chemical!"
            else:
                answer = "Hello! 👋 I'm your Lotte Chemical AI Document Assistant. I can help you with document analysis and answer questions about Lotte Chemical. Please upload some documents or ask me about our company!"
        
        elif 'what can you do' in question_lower or 'help' in question_lower:
            answer = """I'm here to help you with documents and company information! Here's what I can do:

📚 **Document Analysis**: Ask questions about your uploaded documents
🔍 **Smart Search**: Find specific information across multiple documents  
🏢 **Company Information**: Ask me about Lotte Chemical - our history, locations, contact info, production, and values
💬 **Natural Conversation**: Chat with me in plain English
📝 **Summaries**: Get key points and summaries from your documents

Try asking: "What is Lotte Chemical?" or upload documents and start asking questions!"""
        
        elif any(thanks in question_lower for thanks in ['thank you', 'thanks']):
            answer = "You're very welcome! 😊 I'm always here to help you with your documents and answer questions about Lotte Chemical. Is there anything else you'd like to know?"
        
        else:
            answer = "I'm your Lotte Chemical AI Document Assistant! I'm designed to help you find information in your uploaded documents and answer questions about our company. What would you like to know?"
        
        return {
            'answer': answer,
            'sources': [],
            'confidence': 0.9
        }
    
    def _handle_no_relevant_info(self, question: str, documents: List[Dict]) -> Dict:
        """Handle cases where no relevant information is found"""
        # Get unique document names from current conversation
        unique_docs = list(set(doc.get('filename', 'Unknown') for doc in documents))
        doc_names = unique_docs[:3]
        doc_list = ", ".join(doc_names)
        if len(unique_docs) > 3:
            doc_list += f" and {len(unique_docs) - 3} more"
        
        answer = f"I searched through your documents ({doc_list}) but couldn't find specific information about '{question}'. Could you try rephrasing your question or asking about something else in these documents?"
        
        return {
            'answer': answer,
            'sources': [],
            'confidence': 0.1
        }
    
    def build_vector_index(self, documents_data: List[Dict]):
        """Build vector index from documents (simplified for Ollama)"""
        try:
            if not documents_data:
                logger.warning("No documents provided for indexing")
                return
            
            logger.info(f"🔄 Building vector index for {len(documents_data)} documents...")
            
            # Store documents data for search
            self.documents_data = documents_data
            
            # Pre-generate embeddings for all chunks if Ollama is available
            if self._check_ollama_status():
                all_chunks = []
                self.chunk_metadata = []
                
                for doc in documents_data:
                    filename = doc['filename']
                    chunks = doc['chunks']
                    
                    for i, chunk in enumerate(chunks):
                        all_chunks.append(chunk)
                        self.chunk_metadata.append({
                            'filename': filename,
                            'chunk_index': i,
                            'text': chunk
                        })
                
                if all_chunks:
                    logger.info(f"📊 Pre-generating embeddings for {len(all_chunks)} chunks...")
                    # Note: We could cache embeddings here for faster search
                    # For now, we'll generate them on-demand
                    
            logger.info("✅ Vector index building completed")
            
        except Exception as e:
            logger.error(f"Error in build_vector_index: {e}")
            self.documents_data = documents_data
    
    def search_similar_chunks(self, query: str, k: int = 5) -> List[Dict]:
        """Search for similar text chunks"""
        if hasattr(self, 'documents_data'):
            documents = []
            for doc in self.documents_data:
                for chunk in doc['chunks']:
                    documents.append({
                        'content': chunk,
                        'filename': doc['filename']
                    })
            
            return self.semantic_search(query, documents, k)
        
        return []
    
    def _get_all_documents(self) -> List[Dict]:
        """Get all documents from the database"""
        try:
            import sqlite3
            
            # Use the same database path as main.py
            DATABASE_PATH = "chatbot.db"
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents")
            documents = cursor.fetchall()
            conn.close()
            
            doc_list = []
            for doc in documents:
                # doc format based on schema: (id, conversation_id, user_id, filename, original_filename, file_path, file_size, file_type, text_content, processed_text, ...)
                text_content = doc[8] if len(doc) > 8 and doc[8] else ""  # text_content column
                filename = doc[3] if len(doc) > 3 else "Unknown"  # filename column
                
                if text_content.strip():  # Only include documents with content
                    doc_list.append({
                        'content': text_content,
                        'filename': filename
                    })
            
            logger.info(f"📚 Retrieved {len(doc_list)} documents from database")
            return doc_list
        except Exception as e:
            logger.error(f"Error getting documents from database: {e}")
            return []

    def get_model_info(self) -> Dict:
        """Get information about Ollama models"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return {
                    'ollama_available': True,
                    'ollama_url': self.ollama_url,
                    'embedding_model': self.embedding_model,
                    'chat_model': self.chat_model,
                    'available_models': [model['name'] for model in models],
                    'model_count': len(models)
                }
            else:
                return {
                    'ollama_available': False,
                    'error': f"Ollama returned status {response.status_code}"
                }
        except Exception as e:
            return {
                'ollama_available': False,
                'error': str(e)
            }
    
    def _add_document_references(self, answer: str, sources: List[Dict]) -> str:
        """Add document references to the answer"""
        if not sources:
            return answer
        
        # Add source references at the end
        references = "\n\n**Sources:**\n"
        for i, source in enumerate(sources[:3], 1):  # Limit to top 3 sources
            filename = source.get('filename', 'Unknown')
            page_ref = source.get('page_reference', '')
            if page_ref:
                references += f"• {filename} ({page_ref})\n"
            else:
                references += f"• {filename}\n"
        
        return answer + references
    
    def _estimate_confidence(self, answer: str, question: str, context: str) -> float:
        """Estimate confidence based on answer quality"""
        base_confidence = 0.7
        
        # Boost confidence for longer, more detailed answers
        if len(answer) > 100:
            base_confidence += 0.1
        
        # Boost confidence if answer contains specific details
        if any(word in answer.lower() for word in ['specific', 'according to', 'based on', 'document']):
            base_confidence += 0.1
        
        # Reduce confidence for generic responses
        if any(phrase in answer.lower() for phrase in ['i don\'t know', 'unclear', 'not sure']):
            base_confidence -= 0.3
        
        return min(max(base_confidence, 0.1), 0.95)
    
    def _estimate_enhanced_confidence(self, answer: str, question: str, context: str, sources: List[Dict]) -> float:
        """Enhanced confidence estimation with source quality"""
        base_confidence = self._estimate_confidence(answer, question, context)
        
        # Boost confidence based on source quality
        if sources:
            avg_similarity = sum(s.get('similarity', 0.0) for s in sources) / len(sources)
            source_boost = avg_similarity * 0.2
            base_confidence += source_boost
        
        # Boost confidence for cross-document analysis
        if len(sources) > 1:
            base_confidence += 0.05
        
        return min(max(base_confidence, 0.1), 0.95)
    
    def _fallback_answer(self, question: str, context: str) -> Tuple[str, float]:
        """Generate fallback answer when Ollama is not available"""
        if context:
            # Simple keyword-based answer extraction
            sentences = context.split('. ')
            question_words = set(question.lower().split())
            
            best_sentence = ""
            best_score = 0
            
            for sentence in sentences:
                sentence_words = set(sentence.lower().split())
                overlap = len(question_words.intersection(sentence_words))
                if overlap > best_score:
                    best_score = overlap
                    best_sentence = sentence
            
            if best_sentence:
                return f"Based on the documents: {best_sentence.strip()}", 0.6
        
        return "I found some relevant information but couldn't generate a detailed answer. Please try rephrasing your question.", 0.3
