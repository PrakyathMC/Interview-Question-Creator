from fastapi import FastAPI, Form, Request, Response, File, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
import uvicorn
import os
import aiofiles
import json
import csv
from src.helper import llm_pipeline


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_file(request: Request, pdf_file: bytes = File(), filename: str = Form(...)):
    """Upload PDF file and save it to static/docs/"""
    base_folder = 'static/docs/'
    if not os.path.isdir(base_folder):
        os.makedirs(base_folder)
    
    pdf_filename = os.path.join(base_folder, filename)

    try:
        async with aiofiles.open(pdf_filename, 'wb') as f:
            await f.write(pdf_file)
        
        response_data = jsonable_encoder(json.dumps({
            "msg": 'success',
            "pdf_filename": pdf_filename
        }))
        return Response(content=response_data, media_type="application/json")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")


def get_csv(file_path):
    """Generate questions and answers, save to CSV file"""
    try:
        print(f"🔄 Processing file: {file_path}")
        answer_generation_chain, ques_list = llm_pipeline(file_path)
        
        base_folder = 'static/output/'
        if not os.path.isdir(base_folder):
            os.makedirs(base_folder)
        
        output_file = os.path.join(base_folder, "QA.csv")
        
        print(f"💾 Writing {len(ques_list)} Q&A pairs to CSV...")
        
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(["Question", "Answer"])  # Header row

            for i, question in enumerate(ques_list, 1):
                print(f"🤔 Processing question {i}/{len(ques_list)}: {question[:50]}...")
                
                try:
                    # Use invoke instead of run for newer LangChain versions
                    result = answer_generation_chain.invoke({"query": question})
                    
                    # Extract answer from result
                    if isinstance(result, dict):
                        answer = result.get('result', str(result))
                    else:
                        answer = str(result)
                    
                    print(f"✅ Answer generated successfully")
                    
                    # Save to CSV
                    csv_writer.writerow([question, answer])
                    
                except Exception as e:
                    print(f"❌ Error processing question {i}: {e}")
                    csv_writer.writerow([question, f"Error generating answer: {str(e)}"])
        
        print(f"✅ CSV file created: {output_file}")
        return output_file
        
    except Exception as e:
        print(f"❌ Error in get_csv: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.post("/analyze")
async def analyze_file(request: Request, pdf_filename: str = Form(...)):
    """Analyze uploaded PDF and generate Q&A CSV"""
    try:
        if not os.path.exists(pdf_filename):
            raise HTTPException(status_code=404, detail="PDF file not found")
        
        output_file = get_csv(pdf_filename)
        
        response_data = jsonable_encoder(json.dumps({
            "status": "success",
            "output_file": output_file
        }))
        
        return Response(content=response_data, media_type="application/json")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("app:app", host='0.0.0.0', port=8080, reload=True)