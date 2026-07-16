import streamlit as st
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_cohere import CohereEmbeddings, ChatCohere, CohereRerank
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from typing import List

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="RAG Avanzado Moderno", page_icon="🤖", layout="centered")
st.title("🤖 Chat PIXEL FORGETECH (Contrato y Reglamento de trabajo)")
st.subheader("Arquitectura Estable LCEL (Cohere)")

# --- CUSTOM RERANKER (Usa BaseRetriever nativo) ---
class DirectRerankRetriever(BaseRetriever):
    base_retriever: BaseRetriever
    compressor: CohereRerank

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        docs = self.base_retriever.invoke(query)
        return self.compressor.compress_documents(docs, query)

# --- INICIALIZACIÓN DEL PIPELINE ---
@st.cache_resource
def inicializar_rag():
    # Buscamos el archivo PDF en lugar del TXT
    if not os.path.exists("CONTRATO_REGLAMENTO.pdf"):
        st.error("El archivo 'CONTRATO_REGLAMENTO.pdf' no se encuentra en el directorio actual.")
        st.stop()
            
    # 1. Ingesta de datos desde el PDF
    loader = PyPDFLoader("CONTRATO_REGLAMENTO.pdf")
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(docs)
    
    # 2. Vector Store con Embeddings Gratuitos de Cohere
    embeddings = CohereEmbeddings(model="embed-multilingual-v3.0")
    vector_store = Chroma.from_documents(chunks, embeddings)
    
    # 3. Recuperador con Rerank integrado
    base_retriever = vector_store.as_retriever(search_kwargs={"k": 6})
    compressor = CohereRerank(model="rerank-v3.5", top_n=3)
    return DirectRerankRetriever(base_retriever=base_retriever, compressor=compressor)

try:
    retriever_rag = inicializar_rag()
    # Actualizamos al modelo estable y vigente de Cohere optimizado para RAG
    llm = ChatCohere(model="command-r-08-2024", temperature=0)
except Exception as e:
    st.error(f"Error al inicializar componentes: {e}")
    st.stop()

# --- FORMULACIÓN DE PREGUNTAS CON HISTORIAL (Contextualizador) ---
contextualize_system_prompt = (
    "Tu única tarea es reformular la última pregunta del usuario para que sea una consulta independiente, "
    "usando el historial de chat como contexto. \n"
    "REGLAS ESTRICTAS:\n"
    "1. Devuelve ÚNICAMENTE la pregunta reformulada. No respondas la pregunta bajo ninguna circunstancia.\n"
    "2. No agregues saludos, explicaciones, introducciones, ni comentarios secundarios.\n"
    "3. Si la última pregunta no tiene relación con el historial, devuélvela exactamente igual a como la escribió el usuario."
)
contextualize_q_prompt = ChatPromptTemplate.from_messages([
    ("system", contextualize_system_prompt),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])
contextualize_chain = contextualize_q_prompt | llm | StrOutputParser()

# --- PROMPT DE RESPUESTA FINAL ULTRA-ESTRICTO ---
# Redactamos el prompt con reglas severas para que se resigne a responder solo con el contexto
# --- PROMPT DE RESPUESTA FINAL ULTRA-ESTRICTO ---
system_prompt = (
    "Eres un asistente de inteligencia artificial sumamente estricto y preciso. Tu única fuente de verdad es el contexto provisto abajo.\n\n"
    "REGLAS CRÍTICAS DE OPERACIÓN:\n"
    "1. Responde la pregunta basándote ÚNICAMENTE en el contexto que se te proporciona.\n"
    "2. Si el contexto no contiene suficiente información para responder a la pregunta, o si la pregunta es totalmente incoherente/irrelevante con el contexto, debes decir exactamente esto: 'Lo siento, no puedo responder a esa pregunta ya que la información no se encuentra en el documento proporcionado.'\n"
    "3. No utilices bajo ninguna circunstancia tu conocimiento interno o general del mundo para responder temas que falten en el texto.\n"
    "4. REGLA DE REDACCIÓN: Responde de manera directa e informativa. NO inicies tus respuestas con palabras como 'Sí, ...', 'No, ...', 'De acuerdo, ...' o confirmaciones similares a menos que el usuario te haya hecho una pregunta cerrada de sí o no. Ve directo al grano.\n"
    "5. Mantén una actitud amable pero directa.\n\n"
    "Contexto proporcionado:\n{context}"
)
   
qa_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])

# --- CONTROL DE ESTADO (MEMORIA STREAMLIT) ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "display_history" not in st.session_state:
    st.session_state.display_history = []

# Dibujar mensajes previos en pantalla
for message in st.session_state.display_history:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# --- LÓGICA DE EJECUCIÓN DEL CHAT ---
if user_query := st.chat_input("Escribe tu consulta aquí..."):
    
    with st.chat_message("user"):
        st.write(user_query)
    st.session_state.display_history.append({"role": "user", "content": user_query})
    
    with st.chat_message("assistant"):
        with st.spinner("Buscando en tus documentos PDF..."):
            
            # 1. Resolver la pregunta con el contextualizador
            pregunta_final = user_query
            if len(st.session_state.chat_history) > 0:
                try:
                    reformulada = contextualize_chain.invoke({
                        "input": user_query,
                        "chat_history": st.session_state.chat_history
                    })
                    # Si el contextualizador arroja explicaciones largas en vez de una pregunta corta, lo ignoramos
                    if len(reformulada.split()) < 25 and not any(palabra in reformulada.lower() for palabra in ["lo siento", "entiendo que", "hola", "puedo ayudar"]):
                        pregunta_final = reformulada
                except Exception:
                    pregunta_final = user_query
                
            # 2. Recuperar documentos del PDF utilizando la pregunta filtrada
            docs_recuperados = retriever_rag.invoke(pregunta_final)
            contexto_str = "\n\n".join([d.page_content for d in docs_recuperados])
            
            # 3. Generar respuesta final usando LCEL con el prompt estricto
            final_chain = qa_prompt | llm | StrOutputParser()
            respuesta_final = final_chain.invoke({
                "input": pregunta_final,
                "context": contexto_str,
                "chat_history": st.session_state.chat_history
            })
            
            # --- CANDADO DE SEGURIDAD PARA ENTIDADES NO EXISTENTES ---
            # Extraemos palabras clave de la pregunta (ignorando conectores comunes)
            sujeto_pregunta = pregunta_final.lower()
            entidades_clave = [w for w in sujeto_pregunta.split() if len(w) > 4 and w not in ["quien", "sobre", "como", "cual", "que", "donde"]]
            
            # Si el usuario busca algo específico (como un nombre propio) que NO aparece en el texto del PDF,
            # forzamos el mensaje estricto de rechazo ignorando cualquier intento de alucinación del LLM.
            if entidades_clave and not any(entidad in contexto_str.lower() for entidad in entidades_clave):
                respuesta_final = "Lo siento, no puedo responder a esa pregunta ya que la información no se encuentra en el documento proporcionado."

            # Limpiador de muletillas heredadas por el historial de chat (Sí, / No, )
            if respuesta_final.startswith(("Sí, ", "No, ", "Sí. ", "No. ")):
                partes = respuesta_final.split(", ", 1)
                if len(partes) > 1:
                    respuesta_final = partes[1].capitalize()

            st.write(respuesta_final)
            
    # Guardar en la memoria interna de la sesión
    st.session_state.display_history.append({"role": "assistant", "content": respuesta_final})
    st.session_state.chat_history.extend([
        HumanMessage(content=user_query),
        AIMessage(content=respuesta_final)
    ])