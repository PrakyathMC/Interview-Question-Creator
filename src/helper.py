
from langchain_community.document_loaders import PyPDFLoader
from langchain.docstore.document import Document
from langchain.text_splitter import TokenTextSplitter
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains.summarize import load_summarize_chain
from langchain_community.embeddings.openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from src.prompt import *
import os
from dotenv import load_dotenv


# OpenAI authentication - Force load from .env file
if 'OPENAI_API_KEY' in os.environ:
    del os.environ['OPENAI_API_KEY']  # Clear any cached system variable

load_dotenv(override=True)  # Force reload from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")
print("✅ ENV key loaded:", OPENAI_API_KEY[:15] + "...")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


def file_processing(file_path):
    """Process PDF file and return documents for question generation and answer generation"""
    
    # Load data from PDF
    loader = PyPDFLoader(file_path)
    data = loader.load()

    question_gen = ''
    for page in data:
        question_gen += page.page_content
        
    # Split text for question generation (larger chunks)
    splitter_ques_gen = TokenTextSplitter(
        model_name='gpt-3.5-turbo',
        chunk_size=10000,
        chunk_overlap=200
    )
    chunks_ques_gen = splitter_ques_gen.split_text(question_gen)
    document_ques_gen = [Document(page_content=t) for t in chunks_ques_gen]

    # Split text for answer generation (smaller chunks)
    splitter_ans_gen = TokenTextSplitter(
        model_name='gpt-3.5-turbo',
        chunk_size=1000,
        chunk_overlap=100
    )
    document_answer_gen = splitter_ans_gen.split_documents(document_ques_gen)

    return document_ques_gen, document_answer_gen


def llm_pipeline(file_path):
    """Main pipeline for generating questions and setting up answer generation"""
    
    document_ques_gen, document_answer_gen = file_processing(file_path)

    # Initialize LLM for question generation
    llm_ques_gen_pipeline = ChatOpenAI(
        temperature=0.3,
        model="gpt-3.5-turbo"
    )

    # Create prompts
    PROMPT_QUESTIONS = PromptTemplate(
        template=prompt_template, 
        input_variables=["text"]
    )
    
    REFINE_PROMPT_QUESTIONS = PromptTemplate(
        input_variables=["existing_answer", "text"],
        template=refine_template,
    )

    # Create question generation chain
    ques_gen_chain = load_summarize_chain(
        llm=llm_ques_gen_pipeline, 
        chain_type="refine", 
        verbose=True, 
        question_prompt=PROMPT_QUESTIONS, 
        refine_prompt=REFINE_PROMPT_QUESTIONS
    )
    
    print("📄 Processing document for question generation...")
    print(f"Document chunks: {len(document_ques_gen)}")

    # Generate questions using the correct invoke method
    try:
        ques_result = ques_gen_chain.invoke({"input_documents": document_ques_gen})
        # Extract the output text from the result
        if isinstance(ques_result, dict):
            ques = ques_result.get('output_text', str(ques_result))
        else:
            ques = str(ques_result)
    except Exception as e:
        print(f"❌ Error generating questions: {e}")
        raise

    print("📝 Questions generated successfully!")

    # Create embeddings and vector store for answer generation
    try:
        embeddings = OpenAIEmbeddings()
        vector_store = FAISS.from_documents(document_answer_gen, embeddings)
        print("🔍 Vector store created successfully!")
    except Exception as e:
        print(f"❌ Error creating vector store: {e}")
        raise

    # Initialize LLM for answer generation
    llm_answer_gen = ChatOpenAI(temperature=0.1, model="gpt-3.5-turbo")

    # Process questions list
    ques_list = ques.split("\n")
    # Filter out empty lines and ensure we have actual questions
    filtered_ques_list = [
        element.strip() for element in ques_list 
        if element.strip() and (element.strip().endswith('?') or element.strip().endswith('.'))
    ]
    
    print(f"📋 Generated {len(filtered_ques_list)} questions")
    
    # Create answer generation chain
    answer_generation_chain = RetrievalQA.from_chain_type(
        llm=llm_answer_gen, 
        chain_type="stuff", 
        retriever=vector_store.as_retriever()
    )

    return answer_generation_chain, filtered_ques_list