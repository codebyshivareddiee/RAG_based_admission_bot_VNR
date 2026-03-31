"""Quick script to ingest 2023 cutoff data."""
import os
import subprocess
import sys

def main():
    # Change to the correct directory
    os.chdir(r"c:\Unknown Files\Admission-Chatbot-RAG\RAG_Based_Admission_Chatbot")
    
    print("Starting 2023 cutoff data ingestion...")
    print("This may take a few minutes...")
    
    try:
        # Run the main ingestion script
        result = subprocess.run([
            sys.executable, "ingest_tables_pdfs.py", "--year", "2023"
        ], capture_output=False, text=True)
        
        print(f"\nIngestion completed with return code: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ 2023 cutoff data successfully ingested!")
        else:
            print("❌ Ingestion failed. Check the output above for errors.")
            
    except Exception as e:
        print(f"Error running ingestion: {e}")

if __name__ == "__main__":
    main()